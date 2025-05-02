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

# ─── DB init & migrations ────────────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()
create_analytics_events_table()

# ensure stripe_customer_id column
conn = get_db_connection()
try:
    conn.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;")
    conn.commit()
except sqlite3.OperationalError:
    pass
finally:
    conn.close()

# seed admin if set
if ADMIN_EMAIL and ADMIN_PASSWORD:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users "
        "(email, password, first_name, plan_status) "
        "VALUES (?, ?, ?, ?)",
        (ADMIN_EMAIL, ADMIN_PASSWORD, "Admin", "pro")
    )
    conn.commit()
    conn.close()

# ─── Authentication gating ──────────────────────────────────────────────────
PUBLIC_PATHS = {
    "/", "/login", "/terms", "/ping", "/stripe_webhook",
}
@app.before_request
def require_login():
    # static always allowed
    if request.path.startswith("/static/"):
        return
    # public endpoints allowed
    if request.path in PUBLIC_PATHS:
        return
    # otherwise must be logged in
    if "email" not in session:
        return redirect(url_for("login"))

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email, password = request.form.get("email"), request.form.get("password")
        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()
        if user and user["password"] == password:
            session.update({
                "email": email,
                "first_name": user["first_name"],
                "plan_status": user["plan_status"]
            })
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

@app.route("/memberships", methods=["GET","POST"])
def memberships():
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
            cust = sess.customer
            conn = get_db_connection()
            conn.execute(
                "UPDATE users SET stripe_customer_id = ? WHERE email = ?",
                (cust, session["email"])
            )
            conn.commit()
            conn.close()
            return redirect(sess.url, code=303)
        except Exception as e:
            logger.exception("Stripe checkout failed")
            flash("Could not start payment.", "error")
            return redirect(url_for("memberships"))
    return render_template("memberships.html", price=session.get("plan_status")!="pro" and "$1,497")

@app.route("/dashboard")
def dashboard():
    conn = get_db_connection()
    row = conn.execute(
        "SELECT first_name, plan_status FROM users WHERE email = ?",
        (session["email"],)
    ).fetchone()
    conn.close()
    session["plan_status"] = row["plan_status"]
    log_event(session["email"], "pageview")
    return render_template(
        "dashboard.html",
        first_name=row["first_name"],
        plan_status=row["plan_status"],
        automation=get_user_automation(session["email"]),
        automation_complete=bool(get_user_automation(session["email"]))
    )

@app.route("/analytics")
def analytics():
    if session.get("plan_status") != "pro":
        flash("Analytics is a Pro feature—please subscribe.", "error")
        return redirect(url_for("memberships"))
    conn = get_db_connection()
    user = conn.execute(
        "SELECT id FROM users WHERE email = ?", (session["email"],)
    ).fetchone()
    if not user:
        conn.close()
        flash("User not found", "error")
        return redirect(url_for("dashboard"))
    uid = user["id"]
    # totals
    pageviews   = conn.execute(
        "SELECT COUNT(*) FROM analytics_events WHERE user_id = ? AND event_type = 'pageview'",
        (uid,)
    ).fetchone()[0]
    generated   = conn.execute(
        "SELECT COUNT(*) FROM analytics_events WHERE user_id = ? AND event_type = 'generated_proposal'",
        (uid,)
    ).fetchone()[0]
    sent        = conn.execute(
        "SELECT COUNT(*) FROM analytics_events WHERE user_id = ? AND event_type = 'sent_proposal'",
        (uid,)
    ).fetchone()[0]
    conv_rate   = round((sent/generated*100),1) if generated else 0

    # last 7 days
    today = datetime.utcnow().date()
    dates = [today - timedelta(days=i) for i in reversed(range(7))]
    labels = [d.strftime("%b %-d") for d in dates]

    pv_data, gen_data, sent_data = [], [], []
    for d in dates:
        pv = conn.execute(
            "SELECT COUNT(*) FROM analytics_events WHERE user_id = ? AND event_type='pageview' AND date(timestamp)=?",
            (uid, d)
        ).fetchone()[0]
        gp = conn.execute(
            "SELECT COUNT(*) FROM analytics_events WHERE user_id = ? AND event_type='generated_proposal' AND date(timestamp)=?",
            (uid, d)
        ).fetchone()[0]
        sp = conn.execute(
            "SELECT COUNT(*) FROM analytics_events WHERE user_id = ? AND event_type='sent_proposal' AND date(timestamp)=?",
            (uid, d)
        ).fetchone()[0]
        pv_data.append(pv)
        gen_data.append(gp)
        sent_data.append(sp)

    conn.close()
    return render_template("analytics.html",
        pageviews=pageviews,
        generated=generated,
        sent=sent,
        conversion_rate=conv_rate,
        line_labels=labels,
        line_data=pv_data,
        generated_data=gen_data,
        sent_data=sent_data
    )

@app.route("/automation", methods=["GET","POST"])
def automation():
    if session.get("plan_status") != "pro":
        flash("Automation is a Pro feature—please subscribe.", "error")
        return redirect(url_for("memberships"))
    if request.method == "POST":
        tone, style, notes = (
            request.form.get("tone"),
            request.form.get("style"),
            request.form.get("additional_notes"),
        )
        conn = get_db_connection()
        exists = conn.execute(
            "SELECT 1 FROM automation_settings WHERE email = ?", (session["email"],)
        ).fetchone()
        if exists:
            conn.execute(
                "UPDATE automation_settings SET tone=?, style=?, additional_notes=? WHERE email=?",
                (tone, style, notes, session["email"])
            )
        else:
            conn.execute(
                "INSERT INTO automation_settings (email, tone, style, additional_notes) VALUES (?, ?, ?, ?)",
                (session["email"], tone, style, notes)
            )
        conn.commit()
        conn.close()
        log_event(session["email"], "saved_automation")
        return redirect(url_for("dashboard"))
    return render_template(
        "automation.html",
        automation=get_user_automation(session["email"]) or {}
    )

@app.route("/proposal", methods=["GET","POST"])
def proposal():
    # ...
    # same as above
    return render_template("proposal.html")

@app.route("/stripe_webhook", methods=["POST"])
def stripe_webhook():
    # ...
    return jsonify(status="success")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5001)), debug=True)
