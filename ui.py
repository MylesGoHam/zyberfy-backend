from email_assistant import generate_reply
import streamlit as st
import openai
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Page setup
st.set_page_config(page_title="SmartReplies", layout="centered")
theme = st.radio("", ["🌑 Dark", "🌞 Light"], horizontal=True)

if theme == "🌞 Light":
    background_color = "#ffffff"
    text_color = "#000000"
    box_background = "#ffffff"
    border_color = "#000000"
else:
    background_color = "#0E1117"
    text_color = "#ffffff"
    box_background = "#262730"
    border_color = "#ffffff"

st.markdown(f"""
    <style>
    body {{
        background-color: {background_color};
        color: {text_color};
    }}
    textarea, input, select {{
        background-color: {box_background} !important;
        color: {text_color} !important;
        border: 1px solid {border_color} !important;
        border-radius: 10px !important;
        padding: 10px !important;
        font-size: 16px !important;
    }}
    button[kind="primary"] {{
        background-color: #FF4B4B;
        color: white;
        border-radius: 10px;
        font-size: 16px;
        padding: 10px 20px;
    }}
    </style>
""", unsafe_allow_html=True)

# Title
st.markdown("""
    <h1 style='text-align: center;'>SmartReplies</h1>
    <p style='text-align: center;'>Automatically respond to customer emails like a pro.</p>
""", unsafe_allow_html=True)

# Email Input
st.markdown("<h4>Paste the email you'd like a reply to:</h4>", unsafe_allow_html=True)
email_input = st.text_area("Incoming Email", key="email_input_box", height=200, label_visibility="collapsed")

# Tone Selector
tone = st.selectbox("Choose a reply tone:", ["", "Professional", "Friendly", "Direct", "Casual"], key="tone_select")

# Names
recipient_name = st.text_input("Recipient Name", placeholder="e.g. John")
sender_name = st.text_input("Your Name", placeholder="e.g. Myles")

# Generate Reply
if st.button("Generate Reply"):
    if not email_input.strip():
        st.warning("Please enter an email message.")
    elif not tone:
        st.warning("Please select a reply tone.")
    elif not recipient_name.strip() or not sender_name.strip():
        st.warning("Please enter both recipient and sender names.")
    else:
        with st.spinner("Generating reply..."):
            try:
                reply = generate_reply(email_input, tone, sender_name, recipient_name)
                st.success("✅ Here's your reply:")
                st.markdown("## 🤖 Generated Email Reply")
                st.text_area("AI-Generated Reply:", value=reply, height=200, key="generated_reply_output")

                st.markdown("## 📤 Export Options")
                st.download_button("Download .txt", reply, file_name="reply.txt")
                st.text_input("Copy manually:", value=reply, key="manual_copy_output")

                with open("test_emails.txt", "a") as f:
                    f.write(f"{datetime.now()}\nIncoming Email:\n{email_input.strip()}\nAI Reply:\n{reply.strip()}\n{'-'*40}\n")
            except Exception as e:
                st.error(f"Something went wrong: {e}")
