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

# Load environment variables before using them
load_dotenv()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

from models import (
    get_db_connection,
    create_users_table,
    create_automation_settings_table,
    create_subscriptions_table,
    create_analytics_events_table,
    create_proposals_table,
    create_offers_table,
    get_user_automation,
    log_event
)

from email_utils import send_proposal_email
from email_assistant import handle_new_proposal

import qrcode
from sms_utils import send_sms_alert
from flask import g

import logging
logging.basicConfig(level=logging.DEBUG)

from pathlib import Path

import uuid
import requests
from notifications import send_onesignal_notification

from models import get_db_connection, generate_slugified_id

def handle_new_proposal(name, email, company, services, budget, timeline, message, user_email):
    conn = get_db_connection()

    # 🧠 Generate public_id from name/company/services
    base_slug = name or company or services or "client"
    public_id = generate_slugified_id(base_slug)

    conn.execute("""
        INSERT INTO proposals (
            public_id, user_email, lead_name, lead_email, lead_company,
            services, budget, timeline, message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        public_id, user_email, name, email, company,
        services, budget, timeline, message
    ))
    conn.commit()

    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return pid

# --- QR Code Generator Function ---
def generate_qr_code(public_id, base_url):
    try:
        url = f"{base_url}proposal/{public_id}"
        qr = qrcode.make(url)
        output_path = os.path.join("static", "qr")
        os.makedirs(output_path, exist_ok=True)
        full_path = os.path.join(output_path, f"proposal_{public_id}.png")
        qr.save(full_path)
        print(f"[QR] Saved QR to {full_path}")
    except Exception as e:
        print(f"[QR ERROR] Failed to generate QR: {e}")

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
create_proposals_table()

# Add stripe_customer_id column if missing
import os

# Auto-delete old DB on Render if REDEPLOY_FORCE_DB is set
if os.getenv("REDEPLOY_FORCE_DB") == "1" and os.path.exists("zyberfy.db"):
    os.remove("zyberfy.db")
    print("✅ Deleted stale zyberfy.db for fresh deployment.")

conn = get_db_connection()
try:
    conn.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;")
    conn.commit()
except sqlite3.OperationalError:
    pass
finally:
    conn.close()

# Seed admin user if credentials are set
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
@app.before_request
def restrict_routes():
    PUBLIC_PATHS = {
        "/", 
        "/login", 
        "/signup", 
        "/test_proposal", 
        "/proposal", 
        "/proposal/", 
        "/proposal/public", 
        "/proposal_view", 
        "/landing",
        "/test-stripe-signup"
    }

    print(f"[DEBUG] PUBLIC_PATHS: {PUBLIC_PATHS}")
    print(f"[DEBUG] Incoming path: {request.path}")

    if request.path.startswith("/proposal/"):
        print("[DEBUG] Access granted to public proposal page")
        return

    if request.path.startswith("/thank-you"):
        print("[DEBUG] Access granted to thank-you page")
        return

    for public_path in PUBLIC_PATHS:
        if request.path.startswith(public_path):
            return

    if "email" not in session:
        return "Unauthorized", 403
# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/admin")
def admin_entrypoint():
    return redirect(url_for("admin_dashboard"))

@app.route("/admin_dashboard")
def admin_dashboard():
    if "email" not in session or not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_proposals = conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]
    active_subscriptions = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'").fetchone()[0]
    conn.close()

    return render_template("admin_dashboard.html", total_users=total_users, total_proposals=total_proposals, active_subscriptions=active_subscriptions)


@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and user["password"] == password and user["is_admin"] == 1:
            session["email"] = email
            session["is_admin"] = user["is_admin"]
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid admin credentials", "error")
            return redirect(url_for("admin_login"))

    return render_template("admin_login.html")

@app.route("/analytics")
def analytics():
    if "email" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    user_email = session["email"]

    range_days = int(request.args.get("range", 7))
    since_dt = datetime.utcnow() - timedelta(days=range_days)
    since = since_dt.isoformat()

    # Aggregate totals
    totals = conn.execute("""
        SELECT 
            event_name, 
            COUNT(*) AS cnt 
        FROM analytics_events 
        WHERE user_email = ? AND timestamp >= ? 
        GROUP BY event_name
    """, (user_email, since)).fetchall()

    stats = {row["event_name"]: row["cnt"] for row in totals}
    pageviews = stats.get("pageview", 0)
    generated = stats.get("generated_proposal", 0)
    sent = stats.get("sent_proposal", 0)
    conversion_rate = (sent / generated * 100) if generated else 0

    # Line chart data
    raw = conn.execute("""
        SELECT 
            event_name, 
            DATE(timestamp) as day, 
            COUNT(*) AS cnt 
        FROM analytics_events 
        WHERE user_email = ? AND timestamp >= ? 
        GROUP BY event_name, day
    """, (user_email, since)).fetchall()

    date_map = {
        (since_dt + timedelta(days=i)).strftime("%Y-%m-%d"): i
        for i in range(range_days)
    }
    line_data = [0] * range_days
    gen_data = [0] * range_days
    sent_data = [0] * range_days

    for row in raw:
        idx = date_map.get(row["day"])
        if idx is not None:
            if row["event_name"] == "pageview":
                line_data[idx] = row["cnt"]
            elif row["event_name"] == "generated_proposal":
                gen_data[idx] = row["cnt"]
            elif row["event_name"] == "sent_proposal":
                sent_data[idx] = row["cnt"]

    labels = [
        (since_dt + timedelta(days=i)).strftime("%b %-d")
        for i in range(range_days)
    ]

    recent_events = conn.execute(
        "SELECT event_name, timestamp FROM analytics_events WHERE user_email = ? ORDER BY timestamp DESC LIMIT 50",
        (user_email,)
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

    user_email = session["email"]
    range_days = int(request.args.get("range", 7))
    conn = get_db_connection()

    since_dt = datetime.utcnow() - timedelta(days=range_days)
    since = since_dt.isoformat()

    # Labels and date map
    dates = [since_dt + timedelta(days=i) for i in range(range_days)]
    labels = [d.strftime("%b %-d") for d in dates]

    # Totals
    pageviews = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_email = ? AND event_name = 'pageview' AND timestamp >= ?",
        (user_email, since)
    ).fetchone()["cnt"]
    generated = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_email = ? AND event_name = 'generated_proposal' AND timestamp >= ?",
        (user_email, since)
    ).fetchone()["cnt"]
    sent = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_email = ? AND event_name = 'sent_proposal' AND timestamp >= ?",
        (user_email, since)
    ).fetchone()["cnt"]
    conversion_rate = (sent / generated * 100) if generated else 0

    # Daily breakdown
    pv_data, gen_data, sent_data = [], [], []
    for d in dates:
        date_str = d.strftime("%Y-%m-%d")
        pv = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_email = ? AND event_name = 'pageview' AND DATE(timestamp) = ?",
            (user_email, date_str)
        ).fetchone()["cnt"]
        gp = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_email = ? AND event_name = 'generated_proposal' AND DATE(timestamp) = ?",
            (user_email, date_str)
        ).fetchone()["cnt"]
        sp = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events WHERE user_email = ? AND event_name = 'sent_proposal' AND DATE(timestamp) = ?",
            (user_email, date_str)
        ).fetchone()["cnt"]
        pv_data.append(pv)
        gen_data.append(gp)
        sent_data.append(sp)

    # Recent events
    recent_events = conn.execute(
        """
        SELECT event_name, timestamp 
        FROM analytics_events 
        WHERE user_email = ? 
        ORDER BY datetime(timestamp) DESC 
        LIMIT 50
        """,
        (user_email,)
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
            {"event_type": e["event_name"], "timestamp": e["timestamp"]} for e in recent_events
        ]
    })

@app.route("/automation", methods=["GET", "POST"])
def automation():
    if "email" not in session:
        return redirect(url_for("login"))

    user_email = session["email"]
    preview = None

    # Handle POST actions
    if request.method == "POST":
        # Reset settings
        if "reset" in request.form:
            conn = sqlite3.connect("zyberfy.db")
            c = conn.cursor()
            c.execute("DELETE FROM automation_settings WHERE email = ?", (user_email,))
            conn.commit()
            conn.close()
            flash("Automation settings reset to default.")
            return redirect(url_for("automation"))

        # Test Proposal Preview
        elif "test_preview" in request.form:
            row = get_user_automation(user_email)
            settings = dict(row) if row else {}

            tone = settings.get("tone", "friendly")
            length = settings.get("length", "concise")
            first_name = settings.get("first_name", "Your Name")
            position = settings.get("position", "")
            company_name = settings.get("company_name", "Your Company")
            website = settings.get("website", "example.com")
            phone = settings.get("phone", "123-456-7890")
            reply_to = settings.get("reply_to", "contact@example.com")

            prompt = (
                f"Write a {length} business proposal in a {tone} tone.\n"
                f"The sender is {first_name} ({position}) from {company_name}.\n"
                f"Their website is {website}, and they can be reached at {reply_to} or {phone}.\n"
                f"Pretend a lead has just inquired and you're writing the first follow-up."
            )

            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7
            )

            preview = response["choices"][0]["message"]["content"].strip()

        # Save settings
        else:
            tone = request.form.get("tone", "")
            length = request.form.get("length", "concise")
            full_auto = "full_auto" in request.form
            accept_offers = "accept_offers" in request.form
            reject_offers = "reject_offers" in request.form

            conn = sqlite3.connect("zyberfy.db")
            c = conn.cursor()
            c.execute("""
                INSERT INTO automation_settings (email, tone, length, full_auto, accept_offers, reject_offers)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    tone = excluded.tone,
                    length = excluded.length,
                    full_auto = excluded.full_auto,
                    accept_offers = excluded.accept_offers,
                    reject_offers = excluded.reject_offers
            """, (user_email, tone, length, int(full_auto), int(accept_offers), int(reject_offers)))
            conn.commit()
            conn.close()
            flash("Settings saved successfully!")

    # GET logic (load settings or defaults)
    row = get_user_automation(user_email)
    settings = dict(row) if row else {
        "tone": "",
        "length": "concise",
        "full_auto": False,
        "accept_offers": False,
        "reject_offers": False
    }

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

@app.route("/billing")
def billing():
    if "email" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    user = conn.execute(
        """
        SELECT u.plan_status, s.stripe_subscription_id
        FROM users u
        LEFT JOIN subscriptions s ON u.email = s.email
        WHERE u.email = ?
        """,
        (session["email"],)
    ).fetchone()
    conn.close()

    plan_name = "Elite"
    status = "Active" if user and user["stripe_subscription_id"] else "Inactive"
    created_at = None

    if user and user["stripe_subscription_id"]:
        try:
            sub = stripe.Subscription.retrieve(user["stripe_subscription_id"])
            created_at = datetime.utcfromtimestamp(sub.created).strftime('%B %d, %Y')
        except Exception as e:
            print("[ERROR] Stripe fetch failed:", e)

    return render_template(
        "billing.html",
        plan_name=plan_name,
        status=status,
        created_at=created_at
    )

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
                    "price": os.getenv("SECRET_BUNDLE_PRICE_ID"),
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
    
@app.route("/dashboard")
def dashboard():
    try:
        # ✅ Check login session
        if "email" not in session:
            return redirect(url_for("login"))

        conn = get_db_connection()

        # ✅ Get user + settings info (LEFT JOIN ensures we still get user even if settings are missing)
        user_row = conn.execute("""
            SELECT users.first_name AS user_first_name, users.plan_status, users.public_id,
                   settings.first_name AS settings_first_name,
                   settings.company_name, settings.position, settings.website,
                   settings.phone, settings.reply_to
            FROM users
            LEFT JOIN settings ON users.email = settings.email
            WHERE users.email = ?
        """, (session["email"],)).fetchone()

        if not user_row:
            raise Exception("User/settings data not found for email: " + session["email"])

        # ✅ Get all automation settings (not just tone anymore)
        automation_row = conn.execute(
            "SELECT * FROM automation_settings WHERE email = ?",
            (session["email"],)
        ).fetchone()

        # ✅ Get total proposals generated by this user
        proposal_count_row = conn.execute(
            "SELECT COUNT(*) AS total FROM proposals WHERE user_email = ?",
            (session["email"],)
        ).fetchone()
        proposal_count = proposal_count_row["total"] if proposal_count_row else 0

        conn.close()

        # ✅ Generate QR code if missing
        if user_row["public_id"]:
            qr_path = f"static/qr/proposal_{user_row['public_id']}.png"
            if not Path(qr_path).exists():
                generate_qr_code(user_row["public_id"], request.host_url)

        # ✅ Save current plan status into session
        session["plan_status"] = user_row["plan_status"]

        # ✅ Determine if onboarding is incomplete (based on required fields from settings)
        onboarding_incomplete = any([
            not (user_row["settings_first_name"] or "").strip(),
            not (user_row["company_name"] or "").strip(),
            not (user_row["position"] or "").strip(),
            not (user_row["website"] or "").strip(),
            not (user_row["phone"] or "").strip(),
            not (user_row["reply_to"] or "").strip()
        ])

        # ✅ Render dashboard with required values
        return render_template(
            "dashboard.html",
            user=user_row,
            automation_complete=bool(automation_row),
            onboarding_incomplete=onboarding_incomplete,
            proposal_count=proposal_count
        )

    except Exception as e:
        return f"<pre>🔥 DASHBOARD ERROR: {e}</pre>", 500
    

@app.route("/dashboard_proposal", methods=["GET", "POST"])
def dashboard_proposal():
    if "email" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    user = conn.execute("SELECT public_id FROM users WHERE email = ?", (session["email"],)).fetchone()
    conn.close()

    if not user:
        return "User not found", 404

    public_id = user["public_id"]

    # ✅ Save public_id in session if not already
    session["public_id"] = public_id

    # ✅ Generate QR code for /proposal/<public_id> if missing
    if public_id:
        qr_path = f"static/qr/proposal_{public_id}.png"
        if not Path(qr_path).exists():
            full_url = f"{request.host_url}proposal/{public_id}"
            qr = qrcode.make(full_url)
            qr.save(qr_path)
            print(f"[QR] Created: {qr_path}")

    return render_template(
        "dashboard_proposal.html",
        public_id=public_id,
        show_qr=True
    )

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
        "SELECT event_name, timestamp FROM analytics_events WHERE user_id = ? ORDER BY timestamp DESC",
        (uid,)
    ).fetchall()
    conn.close()

    # Write to CSV in memory
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Event Name", "Timestamp"])
    for row in events:
        writer.writerow([row["event_name"], row["timestamp"]])
    output.seek(0)

    return send_file(
        output,
        mimetype="text/csv",
        as_attachment=True,
        download_name="zyberfy_analytics.csv"
    )

@app.route("/generate_qr")
def generate_qr():
    if "email" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    row = conn.execute("SELECT public_id FROM users WHERE email = ?", (session["email"],)).fetchone()
    conn.close()

    if not row or not row["public_id"]:
        flash("No public ID found for your account.", "danger")
        return redirect(url_for("dashboard"))

    public_id = row["public_id"]
    link = f"{request.host_url}proposal/{public_id}"

    # Save to user-specific QR path
    filename = f"proposal_{public_id}.png"
    qr_path = os.path.join("static", "qr", filename)
    os.makedirs("static/qr", exist_ok=True)

    # Generate QR
    img = qrcode.make(link)
    img.save(qr_path)

    flash("QR code generated successfully!", "success")
    return redirect(url_for("proposal"))

@app.route("/landing")
def landing_page():
    return render_template("landing_page.html")


@app.route("/log_event", methods=["POST"])
def log_event_route():
    if "email" not in session:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json()
    event_type = data.get("event_type")
    referrer = request.referrer or "unknown"

    if event_type:
        print(f"[EVENT] {event_type} from {referrer}")
        log_event(
            event_name=event_type,
            user_email=session["email"],
            metadata={"referrer": referrer}
        )
        return jsonify({"status": "ok"}), 200

    return jsonify({"error": "missing event_type"}), 400


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

            # Prepare safe fallback values
            first_name   = user["first_name"] or ""
            company_name = user["company_name"] if "company_name" in user.keys() else ""
            position     = user["position"] if "position" in user.keys() else ""
            website      = user["website"] if "website" in user.keys() else ""
            phone        = user["phone"] if "phone" in user.keys() else ""
            reply_to     = user["reply_to"] if "reply_to" in user.keys() else ""
            timezone     = user["timezone"] if "timezone" in user.keys() else ""
            logo         = user["logo"] if "logo" in user.keys() else None

            # Auto-create automation_settings if missing
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
                    email,
                    "friendly",
                    False,
                    True,
                    True,
                    "concise",
                    first_name,
                    company_name,
                    position,
                    website,
                    phone,
                    reply_to,
                    timezone,
                    logo
                ))
                conn.commit()

            conn.close()
            print(f"[LOGIN] Success for {email}")
            return redirect(url_for("dashboard"))

        conn.close()
        flash("Invalid email or password", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


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


@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if request.method == "POST":
        email = request.form.get("email")
        first_name = request.form.get("first_name")
        position = request.form.get("position")
        company_name = request.form.get("company_name")
        website = request.form.get("website")
        phone = request.form.get("phone")
        tone = request.form.get("tone")
        length = request.form.get("length")
        reply_to = request.form.get("reply_to")

        conn = get_db_connection()
        conn.execute("""
            INSERT OR REPLACE INTO automation_settings (
                user_email, first_name, position, company_name, website,
                phone, tone, length, reply_to
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (email, first_name, position, company_name, website, phone, tone, length, reply_to))
        conn.commit()
        conn.close()

        flash("Automation settings saved successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("onboarding.html")


@app.route("/ping")
def ping():
    return "pong"


@app.route("/proposal", methods=["GET", "POST"])
def proposal():
    if "email" not in session:
        return redirect(url_for("login"))

    user_email = session["email"]
    conn = get_db_connection()

    # ✅ Get full user row to show template data (like logo, etc.)
    user = conn.execute("SELECT * FROM users WHERE email = ?", (user_email,)).fetchone()

    # ✅ On GET — use latest proposal's public_id (if any)
    proposal_row = conn.execute("""
        SELECT public_id FROM proposals 
        WHERE user_email = ? ORDER BY created_at DESC LIMIT 1
    """, (user_email,)).fetchone()
    public_id = proposal_row["public_id"] if proposal_row else user["public_id"]

    if request.method == "POST":
        name     = request.form.get("name")
        email    = request.form.get("email")
        company  = request.form.get("company")
        services = request.form.get("services")
        budget   = request.form.get("budget")
        timeline = request.form.get("timeline")
        message  = request.form.get("message")

        pid = handle_new_proposal(name, email, company, services, budget, timeline, message, user_email)
        conn.close()

        if pid:
            # ✅ Grab new proposal's public_id
            conn = get_db_connection()
            row = conn.execute("SELECT public_id FROM proposals WHERE id = ?", (pid,)).fetchone()
            public_id = row["public_id"] if row else "client-" + uuid.uuid4().hex[:6]
            conn.close()

            # ✅ Generate new QR code
            generate_qr_code(public_id, request.host_url)

            return redirect(url_for("thank_you", pid=pid))
        else:
            flash("Error creating proposal", "error")
            return redirect(url_for("proposal"))

    conn.close()
    return render_template("dashboard_proposal.html", show_qr=True, public_id=public_id, user=user)



@app.route("/proposal/<public_id>", methods=["GET", "POST"])
def public_proposal(public_id):
    import os, qrcode

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE public_id = ?", (public_id,)).fetchone()
    conn.close()

    if not user:
        return "Invalid proposal link.", 404

    client_email = user["email"]
    show_qr = session.get("email") == client_email
    is_client = session.get("email") == client_email
    viewed_key = f"viewed_{public_id}"

    # ✅ Log view once per session
    if not is_client and not session.get(viewed_key):
        session[viewed_key] = True
        print(f"[TRACK] Logging pageview for client: {client_email} from public_id: {public_id}")
        log_event(
            event_name="pageview",
            user_email=client_email,
            metadata={"public_id": public_id, "source": "public_proposal"}
        )
    else:
        print(f"[TRACK] Pageview skipped — already viewed or by client: {public_id}")

    # ✅ Generate QR if missing
    qr_path = f"static/qr/proposal_{public_id}.png"
    full_link = f"https://zyberfy.com/proposal/{public_id}"
    if not os.path.exists(qr_path):
        img = qrcode.make(full_link)
        img.save(qr_path)
        print(f"[QR] Created QR for {full_link}")

    # ✅ Handle form submit
    if request.method == "POST":
        name     = request.form.get("name")
        email    = request.form.get("email")
        company  = request.form.get("company")
        services = request.form.get("services")
        budget   = request.form.get("budget")
        timeline = request.form.get("timeline")
        message  = request.form.get("message")

        pid = handle_new_proposal(name, email, company, services, budget, timeline, message, client_email)
        if pid:
            send_onesignal_notification(
            title="New Proposal Submitted",
            message=f"{name} just submitted a proposal to {client_email}.",
            public_id=public_id,
            proposal_id=pid 
)
            return redirect(url_for("thank_you", pid=pid))
        else:
            flash("Failed to send proposal. Try again.", "error")
            return redirect(url_for("public_proposal", public_id=public_id))

    # ✅ Final render
    return render_template(
        "public_proposal.html",
        user=user,
        public_id=public_id,
        show_qr=show_qr,
        public_link=full_link
    )


@app.route("/proposal_view/<int:pid>", methods=["GET", "POST"])
def proposal_view(pid):
    conn = get_db_connection()
    proposal = conn.execute("SELECT * FROM proposals WHERE id = ?", (pid,)).fetchone()

    if not proposal:
        return "Proposal not found", 404

    # ✅ Log receipt view
    log_event(
        event_name="proposal_viewed",
        user_email=proposal["client_email"],
        metadata={"proposal_id": pid}
    )

    if request.method == "POST":
        action = request.form.get("action")
        if action in ["approved", "declined"]:
            conn.execute("UPDATE proposals SET status = ? WHERE id = ?", (action, pid))
            conn.commit()

            # ✅ Log approval or decline
            log_event(
                event_name=f"proposal_{action}",
                user_email=proposal["client_email"],
                metadata={"proposal_id": pid}
            )

            flash(f"Proposal {action.capitalize()}!", "success")
            return redirect(url_for("proposal_view", pid=pid))

    conn.close()
    return render_template("proposal_receipt.html", proposal=proposal)



@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "email" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":
        # ✅ Save automation/business settings
        conn.execute("""
            INSERT INTO automation_settings (
                email, first_name, last_name, company_name, position,
                website, phone, reply_to, timezone
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                company_name = excluded.company_name,
                position = excluded.position,
                website = excluded.website,
                phone = excluded.phone,
                reply_to = excluded.reply_to,
                timezone = excluded.timezone
        """, (
            session["email"],
            request.form.get("first_name", ""),
            request.form.get("last_name", ""),
            request.form.get("company_name", ""),
            request.form.get("position", ""),
            request.form.get("website", ""),
            request.form.get("phone", ""),
            request.form.get("reply_to", ""),
            request.form.get("timezone", "")
        ))

        # ✅ Save notification preference
        notifications_enabled = request.form.get("notifications_enabled") == "on"
        conn.execute("UPDATE users SET notifications_enabled = ? WHERE email = ?", (int(notifications_enabled), session["email"]))

        # ✅ Handle password change
        new_pw = request.form.get("new_password")
        confirm_pw = request.form.get("confirm_password")
        if new_pw and new_pw == confirm_pw:
            conn.execute("UPDATE users SET password = ? WHERE email = ?", (new_pw, session["email"]))

        conn.commit()
        conn.close()

        flash("Settings updated successfully ✅", "info")
        return redirect(url_for("settings"))

    # ✅ Load automation settings
    settings = conn.execute("""
        SELECT first_name, last_name, company_name, position,
               website, phone, reply_to, timezone
        FROM automation_settings WHERE email = ?
    """, (session["email"],)).fetchone()

    settings = dict(settings) if settings else {}

    # ✅ Load notification preference from users table
    user = conn.execute("SELECT notifications_enabled FROM users WHERE email = ?", (session["email"],)).fetchone()
    if user:
        settings["notifications_enabled"] = user["notifications_enabled"]
    else:
        settings["notifications_enabled"] = 1  # Default to ON if not set

    conn.close()
    return render_template("settings.html", settings=settings)



@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]  # Add your hashing logic here
        public_id = str(uuid.uuid4())[:8]

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO users (email, password, public_id) VALUES (?, ?, ?)",
            (email, password, public_id)
        )
        conn.commit()
        conn.close()

        flash("Account created! You can now log in.", "success")
        return redirect(url_for("login"))
    
    return render_template("signup.html")


@app.route('/sms-handler', methods=['POST'])
def sms_handler():
    data = request.json
    sender = data.get("from")
    message = data.get("message")
    timestamp = data.get("timestamp")

    print(f"[SMS] {timestamp} - From {sender}: {message}")
    return jsonify({"status": "received"}), 200


@app.route("/submit_offer", methods=["POST"])
def submit_offer():
    form_id = request.form.get("form_id")
    offer_amount = request.form.get("offer_amount")

    if not form_id or not offer_amount:
        flash("Missing required fields.", "error")
        return redirect(request.referrer or "/")

    try:
        conn = get_db_connection()
        conn.execute("""
            INSERT INTO offers (public_id, offer_amount)
            VALUES (?, ?)
        """, (form_id, offer_amount))
        conn.commit()

        # Lookup user_email from proposals
        row = conn.execute("SELECT user_email FROM proposals WHERE public_id = ?", (form_id,)).fetchone()
        user_email = row["user_email"] if row else None
        conn.close()

        # Log event
        if user_email:
            log_event("offer_submitted", user_email=user_email, metadata={"public_id": form_id, "amount": offer_amount})

        flash("Offer submitted successfully!", "success")
        return redirect(url_for("public_proposal", public_id=form_id))

    except Exception as e:
        print("[ERROR] Offer submission failed:", e)
        flash("There was an error submitting your offer.", "error")
        return redirect(url_for("public_proposal", public_id=form_id))
    

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

@app.route("/terms")
def terms():
    return render_template("terms.html")



@app.route("/test-stripe-signup")
def test_stripe_signup():
    email = "testsignup@example.com"
    first_name = "Test"
    plan_status = "starter"
    price_id = "price_1RERprKpgIhBPea4U7zezbWd"

    conn = get_db_connection()

    # Insert test user if not exists
    conn.execute("""
        INSERT OR IGNORE INTO users (email, password, first_name, plan_status)
        VALUES (?, ?, ?, ?)
    """, (email, "test1234", first_name, plan_status))

    # Insert dummy subscription
    conn.execute("""
        INSERT OR IGNORE INTO subscriptions (email, plan, status)
        VALUES (?, ?, ?)
    """, (email, "Starter", "active"))

    conn.commit()
    conn.close()

    # Set session
    session["email"] = email

    return redirect(url_for("dashboard"))


@app.route("/test-success")
def test_success():
    session_id = request.args.get("session_id")
    if not session_id:
        return "Missing session ID", 400

    # Fetch details from Stripe (optional)
    session_data = stripe.checkout.Session.retrieve(session_id)

    # Simulate user creation
    conn = get_db_connection()
    conn.execute("""
        INSERT OR IGNORE INTO users (email, password, first_name, plan_status)
        VALUES (?, ?, ?, ?)
    """, (session_data.customer_email, "dummy123", "Test User", "elite"))
    conn.commit()
    conn.close()

    session["email"] = session_data.customer_email

    return "✅ Test user created and logged in. You can now visit the dashboard."

@app.route("/test_proposal", methods=["GET"])
def test_proposal():
    if "email" not in session:
        return redirect(url_for("login"))

    user_email = session["email"]
    settings = get_user_automation(user_email)

    if not settings:
        flash("No automation settings found.", "error")
        return redirect(url_for("automation"))

    # Pull user data safely from settings Row object
    tone = settings["tone"] or "friendly"
    length = settings["length"] or "concise"
    first_name = settings["first_name"] or "Your Name"
    position = settings["position"] or ""
    company_name = settings["company_name"] or "Your Company"
    website = settings["website"] or "example.com"
    phone = settings["phone"] or "123-456-7890"
    reply_to = settings["reply_to"] or "contact@example.com"

    # Create prompt
    prompt = (
        f"Write a {length} business proposal in a {tone} tone.\n"
        f"The sender is {first_name} ({position}) from {company_name}.\n"
        f"Their website is {website}, and they can be reached at {reply_to} or {phone}.\n"
        f"Pretend a lead has just inquired and you're writing the first follow-up."
    )

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.7
    )

    preview = response["choices"][0]["message"]["content"].strip()

    # Render back to the same automation page with preview
    return render_template("automation.html", 
        tone=tone,
        length=length,
        full_auto=settings["full_auto"],
        accept_offers=settings["accept_offers"],
        reject_offers=settings["reject_offers"],
        preview=preview
    )


@app.route("/thank-you")
def thank_you():
    pid = request.args.get("pid")
    if not pid:
        return "Unauthorized", 403

    conn = get_db_connection()
    proposal = conn.execute("SELECT * FROM proposals WHERE public_id = ?", (pid,)).fetchone()
    conn.close()

    if proposal is None:
        return "Unauthorized", 403

    return render_template("thank_you.html", proposal=proposal)

@app.route("/track_event", methods=["POST"])
def track_event():
    try:
        data = request.get_json()
        event_name = data.get("event_name")
        metadata = data.get("metadata", {})
        user_email = None

        # Resolve user_email from public_id if present
        public_id = metadata.get("public_id")
        if public_id:
            conn = get_db_connection()
            row = conn.execute(
                "SELECT user_email FROM proposals WHERE public_id = ?",
                (public_id,)
            ).fetchone()
            conn.close()
            if row:
                user_email = row["user_email"]

        # Log the event
        log_event(event_name, user_email=user_email, metadata=metadata)
        print(f"[TRACK] {event_name} for user: {user_email}")
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("❌ Track event error:", e)
        return jsonify({"error": "Tracking failed"}), 500
    
    
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


from pathlib import Path

@app.context_processor
def inject_user():
    return dict(email=session.get("email"))


@app.before_request
def load_user():
    g.email = session.get("email")


@app.context_processor
def inject_user():
    return dict(email=g.email)



if __name__ == "__main__":
    app.run(host="0.0.0.0",
            port=int(os.getenv("PORT", 5001)),
            debug=True)
