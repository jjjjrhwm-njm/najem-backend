import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread, Lock 

# --- [ الإعدادات الأساسية - لم يتم تغييرها ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json" 

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock() 

def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): 
            return {"users": {}, "app_links": {}, "vouchers": {}, "settings": {"broadcast_msg": ""}}
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
    db = load_db()
    user_data = db["app_links"].get(aid)
    
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
    
    if uid not in db["users"]: 
        db["users"][uid] = {"app_id": None, "join_date": time.time()}
    
    if len(args) > 1:
        aid = args[1]
        db["app_links"][aid] = db["app_links"].get(aid, {"end_time": 0, "banned": False, "trial_used": False, "telegram_id": uid})
        db["app_links"][aid]["telegram_id"] = uid
        db["users"][uid]["app_id"] = aid
        save_db(db)
        bot.send_message(m.chat.id, f"✅ **تم ربط جهازك بنجاح!**\nمعرف الجهاز: `{aid}`", parse_mode="Markdown") 

    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add("🎁 تجربة مجانية (24س)", "🎫 تفعيل كود")
    menu.add("📊 حالتي", "🛒 شراء اشتراك")
    # إضافة زر الدعم الفني كإضافة جمالية
    menu.add("👨‍💻 الدعم الفني")
    
    bot.send_message(m.chat.id, f"أهلاً بك في بوت **نجم الإبداع** 🌟\nنظام الحماية والاشتراكات المتطور.\n\nاختر من القائمة أدناه:", reply_markup=menu, parse_mode="Markdown") 

# --- [ نظام الشراء المطور ] --- 
@bot.message_handler(func=lambda m: m.text == "🛒 شراء اشتراك")
def pricing_plan(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⭐ شهر (100 نجمة)", callback_data="buy_30"))
    markup.add(types.InlineKeyboardButton("⭐ 3 أشهر (250 نجمة)", callback_data="buy_90"))
    bot.send_message(m.chat.id, "💎 **اختر باقة الاشتراك المناسبة لك:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda q: q.data.startswith("buy_"))
def send_payment_invoice(q):
    db = load_db()
    uid = str(q.from_user.id)
    aid = db["users"].get(uid, {}).get("app_id")
    days = int(q.data.split("_")[1])
    price = 100 if days == 30 else 250

    if not aid:
        return bot.answer_callback_query(q.id, "❌ يجب الدخول من التطبيق أولاً لربط جهازك.", show_alert=True)
    
    bot.send_invoice(
        q.message.chat.id, 
        title=f"اشتراك برو - {days} يوم", 
        description=f"تفعيل كامل ميزات التطبيق لجهازك: {aid}",
        invoice_payload=f"pay_{aid}_{days}",
        provider_token="", 
        currency="XTR", 
        prices=[types.LabeledPrice(label="اشتراك برو", amount=price)]
    )

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q):
    bot.answer_pre_checkout_query(q.id, ok=True) 

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db()
    payload = m.successful_payment.invoice_payload.split("_")
    aid = payload[1]
    days = int(payload[2])
    
    current_end = max(time.time(), db["app_links"].get(aid, {}).get("end_time", 0))
    db["app_links"][aid]["end_time"] = current_end + (days * 86400)
    save_db(db)
    
    bot.send_message(m.chat.id, f"✅ **تم الدفع بنجاح!**\nتم تمديد اشتراكك لمدة {days} يوم للمعرف: `{aid}`", parse_mode="Markdown")
    # إشعار للمدير
    bot.send_message(ADMIN_ID, f"💰 **عملية شراء جديدة!**\nالمستخدم: {m.from_user.first_name}\nالجهاز: `{aid}`\nالمدة: {days} يوم")

# --- [ الوظائف الحالية مع تحسينات ] --- 
@bot.message_handler(func=lambda m: m.text == "📊 حالتي")
def status(m):
    db = load_db()
    aid = db["users"].get(str(m.from_user.id), {}).get("app_id")
    if not aid: return bot.send_message(m.chat.id, "❌ لم يتم ربط جهازك. ادخل من التطبيق أولاً.")
    
    info = db["app_links"].get(aid, {})
    end_time = info.get("end_time", 0)
    rem_seconds = end_time - time.time()
    
    if rem_seconds > 0:
        days = int(rem_seconds / 86400)
        hours = int((rem_seconds % 86400) / 3600)
        msg = f"✅ **اشتراكك نشط**\n👤 المعرف: `{aid}`\n⏳ المتبقي: {days} يوم و {hours} ساعة."
    else:
        msg = f"❌ **اشتراكك منتهي**\n👤 المعرف: `{aid}`\nيرجى التجديد للاستمرار."
        
    bot.send_message(m.chat.id, msg, parse_mode="Markdown") 

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية (24س)")
def trial(m):
    db = load_db()
    aid = db["users"].get(str(m.from_user.id), {}).get("app_id")
    if not aid: return bot.send_message(m.chat.id, "❌ ادخل من التطبيق أولاً للربط.")
    
    if db["app_links"][aid].get("trial_used"):
        bot.send_message(m.chat.id, "❌ لقد استخدمت الفترة التجريبية لهذا الجهاز مسبقاً.")
    else:
        db["app_links"][aid]["trial_used"] = True
        db["app_links"][aid]["end_time"] = time.time() + 86400
        save_db(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل 24 ساعة مجانية!\nعد للتطبيق واضغط **دخول** الآن.")
        bot.send_message(ADMIN_ID, f"🎁 مستخدم فعل التجربة: {m.from_user.first_name}\nالجهاز: `{aid}`")

@bot.message_handler(func=lambda m: m.text == "👨‍💻 الدعم الفني")
def support(m):
    bot.send_message(m.chat.id, "للدعم الفني والاستفسارات تواصل مع المطور:\n@نجم_الإبداع") # يمكنك وضع يوزرك هنا

# --- [ لوحة التحكم المتقدمة للمدير ] --- 
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    total_users = len(db["users"])
    active_subs = sum(1 for a in db["app_links"].values() if a.get("end_time", 0) > time.time())
    
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🎫 توليد كود (30 يوم)", callback_data="gen_30"))
    markup.row(types.InlineKeyboardButton("📢 إذاعة للكل", callback_data="broadcast"))
    markup.row(types.InlineKeyboardButton("📊 إحصائيات مفصلة", callback_data="stats"))
    
    msg = f"👑 **لوحة تحكم نجم الإبداع**\n\n👥 عدد المستخدمين: {total_users}\n✅ الاشتراكات النشطة: {active_subs}"
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown") 

@bot.callback_query_handler(func=lambda q: q.data == "broadcast")
def broadcast_step1(q):
    msg = bot.send_message(q.message.chat.id, "أرسل الرسالة التي تريد إرسالها لجميع مستخدمي البوت:")
    bot.register_next_step_handler(msg, broadcast_step2)

def broadcast_step2(m):
    db = load_db()
    users = db["users"].keys()
    count = 0
    for uid in users:
        try:
            bot.send_message(uid, m.text)
            count += 1
        except: continue
    bot.send_message(m.chat.id, f"✅ تم إرسال الرسالة إلى {count} مستخدم.")

@bot.callback_query_handler(func=lambda q: q.data == "gen_30")
def generate(q):
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db = load_db()
    db["vouchers"][code] = 30
    save_db(db)
    bot.edit_message_text(f"🎫 كود جديد تم توليده:\n`{code}`", q.message.chat.id, q.message.message_id, parse_mode="Markdown") 

@bot.message_handler(func=lambda m: m.text == "🎫 تفعيل كود")
def redeem_start(m):
    msg = bot.send_message(m.chat.id, "أرسل كود التفعيل الذي حصلت عليه:")
    bot.register_next_step_handler(msg, redeem_final) 

def redeem_final(m):
    code = m.text.strip()
    db = load_db()
    if code in db["vouchers"]:
        days = db["vouchers"].pop(code)
        aid = db["users"].get(str(m.from_user.id), {}).get("app_id")
        if aid:
            current = max(time.time(), db["app_links"][aid].get("end_time", 0))
            db["app_links"][aid]["end_time"] = current + (days * 86400)
            save_db(db)
            bot.send_message(m.chat.id, f"✅ تم تفعيل الاشتراك بنجاح لمدة {days} يوم!\nاستمتع بميزات التطبيق.")
        else: bot.send_message(m.chat.id, "❌ لم يتم ربط جهازك. افتح التطبيق أولاً.")
    else: bot.send_message(m.chat.id, "❌ الكود غير صحيح أو تم استخدامه مسبقاً.") 

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))) 

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
