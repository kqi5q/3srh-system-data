@client.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id")
        if not custom_id:
            return

        prefixes = ["kick_target_", "recycle_target_", "unban_target_", "ban_target_"]
        matched_prefix = next((p for p in prefixes if custom_id.startswith(p)), None)
        if not matched_prefix:
            return

        action_type = matched_prefix.replace("_target_", "")
        parts = custom_id.replace(matched_prefix, "").split("_", 1)
        b_code = parts[0]
        b_device = parts[1] if len(parts) > 1 else ""

        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db:
            await interaction.followup.send("❌ خطأ بالاتصال.", ephemeral=True)
            return

        if action_type == "kick":
            # زر الطرد التفاعلي يرسل رسالة تحذير فقط دون مسح الكود (يبقى الكود شغال)
            if "targeted_kick_messages" not in db:
                db["targeted_kick_messages"] = {}
            db["targeted_kick_messages"][b_code] = "تم طردك من المالك"

            action_msg = f"👢 **تم إرسال رسالة الطرد للعميل!**\n📌 الكود: `{b_code}`\n💻 الجهاز: `{b_device or 'غير معروف'}`\n💬 السبب: `تم طردك من المالك (يبقى الكود شغال)`"
            commit_msg = f"Soft kick via button for code: {b_code}"

        elif action_type == "recycle":
            if b_device and b_device not in db.get("blacklisted_devices", []):
                db["blacklisted_devices"].append(b_device)
            if b_code in db.get("codes", {}):
                db["codes"][b_code]["used"] = False
                db["codes"][b_code]["device"] = None
            action_msg = f"♻️ تم حظر الجهاز واستعادة الكود!"
            commit_msg = f"Recycle code: {b_code}"

        elif action_type == "unban":
            if b_code in db.get("blacklisted_codes", []):
                db["blacklisted_codes"].remove(b_code)
            if b_device in db.get("blacklisted_devices", []):
                db["blacklisted_devices"].remove(b_device)
            if b_code in db.get("codes", {}):
                db["codes"][b_code]["used"] = False
                db["codes"][b_code]["device"] = None
            action_msg = f"✅ تم إلغاء الحظر والتصفير!"
            commit_msg = f"Unban code: {b_code}"

        else:  # ban
            if "blacklisted_codes" not in db:
                db["blacklisted_codes"] = []
            if "blacklisted_devices" not in db:
                db["blacklisted_devices"] = []
            if b_code not in db["blacklisted_codes"]:
                db["blacklisted_codes"].append(b_code)
            if b_device and b_device not in db["blacklisted_devices"]:
                db["blacklisted_devices"].append(b_device)
            action_msg = f"🚫 تم الحظر النهائي!"
            commit_msg = f"Ban code/device: {b_code}"

        if save_db(db, sha, url, headers, commit_msg):
            await interaction.followup.send(action_msg, ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل التحديث.", ephemeral=True)
