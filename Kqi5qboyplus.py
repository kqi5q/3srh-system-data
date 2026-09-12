import os
import base64
import json
import random
import string
import discord
from discord import app_commands
import requests
from flask import Flask
from threading import Thread

# إعداد سيرفر الـ Flask لإبقاء البوت مستيقظاً على Render
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

# قراءة البيانات الحساسة من متغيرات البيئة في Render بأمان تام
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


# ==========================================
# دوال مساعدة لغيت هب (منع التكرار)
# ==========================================
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


# ==========================================
# واجهات الأزرار (Views)
# ==========================================
class ActivationActionView(discord.ui.View):
    def __init__(self, code, device):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="حظر", style=discord.ButtonStyle.danger, custom_id=f"ban_target_{code}_{device}"))
        self.add_item(discord.ui.Button(label="إلغاء وتصفير", style=discord.ButtonStyle.success, custom_id=f"unban_target_{code}_{device}"))
        self.add_item(discord.ui.Button(label="حظر الجهاز واستعادة الكود", style=discord.ButtonStyle.primary, custom_id=f"recycle_target_{code}_{device}"))
        self.add_item(discord.ui.Button(label="طرد العميل", style=discord.ButtonStyle.secondary, custom_id=f"kick_target_{code}_{device}"))


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
            codes_list_str = "\n".join([f"`{c}`" for c in self.generated_codes])
            try:
                await interaction.message.delete()
            except Exception:
                pass
            await interaction.followup.send(f"✅ **تم رفع وحفظ {self.count} كود بنجاح!**\n\n{codes_list_str}", ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل حفظ الأكواد الجديدة في غيت هب.", ephemeral=True)

    @discord.ui.button(label="لا، إلغاء", style=discord.ButtonStyle.red, custom_id="save_codes_no")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.message.delete()
        except Exception:
            pass
        await interaction.response.send_message("❌ تم إلغاء العملية.", ephemeral=True)


class UnusedCodesView(discord.ui.View):
    def __init__(self, codes_list):
        super().__init__(timeout=180)
        self.add_item(DeleteAllUnusedButton())
        for code in codes_list[:24]:
            self.add_item(UnusedDeleteButton(code))

class DeleteAllUnusedButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🗑️ حذف الكل غير المستخدم", style=discord.ButtonStyle.danger, custom_id="del_all_unused", row=0)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
            return

        if "codes" in db:
            old_count = len(db["codes"])
            db["codes"] = {c: info for c, info in db["codes"].items() if info.get("used", False)}
            removed_count = old_count - len(db["codes"])

            if save_db(db, sha, url, headers, f"Deleted all {removed_count} unused codes"):
                try:
                    await interaction.message.delete()
                except Exception:
                    pass
                await interaction.followup.send(f"🗑️ تم بنجاح حذف جميع الأكواد غير المستخدمة (`{removed_count}` كود)!", ephemeral=True)
            else:
                await interaction.followup.send("❌ فشل الحفظ في غيت هب.", ephemeral=True)

class UnusedDeleteButton(discord.ui.Button):
    def __init__(self, code):
        super().__init__(label=f"حذف {code}", style=discord.ButtonStyle.secondary, custom_id=f"del_unused_{code}")
        self.code_to_delete = code

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
            return

        if "codes" in db and self.code_to_delete in db["codes"]:
            del db["codes"][self.code_to_delete]
            if save_db(db, sha, url, headers, f"Delete unused code: {self.code_to_delete}"):
                try:
                    await interaction.message.delete()
                except Exception:
                    pass
                await interaction.followup.send(f"🗑️ تم حذف الكود `{self.code_to_delete}` بنجاح!", ephemeral=True)


# ==========================================
# أوامر البوت (مرتبة ومنظمة بشكل احترافي)
# ==========================================

# 1. قسم إدارة وتوليد الأكواد
@client.tree.command(name="generate", description="توليد أكواد تفعيل جديدة ومراجعتها")
@app_commands.describe(count="عدد الأكواد (من 1 إلى 20)")
async def generate_codes(interaction: discord.Interaction, count: int = 1):
    if count < 1 or count > 20:
        await interaction.response.send_message("❌ يمكنك توليد ما بين 1 إلى 20 كوداً فقط.", ephemeral=True)
        return

    new_codes = [generate_random_code() for _ in range(count)]
    codes_str = "\n".join([f"`{c}`" for c in new_codes])
    await interaction.response.send_message(f"⚠️ **هل تريد حفظ الأكواد التالية ورفعها للسحابة؟**\n\n{codes_str}", view=ConfirmSaveView(new_codes, count), ephemeral=True)


@client.tree.command(name="unused", description="عرض الأكواد غير المستخدمة مع خيارات الحذف")
async def unused_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db:
        await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
        return

    unused_list = [c for c, info in db.get("codes", {}).items() if not info.get("used", False)]
    if not unused_list:
        await interaction.followup.send("🟢 لا توجد أي أكواد غير مستخدمة حالياً.", ephemeral=True)
        return

    codes_str = "\n".join([f"`{c}`" for c in unused_list[:24]])
    note = "\n\n*(عرض حد أقصى 24 كوداً بأزرار الحذف)*" if len(unused_list) > 24 else ""
    await interaction.followup.send(f"🟢 **الأكواد غير المستخدمة:**\n📊 العدد: `{len(unused_list)}`\n\n{codes_str}{note}", view=UnusedCodesView(unused_list), ephemeral=True)


@client.tree.command(name="clearused", description="حذف جميع الأكواد المستخدمة مسبقاً دفعة واحدة")
async def clear_used_codes(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db or "codes" not in db:
        await interaction.followup.send("❌ خطأ بالاتصال أو لا توجد أكواد.", ephemeral=True)
        return

    old_count = len(db["codes"])
    db["codes"] = {c: info for c, info in db["codes"].items() if not info.get("used", False)}
    removed = old_count - len(db["codes"])

    if save_db(db, sha, url, headers, f"Cleared {removed} used codes"):
        await interaction.followup.send(f"🧹 تم حذف `{removed}` كود مستخدم وتطهير السحابة!", ephemeral=True)
    else:
        await interaction.followup.send("❌ فشل التحديث.", ephemeral=True)


# 2. قسم فحص وإدارة الأكواد الفردية
@client.tree.command(name="check", description="التحقق من حالة كود معين")
@app_commands.describe(code="الكود المراد فحصه")
async def check_code(interaction: discord.Interaction, code: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db or code not in db.get("codes", {}):
        await interaction.followup.send(f"❌ الكود `{code}` غير موجود.", ephemeral=True)
        return

    info = db["codes"][code]
    status = "مستخدم 🔴" if info.get("used") else "متاح 🟢"
    await interaction.followup.send(f"🔍 **معلومات الكود `{code}`:**\n📌 الحالة: {status}\n💻 الجهاز: `{info.get('device') or 'لا يوجد'}`", ephemeral=True)


@client.tree.command(name="delete", description="حذف كود معين نهائياً من النظام")
@app_commands.describe(code="الكود المراد حذفه")
async def delete_code(interaction: discord.Interaction, code: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db or code not in db.get("codes", {}):
        await interaction.followup.send(f"❌ الكود `{code}` غير موجود.", ephemeral=True)
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
    if not db or code not in db.get("codes", {}):
        await interaction.followup.send(f"❌ الكود `{code}` غير موجود.", ephemeral=True)
        return

    db["codes"][code]["used"] = False
    db["codes"][code]["device"] = None

    if save_db(db, sha, url, headers, f"Reset code: {code}"):
        await interaction.followup.send(f"🔄 تم تصفير الكود `{code}` وأصبح متاحاً!", ephemeral=True)
    else:
        await interaction.followup.send("❌ فشل الحفظ.", ephemeral=True)


# 3. قسم الأمان والحظر (Blacklist & Unban)
@client.tree.command(name="blacklisted", description="عرض قائمة الأكواد والأجهزة المحظورة")
async def blacklisted_list(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db:
        await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
        return

    b_codes = "\n".join([f"`{c}`" for c in db.get("blacklisted_codes", [])]) or "لا توجد"
    b_devices = "\n".join([f"`{d}`" for d in db.get("blacklisted_devices", [])]) or "لا توجد"
    await interaction.followup.send(f"🚫 **قائمة الحظر:**\n\n📌 **الأكواد:**\n{b_codes}\n\n💻 **الأجهزة:**\n{b_devices}", ephemeral=True)


@client.tree.command(name="unban", description="إزالة الحظر عن جهاز معين")
@app_commands.describe(device="اسم أو رقم الجهاز لفك الحظر عنه")
async def unban_device(interaction: discord.Interaction, device: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db:
        await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
        return

    b_devices = db.get("blacklisted_devices", [])
    matched = next((d for d in b_devices if device.lower() == d.lower()), None)
    if not matched:
        await interaction.followup.send(f"❌ الجهاز `{device}` ليس موجوداً في قائمة المحظورين.", ephemeral=True)
        return

    b_devices.remove(matched)
    if save_db(db, sha, url, headers, f"Unban device: {matched}"):
        await interaction.followup.send(f"✅ تم فك الحظر عن الجهاز: `{matched}`", ephemeral=True)
    else:
        await interaction.followup.send("❌ فشل الحفظ.", ephemeral=True)


# 4. قسم الإحصائيات والأدوات المساعدة
@client.tree.command(name="stats", description="عرض إحصائيات النظام بالكامل")
async def stats_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db:
        await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
        return

    codes = db.get("codes", {})
    total = len(codes)
    used = sum(1 for c in codes.values() if c.get("used"))
    msg = f"📊 **إحصائيات النظام:**\n\n🔹 الإجمالي: `{total}`\n🟢 المتاح: `{total - used}`\n🔴 المستخدم: `{used}`\n🚫 الأكواد المحظورة: `{len(db.get('blacklisted_codes', []))}`\n💻 الأجهزة المحظورة: `{len(db.get('blacklisted_devices', []))}`"
    await interaction.followup.send(msg, ephemeral=True)


@client.tree.command(name="finddevice", description="البحث عن الكود المرتبط بجهاز معين")
@app_commands.describe(device="اسم الجهاز أو جزء منه")
async def find_device(interaction: discord.Interaction, device: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db:
        await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
        return

    found = [f"الكود: `{c}` | الجهاز: `{info.get('device')}`" for c, info in db.get("codes", {}).items() if info.get("device") and device.lower() in info.get("device").lower()]
    if found:
        await interaction.followup.send(f"🔍 **نتائج البحث عن الجهاز `{device}`:**\n\n" + "\n".join(found), ephemeral=True)
    else:
        await interaction.followup.send(f"❌ لم يتم العثور على جهاز بهذا الاسم.", ephemeral=True)


# ==========================================
# معالجة تفاعل الأزرار في الديسكورد
# ==========================================
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
            await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
            return

        if action_type == "kick":
            if "blacklisted_codes" not in db:
                db["blacklisted_codes"] = []
            if b_code not in db["blacklisted_codes"]:
                db["blacklisted_codes"].append(b_code)
            action_msg = f"👢 **تم طرد المستخدم بنجاح!**\n📌 الكود: `{b_code}`\n💻 الجهاز: `{b_device or 'غير معروف'}`"
            commit_msg = f"Kick client: {b_code}"

        elif action_type == "recycle":
            if b_device and b_device not in db.get("blacklisted_devices", []):
                db["blacklisted_devices"].append(b_device)
            if b_code in db.get("codes", {}):
                db["codes"][b_code]["used"] = False
                db["codes"][b_code]["device"] = None
            action_msg = f"♻️ تم حظر الجهاز `{b_device}` واستعادة الكود `{b_code}`!"
            commit_msg = f"Recycle code: {b_code}"

        elif action_type == "unban":
            if b_code in db.get("blacklisted_codes", []):
                db["blacklisted_codes"].remove(b_code)
            if b_device in db.get("blacklisted_devices", []):
                db["blacklisted_devices"].remove(b_device)
            if b_code in db.get("codes", {}):
                db["codes"][b_code]["used"] = False
                db["codes"][b_code]["device"] = None
            action_msg = f"✅ تم تصفير الكود `{b_code}` وإلغاء الحظر!"
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
            action_msg = f"🚫 تم حظر الكود `{b_code}` والجهاز `{b_device}` نهائياً!"
            commit_msg = f"Ban code/device: {b_code}"

        if save_db(db, sha, url, headers, commit_msg):
            await interaction.followup.send(action_msg, ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل التحديث.", ephemeral=True)


if TOKEN:
    client.run(TOKEN)
else:
    print("Error: TOKEN environment variable not found!")
