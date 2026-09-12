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
            removed = old_count - len(db["codes"])
            if save_db(db, sha, url, headers, f"Deleted {removed} unused codes"):
                try:
                    await interaction.message.delete()
                except Exception:
                    pass
                await interaction.followup.send(f"🗑️ تم حذف {removed} كود غير مستخدم!", ephemeral=True)

class UnusedDeleteButton(discord.ui.Button):
    def __init__(self, code):
        super().__init__(label=f"حذف {code}", style=discord.ButtonStyle.secondary, custom_id=f"del_unused_{code}")
        self.code_to_delete = code

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db:
            await interaction.followup.send("❌ فشل الاتصال.", ephemeral=True)
            return
        if "codes" in db and self.code_to_delete in db["codes"]:
            del db["codes"][self.code_to_delete]
            if save_db(db, sha, url, headers, f"Delete unused code: {self.code_to_delete}"):
                try:
                    await interaction.message.delete()
                except Exception:
                    pass
                await interaction.followup.send(f"🗑️ تم حذف الكود `{self.code_to_delete}`!", ephemeral=True)


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
    codes_str = "\n".join([f"`{c}`" for c in unused_list[:24]])
    await interaction.followup.send(f"🟢 **الأكواد المتاحة:**\n📊 العدد: `{len(unused_list)}`\n\n{codes_str}", view=UnusedCodesView(unused_list), ephemeral=True)


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
    b_codes = "\n".join([f"`{c}`" for c in db.get("blacklisted_codes", [])]) or "لا توجد"
    b_devices = "\n".join([f"`{d}`" for d in db.get("blacklisted_devices", [])]) or "لا توجد"
    await interaction.followup.send(f"🚫 **قائمة الحظر:**\n\n📌 **الأكواد:**\n{b_codes}\n\n💻 **الأجهزة:**\n{b_devices}", ephemeral=True)


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


@client.tree.command(name="sendmessage", description="إرسال رسالة منبهة لجهاز معين عبر اسمه")
@app_commands.describe(device="اسم الجهاز المستهدف", message="الرسالة التي ستظهر في نافذة العميل")
async def send_message_to_device(interaction: discord.Interaction, device: str, message: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db:
        await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
        return

    if "targeted_messages" not in db:
        db["targeted_messages"] = {}
    
    unique_msg_id = str(int(time.time()))
    db["targeted_messages"][device.strip()] = {
        "msg": message,
        "id": unique_msg_id
    }

    if save_db(db, sha, url, headers, f"Send message to device {device}: {message}"):
        await interaction.followup.send(f"📨 **تم إرسال الرسالة بنجاح!**\n💻 الجهاز: `{device}`\n💬 الرسالة: `{message}`", ephemeral=True)
    else:
        await interaction.followup.send("❌ فشل حفظ الرسالة في السحابة.", ephemeral=True)


@client.tree.command(name="clearlogs", description="مسح رسائل إشعارات البوت في القناة الحالية")
@app_commands.describe(limit="عدد الرسائل المراد مسحها (افتراضي 50)")
async def clear_logs(interaction: discord.Interaction, limit: int = 50):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        deleted = await interaction.channel.purge(limit=limit)
        await interaction.followup.send(f"🧹 تم حذف `{len(deleted)}` رسالة من إشعارات السجل بنجاح!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ أثناء مسح الرسائل: {e}", ephemeral=True)


@client.tree.command(name="kick", description="طرد عميل مع خيار إبقاء الكود أو تسجيل الخروج ومسحه")
@app_commands.describe(
    code="الكود المراد طرده", 
    mode="اختر نوع الطرد: message (رسالة مع إغلاق الأداة وبقاء الكود) أو logout (طرد وتسجيل خروج ومسح الكود)",
    reason="سبب الطرد الذي سيظهر للعميل في الأداة"
)
@app_commands.choices(mode=[
    app_commands.Choice(name="رسالة وإغلاق (يبقى الكود شغال)", value="message"),
    app_commands.Choice(name="تسجيل خروج ومسح الكود (إلغاء التفعيل)", value="logout")
])
async def kick_client_cmd(interaction: discord.Interaction, code: str, mode: app_commands.Choice[str], reason: str = "تم طردك من المالك"):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db:
        await interaction.followup.send("❌ فشل الاتصال.", ephemeral=True)
        return

    code = code.upper()
    if "codes" not in db or code not in db["codes"]:
        await interaction.followup.send(f"❌ الكود `{code}` غير موجود في قاعدة البيانات.", ephemeral=True)
        return

    device_name = db["codes"][code].get("device", "غير معروف")

    if mode.value == "message":
        if "targeted_kick_messages" not in db:
            db["targeted_kick_messages"] = {}
        
        unique_kick_id = str(int(time.time()))
        db["targeted_kick_messages"][code] = {
            "msg": reason,
            "id": unique_kick_id
        }
        
        commit_msg = f"Soft kick code {code} with unique id"
        action_text = "💬 تم إرسال رسالة الطرد للعميل (ستظهر لمرة واحدة فقط وتغلق أداته مع بقاء الكود مفعلاً)"
    else:
        if "blacklisted_codes" not in db:
            db["blacklisted_codes"] = []
        if code not in db["blacklisted_codes"]:
            db["blacklisted_codes"].append(code)

        if "kick_reasons" not in db:
            db["kick_reasons"] = {}
        db["kick_reasons"][code] = reason
        
        db["codes"][code]["used"] = False
        db["codes"][code]["device"] = None
        
        commit_msg = f"Logout and kick code {code}: {reason}"
        action_text = "👢 تم طرد العميل وتسجيل خروجه ومسح كوده بنجاح!"

    if save_db(db, sha, url, headers, commit_msg):
        await interaction.followup.send(
            f"✅ **{action_text}**\n📌 الكود: `{code}`\n💻 الجهاز: `{device_name}`\n💬 السبب: `{reason}`",
            ephemeral=True
        )
    else:
        await interaction.followup.send("❌ فشل التحديث في السحابة.", ephemeral=True)


@client.tree.command(name="wipe", description="حذف بيانات الأداة والترخيص من جهاز العميل عن بعد")
@app_commands.describe(code="الكود المراد حذف ملفات أداته", reason="سبب الحذف")
async def wipe_client_cmd(interaction: discord.Interaction, code: str, reason: str = "تم حذف بيانات الأداة من المالك"):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db:
        await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
        return

    code = code.upper()
    if "codes" not in db or code not in db["codes"]:
        await interaction.followup.send(f"❌ الكود `{code}` غير موجود في قاعدة البيانات.", ephemeral=True)
        return

    device_name = db["codes"][code].get("device", "غير معروف")

    if "remote_wipes" not in db:
        db["remote_wipes"] = {}

    unique_wipe_id = str(int(time.time()))
    db["remote_wipes"][code] = {
        "msg": reason,
        "id": unique_wipe_id
    }

    if save_db(db, sha, url, headers, f"Remote wipe command for code {code}"):
        await interaction.followup.send(
            f"🔥 **تم إرسال أمر الحذف والتدمير لجهاز العميل بنجاح!**\n📌 الكود: `{code}`\n💻 الجهاز: `{device_name}`\n💬 السبب: `{reason}`",
            ephemeral=True
        )
    else:
        await interaction.followup.send("❌ فشل التحديث في السحابة.", ephemeral=True)


@client.tree.command(name="stats", description="إحصائيات النظام بالكامل")
async def stats_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db:
        await interaction.followup.send("❌ خطأ.", ephemeral=True)
        return
    codes = db.get("codes", {})
    total = len(codes)
    used = sum(1 for c in codes.values() if c.get("used"))
    msg = f"📊 **الإحصائيات:**\n\n🔹 الإجمالي: `{total}`\n🟢 المتاح: `{total - used}`\n🔴 المستخدم: `{used}`\n🚫 الأكواد المحظورة: `{len(db.get('blacklisted_codes', []))}`"
    await interaction.followup.send(msg, ephemeral=True)


@client.tree.command(name="finddevice", description="البحث عن الكود المرتبط بجهاز")
@app_commands.describe(device="اسم الجهاز أو جزء منه")
async def find_device(interaction: discord.Interaction, device: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db:
        await interaction.followup.send("❌ خطأ.", ephemeral=True)
        return
    found = [f"الكود: `{c}` | الجهاز: `{info.get('device')}`" for c, info in db.get("codes", {}).items() if info.get("device") and device.lower() in info.get("device").lower()]
    if found:
        await interaction.followup.send(f"🔍 **نتائج البحث:**\n\n" + "\n".join(found), ephemeral=True)
    else:
        await interaction.followup.send(f"❌ لم يتم العثور على الجهاز.", ephemeral=True)


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
        b_code = parts[0].upper()
        b_device = parts[1] if len(parts) > 1 else ""

        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db:
            await interaction.followup.send("❌ خطأ بالاتصال.", ephemeral=True)
            return

        if action_type == "kick":
            if "targeted_kick_messages" not in db:
                db["targeted_kick_messages"] = {}
            
            unique_kick_id = str(int(time.time()))
            db["targeted_kick_messages"][b_code] = {
                "msg": "تم طردك من المالك",
                "id": unique_kick_id
            }

            action_msg = f"👢 **تم إرسال رسالة الطرد وإغلاق الأداة!**\n📌 الكود: `{b_code}`\n💻 الجهاز: `{b_device or 'غير معروف'}`\n💬 السبب: `تم طردك من المالك (الكود يبقى شغالاً)`"
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


if TOKEN:
    client.run(TOKEN)
else:
    print("Error: TOKEN environment variable not found!")
