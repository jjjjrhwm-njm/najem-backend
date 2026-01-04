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
CHANNEL_USERNAME = "@your_channel_username"  # غيّر هذا إلى يوزر القناة بدون @ إذا كان private، أو مع @ إذا public

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock()

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE):
            return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً", "logs": [], "purchases": [], "channel_bonus_claimed": []}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
                defaults = {"global_news": "لا توجد أخبار حالياً", "vouchers": {}, "logs": [], "purchases": [], "channel_bonus_claimed": []}
                for k, v in defaults.items():
                    if k not in db: db[k] = v
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً", "logs": [], "purchases": [], "channel_bonus_claimed": []}

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

# --- [ فحص عضوية القناة ] ---
def is_member_of_channel(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# --- [ واجهة البوت - البداية ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    if uid not in db["users"]:
        db["users"][uid] = {"current_app": None, "max_devices": 1}

    args = m.text.split()
    if len(args) > 1:
        cid = args[1]
        user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
        if len(user_apps) >= db["users"][uid]["max_devices"]:
            bot.send_message(m.chat.id, "❌ تجاوزت الحد الأقصى للأجهزة.")
            return
        if cid not in db["app_links"]:
            db["app_links"][cid] = {"end_time": 0, "banned": False, "trial_last_time": 0, "telegram_id": uid}
        db["app_links"][cid]["telegram_id"] = uid
        db["users"][uid]["current_app"] = cid
        add_log(db, "link_device", f"User {uid} linked {cid}")
        save_db(db)
        bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**", parse_mode="Markdown")

        # ميزة جديدة: هدية الانضمام للقناة
        if is_member_of_channel(m.from_user.id) and uid not in db["channel_bonus_claimed"]:
            db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (3 * 86400)
            db["channel_bonus_claimed"].append(uid)
            save_db(db)
            bot.send_message(m.chat.id, "🎁 **مكافأة انضمامك للقناة!**\nتم إضافة 3 أيام اشتراك مجاني تلقائيًا على جهازك!")

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
    bot.answer_callback_query(q.id)  # مهم جدًا لإخفاء التحميل
    uid = str(q.from_user.id)
    db = load_db()

    if q.data == "u_dashboard":
        user_dashboard(q.message)
    elif q.data == "u_redeem":
        msg = bot.send_message(q.message.chat.id, "🎫 **أرسل كود التفعيل الآن:**")
        bot.register_next_step_handler(msg, redeem_code_step)
    elif q.data.startswith("redeem_select_"):
        selected_cid = q.data[len("redeem_select_"):]
        redeem_select_app(q.message, selected_cid)
    elif q.data == "u_trial":
        process_trial(q.message)
    elif q.data.startswith("trial_select_"):
        selected_cid = q.data[len("trial_select_"):]
        trial_select_app(q.message, selected_cid)
    elif q.data == "u_buy":
        process_buy(q.message)
    elif q.data.startswith("buy_select_app_"):
        selected_cid = q.data[len("buy_select_app_"):]
        process_buy_package(q.message, selected_cid)
    elif q.data.startswith("buy_package_"):
        # تم إصلاح المشكلة هنا باستخدام split مع maxsplit
        parts = q.data.split("_", 3)  # مهم: maxsplit=3 عشان الـ cid ما يتقسم
        if len(parts) < 4: return
        days = int(parts[2])
        cid = parts[3]
        send_invoice(q.message, cid, days)
    elif q.data == "u_extend":
        process_extend(q.message)
    elif q.data.startswith("extend_select_app_"):
        selected_cid = q.data[len("extend_select_app_"):]
        process_buy_package(q.message, selected_cid)
    elif q.data == "u_discount":
        msg = bot.send_message(q.message.chat.id, "🤑 **أرسل كود الخصم:**")
        bot.register_next_step_handler(msg, apply_discount_step)
    elif q.from_user.id == ADMIN_ID:
        if q.data == "list_all":
            show_detailed_users(q.message)
        elif q.data == "gen_key":
            msg = bot.send_message(q.message.chat.id, "كم عدد الأيام التي تريدها لهذا الكود؟")
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
            msg = bot.send_message(q.message.chat.id, f"ارسل تليجرام ID {action}:")
            bot.register_next_step_handler(msg, process_ban_unban_user, q.data)
        elif q.data == "admin_recharge":
            msg = bot.send_message(q.message.chat.id, "ارسل المعرف (cid) الذي تريد شحنه:")
            bot.register_next_step_handler(msg, process_recharge_cid)
        elif q.data == "admin_stats":
            show_advanced_stats(q.message)
        elif q.data == "admin_logs":
            show_logs(q.message)

# باقي الدوال زي ما هي (user_dashboard, redeem_code_step, إلخ)... نفس الكود السابق بدون تغيير

# --- [ باقي الكود كما هو (مختصر للتوفير) ] ---
# (جميع الدوال الأخرى نفس اللي في النسخة السابقة: user_dashboard, redeem_code_step, trial, process_buy, process_extend, process_buy_package, send_invoice, pay_success, إلخ)

# --- [ التشغيل ] ---
def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    Thread(target=notification_thread).start()  # إذا كنت حاط الإشعارات
    bot.infinity_polling()
