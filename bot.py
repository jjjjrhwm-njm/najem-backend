import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread, Lock 

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json" 

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock() 

def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): 
            return {"users": {}, "app_subscriptions": {}, "vouchers": {}}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {"users": {}, "app_subscriptions": {}} 

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4) 

# --- [ واجهة فحص التطبيق - API ] ---
@app.route('/check')
def check_status():
    aid = request.args.get('aid') # معرف الجهاز
    pkg = request.args.get('pkg') # اسم التطبيق (باقة)
    
    if not aid or not pkg: return "EXPIRED"
    
    db = load_db()
    # الوصول للاشتراك بناءً على التطبيق + معرف الجهاز
    app_key = f"{pkg}_{aid}"
    user_data = db.get("app_subscriptions", {}).get(app_key)
    
    if not user_data: return "EXPIRED"
    if user_data.get("banned"): return "BANNED"
    if time.time() > user_data.get("end_time", 0): return "EXPIRED"
    
    return "ACTIVE" 

# --- [ واجهة البوت - Telegram ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    args = m.text.split()
    
    if uid not in db["users"]: db["users"][uid] = {"current_app_key": None}
    
    # معالجة الرابط القادم من التطبيق: start=DEVICEID_PKGNAME
    if len(args) > 1:
        payload = args[1] # ستحتوي على ID_PKG
        if "_" in payload:
            aid, pkg = payload.split("_", 1)
            app_key = f"{pkg}_{aid}"
            
            # تسجيل الدخول أو ربط التطبيق الحالي
            if app_key not in db.get("app_subscriptions", {}):
                if "app_subscriptions" not in db: db["app_subscriptions"] = {}
                db["app_subscriptions"][app_key] = {"end_time": 0, "trial_used": False, "pkg": pkg, "aid": aid}
            
            db["users"][uid]["current_app_key"] = app_key
            save_db(db)
            bot.send_message(m.chat.id, f"✅ **تم التعرف على التطبيق!**\n📦 التطبيق: `{pkg}`\n📱 الجهاز: `{aid}`", parse_mode="Markdown")

    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add("🎁 تجربة مجانية (24س)", "🎫 تفعيل كود")
    menu.add("📊 حالتي", "🛒 شراء اشتراك")
    bot.send_message(m.chat.id, "أهلاً بك يا **نجم الإبداع**. اختر من القائمة:", reply_markup=menu, parse_mode="Markdown") 

# --- [ شراء اشتراك ] --- 
@bot.message_handler(func=lambda m: m.text == "🛒 شراء اشتراك")
def buy_subscription(m):
    db = load_db()
    uid = str(m.from_user.id)
    app_key = db["users"].get(uid, {}).get("current_app_key")
    
    if not app_key:
        return bot.send_message(m.chat.id, "❌ يرجى الدخول من التطبيق المراد تفعيله أولاً.")
    
    bot.send_invoice(
        m.chat.id, 
        title="تفعيل تطبيق برو", 
        description=f"تفعيل لمدة 30 يوم للتطبيق المرتبط حالياً.",
        invoice_payload=f"pay_{app_key}",
        provider_token="", 
        currency="XTR", 
        prices=[types.LabeledPrice(label="اشتراك برو", amount=100)]
    )

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True) 

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db()
    app_key = m.successful_payment.invoice_payload.replace("pay_", "")
    
    current_end = max(time.time(), db["app_subscriptions"].get(app_key, {}).get("end_time", 0))
    db["app_subscriptions"][app_key]["end_time"] = current_end + (30 * 86400)
    save_db(db)
    bot.send_message(m.chat.id, "✅ تم التفعيل بنجاح لهذا التطبيق!")

# --- [ حالتي ] ---
@bot.message_handler(func=lambda m: m.text == "📊 حالتي")
def status(m):
    db = load_db()
    uid = str(m.from_user.id)
    app_key = db["users"].get(uid, {}).get("current_app_key")
    
    if not app_key: return bot.send_message(m.chat.id, "❌ لم يتم ربط أي تطبيق حالياً.")
    
    info = db["app_subscriptions"].get(app_key, {})
    pkg = info.get("pkg", "غير معروف")
    rem = max(0, int((info.get("end_time", 0) - time.time()) / 3600))
    bot.send_message(m.chat.id, f"📦 التطبيق: `{pkg}`\n⏳ المتبقي: {rem} ساعة.", parse_mode="Markdown")

# --- [ تجربة مجانية ] ---
@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية (24س)")
def trial(m):
    db = load_db()
    app_key = db["users"].get(str(m.from_user.id), {}).get("current_app_key")
    
    if not app_key: return bot.send_message(m.chat.id, "❌ ادخل من التطبيق أولاً.")
    
    if db["app_subscriptions"][app_key].get("trial_used"):
        bot.send_message(m.chat.id, "❌ استخدمت التجربة لهذا التطبيق سابقاً.")
    else:
        db["app_subscriptions"][app_key]["trial_used"] = True
        db["app_subscriptions"][app_key]["end_time"] = time.time() + 86400
        save_db(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل 24 ساعة لهذا التطبيق!")

# --- [ لوحة المدير والأكواد ] ---
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎫 كود (30 يوم)", callback_data="gen_30"))
    bot.send_message(m.chat.id, "👑 لوحة المدير:", reply_markup=markup)

@bot.callback_query_handler(func=lambda q: q.data == "gen_30")
def generate(q):
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db = load_db()
    if "vouchers" not in db: db["vouchers"] = {}
    db["vouchers"][code] = 30
    save_db(db)
    bot.edit_message_text(f"🎫 كود جديد:\n`{code}`", q.message.chat.id, q.message.message_id)

@bot.message_handler(func=lambda m: m.text == "🎫 تفعيل كود")
def redeem_start(m):
    msg = bot.send_message(m.chat.id, "أرسل كود التفعيل:")
    bot.register_next_step_handler(msg, redeem_final) 

def redeem_final(m):
    code = m.text.strip()
    db = load_db()
    if code in db.get("vouchers", {}):
        days = db["vouchers"].pop(code)
        app_key = db["users"].get(str(m.from_user.id), {}).get("current_app_key")
        if app_key:
            current = max(time.time(), db["app_subscriptions"][app_key].get("end_time", 0))
            db["app_subscriptions"][app_key]["end_time"] = current + (days * 86400)
            save_db(db)
            bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم لهذا التطبيق!")
        else: bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    else: bot.send_message(m.chat.id, "❌ كود غير صحيح.") 

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.infinity_polling()
