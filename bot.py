import telebot
from telebot import types
from flask import Flask, request
import json, os, time
from threading import Thread, Lock

API_TOKEN = "8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g"
ADMIN_ID = 7650083401
DATA_FILE = "db.json"

TRIAL_DAYS = 1
REF_DAYS = 3
REF_NEED = 3

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
lock = Lock()

# ---------------- DB ----------------
def load():
    with lock:
        if not os.path.exists(DATA_FILE):
            return {
                "users": {},
                "config": {
                    "maintenance": False,
                    "msg": "مرحباً بك",
                    "ver": "1.0",
                    "url": ""
                }
            }
        return json.load(open(DATA_FILE, "r", encoding="utf-8"))

def save(db):
    with lock:
        json.dump(db, open(DATA_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# ---------------- API ----------------
@app.route("/check")
def check():
    aid = request.args.get("aid")
    if not aid:
        return "ERR:NO_ID"

    db = load()
    u = db["users"].get(aid)
    if not u:
        return "REG:0"

    if u.get("banned"):
        return "BANNED"

    now = time.time()
    if now > u["end"]:
        return "SUB:0"

    c = db["config"]
    return f"SUB:1|MSG:{c['msg']}|VER:{c['ver']}|URL:{c['url']}"

# ---------------- BOT ----------------
@bot.message_handler(commands=["start"])
def start(m):
    aid = str(m.from_user.id)
    db = load()

    if aid not in db["users"]:
        db["users"][aid] = {
            "end": 0,
            "trial": False,
            "ref": 0,
            "banned": False
        }

    save(db)
    bot.send_message(m.chat.id, "اكتب: كود")

@bot.message_handler(func=lambda m: m.text == "كود")
def menu(m):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🎁 تجربة", "🔗 رابط")
    if m.from_user.id == ADMIN_ID:
        kb.add("نجم1")
    bot.send_message(m.chat.id, "اختر:", reply_markup=kb)

# -------- TRIAL --------
@bot.message_handler(func=lambda m: m.text == "🎁 تجربة")
def trial(m):
    db = load()
    u = db["users"][str(m.from_user.id)]

    if u["trial"]:
        bot.send_message(m.chat.id, "❌ استخدمت التجربة")
        return

    u["trial"] = True
    u["end"] = time.time() + (TRIAL_DAYS * 86400)
    save(db)
    bot.send_message(m.chat.id, "✅ تم تفعيل تجربة يوم")

# -------- ADMIN --------
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin(m):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("اهداء")
    bot.send_message(m.chat.id, "لوحة المدير", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "اهداء" and m.from_user.id == ADMIN_ID)
def gift(m):
    msg = bot.send_message(m.chat.id, "ID DAYS")
    bot.register_next_step_handler(msg, gift_do)

def gift_do(m):
    aid, days = m.text.split()
    db = load()
    if aid in db["users"]:
        db["users"][aid]["end"] = max(time.time(), db["users"][aid]["end"]) + int(days)*86400
        save(db)
        bot.send_message(m.chat.id, "✅ تم")
    else:
        bot.send_message(m.chat.id, "❌ غير موجود")

# ---------------- RUN ----------------
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

Thread(target=run_flask, daemon=True).start()
bot.infinity_polling()
