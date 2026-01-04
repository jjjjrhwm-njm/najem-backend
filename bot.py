import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread, Lock 

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
CHANNEL_ID = "@jrhwm0njm"  # معرف قناتك للهدية
DATA_FILE = "master_data.json" 

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock() 

# باقات الاشتراك (الأيام : السعر بالنجوم XTR)
SUB_PLANS = {
    "7": 30,
    "30": 100,
    "90": 250,
    "365": 800
}

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): 
            return {"users": {}, "app_links": {}, "vouchers": {}, "coupons": {}, "logs": [], "global_news": "لا توجد أخبار"}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: 
                db = json.load(f)
                # ضمان وجود المفاتيح الجديدة
                for key in ["coupons", "logs", "global_news"]:
                    if key not in db: db[key] = [] if key == "logs" else {}
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "coupons": {}, "logs": [], "global_news": "لا توجد أخبار"}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4) 

def add_log(msg):
    db = load_db()
    db["logs"].append(f"[{time.ctime()}] {msg}")
    if len(db["logs"]) > 100: db["logs"].pop(0)
    save_db(db)

# فحص الانضمام للقناة
def is_member(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except: return False

# --- [ واجهة API للمطورين ] ---
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

# --- [ واجهة البوت - البداية ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    username = f"@{m.from_user.username}" if m.from_user.username else m.from_user.first_name
    
    # إعداد بيانات المستخدم الجديد
    if uid not in db["users"]:
        referrer = None
        args = m.text.split()
        if len(args) > 1 and args[1].isdigit() and args[1] != uid:
            referrer = args[1]
        
        db["users"][uid] = {
            "name": username, 
            "current_app": None, 
            "referred_by": referrer,
            "referral_count": 0,
            "gift_claimed": False
        }
        if referrer: add_log(f"مستخدم جديد {uid} دخل بواسطة إحالة من {referrer}")

    db["users"][uid]["name"] = username
    
    # معالجة ربط الجهاز (Deep Link)
    args = m.text.split()
    if len(args) > 1 and "_" in args[1]:
        cid = args[1]
        if cid not in db["app_links"]:
            db["app_links"][cid] = {"end_time": 0, "banned": False, "trial_last_time": 0, "telegram_id": uid, "gift_done": False}
        db["app_links"][cid]["telegram_id"] = uid
        db["users"][uid]["current_app"] = cid
        
        # ميزة هدية القناة (3 أيام)
        if not db["app_links"][cid].get("gift_done") and is_member(uid):
            db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (3 * 86400)
            db["app_links"][cid]["gift_done"] = True
            bot.send_message(m.chat.id, "🎁 **حصلت على 3 أيام مجانية لانضمامك للقناة!**", parse_mode="Markdown")
            
            # مكافأة الإحالة للداعي (7 أيام)
            ref_id = db["users"][uid].get("referred_by")
            if ref_id and ref_id in db["users"]:
                ref_app = db["users"][ref_id].get("current_app")
                if ref_app and ref_app in db["app_links"]:
                    db["app_links"][ref_app]["end_time"] += (7 * 86400)
                    db["users"][ref_id]["referral_count"] += 1
                    try: bot.send_message(ref_id, f"🎊 مبروك! حصلت على 7 أيام إضافية بسبب إحالة ناجحة لـ {username}")
                    except: pass
        
        bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**", parse_mode="Markdown")
    
    save_db(db)

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📱 تطبيقاتي", callback_data="u_dashboard"),
        types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
        types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
        types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy_menu"),
        types.InlineKeyboardButton("🔗 إحالاتي ومكافآتي", callback_data="u_referral")
    )
    bot.send_message(m.chat.id, f"مرحباً بك يا **{username}** 🌟\nاستخدم القائمة للتحكم في اشتراكاتك:", reply_markup=markup, parse_mode="Markdown")

# --- [ معالجة الأزرار ] ---
@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    db = load_db()
    bot.answer_callback_query(q.id) # لإزالة التظليل عن الزر فوراً

    if q.data == "u_dashboard": user_dashboard(q.message)
    elif q.data == "u_redeem":
        msg = bot.send_message(q.message.chat.id, "🎫 **أرسل كود التفعيل أو كود الخصم:**")
        bot.register_next_step_handler(msg, redeem_code_step)
    elif q.data.startswith("redeem_select_"):
        redeem_select_app(q.message, q.data.replace("redeem_select_", ""))
    elif q.data == "u_trial": process_trial(q.message)
    elif q.data.startswith("trial_select_"):
        trial_select_app(q.message, q.data.replace("trial_select_", ""))
    elif q.data == "u_buy_menu": send_plans_menu(q.message)
    elif q.data.startswith("buy_tier_"):
        process_plan_selection(q.message, q.data.split("_")[2])
    elif q.data == "u_referral": show_referral_info(q.message)

    # --- خيارات المدير ---
    elif q.from_user.id == ADMIN_ID:
        if q.data == "list_all": show_detailed_users(q.message)
        elif q.data == "gen_key":
            msg = bot.send_message(q.message.chat.id, "أرسل عدد الأيام للكود:")
            bot.register_next_step_handler(msg, process_gen_key)
        elif q.data == "manual_add":
            msg = bot.send_message(q.message.chat.id, "أرسل (المعرف + مسافة + عدد الأيام):")
            bot.register_next_step_handler(msg, process_manual_add)
        elif q.data == "top_refs": show_top_referrals(q.message)
        elif q.data == "bc_tele":
            msg = bot.send_message(q.message.chat.id, "ارسل رسالة الإذاعة:")
            bot.register_next_step_handler(msg, do_bc_tele)

# --- [ وظائف الإحالات والخطط ] ---

def show_referral_info(m):
    uid = str(m.chat.id)
    db = load_db()
    count = db["users"].get(uid, {}).get("referral_count", 0)
    ref_link = f"https://t.me/{bot.get_me().username}?start={uid}"
    msg = (f"🔗 **نظام الإحالات**\n\n"
           f"شارك رابطك واحصل على **7 أيام** لكل شخص ينضم للقناة ويربط جهازه!\n\n"
           f"👥 عدد إحالاتك الناجحة: `{count}`\n"
           f"🔗 رابطك:\n`{ref_link}`")
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

def send_plans_menu(m):
    markup = types.InlineKeyboardMarkup()
    for days, price in SUB_PLANS.items():
        markup.add(types.InlineKeyboardButton(f"📅 {days} يوم - {price} نجمة", callback_data=f"buy_tier_{days}"))
    bot.send_message(m.chat.id, "🛒 **اختر باقة الاشتراك المناسبة لك:**", reply_markup=markup)

def process_plan_selection(m, days):
    db = load_db()
    uid = str(m.chat.id)
    cid = db["users"].get(uid, {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ اربط جهازك أولاً من داخل التطبيق.")
    
    price = SUB_PLANS[days]
    bot.send_invoice(m.chat.id, title=f"اشتراك {days} يوم", 
                     description=f"تفعيل لجهازك: {cid}", 
                     invoice_payload=f"pay_{days}_{cid}", 
                     provider_token="", currency="XTR",
                     prices=[types.LabeledPrice(label="VIP", amount=price)])

# --- [ لوحة المدير ] ---
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 المشتركين", callback_data="list_all"),
        types.InlineKeyboardButton("🎫 توليد كود", callback_data="gen_key"),
        types.InlineKeyboardButton("➕ شحن يدوي", callback_data="manual_add"),
        types.InlineKeyboardButton("🏆 أفضل المسوقين", callback_data="top_refs"),
        types.InlineKeyboardButton("📢 إذاعة", callback_data="bc_tele")
    )
    bot.send_message(m.chat.id, "👑 **لوحة تحكم نجم الإبداع**", reply_markup=markup)

def show_top_referrals(m):
    db = load_db()
    # ترتيب المستخدمين حسب عدد الإحالات
    top = sorted(db["users"].items(), key=lambda x: x[1].get("referral_count", 0), reverse=True)[:10]
    msg = "🏆 **أفضل 10 داعين:**\n\n"
    for i, (uid, data) in enumerate(top, 1):
        msg += f"{i}- {data['name']} : `{data.get('referral_count', 0)}` إحالة\n"
    bot.send_message(m.chat.id, msg)

def process_manual_add(m):
    try:
        parts = m.text.split()
        cid, days = parts[0], int(parts[1])
        db = load_db()
        if cid in db["app_links"]:
            db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (days * 86400)
            save_db(db)
            bot.send_message(m.chat.id, f"✅ تم شحن {days} يوم للجهاز بنجاح.")
        else: bot.send_message(m.chat.id, "❌ المعرف غير موجود.")
    except: bot.send_message(m.chat.id, "⚠️ صيغة خاطئة. ارسل: المعرف أيام")

# --- [ استكمال منطق التفعيل ] ---

def user_dashboard(m):
    db = load_db(); uid = str(m.chat.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps: return bot.send_message(m.chat.id, "❌ لا توجد أجهزة مرتبطة.")
    
    msg = "👤 **أجهزتك المرتبطة:**\n"
    for cid in user_apps:
        data = db["app_links"][cid]
        rem_time = data.get("end_time", 0) - time.time()
        status = f"✅ {int(rem_time/86400)} يوم" if rem_time > 0 else "❌ منتهي"
        msg += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n🆔 `{cid}`\nالحالة: {status}\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

def redeem_code_step(m):
    code = m.text.strip()
    db = load_db(); uid = str(m.from_user.id)
    
    if code in db["vouchers"]:
        user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
        if not user_apps: return bot.send_message(m.chat.id, "❌ اربط جهازاً أولاً.")
        db["users"][uid]["temp_code"] = code
        save_db(db)
        markup = types.InlineKeyboardMarkup()
        for cid in user_apps:
            markup.add(types.InlineKeyboardButton(f"تفعيل لـ {cid[:10]}...", callback_data=f"redeem_select_{cid}"))
        bot.send_message(m.chat.id, "اختر الجهاز المراد تفعيله:", reply_markup=markup)
    else:
        bot.send_message(m.chat.id, "❌ الكود غير صحيح.")

def redeem_select_app(m, selected_cid):
    db = load_db(); uid = str(m.chat.id)
    code = db["users"].get(uid, {}).pop("temp_code", None)
    if code and code in db["vouchers"]:
        days = db["vouchers"].pop(code)
        db["app_links"][selected_cid]["end_time"] = max(time.time(), db["app_links"][selected_cid].get("end_time", 0)) + (days * 86400)
        save_db(db)
        bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم بنجاح!")

def process_trial(m):
    db = load_db(); uid = str(m.chat.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps: return bot.send_message(m.chat.id, "❌ اربط جهازاً أولاً.")
    markup = types.InlineKeyboardMarkup()
    for cid in user_apps:
        markup.add(types.InlineKeyboardButton(f"تجربة لـ {cid[:10]}...", callback_data=f"trial_select_{cid}"))
    bot.send_message(m.chat.id, "اختر الجهاز للتجربة:", reply_markup=markup)

def trial_select_app(m, selected_cid):
    db = load_db(); data = db["app_links"][selected_cid]
    if time.time() - data.get("trial_last_time", 0) < 86400:
        return bot.send_message(m.chat.id, "❌ مسموح مرة كل 24 ساعة.")
    data["trial_last_time"] = time.time()
    data["end_time"] = max(time.time(), data.get("end_time", 0)) + 10800 # 3 ساعات
    save_db(db)
    bot.send_message(m.chat.id, "✅ تم تفعيل 3 ساعات تجربة!")

# --- [ الدفع والسداد ] ---
@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True) 

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    payload = m.successful_payment.invoice_payload.split("_")
    days = int(payload[1])
    cid = "_".join(payload[2:])
    db = load_db()
    if cid in db["app_links"]:
        db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (days * 86400)
        save_db(db)
        bot.send_message(m.chat.id, f"✅ تم شراء {days} يوم بنجاح!")
        add_log(f"عملية شراء ناجحة: {days} يوم للجهاز {cid}")

# --- [ التشغيل ] ---
def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
