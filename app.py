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

# ─── Config ─────────────────────────────────────────────────────────────────
load_dotenv()
stripe.api_key     = os.getenv("STRIPE_SECRET_KEY")
openai.api_key     = os.getenv("OPENAI_API_KEY")
PERSONAL_EMAIL     = os.getenv("PERSONAL_EMAIL")
ADMIN_EMAIL        = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD     = os.getenv("ADMIN_PASSWORD")
PRICE_PER_MONTH    = os.getenv("SECRET_BUNDLE_PRICE", "1,497")

# ─── Flask Setup ────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

# ─── DB Init + Migration ─────────────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()
create_analytics_events_table()

# Add stripe_customer_id if missing
conn = get_db_connection()
try:
    conn.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;")
    conn.commit()
except sqlite3.OperationalError:
    pass
conn.close()

# Seed admin
if ADMIN_EMAIL and ADMIN_PASSWORD:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (email, password, first_name, plan_status) "
        "VALUES (?, ?, ?, ?)",
        (ADMIN_EMAIL, ADMIN_PASSWORD, "Admin", "pro")
    )
    conn.commit()
    conn.close()

# ─── Require login on every route except these ───────────────────────────────
PUBLIC_PATHS = {
    "/", "/login", "/terms", "/ping", "/stripe_webhook", "/memberships"
}
@app.before_request
def require_login():
    # allow static assets through
    if request.path.startswith("/static/"):
        return
    # allow the public paths through
    if request.path in PUBLIC_PATHS:
        return
    # otherwise require a user in session
    if "email" not in session:
        return redirect(url_for("login"))


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form["email"]
        password = request.form["password"]
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


@app.route("/memberships", methods=["GET", "POST"])
def memberships():
    # only logged-in users can subscribe
    if "email" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        if not request.form.get("terms"):
            flash("You must agree to the Terms of Service.", "error")
            return redirect(url_for("memberships"))

        price_id = os.getenv("SECRET_BUNDLE_PRICE_ID")
        if not price_id:
            flash("Payment configuration missing.", "error")
            return redirect(url_for("memberships"))

        try:
            sess = stripe.checkout.Session.create(
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=url_for("dashboard", _external=True),
                cancel_url =url_for("memberships", _external=True),
            )
            # persist the new customer ID
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
            logger.exception("Stripe checkout failed: %s", e)
            flash("Could not start payment.", "error")
            return redirect(url_for("memberships"))

    # GET → show the form
    return render_template("memberships.html", price=PRICE_PER_MONTH)


@app.route("/dashboard")
def dashboard():
    # guaranteed logged in
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


@app.route("/analytics")
def analytics():
    # only pro users get here
    if session.get("plan_status") != "pro":
        flash("Analytics is a Pro feature—please subscribe.", "error")
        return redirect(url_for("memberships"))

    conn = get_db_connection()

    # look up user_id
    user = conn.execute(
        "SELECT id FROM users WHERE email = ?", (session["email"],)
    ).fetchone()
    if not user:
        conn.close()
        flash("User not found", "error")
        return redirect(url_for("dashboard"))
    user_id = user["id"]

    # Totals
    pageviews   = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'pageview'",
        (user_id,)
    ).fetchone()["cnt"]
    generated   = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'generated_proposal'",
        (user_id,)
    ).fetchone()["cnt"]
    conversions = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'sent_proposal'",
        (user_id,)
    ).fetchone()["cnt"]
    conversion_rate = (conversions / generated * 100) if generated else 0

    # Last 7 days
    today  = datetime.utcnow().date()
    dates  = [today - timedelta(days=i) for i in reversed(range(7))]
    line_labels = [d.strftime("%b %-d") for d in dates]

    # Build series
    pageviews_data = []
    generated_data = []
    sent_data      = []
    for d in dates:
        pv = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id = ? AND event_type = 'pageview' AND date(timestamp)=?",
            (user_id, d)
        ).fetchone()["cnt"]
        gp = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id = ? AND event_type = 'generated_proposal' AND date(timestamp)=?",
            (user_id, d)
        ).fetchone()["cnt"]
        sp = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id = ? AND event_type = 'sent_proposal' AND date(timestamp)=?",
            (user_id, d)
        ).fetchone()["cnt"]

        pageviews_data.append(pv)
        generated_data.append(gp)
        sent_data.append(sp)

    conn.close()

    return render_template(
        "analytics.html",
        pageviews       = pageviews,
        generated       = generated,
        conversions     = conversions,
        conversion_rate = round(conversion_rate, 1),
        line_labels     = line_labels,
        line_data       = pageviews_data,
        generated_data  = generated_data,
        sent_data       = sent_data
    )


@app.route("/automation", methods=["GET","POST"])
def automation():
    # only Pro users
    if session.get("plan_status") != "pro":
        flash("Automation is a Pro feature—please subscribe.", "error")
        return redirect(url_for("memberships"))

    if request.method == "POST":
        tone, style, notes = (
            request.form.get("tone"),
            request.form.get("style"),
            request.form.get("additional_notes"),
        )
        conn  = get_db_connection()
        exists = conn.execute(
            "SELECT 1 FROM automation_settings WHERE email=?", 
            (session["email"],)
        ).fetchone()

        if exists:
            conn.execute(
                "UPDATE automation_settings "
                "SET tone=?, style=?, additional_notes=? WHERE email=?",
                (tone, style, notes, session["email"])
            )
        else:
            conn.execute(
                "INSERT INTO automation_settings "
                "(email,tone,style,additional_notes) VALUES (?,?,?,?)",
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
    # must be logged in (enforced by @before_request)
    if request.method == "POST":
        lead_name  = request.form["name"]
        lead_email = PERSONAL_EMAIL or request.form["email"]
        budget     = request.form["budget"]
        conn       = get_db_connection()
        auto       = conn.execute(
            "SELECT * FROM automation_settings WHERE email=?", 
            (session["email"],)
        ).fetchone()
        conn.close()

        prompt = (
            f"Write a business proposal email to {lead_name}, budget ${budget}, "
            f"in a {auto['tone']} tone & {auto['style']} style. "
            f"Notes: {auto['additional_notes'] or 'none'}"
        )
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role":"system","content":"You are a helpful assistant."},
                    {"role":"user",  "content":prompt}
                ],
                max_tokens=350, temperature=0.7
            )
            body = resp.choices[0].message.content.strip()
        except Exception as e:
            flash(f"Error generating proposal: {e}", "error")
            return redirect(url_for("proposal"))

        subject = f"Proposal for {lead_name} (Budget: ${budget})"
        r = send_proposal_email(
            to_email=lead_email,
            subject=subject,
            content=body,
            cc_client=False
        )
        if 200 <= getattr(r, "status_code", 0) < 300:
            log_event(session["email"], "sent_proposal")
            flash(f"✅ Proposal sent to {lead_email}", "success")
            return render_template("thank_you.html")

        flash("❌ Failed to send proposal email.", "error")
        return redirect(url_for("proposal"))

    return render_template("proposal.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/ping")
def ping():
    return "pong"


@app.route("/stripe_webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig     = request.headers.get("Stripe-Signature")
    secret  = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except Exception as e:
        logger.exception("Webhook error")
        return jsonify(error=str(e)), 400

    obj = event["data"]["object"]
    if event["type"] == "checkout.session.completed":
        cid = obj["customer"]
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET plan_status='pro' WHERE stripe_customer_id=?",
            (cid,)
        )
        conn.commit()
        conn.close()
    elif event["type"].startswith("invoice."):
        cid  = obj["customer"]
        paid = obj["paid"]
        conn = get_db_connection()
        if not paid:
            conn.execute(
                "UPDATE users SET plan_status='free' WHERE stripe_customer_id=?",
                (cid,)
            )
        conn.commit()
        conn.close()

    return jsonify(status="ok")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5001)), debug=True)
