@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    subscription = conn.execute(
        "SELECT stripe_subscription_id FROM subscriptions WHERE email = ?", 
        (session['email'],)
    ).fetchone()

    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", 
        (session['email'],)
    ).fetchone()

    conn.close()

    # Check if automation settings are complete
    automation_complete = bool(automation)

    plan_status = "Free"
    if subscription:
        plan_status = "Active Subscription"

    return render_template('dashboard.html', email=session['email'], plan_status=plan_status, automation_complete=automation_complete)
