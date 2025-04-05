from email_assistant import generate_reply
import streamlit as st
import openai
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Page configuration
st.set_page_config(page_title="SmartReplies", layout="centered")

# Custom styling for better layout and input visuals
st.markdown("""
    <style>
        .main {
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        h1 {
            text-align: center;
            font-size: 3rem;
        }
        h4 {
            font-size: 1.4rem;
            margin-bottom: 0.75rem;
        }
        .stTextInput > div > div > input, .stTextArea textarea {
            border-radius: 8px;
            border: 1px solid #888;
            padding: 10px;
            font-size: 16px;
        }
        .stSelectbox > div > div {
            border: 1px solid #888 !important;
            border-radius: 8px !important;
        }
        .stTextInput input::placeholder, .stTextArea textarea::placeholder {
            color: #999;
        }
    </style>
""", unsafe_allow_html=True)

# UI Title and Instructions
st.markdown("""
    <div class="main">
        <h1>SmartReplies</h1>
        <h4>Automatically respond to customer emails like a pro.</h4>
    </div>
""", unsafe_allow_html=True)

# Input Section
st.subheader("Paste the email you'd like a reply to:")
email_input = st.text_area("Incoming Email:", height=200, key="email_input_box", label_visibility="collapsed")

# Reply tone
st.subheader("Choose a reply tone:")
tone = st.selectbox("", ["Professional", "Friendly", "Direct", "Casual"], key="tone_select")

# Sender & Recipient Names
recipient_name = st.text_input("Recipient Name", placeholder="e.g. John")
sender_name = st.text_input("Your Name", placeholder="e.g. Myles")

# Generate Button
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
                st.subheader("Generated Email Reply")
                st.text_area("AI-Generated Reply:", value=reply, height=200, key="generated_reply_output")

                st.subheader("Export Options")
                st.download_button("Download .txt", reply, file_name="reply.txt")
                st.text_input("Copy manually:", value=reply, key="manual_copy_output")

                with open("test_emails.txt", "a") as f:
                    f.write(f"{datetime.now()}\n")
                    f.write(f"Incoming Email:\n{email_input.strip()}\n")
                    f.write(f"AI Reply:\n{reply.strip()}\n")
                    f.write("-" * 40 + "\n")

            except Exception as e:
                st.error(f"Something went wrong: {e}")

