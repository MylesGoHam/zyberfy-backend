def generate_proposal(settings, form_data):
    subject = settings["subject"]
    greeting = settings["greeting"]
    tone = settings["tone"]
    footer = settings["footer"]
    ai_training = settings["ai_training"]
    accept_msg = settings["accept_msg"]
    decline_msg = settings["decline_msg"]
    proposal_mode = settings["proposal_mode"]

    lead_name = form_data.get("lead_name", "there")
    message = form_data.get("message", "")

    # Build your system prompt
    system_prompt = f"""
You are a helpful AI assistant that writes {proposal_mode} email proposals for {settings['email']}'s business in a {tone} tone.

Start with a personalized greeting like "{greeting}", write a response based on the message below, and end with "{footer}".

The business has trained you with this style guide: "{ai_training}"

If this is an offer, use this acceptance message: "{accept_msg}". 
If declining, use this: "{decline_msg}".
"""

    user_prompt = f"""
Message from lead {lead_name}: {message}
Write a full reply as an email proposal.
"""

    response = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.8
    )

    return response["choices"][0]["message"]["content"]
