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
    create_analytics_events_table
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
            session['email'] = email
            return redirect(url_for('dashboard'))

        flash('Invalid email or password', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    # if not logged in, send to login
    if 'email' not in session:
        return redirect(url_for('login'))

    # fetch user + automation settings
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (session['email'],)
    ).fetchone()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
    ).fetchone()
    conn.close()

    # render dashboard.html with all the context it needs
    return render_template(
        'dashboard.html',
        first_name       = user    ['first_name']         if user else '',
        plan_status      = user    ['plan_status']        if user else 'None',
        automation       = automation,
        automation_complete = bool(automation)
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
            logger.exception("Stripe checkout creation failed: %s", e)
            flash("Could not start payment. Please try again.", "error")
            return redirect(url_for('memberships'))

    return render_template('memberships.html')


@app.route('/automation')
def automation_page():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
    ).fetchone()
    conn.close()

    return render_template('automation.html', automation=automation)


@app.route('/save-automation', methods=['POST'])
def save_automation():
    if 'email' not in session:
        return jsonify(success=False, error='Unauthorized'), 403

    tone, style, notes = (
        request.form.get('tone'),
        request.form.get('style'),
        request.form.get('additional_notes'),
    )

    conn = get_db_connection()
    if conn.execute(
        "SELECT 1 FROM automation_settings WHERE email = ?", (session['email'],)
    ).fetchone():
        conn.execute(
            "UPDATE automation_settings "
            "SET tone=?, style=?, additional_notes=? WHERE email=?",
            (tone, style, notes, session['email'])
        )
    else:
        conn.execute(
            "INSERT INTO automation_settings (email, tone, style, additional_notes) "
            "VALUES (?, ?, ?, ?)",
            (session['email'], tone, style, notes)
        )
    conn.commit()
    conn.close()

    return jsonify(success=True)


@app.route('/generate-proposal', methods=['POST'])
def generate_proposal():
    if 'email' not in session:
        return jsonify(success=False, error='Unauthorized'), 403

    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
    ).fetchone()
    conn.close()

    if not automation:
        return jsonify(success=False, error='No automation settings found'), 400

    prompt = (
        f"Write a concise business proposal email in a {automation['tone']} tone "
        f"and {automation['style']} style.\n\n"
        f"Extra notes: {automation['additional_notes'] or 'none'}"
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system",
                 "content": "You are a helpful assistant writing business proposals."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        return jsonify(success=True,
                       proposal=resp.choices[0].message.content.strip())
    except Exception:
        logger.exception("OpenAI failure; using dummy.")
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
            "SELECT * FROM automation_settings WHERE email = ?", (session['email'],)
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
                    {"role": "system",
                     "content": "You are a helpful assistant writing business proposals."},
                    {"role": "user", "content": prompt}
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
            flash(f"✅ Proposal sent to {lead_email}", "success")
            return render_template('thank_you.html')

        flash("❌ Failed to send proposal email.", "error")
        return redirect(url_for('proposal'))

    return render_template('proposal.html')


@app.route('/analytics')
def analytics():
    conn = get_db_connection()
    # … compute total_pageviews, total_converted, drop_offs …
    # … compute line_labels, line_data …
    kpis = {
        "Pageviews": total_pageviews,
        "Conversions": total_converted,
        "Drop-Offs": drop_offs,
        "Conversion Rate (%)": round((total_converted/total_pageviews)*100,1) if total_pageviews else 0
    }
    conn.close()
    return render_template(
        "analytics.html",
        donut_converted=total_converted,
        donut_dropped=drop_offs,
        line_labels=line_labels,
        line_data=line_data,
        kpis=kpis
    )


@app.route('/terms')
def terms():
    return render_template('terms.html')


@app.route('/track', methods=['POST'])
def track_event():
    data = request.get_json()
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO analytics_events (user_id, event_type) VALUES (?,?)",
        (session.get('email'), data.get('event'))
    )
    conn.commit()
    conn.close()
    return ('', 204)


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
    files = sorted(os.listdir(tpl_dir))
    items = "".join(f"<li>{f}</li>" for f in files)
    return f"<h2>Templates folder contains:</h2><ul>{items}</ul>"


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)