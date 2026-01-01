import os
import time
import json
import uuid
from flask import Flask, request, jsonify
from telebot import TeleBot, types
from threading import Thread

# --- إعداداتك الخاصة ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 12345678  # ضع هنا آيدي حسابك الحقيقي
DB_FILE = 'database.json'

bot = TeleBot(API_TOKEN)
app = Flask(__name__)

# --- وظائف قاعدة البيانات ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "app_links": {}, "vouchers": {}}
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=4)

# --- نظام الفحص (API) ---
@app.route('/check')
def check():
    aid = request.args.get('aid')
    pkg = request.args.get('pkg') # استلام اسم الحزمة لضمان الفصل
    
    if not aid or not pkg:
        return "EXPIRED"
        
    db = load_db()
    # إنشاء مفتاح فريد لكل تطبيق على كل جهاز
    app_key = f"{aid}_{pkg}"
    
    if app_key in db["app_links"]:
        if db["app_links"][app_key].get("end_time", 0) > time.time():
            return "ACTIVE"
    return "EXPIRED"

# --- معالجات البوت ---

@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    args = m.text.split()
    if len(args) > 1:
        # استلام البيانات بصيغة ID_PKG
        data = args[1].split('_')
        if len(data) == 2:
            aid, pkg = data[0], data[1]
            db["users"][str(m.from_user.id)] = {"aid": aid, "pkg": pkg}
            save_db(db)
            bot.send_message(m.chat.id, f"✅ تم الربط!\n📱 التطبيق: {pkg}\n🆔 الجهاز: {aid}")

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🎁 تجربة مجانية (3س)", "📊 حالتي")
    markup.add("🎫 تفعيل كود", "💎 شراء اشتراك")
    bot.send_message(m.chat.id, "مرحباً بك في بوت نجم الإبداع 🌟", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "💎 شراء اشتراك")
def buy_pro(m):
    db = load_db()
    user = db["users"].get(str(m.from_user.id))
    if not user: return bot.send_message(m.chat.id, "❌ ادخل من التطبيق أولاً للربط.")
    
    aid, pkg = user["aid"], user["pkg"]
    
    bot.send_invoice(
        m.chat.id,
        title="اشتراك شهر كامل - برو",
        description=f"تفعيل ميزات تطبيق {pkg} لمدة 30 يوم.",
        invoice_payload=f"pay_{aid}_{pkg}", # Payload يحتوي على الجهاز والحزمة
        provider_token="",
        currency="XTR",
        prices=[types.LabeledPrice(label="اشتراك برو", amount=100)]
    )

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q):
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db()
    payload = m.successful_payment.invoice_payload.replace("pay_", "")
    # Payload الآن هو aid_pkg
    
    current_end = max(time.time(), db["app_links"].get(payload, {}).get("end_time", 0))
    if payload not in db["app_links"]: db["app_links"][payload] = {}
    
    db["app_links"][payload]["end_time"] = current_end + (30 * 86400)
    save_db(db)
    bot.send_message(m.chat.id, f"✅ تم الدفع بنجاح لتطبيقك!")

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية (3س)")
def trial(m):
    db = load_db()
    user = db["users"].get(str(m.from_user.id))
    if not user: return bot.send_message(m.chat.id, "❌ ادخل من التطبيق أولاً.")
    
    app_key = f"{user['aid']}_{user['pkg']}"
    if app_key not in db["app_links"]: db["app_links"][app_key] = {}

    if db["app_links"][app_key].get("trial_used"):
        bot.send_message(m.chat.id, "❌ استخدمت الفترة التجريبية لهذا التطبيق سابقاً.")
    else:
        db["app_links"][app_key]["trial_used"] = True
        db["app_links"][app_key]["end_time"] = time.time() + 10800 # 3 ساعات
        save_db(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل 3 ساعات! عد للتطبيق واضغط دخول.")

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
    bot.edit_message_text(f"🎫 كود جديد:\n`{code}`", q.message.chat.id, q.message.message_id)

@bot.message_handler(func=lambda m: m.text == "🎫 تفعيل كود")
def redeem_start(m):
    msg = bot.send_message(m.chat.id, "أرسل كود التفعيل:")
    bot.register_next_step_handler(msg, redeem_final)

def redeem_final(m):
    code = m.text.strip()
    db = load_db()
    if code in db["vouchers"]:
        days = db["vouchers"].pop(code)
        user = db["users"].get(str(m.from_user.id))
        if user:
            app_key = f"{user['aid']}_{user['pkg']}"
            if app_key not in db["app_links"]: db["app_links"][app_key] = {}
            db["app_links"][app_key]["end_time"] = max(time.time(), db["app_links"][app_key].get("end_time", 0)) + (days * 86400)
            save_db(db)
            bot.send_message(m.chat.id, f"✅ تم التفعيل لمدة {days} يوم!")
        else: bot.send_message(m.chat.id, "❌ اربط جهازك أولاً.")
    else: bot.send_message(m.chat.id, "❌ كود غير صحيح.")

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
