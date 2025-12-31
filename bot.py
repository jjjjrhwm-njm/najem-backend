import telebot
from telebot import types
from flask import Flask, request
import json
import os
import time
from threading import Thread, Lock

# --- [ الإعدادات ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json"
REQUIRED_REFERRALS = 3
REFERRAL_REWARD_DAYS = 3

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock()

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE):
            return {"users": {}, "config": {"maintenance": 0, "announcement": "مرحباً بك", "ver": "1.0", "url": ""}}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"users": {}, "config": {"maintenance": 0, "announcement": "مرحباً بك", "ver": "1.0", "url": ""}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)

# --- [ واجهة الـ API للتطبيق ] ---
@app.route('/check')
def check_status():
    aid = request.args.get('aid')
    db = load_db()
    if not aid or aid not in db["users"]:
        return "ERROR:NOT_FOUND" # التطبيق سيفهم أنه يجب التسجيل
    
    user = db["users"][aid]
    if user.get("banned"): return "STATUS:BANNED"
    
    now = time.time()
    # التحقق من انتهاء الصلاحية
    if now > user["end_time"]:
        status = "FREE"
    else:
        status = user["subscription_type"].upper()
    
    cfg = db["config"]
    # نرسل البيانات كـ نص بسيط ليتم فكها بالسمالي بسهولة
    return f"ST:{status}|MT:{cfg['maintenance']}|VER:{cfg['ver']}"

# --- [ أوامر البوت ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    aid = str(m.from_user.id)
    
    # نظام الإحالة
    args = m.text.split()
    if len(args) > 1 and args[1] != aid:
        ref_id = args[1]
        if aid not in db["users"]:
            if ref_id in db["users"]:
                db["users"][ref_id]["ref_count"] = db["users"][ref_id].get("ref_count", 0) + 1
                if db["users"][ref_id]["ref_count"] >= REQUIRED_REFERRALS:
                    db["users"][ref_id]["end_time"] += (REFERRAL_REWARD_DAYS * 86400)
                    db["users"][ref_id]["ref_count"] = 0
                    bot.send_message(ref_id, "🎁 حصلت على مكافأة لدعوة أصدقائك!")

    if aid not in db["users"]:
        db["users"][aid] = {"subscription_type": "free", "end_time": 0, "trial_used": False, "ref_count": 0, "banned": False}
        save_db(db)
    
    bot.send_message(m.chat.id, "مرحباً بك في لوحة تحكم **نجم الإبداع**\nأرسل كلمة (**كود**) لإدارة اشتراكك.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "كود")
def menu(m):
    db = load_db()
    aid = str(m.from_user.id)
    user = db["users"].get(aid, {})
    rem = max(0, int((user.get("end_time", 0) - time.time()) / 86400))
    
    txt = f"👤 **حسابك:** {aid}\n⭐ **الحالة:** {user.get('subscription_type')}\n📅 **المتبقي:** {rem} يوم"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🎁 تجربة مجانية", "💎 شراء اشتراك")
    markup.add("🔗 رابط الإحالة")
    bot.send_message(m.chat.id, txt, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية")
def trial(m):
    db = load_db()
    aid = str(m.from_user.id)
    user = db["users"].get(aid)
    if user["trial_used"]:
        bot.send_message(m.chat.id, "❌ استخدمت الفترة التجريبية سابقاً.")
    else:
        user["trial_used"] = True
        user["end_time"] = time.time() + 86400
        user["subscription_type"] = "trial"
        save_db(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل 24 ساعة تجريبية.")

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_pnl(m):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🎁 إهداء اشتراك", "🛠 صيانة")
    bot.send_message(m.chat.id, "لوحة المدير:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🎁 إهداء اشتراك" and m.from_user.id == ADMIN_ID)
def gift_init(m):
    msg = bot.send_message(m.chat.id, "أرسل الـ ID ثم عدد الأيام (مثال: 7650083401 30)")
    bot.register_next_step_handler(msg, gift_done)

def gift_done(m):
    try:
        parts = m.text.split()
        target_id, days = parts[0], int(parts[1])
        db = load_db()
        if target_id in db["users"]:
            curr = max(time.time(), db["users"][target_id]["end_time"])
            db["users"][target_id]["end_time"] = curr + (days * 86400)
            db["users"][target_id]["subscription_type"] = "premium"
            save_db(db)
            bot.send_message(m.chat.id, f"✅ تم الإهداء بنجاح لـ {target_id}")
        else: bot.send_message(m.chat.id, "❌ المستخدم لم يسجل في البوت.")
    except: bot.send_message(m.chat.id, "❌ خطأ في الصيغة.")

@app.route('/')
def h(): return "SERVER ONLINE"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
