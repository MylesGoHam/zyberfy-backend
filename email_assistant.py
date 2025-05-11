import openai
import uuid
import os
from datetime import datetime
from dotenv import load_dotenv

from models import get_db_connection
from email_utils import send_proposal_email
from sms_utils import send_sms_alert
from analytics import log_event

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def handle_new_proposal(name, email, company, services, budget, timeline, message, client_email):
    try:
        conn = get_db_connection()
        settings = conn.execute("""
            SELECT first_name, company_name, position, website, phone, reply_to, tone, length
            FROM automation_settings
            WHERE email = ?
        """, (client_email,)).fetchone()
        conn.close()

        if not settings:
            raise ValueError("Client automation settings not found.")

        # Prepare GPT prompt
        prompt = (
            f"Write a {settings['length']} business proposal in a {settings['tone']} tone.\n"
            f"Client: {settings['first_name']} ({settings['position']}) from {settings['company_name']}.\n"
            f"Website: {settings['website']}, Contact: {settings['reply_to']} / {settings['phone']}.\n"
            f"Lead Info: {name} from {company}, wants: {services}, budget: {budget}, timeline: {timeline}.\n"
            f"Extra message from lead: {message}\n"
            f"Generate a custom response from the client to the lead."
        )

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7
        )

        proposal_text = response["choices"][0]["message"]["content"].strip()
        public_id = str(uuid.uuid4())

        # Save to DB
        conn = get_db_connection()
        conn.execute("""
            INSERT INTO proposals (
                user_email, name, email, company, services, budget, timeline, message,
                generated_proposal, public_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            client_email, name, email, company, services, budget, timeline, message,
            proposal_text, public_id, datetime.utcnow()
        ))
        conn.commit()
        conn.close()

        # Log event
        log_event("generated_proposal", user_email=client_email, metadata={"lead_email": email})

        # Send email
        send_proposal_email(
            to=email,
            proposal=proposal_text,
            from_name=settings["first_name"]
        )

        # Optional SMS (resume after toll-free approved)
        # if settings["phone"]:
        #     sms_message = f"New proposal from {name} for {services}. Check your dashboard."
        #     send_sms_alert(settings["phone"], sms_message, user_email=client_email)

        return public_id

    except Exception as e:
        print(f"[ERROR] Failed to handle proposal: {e}")
        return None
