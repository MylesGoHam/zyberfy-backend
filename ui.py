from email_assistant import generate_reply
import streamlit as st
import openai
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# UI Setup
st.set_page_config(page_title="SmartReplies AI", layout="centered")

# Theme Toggle
selected_theme = st.radio("Choose Theme", ["Dark", "Light"], horizontal=True)
if selected_theme == "Light":
    st.markdown("""
        <style>
            html, body, [class*="css"] {
                background-color: #ffffff;
                color: #000000;
            }
            .stTextInput input, .stTextArea textarea, .stSelectbox div, .stDownloadButton button {
                background-color: #ffffff;
                color: #000000;
            }
        </style>
    """, unsafe_allow_html=True)

# Header
st.markdown("""
    <h1 style='text-align: center;'>SmartReplies AI</h1>
    <h4 style='text-align: center;'>Automatically respond to customer emails like a pro.</h4>
""", unsafe_allow_html=True)

# Email input
st.markdown("### Paste the email you'd like a reply to:")
email_input = st.text_area("Incoming Email:", height=180, key="email_input_box")

# Tone selector
st.markdown("### Choose a reply tone:")
tone = st.selectbox("", ["", "Professional", "Friendly", "Direct", "Casual"], key="tone_select")

# Recipient and sender
recipient_name = st.text_input("Recipient Name", placeholder="e.g. John")
sender_name = st.text_input("Your Name", placeholder="e.g. Myles")

# Generate reply
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
                st.markdown("## Generated Email Reply")
                st.text_area("AI-Generated Reply:", value=reply, height=200, key="generated_reply_output")

                # Export options
                st.markdown("## Export Options")
                st.download_button("Download .txt", reply, file_name="reply.txt")

                # Manual fallback
                st.text_input("Copy manually:", value=reply, key="manual_copy_output")

                # Log to file
                with open("test_emails.txt", "a") as f:
                    f.write(f"{datetime.now()}\n")
                    f.write(f"Incoming Email:\n{email_input.strip()}\n\n")
                    f.write(f"AI Reply:\n{reply.strip()}\n\n")
                    f.write("=" * 50 + "\n")
            except Exception as e:
                st.error(f"Something went wrong: {e}")

# Optional styling
st.markdown("""
    <style>
        textarea, input[type="text"] {
            border-radius: 10px !important;
            padding: 10px !important;
            font-size: 15px !important;
        }
        .stDownloadButton > button {
            background-color: #444654;
            color: white;
            border-radius: 8px;
            padding: 10px 16px;
            font-size: 15px;
        }
    </style>
""", unsafe_allow_html=True)