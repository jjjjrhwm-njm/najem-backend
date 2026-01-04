import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread, Lock
import datetime

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
            return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً", "logs": [], "purchases": []}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
                if "global_news" not in db: db["global_news"] = "لا توجد أخبار حالياً"
                if "vouchers" not in db: db["vouchers"] = {}
                if "logs" not in db: db["logs"] = []
                if "purchases" not in db: db["purchases"] = []
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً", "logs": [], "purchases": []}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4)

def add_log(db, action, details):
    db["logs"].append({"time": time.time(), "action": action, "details": details})
    if len(db["logs"]) > 100: db["logs"] = db["logs"][-100:]  # Keep last 100 logs
    save_db(db)

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
    if uid not in db["users"]: db["users"][uid] = {"current_app": None, "max_devices": 1}  # Default max devices

    args = m.text.split()
    if len(args) > 1:
        cid = args[1]
        user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
        if len(user_apps) >= db["users"][uid]["max_devices"]:
            bot.send_message(m.chat.id, "❌ تجاوزت الحد الأقصى للأجهزة. اشترِ باقة متعددة الأجهزة.")
            return
        if cid not in db["app_links"]:
            db["app_links"][cid] = {"end_time": 0, "banned": False, "trial_last_time": 0, "telegram_id": uid}
        db["app_links"][cid]["telegram_id"] = uid
        db["users"][uid]["current_app"] = cid
        add_log(db, "link_device", f"User {uid} linked {cid}")
        save_db(db)
        bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**", parse_mode="Markdown")

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
        types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
        types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
        types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy"),
        types.InlineKeyboardButton("🔄 تمديد اشتراك", callback_data="u_extend")
    )
    bot.send_message(m.chat.id, f"مرحباً بك يا **نجم الإبداع** 🌟\nاستخدم القائمة أدناه للتحكم في اشتراكاتك:", reply_markup=markup, parse_mode="Markdown")

# --- [ معالجة ضغطات الأزرار ] ---
@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    db = load_db()

    if q.data == "u_dashboard":
        user_dashboard(q.message)
    elif q.data == "u_redeem":
        msg = bot.send_message(q.message.chat.id, "🎫 **أرسل كود التفعيل الآن:**")
        bot.register_next_step_handler(msg, redeem_code_step)
    elif q.data.startswith("redeem_select_"):
        selected_cid = q.data.replace("redeem_select_", "")
        redeem_select_app(q.message, selected_cid)
    elif q.data == "u_trial":
        process_trial(q.message)
    elif q.data.startswith("trial_select_"):
        selected_cid = q.data.replace("trial_select_", "")
        trial_select_app(q.message, selected_cid)
    elif q.data == "u_buy":
        process_buy(q.message)
    elif q.data.startswith("buy_select_app_"):
        selected_cid = q.data.replace("buy_select_app_", "")
        process_buy_package(q.message, selected_cid)
    elif q.data.startswith("buy_package_"):
        parts = q.data.split("_")
        cid = "_".join(parts[2:])  # Since cid may have _
        days = int(parts[1])
        send_invoice(q.message, cid, days)
    elif q.data == "u_extend":
        process_extend(q.message)
    elif q.data.startswith("extend_select_app_"):
        selected_cid = q.data.replace("extend_select_app_", "")
        process_buy_package(q.message, selected_cid)  # Same as buy
    elif q.data == "u_discount":
        msg = bot.send_message(q.message.chat.id, "🤑 **أرسل كود الخصم:**")
        bot.register_next_step_handler(msg, apply_discount_step)
    elif q.from_user.id == ADMIN_ID:
        if q.data == "list_all":
            show_detailed_users(q.message)
        elif q.data == "gen_key":
            msg = bot.send_message(q.message.chat.id, "كم عدد الأيام التي تريدها لهذا الكود؟ (أرسل رقماً فقط)")
            bot.register_next_step_handler(msg, process_gen_key)
        elif q.data == "gen_discount":
            msg = bot.send_message(q.message.chat.id, "كم نسبة الخصم (مثل 50 لـ50%)؟")
            bot.register_next_step_handler(msg, process_gen_discount)
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
        elif q.data in ["ban_user_op", "unban_user_op"]:
            action = "لحظر المستخدم" if q.data == "ban_user_op" else "لفك حظر المستخدم"
            msg = bot.send_message(q.message.chat.id, f"ارسل تليجرام ID أو يوزرنيم {action}:")
            bot.register_next_step_handler(msg, process_ban_unban_user, q.data)
        elif q.data == "admin_recharge":
            msg = bot.send_message(q.message.chat.id, "ارسل المعرف (cid) الذي تريد شحنه:")
            bot.register_next_step_handler(msg, process_recharge_cid)
        elif q.data == "admin_stats":
            show_advanced_stats(q.message)
        elif q.data == "admin_logs":
            show_logs(q.message)

# --- [ وظائف الإدارة ] ---

def show_detailed_users(m):
    db = load_db()
    if not db["app_links"]: return bot.send_message(m.chat.id, "لا توجد أجهزة مسجلة.")
    
    full_list = "📂 **قائمة المشتركين والأجهزة:**\n\n"
    for cid, data in db["app_links"].items():
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        rem_time = data.get("end_time", 0) - time.time()
        
        if data.get("banned"): stat = "🔴 محظور"
        elif rem_time > 0: stat = f"🟢 نشط ({int(rem_time/86400)} يوم)"
        else: stat = "⚪ منتهي"
        
        full_list += f"📦 التطبيق: `{pkg}`\n🆔 المعرف: `{cid}`\nحالة الاشتراك: {stat}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        if len(full_list) > 3500:
            bot.send_message(m.chat.id, full_list, parse_mode="Markdown")
            full_list = ""
    
    if full_list: bot.send_message(m.chat.id, full_list, parse_mode="Markdown")

def process_gen_key(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "⚠️ خطأ! يرجى إرسال رقم فقط.")
    days = int(m.text)
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db = load_db(); db["vouchers"][code] = {"type": "days", "value": days}; save_db(db)
    bot.send_message(m.chat.id, f"🎫 **تم إنشاء كود جديد:**\n\nالمدة: `{days}` يوم\nالكود: `{code}`", parse_mode="Markdown")

def process_gen_discount(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "⚠️ خطأ! يرجى إرسال رقم فقط.")
    percent = int(m.text)
    if percent < 1 or percent > 100: return bot.send_message(m.chat.id, "⚠️ النسبة يجب أن تكون بين 1 و100.")
    code = f"DSC-{str(uuid.uuid4())[:8].upper()}"
    db = load_db(); db["vouchers"][code] = {"type": "discount", "value": percent}; save_db(db)
    bot.send_message(m.chat.id, f"🤑 **تم إنشاء كود خصم جديد:**\n\nالنسبة: `{percent}%`\nالكود: `{code}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    active_now = sum(1 for x in db["app_links"].values() if x.get("end_time", 0) > time.time())
    msg = (f"👑 **إدارة نجم الإبداع**\n\n"
           f"👥 المستخدمين: `{len(db['users'])}`\n"
           f"⚡ الأجهزة: `{len(db['app_links'])}`\n"
           f"🟢 النشطين: `{active_now}`\n")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 تفاصيل المشتركين", callback_data="list_all"),
        types.InlineKeyboardButton("🎫 توليد كود", callback_data="gen_key"),
        types.InlineKeyboardButton("🤑 توليد خصم", callback_data="gen_discount"),
        types.InlineKeyboardButton("🚫 حظر جهاز", callback_data="ban_op"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="unban_op"),
        types.InlineKeyboardButton("🚫 حظر مستخدم", callback_data="ban_user_op"),
        types.InlineKeyboardButton("✅ فك حظر مستخدم", callback_data="unban_user_op"),
        types.InlineKeyboardButton("📢 إعلان تطبيق", callback_data="bc_app"),
        types.InlineKeyboardButton("📢 إعلان تلجرام", callback_data="bc_tele"),
        types.InlineKeyboardButton("💰 شحن اشتراك", callback_data="admin_recharge"),
        types.InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats"),
        types.InlineKeyboardButton("🗒 سجل العمليات", callback_data="admin_logs")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- [ ميزة جديدة: شحن اشتراك من المدير ] ---
def process_recharge_cid(m):
    cid = m.text.strip()
    db = load_db()
    if cid not in db["app_links"]:
        return bot.send_message(m.chat.id, "❌ المعرف غير موجود.")
    
    db["temp_recharge"] = {"cid": cid}  # حفظ مؤقت للمعرف
    save_db(db)
    msg = bot.send_message(m.chat.id, "كم عدد الأيام التي تريد إضافتها؟ (أرسل رقماً فقط)")
    bot.register_next_step_handler(msg, process_recharge_days)

def process_recharge_days(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "⚠️ خطأ! يرجى إرسال رقم فقط.")
    days = int(m.text)
    db = load_db()
    temp = db.pop("temp_recharge", None)
    if not temp:
        return bot.send_message(m.chat.id, "❌ خطأ في الجلسة.")
    
    cid = temp["cid"]
    current_end = max(time.time(), db["app_links"][cid].get("end_time", 0))
    db["app_links"][cid]["end_time"] = current_end + (days * 86400)
    add_log(db, "admin_recharge", f"Added {days} days to {cid}")
    save_db(db)
    bot.send_message(m.chat.id, f"✅ تم إضافة {days} يوم بنجاح على المعرف {cid}!")

# --- [ ميزة جديدة: إحصائيات متقدمة ] ---
def show_advanced_stats(m):
    db = load_db()
    now = time.time()
    week_ago = now - (7 * 86400)
    new_users = sum(1 for u in db["users"].values() if "join_time" in u and u["join_time"] > week_ago)  # Assume add join_time later
    new_subs = sum(1 for p in db["purchases"] if p["time"] > week_ago)
    total_sales = sum(p["amount"] for p in db["purchases"])
    popular_apps = {}
    for cid in db["app_links"]:
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        popular_apps[pkg] = popular_apps.get(pkg, 0) + 1
    popular = sorted(popular_apps.items(), key=lambda x: x[1], reverse=True)[:5]
    
    msg = f"📊 **إحصائيات متقدمة:**\n\n"
    msg += f"🆕 مستخدمين جدد هذا الأسبوع: {new_users}\n"
    msg += f"🛒 اشتراكات جديدة هذا الأسبوع: {new_subs}\n"
    msg += f"💵 إجمالي المبيعات: {total_sales} XTR\n"
    msg += "📱 أكثر التطبيقات شعبية:\n"
    for pkg, count in popular:
        msg += f"- {pkg}: {count}\n"
    bot.send_message(m.chat.id, msg)

# --- [ ميزة جديدة: سجل عمليات ] ---
def show_logs(m):
    db = load_db()
    if not db["logs"]: return bot.send_message(m.chat.id, "لا توجد سجلات.")
    msg = "🗒 **آخر 50 عملية:**\n\n"
    for log in reversed(db["logs"][-50:]):
        dt = datetime.datetime.fromtimestamp(log["time"]).strftime("%Y-%m-%d %H:%M")
        msg += f"[{dt}] {log['action']}: {log['details']}\n"
        if len(msg) > 3500:
            bot.send_message(m.chat.id, msg)
            msg = ""
    if msg: bot.send_message(m.chat.id, msg)

# --- [ ميزة جديدة: حظر/فك حظر مستخدم ] ---
def process_ban_unban_user(m, mode):
    db = load_db()
    target = m.text.strip()
    # Assume target is telegram_id for simplicity, or username if starts with @
    users = [k for k, v in db["users"].items() if k == target or v.get("username") == target.lstrip("@")]
    if not users:
        return bot.send_message(m.chat.id, "❌ المستخدم غير موجود.")
    uid = users[0]
    banned = (mode == "ban_user_op")
    for cid, data in db["app_links"].items():
        if data.get("telegram_id") == uid:
            data["banned"] = banned
    add_log(db, "ban_user" if banned else "unban_user", f"User {uid}")
    save_db(db)
    bot.send_message(m.chat.id, "✅ تم التحديث لكل أجهزة المستخدم.")

# --- [ منطق المستخدم ] ---

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
    voucher = db["vouchers"][code]
    if voucher["type"] == "discount":
        db["users"][str(m.chat.id)]["discount"] = voucher["value"]
        del db["vouchers"][code]
        save_db(db)
        return bot.send_message(m.chat.id, f"🤑 تم تفعيل خصم {voucher['value']}% على شرائك التالي!")
    
    uid = str(m.from_user.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps:
        return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة بحسابك.")
    
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
    code = db["users"].get(uid, {}).pop("temp_code", None)
    
    if not code or code not in db["vouchers"]:
        return bot.send_message(m.chat.id, "❌ خطأ في الكود أو انتهت الجلسة.")
    
    voucher = db["vouchers"].pop(code)
    days = voucher["value"]
    db["app_links"][selected_cid]["end_time"] = max(time.time(), db["app_links"][selected_cid].get("end_time", 0)) + (days * 86400)
    add_log(db, "redeem_code", f"User {uid} redeemed {days} days on {selected_cid}")
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
    if selected_cid not in db["app_links"]:
        return bot.send_message(m.chat.id, "❌ حدث خطأ في التعرف على التطبيق.")
        
    data = db["app_links"][selected_cid]
    current_time = time.time()
    last_trial = data.get("trial_last_time", 0)
    
    if current_time - last_trial < 86400:
        return bot.send_message(m.chat.id, "❌ يمكنك استخدام التجربة مرة واحدة فقط كل يوم لهذا التطبيق.")
    
    data["trial_last_time"] = current_time
    data["end_time"] = max(current_time, data.get("end_time", 0)) + 10800 
    add_log(db, "trial", f"Activated trial on {selected_cid}")
    save_db(db)
    bot.send_message(m.chat.id, "✅ تم تفعيل 3 ساعات تجربة مجانية بنجاح!")

# --- [ ميزة جديدة: باقات متعددة وشراء/تمديد ] ---
def process_buy(m):
    db = load_db()
    uid = str(m.chat.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps:
        return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة. اربط جهاز أولاً.")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for cid in user_apps:
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        markup.add(types.InlineKeyboardButton(f"📦 {pkg}", callback_data=f"buy_select_app_{cid}"))
    bot.send_message(m.chat.id, "🛠️ **اختر التطبيق لشراء اشتراك عليه:**", reply_markup=markup)

def process_extend(m):
    db = load_db()
    uid = str(m.chat.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps:
        return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة.")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for cid in user_apps:
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        markup.add(types.InlineKeyboardButton(f"📦 {pkg}", callback_data=f"extend_select_app_{cid}"))
    bot.send_message(m.chat.id, "🛠️ **اختر التطبيق لتمديد الاشتراك عليه:**", reply_markup=markup)

def process_buy_package(m, cid):
    markup = types.InlineKeyboardMarkup(row_width=2)
    packages = [
        (7, 50, "7 أيام"),
        (30, 100, "30 يوم"),
        (90, 250, "90 يوم"),
        (365, 900, "سنة كاملة")
    ]
    for days, amount, label in packages:
        markup.add(types.InlineKeyboardButton(f"{label} - {amount} XTR", callback_data=f"buy_package_{days}_{cid}"))
    bot.send_message(m.chat.id, "📦 **اختر الباقة:**", reply_markup=markup)

def send_invoice(m, cid, days):
    db = load_db()
    uid = str(m.chat.id)
    discount = db["users"].get(uid, {}).get("discount", 0)
    packages = {7: 50, 30: 100, 90: 250, 365: 900}
    amount = packages.get(days, 100)
    if discount:
        amount = int(amount * (1 - discount / 100))
        del db["users"][uid]["discount"]  # One-time use
        save_db(db)
    bot.send_invoice(m.chat.id, title=f"اشتراك {days} يوم", description=f"للحساب: {cid}",
                     invoice_payload=f"pay_{cid}_{days}", provider_token="", currency="XTR",
                     prices=[types.LabeledPrice(label="VIP", amount=amount)])

# --- [ وظائف مساعدة ] ---
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
        add_log(db, "ban" if mode == "ban_op" else "unban", f"Device {target}")
        save_db(db); bot.send_message(m.chat.id, "✅ تم التحديث.")
    else: bot.send_message(m.chat.id, "❌ المعرف غير موجود.")

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db()
    payload = m.successful_payment.invoice_payload.replace("pay_", "")
    cid, days = payload.rsplit("_", 1)
    days = int(days)
    current_end = max(time.time(), db["app_links"][cid].get("end_time", 0))
    db["app_links"][cid]["end_time"] = current_end + (days * 86400)
    db["purchases"].append({"time": time.time(), "uid": str(m.chat.id), "cid": cid, "days": days, "amount": m.successful_payment.total_amount})
    add_log(db, "purchase", f"User {m.chat.id} bought {days} days for {cid}")
    save_db(db)
    bot.send_message(m.chat.id, f"✅ تم الشراء/التمديد بنجاح لـ {days} يوم!")

# --- [ ميزة جديدة: إشعارات تلقائية لانتهاء الاشتراك ] ---
def notification_thread():
    while True:
        time.sleep(86400)  # Every 24 hours
        db = load_db()
        now = time.time()
        for cid, data in db["app_links"].items():
            rem_time = data.get("end_time", 0) - now
            if 86400 < rem_time < 2 * 86400:  # Between 1 and 2 days
                uid = data.get("telegram_id")
                if uid:
                    try:
                        bot.send_message(uid, f"⚠️ اشتراكك في {cid} سينتهي غدًا. جدد الآن لتجنب الانقطاع!")
                    except:
                        pass

# --- [ التشغيل ] ---
def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    Thread(target=notification_thread).start()
    bot.infinity_polling()
