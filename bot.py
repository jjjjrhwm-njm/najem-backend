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
    if not aid or not pkg: return "EXPIRED"
    
    # تحويل النقاط إلى شرطات لتتطابق مع قاعدة البيانات
    pkg_safe = pkg.replace(".", "_")
    unique_id = f"{aid}_{pkg_safe}"
    
    db = load_db()
    user_data = db["app_links"].get(unique_id)
    
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
    
    if uid not in db["users"]: db["users"][uid] = {"current_app": None}
    
    if len(args) > 1:
        # هنا سيستلم البوت البيانات تلقائياً (AID_PKG)
        combined_id = args[1]
        db["app_links"][combined_id] = db["app_links"].get(combined_id, {"end_time": 0, "banned": False, "trial_used": False, "telegram_id": uid})
        db["app_links"][combined_id]["telegram_id"] = uid
        db["users"][uid]["current_app"] = combined_id
        save_db(db)
        
        # استخراج اسم الحزمة الأصلي للعرض (تبديل _ بنقطة للجمال فقط)
        pkg_display = combined_id.split('_', 1)[-1].replace("_", ".") if '_' in combined_id else "Unknown"
        bot.send_message(m.chat.id, f"✅ **تم ربط جهازك بنجاح!**\n📦 التطبيق: `{pkg_display}`", parse_mode="Markdown") 

    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add("🎁 تجربة مجانية (24س)", "🎫 تفعيل كود")
    menu.add("📊 حالتي", "🛒 شراء اشتراك")
    bot.send_message(m.chat.id, f"أهلاً بك يا نجم الإبداع. اختر من القائمة:", reply_markup=menu, parse_mode="Markdown") 

# --- [ وظائف الشراء والحالة - تبقى كما هي لكن تتعامل مع المعرف الجديد ] ---
@bot.message_handler(func=lambda m: m.text == "🛒 شراء اشتراك")
def send_payment_invoice(m):
    db = load_db()
    uid = str(m.from_user.id)
    combined_id = db["users"].get(uid, {}).get("current_app")
    if not combined_id: return bot.send_message(m.chat.id, "❌ ادخل من التطبيق أولاً.")
    
    bot.send_invoice(m.chat.id, title="اشتراك برو", description=f"تفعيل التطبيق: {combined_id}",
        invoice_payload=f"pay_{combined_id}", provider_token="", currency="XTR",
        prices=[types.LabeledPrice(label="اشتراك 30 يوم", amount=100)])

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db()
    combined_id = m.successful_payment.invoice_payload.replace("pay_", "")
    current_end = max(time.time(), db["app_links"].get(combined_id, {}).get("end_time", 0))
    db["app_links"][combined_id]["end_time"] = current_end + (30 * 86400)
    save_db(db)
    bot.send_message(m.chat.id, "✅ تم التفعيل!")

@bot.message_handler(func=lambda m: m.text == "📊 حالتي")
def status(m):
    db = load_db()
    combined_id = db["users"].get(str(m.from_user.id), {}).get("current_app")
    if not combined_id: return bot.send_message(m.chat.id, "❌ لم يتم ربط تطبيق.")
    info = db["app_links"].get(combined_id, {})
    rem = max(0, int((info.get("end_time", 0) - time.time()) / 3600))
    bot.send_message(m.chat.id, f"⏳ المتبقي: {rem} ساعة.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية (24س)")
def trial(m):
    db = load_db()
    combined_id = db["users"].get(str(m.from_user.id), {}).get("current_app")
    if not combined_id: return bot.send_message(m.chat.id, "❌ ادخل من التطبيق أولاً.")
    if db["app_links"][combined_id].get("trial_used"):
        bot.send_message(m.chat.id, "❌ استخدمت التجربة سابقاً.")
    else:
        db["app_links"][combined_id]["trial_used"] = True
        db["app_links"][combined_id]["end_time"] = time.time() + 86400
        save_db(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل 24 ساعة!")

@bot.message_handler(func=lambda m: m.text == "🎫 تفعيل كود")
def redeem_start(m):
    msg = bot.send_message(m.chat.id, "أرسل كود التفعيل:")
    bot.register_next_step_handler(msg, redeem_final)

def redeem_final(m):
    code, db = m.text.strip(), load_db()
    if code in db["vouchers"]:
        days = db["vouchers"].pop(code)
        cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
        if cid:
            db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid]["end_time"]) + (days * 86400)
            save_db(db)
            bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم!")
        else: bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    else: bot.send_message(m.chat.id, "❌ كود خطأ.")

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎫 توليد كود (30 يوم)", callback_data="gen_30"))
    bot.send_message(m.chat.id, "👑 لوحة المدير:", reply_markup=markup)

@bot.callback_query_handler(func=lambda q: q.data == "gen_30")
def generate(q):
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db = load_db()
    db["vouchers"][code] = 30
    save_db(db)
    bot.edit_message_text(f"🎫 كود جديد:\n`{code}`", q.message.chat.id, q.message.message_id, parse_mode="Markdown")

def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
