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
        print("Bot is online and ready!")


client = LicenseBot()


def generate_random_code():
    chars = string.ascii_uppercase + string.digits
    part = ''.join(random.choices(chars, k=5))
    return f"3SRH-{part}"


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
    update_data = {
        "message": commit_message,
        "content": new_content,
        "sha": sha,
    }
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
        if not db:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
            return

        if "codes" not in db:
            db["codes"] = {}

        for code in self.generated_codes:
            db["codes"][code] = {"used": False, "device": None}

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


# 1. قائمة خيارات إدارة الأكواد الفرعية
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

    @discord.ui.button(label="🔴 المستخدمة", style=discord.ButtonStyle.secondary, custom_id="sub_codes_used", row=0)
    async def used_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = fetch_db()
        if not db:
            await interaction.followup.send("❌ خطأ.", ephemeral=True)
            return
        used_list = [f"`{c}` (الجهاز: {info.get('device')})" for c, info in db.get("codes", {}).items() if info.get("used")]
        if not used_list:
            await interaction.followup.send("🔴 لا توجد أكواد مستخدمة حالياً.", ephemeral=True)
            return
        text_out = "\n".join(used_list[:25])
        await interaction.followup.send(f"🔴 **الأكواد المستخدمة حالياً:**\n{text_out}", ephemeral=True)

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
        await interaction.followup.send("🚫 **الأكواد المحظورة (اختر لفك الحظر أو الحذف النهائي):**", view=view, ephemeral=True)

    @discord.ui.button(label="⚡ توليد كود سريع", style=discord.ButtonStyle.primary, custom_id="sub_codes_gen", row=1)
    async def gen_quick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db:
            await interaction.followup.send("❌ فشل.", ephemeral=True)
            return
        if "codes" not in db:
            db["codes"] = {}
        new_code = generate_random_code()
        db["codes"][new_code] = {"used": False, "device": None}
        if save_db(db, sha, url, headers, f"Quick generated code {new_code}"):
            await interaction.followup.send(f"✨ **تم توليد وحفظ كود جديد بنجاح!**\n🔑 الكود: `{new_code}`", ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل حفظ الكود.", ephemeral=True)


# 2. إدارة الأكواد غير المستخدمة (المتاحة) مع خيارات الحذف
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
        await interaction.followup.send("❌ الكود غير موجود أو تم حذفه مسبقاً.", ephemeral=True)


# 3. إدارة الأكواد المحظورة (فك الحظر أو الحذف النهائي)
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
        if not db:
            await interaction.followup.send("❌ خطأ.", ephemeral=True)
            return
        if self.code in db.get("blacklisted_codes", []):
            db["blacklisted_codes"].remove(self.code)
        if self.code in db.get("codes", {}):
            db["codes"][self.code]["used"] = False
            db["codes"][self.code]["device"] = None
        if save_db(db, sha, url, headers, f"Unban code {self.code}"):
            await interaction.followup.send(f"✅ تم فك الحظر عن الكود `{self.code}` وإرجاعه متاحاً!", ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل الحفظ.", ephemeral=True)

    @discord.ui.button(label="🗑️ حذف نهائي", style=discord.ButtonStyle.danger, custom_id="b_opt_delete")
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db:
            await interaction.followup.send("❌ خطأ.", ephemeral=True)
            return
        if self.code in db.get("blacklisted_codes", []):
            db["blacklisted_codes"].remove(self.code)
        if self.code in db.get("codes", {}):
            del db["codes"][self.code]
        if save_db(db, sha, url, headers, f"Permanently delete blacklisted code {self.code}"):
            await interaction.followup.send(f"🗑️ تم حذف الكود المحظور `{self.code}` نهائياً من السحابة!", ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل الحفظ.", ephemeral=True)


# 4. قائمة خيارات إدارة الأجهزة الفرعية
class DevicesSubMenuView(discord.ui.View):
    def __init__(self, devices_list):
        super().__init__(timeout=180)
        for code, device in devices_list[:25]:
            self.add_item(DeviceManageButton(code, device))

class DeviceManageButton(discord.ui.Button):
    def __init__(self, code, device):
        super().__init__(label=f"💻 {device[:10]} ({code})", style=discord.ButtonStyle.secondary, custom_id=f"man_dev_{code}")
        self.code = code
        self.device = device

    async def callback(self, interaction: discord.Interaction):
        view = DeviceActionsView(self.code, self.device)
        await interaction.response.send_message(
            f"⚙️ **خيارات التحكم بالجهاز:**\n💻 اسم الجهاز: `{self.device}`\n🔑 الكود: `{self.code}`", 
            view=view, 
            ephemeral=True
        )

class DeviceActionsView(discord.ui.View):
    def __init__(self, code, device):
        super().__init__(timeout=60)
        self.code = code
        self.device = device

    @discord.ui.button(label="🚫 حظر الجهاز والكود", style=discord.ButtonStyle.danger, custom_id="dev_act_ban")
    async def ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "blacklisted_codes" not in db:
                db["blacklisted_codes"] = []
            if "blacklisted_devices" not in db:
                db["blacklisted_devices"] = []
            if self.code not in db["blacklisted_codes"]:
                db["blacklisted_codes"].append(self.code)
            if self.device not in db["blacklisted_devices"]:
                db["blacklisted_devices"].append(self.device)
            
            db["codes"][self.code]["used"] = False
            db["codes"][self.code]["device"] = None

            if save_db(db, sha, url, headers, f"Ban device {self.device} and code {self.code}"):
                await interaction.followup.send(f"🚫 تم حظر الجهاز `{self.device}` والكود `{self.code}` بنجاح!", ephemeral=True)
                return
        await interaction.followup.send("❌ فشل الحظر.", ephemeral=True)

    @discord.ui.button(label="🔓 فك الحظر عن الجهاز", style=discord.ButtonStyle.success, custom_id="dev_act_unban")
    async def unban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if self.device in db.get("blacklisted_devices", []):
                db["blacklisted_devices"].remove(self.device)
            if self.code in db.get("blacklisted_codes", []):
                db["blacklisted_codes"].remove(self.code)
            
            if save_db(db, sha, url, headers, f"Unban device {self.device}"):
                await interaction.followup.send(f"✅ تم فك الحظر عن الجهاز `{self.device}` بنجاح!", ephemeral=True)
                return
        await interaction.followup.send("❌ فشل فك الحظر.", ephemeral=True)

    @discord.ui.button(label="👢 طرد الجهاز (بدون حظر)", style=discord.ButtonStyle.primary, custom_id="dev_act_kick")
    async def kick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "targeted_kick_messages" not in db:
                db["targeted_kick_messages"] = {}
            db["targeted_kick_messages"][self.code] = {"msg": "تم طردك من المالك", "id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Soft kick device {self.device}"):
                await interaction.followup.send(f"👢 تم إرسال أمر الطرد وإغلاق الأداة للجهاز `{self.device}` مع إبقاء كوده سارياً!", ephemeral=True)
                return
        await interaction.followup.send("❌ فشل الطرد.", ephemeral=True)


# 5. واجهة لوحة التحكم الرئيسية
class MainDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔑 إدارة الأكواد", style=discord.ButtonStyle.primary, custom_id="dash_main_codes", row=0)
    async def codes_menu_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CodesSubMenuView()
        await interaction.response.send_message("📁 **قائمة إدارة الأكواد:** اختر القسم المطلوب:", view=view, ephemeral=True)

    @discord.ui.button(label="💻 إدارة الأجهزة", style=discord.ButtonStyle.secondary, custom_id="dash_main_devices", row=0)
    async def devices_menu_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = fetch_db()
        if not db:
            await interaction.followup.send("❌ فشل الاتصال بقاعدة البيانات.", ephemeral=True)
            return

        codes = db.get("codes", {})
        devices_list = []
        for code, info in codes.items():
            if info.get("used") and info.get("device"):
                devices_list.append((code, info.get("device")))

        if not devices_list:
            await interaction.followup.send("🟢 لا توجد أي أجهزة متصلة أو مفعلة حالياً.", ephemeral=True)
            return

        view = DevicesSubMenuView(devices_list)
        await interaction.followup.send("⚙️ **اختر الجهاز المطلوب لإدارته (حظر، فك حظر، أو طرد):**", view=view, ephemeral=True)

    @discord.ui.button(label="🚨 تبديل الصيانة", style=discord.ButtonStyle.danger, custom_id="dash_maint", row=1)
    async def maint_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db:
            await interaction.followup.send("❌ خطأ.", ephemeral=True)
            return
        if "settings" not in db:
            db["settings"] = {}
        current_status = db["settings"].get("maintenance", False)
        new_status = not current_status
        db["settings"]["maintenance"] = new_status
        msg = f"🚨 تم **تفعيل** وضع الصيانة العام!" if new_status else "🟢 تم **إيقاف** وضع الصيانة وعودة النظام للعمل!"
        if save_db(db, sha, url, headers, f"Toggle maintenance via dashboard to {new_status}"):
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل حفظ حالة الصيانة.", ephemeral=True)

    @discord.ui.button(label="📦 نسخة احتياطية", style=discord.ButtonStyle.secondary, custom_id="dash_export", row=1)
    async def export_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = fetch_db()
        if not db:
            await interaction.followup.send("❌ فشل.", ephemeral=True)
            return
        file_content = json.dumps(db, indent=4).encode("utf-8")
        file_path_temp = "licenses_backup.json"
        with open(file_path_temp, "wb") as f:
            f.write(file_content)
        try:
            await interaction.user.send("📦 **نسخة احتياطية مباشرة من لوحة التحكم:**", file=discord.File(file_path_temp))
            await interaction.followup.send("✅ تم إرسال النسخة الاحتياطية لخاصك (DM) بنجاح!", ephemeral=True)
        except Exception:
            await interaction.followup.send("❌ تعذر الإرسال، تأكد من فتح الرسائل الخاصة في السيرفر.", ephemeral=True)
        if os.path.exists(file_path_temp):
            os.remove(file_path_temp)


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
    if not db:
        await interaction.followup.send("❌ خطأ بالاتصال.", ephemeral=True)
        return
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
    if not db or "codes" not in db:
        await interaction.followup.send("❌ خطأ.", ephemeral=True)
        return
    old_count = len(db["codes"])
    db["codes"] = {c: info for c, info in db["codes"].items() if not info.get("used", False)}
    removed = old_count - len(db["codes"])
    if save_db(db, sha, url, headers, f"Cleared {removed} used codes"):
        await interaction.followup.send(f"🧹 تم حذف `{removed}` كود مستخدم!", ephemeral=True)
    else:
        await interaction.followup.send("❌ فشل التحديث.", ephemeral=True)


@client.tree.command(name="check", description="التحقق من حالة كود معين")
@app_commands.describe(code="الكود المراد فحصه")
async def check_code(interaction: discord.Interaction, code: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db or code.upper() not in db.get("codes", {}):
        await interaction.followup.send(f"❌ الكود غير موجود.", ephemeral=True)
        return
    info = db["codes"][code.upper()]
    status = "مستخدم 🔴" if info.get("used") else "متاح 🟢"
    await interaction.followup.send(f"🔍 **الكود `{code.upper()}`:**\n📌 الحالة: {status}\n💻 الجهاز: `{info.get('device') or 'لا يوجد'}`", ephemeral=True)


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
    else:
        await interaction.followup.send("❌ فشل الحفظ.", ephemeral=True)


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
    if save_db(db, sha, url, headers, f"Reset code: {code}"):
        await interaction.followup.send(f"🔄 تم تصفير الكود `{code}` وأصبح متاحاً!", ephemeral=True)
    else:
        await interaction.followup.send("❌ فشل الحفظ.", ephemeral=True)


@client.tree.command(name="blacklisted", description="عرض الأكواد والأجهزة المحظورة")
async def blacklisted_list(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db:
        await interaction.followup.send("❌ خطأ بالاتصال.", ephemeral=True)
        return
    b_codes = db.get("blacklisted_codes", [])
    if not b_codes:
        await interaction.followup.send("🟢 لا توجد أكواد محظورة حالياً.", ephemeral=True)
        return
    view = BlacklistManagementView(b_codes)
    await interaction.followup.send("🚫 **الأكواد المحظورة (اختر لفك الحظر أو الحذف):**", view=view, ephemeral=True)


@client.tree.command(name="unban", description="إزالة الحظر عن جهاز معين")
@app_commands.describe(device="اسم أو رقم الجهاز لفك الحظر عنه")
async def unban_device(interaction: discord.Interaction, device: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db:
        await interaction.followup.send("❌ خطأ.", ephemeral=True)
        return
    b_devices = db.get("blacklisted_devices", [])
    matched = next((d for d in b_devices if device.lower() == d.lower()), None)
    if not matched:
        await interaction.followup.send(f"❌ الجهاز غير محظور.", ephemeral=True)
        return
    b_devices.remove(matched)
    if save_db(db, sha, url, headers, f"Unban device: {matched}"):
        await interaction.followup.send(f"✅ تم فك الحظر عن الجهاز: `{matched}`", ephemeral=True)
    else:
        await interaction.followup.send("❌ فشل الحفظ.", ephemeral=True)


@client.tree.command(name="message", description="إرسال رسالة لجهاز معين أو لكل الأجهزة دفعة واحدة")
@app_commands.describe(
    target_type="اختر الهدف: device (جهاز معين) أو all (كل الأجهزة)",
    message="الرسالة التي ستظهر في نافذة العميل",
    device_name="اسم الجهاز المستهدف (مطلوب فقط إذا اخترت device)"
)
@app_commands.choices(target_type=[
    app_commands.Choice(name="جهاز معين (Device)", value="device"),
    app_commands.Choice(name="كل الأجهزة (All)", value="all")
])
async def send_message_cmd(interaction: discord.Interaction, target_type: app_commands.Choice[str], message: str, device_name: str = None):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db:
        await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
        return

    unique_id = str(int(time.time()))

    if target_type.value == "all":
        if "broadcasts" not in db:
            db["broadcasts"] = {}
        db["broadcasts"] = {
            "msg": message,
            "id": unique_id
        }
        commit_msg = f"Broadcast message to all devices: {message}"
        response_text = f"📢 **تم إرسال الرسالة بنجاح إلى جميع الأجهزة المتصلة!**\n💬 الرسالة: `{message}`"
    else:
        if not device_name:
            await interaction.followup.send("❌ يجب تحديد اسم الجهاز المستهدف!", ephemeral=True)
            return

        if "targeted_messages" not in db:
            db["targeted_messages"] = {}
        
        db["targeted_messages"][device_name.strip()] = {
            "msg": message,
            "id": unique_id
        }
        commit_msg = f"Send message to device {device_name}: {message}"
        response_text = f"📨 **تم إرسال الرسالة بنجاح!**\n💻 الجهاز: `{device_name.strip()}`\n💬 الرسالة: `{message}`"

    if save_db(db, sha, url, headers, commit_msg):
        await interaction.followup.send(response_text, ephemeral=True)
    else:
        await interaction.followup.send("❌ فشل حفظ الرسالة في السحابة.", ephemeral=True)


@client.tree.command(name="maintenance", description="تشغيل أو إيقاف وضع الصيانة العام على جميع الأجهزة")
@app_commands.describe(status="اختر الحالة: on (تشغيل الصيانة) أو off (إيقاف الصيانة)", reason="سبب الصيانة")
@app_commands.choices(status=[
    app_commands.Choice(name="تشغيل الصيانة (On)", value="on"),
    app_commands.Choice(name="إيقاف الصيانة (Off)", value="off")
])
async def maintenance_mode(interaction: discord.Interaction, status: app_commands.Choice[str], reason: str = "النظام تحت الصيانة الدورية"):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db:
        await interaction.followup.send("❌ فشل الاتصال.", ephemeral=True)
        return

    if "settings" not in db:
        db["settings"] = {}

    is_maint = (status.value == "on")
    db["settings"]["maintenance"] = is_maint
    db["settings"]["maintenance_reason"] = reason

    action_text = f"🚨 **تم تفعيل وضع الصيانة العام!** السبب: {reason}" if is_maint else "🟢 **تم إيقاف وضع الصيانة وعودة النظام للعمل!**"

    if save_db(db, sha, url, headers, f"Set maintenance mode to {status.value}"):
        await interaction.followup.send(action_text, ephemeral=True)
    else:
        await interaction.followup.send("❌ فشل التحديث في السحابة.", ephemeral=True)


@client.tree.command(name="export", description="سحب نسخة احتياطية من قاعدة البيانات وإرسالها على الخاص")
async def export_database(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db:
        await interaction.followup.send("❌ فشل جلب البيانات.", ephemeral=True)
        return

    file_content = json.dumps(db, indent=4).encode("utf-8")
    file_path_temp = "licenses_backup.json"
    
    with open(file_path_temp, "wb") as f:
        f.write(file_content)

    try:
        await interaction.user.send("📦 **هذه نسخة احتياطية حديثة من قاعدة بيانات الأداة:**", file=discord.File(file_path_temp))
        await interaction.followup.send("✅ تم إرسال النسخة الاحتياطية إلى رسائلك الخاصة (DM) بنجاح!", ephemeral=True)
    except Exception:
        await interaction.followup.send("❌ تعذر إرسال رسالة خاصة لك، تأكد من فتح الخاص في السيرفر.", ephemeral=True)
    
    if os.path.exists(file_path_temp):
        os.remove(file_path_temp)


@client.tree.command(name="clearlogs", description="مسح رسائل إشعارات البوت في القناة الحالية")
@app_commands.describe(limit="عدد الرسائل المراد مسحها (افتراضي 50)")
async def clear_logs(interaction: discord.Interaction, limit: int = 50):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        deleted = await interaction.channel.purge(limit=limit)
        await interaction.followup.send(f"🧹 تم حذف `{len(deleted)}` رسالة من إشعارات السجل بنجاح!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ أثناء مسح الرسائل: {e}", ephemeral=True)


@client.tree.command(name="statsgui", description="لوحة معلومات وإحصائيات تفاعلية مع أزرار الإدارة الشاملة")
async def stats_gui_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db:
        await interaction.followup.send("❌ خطأ.", ephemeral=True)
        return
    
    codes = db.get("codes", {})
    total = len(codes)
    used = sum(1 for c in codes.values() if c.get("used"))
    available = total - used
    blacklisted_c = len(db.get("blacklisted_codes", []))
    blacklisted_d = len(db.get("blacklisted_devices", []))
    maint_status = "🚨 مفعل (الصيانة نشطة)" if db.get("settings", {}).get("maintenance") else "🟢 معطل (النظام يعمل طبيعي)"

    embed = discord.Embed(
        title="📊 لوحة التحكم وإحصائيات نظام 3SRH الشاملة",
        description="اختر القسم المطلوبة من الأزرار أدناه (إدارة الأكواد أو إدارة الأجهزة):",
        color=0xA871FF
    )
    embed.add_field(name="📌 إجمالي الأكواد", value=f"`{total}`", inline=True)
    embed.add_field(name="🟢 الأكواد المتاحة", value=f"`{available}`", inline=True)
    embed.add_field(name="🔴 الأكواد المستخدمة", value=f"`{used}`", inline=True)
    embed.add_field(name="🚫 الأكواد المحظورة", value=f"`{blacklisted_c}`", inline=True)
    embed.add_field(name="💻 الأجهزة المحظورة", value=f"`{blacklisted_d}`", inline=True)
    embed.add_field(name="⚙️ حالة الصيانة العامة", value=maint_status, inline=False)
    embed.set_footer(text="3SRH Secure License Management System")

    view = MainDashboardView()
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)


@client.tree.command(name="sync", description="تحديث ومزامنة الأوامر فوراً")
async def sync_commands(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        await client.tree.sync()
        await interaction.followup.send("✅ **تم مزامنة وتحديث جميع الأوامر بنجاح!**", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ فشل مزامنة الأوامر: {e}", ephemeral=True)


if TOKEN:
    client.run(TOKEN)
else:
    print("Error: TOKEN environment variable not found!")
