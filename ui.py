from email_assistant import generate_reply
import streamlit as st
import openai
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Page config
st.set_page_config(page_title="SmartReplies AI", page_icon="📧", layout="centered")

# Styling
st.markdown("""
<style>
:root {
    --primary-bg: #0e1117;
    --card-bg: #1e2127;
    --text-color: #f0f0f0;
    --input-bg: #252830;
    --border-radius: 12px;
}

body {
    background-color: var(--primary-bg);
    color: var(--text-color);
}

textarea, input, select {
    border-radius: var(--border-radius) !important;
    padding: 10px !important;
    font-size: 16px !important;
    background-color: var(--input-bg) !important;
    color: white !important;
}

.stTextInput > div > div > input {
    background-color: var(--input-bg) !important;
}

.stButton button, .stDownloadButton button {
    border-radius: var(--border-radius);
    font-size: 16px;
    padding: 0.6em 1.2em;
    margin-top: 12px;
}

.card {
    background-color: var(--card-bg);
    padding: 25px;
    border-radius: var(--border-radius);
    box-shadow: 0 0 12px rgba(0, 0, 0, 0.3);
    margin-top: 20px;
}
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("<h1 style='text-align: center;'>📬 SmartReplies AI</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>Automatically respond to customer emails like a pro.</p>", unsafe_allow_html=True)

# Light/Dark Toggle (Streamlit-native hack)
theme = st.radio("Choose Theme", ["🌙 Dark", "☀️ Light"], horizontal=True)
if theme == "☀️ Light":
    st.markdown("""
        <style>
        body, .stApp {
            background-color: #ffffff !important;
            color: #000000 !important;
        }
        .card {
            background-color: #f1f1f1 !important;
            color: #000000 !important;
        }
        textarea, input, select {
            background-color: #ffffff !important;
            color: #000000 !important;
        }
        </style>
    """, unsafe_allow_html=True)

# ✉️ Email Card
with st.container():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### ✉️ Paste the email you'd like a reply to:")

    email_input = st.text_area("Incoming Email:", height=200, key="email_input_box")
    with open("test_emails.txt", "a") as f:
        f.write(email_input.strip() + "\n" + "-" * 40 + "\n")

    tone = st.selectbox("🎯 Choose a reply tone:", ["", "Professional", "Friendly", "Direct", "Casual"])
    recipient_name = st.text_input("👤 Recipient Name", placeholder="e.g. John")
    sender_name = st.text_input("✍️ Your Name", placeholder="e.g. Myles")
    st.markdown("</div>", unsafe_allow_html=True)

# 🚀 Generate Reply
if st.button("🧠 Generate Reply"):
    if not email_input.strip():
        st.warning("Please enter an email message.")
    elif not tone:
        st.warning("Please select a reply tone.")
    elif not recipient_name or not sender_name:
        st.warning("Please enter both recipient and sender names.")
    else:
        with st.spinner("✍️ Crafting the perfect reply..."):
            try:
                reply = generate_reply(email_input, tone, sender_name, recipient_name)

                # Display
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.success("✅ Here's your reply:")
                st.markdown("### 🤖 Generated Email Reply")
                st.text_area("AI-Generated Reply:", value=reply, height=200, key="generated_reply_output")

                # Export
                st.markdown("### 📤 Export Options")
                st.download_button("Download .txt", reply, file_name="reply.txt")

                # Manual Copy
                st.text_input("📋 Copy manually:", value=reply, key="manual_copy_output")
                st.markdown("</div>", unsafe_allow_html=True)

                # Save full log
                with open("test_emails.txt", "a") as f:
                    f.write(f"{datetime.now()}\n")
                    f.write(f"Incoming Email:\n{email_input.strip()}\n\n")
                    f.write(f"AI Reply:\n{reply.strip()}\n")
                    f.write("-" * 48 + "\n\n")

            except Exception as e:
                st.error(f"Something went wrong: {e}")