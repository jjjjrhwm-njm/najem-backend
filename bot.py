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
                "settings": {"news": "مرحباً بكم في تطبيق نجم الإبداع", "price": 100, "trial_days": 2},
                "stats": {"total_revenue": 0}
            }
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "settings": {}, "stats": {}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)

# --- [ واجهة API للتطبيقات ] ---
@app.route('/check')
def check_status():
    aid = request.args.get('aid') # معرف الجهاز
    pkg = request.args.get('pkg') # اسم الحزمة
    app_name = request.args.get('name', 'تطبيق غير معروف') # اسم التطبيق
    
    if not aid or not pkg: return "EXPIRED"
    
    uid = f"{aid}_{pkg.replace('.', '_')}"
    db = load_db()
    
    if uid not in db["app_links"]:
        # تسجيل الجهاز أول مرة حتى لو لم يربط بعد لمعرفة اسم التطبيق
        db["app_links"][uid] = {"end_time": 0, "banned": False, "trial_used": False, "app_name": app_name}
        save_db(db)
        
    data = db["app_links"].get(uid)
    if data.get("banned"): return "BANNED"
    if time.time() > data.get("end_time", 0): return "EXPIRED"
    return "ACTIVE"

# --- [ واجهة البوت - البداية ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    user_id = str(m.from_user.id)
    user_name = m.from_user.first_name
    
    if user_id not in db["users"]:
        db["users"][user_id] = {"name": user_name, "current_app": None}
    
    args = m.text.split()
    if len(args) > 1:
        cid = args[1] # المعرف القادم من التطبيق
        if cid in db["app_links"]:
            db["app_links"][cid]["telegram_id"] = user_id
            db["app_links"][cid]["user_real_name"] = user_name
            db["users"][user_id]["current_app"] = cid
            save_db(db)
            bot.send_message(m.chat.id, f"✅ **تم ربط جهازك بنجاح!**\n📦 التطبيق: `{db['app_links'][cid].get('app_name')}`", parse_mode="Markdown")

    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add("📱 تطبيقاتي ورصيدي", "🎫 تفعيل كود")
    menu.add("🎁 تجربة مجانية (يومين)", "🛒 شراء اشتراك")
    bot.send_message(m.chat.id, f"مرحباً بك يا **{user_name}** في لوحة تحكم **نجم الإبداع**.", reply_markup=menu, parse_mode="Markdown")

# --- [ لوحة المستخدم ] ---
@bot.message_handler(func=lambda m: m.text == "📱 تطبيقاتي ورصيدي")
def user_dashboard(m):
    db = load_db()
    user_id = str(m.from_user.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == user_id]
    
    if not user_apps: return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة بحسابك حالياً.")
    
    msg = "👤 **لوحة اشتراكاتك الشخصية**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    for cid in user_apps:
        data = db["app_links"][cid]
        rem_time = data.get("end_time", 0) - time.time()
        days = int(rem_time // 86400) if rem_time > 0 else 0
        status = f"✅ نشط ({days} يوم)" if rem_time > 0 else "❌ منتهي"
        if data.get("banned"): status = "🚫 محظور"
        
        msg += f"📦 التطبيق: *{data.get('app_name')}*\n🆔 المعرف: `{cid}`\n📊 الحالة: {status}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

# --- [ ميزات المستخدم: تجربة ] ---
@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية (يومين)")
def trial_logic(m):
    db = load_db()
    user_id = str(m.from_user.id)
    cid = db["users"].get(user_id, {}).get("current_app")
    
    if not cid: return bot.send_message(m.chat.id, "❌ يرجى فتح التطبيق والضغط على 'ربط' أولاً.")
    
    if db["app_links"][cid].get("trial_used"): 
        bot.send_message(m.chat.id, "❌ لقد استخدمت الفترة التجريبية لهذا التطبيق مسبقاً.")
    else:
        # التجربة لـ 48 ساعة (يومين)
        db["app_links"][cid].update({"trial_used": True, "end_time": time.time() + (48 * 3600)})
        save_db(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل 48 ساعة تجربة مجانية بنجاح! استمتع.")

# --- [ لوحة الإدارة المتطورة (نجم1) ] ---
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    active_apps = sum(1 for x in db["app_links"].values() if x.get("end_time", 0) > time.time())
    
    msg = (f"👑 **إدارة نجم الإبداع**\n\n"
           f"👥 المستخدمين: `{len(db['users'])}` | 📱 الأجهزة: `{len(db['app_links'])}`\n"
           f"🟢 الاشتراكات النشطة: `{active_apps}`\n"
           f"💰 إجمالي الدخل: `{db['stats'].get('total_revenue', 0)}` نجمة")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎫 توليد كود", callback_data="adm_gen"),
        types.InlineKeyboardButton("🚫 حظر جهاز", callback_data="adm_ban"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="adm_unban"),
        types.InlineKeyboardButton("📊 قائمة الأجهزة", callback_data="adm_list"),
        types.InlineKeyboardButton("💰 تعديل السعر", callback_data="adm_price"),
        types.InlineKeyboardButton("📩 إذاعة", callback_data="adm_bc")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda q: q.data.startswith("adm_"))
def admin_actions(q):
    if q.from_user.id != ADMIN_ID: return
    
    if q.data == "adm_list":
        db = load_db()
        txt = "📋 **آخر 15 جهاز مسجل:**\n\n"
        for cid, v in list(db["app_links"].items())[-15:]:
            name = v.get("user_real_name", "غير مرتبط")
            app_n = v.get("app_name", "مجهول")
            status = "🟢" if v['end_time'] > time.time() else "🔴"
            if v.get("banned"): status = "🚫"
            txt += f"{status} `{cid}`\n👤 {name} | 📱 {app_n}\n⎯⎯⎯⎯⎯\n"
        bot.send_message(q.message.chat.id, txt, parse_mode="Markdown")

    elif q.data == "adm_ban":
        msg = bot.send_message(q.message.chat.id, "أرسل (ID) الجهاز المراد حظره:")
        bot.register_next_step_handler(msg, lambda m: toggle_ban(m, True))

    elif q.data == "adm_unban":
        msg = bot.send_message(q.message.chat.id, "أرسل (ID) الجهاز لفك الحظر عنه:")
        bot.register_next_step_handler(msg, lambda m: toggle_ban(m, False))

    elif q.data == "adm_gen":
        msg = bot.send_message(q.message.chat.id, "أرسل عدد الأيام للكود:")
        bot.register_next_step_handler(msg, process_gen_key)

# --- [ وظائف الإدارة ] ---

def toggle_ban(m, status):
    db = load_db()
    cid = m.text.strip()
    if cid in db["app_links"]:
        db["app_links"][cid]["banned"] = status
        save_db(db)
        word = "حظر" if status else "فك حظر"
        bot.send_message(m.chat.id, f"✅ تم {word} الجهاز `{cid}` بنجاح.", parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, "❌ المعرف غير موجود.")

def process_gen_key(m):
    try:
        days = int(m.text)
        code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
        db = load_db(); db["vouchers"][code] = days; save_db(db)
        bot.send_message(m.chat.id, f"✅ تم توليد كود جديد لمدة {days} يوم:\n\n`{code}`", parse_mode="Markdown")
    except: bot.send_message(m.chat.id, "❌ أرسل رقماً فقط.")

# --- [ تفعيل الكود ] ---
@bot.message_handler(func=lambda m: m.text == "🎫 تفعيل كود")
def redeem_ui(m):
    msg = bot.send_message(m.chat.id, "قم بإرسال كود التفعيل هنا:")
    bot.register_next_step_handler(msg, redeem_logic)

def redeem_logic(m):
    code = m.text.strip()
    db = load_db()
    user_id = str(m.from_user.id)
    cid = db["users"].get(user_id, {}).get("current_app")
    
    if code in db["vouchers"]:
        if not cid: return bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
        days = db["vouchers"].pop(code)
        db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (days * 86400)
        save_db(db)
        bot.send_message(m.chat.id, f"✅ ممتاز! تم إضافة {days} يوم لاشتراكك في تطبيق {db['app_links'][cid].get('app_name')}.")
    else:
        bot.send_message(m.chat.id, "❌ الكود خاطئ أو تم استخدامه سابقاً.")

# --- [ تشغيل السيرفر والبوت ] ---
if __name__ == "__main__":
    # تشغيل Flask في ثريد منفصل
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)), debug=False, use_reloader=False)).start()
    print("Bot is running...")
    bot.infinity_polling()
