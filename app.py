import os
import logging
import sqlite3
import uuid
import csv

from flask import (
    Flask, render_template, request,
    redirect, url_for, session,
    flash, jsonify, send_file
)
from dotenv import load_dotenv
from datetime import datetime, timedelta

import openai
import stripe

from models import (
    get_db_connection,
    create_users_table,
    create_automation_settings_table,
    create_subscriptions_table,
    create_analytics_events_table,
    create_proposals_table,
    get_user_automation,
    log_event
)

from email_utils import send_proposal_email

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
create_proposals_table()  # ← This is the fix that ensures your `proposals` table is created

# You’re now ready to continue building routes below…

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

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()

        if user and user["password"] == password:
            session["email"]       = email
            session["first_name"]  = user["first_name"]
            session["plan_status"] = user["plan_status"]
            session["user_id"]     = user["id"]

            # ✅ Auto-create automation_settings if missing
            exists = conn.execute(
                "SELECT 1 FROM automation_settings WHERE email = ?", (email,)
            ).fetchone()
            if not exists:
                conn.execute("""
                    INSERT INTO automation_settings (
                        email, tone, full_auto, accept_offers, reject_offers, length,
                        first_name, company_name, position, website, phone, reply_to, timezone, logo
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user["email"],
                    "friendly",
                    False,
                    True,
                    True,
                    "concise",
                    user["first_name"],
                    user["company_name"],
                    user["position"],
                    user["website"],
                    user["phone"],
                    user["reply_to"],
                    user["timezone"],
                    user["logo"]
                ))
                conn.commit()

            conn.close()
            return redirect(url_for("dashboard"))

        conn.close()
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


@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    endpoint_secret = os.getenv('STRIPE_WEBHOOK_SECRET')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        return 'Invalid signature', 400

    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        customer_email = session_obj.get('customer_email')

        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET plan_status = ? WHERE email = ?",
            ("active", customer_email)
        )
        conn.commit()
        conn.close()

    return '', 200


@app.route("/dashboard")
def dashboard():
    if "email" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    row = conn.execute(
        "SELECT first_name, plan_status FROM users WHERE email = ?",
        (session["email"],)
    ).fetchone()

    # Get automation settings if they exist
    automation_row = conn.execute(
        "SELECT tone FROM automation_settings WHERE email = ?",
        (session["email"],)
    ).fetchone()
    conn.close()

    session["plan_status"] = row["plan_status"]
    log_event(session["email"], "pageview")

    return render_template(
        "dashboard.html",
        first_name=row["first_name"],
        plan_status=row["plan_status"],
        automation=automation_row,
        automation_complete=bool(automation_row)
    )


@app.route("/automation", methods=["GET", "POST"])
def automation():
    if "email" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":
        # Save settings to DB
        conn.execute("""
            INSERT INTO automation_settings (email, tone, full_auto, accept_offers, reject_offers, length,
                                             first_name, company_name, position, website, phone, reply_to, timezone)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                tone=excluded.tone,
                full_auto=excluded.full_auto,
                accept_offers=excluded.accept_offers,
                reject_offers=excluded.reject_offers,
                length=excluded.length,
                first_name=excluded.first_name,
                company_name=excluded.company_name,
                position=excluded.position,
                website=excluded.website,
                phone=excluded.phone,
                reply_to=excluded.reply_to,
                timezone=excluded.timezone
        """, (
            session["email"],
            request.form.get("tone", ""),
            int("full_auto" in request.form),
            int("accept_offers" in request.form),
            int("reject_offers" in request.form),
            request.form.get("length", "concise"),
            request.form.get("first_name", ""),
            request.form.get("company_name", ""),
            request.form.get("position", ""),
            request.form.get("website", ""),
            request.form.get("phone", ""),
            request.form.get("reply_to", ""),
            request.form.get("timezone", "")
        ))
        conn.commit()
        flash("Your automation settings have been updated ✅", "info")
        return redirect(url_for("automation"))

    # Load settings for GET or after saving
    row = conn.execute("""
        SELECT tone, full_auto, accept_offers, reject_offers, length,
               first_name, company_name, position, website, phone, reply_to, timezone
        FROM automation_settings WHERE email = ?
    """, (session["email"],)).fetchone()
    conn.close()

    # Defaults if no settings yet
    settings = {
        "tone": row["tone"] if row else "",
        "full_auto": bool(row["full_auto"]) if row else False,
        "accept_offers": bool(row["accept_offers"]) if row else False,
        "reject_offers": bool(row["reject_offers"]) if row else False,
        "length": row["length"] if row else "concise",
        "first_name": row["first_name"] if row else "Your Name",
        "company_name": row["company_name"] if row else "Your Company",
        "position": row["position"] if row else "",
        "website": row["website"] if row else "",
        "phone": row["phone"] if row else "",
        "reply_to": row["reply_to"] if row else "",
        "timezone": row["timezone"] if row else ""
    }

    # Generate test proposal preview
    prompt = (
        f"Write a {settings['length']} business proposal in a {settings['tone']} tone.\n"
        f"The sender is {settings['first_name']} ({settings['position']}) from {settings['company_name']}.\n"
        f"Their website is {settings['website']}, and they can be reached at {settings['reply_to']} or {settings['phone']}.\n"
        f"Pretend a lead has just inquired and you're writing the first follow-up."
    )

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.7
    )
    preview = response["choices"][0]["message"]["content"].strip()

    return render_template("automation.html", preview=preview, **settings)

@app.route("/automation-preview")
def automation_preview():
    if "email" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    row = conn.execute("""
        SELECT tone, full_auto, accept_offers, reject_offers, length,
               first_name, company_name, position, website, phone, reply_to, timezone
        FROM automation_settings WHERE email = ?
    """, (session["email"],)).fetchone()
    conn.close()

    if not row:
        flash("Please configure your automation settings first.", "error")
        return redirect(url_for("automation"))

    # Extract and format
    settings = {
        "tone": row["tone"],
        "length": row["length"],
        "first_name": row["first_name"],
        "company_name": row["company_name"],
        "position": row["position"],
        "website": row["website"],
        "phone": row["phone"],
        "reply_to": row["reply_to"],
        "timezone": row["timezone"]
    }

    prompt = (
        f"Write a {settings['length']} business proposal in a {settings['tone']} tone.\n"
        f"The sender is {settings['first_name']} ({settings['position']}) from {settings['company_name']}.\n"
        f"Their website is {settings['website']}, and they can be reached at {settings['reply_to']} or {settings['phone']}.\n"
        f"Pretend a lead has just inquired and you're writing the first follow-up."
    )

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.7
    )
    preview = response["choices"][0]["message"]["content"].strip()

    return render_template("automation_preview.html", preview=preview, **settings)

@app.route("/proposal", methods=["GET", "POST"])
def proposal():
    if request.method == "POST":
        name     = request.form.get("name")
        email    = request.form.get("email")
        company  = request.form.get("company")
        details  = request.form.get("details")
        budget   = request.form.get("budget")
        public_id = str(uuid.uuid4())

        conn = get_db_connection()
        conn.execute("""
            INSERT INTO proposals (public_id, name, email, company, details, budget, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (public_id, name, email, company, details, budget))
        conn.commit()
        conn.close()

        flash("Proposal submitted successfully!", "success")
        return redirect(url_for("thank_you", pid=public_id))

    return render_template("proposal.html")

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

    # Aggregate totals (1 query)
    totals = conn.execute("""
        SELECT 
            event_type, 
            COUNT(*) AS cnt 
        FROM analytics_events 
        WHERE user_id = ? AND date(timestamp) >= ? 
        GROUP BY event_type
    """, (uid, since)).fetchall()

    # Map totals
    stats = {row["event_type"]: row["cnt"] for row in totals}
    pageviews = stats.get("pageview", 0)
    generated = stats.get("generated_proposal", 0)
    sent = stats.get("sent_proposal", 0)
    conversion_rate = (sent / generated * 100) if generated else 0

    # Line Chart Data (1 query total, not 3 per day)
    raw = conn.execute("""
        SELECT 
            event_type, 
            DATE(timestamp) as day, 
            COUNT(*) AS cnt 
        FROM analytics_events 
        WHERE user_id = ? AND date(timestamp) >= ? 
        GROUP BY event_type, day
    """, (uid, since)).fetchall()

    # Organize by date
    date_map = {d.strftime("%Y-%m-%d"): i for i, d in enumerate([since + timedelta(days=i) for i in range(range_days)])}
    line_data = [0] * range_days
    gen_data = [0] * range_days
    sent_data = [0] * range_days

    for row in raw:
        idx = date_map.get(row["day"])
        if idx is not None:
            if row["event_type"] == "pageview":
                line_data[idx] = row["cnt"]
            elif row["event_type"] == "generated_proposal":
                gen_data[idx] = row["cnt"]
            elif row["event_type"] == "sent_proposal":
                sent_data[idx] = row["cnt"]

    labels = [(since + timedelta(days=i)).strftime("%b %-d") for i in range(range_days)]

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

    # Line chart data
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
        """
        SELECT event_type, timestamp 
        FROM analytics_events 
        WHERE user_id = ? 
        ORDER BY datetime(timestamp) DESC 
        LIMIT 50
        """,
        (uid,)
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

@app.route("/subscribe", methods=["POST"])
def subscribe():
    if "email" not in session:
        return redirect(url_for("login"))

    # Confirm terms were agreed to
    agreed = request.form.get("terms")
    if not agreed:
        flash("You must agree to the Terms of Service.")
        return redirect(url_for("memberships"))

    # You could trigger Stripe checkout or update the user's plan in your DB here
    conn = get_db_connection()
    conn.execute("UPDATE users SET plan_status = ? WHERE email = ?", ("elite", session["email"]))
    conn.commit()
    conn.close()

    flash("Subscription successful! You now have full access.")
    return redirect(url_for("dashboard"))


@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    if "email" not in session:
        return redirect("/login")

    try:
        checkout_session = stripe.checkout.Session.create(
            customer_email=session["email"],
            payment_method_types=["card"],
            line_items=[
                {
                    "price": "price_1RGEnNKpgIhBPea4U7GbbWJd",  # Your real Stripe price ID (Pro)
                    "quantity": 1,
                }
            ],
            mode="subscription",
            success_url=url_for("dashboard", _external=True),
            cancel_url=url_for("memberships", _external=True),
        )
        return redirect(checkout_session.url, code=303)

    except Exception as e:
        return jsonify(error=str(e)), 400
    

@app.route('/settings')
def settings():
    if 'email' not in session:
        return redirect(url_for('login'))

    # Temporary mock user object for display only
    mock_user = {
        "first_name": "Admin",
        "company_name": "Zyberfy",
        "position": "Founder",
        "website": "https://zyberfy.com",
        "phone": "+1 (555) 123-4567",
        "reply_to": "hello@zyberfy.com",
        "timezone": "PST",
        "logo": None  # Add later if needed
    }

    return render_template('settings.html', user=mock_user)

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

@app.route("/proposal/view/<pid>")
def view_proposal(pid):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM proposals WHERE public_id = ?", (pid,)).fetchone()
    conn.close()
    if not row:
        return "Proposal not found.", 404

    log_event(row["email"], "viewed_shared_proposal")  # optional tracking
    return render_template("public_proposal.html", proposal=row)

@app.route("/thank-you")
def thank_you():
    pid = request.args.get("pid")
    if not pid:
        return redirect(url_for("proposal"))
    full_url = url_for("view_proposal", pid=pid, _external=True)
    return render_template("thank_you.html", proposal_url=full_url)

@app.route("/patch-users-columns")
def patch_users_columns():
    conn = get_db_connection()
    try:
        for column in [
            "company_name TEXT",
            "position TEXT",
            "website TEXT",
            "phone TEXT",
            "reply_to TEXT",
            "timezone TEXT",
            "logo TEXT"
        ]:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {column};")
            except sqlite3.OperationalError:
                pass
        conn.commit()
        return "Users table successfully patched on Render."
    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        conn.close()



if __name__ == "__main__":
    app.run(host="0.0.0.0",
            port=int(os.getenv("PORT", 5001)),
            debug=True)
