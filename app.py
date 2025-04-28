import os
import logging
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

# ─── Force DB Init ──────────────────────────────────────────────────────────
create_users_table()
create_automation_settings_table()
create_subscriptions_table()
create_analytics_events_table()

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

# ─── Routes ──────────────────────────────────────────────────────────────────

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


@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    log_event(session['email'], 'pageview')

    first_name          = session.get('first_name', 'there')
    plan_status         = session.get('plan_status', 'free')
    automation          = get_user_automation(session['email'])
    automation_complete = bool(automation)

    return render_template(
        'dashboard.html',
        first_name=first_name,
        plan_status=plan_status,
        automation=automation,
        automation_complete=automation_complete
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
                cancel_url=url_for('memberships', _external=True),
            )
            return redirect(session_obj.url, code=303)
        except Exception as e:
            logger.exception("Stripe checkout failed: %s", e)
            flash("Could not start payment. Please try again.", "error")
            return redirect(url_for('memberships'))

    return render_template('memberships.html')


@app.route('/automation', methods=['GET', 'POST'])
def automation():
    if 'email' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # pull the submitted form values
        tone  = request.form.get('tone')
        style = request.form.get('style')
        notes = request.form.get('additional_notes')

        conn = get_db_connection()
        exists = conn.execute(
            "SELECT 1 FROM automation_settings WHERE email = ?",
            (session['email'],)
        ).fetchone()

        if exists:
            conn.execute(
                "UPDATE automation_settings "
                "SET tone = ?, style = ?, additional_notes = ? "
                "WHERE email = ?",
                (tone, style, notes, session['email'])
            )
        else:
            conn.execute(
                "INSERT INTO automation_settings "
                "(email, tone, style, additional_notes) VALUES (?, ?, ?, ?)",
                (session['email'], tone, style, notes)
            )

        conn.commit()
        conn.close()

        # log + flash + redirect
        log_event(session['email'], 'saved_automation')
        flash("✅ Your automation settings have been saved!", "success")
        return redirect(url_for('dashboard'))

    # GET: render the form
    automation = get_user_automation(session['email']) or {}
    return render_template('automation.html', automation=automation)


@app.route('/save-automation', methods=['POST'])
def save_automation():
    if 'email' not in session:
        return jsonify(success=False, error='Unauthorized'), 403

    tone  = request.form.get('tone')
    style = request.form.get('style')
    notes = request.form.get('additional_notes')

    logger.info(f"Attempting to save automation for {session['email']} → tone={tone}, style={style}")
    conn = get_db_connection()
    try:
        exists = conn.execute(
            "SELECT 1 FROM automation_settings WHERE email = ?", 
            (session['email'],)
        ).fetchone()

        if exists:
            conn.execute(
                "UPDATE automation_settings "
                "SET tone=?, style=?, additional_notes=? "
                "WHERE email=?",
                (tone, style, notes, session['email'])
            )
            logger.info("Updated existing automation_settings row")
        else:
            conn.execute(
                "INSERT INTO automation_settings (email, tone, style, additional_notes) "
                "VALUES (?, ?, ?, ?)",
                (session['email'], tone, style, notes)
            )
            logger.info("Inserted new automation_settings row")

        conn.commit()
    except Exception as e:
        logger.exception("Failed to save automation settings")
        return jsonify(success=False, error=str(e)), 500
    finally:
        conn.close()

    # Log the event, too
    log_event(session['email'], 'saved_automation')
    return jsonify(success=True)

@app.route('/generate-proposal', methods=['POST'])
def generate_proposal():
    if 'email' not in session:
        return jsonify(success=False, error='Unauthorized'), 403

    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", 
        (session['email'],)
    ).fetchone()
    conn.close()

    if not automation:
        return jsonify(success=False, error='No automation settings found'), 400

    log_event(session['email'], 'generated_proposal')

    prompt = (
        f"Write a concise business proposal email in a {automation['tone']} tone "
        f"and {automation['style']} style.\n\n"
        f"Extra notes: {automation['additional_notes'] or 'none'}"
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
            f"Hi there,\n\nThanks for reaching out! Here's a "
            f"{automation['tone']} & {automation['style']} proposal.\n\n"
            f"{automation['additional_notes'] or ''}\n\n"
            "Best regards,\nThe Zyberfy Team"
        )
        return jsonify(success=True, proposal=fallback, fallback=True)


@app.route('/proposal', methods=['GET', 'POST'])
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

    conn = get_db_connection()
    rows = conn.execute("""
        SELECT event_type, COUNT(*) AS cnt
          FROM analytics_events
         WHERE user_id = ?
      GROUP BY event_type
    """, (session['email'],)).fetchall()
    conn.close()

    kpis       = {r['event_type']: r['cnt'] for r in rows}
    pageviews   = kpis.get('pageview', 0)
    saves       = kpis.get('saved_automation', 0)
    generated   = kpis.get('generated_proposal', 0)
    conversions = kpis.get('sent_proposal', 0)
    conversion_rate = (conversions / generated * 100) if generated else 0
    donut_converted = conversions
    donut_dropped   = max(0, generated - conversions)

    # build 7-day sparkline
    today       = datetime.utcnow().date()
    dates       = [today - timedelta(days=i) for i in reversed(range(7))]
    line_labels = [d.strftime('%b %-d') for d in dates]
    line_data   = []
    conn = get_db_connection()
    for d in dates:
        cnt = conn.execute("""
            SELECT COUNT(*) AS cnt
              FROM analytics_events
             WHERE user_id = ?
               AND event_type = 'pageview'
               AND date(timestamp) = ?
        """, (session['email'], d)).fetchone()['cnt']
        line_data.append(cnt)
    conn.close()

    return render_template(
        'analytics.html',
        pageviews=pageviews,
        saves=saves,
        generated=generated,
        conversions=conversions,
        conversion_rate=round(conversion_rate,1),
        donut_converted=donut_converted,
        donut_dropped=donut_dropped,
        line_labels=line_labels,
        line_data=line_data
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


@app.route('/debug_templates')
def debug_templates():
    import os
    tpl_dir = os.path.join(app.root_path, 'templates')
    files   = sorted(os.listdir(tpl_dir))
    items   = "".join(f"<li>{f}</li>" for f in files)
    return f"<h2>Templates folder contains:</h2><ul>{items}</ul>"


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
