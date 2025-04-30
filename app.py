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

# ─── Flask Setup ────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

# ─── DB Init + Migration ─────────────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()
create_analytics_events_table()

# add stripe_customer_id column if missing
conn = get_db_connection()
try:
    conn.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;")
    conn.commit()
except sqlite3.OperationalError:
    pass
conn.close()

# seed an admin user if configured
if ADMIN_EMAIL and ADMIN_PASSWORD:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (email, password, first_name, plan_status) "
        "VALUES (?, ?, ?, ?)",
        (ADMIN_EMAIL, ADMIN_PASSWORD, "Admin", "pro")
    )
    conn.commit()
    conn.close()

# ─── Public endpoints ───────────────────────────────────────────────────────
PUBLIC_ENDPOINTS = {
    'home', 'login', 'terms', 'ping', 'static', 'stripe_webhook'
}

@app.before_request
def require_login():
    # if the endpoint is not in PUBLIC_ENDPOINTS and user not in session, redirect to login
    if request.endpoint not in PUBLIC_ENDPOINTS and 'email' not in session:
        return redirect(url_for('login'))

# ─── Routes ─────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        conn     = get_db_connection()
        user     = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and user['password'] == password:
            session['email']       = user['email']
            session['first_name']  = user['first_name']
            session['plan_status'] = user['plan_status']
            return redirect(url_for('dashboard'))

        flash('Invalid email or password', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    # guaranteed logged in by @before_request
    conn = get_db_connection()
    row  = conn.execute(
        "SELECT first_name, plan_status FROM users WHERE email = ?", 
        (session['email'],)
    ).fetchone()
    conn.close()

    # refresh session.plan_status
    session['plan_status'] = row['plan_status']
    log_event(session['email'], 'pageview')

    return render_template(
        'dashboard.html',
        first_name         = row['first_name'],
        plan_status        = row['plan_status'],
        automation         = get_user_automation(session['email']),
        automation_complete= bool(get_user_automation(session['email']))
    )


@app.route('/memberships', methods=['GET', 'POST'])
def memberships():
    if request.method == 'POST':
        if not request.form.get('terms'):
            flash("You must agree to the Terms of Service.", "error")
            return redirect(url_for('memberships'))

        price_id = os.getenv("SECRET_BUNDLE_PRICE_ID")
        if not price_id:
            flash("Payment configuration missing. Try again later.", "error")
            return redirect(url_for('memberships'))

        try:
            session_obj = stripe.checkout.Session.create(
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=url_for('dashboard', _external=True),
                cancel_url =url_for('memberships', _external=True),
            )
            # store customer immediately
            cust = session_obj.customer
            conn = get_db_connection()
            conn.execute(
                "UPDATE users SET stripe_customer_id = ? WHERE email = ?",
                (cust, session['email'])
            )
            conn.commit()
            conn.close()

            return redirect(session_obj.url, code=303)
        except Exception as e:
            logger.exception("Stripe checkout failed: %s", e)
            flash("Could not start payment. Please try again.", "error")
            return redirect(url_for('memberships'))

    return render_template('memberships.html')


@app.route('/analytics')
def analytics():
    if session.get('plan_status') != 'pro':
        flash("Analytics is a Pro feature—please subscribe.", "error")
        return redirect(url_for('memberships'))

    conn    = get_db_connection()
    user    = conn.execute(
        "SELECT id FROM users WHERE email = ?", (session['email'],)
    ).fetchone()
    if not user:
        conn.close()
        flash("User not found", "error")
        return redirect(url_for('dashboard'))
    user_id = user['id']

    # fetch metrics...
    pageviews  = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id=? AND event_type='pageview'",
        (user_id,)
    ).fetchone()['cnt']
    generated  = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id=? AND event_type='generated_proposal'",
        (user_id,)
    ).fetchone()['cnt']
    sent       = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id=? AND event_type='sent_proposal'",
        (user_id,)
    ).fetchone()['cnt']
    conn.close()

    conversion_rate = round(sent / generated * 100, 1) if generated else 0

    # last 7-day arrays...
    today   = datetime.utcnow().date()
    dates   = [today - timedelta(days=i) for i in reversed(range(7))]
    labels  = [d.strftime("%b %-d") for d in dates]
    data_pv = []
    data_gen= []
    data_sent=[]
    conn    = get_db_connection()
    for d in dates:
        data_pv .append(conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id=? AND event_type='pageview'  AND date(timestamp)=?",
            (user_id,d)
        ).fetchone()['cnt'])
        data_gen.append(conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id=? AND event_type='generated_proposal' AND date(timestamp)=?",
            (user_id,d)
        ).fetchone()['cnt'])
        data_sent.append(conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id=? AND event_type='sent_proposal' AND date(timestamp)=?",
            (user_id,d)
        ).fetchone()['cnt'])
    conn.close()

    return render_template(
        'analytics.html',
        pageviews       = pageviews,
        generated       = generated,
        sent            = sent,
        conversion_rate = conversion_rate,
        line_labels     = labels,
        line_data       = data_pv,
        generated_data  = data_gen,
        sent_data       = data_sent
    )


@app.route('/automation', methods=['GET', 'POST'])
def automation():
    if session.get('plan_status') != 'pro':
        flash("Automation is a Pro feature—please subscribe.", "error")
        return redirect(url_for('memberships'))

    if request.method == 'POST':
        tone, style, notes = (
            request.form.get('tone'),
            request.form.get('style'),
            request.form.get('additional_notes'),
        )
        conn   = get_db_connection()
        exists= conn.execute(
            "SELECT 1 FROM automation_settings WHERE email=?",
            (session['email'],)
        ).fetchone()
        if exists:
            conn.execute(
                "UPDATE automation_settings SET tone=?,style=?,additional_notes=? WHERE email=?",
                (tone, style, notes, session['email'])
            )
        else:
            conn.execute(
                "INSERT INTO automation_settings (email,tone,style,additional_notes) "
                "VALUES (?,?,?,?)",
                (session['email'], tone, style, notes)
            )
        conn.commit()
        conn.close()
        log_event(session['email'], 'saved_automation')
        return redirect(url_for('dashboard'))

    return render_template(
        'automation.html',
        automation=get_user_automation(session['email']) or {}
    )


@app.route('/proposal', methods=['GET', 'POST'])
def proposal():
    if request.method == 'POST':
        lead_name  = request.form['name']
        lead_email = PERSONAL_EMAIL or request.form['email']
        budget     = request.form['budget']
        conn       = get_db_connection()
        automation = conn.execute(
            "SELECT * FROM automation_settings WHERE email=?",
            (session['email'],)
        ).fetchone()
        conn.close()

        prompt = (
            f"Write a business proposal email to {lead_name}, budget ${budget}, "
            f"in a {automation['tone']} tone & {automation['style']} style. "
            f"Notes: {automation['additional_notes'] or 'none'}"
        )
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role":"system","content":"You are a helpful assistant writing business proposals."},
                    {"role":"user",  "content":prompt}
                ],
                max_tokens=350,
                temperature=0.7
            )
            email_body = resp.choices[0].message.content.strip()
        except Exception as e:
            flash(f"Error generating proposal: {e}","error")
            return redirect(url_for('proposal'))

        subject  = f"Proposal for {lead_name} (Budget: ${budget})"
        resp_obj = send_proposal_email(
            to_email=lead_email,
            subject=subject,
            content=email_body,
            cc_client=False
        )
        if 200 <= getattr(resp_obj,'status_code',0) < 300:
            log_event(session['email'],'sent_proposal')
            flash(f"✅ Proposal sent to {lead_email}","success")
            return render_template('thank_you.html')

        flash("❌ Failed to send proposal email.","error")
        return redirect(url_for('proposal'))

    return render_template('proposal.html')


@app.route('/terms')
def terms():
    return render_template('terms.html')


@app.route('/ping')
def ping():
    return "pong"


if __name__ == '__main__':
    app.run(host='0.0.0.0',
            port=int(os.getenv('PORT',5001)),
            debug=True)
