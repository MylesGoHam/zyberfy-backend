import openai
import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

# Set OpenAI API key
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

    try:
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
