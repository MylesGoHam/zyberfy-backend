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
st.set_page_config(page_title="SmartReplies", layout="centered")
st.title("SmartReplies")
st.caption("Automatically respond to customer emails like a pro.")

st.markdown("""
<h4>Paste the email you'd like a reply to:</h4>
""", unsafe_allow_html=True)

# Email input
email_input = st.text_area("Incoming Email:", height=200, key="email_input_box")

# Save input to log
with open("test_emails.txt", "a") as f:
    f.write(email_input.strip() + "\n" + "-" * 40 + "\n")

# Tone selector
st.markdown("<br><b>Choose a reply tone:</b>", unsafe_allow_html=True)
tone = st.selectbox(" ", ["", "Professional", "Friendly", "Direct", "Casual"], key="tone_select", label_visibility="collapsed")

# Recipient and sender name
recipient_name = st.text_input("Recipient Name", placeholder="e.g. John")
sender_name = st.text_input("Your Name", placeholder="e.g. Myles")

# Generate Reply
if st.button("Generate Reply"):
    if not email_input.strip():
        st.warning("Please enter an email message.")
    elif not tone:
        st.warning("Please select a reply tone.")
    elif not recipient_name or not sender_name:
        st.warning("Please enter both recipient and sender names.")
    else:
        with st.spinner("Generating reply..."):
            try:
                reply = generate_reply(email_input, tone, sender_name, recipient_name)

                # Display output
                st.success("\u2705 Here's your reply:")
                st.markdown("## Generated Email Reply")
                st.text_area("AI-Generated Reply:", value=reply, height=200, key="generated_reply_output")

                # Export
                st.markdown("## Export Options")
                st.download_button("Download .txt", reply, file_name="reply.txt")

                # Manual copy fallback
                st.text_input("Copy manually:", value=reply, key="manual_copy_output")

                # Save to log
                with open("test_emails.txt", "a") as f:
                    f.write(f"{datetime.now()}\n")
                    f.write(f"Incoming Email:\n{email_input.strip()}\n")
                    f.write(f"AI Reply:\n{reply.strip()}\n")
                    f.write("-" * 40 + "\n\n")

            except Exception as e:
                st.error(f"Something went wrong: {e}")

# Optional styling
st.markdown("""
<style>
    textarea, input, select {
        border-radius: 10px !important;
        padding: 10px !important;
        font-size: 15px !important;
    }
    .stTextInput input, .stDownloadButton button, .stSelectbox div, .stTextArea textarea {
        border: 1px solid #333;
    }
</style>
""", unsafe_allow_html=True)
