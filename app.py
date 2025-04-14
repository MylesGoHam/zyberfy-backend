from flask import Flask, request, render_template, redirect, url_for, flash, session
from dotenv import load_dotenv
import os
import re

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')

# ---------- INDEX (Landing Page) ----------
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

# ---------- CLIENT LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        if not is_valid_email(email):
            flash("Invalid email format.", "error")
            return redirect(url_for("login"))
        session["client_email"] = email
        flash("Welcome back!", "success")
        return redirect(url_for("dashboard"))
    return render_template("login.html")

# ---------- CLIENT DASHBOARD ----------
@app.route("/dashboard")
def dashboard():
    email = session.get("client_email")
    if not email:
        flash("Please log in to access the dashboard.", "error")
        return redirect(url_for("login"))
    return render_template("dashboard.html", email=email)

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.pop("client_email", None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))

# ---------- UTILS ----------
def is_valid_email(email):
    return re.match(r"(^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$)", email) is not None

# ---------- RUN ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
