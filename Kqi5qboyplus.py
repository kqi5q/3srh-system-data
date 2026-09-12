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

# تشغيل سيرفر الـ Flask في الخلفية قبل تشغيل البوت
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


# كلاس الأزرار لحفظ أو إلغاء الأكواد المولدة مع مسح الرسالة القديمة
class ConfirmSaveView(discord.ui.View):
    def __init__(self, generated_codes, count):
        super().__init__(timeout=60)
        self.generated_codes = generated_codes
        self.count = count

    @discord.ui.button(label="نعم، حفظ الأكواد", style=discord.ButtonStyle.green, custom_id="save_codes_yes")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
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
            db = json.loads(base64.b64decode(file_data["content"]).decode("utf-8"))

            if "codes" not in db:
                db["codes"] = {}

            for code in self.generated_codes:
                db["codes"][code] = {
                    "used": False,
                    "device": None
                }

            new_content = base64.b64encode(json.dumps(db, indent=4).encode("utf-8")).decode("utf-8")
            update_data = {
                "message": f"Generated {self.count} new license codes via Discord command",
                "content": new_content,
                "sha": sha,
            }
            update_r = requests.put(url, headers=headers, json=update_data)

            if update_r.status_code in [200, 201]:
                codes_list_str = "\n".join([f"`{c}`" for c in self.generated_codes])
                
                try:
                    await interaction.message.delete()
                except Exception:
                    pass

                await interaction.followup.send(
                    f"✅ **تم رفع وحفظ {self.count} كود بنجاح إلى السحابة!**\n\nالأكواد المضافة:\n{codes_list_str}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("❌ فشل حفظ الأكواد الجديدة في غيت هب.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ غير متوقع: {str(e)}", ephemeral=True)

    @discord.ui.button(label="لا، إلغاء", style=discord.ButtonStyle.red, custom_id="save_codes_no")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.message.delete()
        except Exception:
            pass
        await interaction.response.send_message("❌ تم إلغاء العملية، ولن يتم رفع أو حفظ أي كود للسحابة.", ephemeral=True)


# كلاس لعرض الأكواد غير المستخدمة مع زر حذف الكل وأزرار الحذف الفردية
class UnusedCodesView(discord.ui.View):
    def __init__(self, codes_list):
        super().__init__(timeout=180)
        
        # إضافة زر "حذف الكل" في البداية
        self.add_item(DeleteAllUnusedButton())

        # إضافة زر حذف لكل كود (بحد أقصى 24 كوداً إضافياً ليصبح المجموع 25 زرا كحد أقصى مسموح في ديسكورد)
        for code in codes_list[:24]:
            self.add_item(UnusedDeleteButton(code))

class DeleteAllUnusedButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🗑️ حذف الكل غير المستخدم", style=discord.ButtonStyle.danger, custom_id="del_all_unused", row=0)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
            headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
            r = requests.get(url, headers=headers)
            if r.status_code != 200:
                await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
                return
            file_data = r.json()
            sha = file_data["sha"]
            db = json.loads(base64.b64decode(file_data["content"]).decode("utf-8"))

            if "codes" in db:
                old_count = len(db["codes"])
                db["codes"] = {c: info for c, info in db["codes"].items() if info.get("used", False)}
                removed_count = old_count - len(db["codes"])

                new_content = base64.b64encode(json.dumps(db, indent=4).encode("utf-8")).decode("utf-8")
                update_data = {
                    "message": f"Deleted all {removed_count} unused codes",
                    "content": new_content,
                    "sha": sha,
                }
                update_r = requests.put(url, headers=headers, json=update_data)
                if update_r.status_code in [200, 201]:
                    try:
                        await interaction.message.delete()
                    except Exception:
                        pass
                    await interaction.followup.send(f"🗑️ تم بنجاح حذف جميع الأكواد غير المستخدمة (`{removed_count}` كود) من السحابة!", ephemeral=True)
                else:
                    await interaction.followup.send("❌ فشل الحفظ في غيت هب.", ephemeral=True)
            else:
                await interaction.followup.send("❌ لا توجد قاعدة بيانات للأكواد.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)

class UnusedDeleteButton(discord.ui.Button):
    def __init__(self, code):
        super().__init__(label=f"حذف {code}", style=discord.ButtonStyle.secondary, custom_id=f"del_unused_{code}")
        self.code_to_delete = code

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
            headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
            r = requests.get(url, headers=headers)
            if r.status_code != 200:
                await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
                return
            file_data = r.json()
            sha = file_data["sha"]
            db = json.loads(base64.b64decode(file_data["content"]).decode("utf-8"))

            if "codes" in db and self.code_to_delete in db["codes"]:
                del db["codes"][self.code_to_delete]

                new_content = base64.b64encode(json.dumps(db, indent=4).encode("utf-8")).decode("utf-8")
                update_data = {
                    "message": f"Delete unused code: {self.code_to_delete}",
                    "content": new_content,
                    "sha": sha,
                }
                update_r = requests.put(url, headers=headers, json=update_data)
                if update_r.status_code in [200, 201]:
                    try:
                        await interaction.message.delete()
                    except Exception:
                        pass
                    await interaction.followup.send(f"🗑️ تم حذف الكود `{self.code_to_delete}` بنجاح من السحابة!", ephemeral=True)
                else:
                    await interaction.followup.send("❌ فشل الحفظ في غيت هب.", ephemeral=True)
            else:
                await interaction.followup.send("❌ الكود غير موجود أو تم حذفه مسبقاً.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)


@client.tree.command(name="generate", description="توليد أكواد تفعيل ومراجعتها قبل إضافتها للسحابة")
@app_commands.describe(count="عدد الأكواد التي تريد توليدها")
async def generate_codes(interaction: discord.Interaction, count: int = 1):
    if count < 1 or count > 20:
        await interaction.response.send_message("❌ يمكنك توليد ما بين 1 إلى 20 كوداً في المره الواحدة فقط.", ephemeral=True)
        return

    new_generated_codes = [generate_random_code() for _ in range(count)]
    codes_list_str = "\n".join([f"`{c}`" for c in new_generated_codes])

    view = ConfirmSaveView(new_generated_codes, count)
    await interaction.response.send_message(
        f"⚠️ **تم توليد الأكواد التالية مؤقتاً. هل تريد حفظها ورفعها للسحابة؟**\n\n{codes_list_str}",
        view=view,
        ephemeral=True
    )


@client.tree.command(name="unused", description="عرض الأكواد غير المستخدمة مع زر لحذفها فردياً أو دفعة واحدة")
async def unused_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب لجلب الأكواد.", ephemeral=True)
            return
        db = json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
        codes = db.get("codes", {})
        
        unused_list = [c for c, info in codes.items() if not info.get("used", False)]
        
        if not unused_list:
            await interaction.followup.send("🟢 لا توجد أي أكواد غير مستخدمة حالياً.", ephemeral=True)
            return

        codes_str = "\n".join([f"`{c}`" for c in unused_list[:24]])
        note = "\n\n*(ملاحظة: يُعرض كحد أقصى 24 كوداً مع أزرار الحذف في الرسالة الواحدة)*" if len(unused_list) > 24 else ""
        
        view = UnusedCodesView(unused_list)
        msg = (
            f"🟢 **الأكواد غير المستخدمة المتاحة:**\n"
            f"📊 العدد الإجمالي: `{len(unused_list)}`\n\n"
            f"{codes_str}{note}"
        )
        await interaction.followup.send(msg, view=view, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)


@client.tree.command(name="stats", description="عرض إحصائيات الأكواد والنظام بالكامل")
async def stats_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب لجلب الإحصائيات.", ephemeral=True)
            return
        db = json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
        
        codes = db.get("codes", {})
        total_codes = len(codes)
        used_codes = sum(1 for c in codes.values() if c.get("used"))
        unused_codes = total_codes - used_codes
        b_codes = len(db.get("blacklisted_codes", []))
        b_devices = len(db.get("blacklisted_devices", []))

        msg = (
            f"📊 **إحصائيات نظام 3SRH Manager:**\n\n"
            f"🔹 إجمالي الأكواد: `{total_codes}`\n"
            f"🟢 الأكواد المتاحة: `{unused_codes}`\n"
            f"🔴 الأكواد المستخدمة: `{used_codes}`\n"
            f"🚫 الأكواد المحظورة: `{b_codes}`\n"
            f"💻 الأجهزة المحظورة: `{b_devices}`"
        )
        await interaction.followup.send(msg, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)


@client.tree.command(name="check", description="التحقق من حالة كود معين")
@app_commands.describe(code="الكود المراد فحصه")
async def check_code(interaction: discord.Interaction, code: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
            return
        db = json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
        codes = db.get("codes", {})
        
        if code not in codes:
            await interaction.followup.send(f"❌ الكود `{code}` غير موجود في النظام.", ephemeral=True)
            return

        info = codes[code]
        used = info.get("used", False)
        device = info.get("device")
        status = "مستخدم 🔴" if used else "متاح 🟢"
        
        msg = (
            f"🔍 **معلومات الكود `{code}`:**\n\n"
            f"📌 الحالة: {status}\n"
            f"💻 الجهاز المرتبط: `{device if device else 'لا يوجد'}`"
        )
        await interaction.followup.send(msg, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)


@client.tree.command(name="delete", description="حذف كود معين بشكل نهائي من النظام")
@app_commands.describe(code="الكود المراد حذفه")
async def delete_code(interaction: discord.Interaction, code: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
            return
        file_data = r.json()
        sha = file_data["sha"]
        db = json.loads(base64.b64decode(file_data["content"]).decode("utf-8"))
        
        if "codes" not in db or code not in db["codes"]:
            await interaction.followup.send(f"❌ الكود `{code}` غير موجود أصلاً.", ephemeral=True)
            return

        del db["codes"][code]

        new_content = base64.b64encode(json.dumps(db, indent=4).encode("utf-8")).decode("utf-8")
        update_data = {
            "message": f"Delete code: {code}",
            "content": new_content,
            "sha": sha,
        }
        update_r = requests.put(url, headers=headers, json=update_data)
        if update_r.status_code in [200, 201]:
            await interaction.followup.send(f"🗑️ تم حذف الكود `{code}` نهائياً من السحابة بنجاح!", ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل حفظ التعديل في غيت هب.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)


# كلاس أزرار الاختيار بعد الطرد الفوري
class PostResetActionView(discord.ui.View):
    def __init__(self, code: str):
        super().__init__(timeout=60)
        self.code = code

    @discord.ui.button(label="🔄 الاحتفاظ بالكود (إعادة إتاحته)", style=discord.ButtonStyle.green, custom_id="post_reset_keep")
    async def keep_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
            headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
            r = requests.get(url, headers=headers)
            if r.status_code != 200:
                await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
                return
            file_data = r.json()
            sha = file_data["sha"]
            db = json.loads(base64.b64decode(file_data["content"]).decode("utf-8"))

            if "codes" not in db:
                db["codes"] = {}

            # إعادة إضافة الكود كـ متاح وغير مرتبط بجهاز
            db["codes"][self.code] = {
                "used": False,
                "device": None
            }

            new_content = base64.b64encode(json.dumps(db, indent=4).encode("utf-8")).decode("utf-8")
            update_data = {
                "message": f"Restore and make code available: {self.code}",
                "content": new_content,
                "sha": sha,
            }
            update_r = requests.put(url, headers=headers, json=update_data)
            if update_r.status_code in [200, 201]:
                try:
                    await interaction.message.delete()
                except Exception:
                    pass
                await interaction.followup.send(f"✅ تم إعادة تفعيل الكود `{self.code}` وجعله متاحاً للاستخدام من جديد!", ephemeral=True)
            else:
                await interaction.followup.send("❌ فشل الحفظ في غيت هب.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)

    @discord.ui.button(label="🗑️ إبقاء الكود محذوفاً", style=discord.ButtonStyle.red, custom_id="post_reset_delete")
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            try:
                await interaction.message.delete()
            except Exception:
                pass
            await interaction.followup.send(f"🗑️ تم تأكيد حذف الكود `{self.code}` نهائياً من النظام!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)


@client.tree.command(name="resetdevice", description="طرد العميل من الأداة فوراً ثم سؤالك للاحتفاظ بالكود أو حذفه")
@app_commands.describe(code="الكود المراد إدارته")
async def reset_device(interaction: discord.Interaction, code: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
            return
        file_data = r.json()
        sha = file_data["sha"]
        db = json.loads(base64.b64decode(file_data["content"]).decode("utf-8"))
        
        if "codes" not in db or code not in db["codes"]:
            await interaction.followup.send(f"❌ الكود `{code}` غير موجود في النظام.", ephemeral=True)
            return

        # الطرد الفوري تماماً مثل السكربت الأصلي (حذف الكود لكي تكتشفه الأداة فتنطرد فوراً)
        del db["codes"][code]

        new_content = base64.b64encode(json.dumps(db, indent=4).encode("utf-8")).decode("utf-8")
        update_data = {
            "message": f"Immediate kick/delete for code: {code}",
            "content": new_content,
            "sha": sha,
        }
        update_r = requests.put(url, headers=headers, json=update_data)
        
        if update_r.status_code in [200, 201]:
            view = PostResetActionView(code)
            await interaction.followup.send(
                f"👢 **تم طرد العميل وإلغاء الكود `{code}` فوراً من الأداة!**\n\n"
                f"ماذا تريد أن تفعل بهذا الكود الآن؟",
                view=view,
                ephemeral=True
            )
        else:
            await interaction.followup.send("❌ فشل التحديث في غيت هب.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)


@client.tree.command(name="blacklisted", description="عرض قائمة الأكواد والأجهزة المحظورة")
async def blacklisted_list(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
            return
        db = json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
        
        b_codes = db.get("blacklisted_codes", [])
        b_devices = db.get("blacklisted_devices", [])

        codes_str = "\n".join([f"`{c}`" for c in b_codes]) if b_codes else "لا توجد أكواد محظورة"
        devices_str = "\n".join([f"`{d}`" for d in b_devices]) if b_devices else "لا توجد أجهزة محظورة"

        msg = (
            f"🚫 **قائمة الحظر في النظام:**\n\n"
            f"📌 **الأكواد المحظورة:**\n{codes_str}\n\n"
            f"💻 **الأجهزة المحظورة:**\n{devices_str}"
        )
        await interaction.followup.send(msg, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)


@client.tree.command(name="finddevice", description="البحث عن الكود المرتبط باسم جهاز معين")
@app_commands.describe(device="اسم الجهاز أو جزء منه للبحث")
async def find_device(interaction: discord.Interaction, device: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
            return
        db = json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
        codes = db.get("codes", {})
        
        found = []
        for c, info in codes.items():
            dev_name = info.get("device")
            if dev_name and device.lower() in dev_name.lower():
                found.append(f"الكود: `{c}` | الجهاز: `{dev_name}`")

        if found:
            found_str = "\n".join(found)
            await interaction.followup.send(f"🔍 **نتائج البحث عن الجهاز `{device}`:**\n\n{found_str}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ لم يتم العثور على أي كود مرتبط بجهاز يحتوي على الاسم `{device}`.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)


@client.tree.command(name="clearused", description="حذف جميع الأكواد المستخدمة مسبقاً دفعة واحدة")
async def clear_used_codes(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
            return
        file_data = r.json()
        sha = file_data["sha"]
        db = json.loads(base64.b64decode(file_data["content"]).decode("utf-8"))
        
        if "codes" not in db:
            await interaction.followup.send("❌ لا توجد أكواد في قاعدة البيانات.", ephemeral=True)
            return

        old_count = len(db["codes"])
        db["codes"] = {c: info for c, info in db["codes"].items() if not info.get("used", False)}
        removed_count = old_count - len(db["codes"])

        new_content = base64.b64encode(json.dumps(db, indent=4).encode("utf-8")).decode("utf-8")
        update_data = {
            "message": f"Cleared {removed_count} used codes",
            "content": new_content,
            "sha": sha,
        }
        update_r = requests.put(url, headers=headers, json=update_data)
        if update_r.status_code in [200, 201]:
            await interaction.followup.send(f"🧹 تم بنجاح حذف `{removed_count}` كود مستخدم وتطهير السحابة!", ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل التحديث في غيت هب.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)


@client.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id")

        if custom_id and (custom_id.startswith("ban_target_") or custom_id.startswith("unban_target_") or custom_id.startswith("recycle_target_")):
            
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


if TOKEN:
    client.run(TOKEN)
else:
    print("Error: TOKEN environment variable not found!")
