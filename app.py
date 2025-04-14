from flask import Flask, render_template, session, redirect, url_for

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with a secure secret key

# Dummy data functions for demonstration purposes.
def get_current_client_email():
    # In a real application, retrieve the email from the session or database.
    # For now, we default to a sample email if not set.
    return session.get('client_email', 'client@example.com')

def get_client_proposals(client_email):
    # Replace this dummy list with a database query for proposals matching the client_email.
    return [
        {
            "Name": "Proposal One",
            "Timestamp": "2025-04-01 10:00 AM",
            "Service": "Luxury Travel",
            "Budget": "$10,000",
            "Location": "Paris"
        },
        {
            "Name": "Proposal Two",
            "Timestamp": "2025-04-05 02:30 PM",
            "Service": "Event Planning",
            "Budget": "$5,000",
            "Location": "New York"
        }
    ]

# Landing page route for zyberfy.com
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Simulated login; in production you'd verify credentials.
    # Here we simply set the client_email in the session to force a client login.
    session['client_email'] = 'client@example.com'
    return redirect(url_for('client_dashboard'))

@app.route('/dashboard')
def client_dashboard():
    client_email = get_current_client_email()
    proposals = get_client_proposals(client_email)
    return render_template('client_dashboard.html', client_email=client_email, proposals=proposals)

@app.route('/client-logout')
def client_logout():
    session.pop('client_email', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
