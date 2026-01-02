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
            return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً"}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: 
                db = json.load(f)
                if "global_news" not in db: db["global_news"] = "لا توجد أخبار حالياً"
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً"}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4) 

# --- [ واجهة فحص التطبيق والرسائل الإدارية - API ] ---

@app.route('/check')
def check_status():
    aid, pkg = request.args.get('aid'), request.args.get('pkg')
    if not aid or not pkg: return "EXPIRED"
    unique_id = f"{aid}_{pkg.replace('.', '_')}"
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
    combined_id = db["users"].get(str(m.from_user.id), {}).get("current_app")
    if not combined_id: return bot.send_message(m.chat.id, "❌ ادخل من التطبيق أولاً لربط جهازك.")
    
    bot.send_invoice(
        m.chat.id, title="تفعيل اشتراك برو",
        description=f"تفعيل لمدة 30 يوم للتطبيق: {combined_id}",
        invoice_payload=f"pay_{combined_id}",
        provider_token="", currency="XTR",
        prices=[types.LabeledPrice(label="اشتراك 30 يوم", amount=100)]
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
    bot.send_message(m.chat.id, "✅ **تم تفعيل الاشتراك بنجاح!**")

# --- [ ميزات المستخدم ] ---

@bot.message_handler(func=lambda m: m.text == "📱 تطبيقاتي")
def my_apps(m):
    db = load_db(); uid = str(m.from_user.id); my_subs = []
    for cid, data in db["app_links"].items():
        if data.get("telegram_id") == uid:
            pkg = cid.split('_', 1)[-1].replace("_", ".")
            rem = max(0, int((data.get("end_time", 0) - time.time()) / 3600))
            status = "✅ نشط" if rem > 0 else "❌ منتهي"
            if data.get("banned"): status = "🚫 محظور"
            my_subs.append(f"📦 `{pkg}`\n   الوضع: {status} ({rem} ساعة)")
    bot.send_message(m.chat.id, "📋 **قائمة اشتراكاتك:**\n\n" + ("\n".join(my_subs) if my_subs else "❌ لا توجد تطبيقات."))

@bot.message_handler(func=lambda m: m.text == "📊 حالتي")
def status(m):
    db = load_db(); cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ لم يتم الربط.")
    info = db["app_links"].get(cid, {})
    rem = max(0, int((info.get("end_time", 0) - time.time()) / 3600))
    bot.send_message(m.chat.id, f"⏳ المتبقي للتطبيق الحالي: {rem} ساعة.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة (ساعتين)")
def trial(m):
    db = load_db(); cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ ادخل من التطبيق أولاً.")
    if db["app_links"][cid].get("trial_used"):
        bot.send_message(m.chat.id, "❌ استخدمت التجربة سابقاً.")
    else:
        db["app_links"][cid]["trial_used"] = True
        db["app_links"][cid]["end_time"] = time.time() + 7200
        save_db(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل ساعتين تجربة!")

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
            db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (days * 86400)
            save_db(db)
            bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم!")
        else: bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    else: bot.send_message(m.chat.id, "❌ كود خطأ.")

# --- [ لوحة المدير - نجم1 ] ---

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    stats = (f"👑 **لوحة المدير**\n\n👥 مستخدمين: `{len(db['users'])}`"
             f"\n⚡ روابط: `{len(db['app_links'])}`\n🎫 أكواد: `{len(db['vouchers'])}`"
             f"\n📢 الخبر: `{db.get('global_news')[:20]}...`")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎫 توليد كود", callback_data="gen_key"),
        types.InlineKeyboardButton("📢 إذاعة تلجرام", callback_data="bc_tele"),
        types.InlineKeyboardButton("📱 إذاعة التطبيق", callback_data="bc_app"),
        types.InlineKeyboardButton("🚫 حظر مستخدم", callback_data="ban_user"),
        types.InlineKeyboardButton("🧹 تنظيف", callback_data="cleanup")
    )
    bot.send_message(m.chat.id, stats, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda q: True)
def admin_actions(q):
    if q.data == "gen_key":
        code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
        db = load_db(); db["vouchers"][code] = 30; save_db(db)
        bot.answer_callback_query(q.id, "تم التوليد")
        bot.send_message(q.message.chat.id, f"🎫 كود (30 يوم):\n`{code}`", parse_mode="Markdown")
    
    elif q.data == "bc_tele":
        msg = bot.send_message(q.message.chat.id, "ارسل رسالة الإذاعة:")
        bot.register_next_step_handler(msg, lambda m: [bot.send_message(u, f"📢 **إعلان:**\n\n{m.text}") for u in load_db()["users"]] and bot.send_message(m.chat.id, "✅ تم"))

    elif q.data == "bc_app":
        msg = bot.send_message(q.message.chat.id, "ارسل الخبر للتطبيقات:")
        bot.register_next_step_handler(msg, do_bc_app)

    elif q.data == "ban_user":
        msg = bot.send_message(q.message.chat.id, "ارسل (AID_PKG) للحظر:")
        bot.register_next_step_handler(msg, process_ban)

def do_bc_app(m):
    db = load_db(); db["global_news"] = m.text; save_db(db)
    bot.send_message(m.chat.id, "✅ تم تحديث خبر التطبيقات.")

def process_ban(m):
    db = load_db(); target = m.text.strip()
    if target in db["app_links"]:
        db["app_links"][target]["banned"] = True
        save_db(db); bot.send_message(m.chat.id, f"🚫 تم حظر `{target}`")
    else: bot.send_message(m.chat.id, "❌ غير موجود.")

# --- [ التشغيل ] ---
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
