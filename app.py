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

# ─── Logging & Config ─────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
openai.api_key = os.getenv("OPENAI_API_KEY")

# ─── Flask Setup & DB Init ────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

create_users_table()
create_automation_settings_table()
create_subscriptions_table()
create_analytics_events_table()

# ─── Helpers ─────────────────────────────────────────────────────────────────
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "email" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ─── Public Routes ────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        pw    = request.form["password"]
        conn  = get_db_connection()
        user  = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if user and user["password"] == pw:
            session["email"] = email
            return redirect(url_for("dashboard"))
        flash("Invalid credentials", "error")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/ping")
def ping():
    return "pong"

# ─── Now the Analytics page is 100% public again ─────────────────────────────
@app.route("/analytics")
def analytics():
    # (Even anonymous visitors can hit this now)
    conn = get_db_connection()
    # If you still want to record pageviews only for logged-in folks:
    user = conn.execute(
        "SELECT id FROM users WHERE email=?", (session.get("email"),)
    ).fetchone()
    if user:
        log_event(session["email"], "pageview")
        user_id = user["id"]
    else:
        user_id = None

    # If you only want charted data for a real user, you can bail here:
    if not user_id:
        conn.close()
        return render_template("please_log_in.html")  # or just show analytics form

    # build your counts & time-series exactly as before…
    pageviews   = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id=? AND event_type='pageview'", (user_id,)
    ).fetchone()["cnt"]
    generated   = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id=? AND event_type='generated_proposal'", (user_id,)
    ).fetchone()["cnt"]
    conversions = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id=? AND event_type='sent_proposal'", (user_id,)
    ).fetchone()["cnt"]
    conversion_rate = (conversions / generated * 100) if generated else 0

    # build last-7-days arrays…
    from datetime import datetime, timedelta
    today  = datetime.utcnow().date()
    dates  = [today - timedelta(days=i) for i in reversed(range(7))]
    labels = [d.strftime("%b %-d") for d in dates]

    pv_data, gen_data, sent_data = [], [], []
    for d in dates:
        pv = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id=? AND event_type='pageview' AND date(timestamp)=?",
            (user_id, d)
        ).fetchone()["cnt"]
        gp = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id=? AND event_type='generated_proposal' AND date(timestamp)=?",
            (user_id, d)
        ).fetchone()["cnt"]
        sp = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id=? AND event_type='sent_proposal' AND date(timestamp)=?",
            (user_id, d)
        ).fetchone()["cnt"]
        pv_data.append(pv)
        gen_data.append(gp)
        sent_data.append(sp)

    conn.close()
    return render_template(
        "analytics.html",
        pageviews       = pageviews,
        generated       = generated,
        conversions     = conversions,
        conversion_rate = round(conversion_rate, 1),
        line_labels     = labels,
        line_data       = pv_data,
        generated_data  = gen_data,
        sent_data       = sent_data
    )

# ─── Protected Routes ─────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/automation", methods=["GET","POST"])
@login_required
def automation():
    # …your existing code…
    pass

@app.route("/proposal", methods=["GET","POST"])
@login_required
def proposal():
    # …your existing code…
    pass

@app.route("/memberships", methods=["GET","POST"])
@login_required
def memberships():
    # …your existing code…
    pass

# ─── Stripe Webhook ───────────────────────────────────────────────────────────
@app.route("/stripe_webhook", methods=["POST"])
def stripe_webhook():
    # …your existing code…
    pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5001)), debug=True)
