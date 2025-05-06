import openai
import uuid
from datetime import datetime

<<<<<<< Updated upstream
from models import get_db_connection
from email_utils import send_proposal_email
from sms_utils import send_sms_alert  # ✅ Import goes here
=======
load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_proposal(name, service, budget, location, special_requests):
    prompt = f"""
You are an elite concierge assistant writing high-end service proposals.
Client Name: {name}
Requested Service: {service}
Budget: {budget}
Location: {location}
Special Requests: {special_requests}

Write a polished, luxury-style service proposal in under 200 words.
    """
>>>>>>> Stashed changes

def handle_new_proposal(name, email, company, services, budget, timeline, message, client_email):
    try:
<<<<<<< Updated upstream
        conn = get_db_connection()
        settings = conn.execute("""
            SELECT first_name, company_name, position, website, phone, reply_to, tone, length
            FROM automation_settings
            WHERE email = ?
        """, (client_email,)).fetchone()
        conn.close()

        if not settings:
            raise ValueError("Client automation settings not found.")

        # Prompt for GPT
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

        # Save proposal to DB
        conn = get_db_connection()
        public_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO proposals (user_email, lead_name, lead_email, lead_company,
                                   services, budget, timeline, message, proposal_text,
                                   created_at, public_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            client_email, name, email, company, services, budget, timeline,
            message, proposal_text, datetime.utcnow(), public_id
        ))
        conn.commit()
        conn.close()

        # Send email to lead and client
        send_proposal_email(
            to_lead=email,
            to_client=client_email,
            subject="New Proposal from " + settings['company_name'],
            proposal_body=proposal_text
        )

        # ✅ Send SMS to client
        if settings["phone"]:
            sms_message = f"New proposal from {name} for {services}. Check your dashboard."
            send_sms_alert(settings["phone"], sms_message)

        return True

    except Exception as e:
        print(f"[ERROR] handle_new_proposal failed: {e}")
        return False
=======
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You write upscale, warm proposals for concierge clients."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"OpenAI Error: {e}")
        return "We're preparing your custom proposal. A concierge will follow up shortly."
>>>>>>> Stashed changes
