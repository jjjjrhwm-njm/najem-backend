import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread, Lock

# --- [ الإعدادات ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock()

def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): return {"users": {}, "app_links": {}, "vouchers": {}}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {"users": {}, "app_links": {}, "vouchers": {}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4)

# --- [ واجهة فحص التطبيق - API ] ---
@app.route('/check')
def check_status():
    aid = request.args.get('aid')
    pkg = request.args.get('pkg')
    db = load_db()
    key = f"{aid}_{pkg}"
    user_data = db["app_links"].get(key)
    if not user_data or time.time() > user_data.get("end_time", 0): return "EXPIRED"
    if user_data.get("banned"): return "BANNED"
    return "ACTIVE"

# --- [ واجهة البوت - التسجيل التلقائي ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    args = m.text.split()
    
    # التحقق من وجود بيانات قادمة من التطبيق (Deep Link)
    if len(args) > 1:
        payload = args[1] # ستحتوي على ID_PKG
        try:
            aid, pkg = payload.split('_')
            key = f"{aid}_{pkg}"
            # تسجيل أو تحديث الربط تلقائياً
            db["app_links"][key] = db["app_links"].get(key, {"end_time": 0, "banned": False, "trial_used": False, "telegram_id": uid, "pkg": pkg})
            db["app_links"][key]["telegram_id"] = uid
            if uid not in db["users"]: db["users"][uid] = {}
            db["users"][uid]["last_key"] = key
            save_db(db)
            bot.send_message(m.chat.id, f"✅ **تم التعرف على جهازك تلقائياً!**\n📦 التطبيق: `{pkg}`\n🆔 المعرف: `{aid}`", parse_mode="Markdown")
        except:
            bot.send_message(m.chat.id, "⚠️ حدث خطأ في معالجة بيانات التطبيق.")
    else:
        bot.send_message(m.chat.id, "أهلاً بك. يرجى الدخول من التطبيق ليتم التعرف على جهازك.")

    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add("🎁 تجربة مجانية (24س)", "🎫 تفعيل كود")
    menu.add("📊 حالتي", "🛒 شراء اشتراك (100⭐️)")
    bot.send_message(m.chat.id, "اختر من القائمة أدناه:", reply_markup=menu)

# --- [ وظائف المستخدم والمدير (نفس المنطق السابق) ] ---
@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية (24س)")
def trial(m):
    db = load_db()
    uid = str(m.from_user.id)
    key = db["users"].get(uid, {}).get("last_key")
    if not key: return bot.send_message(m.chat.id, "❌ لم يتم ربط تطبيقك.")
    if db["app_links"][key].get("trial_used"):
        bot.send_message(m.chat.id, "❌ استخدمت التجربة سابقاً.")
    else:
        db["app_links"][key]["trial_used"] = True
        db["app_links"][key]["end_time"] = time.time() + 86400
        save_db(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل 24 ساعة! اعد فحص الحالة في التطبيق.")

def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
