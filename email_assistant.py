import openai
from email_utils import send_proposal_email
from models import get_db_connection
from datetime import datetime
import uuid

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

        # Construct prompt for GPT
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

        # Save to DB
        conn = get_db_connection()
        conn.execute("""
            INSERT INTO proposals (user_email, lead_name, lead_email, lead_company,
                                   services, budget, timeline, message, proposal_text,
                                   created_at, public_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            client_email, name, email, company, services, budget, timeline,
            message, proposal_text, datetime.utcnow(), str(uuid.uuid4())
        ))
        conn.commit()
        conn.close()

        # Send email to both client and lead
        send_proposal_email(
            to_lead=email,
            to_client=client_email,
            subject="New Proposal from " + settings['company_name'],
            proposal_body=proposal_text
        )

        return True

    except Exception as e:
        print(f"[ERROR] handle_new_proposal failed: {e}")
        return False