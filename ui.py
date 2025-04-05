import streamlit as st
import re
from email_assistant import generate_reply
from datetime import datetime
import posthog

# === PostHog Analytics Setup ===
posthog.api_key = "phc_HHlLr5iPRAK8q7sLEoM3HIdbEveC9JR13ay5tRmVx4V"
posthog.host = "https://us.i.posthog.com"

# === UI Config ===
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
            color: white;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="title">SmartReplies</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Automatically Respond To Customer Emails Like A Pro.</div>', unsafe_allow_html=True)
st.markdown("---")

# === Email Fields ===
sender_email = st.text_input("Your Email", placeholder="you@example.com")
recipient_email = st.text_input("Recipient Email", placeholder="recipient@example.com")

# === Validation ===
email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
if sender_email and not re.match(email_regex, sender_email):
    st.warning("Please enter a valid sender email address.")

if recipient_email and not re.match(email_regex, recipient_email):
    st.warning("Please enter a valid recipient email address.")

# === Input Email ===
input_email = st.text_area("Paste the email you received", height=200)

# === Tone ===
tone = st.selectbox("Choose a reply tone", ["Professional", "Friendly", "Witty", "Neutral"])

# === Generate Button ===
if st.button("Generate Reply"):
    if not sender_email or not recipient_email or not input_email:
        st.error("Fill out all fields before generating a reply.")
    elif not re.match(email_regex, sender_email) or not re.match(email_regex, recipient_email):
        st.error("Please enter valid email addresses.")
    else:
        posthog.capture(distinct_id=sender_email, event="generate_reply_clicked")

        with st.spinner("Generating your reply..."):
            try:
                reply = generate_reply(input_email, tone, sender_email, recipient_email)
                st.success("Reply generated!")
                st.text_area("AI-Generated Reply", value=reply, height=200)

                # === Export Download ===
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                filename = f"SmartReply_{timestamp}.txt"
                st.download_button("Download .txt", data=reply, file_name=filename, mime="text/plain")

                # === Feedback Buttons ===
                st.markdown("### Was this reply helpful?")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("👍 Yes, helpful"):
                        posthog.capture(
                            distinct_id=sender_email,
                            event="feedback_helpful",
                            properties={"timestamp": str(datetime.now()), "tone": tone}
                        )
                        st.success("Thanks for the feedback!")
                with col2:
                    if st.button("💬 Suggest improvement"):
                        with st.form("suggestion_form"):
                            feedback_text = st.text_area("Your suggestion:")
                            submitted = st.form_submit_button("Submit")
                            if submitted and feedback_text:
                                posthog.capture(
                                    distinct_id=sender_email,
                                    event="feedback_suggestion",
                                    properties={
                                        "suggestion": feedback_text,
                                        "tone": tone,
                                        "timestamp": str(datetime.now())
                                    }
                                )
                                st.success("Thanks! Suggestion submitted.")
            except Exception as e:
                st.error(f"An error occurred: {e}")