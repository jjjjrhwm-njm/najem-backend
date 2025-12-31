import telebot
from telebot import types
import json, os, time
from flask import Flask, request
from threading import Thread

API_TOKEN = 'PUT_TOKEN'
ADMIN_ID = 7650083401
CHANNEL_ID = "@nejm_njm"
DATA_FILE = "master_control.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# ---------- DB ----------
def get_data():
    if not os.path.exists(DATA_FILE):
        return {
            "banned": [],
            "active": {},
            "config": {
                "mt": "0",
                "bc": "لا يوجد إعلان",
                "ver": "1.0",
                "url": "https://t.me/nejm_njm"
            }
        }
    return json.load(open(DATA_FILE))

def save_data(d):
    json.dump(d, open(DATA_FILE,"w"), indent=2)

# ---------- API ----------
@app.route('/check')
def check():
    aid = request.args.get('aid')
    db = get_data()

    db["active"][aid] = time.time()
    save_data(db)

    if aid in db["banned"]:
        return "BANNED"

    if db["config"]["mt"] == "1":
        return "MAINTENANCE"

    return f"OK|BC:{db['config']['bc']}|VER:{db['config']['ver']}|URL:{db['config']['url']}"

# ---------- BOT ----------
@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id != ADMIN_ID:
        return
    bot.send_message(m.chat.id,
    "👑 لوحة التحكم\n"
    "📊 /stats\n"
    "📢 /bc\n"
    "🛠 /mt\n"
    "🆙 /ver\n"
    "🎁 /gift\n"
    "🚫 /ban\n"
    "✅ /unban")

@bot.message_handler(commands=['stats'])
def stats(m):
    db = get_data()
    online = len([t for t in db["active"].values() if time.time()-t < 60])
    bot.send_message(m.chat.id,f"👥 المتصلين الآن: {online}")

@bot.message_handler(commands=['bc'])
def bc(m):
    msg = bot.send_message(m.chat.id,"أرسل الإذاعة:")
    bot.register_next_step_handler(msg,save_bc)

def save_bc(m):
    db = get_data()
    db["config"]["bc"] = m.text
    save_data(db)
    bot.send_message(m.chat.id,"✅ تم")

@bot.message_handler(commands=['mt'])
def mt(m):
    db = get_data()
    db["config"]["mt"] = "1" if db["config"]["mt"]=="0" else "0"
    save_data(db)
    bot.send_message(m.chat.id,"🛠 تم التبديل")

@bot.message_handler(commands=['ver'])
def ver(m):
    msg = bot.send_message(m.chat.id,"الإصدار الجديد:")
    bot.register_next_step_handler(msg,save_ver)

def save_ver(m):
    db = get_data()
    db["config"]["ver"] = m.text
    save_data(db)
    bot.send_message(m.chat.id,"⬆️ جاهز")

@bot.message_handler(commands=['gift'])
def gift(m):
    msg = bot.send_message(m.chat.id,"AndroidID | Plan:30 أو Plan:1")
    bot.register_next_step_handler(msg,save_gift)

def save_gift(m):
    with open("gift.txt","a") as f:
        f.write(m.text+"\n")
    bot.send_message(m.chat.id,"🎁 أرسل السطر للقناة")

@bot.message_handler(commands=['ban'])
def ban(m):
    msg = bot.send_message(m.chat.id,"AndroidID:")
    bot.register_next_step_handler(msg,save_ban)

def save_ban(m):
    db = get_data()
    db["banned"].append(m.text.strip())
    save_data(db)
    bot.send_message(m.chat.id,"🚫 محظور")

@bot.message_handler(commands=['unban'])
def unban(m):
    msg = bot.send_message(m.chat.id,"AndroidID:")
    bot.register_next_step_handler(msg,save_unban)

def save_unban(m):
    db = get_data()
    db["banned"].remove(m.text.strip())
    save_data(db)
    bot.send_message(m.chat.id,"✅ تم")

# ---------- RUN ----------
def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()
bot.infinity_polling()
