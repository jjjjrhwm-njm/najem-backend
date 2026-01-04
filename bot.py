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
            return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً", "logs": [], "purchases": [], "referrals": {}}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: 
                db = json.load(f)
                defaults = {"global_news": "لا توجد أخبار حالياً", "vouchers": {}, "logs": [], "purchases": [], "referrals": {}}
                for k, v in defaults.items():
                    if k not in db: db[k] = v
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً", "logs": [], "purchases": [], "referrals": {}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4) 

def add_log(db, action, details):
    db["logs"].append({"time": time.time(), "action": action, "details": details})
    if len(db["logs"]) > 100: db["logs"] = db["logs"][-100:]
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
    if uid not in db["users"]: 
        db["users"][uid] = {"current_app": None, "first_name": m.from_user.first_name or "", "referrer": None, "referrals_count": 0, "referral_days": 0}
    
    args = m.text.split()
    referrer = None
    if len(args) > 1:
        if args[1].isdigit():  # Referral
            referrer = args[1]
            db["users"][uid]["referrer"] = referrer
        else:  # Link device
            cid = args[1]
            if cid not in db["app_links"]:
                db["app_links"][cid] = {"end_time": 0, "banned": False, "trial_last_time": 0, "telegram_id": uid}
            db["app_links"][cid]["telegram_id"] = uid
            db["users"][uid]["current_app"] = cid
            add_log(db, "link_device", f"User {uid} linked {cid}")
            save_db(db)
            bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**", parse_mode="Markdown")
            
            # Process referral reward if referrer exists
            if db["users"][uid]["referrer"]:
                referrer_uid = db["users"][uid]["referrer"]
                if referrer_uid in db["users"] and referrer_uid != uid:
                    referrer_cid = db["users"][referrer_uid].get("current_app")
                    if referrer_cid:
                        db["app_links"][referrer_cid]["end_time"] += 10 * 86400
                        db["users"][referrer_uid]["referrals_count"] += 1
                        db["users"][referrer_uid]["referral_days"] += 10
                        add_log(db, "referral_reward", f"Added 10 days to {referrer_uid} for referral {uid}")
                        try:
                            bot.send_message(referrer_uid, "🎉 **شخص جديد انضم من رابطك! +10 أيام أضيفت لاشتراكك!**")
                        except:
                            pass
                    save_db(db)
    
    save_db(db)
    show_main_menu(m.chat.id)

def show_main_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📱 قسم الاشتراكات", callback_data="section_subs"),
        types.InlineKeyboardButton("🔗 قسم الإحالات", callback_data="section_referrals"),
        types.InlineKeyboardButton("🛠 قسم الإعدادات", callback_data="section_settings")
    )
    bot.send_message(chat_id, "اختر القسم:", reply_markup=markup)

# --- [ معالجة ضغطات الأزرار ] ---
@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    bot.answer_callback_query(q.id)
    uid = str(q.from_user.id)
    db = load_db()

    if q.data == "section_subs":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
            types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy"),
            types.InlineKeyboardButton("🔄 تمديد اشتراك", callback_data="u_extend"),
            types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem")
        )
        bot.edit_message_reply_markup(q.message.chat.id, q.message.message_id, reply_markup=markup)
    elif q.data == "section_referrals":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🔗 رابط دعوتي وإحصائيات", callback_data="u_referrals")
        )
        bot.edit_message_reply_markup(q.message.chat.id, q.message.message_id, reply_markup=markup)
    elif q.data == "section_settings":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial")
        )
        bot.edit_message_reply_markup(q.message.chat.id, q.message.message_id, reply_markup=markup)
    elif q.data == "u_dashboard":
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
        parts = q.data.split("_", maxsplit=2)
        days = int(parts[1])
        cid = parts[2]
        send_invoice(q.message, cid, days)
    elif q.data == "u_extend":
        process_extend(q.message)
    elif q.data.startswith("extend_select_app_"):
        selected_cid = q.data.replace("extend_select_app_", "")
        process_buy_package(q.message, selected_cid)
    elif q.data == "u_referrals":
        show_referrals(q.message)
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
            msg = bot.send_message(q.message.chat.id, f"ارسل المعرف أو الاسم {action}:")
            bot.register_next_step_handler(msg, process_ban_unban, q.data)
        elif q.data == "admin_recharge":
            msg = bot.send_message(q.message.chat.id, "ارسل المعرف أو الاسم الذي تريد شحنه:")
            bot.register_next_step_handler(msg, process_recharge_cid)
        elif q.data == "admin_stats":
            show_advanced_stats(q.message)
        elif q.data == "admin_logs":
            show_logs(q.message)
        elif q.data == "admin_top_referrers":
            show_top_referrers(q.message)

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
        
        tg_id = data.get("telegram_id")
        name = db["users"].get(tg_id, {}).get("first_name", "غير معروف")
        
        full_list += f"📦 التطبيق: `{pkg}`\n🆔 المعرف: `{cid}`\nالاسم: `{name}`\nحالة الاشتراك: {stat}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
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
        types.InlineKeyboardButton("🚫 حظر جهاز", callback_data="ban_op"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="unban_op"),
        types.InlineKeyboardButton("📢 إعلان تطبيق", callback_data="bc_app"),
        types.InlineKeyboardButton("📢 إعلان تلجرام", callback_data="bc_tele"),
        types.InlineKeyboardButton("💰 شحن اشتراك", callback_data="admin_recharge"),
        types.InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats"),
        types.InlineKeyboardButton("🗒 سجل العمليات", callback_data="admin_logs"),
        types.InlineKeyboardButton("🏆 أفضل الداعين", callback_data="admin_top_referrers")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- [ ميزة شحن اشتراك من المدير بالاسم أو cid ] ---
def process_recharge_cid(m):
    target = m.text.strip()
    db = load_db()
    found = None
    for cid, data in db["app_links"].items():
        tg_id = data.get("telegram_id")
        name = db["users"].get(tg_id, {}).get("first_name", "")
        if cid == target or name == target:
            found = cid
            break
    if not found:
        return bot.send_message(m.chat.id, "❌ المعرف أو الاسم غير موجود.")
    
    db["temp_recharge"] = {"cid": found}
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
    save_db(db)
    bot.send_message(m.chat.id, f"✅ تم إضافة {days} يوم بنجاح على {cid}!")

# --- [ ميزة عرض الإحالات ] ---
def show_referrals(m):
    db = load_db()
    uid = str(m.chat.id)
    referral_link = f"https://t.me/{bot.get_me().username}?start={uid}"
    count = db["users"][uid].get("referrals_count", 0)
    days = db["users"][uid].get("referral_days", 0)
    msg = f"🔗 **رابط دعوتك:**\n`{referral_link}`\n\nعدد الإحالات: {count}\nإجمالي الأيام المكتسبة: {days}"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

# --- [ ميزة أفضل الداعين ] ---
def show_top_referrers(m):
    db = load_db()
    top = sorted(db["users"].items(), key=lambda x: x[1].get("referrals_count", 0), reverse=True)[:10]
    msg = "🏆 **أفضل 10 داعين:**\n\n"
    for uid, data in top:
        name = data.get("first_name", "غير معروف")
        count = data.get("referrals_count", 0)
        msg += f"- {name} ({uid}): {count} إحالات\n"
    bot.send_message(m.chat.id, msg)

# --- [ ميزة الحظر بالاسم أو cid ] ---
def process_ban_unban(m, mode):
    target = m.text.strip()
    db = load_db()
    found = None
    for cid, data in db["app_links"].items():
        tg_id = data.get("telegram_id")
        name = db["users"].get(tg_id, {}).get("first_name", "")
        if cid == target or name == target:
            found = cid
            break
    if not found:
        return bot.send_message(m.chat.id, "❌ المعرف أو الاسم غير موجود.")
    
    db["app_links"][found]["banned"] = (mode == "ban_op")
    save_db(db)
    bot.send_message(m.chat.id, "✅ تم التحديث.")

# --- [ الإحصائيات والسجل - افتراضي ] ---
def show_advanced_stats(m):
    db = load_db()
    msg = "📊 **إحصائيات:**\n\n"  # أضف إحصائيات كما في السابق
    bot.send_message(m.chat.id, msg)

def show_logs(m):
    db = load_db()
    if not db["logs"]: return bot.send_message(m.chat.id, "لا توجد سجلات.")
    msg = "🗒 **سجل العمليات:**\n\n"  # أضف السجلات
    bot.send_message(m.chat.id, msg)

# --- [ باقي الوظائف كما في الكود الأصلي - افتراضي ] ---
# (user_dashboard, redeem_code_step, redeem_select_app, process_trial, trial_select_app, send_payment, do_bc_tele, do_bc_app, process_ban_unban, checkout, pay_success, run)

def user_dashboard(m):
    # كما في الأصل
    pass

# أكمل الباقي كما في الكود الأصلي

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
