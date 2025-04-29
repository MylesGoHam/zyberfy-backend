from flask import Flask, render_template, redirect, url_for, session, flash, jsonify
from datetime import datetime, timedelta
# … your other imports …

@app.route('/analytics')
def analytics():
    if 'email' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    # look up user_id
    user = conn.execute(
        "SELECT id FROM users WHERE email = ?", (session['email'],)
    ).fetchone()
    if not user:
        conn.close()
        flash("User not found", "error")
        return redirect(url_for('dashboard'))
    user_id = user['id']

    # Totals
    pageviews = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'pageview'",
        (user_id,)
    ).fetchone()['cnt']
    configs = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'saved_automation'",
        (user_id,)
    ).fetchone()['cnt']
    generated = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'generated_proposal'",
        (user_id,)
    ).fetchone()['cnt']
    conversions = conn.execute(
        "SELECT COUNT(*) AS cnt FROM analytics_events "
        "WHERE user_id = ? AND event_type = 'sent_proposal'",
        (user_id,)
    ).fetchone()['cnt']
    conversion_rate = (conversions / generated * 100) if generated else 0

    # Last 7 days labels
    today  = datetime.utcnow().date()
    dates  = [today - timedelta(days=i) for i in reversed(range(7))]
    line_labels = [d.strftime('%b %-d') for d in dates]

    # Pageviews per day
    pageviews_data = []
    for d in dates:
        cnt = conn.execute("""
            SELECT COUNT(*) AS cnt FROM analytics_events
             WHERE user_id = ? AND event_type = 'pageview'
               AND date(timestamp) = ?
        """, (user_id, d)).fetchone()['cnt']
        pageviews_data.append(cnt)

    # Proposals Generated per day
    generated_data = []
    for d in dates:
        cnt = conn.execute("""
            SELECT COUNT(*) AS cnt FROM analytics_events
             WHERE user_id = ? AND event_type = 'generated_proposal'
               AND date(timestamp) = ?
        """, (user_id, d)).fetchone()['cnt']
        generated_data.append(cnt)

    # Proposals Sent per day
    sent_data = []
    for d in dates:
        cnt = conn.execute("""
            SELECT COUNT(*) AS cnt FROM analytics_events
             WHERE user_id = ? AND event_type = 'sent_proposal'
               AND date(timestamp) = ?
        """, (user_id, d)).fetchone()['cnt']
        sent_data.append(cnt)

    conn.close()

    return render_template(
        'analytics.html',
        pageviews        = pageviews,
        configs          = configs,
        generated        = generated,
        conversions      = conversions,
        conversion_rate  = round(conversion_rate, 1),
        donut_converted  = conversions,
        donut_dropped    = max(0, generated - conversions),
        line_labels      = line_labels,
        line_data        = pageviews_data,
        generated_data   = generated_data,
        sent_data        = sent_data
    )
