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
    if uid not in db["users"]: db["users"][uid] = {"current_app": None, "temp_target": None}
    
    args = m.text.split()
    if len(args) > 1:
        cid = args[1]
        if cid not in db["app_links"]:
            db["app_links"][cid] = {"end_time": 0, "banned": False, "trial_used": False, "telegram_id": uid}
        db["app_links"][cid]["telegram_id"] = uid
        db["users"][uid]["current_app"] = cid
        save_db(db)
        bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**", parse_mode="Markdown")

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
        types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem_select"),
        types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
        types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy")
    )
    bot.send_message(m.chat.id, f"مرحباً بك يا **نجم الإبداع** 🌟\nإدارة اشتراكاتك بكل سهولة:", reply_markup=markup, parse_mode="Markdown")

# --- [ معالجة ضغطات الأزرار ] ---
@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    db = load_db()

    # --- خيارات المستخدم ---
    if q.data == "u_dashboard":
        user_dashboard(q.message)
    
    elif q.data == "u_redeem_select":
        # عرض قائمة تطبيقات المستخدم ليختار منها
        user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
        if not user_apps: return bot.send_message(q.message.chat.id, "❌ ليس لديك تطبيقات مرتبطة.")
        
        markup = types.InlineKeyboardMarkup()
        for cid in user_apps:
            pkg = cid.split('_', 1)[-1].replace("_", ".")
            markup.add(types.InlineKeyboardButton(f"📦 {pkg}", callback_data=f"sel_{cid}"))
        bot.send_message(q.message.chat.id, "اختر التطبيق الذي تريد تفعيل الكود له:", reply_markup=markup)

    elif q.data.startswith("sel_"):
        target_cid = q.data.replace("sel_", "")
        db["users"][uid]["temp_target"] = target_cid
        save_db(db)
        msg = bot.send_message(q.message.chat.id, "🎫 **أرسل كود التفعيل الآن لهذا التطبيق:**")
        bot.register_next_step_handler(msg, redeem_final)

    elif q.data == "u_trial":
        process_trial(q.message)
    elif q.data == "u_buy":
        send_payment(q.message)

    # --- خيارات المدير (نجم1) ---
    elif q.from_user.id == ADMIN_ID:
        if q.data == "list_all":
            show_detailed_users(q.message)
        elif q.data == "gen_key":
            msg = bot.send_message(q.message.chat.id, "كم عدد الأيام للكود؟ (أرسل رقم فقط)")
            bot.register_next_step_handler(msg, process_gen_key)
        elif q.data == "add_manual":
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("👤 لجهاز محدد", callback_data="add_one"),
                       types.InlineKeyboardButton("🌍 للجميع", callback_data="add_all"))
            bot.send_message(q.message.chat.id, "إضافة وقت يدوي لمن؟", reply_markup=markup)
        elif q.data == "add_one":
            msg = bot.send_message(q.message.chat.id, "ارسل معرف الجهاز (ID):")
            bot.register_next_step_handler(msg, admin_add_time_target)
        elif q.data == "add_all":
            msg = bot.send_message(q.message.chat.id, "ارسل الوقت للإضافة للجميع بالصيغة (رقم+نوع)\nمثال: `30d` لـ 30 يوم أو `2h` لساعتين", parse_mode="Markdown")
            bot.register_next_step_handler(msg, admin_add_all_confirm)
        elif q.data in ["ban_op", "unban_op"]:
            action = "لحظره" if q.data == "ban_op" else "لفك حظره"
            msg = bot.send_message(q.message.chat.id, f"ارسل المعرف {action}:")
            bot.register_next_step_handler(msg, process_ban_unban, q.data)
        elif q.data == "bc_app":
            msg = bot.send_message(q.message.chat.id, "ارسل الخبر الجديد للتطبيق:")
            bot.register_next_step_handler(msg, do_bc_app)
        elif q.data == "bc_tele":
            msg = bot.send_message(q.message.chat.id, "ارسل الإذاعة للتلجرام:")
            bot.register_next_step_handler(msg, do_bc_tele)

# --- [ وظائف الإدارة ] ---

def admin_add_time_target(m):
    target = m.text.strip()
    db = load_db()
    if target not in db["app_links"]: return bot.send_message(m.chat.id, "❌ المعرف غير موجود.")
    msg = bot.send_message(m.chat.id, f"كم تريد الإضافة للمعرف `{target}`؟\nاكتب مثلاً `1d` ليوم أو `5h` لخمس ساعات.", parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_apply_time, target)

def admin_apply_time(m, target):
    time_str = m.text.lower()
    seconds = parse_time_string(time_str)
    if seconds == 0: return bot.send_message(m.chat.id, "⚠️ صيغة وقت غير صحيحة. استخدم d للأيام و h للساعات.")
    
    db = load_db()
    current_end = max(time.time(), db["app_links"][target].get("end_time", 0))
    db["app_links"][target]["end_time"] = current_end + seconds
    save_db(db)
    bot.send_message(m.chat.id, f"✅ تم إضافة `{time_str}` للمعرف بنجاح.", parse_mode="Markdown")

def admin_add_all_confirm(m):
    time_str = m.text.lower()
    seconds = parse_time_string(time_str)
    if seconds == 0: return bot.send_message(m.chat.id, "⚠️ صيغة خاطئة.")
    
    db = load_db()
    for cid in db["app_links"]:
        curr = max(time.time(), db["app_links"][cid].get("end_time", 0))
        db["app_links"][cid]["end_time"] = curr + seconds
    save_db(db)
    bot.send_message(m.chat.id, f"✅ تم إضافة `{time_str}` لجميع الأجهزة المشتركة!", parse_mode="Markdown")

def parse_time_string(s):
    try:
        if s.endswith('d'): return int(s[:-1]) * 86400
        if s.endswith('h'): return int(s[:-1]) * 3600
        return 0
    except: return 0

# --- [ لوحة المدير الرئيسية ] ---
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    msg = f"👑 **لوحة إدارة نجم الإبداع**\n\n👥 مستخدمين: `{len(db['users'])}` | ⚡ أجهزة: `{len(db['app_links'])}`"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 قائمة المشتركين", callback_data="list_all"),
        types.InlineKeyboardButton("🎫 توليد كود مخصص", callback_data="gen_key"),
        types.InlineKeyboardButton("🎁 إضافة وقت يدوي", callback_data="add_manual"),
        types.InlineKeyboardButton("🚫 حظر جهاز", callback_data="ban_op"),
        types.InlineKeyboardButton("📢 إذاعة تطبيق", callback_data="bc_app"),
        types.InlineKeyboardButton("📢 إذاعة تلجرام", callback_data="bc_tele")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- [ منطق المستخدم ] ---

def redeem_final(m):
    code = m.text.strip()
    db = load_db()
    uid = str(m.from_user.id)
    target_cid = db["users"].get(uid, {}).get("temp_target")
    
    if not target_cid: return bot.send_message(m.chat.id, "❌ حدث خطأ، اختر التطبيق مرة أخرى.")
    
    if code in db["vouchers"]:
        days = db["vouchers"].pop(code)
        # ميزة تراكم الوقت: نأخذ الوقت الأكبر بين (الآن) و (وقت انتهاء الاشتراك الحالي) ونضيف عليه
        current_end = max(time.time(), db["app_links"][target_cid].get("end_time", 0))
        db["app_links"][target_cid]["end_time"] = current_end + (days * 86400)
        save_db(db)
        bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم للتطبيق بنجاح!\nوقتك الجديد ينتهي بعد {int((db['app_links'][target_cid]['end_time'] - time.time())/86400)} يوم.")
    else:
        bot.send_message(m.chat.id, "❌ الكود غير صحيح أو مستخدم.")

def user_dashboard(m):
    db = load_db(); uid = str(m.chat.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps: return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات.")
    
    msg = "👤 **حالة اشتراكاتك:**\n"
    for cid in user_apps:
        data = db["app_links"][cid]
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        rem = data.get("end_time", 0) - time.time()
        status = f"✅ {int(rem/86400)} يوم" if rem > 0 else "❌ منتهي"
        if data.get("banned"): status = "🚫 محظور"
        msg += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📦 `{pkg}`\nالحالة: {status}\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

# بقية الوظائف الأصلية (show_detailed_users, process_gen_key, etc.) بدون تغيير في منطقها
def show_detailed_users(m):
    db = load_db()
    if not db["app_links"]: return bot.send_message(m.chat.id, "لا توجد أجهزة.")
    full_list = "📂 **قائمة الأجهزة المشتركة:**\n\n"
    for cid, data in db["app_links"].items():
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        rem = data.get("end_time", 0) - time.time()
        stat = "🟢" if rem > 0 else "⚪"
        if data.get("banned"): stat = "🔴"
        full_list += f"{stat} `{cid}`\n📦 {pkg}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    bot.send_message(m.chat.id, full_list, parse_mode="Markdown")

def process_gen_key(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "رقم فقط!")
    days = int(m.text)
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db = load_db(); db["vouchers"][code] = days; save_db(db)
    bot.send_message(m.chat.id, f"🎫 كود `{days}` يوم:\n`{code}`", parse_mode="Markdown")

def do_bc_tele(m):
    db = load_db(); count = 0
    for uid in db["users"]:
        try: bot.send_message(uid, f"📢 **إشعار:**\n\n{m.text}"); count += 1
        except: pass
    bot.send_message(m.chat.id, f"✅ تم الإرسال لـ {count}")

def do_bc_app(m):
    db = load_db(); db["global_news"] = m.text; save_db(db)
    bot.send_message(m.chat.id, "✅ تم التحديث.")

def process_ban_unban(m, mode):
    db = load_db(); target = m.text.strip()
    if target in db["app_links"]:
        db["app_links"][target]["banned"] = (mode == "ban_op")
        save_db(db); bot.send_message(m.chat.id, "✅ تم التحديث.")
    else: bot.send_message(m.chat.id, "❌ المعرف غير موجود.")

def process_trial(m):
    db = load_db(); cid = db["users"].get(str(m.chat.id), {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    if db["app_links"][cid].get("trial_used"): bot.send_message(m.chat.id, "❌ استخدمت التجربة.")
    else:
        db["app_links"][cid].update({"trial_used": True, "end_time": time.time() + 7200})
        save_db(db); bot.send_message(m.chat.id, "✅ تم تفعيل ساعتين تجربة!")

def send_payment(m):
    db = load_db(); uid = str(m.chat.id)
    cid = db["users"].get(uid, {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ افتح التطبيق أولاً.")
    bot.send_invoice(m.chat.id, title="اشتراك 30 يوم", description=f"للحساب: {cid}", 
                     invoice_payload=f"pay_{cid}", provider_token="", currency="XTR",
                     prices=[types.LabeledPrice(label="VIP", amount=100)])

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True) 

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db(); cid = m.successful_payment.invoice_payload.replace("pay_", "")
    current_end = max(time.time(), db["app_links"][cid].get("end_time", 0))
    db["app_links"][cid]["end_time"] = current_end + (30 * 86400)
    save_db(db); bot.send_message(m.chat.id, "✅ تم الشراء بنجاح!")

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
