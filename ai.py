# ai.py
import openai
import os
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_proposal(settings, form_data):
    try:
        subject = settings.get("subject", "Your Proposal from Our Team")
        greeting = settings.get("greeting", "Hi")
        tone = settings.get("tone", "Professional")
        footer = settings.get("footer", "Best regards,")
        ai_training = settings.get("ai_training", "Write clearly and persuasively.")
        
        lead_name = form_data.get("lead_name", "there").strip()
        message = form_data.get("message", "").strip()

        # Check for embedded offer in message
        offer_line = ""
        if "Offer Submitted:" in message:
            offer_amount = message.split("Offer Submitted:")[-1].strip()
            offer_line = f"\n\nNote: The lead has made a preliminary offer of {offer_amount}. Acknowledge and address it appropriately."

        prompt = f"""
        You are a helpful assistant trained to write elegant, human-sounding proposal emails.
        The client communicates in a tone that is: {tone}.
        Write in this voice: {ai_training}

        Generate a full email with:
        - Subject: {subject}
        - Greeting: {greeting} {lead_name}
        - Body: Based on this inquiry: {message}
        - Footer: {footer}
        {offer_line}

        Make it sound warm, persuasive, and professionally written.
        """

        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85
        )

        return response["choices"][0]["message"]["content"]

    except Exception as e:
        return f"⚠️ Error generating proposal: {str(e)}"
