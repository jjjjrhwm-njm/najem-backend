import telebot # تم التأكد من الحرف الصغير
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
            return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً"}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: 
                db = json.load(f)
                if "global_news" not in db: db["global_news"] = "لا توجد أخبار"
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار"}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4) 

# --- [ واجهة فحص التطبيق والرسائل الإدارية - API ] ---

@app.route('/check')
def check_status():
    aid = request.args.get('aid')
    pkg = request.args.get('pkg') 
    if not aid or not pkg: return "EXPIRED"
    pkg_safe = pkg.replace(".", "_")
    unique_id = f"{aid}_{pkg_safe}"
    db = load_db()
    user_data = db["app_links"].get(unique_id)
    if not user_data: return "EXPIRED"
    if user_data.get("banned"): return "BANNED"
    if time.time() > user_data.get("end_time", 0): return "EXPIRED"
    return "ACTIVE" 

@app.route('/get_news') 
def get_news():
    db = load_db()
    return db.get("global_news", "لا توجد أخبار حالياً")

# --- [ واجهة البوت - Telegram ] ---

@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    args = m.text.split()
    if uid not in db["users"]: db["users"][uid] = {"current_app": None}
    
    if len(args) > 1:
        combined_id = args[1]
        if combined_id not in db["app_links"]:
            db["app_links"][combined_id] = {"end_time": 0, "banned": False, "trial_used": False, "telegram_id": uid}
        db["app_links"][combined_id]["telegram_id"] = uid
        db["users"][uid]["current_app"] = combined_id
        save_db(db)
        pkg_display = combined_id.split('_', 1)[-1].replace("_", ".")
        bot.send_message(m.chat.id, f"✅ **تم ربط جهازك!**\n📦 التطبيق: `{pkg_display}`", parse_mode="Markdown") 

    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add("🎁 تجربة (ساعتين)", "🎫 تفعيل كود")
    menu.add("📊 حالتي", "📱 تطبيقاتي")
    menu.add("🛒 شراء اشتراك")
    bot.send_message(m.chat.id, "أهلاً بك في نظام **NJM**. اختر من القائمة:", reply_markup=menu, parse_mode="Markdown") 

# --- [ نظام الشراء (Stars) ] ---

@bot.message_handler(func=lambda m: m.text == "🛒 شراء اشتراك")
def send_payment(m):
    db = load_db()
    uid = str(m.from_user.id)
    combined_id = db["users"].get(uid, {}).get("current_app")
    if not combined_id: return bot.send_message(m.chat.id, "❌ ادخل من التطبيق أولاً لربط جهازك.")
    
    bot.send_invoice(
        m.chat.id, 
        title="تفعيل اشتراك برو",
        description=f"تفعيل لمدة 30 يوم للتطبيق المرتبط: {combined_id}",
        invoice_payload=f"pay_{combined_id}",
        provider_token="", # فارغ للنجوم
        currency="XTR",
        prices=[types.LabeledPrice(label="اشتراك 30 يوم", amount=100)] # 100 نجمة
    )

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True) 

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db()
    combined_id = m.successful_payment.invoice_payload.replace("pay_", "")
    
    if combined_id not in db["app_links"]:
        db["app_links"][combined_id] = {"end_time": 0, "banned": False, "trial_used": False, "telegram_id": str(m.from_user.id)}
        
    current_end = max(time.time(), db["app_links"][combined_id].get("end_time", 0))
    db["app_links"][combined_id]["end_time"] = current_end + (30 * 86400)
    save_db(db)
    bot.send_message(m.chat.id, "✅ **تم تفعيل الاشتراك لمدة 30 يوم بنجاح!**", parse_mode="Markdown")

# --- [ ميزات المستخدم والمدير ] ---
# ... (نفس بقية وظائفك السابقة: تطبيقاتي، نجم1، الحظر، التجربة) ...
