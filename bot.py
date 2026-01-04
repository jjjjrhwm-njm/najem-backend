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
            return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً"}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: 
                db = json.load(f)
                if "global_news" not in db: db["global_news"] = "لا توجد أخبار حالياً"
                if "vouchers" not in db: db["vouchers"] = {}
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً"}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4) 

# --- [ واجهة API ] ---
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
    return load_db().get("global_news", "لا توجد أخبار")

# --- [ واجهة البوت - البداية ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    if uid not in db["users"]: db["users"][uid] = {"current_app": None}
    
    args = m.text.split()
    if len(args) > 1:
        cid = args[1]
        if cid not in db["app_links"]:
            db["app_links"][cid] = {"end_time": 0, "banned": False, "trial_last_time": 0, "telegram_id": uid}
        db["app_links"][cid]["telegram_id"] = uid
        db["users"][uid]["current_app"] = cid
        save_db(db)
        bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**", parse_mode="Markdown")

    # أزرار شفافة (Inline) بدلاً من الكيبورد العادي
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
        types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
        types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
        types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy")
    )
    bot.send_message(m.chat.id, f"مرحباً بك يا **نجم الإبداع** 🌟\nاستخدم القائمة أدناه للتحكم في اشتراكاتك:", reply_markup=markup, parse_mode="Markdown")

# --- [ معالجة ضغطات الأزرار ] ---
@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    db = load_db()

    # --- خيارات المستخدم ---
    if q.data == "u_dashboard":
        user_dashboard(q.message)
    elif q.data == "u_redeem":
        msg = bot.send_message(q.message.chat.id, "🎫 **أرسل كود التفعيل الآن:**")
        bot.register_next_step_handler(msg, redeem_code_step)
    elif q.data.startswith("redeem_select_"):
        redeem_select_app(q.message, q.data.split("_")[2])
    elif q.data == "u_trial":
        process_trial(q.message)
    elif q.data.startswith("trial_select_"):
        trial_select_app(q.message, q.data.split("_")[2])
    elif q.data == "u_buy":
        send_payment(q.message)

    # --- خيارات المدير (نجم1) ---
    elif q.from_user.id == ADMIN_ID:
        if q.data == "list_all":
            show_detailed_users(q.message)
        elif q.data == "gen_key":
            msg = bot.send_message(q.message.chat.id, "كم عدد الأيام التي تريدها لهذا الكود؟ (أرسل رقماً فقط)")
            bot.register_next_step_handler(msg, process_gen_key)
        elif q.data == "bc_tele":
            msg = bot.send_message(q.message.chat.id, "ارسل رسالة الإذاعة للتلجرام:")
            bot.register_next_step_handler(msg, do_bc_tele)
        elif q.data == "bc_app":
            msg = bot.send_message(q.message.chat.id, "ارسل الخبر الجديد للتطبيق:")
            bot.register_next_step_handler(msg, do_bc_app)
        elif q.data in ["ban_op", "unban_op"]:
            action = "لحظره" if q.data == "ban_op" else "لفك حظره"
            msg = bot.send_message(q.message.chat.id, f"ارسل المعرف {action}:")
            bot.register_next_step_handler(msg, process_ban_unban, q.data)

# --- [ وظائف الإدارة المطورة ] ---

def show_detailed_users(m):
    db = load_db()
    if not db["app_links"]: return bot.send_message(m.chat.id, "لا توجد أجهزة مسجلة.")
    
    full_list = "📂 **قائمة المشتركين والأجهزة:**\n\n"
    user_count = len(db["users"])
    app_count = len(db["app_links"])
    active_now = sum(1 for x in db["app_links"].values() if x.get("end_time", 0) > time.time())
    
    full_list += f"👥 عدد المستخدمين: `{user_count}`\n"
    full_list += f"⚡ عدد التطبيقات/الأجهزة: `{app_count}`\n"
    full_list += f"🟢 النشطين: `{active_now}`\n\n"
    
    for cid, data in db["app_links"].items():
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        rem_time = data.get("end_time", 0) - time.time()
        
        if data.get("banned"): stat = "🔴 محظور"
        elif rem_time > 0: stat = f"🟢 نشط ({int(rem_time/86400)} يوم)"
        else: stat = "⚪ منتهي"
        
        full_list += f"📦 التطبيق: `{pkg}`\n"
        full_list += f"🆔 المعرف (اضغط للنسخ):\n`{cid}`\n"
        full_list += f"🧑‍💻 المستخدم ID (اضغط للنسخ):\n`{data.get('telegram_id', 'غير معروف')}`\n"
        full_list += f"حالة الاشتراك: {stat}\n"
        full_list += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        
        # تجنب تجاوز طول رسالة تلجرام
        if len(full_list) > 3500:
            bot.send_message(m.chat.id, full_list, parse_mode="Markdown")
            full_list = ""
    
    if full_list: bot.send_message(m.chat.id, full_list, parse_mode="Markdown")

def process_gen_key(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "⚠️ خطأ! يرجى إرسال رقم فقط.")
    days = int(m.text)
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db = load_db(); db["vouchers"][code] = days; save_db(db)
    bot.send_message(m.chat.id, f"🎫 **تم إنشاء كود جديد:**\n\nالمدة: `{days}` يوم\nالكود: `{code}`", parse_mode="Markdown")

# --- [ لوحة المدير الرئيسية ] ---
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    active_now = sum(1 for x in db["app_links"].values() if x.get("end_time", 0) > time.time())
    msg = (f"👑 **إدارة نجم الإبداع**\n\n"
           f"👥 المستخدمين: `{len(db['users'])}`\n"
           f"⚡ الأجهزة: `{len(db['app_links'])}`\n"
           f"🟢 النشطين: `{active_now}`\n"
           f"🎫 الأكواد: `{len(db['vouchers'])}` \n")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 عرض وتفاصيل المشتركين", callback_data="list_all"),
        types.InlineKeyboardButton("🎫 توليد كود مخصص", callback_data="gen_key"),
        types.InlineKeyboardButton("🚫 حظر جهاز", callback_data="ban_op"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="unban_op"),
        types.InlineKeyboardButton("📢 إعلان تطبيق", callback_data="bc_app"),
        types.InlineKeyboardButton("📢 إعلان تلجرام", callback_data="bc_tele")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- [ منطق المستخدم المحدث ] ---

def user_dashboard(m):
    db = load_db()
    uid = str(m.chat.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps: return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة.")
    
    msg = "👤 **حالة اشتراكاتك:**\n"
    for cid in user_apps:
        data = db["app_links"][cid]
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        rem_time = data.get("end_time", 0) - time.time()
        status = f"✅ {int(rem_time/86400)} يوم" if rem_time > 0 else "❌ منتهي"
        if data.get("banned"): status = "🚫 محظور"
        msg += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📦 `{pkg}`\nStatus: {status}\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

def redeem_code_step(m):
    code = m.text.strip()
    db = load_db()
    if code not in db["vouchers"]:
        return bot.send_message(m.chat.id, "❌ الكود غير صحيح أو تم استخدامه.")
    
    uid = str(m.from_user.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps:
        return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة بحسابك.")
    
    # حفظ الكود مؤقتاً في الـ user data (بديل بسيط لتخزين مؤقت)
    db["users"][uid]["temp_code"] = code
    save_db(db)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for cid in user_apps:
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        markup.add(types.InlineKeyboardButton(f"📦 {pkg}", callback_data=f"redeem_select_{cid}"))
    
    bot.send_message(m.chat.id, "🛠️ **اختر التطبيق لتفعيل الكود عليه:**", reply_markup=markup)

def redeem_select_app(m, selected_cid):
    db = load_db()
    uid = str(m.chat.id)
    code = db["users"][uid].pop("temp_code", None)
    if not code or code not in db["vouchers"]:
        return bot.send_message(m.chat.id, "❌ خطأ في الكود أو انتهت الجلسة.")
    
    days = db["vouchers"].pop(code)
    db["app_links"][selected_cid]["end_time"] = max(time.time(), db["app_links"][selected_cid].get("end_time", 0)) + (days * 86400)
    save_db(db)
    bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم بنجاح على التطبيق المختار!")

def process_trial(m):
    db = load_db()
    uid = str(m.chat.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps:
        return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة بحسابك.")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for cid in user_apps:
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        markup.add(types.InlineKeyboardButton(f"📦 {pkg}", callback_data=f"trial_select_{cid}"))
    
    bot.send_message(m.chat.id, "🛠️ **اختر التطبيق لتفعيل التجربة المجانية عليه:**", reply_markup=markup)

def trial_select_app(m, selected_cid):
    db = load_db()
    data = db["app_links"][selected_cid]
    current_time = time.time()
    last_trial = data.get("trial_last_time", 0)
    
    if current_time - last_trial < 86400:  # 24 ساعة
        return bot.send_message(m.chat.id, "❌ يمكنك استخدام التجربة مرة واحدة فقط كل يوم.")
    
    data["trial_last_time"] = current_time
    data["end_time"] = max(current_time, data.get("end_time", 0)) + 7200  # إضافة ساعتين
    save_db(db)
    bot.send_message(m.chat.id, "✅ تم تفعيل ساعتين تجربة مجانية!")

def send_payment(m):
    db = load_db(); uid = str(m.chat.id)
    cid = db["users"].get(uid, {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ افتح التطبيق أولاً.")
    bot.send_invoice(m.chat.id, title="اشتراك 30 يوم", description=f"للحساب: {cid}", 
                     invoice_payload=f"pay_{cid}", provider_token="", currency="XTR",
                     prices=[types.LabeledPrice(label="VIP", amount=100)])

# --- [ وظائف مساعدة للإدارة ] ---
def do_bc_tele(m):
    db = load_db(); count = 0
    for uid in db["users"]:
        try: bot.send_message(uid, f"📢 **إشعار:**\n\n{m.text}"); count += 1
        except: pass
    bot.send_message(m.chat.id, f"✅ تم الإرسال لـ {count}")

def do_bc_app(m):
    db = load_db(); db["global_news"] = m.text; save_db(db)
    bot.send_message(m.chat.id, "✅ تم تحديث خبر التطبيق.")

def process_ban_unban(m, mode):
    db = load_db(); target = m.text.strip()
    if target in db["app_links"]:
        db["app_links"][target]["banned"] = (mode == "ban_op")
        save_db(db); bot.send_message(m.chat.id, "✅ تم التحديث.")
    else: bot.send_message(m.chat.id, "❌ المعرف غير موجود.")

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True) 

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db(); cid = m.successful_payment.invoice_payload.replace("pay_", "")
    current_end = max(time.time(), db["app_links"][cid].get("end_time", 0))
    db["app_links"][cid]["end_time"] = current_end + (30 * 86400)
    save_db(db); bot.send_message(m.chat.id, "✅ تم الشراء بنجاح!")

# --- [ التشغيل ] ---
def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
