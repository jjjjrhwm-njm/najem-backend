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

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE):
            return {
                "users": {}, "app_links": {}, "vouchers": {}, 
                "settings": {"news": "مرحباً بكم في تطبيق نجم الإبداع", "price": 100, "trial_hours": 2},
                "stats": {"total_revenue": 0}
            }
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
                # ضمان وجود المفاتيح الأساسية
                for key in ["users", "app_links", "vouchers", "settings", "stats"]:
                    if key not in db: db[key] = {}
                if not db["settings"]: db["settings"] = {"news": "لا توجد أخبار", "price": 100, "trial_hours": 2}
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "settings": {}, "stats": {}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)

# --- [ واجهة API للتطبيقات ] ---
@app.route('/check')
def check_status():
    aid, pkg = request.args.get('aid'), request.args.get('pkg')
    if not aid or not pkg: return "EXPIRED"
    uid = f"{aid}_{pkg.replace('.', '_')}"
    db = load_db()
    data = db["app_links"].get(uid)
    if not data: return "EXPIRED"
    if data.get("banned"): return "BANNED"
    if time.time() > data.get("end_time", 0): return "EXPIRED"
    return "ACTIVE"

@app.route('/get_news')
def get_news():
    return load_db()["settings"].get("news", "لا توجد أخبار حالياً")

# --- [ واجهة البوت - البداية ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    if uid not in db["users"]: db["users"][uid] = {"current_app": None}
    
    args = m.text.split()
    if len(args) > 1:
        cid = args[1] # المعرف القادم من التطبيق
        db["app_links"].setdefault(cid, {"end_time": 0, "banned": False, "trial_used": False})
        db["app_links"][cid]["telegram_id"] = uid
        db["users"][uid]["current_app"] = cid
        save_db(db)
        bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**\nيمكنك الآن إدارة اشتراكك من هنا.", parse_mode="Markdown")

    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add("📱 تطبيقاتي ورصيدي", "🎫 تفعيل كود")
    menu.add("🎁 تجربة مجانية", "🛒 شراء اشتراك")
    bot.send_message(m.chat.id, f"مرحباً بك يا **نجم الإبداع** في لوحة التحكم الخاصة بك.", reply_markup=menu, parse_mode="Markdown")

# --- [ لوحة المستخدم ] ---
@bot.message_handler(func=lambda m: m.text == "📱 تطبيقاتي ورصيدي")
def user_dashboard(m):
    db = load_db()
    uid = str(m.from_user.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    
    if not user_apps: return bot.send_message(m.chat.id, "❌ لا توجد أجهزة مرتبطة.")
    
    msg = "👤 **لوحة اشتراكاتك الشخصية**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    for cid in user_apps:
        data = db["app_links"][cid]
        rem_time = data.get("end_time", 0) - time.time()
        status = "✅ نشط" if rem_time > 0 else "❌ منتهي"
        if data.get("banned"): status = "🚫 محظور"
        
        msg += f"📦 جهاز: `{cid[:15]}...`\n📊 الحالة: {status}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

# --- [ نظام الشراء ] ---
@bot.message_handler(func=lambda m: m.text == "🛒 شراء اشتراك")
def send_payment(m):
    db = load_db()
    cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ افتح التطبيق أولاً للربط.")
    
    price = db["settings"].get("price", 100)
    bot.send_invoice(
        m.chat.id, title="تفعيل اشتراك 30 يوم",
        description=f"تفعيل الجهاز: {cid}",
        invoice_payload=f"pay_{cid}",
        provider_token="", currency="XTR",
        prices=[types.LabeledPrice(label="اشتراك برو", amount=price)]
    )

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db()
    cid = m.successful_payment.invoice_payload.replace("pay_", "")
    db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (30 * 86400)
    db["stats"]["total_revenue"] = db["stats"].get("total_revenue", 0) + m.successful_payment.total_amount
    save_db(db)
    bot.send_message(m.chat.id, "✅ تم الشراء بنجاح!")

# --- [ لوحة الإدارة المتطورة (نجم1) ] ---
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    active = sum(1 for x in db["app_links"].values() if x.get("end_time", 0) > time.time())
    msg = (f"👑 **إدارة نجم الإبداع**\n\n"
           f"👥 المستخدمين: `{len(db['users'])}` | ⚡ الأجهزة: `{len(db['app_links'])}`\n"
           f"🟢 نشط حالياً: `{active}`\n"
           f"💰 إجمالي الدخل: `{db['stats'].get('total_revenue', 0)}` نجمة\n"
           f"⚙️ السعر الحالي: `{db['settings'].get('price')}`")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎫 توليد كود", callback_data="adm_gen"),
        types.InlineKeyboardButton("📢 خبر التطبيق", callback_data="adm_news"),
        types.InlineKeyboardButton("💰 تعديل السعر", callback_data="adm_price"),
        types.InlineKeyboardButton("🚫 حظر/فك", callback_data="adm_ban"),
        types.InlineKeyboardButton("📊 عرض الأجهزة", callback_data="adm_list"),
        types.InlineKeyboardButton("📩 إذاعة عامة", callback_data="adm_bc")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda q: q.data.startswith("adm_"))
def admin_actions(q):
    if q.from_user.id != ADMIN_ID: return
    
    if q.data == "adm_gen":
        msg = bot.send_message(q.message.chat.id, "كم يوماً تريد للكود؟ (أرسل رقماً):")
        bot.register_next_step_handler(msg, process_gen_key)
    
    elif q.data == "adm_news":
        msg = bot.send_message(q.message.chat.id, "أرسل الخبر الجديد ليظهر في التطبيق:")
        bot.register_next_step_handler(msg, process_set_news)

    elif q.data == "adm_price":
        msg = bot.send_message(q.message.chat.id, "أدخل السعر الجديد بالنجوم:")
        bot.register_next_step_handler(msg, process_set_price)
    
    elif q.data == "adm_list":
        db = load_db()
        txt = "📋 **قائمة الأجهزة:**\n"
        for k, v in list(db["app_links"].items())[-10:]: # آخر 10
            txt += f"🔹 `{k[:10]}...` -> {'✅' if v['end_time'] > time.time() else '❌'}\n"
        bot.send_message(q.message.chat.id, txt, parse_mode="Markdown")

    elif q.data == "adm_bc":
        msg = bot.send_message(q.message.chat.id, "أرسل نص الإذاعة للجميع:")
        bot.register_next_step_handler(msg, process_broadcast)

# --- [ وظائف المعالجة للإدارة ] ---

def process_gen_key(m):
    try:
        days = int(m.text)
        code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
        db = load_db(); db["vouchers"][code] = days; save_db(db)
        bot.send_message(m.chat.id, f"✅ تم توليد كود ({days} يوم):\n`{code}`", parse_mode="Markdown")
    except: bot.send_message(m.chat.id, "❌ خطأ: أرسل رقماً فقط.")

def process_set_news(m):
    db = load_db(); db["settings"]["news"] = m.text; save_db(db)
    bot.send_message(m.chat.id, "✅ تم تحديث خبر التطبيق.")

def process_set_price(m):
    try:
        db = load_db(); db["settings"]["price"] = int(m.text); save_db(db)
        bot.send_message(m.chat.id, f"✅ تم تغيير السعر إلى {m.text} نجمة.")
    except: bot.send_message(m.chat.id, "❌ خطأ في السعر.")

def process_broadcast(m):
    db = load_db(); count = 0
    for uid in db["users"]:
        try: bot.send_message(uid, f"📢 **إعلان من الإدارة:**\n\n{m.text}", parse_mode="Markdown"); count += 1
        except: pass
    bot.send_message(m.chat.id, f"✅ تم الإرسال لـ {count} مستخدم.")

# --- [ ميزات المستخدم: تفعيل وتجربة ] ---
@bot.message_handler(func=lambda m: m.text == "🎫 تفعيل كود")
def redeem_ui(m):
    msg = bot.send_message(m.chat.id, "أرسل كود التفعيل الخاص بك:")
    bot.register_next_step_handler(msg, redeem_logic)

def redeem_logic(m):
    code, db = m.text.strip(), load_db()
    if code in db["vouchers"]:
        days = db["vouchers"].pop(code)
        cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
        if cid:
            db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (days * 86400)
            save_db(db); bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم بنجاح!")
        else: bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    else: bot.send_message(m.chat.id, "❌ الكود غير صحيح أو مستخدم.")

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية")
def trial_logic(m):
    db = load_db(); cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    if db["app_links"][cid].get("trial_used"): bot.send_message(m.chat.id, "❌ استخدمت التجربة سابقاً.")
    else:
        hours = db["settings"].get("trial_hours", 2)
        db["app_links"][cid].update({"trial_used": True, "end_time": time.time() + (hours * 3600)})
        save_db(db); bot.send_message(m.chat.id, f"✅ تم تفعيل {hours} ساعات تجربة مجانية!")

# --- [ تشغيل ] ---
if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))).start()
    bot.infinity_polling()
