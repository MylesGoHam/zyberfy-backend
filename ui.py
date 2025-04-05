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
st.set_page_config(page_title="SmartReplies AI", page_icon="📩", layout="centered")
st.title("SmartReplies📧")

st.markdown("""
<h3 style="margin-bottom: 10px;">📮 Paste the email you'd like a reply to:</h3>
""", unsafe_allow_html=True)

# Email input
email_input = st.text_area("Incoming Email:", height=200, key="email_input_box")

# Save input to log
with open("test_emails.txt", "a") as f:
    f.write(email_input.strip() + "\n" + "-" * 40 + "\n")

# Tone selector
tone = st.selectbox("Choose a reply tone:",
                    ["", "Professional", "Friendly", "Direct", "Casual"],
                    key="tone_select")

# Recipient + sender names
recipient_name = st.text_input("Recipient Name", placeholder="e.g. John")
sender_name = st.text_input("Your Name", placeholder="e.g. Myles")

st.markdown("<br>", unsafe_allow_html=True)

# Generate button
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

                # Show output
                st.success("✅ Here's your reply:")
                st.markdown("## 🤖 Generated Email Reply")
                st.text_area("AI-Generated Reply:", value=reply, height=200, key="generated_reply_output")

                # Prepare filename and content
                filename = f"reply_to_{recipient_name.strip().lower().replace(' ', '_')}.txt"
                formatted_reply = f"""To: {recipient_name}\nFrom: {sender_name}\n\n{reply.strip()}\n"""

                # Export button
                st.markdown("### 📤 Export Options", unsafe_allow_html=True)
                st.download_button("Download .txt", formatted_reply, file_name=filename)

                # Manual copy fallback
                st.text_input("Copy manually:", value=reply, key="manual_copy_output")

                # Save full log
                with open("test_emails.txt", "a") as f:
                    f.write(f"{datetime.now()}\n")
                    f.write(f"📥 Incoming Email:\n{email_input.strip()}\n\n")
                    f.write(f"🤖 AI Reply:\n{reply.strip()}\n")
                    f.write("-" * 48 + "\n\n")

            except Exception as e:
                st.error(f"Something went wrong: {e}")

# 💅 Optional styling
st.markdown("""
<style>
textarea {
    border-radius: 10px !important;
    padding: 10px !important;
    font-size: 15px !important;
}
</style>
""", unsafe_allow_html=True)