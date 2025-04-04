import streamlit as st
import openai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# UI Setup
st.set_page_config(page_title="SmartReplies AI", page_icon="📧", layout="centered")
st.title("📧 AI Email Assistant")

st.markdown("### Paste the email message you want a reply to:")
email_input = st.text_area("Incoming Email", height=200)

tone = st.selectbox("Choose a reply tone:", ["Professional", "Friendly", "Direct", "Casual"])

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
                st.text_area("AI-Generated Reply", value=reply, height=200, key="reply_output")

                # Download button
                st.download_button("📥 Download Reply as .txt", reply, file_name="reply.txt")

                # Copy workaround: shows value that can be copied manually
                st.text_input("Copy manually:", value=reply, key="copy_text")

            except Exception as e:
                st.error(f"Something went wrong: {e}")