import os
import discord
import requests
from flask import Flask
from threading import Thread

# إعداد سيرفر الـ Flask الداخلي لإبقاء البوت مستيقظاً
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# تشغيل السيرفر الوهمي في الخلفية
keep_alive()

# إعدادات بوت الديسكورد
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'Bot is online and ready as {client.user}')

# قراءة التوكن من متغيرات البيئة التي أضفناها في Render
TOKEN = os.getenv('TOKEN')

if TOKEN:
    client.run(TOKEN)
else:
    print("Error: TOKEN environment variable not found!")
