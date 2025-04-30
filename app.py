import os
import logging
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
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
stripe.api_key   = os.getenv("STRIPE_SECRET_KEY")
openai.api_key   = os.getenv("OPENAI_API_KEY")
PERSONAL_EMAIL   = os.getenv("PERSONAL_EMAIL")
ADMIN_EMAIL      = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD   = os.getenv("ADMIN_PASSWORD")

# ─── Flask Setup ────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default_secret_key')

# ─── Force DB Init ──────────────────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()
create_analytics_events_table()

# ─── Migration: add stripe_customer_id if missing ───────────────────────────
def migrate_stripe_column():
    conn = get_db_connection()
    try:
        conn.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;")
        conn.commit()
    except sqlite3.OperationalError:
        # already there
        pass
    finally:
        conn.close()

migrate_stripe_column()

# ─── Seed admin if configured ───────────────────────────────────────────────
if ADMIN_EMAIL and ADMIN_PASSWORD:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (email, password, first_name, plan_status) "
        "VALUES (?, ?, ?, ?)",
        (ADMIN_EMAIL, ADMIN_PASSWORD, "Admin", "pro")
    )
    conn.commit()
    conn.close()

# Run the migration at startup
migrate_stripe_column()

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Config ─────────────────────────────────────────────────────────────────
load_dotenv()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
openai.api_key = os.getenv("OPENAI_API_KEY")
PERSONAL_EMAIL = os.getenv("PERSONAL_EMAIL")
ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# ─── Flask Setup ───────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default_secret_key')

# ─── Force DB Init + Migration ──────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()
create_analytics_events_table()

# Add stripe_customer_id if the column is missing
conn = get_db_connection()
try:
    conn.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;")
    conn.commit()
except sqlite3.OperationalError:
    pass
conn.close()

# Seed admin if configured
if ADMIN_EMAIL and ADMIN_PASSWORD:
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (email, password, first_name, plan_status) "
        "VALUES (?, ?, ?, ?)",
        (ADMIN_EMAIL, ADMIN_PASSWORD, "Admin", "pro")
    )
    conn.commit()
    conn.close()

# ─── Routes ─────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and user['password'] == password:
            session['email']       = email
            session['first_name']  = user['first_name']
            session['plan_status'] = user['plan_status']
            return redirect(url_for('dashboard'))

        flash('Invalid email or password', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/memberships', methods=['GET','POST'])
def memberships():
    if 'email' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        price_id = os.getenv("SECRET_BUNDLE_PRICE_ID")
        if not price_id:
            logger.error("⚠️ SECRET_BUNDLE_PRICE_ID not set!")
            flash("Payment configuration missing. Please try again later.", "error")
            return redirect(url_for('memberships'))

        if not request.form.get('terms'):
            flash("You must agree to the Terms of Service.", "error")
            return redirect(url_for('memberships'))

        try:
            session_obj = stripe.checkout.Session.create(
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url = url_for('dashboard', _external=True),
                cancel_url  = url_for('memberships', _external=True),
            )

            # persist the customer id immediately
            customer_id = session_obj.customer
            conn = get_db_connection()
            conn.execute(
                "UPDATE users SET stripe_customer_id = ? WHERE email = ?",
                (customer_id, session['email'])
            )
            conn.commit()
            conn.close()

            return redirect(session_obj.url, code=303)

        except Exception as e:
            logger.exception("Stripe checkout failed: %s", e)
            flash("Could not start payment. Please try again.", "error")
            return redirect(url_for('memberships'))

    return render_template('memberships.html')

@app.route('/billing-portal')
def billing_portal():
    if 'email' not in session or session.get('plan_status') != 'pro':
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    customer_id = conn.execute(
        "SELECT stripe_customer_id FROM users WHERE email = ?",
        (session['email'],)
    ).fetchone()['stripe_customer_id']
    conn.close()

    session_obj = stripe.billing_portal.Session.create(
        customer   = customer_id,
        return_url = url_for('dashboard', _external=True)
    )
    return redirect(session_obj.url, code=303)

@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload    = request.data
    sig_header = request.headers.get('Stripe-Signature')
    secret     = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, secret
        )
    except Exception as e:
        logger.exception("Webhook signature verification failed")
        return jsonify({'error': str(e)}), 400

    obj = event['data']['object']

    if event['type'] == 'checkout.session.completed':
        customer_id = obj['customer']
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET plan_status='pro' WHERE stripe_customer_id = ?",
            (customer_id,)
        )
        conn.commit()
        conn.close()

    elif event['type'].startswith('invoice.'):
        invoice     = obj
        customer_id = invoice['customer']
        paid        = invoice['paid']
        conn = get_db_connection()
        if not paid:
            conn.execute(
                "UPDATE users SET plan_status='free' WHERE stripe_customer_id = ?",
                (customer_id,)
            )
        conn.commit()
        conn.close()

    return jsonify({'status': 'success'})

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    row = conn.execute(
        "SELECT plan_status, first_name FROM users WHERE email = ?",
        (session['email'],)
    ).fetchone()
    session['plan_status'] = row['plan_status']
    conn.close()

    log_event(session['email'], 'pageview')

    return render_template(
      'dashboard.html',
      first_name     = session.get('first_name', 'there'),
      plan_status    = session['plan_status'],
      automation     = get_user_automation(session['email']),
      automation_complete = bool(get_user_automation(session['email']))
    )

@app.route('/automation', methods=['GET','POST'])
def automation():
    if 'email' not in session:
        return redirect(url_for('login'))
    if session.get('plan_status') != 'pro':
        flash("Automation is a Pro feature—please subscribe.", "error")
        return redirect(url_for('memberships'))

    if request.method == 'POST':
        tone, style, notes = (
            request.form.get('tone'),
            request.form.get('style'),
            request.form.get('additional_notes'),
        )
        conn = get_db_connection()
        exists = conn.execute(
            "SELECT 1 FROM automation_settings WHERE email = ?", 
            (session['email'],)
        ).fetchone()
        if exists:
            conn.execute(
                "UPDATE automation_settings SET tone=?, style=?, additional_notes=? WHERE email=?",
                (tone, style, notes, session['email'])
            )
        else:
            conn.execute(
                "INSERT INTO automation_settings (email, tone, style, additional_notes) VALUES (?, ?, ?, ?)",
                (session['email'], tone, style, notes)
            )
        conn.commit()
        conn.close()
        log_event(session['email'], 'saved_automation')
        return redirect(url_for('dashboard'))

    return render_template('automation.html', automation=get_user_automation(session['email']) or {})

@app.route('/generate-proposal', methods=['POST'])
def generate_proposal():
    if 'email' not in session:
        return jsonify(success=False, error='Unauthorized'), 403
    if session.get('plan_status') != 'pro':
        return jsonify(success=False, error='Upgrade to Pro'), 402

    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", 
        (session['email'],)
    ).fetchone()
    conn.close()
    if not automation:
        return jsonify(success=False, error='No automation settings'), 400

    log_event(session['email'], 'generated_proposal')
    prompt = (
        f"Write a concise business proposal email in a {automation['tone']} tone "
        f"and {automation['style']} style.\n\nExtra notes: {automation['additional_notes'] or 'none'}"
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant writing business proposals."},
                {"role": "user",   "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        return jsonify(success=True, proposal=resp.choices[0].message.content.strip())
    except Exception:
        logger.exception("OpenAI failure; using fallback.")
        fallback = (
            f"Hi there,\n\nHere's your {automation['tone']} & {automation['style']} proposal:\n\n"
            f"{automation['additional_notes'] or ''}\n\nBest,\nThe Zyberfy Team"
        )
        return jsonify(success=True, proposal=fallback, fallback=True)

@app.route('/proposal', methods=['GET','POST'])
def proposal():
    if 'email' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        lead_name  = request.form['name']
        lead_email = PERSONAL_EMAIL or request.form['email']
        budget     = request.form['budget']
        conn = get_db_connection()
        automation = conn.execute(
            "SELECT * FROM automation_settings WHERE email = ?", 
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
                    {"role": "system", "content": "You are a helpful assistant writing business proposals."},
                    {"role": "user",   "content": prompt}
                ],
                max_tokens=350,
                temperature=0.7
            )
            email_body = resp.choices[0].message.content.strip()
        except Exception as e:
            flash(f"Error generating proposal: {e}", "error")
            return redirect(url_for('proposal'))
        subject = f"Proposal for {lead_name} (Budget: ${budget})"
        resp_obj = send_proposal_email(
            to_email=lead_email,
            subject=subject,
            content=email_body,
            cc_client=False
        )
        status_code = getattr(resp_obj, 'status_code', resp_obj)
        if 200 <= status_code < 300:
            log_event(session['email'], 'sent_proposal')
            flash(f"✅ Proposal sent to {lead_email}", "success")
            return render_template('thank_you.html')
        flash("❌ Failed to send proposal email.", "error")
        return redirect(url_for('proposal'))
    return render_template('proposal.html')

@app.route('/analytics')
def analytics():
    if 'email' not in session:
        return redirect(url_for('login'))
    if session.get('plan_status') != 'pro':
        flash("Analytics is a Pro feature—please subscribe.", "error")
        return redirect(url_for('memberships'))

    conn = get_db_connection()
    user = conn.execute(
        "SELECT id FROM users WHERE email = ?", (session['email'],)
    ).fetchone()
    if not user:
        conn.close()
        flash("User not found", "error")
        return redirect(url_for('dashboard'))
    user_id = user['id']

    # Totals
    pageviews     = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'pageview'", (user_id,)
    ).fetchone()['cnt']
    configs       = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'saved_automation'", (user_id,)
    ).fetchone()['cnt']
    generated     = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'generated_proposal'", (user_id,)
    ).fetchone()['cnt']
    conversions   = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'sent_proposal'", (user_id,)
    ).fetchone()['cnt']
    conversion_rate = (conversions / generated * 100) if generated else 0

    today   = datetime.utcnow().date()
    dates   = [today - timedelta(days=i) for i in reversed(range(7))]
    labels  = [d.strftime('%b %-d') for d in dates]

    data_pv = []
    data_gen = []
    data_sent = []
    for d in dates:
        cnt_pv = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id = ? AND event_type = 'pageview' AND date(timestamp)=?", (user_id, d)
        ).fetchone()['cnt']
        cnt_gen = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id = ? AND event_type = 'generated_proposal' AND date(timestamp)=?", (user_id, d)
        ).fetchone()['cnt']
        cnt_sent = conn.execute(
            "SELECT COUNT(*) AS cnt FROM analytics_events "
            "WHERE user_id = ? AND event_type = 'sent_proposal' AND date(timestamp)=?", (user_id, d)
        ).fetchone()['cnt']
        data_pv.append(cnt_pv)
        data_gen.append(cnt_gen)
        data_sent.append(cnt_sent)

    conn.close()
    return render_template(
        'analytics.html',
        pageviews       = pageviews,
        configs         = configs,
        generated       = generated,
        conversions     = conversions,
        conversion_rate = round(conversion_rate, 1),
        donut_converted = conversions,
        donut_dropped   = max(0, generated - conversions),
        line_labels     = labels,
        line_data       = data_pv,
        generated_data  = data_gen,
        sent_data       = data_sent
    )

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/ping')
def ping():
    return "pong"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5001)), debug=True)
