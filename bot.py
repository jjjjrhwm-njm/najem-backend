import telebot
from telebot import types
from flask import Flask, request
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
        if not os.path.exists(DATA_FILE): return {"users": {}, "app_links": {}}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {"users": {}, "app_links": {}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4)

@app.route('/check')
def check_status():
    aid = request.args.get('aid')
    db = load_db()
    user_data = db["app_links"].get(aid)
    if not user_data: return "STATUS:EXPIRED"
    if user_data.get("banned"): return "STATUS:BANNED"
    if time.time() > user_data.get("end_time", 0): return "STATUS:EXPIRED"
    return "STATUS:ACTIVE"

@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    args = m.text.split()
    
    # إذا جاء المستخدم من التطبيق برابط مثل t.me/bot?start=a1d306...
    if len(args) > 1:
        aid = args[1]
        db["app_links"][aid] = db["app_links"].get(aid, {"end_time": 0, "banned": False, "trial_used": False})
        db["app_links"][aid]["telegram_id"] = uid
        save_db(db)
        bot.send_message(m.chat.id, f"✅ تم التعرف على جهازك تلقائياً!\nمعرف الجهاز: `{aid}`\nيمكنك الآن طلب التجربة المجانية أو الاشتراك.", parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, "مرحباً بك في بوت نجم الإبداع.\nيرجى الدخول من خلال التطبيق ليتم التعرف على جهازك تلقائياً.")

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية")
def claim_trial(m):
    db = load_db()
    uid = str(m.from_user.id)
    # البحث عن المعرف المربوط بهذا الحساب
    aid = next((k for k, v in db["app_links"].items() if v.get("telegram_id") == uid), None)
    
    if not aid:
        return bot.send_message(m.chat.id, "❌ لم يتم العثور على جهاز مربوط بحسابك. ادخل من التطبيق أولاً.")
    
    if db["app_links"][aid].get("trial_used"):
        bot.send_message(m.chat.id, "❌ استخدمت التجربة سابقاً لهذا الجهاز.")
    else:
        db["app_links"][aid]["trial_used"] = True
        db["app_links"][aid]["end_time"] = time.time() + 86400
        save_db(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل 24 ساعة مجانية لجهازك. افتح التطبيق الآن!")

# --- [ واجهة المدير ] ---
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_pnl(m):
    bot.send_message(m.chat.id, "👑 لوحة المدير.\nأرسل `اهداء المعرف الايام` لإعطاء اشتراك.\nمثال: `اهداء a1d30676ae954041 30`")

@bot.message_handler(func=lambda m: m.text.startswith("اهداء "))
def admin_gift(m):
    if m.from_user.id != ADMIN_ID: return
    try:
        _, aid, days = m.text.split()
        db = load_db()
        if aid in db["app_links"]:
            db["app_links"][aid]["end_time"] = max(time.time(), db["app_links"][aid]["end_time"]) + (int(days) * 86400)
            save_db(db)
            bot.send_message(m.chat.id, f"✅ تم إهداء {days} يوم للمعرف {aid}")
        else: bot.send_message(m.chat.id, "❌ المعرف غير موجود.")
    except: bot.send_message(m.chat.id, "❌ الصيغة: اهداء المعرف الايام")

@app.route('/')
def h(): return "SERVER ONLINE"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
