import openai
import os
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_proposal(settings, form_data):
    subject = settings["subject"]
    greeting = settings["greeting"]
    tone = settings["tone"]
    footer = settings["footer"]
    ai_training = settings["ai_training"]
    proposal_mode = settings["proposal_mode"]

    detail_instruction = "Keep it brief and to the point." if proposal_mode == "concise" else "Feel free to elaborate with a persuasive tone."

    prompt = f"""
You are a helpful assistant trained to write elegant and on-brand proposal emails.

- The client's tone is: {tone}
- The assistant should write in this voice: {ai_training}
- Proposal Mode: {proposal_mode} – {detail_instruction}

Please generate a full email with:
- Subject: {subject}
- Greeting: {greeting} {form_data['lead_name']}
- Body: Based on this inquiry: {form_data['message']}
- Signature/Footer: {footer}

Make it sound human, thoughtful, and professional.
"""

    response = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8
    )

    return response["choices"][0]["message"]["content"]
