import os
import sqlite3
import openai
from flask import Flask, request, render_template, redirect, url_for, g
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# ——— Flask setup —————————————————————————————
app = Flask(__name__)

# Load API keys from environment
openai.api_key = os.getenv("OPENAI_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = 'hello@zyberfy.com'  # your verified sender email

# ——— Database config ———————————————————————————
DATABASE = os.path.join(os.path.dirname(__file__), 'proposals.db')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input_text TEXT NOT NULL,
                generated_text TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        db.commit()

# Ensure the DB exists on startup
init_db()

# ——— Routes —————————————————————————————————————
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        user_input      = request.form["user_input"]
        recipient_email = request.form["recipient_email"]

        try:
            # 1) Generate with GPT-3.5-Turbo
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # using GPT‑3.5 Turbo
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that writes professional proposals."},
                    {"role": "user",   "content": user_input},
                ],
                temperature=0.7,
                max_tokens=800
            )
            generated_text = response.choices[0].message.content

            # 2) Send via SendGrid
            message = Mail(
                from_email=FROM_EMAIL,
                to_emails=recipient_email,
                subject="Your AI‑Generated Proposal",
                html_content=f"<p>{generated_text}</p>"
            )
            SendGridAPIClient(SENDGRID_API_KEY).send(message)

            # 3) Save to SQLite
            db = get_db()
            db.execute(
                "INSERT INTO proposals (input_text, generated_text, recipient_email) VALUES (?, ?, ?)",
                (user_input, generated_text, recipient_email)
            )
            db.commit()

            # 4) Redirect to a thank-you page
            return redirect(url_for("thank_you"))

        except Exception as e:
            print("ERROR:", e)
            return render_template("error.html", error=str(e)), 500

    return render_template("index.html")


@app.route("/thank_you")
def thank_you():
    return render_template("thank_you.html")


@app.route("/dashboard")
def dashboard():
    db = get_db()
    cur = db.execute("SELECT * FROM proposals ORDER BY created_at DESC")
    proposals = cur.fetchall()
    return render_template("dashboard.html", proposals=proposals)


# ——— Run the app —————————————————————————————
if __name__ == "__main__":
    app.run(debug=True)
