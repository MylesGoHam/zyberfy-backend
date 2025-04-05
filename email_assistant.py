import openai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_reply(email_input, tone):
    prompt = f"Reply to the following email in a {tone} tone:\n\n{email_input}"

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
    )

    reply = response.choices[0].message.content
    return reply