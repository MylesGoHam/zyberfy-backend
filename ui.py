import streamlit as st
import requests
import posthog

# Initialize PostHog
posthog.api_key = "phc_HHlLr5iPRAK8q7slEoM3HIdbEvec9JR13ay5tRmVx4V"
posthog.host = "https://us.i.posthog.com"

# Track page view
posthog.capture(distinct_id="smartreplies_user", event="page_view")

# UI setup
st.set_page_config(page_title="SmartReplies", layout="centered")
st.markdown("<h1 style='text-align: center;'>SmartReplies</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size: 18px;'>Automatically respond to customer emails like a pro.</p>", unsafe_allow_html=True)

st.markdown("### Paste the email you'd like a reply to:")
email_input = st.text_area("Incoming Email:", height=200, label_visibility="collapsed", key="email_input_box")

st.markdown("### Choose a reply tone:")
tone = st.selectbox("", ["Professional", "Friendly", "Direct", "Casual"], key="tone_select")

sender_name = st.text_input("Recipient Name", placeholder="e.g. John")
recipient_name = st.text_input("Your Name", placeholder="e.g. Myles")

if st.button("Generate Reply"):
    if not email_input.strip() or not sender_name.strip() or not recipient_name.strip():
        st.warning("Please complete all fields before generating a reply.")
    else:
        posthog.capture(distinct_id="smartreplies_user", event="generate_reply_clicked")

        with st.spinner("Generating reply..."):
            try:
                response = requests.post("https://smartrepliesai.onrender.com/generate_reply", json={
                    "incoming_email": email_input,
                    "tone": tone,
                    "sender_name": sender_name,
                    "recipient_name": recipient_name
                })
                response.raise_for_status()
                reply = response.json().get("reply", "")
                st.success("✅ Here's your reply:")

                st.markdown("### Generated Email Reply")
                st.text_area("AI-Generated Reply:", value=reply, height=200, key="generated_reply_output")

                st.markdown("### Export Options")
                st.download_button(
                    label="Download .txt",
                    data=f"To: {recipient_name}\n\nFrom: {sender_name}\n\n{reply.strip()}",
                    file_name=f"{recipient_name.lower().replace(' ', '_')}_reply.txt",
                    mime="text/plain",
                )

                st.text_area("Copy manually:", value=reply.replace("\n", " "), key="manual_copy_output")

            except requests.exceptions.RequestException as e:
                st.error(f"An error occurred while generating the reply: {e}")