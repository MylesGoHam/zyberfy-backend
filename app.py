import os
import sqlite3
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from dotenv import load_dotenv
import openai

from models import (
    get_db_connection,
    create_users_table,
    create_automation_settings_table,
    create_subscriptions_table
)
from email_utils import send_proposal_email

load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")

# === OpenAI setup ===
openai.api_key = os.getenv("OPENAI_API_KEY")


# --- initialize our three tables ---
create_users_table()
create_automation_settings_table()
create_subscriptions_table()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/memberships", methods=["GET", "POST"])
def memberships():
    if "email" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        first_name = request.form.get("first_name", "")
        plan = request.form.get("plan", "free")

        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO users (email, password, first_name, plan_status) VALUES (?, ?, ?, ?)",
                (email, password, first_name, plan),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            flash("That email is already registered.", "error")
            return redirect(url_for("memberships"))
        finally:
            conn.close()

        session["email"] = email
        return redirect(url_for("dashboard"))

    return render_template("memberships.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and user["password"] == password:
            session["email"] = email
            return redirect(url_for("dashboard"))

        flash("Invalid email or password", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "email" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (session["email"],)
    ).fetchone()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (session["email"],)
    ).fetchone()
    conn.close()

    return render_template(
        "dashboard.html",
        first_name=user["first_name"],
        plan_status=user["plan_status"],
        automation_complete=automation is not None,
        automation=automation
    )


#
# ——— Automation settings (backing the AJAX “Save Settings” button) ———
#
@app.route("/automation")
def automation_ui():
    if "email" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    automation = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (session["email"],)
    ).fetchone()
    conn.close()

    return render_template("automation.html", automation=automation)


@app.route("/save-automation", methods=["POST"])
def save_automation():
    if "email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    tone = request.form.get("tone")
    style = request.form.get("style")
    notes = request.form.get("additional_notes")

    conn = get_db_connection()
    exists = conn.execute(
        "SELECT 1 FROM automation_settings WHERE email = ?", (session["email"],)
    ).fetchone()

    if exists:
        conn.execute(
            """
            UPDATE automation_settings
               SET tone = ?, style = ?, additional_notes = ?
             WHERE email = ?
            """,
            (tone, style, notes, session["email"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO automation_settings (email, tone, style, additional_notes)
            VALUES (?, ?, ?, ?)
            """,
            (session["email"], tone, style, notes),
        )

    conn.commit()
    conn.close()
    return jsonify({"success": True})


#
# ——— Test-only endpoint: get a live AI proposal sample ———
#
@app.route("/generate-proposal", methods=["POST"])
def generate_proposal():
    if "email" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    conn = get_db_connection()
    auto = conn.execute(
        "SELECT * FROM automation_settings WHERE email = ?", (session["email"],)
    ).fetchone()
    conn.close()

    if not auto:
        return jsonify({"success": False, "error": "Set up your automation first"}), 400

    # build a quick demo prompt
    prompt = (
        f"Write a short, {auto['style'].lower()} business proposal email "
        f"in a {auto['tone'].lower()} tone. Include these notes if any: {auto['additional_notes']}. "
        "Keep it under 200 words."
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        proposal = resp.choices[0].message.content.strip()
        return jsonify({"success": True, "proposal": proposal})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


#
# ——— New “public” proposal form for prospects ———
#
@app.route("/proposal", methods=["GET", "POST"])
def proposal():
    if "email" not in session:
        # you must be logged in (you’re the vendor) to send
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["prospect_name"]
        to_email = request.form["prospect_email"]
        budget = request.form.get("budget", "N/A")

        # grab your saved tone/style/notes
        conn = get_db_connection()
        auto = conn.execute(
            "SELECT * FROM automation_settings WHERE email = ?", (session["email"],)
        ).fetchone()
        conn.close()

        if not auto:
            flash("Please configure your automation settings first.", "error")
            return redirect(url_for("automation_ui"))

        # build and call the AI
        prompt = (
            f"Write a proposal email to {name} who has a budget of ${budget}. "
            f"Use a {auto['style'].lower()} style and {auto['tone'].lower()} tone. "
            f"Additional notes: {auto['additional_notes'] or 'none'}. "
            "Include a clear subject line."
        )
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500,
            )
            body = resp.choices[0].message.content.strip()

            # you can parse out a subject if the model included one,
            # or just hard‑prefix:
            subject = f"Proposal for {name}"
            send_proposal_email(to_email, subject, body)

            return render_template("lead_sent.html", prospect_email=to_email)
        except Exception as e:
            flash("Error generating or sending proposal: " + str(e), "error")
            return redirect(url_for("proposal"))

    return render_template("proposal.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
