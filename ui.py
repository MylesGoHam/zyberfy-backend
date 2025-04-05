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
st.set_page_config(page_title="SmartReplies AI", layout="centered", page_icon="📬")

# Theming
st.markdown("<h1 style='text-align: center;'>📬 SmartReplies AI</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>Automatically respond to customer emails like a pro.</p>", unsafe_allow_html=True)
theme = st.radio("Choose Theme", options=["Dark", "Light"], index=0, horizontal=True)

# Input styling based on theme
if theme == "Dark":
    bg_color = "#1E1E1E"
    text_color = "#FFFFFF"
else:
    bg_color = "#FFFFFF"
    text_color = "#000000"

st.markdown(
    f"""
    <style>
    textarea, input, select {{
        background-color: {bg_color} !important;
        color: {text_color} !important;
        border-radius: 10px !important;
        padding: 10px !important;
        font-size: 16px !important;
        border: 1px solid #ccc !important;
    }}
    .stButton>button {{
        background: linear-gradient(to right, #ff4b2b, #ff416c);
        color: white;
        border-radius: 12px;
        padding: 0.5em 1.2em;
        font-weight: bold;
    }}
    </style>
    """,
    unsafe_allow_html=True
)

# Inputs
st.markdown("### 📧 Paste the email you'd like a reply to:")
email_input = st.text_area("Incoming Email:", key="email_input_box", height=200)

tone = st.selectbox("🍒 Choose a reply tone:", ["", "Professional", "Friendly", "Direct", "Casual"], key="tone_select")

recipient_name = st.text_input("👤 Recipient Name", placeholder="e.g. John")
sender_name = st.text_input("✍️ Your Name", placeholder="e.g. Myles")

# Submit
if st.button("🧠 Generate Reply"):
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
                st.success("✅ Here's your reply:")
                st.markdown("## 🤖 Generated Email Reply")
                st.text_area("AI-Generated Reply:", value=reply, height=200, key="generated_reply_output")

                # Export section
                st.markdown("## 📤 Export Options ↩️")
                st.download_button("Download .txt", reply, file_name="reply.txt")

                st.markdown("#### 📋 Copy manually:")
                st.text_input("", value=reply, key="manual_copy_output")

                # Save to log
                with open("test_emails.txt", "a") as f:
                    f.write(f"{datetime.now()}\n")
                    f.write(f"Incoming Email:\n{email_input.strip()}\n\n")
                    f.write(f"AI Reply:\n{reply.strip()}\n")
                    f.write("=" * 40 + "\n")

            except Exception as e:
                st.error(f"Something went wrong: {e}")