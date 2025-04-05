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
st.set_page_config(page_title="SmartReplies AI", page_icon="✉️", layout="centered")
st.title("SmartReplies ✨")

st.markdown(
    "<h3 style='margin-bottom: 10px;'>📨 Paste the email you'd like a reply to:</h3>",
    unsafe_allow_html=True
)
email_input = st.text_area("Incoming Email:", height=200, key="email_input_box")

# Save input for testing/training
with open("test_emails.txt", "a") as f:
    f.write(email_input.strip() + "\n" + "-" * 40 + "\n")

tone = st.selectbox("Choose a reply tone:", ["Professional", "Friendly", "Direct", "Casual"], key="tone_select")

st.markdown("<br>", unsafe_allow_html=True)

if st.button("Generate Reply"):
    if not email_input.strip():
        st.warning("Please enter an email message.")
    else:
        with st.spinner("Generating reply..."):
            try:
                reply = generate_reply(email_input, tone)

                st.success("✅ Here's your reply:")
                st.markdown("### 🤖 Generated Email Reply")
                st.text_area("AI-Generated Reply", value=reply, height=200, key="generated_reply_output")

                st.markdown("<hr>", unsafe_allow_html=True)
                st.markdown("### 📥 Export Options", unsafe_allow_html=True)
                st.download_button("📩 Download Reply as .txt", reply, file_name="reply.txt")

                # Manual copy fallback
                st.text_input("Copy manually:", value=reply, key="manual_copy_output")

                # Save both input and reply
                with open("test_emails.txt", "a") as f:
                    f.write(f"{datetime.now()}\n")
                    f.write(f"Incoming Email:\n{email_input.strip()}\n")
                    f.write(f"AI Reply:\n{reply.strip()}\n")
                    f.write("-" * 40 + "\n\n")

            except Exception as e:
                st.error(f"Something went wrong: {e}")

# Optional custom styling
st.markdown("""
    <style>
        textarea {
            border-radius: 10px !important;
            padding: 10px !important;
            font-size: 15px !important;
        }
    </style>
""", unsafe_allow_html=True)