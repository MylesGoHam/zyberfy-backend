@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            print("🚨 Form POST hit Flask route")  # ✅ STEP 3 DEBUG LINE

            # Get form data
            name = request.form.get("name")
            email = request.form.get("email")
            service = request.form.get("service")
            budget = request.form.get("budget")
            location = request.form.get("location")
            special_requests = request.form.get("requests")

            # Validate email format
            if not is_valid_email(email):
                flash("Invalid email address", "error")
                return redirect(url_for('index'))

            print(f"📨 Generating proposal for {name} - {service}")

            # Generate AI-powered proposal
            proposal = generate_proposal(name, service, budget, location, special_requests)

            # Create email content
            subject = f"Proposal Request from {name} ({service})"
            content = f"""
A new proposal request has been submitted:

Name: {name}
Email: {email}
Service: {service}
Budget: {budget}
Location: {location}
Special Requests: {special_requests}

---------------------
✨ AI-Generated Proposal:
{proposal}
"""

            # Send email through SendGrid
            send_email(subject, content)

            flash("Your request has been sent successfully!", "success")
            return redirect(url_for('index'))

        except Exception as e:
            print(f"❌ Error in POST handler: {e}")
            flash(f"An error occurred: {e}", "error")
            return redirect(url_for('index'))

    return render_template("index.html")
