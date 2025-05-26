# email_assistant.py
from slugify import slugify
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

def generate_public_id(full_name):
    slug = slugify(full_name)
    short_id = str(uuid.uuid4())[:6]
    return f"{slug}-{short_id}"

def handle_new_proposal(name, email, company, services, budget, timeline, message, client_email):
    try:
        public_id = str(uuid.uuid4())

        # ✅ Check if client has exceeded proposal limit
        conn = get_db_connection()
        count_row = conn.execute("SELECT COUNT(*) as count FROM proposals WHERE user_email = ?", (client_email,)).fetchone()
        conn.close()

        proposal_count = count_row["count"]
        PROPOSAL_LIMIT = 3  # Temporary free plan limit

        if proposal_count >= PROPOSAL_LIMIT:
            print(f"[LIMIT] Client {client_email} reached proposal cap.")
            return "LIMIT_REACHED"

        # ✅ Fetch automation settings for the client
        settings = get_user_automation(client_email)
        if not settings:
            print("[ERROR] No automation settings found.")
            return None

        # ✅ Access with fallback defaults
        tone         = settings["tone"]         if settings["tone"] else "friendly"
        length       = settings["length"]       if settings["length"] else "concise"

        # ✅ Pull identity + contact info from settings table
        conn = get_db_connection()
        row = conn.execute("""
            SELECT first_name, company_name, position, website, phone, reply_to
            FROM settings WHERE email = ?
        """, (client_email,)).fetchone()
        conn.close()

        first_name   = row["first_name"]   if row and row["first_name"] else "Your Name"
        position     = row["position"]     if row and row["position"] else ""
        company_name = row["company_name"] if row and row["company_name"] else "Your Company"
        website      = row["website"]      if row and row["website"] else "example.com"
        reply_to     = row["reply_to"]     if row and row["reply_to"] else "contact@example.com"
        phone        = row["phone"]        if row and row["phone"] else "123-456-7890"

        # ✅ Build OpenAI prompt
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

        # ✅ Save proposal to database
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

        # ✅ Log the generation in analytics
        log_event("generated_proposal", user_email=client_email, metadata={"public_id": public_id})

        # ✅ Email the proposal to the lead
        send_proposal_email(
            to_email=email,
            subject="Your Proposal Has Been Received",
            content=proposal_text,
            cc_client=True,
            client_email=client_email
        )

        # ✅ Optional SMS alert
        # sms_msg = f"New proposal from {name} for {services} just submitted."
        # send_sms_alert(phone, sms_msg, user_email=client_email)

        return public_id

    except Exception as e:
        print(f"[ERROR] Failed to handle proposal: {e}")
