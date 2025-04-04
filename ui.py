import streamlit as st
import openai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Streamlit UI
st.set_page_config(page_title="Email Assistant", layout="centered")
st.title("📧 AI Email Assistant")

email_input = st.text_area("Paste the email message you want a reply to:")

# Add tone selection dropdown
tone = st.selectbox(
    "Choose a reply tone:",
    ("Casual", "Professional", "Friendly", "Assertive")
)

if st.button("Generate Reply"):
    if email_input.strip() == "":
        st.warning("Please enter an email message.")
    else:
        with st.spinner("Generating reply..."):
            try:
                client = openai.OpenAI()
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": f"You are a helpful assistant that writes *{tone.lower()}* replies to emails."
                        },
                        {
                            "role": "user",
                            "content": email_input
                        }
                    ]
                )
                reply = response.choices[0].message.content
                st.success("Here's your reply:")
                st.text_area("Generated Reply", value=reply, height=200)
            except Exception as e:
                st.error(f"Error: {str(e)}")