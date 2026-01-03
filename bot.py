import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread, Lock

# --- [ الإعدادات الأساسية - مبرمجة وجاهزة ] ---
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
                "settings": {"news": "مرحباً بك في تطبيقات نجم الإبداع", "price": 100},
                "stats": {"total_revenue": 0}
            }
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "settings": {"news": "خبر جديد", "price": 100}, "stats": {"total_revenue": 0}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)

# --- [ واجهات API للتطبيق ] ---
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

# --- [ أوامر البوت ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    if uid not in db["users"]: db["users"][uid] = {"current_app": None}
    
    args = m.text.split()
    if len(args) > 1: # معالجة الربط التلقائي من التطبيق
        cid = args[1]
        db["app_links"].setdefault(cid, {"end_time": 0, "banned": False, "trial_used": False})
        db["app_links"][cid]["telegram_id"] = uid
        db["users"][uid]["current_app"] = cid
        save_db(db)
        bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**\nيمكنك الآن التحكم في اشتراكك.", parse_mode="Markdown")

    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add("📱 تطبيقاتي ورصيدي", "🎫 تفعيل كود")
    menu.add("🎁 تجربة مجانية", "🛒 شراء اشتراك")
    bot.send_message(m.chat.id, f"مرحباً بك يا **نجم الإبداع** في بوت الإدارة الخاص بك.", reply_markup=menu, parse_mode="Markdown")

# --- [ لوحة المدير (نجم1) ] ---
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    msg = (f"👑 **لوحة تحكم نجم الإبداع**\n\n"
           f"👥 المستخدمين: `{len(db['users'])}`\n"
           f"💰 الدخل الكلي: `{db['stats'].get('total_revenue', 0)}` نجمة\n"
           f"⚙️ السعر الحالي: `{db['settings'].get('price')}` نجمة\n"
           f"📢 الخبر: `{db['settings'].get('news')[:20]}...`")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎫 توليد كود", callback_data="adm_gen"),
        types.InlineKeyboardButton("📢 خبر التطبيق", callback_data="adm_news"),
        types.InlineKeyboardButton("💰 سعر الاشتراك", callback_data="adm_price"),
        types.InlineKeyboardButton("🚫 حظر جهاز", callback_data="adm_ban"),
        types.InlineKeyboardButton("📩 إذاعة عامة", callback_data="adm_bc")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda q: q.data.startswith("adm_"))
def admin_callbacks(q):
    if q.data == "adm_gen":
        msg = bot.send_message(q.message.chat.id, "أدخل عدد الأيام للكود:")
        bot.register_next_step_handler(msg, do_gen_key)
    elif q.data == "adm_news":
        msg = bot.send_message(q.message.chat.id, "أرسل الخبر الجديد للمستخدمين:")
        bot.register_next_step_handler(msg, do_set_news)
    elif q.data == "adm_price":
        msg = bot.send_message(q.message.chat.id, "أدخل السعر الجديد بالنجوم:")
        bot.register_next_step_handler(msg, do_set_price)
    elif q.data == "adm_bc":
        msg = bot.send_message(q.message.chat.id, "أرسل رسالة الإذاعة للجميع:")
        bot.register_next_step_handler(msg, do_broadcast)

# --- [ وظائف المدير ] ---
def do_gen_key(m):
    try:
        days = int(m.text)
        code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
        db = load_db(); db["vouchers"][code] = days; save_db(db)
        bot.send_message(m.chat.id, f"✅ كود جديد ({days} يوم):\n`{code}`")
    except: bot.send_message(m.chat.id, "❌ خطأ: أرسل رقماً فقط.")

def do_set_news(m):
    db = load_db(); db["settings"]["news"] = m.text; save_db(db)
    bot.send_message(m.chat.id, "✅ تم تحديث الخبر داخل التطبيق.")

def do_set_price(m):
    try:
        db = load_db(); db["settings"]["price"] = int(m.text); save_db(db)
        bot.send_message(m.chat.id, "✅ تم تحديث السعر بنجاح.")
    except: bot.send_message(m.chat.id, "❌ خطأ في السعر.")

def do_broadcast(m):
    db = load_db(); count = 0
    for uid in db["users"]:
        try: bot.send_message(uid, f"📢 **إعلان هام:**\n\n{m.text}"); count += 1
        except: pass
    bot.send_message(m.chat.id, f"✅ تم الإرسال لـ {count} مستخدم.")

# --- [ وظائف المستخدم ] ---
@bot.message_handler(func=lambda m: m.text == "📱 تطبيقاتي ورصيدي")
def user_dashboard(m):
    db = load_db(); uid = str(m.from_user.id)
    apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not apps: return bot.send_message(m.chat.id, "❌ لا توجد أجهزة مرتبطة.")
    msg = "👤 **حالة اشتراكاتك:**\n⎯⎯⎯⎯⎯⎯⎯⎯\n"
    for cid in apps:
        rem = db["app_links"][cid]["end_time"] - time.time()
        stat = "✅ نشط" if rem > 0 else "❌ منتهي"
        msg += f"📦 جهاز: `{cid[:12]}...` | {stat}\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🛒 شراء اشتراك")
def buy_subs(m):
    db = load_db(); cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ افتح التطبيق أولاً لربط جهازك.")
    price = db["settings"].get("price", 100)
    bot.send_invoice(m.chat.id, "تفعيل اشتراك برو", f"جهاز: {cid}", f"pay_{cid}", "", "XTR", [types.LabeledPrice("اشتراك 30 يوم", price)])

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db(); cid = m.successful_payment.invoice_payload.replace("pay_", "")
    db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (30 * 86400)
    db["stats"]["total_revenue"] += m.successful_payment.total_amount
    save_db(db); bot.send_message(m.chat.id, "✅ تم الشراء وتفعيل الاشتراك!")

@bot.message_handler(func=lambda m: m.text == "🎫 تفعيل كود")
def use_voucher(m):
    msg = bot.send_message(m.chat.id, "أرسل الكود:")
    bot.register_next_step_handler(msg, finish_voucher)

def finish_voucher(m):
    code, db = m.text.strip(), load_db()
    if code in db["vouchers"]:
        days = db["vouchers"].pop(code)
        cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
        if cid:
            db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (days * 86400)
            save_db(db); bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم بنجاح!")
        else: bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    else: bot.send_message(m.chat.id, "❌ الكود غير صحيح.")

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية")
def trial_start(m):
    db = load_db(); cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    if db["app_links"][cid].get("trial_used"): bot.send_message(m.chat.id, "❌ استخدمت التجربة سابقاً.")
    else:
        db["app_links"][cid].update({"trial_used": True, "end_time": time.time() + 7200})
        save_db(db); bot.send_message(m.chat.id, "✅ تم تفعيل ساعتين تجربة!")

# --- [ تشغيل ] ---
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
