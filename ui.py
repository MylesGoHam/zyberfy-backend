import streamlit as st
import re
from email_assistant import generate_reply
from datetime import datetime

st.set_page_config(page_title="SmartReplies", layout="centered")
st.markdown("""
    <style>
        body {
            background-color: #f5f9ff;
        }
        .title {
            text-align: center;
            font-size: 2.8em;
            font-weight: 800;
            margin-bottom: 0;
        }
        .subtitle {
            text-align: center;
            font-size: 1.3em;
            margin-top: 0.2em;
            color: #333;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="title">SmartReplies</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Instant, AI-powered email replies in your tone</div>', unsafe_allow_html=True)

st.markdown("---")

# Email input fields
sender_email = st.text_input("Your Email", placeholder="you@example.com")
recipient_email = st.text_input("Recipient Email", placeholder="recipient@example.com")

# Email validation
email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
if sender_email and not re.match(email_regex, sender_email):
    st.warning("Please enter a valid sender email address.")

if recipient_email and not re.match(email_regex, recipient_email):
    st.warning("Please enter a valid recipient email address.")

# Main email content input
input_email = st.text_area("Paste the email you received", height=200)

# Reply tone selection
tone = st.selectbox("Choose a reply tone", ["Professional", "Friendly", "Witty", "Neutral"])

# Generate button
if st.button("Generate Reply"):
    if not sender_email or not recipient_email or not input_email:
        st.error("Please fill out all fields before generating a reply.")
    elif not re.match(email_regex, sender_email) or not re.match(email_regex, recipient_email):
        st.error("Please enter valid email addresses.")
    else:
        with st.spinner("Generating your reply..."):
            reply = generate_reply(input_email, tone)
            st.success("Reply generated!")
            st.text_area("AI-Generated Reply", reply, height=200)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"SmartReply_{timestamp}.txt"
            st.download_button("Download .txt", data=reply, file_name=filename, mime="text/plain")
