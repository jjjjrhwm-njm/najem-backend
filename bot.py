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

# --- [ API فحص التطبيق - فحص مستقل لكل حزمة ] ---
@app.route('/check')
def check_status():
    aid = request.args.get('aid')
    pkg = request.args.get('pkg') # استلام اسم الحزمة
    db = load_db()
    
    key = f"{aid}_{pkg}" # مفتاح الربط الفريد
    user_data = db["app_links"].get(key)
    
    if not user_data or time.time() > user_data.get("end_time", 0): return "EXPIRED"
    if user_data.get("banned"): return "BANNED"
    return "ACTIVE"

# --- [ واجهة البوت ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    args = m.text.split()
    
    if uid not in db["users"]: db["users"][uid] = {"last_key": None}
    
    if len(args) > 1:
        try:
            # الرابط يأتي بصيغة: AID_PKG
            aid_pkg = args[1]
            aid, pkg = aid_pkg.split('_')
            key = f"{aid}_{pkg}"
            
            db["app_links"][key] = db["app_links"].get(key, {"end_time": 0, "banned": False, "trial_used": False, "telegram_id": uid, "pkg": pkg})
            db["app_links"][key]["telegram_id"] = uid
            db["users"][uid]["last_key"] = key # حفظ آخر مفتاح تم التعامل معه
            save_db(db)
            bot.send_message(m.chat.id, f"✅ **تم ربط التطبيق بنجاح!**\n📦 التطبيق: `{pkg}`\n🆔 المعرف: `{aid}`", parse_mode="Markdown")
        except: pass

    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add("🎁 تجربة مجانية (24س)", "🎫 تفعيل كود")
    menu.add("📊 حالتي", "🛒 شراء اشتراك (100⭐️)")
    bot.send_message(m.chat.id, "أهلاً بك في بوت **نجم الإبداع**. اختر من القائمة:", reply_markup=menu, parse_mode="Markdown")

# --- [ نظام الشراء بالنجوم - مستقل لكل تطبيق ] ---
@bot.message_handler(func=lambda m: m.text == "🛒 شراء اشتراك (100⭐️)")
def send_invoice(m):
    db = load_db()
    key = db["users"].get(str(m.from_user.id), {}).get("last_key")
    if not key: return bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً عبر الدخول منه.")
    
    pkg = key.split('_')[1]
    bot.send_invoice(
        m.chat.id, title=f"اشتراك شهر - {pkg}", 
        description=f"تفعيل تطبيق {pkg} لمدة 30 يوم.",
        invoice_payload=f"pay_{key}", currency="XTR",
        prices=[types.LabeledPrice(label="اشتراك برو", amount=100)], provider_token=""
    )

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db()
    key = m.successful_payment.invoice_payload.replace("pay_", "")
    current_end = max(time.time(), db["app_links"][key].get("end_time", 0))
    db["app_links"][key]["end_time"] = current_end + (30 * 86400)
    save_db(db)
    bot.send_message(m.chat.id, f"✅ تم التفعيل بنجاح للمفتاح: `{key}`")

@bot.message_handler(func=lambda m: m.text == "📊 حالتي")
def my_status(m):
    db = load_db()
    key = db["users"].get(str(m.from_user.id), {}).get("last_key")
    if not key: return bot.send_message(m.chat.id, "❌ لا يوجد تطبيق مربوط حالياً.")
    status = db["app_links"].get(key, {})
    rem = max(0, int((status.get("end_time", 0) - time.time()) / 3600))
    bot.send_message(m.chat.id, f"📦 الحزمة: `{status.get('pkg')}`\n⏳ المتبقي: {rem} ساعة.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية (24س)")
def free_trial(m):
    db = load_db()
    key = db["users"].get(str(m.from_user.id), {}).get("last_key")
    if not key: return bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    if db["app_links"][key].get("trial_used"):
        bot.send_message(m.chat.id, "❌ استخدمت التجربة سابقاً لهذا التطبيق.")
    else:
        db["app_links"][key]["trial_used"] = True
        db["app_links"][key]["end_time"] = time.time() + 86400
        save_db(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل 24 ساعة لهذا التطبيق.")

def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
