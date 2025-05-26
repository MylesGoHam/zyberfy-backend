from slugify import slugify
import random
import string

def handle_new_proposal(name, email, company, services, budget, timeline, message, client_email):
    try:
        conn = get_db_connection()

        # ✅ Check proposal limit
        count_row = conn.execute("SELECT COUNT(*) as count FROM proposals WHERE user_email = ?", (client_email,)).fetchone()
        if count_row["count"] >= 3:
            conn.close()
            print(f"[LIMIT] Client {client_email} reached proposal cap.")
            return "LIMIT_REACHED"

        # ✅ Fetch automation + identity
        settings = get_user_automation(client_email)
        user_row = conn.execute("SELECT * FROM users WHERE email = ?", (client_email,)).fetchone()
        settings_row = conn.execute("SELECT * FROM settings WHERE email = ?", (client_email,)).fetchone()

        if not (settings and user_row and settings_row):
            conn.close()
            print("[ERROR] Missing automation or user/settings.")
            return None

        # 🔨 Generate unique public_id from business name
        base_slug = slugify(settings_row["company_name"] or "client")
        rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        proposal_public_id = f"{base_slug}-{rand_suffix}"

        # ✅ Generate proposal
        prompt = (
            f"Write a {settings.get('length', 'concise')} business proposal in a {settings.get('tone', 'friendly')} tone.\n"
            f"Client: {settings_row['first_name']} ({settings_row['position']}) from {settings_row['company_name']}.\n"
            f"Website: {settings_row['website']}, Contact: {settings_row['reply_to']} / {settings_row['phone']}.\n"
            f"Lead Info: {name} from {company}, wants: {services}, budget: {budget}, timeline: {timeline}.\n"
            f"Extra message from lead: {message}\n"
            f"Generate a custom response from the client to the lead."
        )

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7
        )
        proposal_text = response["choices"][0]["message"]["content"].strip()

        # ✅ Insert new proposal
        conn.execute("""
            INSERT INTO proposals (
                public_id,
                user_email,
                lead_name,
                lead_email,
                lead_company,
                services,
                budget,
                timeline,
                message,
                proposal_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            proposal_public_id,
            client_email,
            name,
            email,
            company,
            services,
            budget,
            timeline,
            message,
            proposal_text
        ))
        conn.commit()
        conn.close()

        # ✅ Notifications + email
        log_event("generated_proposal", user_email=client_email, metadata={"public_id": proposal_public_id})
        send_proposal_email(
            to_email=email,
            subject="Your Proposal Has Been Received",
            content=proposal_text,
            cc_client=True,
            client_email=client_email
        )

        return proposal_public_id

    except Exception as e:
        print(f"[ERROR] Failed to handle proposal: {e}")
        return None
