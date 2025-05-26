def handle_new_proposal(name, email, company, services, budget, timeline, message, client_email):
    try:
        import uuid
        from slugify import slugify
        from utils import generate_qr_code

        conn = get_db_connection()

        # ✅ Check if client has exceeded proposal limit
        count_row = conn.execute("SELECT COUNT(*) as count FROM proposals WHERE user_email = ?", (client_email,)).fetchone()
        proposal_count = count_row["count"]
        PROPOSAL_LIMIT = 3  # Temporary free plan limit
        if proposal_count >= PROPOSAL_LIMIT:
            conn.close()
            print(f"[LIMIT] Client {client_email} reached proposal cap.")
            return "LIMIT_REACHED"

        # ✅ Fetch client's automation settings
        settings = get_user_automation(client_email)
        if not settings:
            conn.close()
            print("[ERROR] No automation settings found.")
            return None

        tone   = settings.get("tone", "friendly")
        length = settings.get("length", "concise")

        # ✅ Pull client identity and contact info
        user_row = conn.execute("SELECT * FROM users WHERE email = ?", (client_email,)).fetchone()
        settings_row = conn.execute("SELECT * FROM settings WHERE email = ?", (client_email,)).fetchone()
        if not user_row or not settings_row:
            conn.close()
            print("[ERROR] Missing user/settings data.")
            return None

        base_id      = user_row["public_id"]
        first_name   = settings_row["first_name"] or "Your Name"
        position     = settings_row["position"] or ""
        company_name = settings_row["company_name"] or "Your Company"
        website      = settings_row["website"] or "example.com"
        reply_to     = settings_row["reply_to"] or "contact@example.com"
        phone        = settings_row["phone"] or "123-456-7890"

        # ✅ Generate unique public_id for this proposal
        public_id = f"{base_id}-{str(uuid.uuid4())[:8]}"

        # ✅ Build OpenAI prompt
        prompt = (
            f"Write a {length} business proposal in a {tone} tone.\n"
            f"Client: {first_name} ({position}) from {company_name}.\n"
            f"Website: {website}, Contact: {reply_to} / {phone}.\n"
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

        # ✅ Save to database
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
            public_id,
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

        # ✅ Create a QR code
        generate_qr_code(public_id, base_url="https://zyberfy.com/")

        # ✅ Log + send email
        log_event("generated_proposal", user_email=client_email, metadata={"public_id": public_id})
        send_proposal_email(
            to_email=email,
            subject="Your Proposal Has Been Received",
            content=proposal_text,
            cc_client=True,
            client_email=client_email
        )

        return public_id

    except Exception as e:
        print(f"[ERROR] Failed to handle proposal: {e}")
        return None
