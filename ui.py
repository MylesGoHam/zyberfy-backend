from email_assistant import generate_reply
import streamlit as st
import openai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# UI Setup
st.set_page_config(page_title="SmartReplies AI", page_icon="📧", layout="centered")
st.title("SmartReplies 📧")

st.markdown("<h3 style='margin-bottom: 10px;'>📩 Paste the email you'd like a reply to:</h3>", unsafe_allow_html=True)
email_input = st.text_area("Incoming Email", height=200)
# Save input to a local file for testing/training
with open("test_emails.txt", "a") as f:
    f.write(email_input.strip() + "\n---\n")
st.markdown("<br>", unsafe_allow_html=True)
tone = st.selectbox("Choose a reply tone:", ["Professional", "Friendly", "Direct", "Casual"])
st.markdown("<br>", unsafe_allow_html=True)
if st.button("Generate Reply"):
    if not email_input.strip():
        st.warning("Please enter an email message.")
    else:
        with st.spinner("Generating reply..."):
            try:
                prompt = f"Reply to the following email in a {tone} tone:\n\n{email_input}"

                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                )

                reply = response.choices[0].message.content

                st.success("Here’s your reply:")
                st.markdown("### ✨ Generated Email Reply")
                st.text_area("AI-Generated Reply", value=reply, height=200, key="reply_output")
                st.markdown("<hr>", unsafe_allow_html=True)  # horizontal line
                st.markdown("### Export Options", unsafe_allow_html=True)  
                st.markdown("<br>", unsafe_allow_html=True)
                # Download button
                st.download_button("📥 Download Reply as .txt", reply, file_name="reply.txt")

                # Copy workaround: shows value that can be copied manually
                st.text_input("Copy manually:", value=reply, key="copy_text")

            except Exception as e:
                st.error(f"Something went wrong: {e}")
                # Custom styling
st.markdown(
    """
    <style>
    textarea {
        border-radius: 10px !important;
        padding: 10px !important;
        font-size: 15px !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)
from datetime import datetime

# ...

    # Save input and reply to a local file for testing/training
try:
    ...
    reply = generate_reply(email_input, selected_tone)

    st.text_area("AI-Generated Reply", value=reply, height=200, key="reply_output")
    
    # Save input and reply to a local file for testing/training
    with open("test_emails.txt", "a") as f:
        f.write(f"{datetime.now()}\n")
        f.write(f"Incoming Email:\n{email_input.strip()}\n\n")
        f.write(f"AI Reply:\n{reply.strip()}\n")
        f.write("-" * 40 + "\n\n")

    ...
except Exception as e:
    st.error(f"Something went wrong: {e}")