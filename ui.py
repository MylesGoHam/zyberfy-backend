import streamlit as st
from email_assistant import generate_reply
import re

st.set_page_config(page_title="Zyberfy", layout="centered")

st.markdown(
    """
    <style>
        body {
            background-color: #ffffff;
            color: #000000;
        }
        .stTextInput > div > div > input {
            border: 1px solid #000;
        }
        .stTextArea > div > textarea {
            border: 1px solid #000;
        }
        .title {
            font-size: 3em;
            font-weight: bold;
            color: #007BFF;
            text-align: center;
        }
        .subtitle {
            font-size: 1.2em;
            font-weight: 400;
            color: #ffffff;
            text-align: center;
            margin-bottom: 1em;
        }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="title">Zyberfy</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Automatically Respond To Customer Emails Like A Pro.</div>', unsafe_allow_html=True)

# Email validation function
def is_valid_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

# Email Input Fields
sender_email = st.text_input("Sender Email", key="sender")
recipient_email = st.text_input("Recipient Email", key="recipient")
tone = st.selectbox("Choose a reply tone", ["Professional", "Friendly", "Casual", "Confident", "Formal"])
email_input = st.text_area("Paste the email you received", height=200)

# Generate Reply Button with Validation
if st.button("Generate Reply"):
    if not is_valid_email(sender_email):
        st.warning("Please enter a valid sender email address.")
    elif not is_valid_email(recipient_email):
        st.warning("Please enter a valid recipient email address.")
    elif not email_input.strip():
        st.warning("Please paste an email to reply to.")
    else:
        with st.spinner("Generating reply..."):
            reply = generate_reply(sender_email, recipient_email, email_input, tone)
            st.text_area("Reply", value=reply, height=200)
            st.session_state.reply = reply

# Optional download button
if "reply" in st.session_state:
    st.download_button("Download .txt", st.session_state.reply, file_name="reply.txt")