# email_assistant.py

import openai
import uuid
import os
from datetime import datetime
from dotenv import load_dotenv

from models import get_db_connection, get_user_automation, log_event
from email_utils import send_proposal_email
from sms_utils import send_sms_alert  # Optional, still included

# Load API keys
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def handle_new_proposal(name, email, company, services, budget, timeline, message, client_email):
    try:
        public_id = str(uuid.uuid4())

        # Fetch automation settings for the client
        settings = get_user_automation(client_email)
        if not settings:
            print("[ERROR] No automation settings found.")
            return None, None

        # Safe fallback values
        tone = settings.get("tone", "friendly")
        length = settings.get("length", "concise")
        first_name = settings.get("first_name", "Your Name")
        position = settings.get("position", "")
        company_name = settings.get("company_name", "Your Company")
        website = settings.get("website", "example.com")
        reply_to = settings.get("reply_to", "contact@example.com")
        phone = settings.get("phone", "123-456-7890")

        # Build OpenAI prompt
        prompt = (
            f"Write a {length} business proposal in a {tone} tone.\n"
            f"Client: {first_name} ({position}) from {company_name}.\n"
            f"Website: {website}, Contact: {reply_to} / {phone}.\n"
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

        # Log the generation in analytics
        log_event("generated_proposal", user_email=client_email, metadata={"public_id": public_id})

        # Email the proposal to the lead
        send_proposal_email(
            to_email=email,
            subject=f"Your Custom Proposal from {first_name}",
            content=proposal_text
        )

        # Optional: SMS alert to client
        # sms_msg = f"New proposal from {name} for {services} just submitted."
        # send_sms_alert(phone, sms_msg, user_email=client_email)

        return public_id, proposal_text

    except Exception as e:
        print(f"[ERROR] Failed to handle proposal: {e}")
        return None, None
