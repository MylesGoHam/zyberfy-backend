import openai
import uuid
import os
from datetime import datetime
from dotenv import load_dotenv

from models import get_db_connection
from email_utils import send_proposal_email
from sms_utils import send_sms_alert
from models import log_event
from models import get_user_automation

# Load API keys
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def handle_new_proposal(name, email, company, services, budget, timeline, message, client_email):
    try:
        public_id = str(uuid.uuid4())

        # Get automation settings
        settings = get_user_automation(client_email)
        if not settings:
            print("[ERROR] No automation settings found.")
            return None

        # Generate proposal using OpenAI
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

        # Save proposal to database
        conn = get_db_connection()
        conn.execute("""
            INSERT INTO proposals (
                public_id,
                user_email,
                lead_name,
                lead_email,
                lead_company,
                services,
                budget,
                timeline,
                message,
                proposal_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            public_id,
            client_email,
            name,
            email,
            company,
            services,
            budget,
            timeline,
            message,
            proposal_text
        ))
        conn.commit()
        conn.close()

        send_proposal_email(
            to_email=email,
            subject="Your Custom Proposal from " + settings["first_name"],
            content=proposal_text
        )

        # Optional SMS
        # sms_msg = f"New proposal from {name} for {services} just submitted."
        # send_sms_alert(settings["phone"], sms_msg, user_email=client_email)

        return public_id

    except Exception as e:
        print(f"[ERROR] Failed to handle proposal: {e}")
        return None
