import base64
import json
import os
import random
import string
import discord
from discord import app_commands
import requests

# تم جعل التوكنات تقرأ من إعدادات النظام (Environment Variables) لحمايتها أمنياً
TOKEN = os.environ.get("TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

REPO_OWNER = "kqi5q"
REPO_NAME = "3srh-system-data"
FILE_PATH = "licenses.json"
CHANNEL_ID = 1547705815698382970


class LicenseBot(discord.Client):

    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("Slash commands synced successfully!")

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("Bot is online and ready!")


client = LicenseBot()


def generate_random_code():
    chars = string.ascii_uppercase + string.digits
    part = ''.join(random.choices(chars, k=5))
    return f"3SRH-{part}"


@client.tree.command(name="generate", description="توليد أكواد تفعيل جديدة وإضافتها تلقائياً للسحابة")
@app_commands.describe(count="عدد الأكواد التي تريد توليدها")
async def generate_codes(interaction: discord.Interaction, count: int = 1):
    if count < 1 or count > 20:
        await interaction.response.send_message("❌ يمكنك توليد ما بين 1 إلى 20 كوداً في المرة الواحدة فقط.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True, ephemeral=True)

    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers)

        if r.status_code != 200:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب لجلب ملف الأكواد.", ephemeral=True)
            return

        file_data = r.json()
        sha = file_data["sha"]
        content_decoded = base64.b64decode(file_data["content"]).decode("utf-8")
        db = json.loads(content_decoded)

        if "codes" not in db:
            db["codes"] = {}

        new_generated_codes = []

        for _ in range(count):
            while True:
                code = generate_random_code()
                if code not in db["codes"]:
                    break
            
            db["codes"][code] = {
                "used": False,
                "device": None
            }
            new_generated_codes.append(code)

        new_content = base64.b64encode(json.dumps(db, indent=4).encode("utf-8")).decode("utf-8")
        update_data = {
            "message": f"Generated {count} new license codes via Discord command",
            "content": new_content,
            "sha": sha,
        }
        update_r = requests.put(url, headers=headers, json=update_data)

        if update_r.status_code in [200, 201]:
            codes_list_str = "\n".join([f"`{c}`" for c in new_generated_codes])
            await interaction.followup.send(
                f"✅ **تم توليد وإضافة {count} كود بنجاح إلى السحابة!**\n\nالأكواد الجديدة:\n{codes_list_str}",
                ephemeral=True
            )
        else:
            await interaction.followup.send("❌ فشل حفظ الأكواد الجديدة في غيت هب.", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ غير متوقع: {str(e)}", ephemeral=True)


@client.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id")

        if custom_id.startswith("ban_target_") or custom_id.startswith("unban_target_") or custom_id.startswith("recycle_target_"):
            
            if custom_id.startswith("recycle_target_"):
                action_type = "recycle"
                prefix = "recycle_target_"
            elif custom_id.startswith("unban_target_"):
                action_type = "unban"
                prefix = "unban_target_"
            else:
                action_type = "ban"
                prefix = "ban_target_"

            parts = custom_id.replace(prefix, "").split("_", 1)
            b_code = parts[0]
            b_device = parts[1] if len(parts) > 1 else ""

            await interaction.response.defer(thinking=True, ephemeral=True)

            try:
                url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
                headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
                r = requests.get(url, headers=headers)

                if r.status_code == 200:
                    file_data = r.json()
                    sha = file_data["sha"]
                    content_decoded = base64.b64decode(file_data["content"]).decode("utf-8")
                    db = json.loads(content_decoded)

                    if action_type == "recycle":
                        if b_device and b_device not in db.get("blacklisted_devices", []):
                            db["blacklisted_devices"].append(b_device)
                        
                        if b_code in db.get("codes", {}):
                            db["codes"][b_code]["used"] = False
                            db["codes"][b_code]["device"] = None

                        action_msg = f"♻️ تم حظر الجهاز `{b_device}` واستعادة الكود `{b_code}` بنجاح وأصبح جاهزاً للاستخدام مرة أخرى!"
                        commit_msg = f"Ban device & recycle code: {b_code} / {b_device}"

                    elif action_type == "unban":
                        if b_code in db.get("blacklisted_codes", []):
                            db["blacklisted_codes"].remove(b_code)
                        if b_device in db.get("blacklisted_devices", []):
                            db["blacklisted_devices"].remove(b_device)
                        
                        if b_code in db.get("codes", {}):
                            db["codes"][b_code]["used"] = False
                            db["codes"][b_code]["device"] = None

                        action_msg = f"✅ تم إلغاء الحظر وتصفير الكود `{b_code}` وجهازه بنجاح!"
                        commit_msg = f"Reset & Unban code: {b_code}"

                    else:
                        if b_code not in db.get("blacklisted_codes", []):
                            db["blacklisted_codes"].append(b_code)
                        if b_device and b_device not in db.get("blacklisted_devices", []):
                            db["blacklisted_devices"].append(b_device)
                        
                        action_msg = f"🚫 تم حظر الكود `{b_code}` والجهاز `{b_device}` وإيقافهما نهائياً!"
                        commit_msg = f"Ban code/device: {b_code} / {b_device}"

                    new_content = base64.b64encode(json.dumps(db, indent=4).encode("utf-8")).decode("utf-8")
                    update_data = {
                        "message": commit_msg,
                        "content": new_content,
                        "sha": sha,
                    }
                    update_r = requests.put(url, headers=headers, json=update_data)

                    if update_r.status_code in [200, 201]:
                        await interaction.followup.send(action_msg, ephemeral=True)
                    else:
                        await interaction.followup.send("❌ فشل التحديث على غيت هب.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)


client.run(TOKEN)
