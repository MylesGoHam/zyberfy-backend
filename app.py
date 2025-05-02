import os
import logging
import sqlite3

from flask import (
    Flask, render_template, request,
    redirect, url_for, session,
    flash, jsonify
)
from dotenv import load_dotenv
import openai
import stripe

from models import (
    get_db_connection,
    create_users_table,
    create_automation_settings_table,
    create_subscriptions_table,
    create_analytics_events_table,
    get_user_automation,
    log_event
)
from email_utils import send_proposal_email
from datetime import datetime, timedelta
from flask import send_file
import csv
from io import StringIO

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Load config ────────────────────────────────────────────────────────────
load_dotenv()
stripe.api_key           = os.getenv("STRIPE_SECRET_KEY")
openai.api_key           = os.getenv("OPENAI_API_KEY")
PERSONAL_EMAIL           = os.getenv("PERSONAL_EMAIL")
ADMIN_EMAIL              = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD           = os.getenv("ADMIN_PASSWORD")
SECRET_BUNDLE_PRICE_ID   = os.getenv("SECRET_BUNDLE_PRICE_ID")
STRIPE_WEBHOOK_SECRET    = os.getenv("STRIPE_WEBHOOK_SECRET")

# ─── Flask setup ────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

# ─── Database init + migration ───────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()
create_analytics_events_table()

# Ensure stripe_customer_id exists
conn = get_db_connection()
try:
    conn.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;")
    conn.commit()
except sqlite3.OperationalError:
    pass
finally:
    conn.close()

# Seed an admin user if provided
if ADMIN_EMAIL and ADMIN_PASSWORD:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (email, password, first_name, plan_status) "
        "VALUES (?, ?, ?, ?)",
        (ADMIN_EMAIL, ADMIN_PASSWORD, "Admin", "pro")
    )
    conn.commit()
    conn.close()

# ─── Authentication gating ──────────────────────────────────────────────────
# allow anonymous access to these paths:
PUBLIC_PATHS = {
    "/", "/login", "/terms", "/ping", "/stripe_webhook", "/analytics"
}
@app.before_request
def require_login():
    if request.path.startswith("/static/"):
        return  # static assets always public
    if request.path in PUBLIC_PATHS:
        return  # explicitly public endpoints
    if "email" not in session:
        return redirect(url_for("login"))


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email")
        password = request.form.get("password")
        conn     = get_db_connection()
        user     = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and user["password"] == password:
            session["email"]       = email
            session["first_name"]  = user["first_name"]
            session["plan_status"] = user["plan_status"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/ping")
def ping():
    return "pong"


@app.route("/memberships", methods=["GET", "POST"])
def memberships():
    # only logged-in users
    if "email" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        if not request.form.get("terms"):
            flash("You must agree to the Terms of Service.", "error")
            return redirect(url_for("memberships"))

        if not SECRET_BUNDLE_PRICE_ID:
            flash("Payment configuration missing.", "error")
            return redirect(url_for("memberships"))

        try:
            sess = stripe.checkout.Session.create(
                line_items=[{"price": SECRET_BUNDLE_PRICE_ID, "quantity": 1}],
                mode="subscription",
                success_url=url_for("dashboard", _external=True),
                cancel_url =url_for("memberships", _external=True),
            )
            # store stripe customer immediately
            customer_id = sess.customer
            conn = get_db_connection()
            conn.execute(
                "UPDATE users SET stripe_customer_id = ? WHERE email = ?",
                (customer_id, session["email"])
            )
            conn.commit()
            conn.close()
            return redirect(sess.url, code=303)

        except Exception as e:
            logger.exception("Stripe checkout failed: %s", e)
            flash("Could not start payment.", "error")
            return redirect(url_for("memberships"))

    # GET → render plan
    return render_template("memberships.html")


@app.route("/billing-portal")
def billing_portal():
    # only logged-in
    if "email" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    row = conn.execute(
        "SELECT stripe_customer_id FROM users WHERE email = ?", (session["email"],)
    ).fetchone()
    conn.close()

    if not row or not row["stripe_customer_id"]:
        flash("No active subscription found.", "error")
        return redirect(url_for("memberships"))

    portal = stripe.billing_portal.Session.create(
        customer=row["stripe_customer_id"],
        return_url=url_for("dashboard", _external=True)
    )
    return redirect(portal.url, code=303)


@app.route("/stripe_webhook", methods=["POST"])
def stripe_webhook():
    payload    = request.data
    sig_header = request.headers.get('Stripe-Signature')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        logger.exception("Webhook verification failed")
        return jsonify(error=str(e)), 400

    obj = event['data']['object']
    if event['type'] == 'checkout.session.completed':
        cid = obj['customer']
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET plan_status='pro' WHERE stripe_customer_id = ?", (cid,)
        )
        conn.commit()
        conn.close()

    elif event['type'].startswith('invoice.'):
        cid  = obj['customer']
        paid = obj.get('paid', False)
        conn = get_db_connection()
        if not paid:
            conn.execute(
                "UPDATE users SET plan_status='free' WHERE stripe_customer_id = ?", (cid,)
            )
            conn.commit()
        conn.close()

    return jsonify(status='success')


@app.route("/dashboard")
def dashboard():
    # guaranteed logged-in
    conn = get_db_connection()
    row  = conn.execute(
        "SELECT first_name, plan_status FROM users WHERE email = ?",
        (session["email"],)
    ).fetchone()
    conn.close()

    session["plan_status"] = row["plan_status"]
    log_event(session["email"], "pageview")

    return render_template(
        "dashboard.html",
        first_name          = row["first_name"],
        plan_status         = row["plan_status"],
        automation          = get_user_automation(session["email"]),
        automation_complete = bool(get_user_automation(session["email"]))
    )


@app.route("/automation", methods=["POST"])
def save_automation_settings():
    if "email" not in session:
        return redirect(url_for("login"))

    tone = request.form.get("tone", "").strip()
    full_auto = request.form.get("full_auto") == "on"
    smart_offers = request.form.get("smart_offers") == "on"
    output_type = request.form.get("output_type", "concise")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if a settings row already exists
    cursor.execute("SELECT id FROM automation_settings WHERE email = ?", (session["email"],))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            UPDATE automation_settings
            SET tone = ?, full_auto = ?, smart_offers = ?, output_type = ?
            WHERE email = ?
        """, (tone, full_auto, smart_offers, output_type, session["email"]))
    else:
        cursor.execute("""
            INSERT INTO automation_settings (email, tone, full_auto, smart_offers, output_type)
            VALUES (?, ?, ?, ?, ?)
        """, (session["email"], tone, full_auto, smart_offers, output_type))

    conn.commit()
    conn.close()

    flash("Automation settings saved successfully.", "success")
    return redirect(url_for("automation"))


@app.route("/proposal", methods=["GET", "POST"])
def proposal():
    ...
    # keep your existing /proposal implementation
    ...

@app.route("/generate-proposal", methods=["POST"])
def generate_proposal():
    ...
    # keep your existing /generate-proposal implementation
    ...

@app.route("/analytics")
def analytics():
    if "email" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    user = conn.execute(
        "SELECT id FROM users WHERE email = ?", (session["email"],)
    ).fetchone()
    if not user:
        conn.close()
        flash("User not found", "error")
        return redirect(url_for("dashboard"))
    uid = user["id"]

    range_days = int(request.args.get("range", 7))
    since = datetime.utcnow().date() - timedelta(days=range_days)

    # Totals
    pageviews = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_id = ? AND event_type = 'pageview' AND date(timestamp) >= ?",
        (uid, since)
    ).fetchone()["cnt"]
    generated = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_id = ? AND event_type = 'generated_proposal' AND date(timestamp) >= ?",
        (uid, since)
    ).fetchone()["cnt"]
    sent = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_id = ? AND event_type = 'sent_proposal' AND date(timestamp) >= ?",
        (uid, since)
    ).fetchone()["cnt"]
    conversion_rate = (sent / generated * 100) if generated else 0

    # Line Chart Data
    dates = [since + timedelta(days=i) for i in range(range_days)]
    labels = [d.strftime("%b %-d") for d in dates]
    line_data, gen_data, sent_data = [], [], []
    for d in dates:
        date_str = d.isoformat()
        line_data.append(
            conn.execute("SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_id = ? AND event_type = 'pageview' AND date(timestamp) = ?", (uid, date_str)).fetchone()["cnt"]
        )
        gen_data.append(
            conn.execute("SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_id = ? AND event_type = 'generated_proposal' AND date(timestamp) = ?", (uid, date_str)).fetchone()["cnt"]
        )
        sent_data.append(
            conn.execute("SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_id = ? AND event_type = 'sent_proposal' AND date(timestamp) = ?", (uid, date_str)).fetchone()["cnt"]
        )

    # Recent Events
    recent_events = conn.execute(
        "SELECT event_type, timestamp FROM analytics_events WHERE user_id = ? ORDER BY timestamp DESC LIMIT 50", (uid,)
    ).fetchall()

    conn.close()
    return render_template(
        "analytics.html",
        pageviews=pageviews,
        generated=generated,
        sent=sent,
        conversion_rate=round(conversion_rate, 1),
        line_labels=labels,
        line_data=line_data,
        generated_data=gen_data,
        sent_data=sent_data,
        recent_events=recent_events,
        range_days=range_days
    )

@app.route("/analytics-data")
def analytics_data():
    if "email" not in session:
        return jsonify({"error": "unauthorized"}), 401

    range_days = int(request.args.get("range", 7))
    conn = get_db_connection()
    user = conn.execute(
        "SELECT id FROM users WHERE email = ?", (session["email"],)
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "user not found"}), 404
    uid = user["id"]
    since = datetime.utcnow() - timedelta(days=range_days)

    # Totals
    pageviews = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_id = ? AND event_type = 'pageview' AND timestamp >= ?",
        (uid, since)
    ).fetchone()["cnt"]
    generated = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_id = ? AND event_type = 'generated_proposal' AND timestamp >= ?",
        (uid, since)
    ).fetchone()["cnt"]
    sent = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_id = ? AND event_type = 'sent_proposal' AND timestamp >= ?",
        (uid, since)
    ).fetchone()["cnt"]
    conversion_rate = (sent / generated * 100) if generated else 0

    # Dates for graph
    today = datetime.utcnow().date()
    dates = [today - timedelta(days=i) for i in reversed(range(range_days))]
    labels = [d.strftime("%b %-d") for d in dates]

    pv_data, gen_data, sent_data = [], [], []
    for d in dates:
        pv = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_id = ? AND event_type = 'pageview' AND date(timestamp)=?",
            (uid, d)
        ).fetchone()["cnt"]
        gp = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_id = ? AND event_type = 'generated_proposal' AND date(timestamp)=?",
            (uid, d)
        ).fetchone()["cnt"]
        sp = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_id = ? AND event_type = 'sent_proposal' AND date(timestamp)=?",
            (uid, d)
        ).fetchone()["cnt"]
        pv_data.append(pv)
        gen_data.append(gp)
        sent_data.append(sp)

    # Recent events
    recent_events = conn.execute(
        "SELECT event_type, timestamp FROM analytics_events WHERE user_id = ? AND timestamp >= ? ORDER BY timestamp DESC LIMIT 50",
        (uid, since)
    ).fetchall()

    conn.close()

    return jsonify({
        "pageviews": pageviews,
        "generated": generated,
        "sent": sent,
        "conversion_rate": round(conversion_rate, 1),
        "labels": labels,
        "pv_data": pv_data,
        "gen_data": gen_data,
        "sent_data": sent_data,
        "recent_events": [
            {"event_type": e["event_type"], "timestamp": e["timestamp"]} for e in recent_events
        ]
    })

@app.route("/export-analytics")
def export_analytics():
    if "email" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    user = conn.execute(
        "SELECT id FROM users WHERE email = ?", (session["email"],)
    ).fetchone()
    if not user:
        conn.close()
        flash("User not found", "error")
        return redirect(url_for("dashboard"))
    uid = user["id"]

    events = conn.execute(
        "SELECT event_type, timestamp FROM analytics_events WHERE user_id = ? ORDER BY timestamp DESC",
        (uid,)
    ).fetchall()
    conn.close()

    # Write to CSV in memory
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Event Type", "Timestamp"])
    for row in events:
        writer.writerow([row["event_type"], row["timestamp"]])
    output.seek(0)

    return send_file(
        output,
        mimetype="text/csv",
        as_attachment=True,
        download_name="zyberfy_analytics.csv"
    )

@app.route("/log_event", methods=["POST"])
def log_event_route():
    if "email" not in session:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json()
    event_type = data.get("event_type")
    if event_type:
        log_event(session["email"], event_type)
        return jsonify({"status": "ok"}), 200
    return jsonify({"error": "missing event_type"}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0",
            port=int(os.getenv("PORT", 5001)),
            debug=True)
