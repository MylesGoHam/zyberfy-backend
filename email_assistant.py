import openai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_reply(email_input, tone, sender_name, recipient_name):
    prompt = f"""
You are an AI email assistant helping write a reply.

- Use a {tone.lower()} tone.
- Address the recipient as: Dear {recipient_name},
- Sign off with: {sender_name}

Here’s the email you’re replying to:
\"\"\"
{email_input}
\"\"\"

Now write a clear and helpful reply:
"""

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500
    )

    return response.choices[0].message["content"].strip()