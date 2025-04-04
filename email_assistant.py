import os
from openai import OpenAI
from dotenv import load_dotenv

# Load your OpenAI API key from .env file
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
email_text = input("Paste the email message you want a reply to:\n")

response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": "You're a helpful assistant that writes polite, professional replies."},
        {"role": "user", "content": email_text}
    ]
)

print("\nGenerated Reply:\n")
print(response.choices[0].message.content)