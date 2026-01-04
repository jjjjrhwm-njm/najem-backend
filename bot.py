import telebot
from telebot import types
from flask import Flask, request, jsonify
import json, os, time
from threading import Thread, Lock

API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock()

def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE):
            return {"ui_config": {"title": "نجم الإبداع", "msg": "يرجى التفعيل", "btn_text": "دعم", "btn_link": "https://t.me/rashed"}}
        with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)

@app.route('/app_sync')
def app_sync():
    db = load_db()
    return jsonify(db["ui_config"])

@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id == ADMIN_ID:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🖼 تعديل النافذة", callback_data="edit_ui"))
        bot.send_message(m.chat.id, "لوحة التحكم جاهزة:", reply_markup=markup)

@bot.callback_query_handler(func=lambda q: q.data == "edit_ui")
def edit(q):
    msg = bot.send_message(q.message.chat.id, "أرسل: العنوان | الرسالة | نص الزر | الرابط")
    bot.register_next_step_handler(msg, update)

def update(m):
    p = m.text.split("|")
    if len(p) < 4: return bot.send_message(m.chat.id, "خطأ في التنسيق")
    db = load_db()
    db["ui_config"] = {"title": p[0].strip(), "msg": p[1].strip(), "btn_text": p[2].strip(), "btn_link": p[3].strip()}
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4, ensure_ascii=False)
    bot.send_message(m.chat.id, "✅ تم التحديث")

Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
bot.infinity_polling()
