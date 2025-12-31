import telebot, json, time, os
from flask import Flask, request, jsonify
from threading import Thread

# ====== الإعدادات ======
BOT_TOKEN = "PUT_YOUR_TOKEN"
ADMIN_ID = 7650083401
DATA_FILE = "db.json"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ====== قاعدة البيانات ======
def load():
    if not os.path.exists(DATA_FILE):
        return {
            "users": {},
            "banned": [],
            "maintenance": False,
            "broadcast": "",
            "version": "1.0",
            "update_url": ""
        }
    return json.load(open(DATA_FILE))

def save(db):
    json.dump(db, open(DATA_FILE,"w"), indent=2)

# ====== API للتطبيق ======
@app.route("/sync")
def sync():
    uid = request.args.get("uid")
    db = load()

    if uid in db["banned"]:
        return jsonify({"status":"banned"})

    if uid not in db["users"]:
        db["users"][uid] = {
            "sub_until": time.time() + 86400,
            "points": 0
        }
        save(db)

    user = db["users"][uid]

    return jsonify({
        "status":"ok",
        "maintenance": db["maintenance"],
        "broadcast": db["broadcast"],
        "version": db["version"],
        "update_url": db["update_url"],
        "sub_until": user["sub_until"],
        "points": user["points"]
    })

# ====== أوامر البوت ======
@bot.message_handler(commands=["start"])
def start(m):
    if m.from_user.id != ADMIN_ID: return
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📢 بث", "🛠 صيانة")
    kb.add("🚫 حظر", "🎁 هدية اشتراك")
    kb.add("🆙 تحديث")
    bot.send_message(m.chat.id,"👑 لوحة التحكم",reply_markup=kb)

@bot.message_handler(func=lambda m:m.text=="📢 بث")
def bc(m):
    msg = bot.send_message(m.chat.id,"اكتب الرسالة")
    bot.register_next_step_handler(msg,save_bc)

def save_bc(m):
    db=load()
    db["broadcast"]=m.text
    save(db)
    bot.send_message(m.chat.id,"✅ تم")

@bot.message_handler(func=lambda m:m.text=="🛠 صيانة")
def mt(m):
    db=load()
    db["maintenance"]=not db["maintenance"]
    save(db)
    bot.send_message(m.chat.id,"🔁 تم التغيير")

@bot.message_handler(func=lambda m:m.text=="🚫 حظر")
def ban(m):
    msg=bot.send_message(m.chat.id,"أرسل UID")
    bot.register_next_step_handler(msg,do_ban)

def do_ban(m):
    db=load()
    db["banned"].append(m.text)
    save(db)
    bot.send_message(m.chat.id,"🚫 محظور")

@bot.message_handler(func=lambda m:m.text=="🎁 هدية اشتراك")
def gift(m):
    msg=bot.send_message(m.chat.id,"UID + أيام\nمثال:\nABC123 7")
    bot.register_next_step_handler(msg,do_gift)

def do_gift(m):
    uid,days=m.text.split()
    db=load()
    db["users"][uid]["sub_until"]=time.time()+int(days)*86400
    save(db)
    bot.send_message(m.chat.id,"🎉 تم")

@bot.message_handler(func=lambda m:m.text=="🆙 تحديث")
def upd(m):
    msg=bot.send_message(m.chat.id,"version | url")
    bot.register_next_step_handler(msg,do_upd)

def do_upd(m):
    v,u=m.text.split("|")
    db=load()
    db["version"]=v.strip()
    db["update_url"]=u.strip()
    save(db)
    bot.send_message(m.chat.id,"⬆️ جاهز")

# ====== تشغيل ======
def run_api():
    app.run("0.0.0.0",8080)

Thread(target=run_api).start()
bot.infinity_polling()
