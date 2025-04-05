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
st.title("📨 SmartReplies")
st.caption("Automatically respond to customer emails like a pro.")

# Theme toggle
theme = st.radio(" ", ["Dark", "Light"], horizontal=True)
dark_mode = theme == "Dark"

# Style
st.markdown(f"""
<style>
    body {{
        background-color: {"#0e1117" if dark_mode else "#ffffff"};
        color: {"white" if dark_mode else "black"};
    }}
    .stTextInput > div > div > input,
    .stTextArea > div > textarea,
    .stSelectbox > div > div > div {{
        background-color: {"#262730" if dark_mode else "#ffffff"} !important;
        border: 1px solid black !important;
        color: {"white" if dark_mode else "black"} !important;
    }}
    .stButton > button {{
        background-color: #ff4b4b;
        color: white;
        border-radius: 8px;
        padding: 8px 20px;
        font-weight: 600;
        border: none;
        transition: all 0.2s;
    }}
    .stButton > button:hover {{
        background-color: #ff1c1c;
        transform: scale(1.02);
    }}
    textarea, input, select {{
        font-size: 15px !important;
    }}
</style>
""", unsafe_allow_html=True)

# Inputs
email_input = st.text_area("Paste the email you'd like a reply to:", height=200, key="email_input_box")
tone = st.selectbox("Choose a reply tone:", ["", "Professional", "Friendly", "Direct", "Casual"], key="tone_select")
recipient_name = st.text_input("Recipient Name", placeholder="e.g. John")
sender_name = st.text_input("Your Name", placeholder="e.g. Myles")

# Validation + Generate
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

                # Export
                st.markdown("### 📤 Export Options")
                st.download_button("Download .txt", reply, file_name="reply.txt")

                # Manual copy
                st.text_input("Copy manually:", value=reply, key="manual_copy_output")

                # Save log
                with open("test_emails.txt", "a") as f:
                    f.write(f"{datetime.now()}\n")
                    f.write(f"Incoming Email:\n{email_input.strip()}\n")
                    f.write(f"AI Reply:\n{reply.strip()}\n")
                    f.write("-" * 40 + "\n")

            except Exception as e:
                st.error(f"Something went wrong: {e}")