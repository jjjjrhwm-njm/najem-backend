import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread
import firebase_admin
from firebase_admin import credentials, firestore

# --- [ الإعدادات الأساسية - مشفرة عبر راندر ] ---
# هنا قمنا بربط الكود بالأسماء التي وضعتها في صفحة Environment
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', 7650083401))
CHANNEL_ID = os.getenv('CHANNEL_ID', "@jrhwm0njm") 

# تهيئة Firebase Firestore
if not firebase_admin._apps:
    cred_val = os.environ.get('FIREBASE_CREDENTIALS')
    if cred_val:
        cred_dict = json.loads(cred_val)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    else:
        print("Warning: FIREBASE_CREDENTIALS not found in environment variables.")

db_fs = firestore.client()
bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- [ إدارة قاعدة البيانات ] ---

def get_user(uid):
    doc = db_fs.collection("users").document(str(uid)).get()
    return doc.to_dict() if doc.exists else None

def update_user(uid, data):
    db_fs.collection("users").document(str(uid)).set(data, merge=True)

def get_app_link(cid):
    doc = db_fs.collection("app_links").document(str(cid)).get()
    return doc.to_dict() if doc.exists else None

def update_app_link(cid, data):
    db_fs.collection("app_links").document(str(cid)).set(data, merge=True)

def get_voucher(code):
    doc = db_fs.collection("vouchers").document(str(code)).get()
    if doc.exists:
        return doc.to_dict().get("days")
    return None

def delete_voucher(code):
    db_fs.collection("vouchers").document(str(code)).delete()

def add_log(text):
    log_data = {"text": f"[{time.strftime('%Y-%m-%d %H:%M')}] {text}", "timestamp": time.time()}
    db_fs.collection("logs").add(log_data)

def get_global_news():
    doc = db_fs.collection("config").document("global").get()
    return doc.to_dict().get("global_news", "لا توجد أخبار") if doc.exists else "لا توجد أخبار"

def set_global_news(text):
    db_fs.collection("config").document("global").set({"global_news": text}, merge=True)

def check_membership(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False 

# --- [ واجهة API - تم التعديل لعرض الرصيد ] ---
@app.route('/check')
def check_status():
    aid, pkg = request.args.get('aid'), request.args.get('pkg')
    if not aid or not pkg: return "EXPIRED"
    cid = f"{aid}_{pkg.replace('.', '_')}"
    data = get_app_link(cid)
    if not data: return "EXPIRED"
    if data.get("banned"): return "BANNED"
    
    rem_time = data.get("end_time", 0) - time.time()
    if rem_time <= 0: return "EXPIRED"
    
    # إرسال الحالة مع عدد الأيام المتبقية ليظهر في التطبيق
    days = int(rem_time / 86400)
    return f"ACTIVE|{days} Days" 

@app.route('/get_news') 
def get_news():
    return get_global_news()

# --- [ واجهة البوت - تعديل منطق الدخول ] ---
@bot.message_handler(commands=['start'])
def start(m):
    uid = str(m.from_user.id)
    username = f"@{m.from_user.username}" if m.from_user.username else m.from_user.first_name
    
    args = m.text.split()
    user_data = get_user(uid)
    
    if not user_data:
        # فحص إذا كان هناك رابط دعوة
        inviter_id = args[1] if len(args) > 1 and args[1].isdigit() and args[1] != uid else None
        user_data = {
            "current_app": None, "name": username, "invited_by": inviter_id,
            "referral_count": 0, "claimed_channel_gift": False, "join_date": time.time()
        }
        update_user(uid, user_data)
    else:
        update_user(uid, {"name": username})

    # معالجة الروابط القادمة من التطبيق
    if len(args) > 1:
        param = args[1]
        
        # 1. حالة التجربة المجانية
        if "trial_" in param:
            cid = param.replace("trial_", "")
            update_user(uid, {"current_app": cid})
            update_app_link(cid, {"telegram_id": uid})
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data=f"trial_select_{cid}"))
            return bot.send_message(m.chat.id, "مرحباً بك! اضغط أدناه للحصول على التجربة المجانية:", reply_markup=markup)

        # 2. حالة شراء اشتراك (بأقل من 8 ريال)
        elif "buy_" in param:
            cid = param.replace("buy_", "")
            update_user(uid, {"current_app": cid})
            update_app_link(cid, {"telegram_id": uid})
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🛒 باقل من 8 ريال", callback_data="u_buy"))
            return bot.send_message(m.chat.id, "مرحباً بك! يمكنك الاشتراك الآن بأفضل سعر:", reply_markup=markup)

        # 3. حالة تفعيل الكود المباشر
        elif "redeem_" in param:
            cid = param.replace("redeem_", "")
            update_user(uid, {"current_app": cid, "temp_target_app": cid})
            update_app_link(cid, {"telegram_id": uid})
            msg = bot.send_message(m.chat.id, "🎫 **أرسل كود التفعيل الآن ليتم تفعيله فوراً على جهازك:**")
            return bot.register_next_step_handler(msg, direct_redeem_step)

        # 4. الحالة الافتراضية للربط العادي
        elif "_" in param:
            cid = param
            link_data = get_app_link(cid) or {"end_time": 0, "banned": False, "trial_last_time": 0, "gift_claimed": False}
            link_data["telegram_id"] = uid
            update_user(uid, {"current_app": cid})
            update_app_link(cid, link_data)
            bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**", parse_mode="Markdown")

    # القائمة الرئيسية الافتراضية
    main_markup = types.InlineKeyboardMarkup(row_width=2)
    main_markup.add(
        types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
        types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
        types.InlineKeyboardButton("🔗 إحالاتي ومكافآتي", callback_data="u_referral"),
        types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
        types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy")
    )
    bot.send_message(m.chat.id, f"مرحباً بك يا **{username}** 🌟\nاستخدم القائمة أدناه للتحكم في اشتراكاتك:", reply_markup=main_markup, parse_mode="Markdown") 

# --- [ تفعيل الكود المباشر ] ---
def direct_redeem_step(m):
    code = m.text.strip()
    uid = str(m.from_user.id)
    user_data = get_user(uid)
    cid = user_data.get("temp_target_app")
    
    if not cid: return bot.send_message(m.chat.id, "❌ خطأ في تحديد الجهاز، حاول مرة أخرى.")
    
    days = get_voucher(code)
    if not days: return bot.send_message(m.chat.id, "❌ الكود غير صحيح أو مستخدم.")
    
    link_data = get_app_link(cid)
    new_end_time = max(time.time(), link_data.get("end_time", 0)) + (days * 86400)
    update_app_link(cid, {"end_time": new_end_time})
    delete_voucher(code)
    
    add_log(f"تفعيل كود ({days} يوم) للجهاز {cid}")
    bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم بنجاح لجهازك الحالي!")

# --- [ معالجة ضغطات الأزرار ] ---
@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    if q.data == "u_dashboard": user_dashboard(q.message)
    elif q.data == "u_referral": show_referral_info(q.message)
    elif q.data == "u_redeem":
        msg = bot.send_message(q.message.chat.id, "🎫 **أرسل كود التفعيل الآن:**")
        bot.register_next_step_handler(msg, redeem_code_step)
    elif q.data.startswith("redeem_select_"): redeem_select_app(q.message, q.data.replace("redeem_select_", ""))
    elif q.data == "u_trial": process_trial(q.message)
    elif q.data.startswith("trial_select_"): trial_select_app(q.message, q.data.replace("trial_select_", ""))
    elif q.data == "u_buy": send_payment(q.message) 
    
    elif q.from_user.id == ADMIN_ID:
        if q.data == "list_all": show_detailed_users(q.message)
        elif q.data == "admin_logs": show_logs(q.message)
        elif q.data == "top_ref": show_top_referrers(q.message)
        elif q.data == "gen_key":
            msg = bot.send_message(q.message.chat.id, "كم عدد الأيام؟")
            bot.register_next_step_handler(msg, process_gen_key)
        elif q.data == "bc_tele":
            msg = bot.send_message(q.message.chat.id, "ارسل رسالة الإذاعة:")
            bot.register_next_step_handler(msg, do_bc_tele)
        elif q.data == "bc_app":
            msg = bot.send_message(q.message.chat.id, "ارسل الخبر للتطبيق:")
            bot.register_next_step_handler(msg, do_bc_app)
        elif q.data in ["ban_op", "unban_op"]:
            msg = bot.send_message(q.message.chat.id, "ارسل المعرف:")
            bot.register_next_step_handler(msg, process_ban_unban, q.data) 

# --- [ بقية وظائف النطام - بدون تغيير ] ---

def show_detailed_users(m):
    links = db_fs.collection("app_links").get()
    if not links: return bot.send_message(m.chat.id, "لا توجد أجهزة مسجلة.")
    full_list = "📂 **إحصائيات الأجهزة:**\n\n"
    for doc in links:
        cid = doc.id
        data = doc.to_dict()
        rem_time = data.get("end_time", 0) - time.time()
        stat = "🔴 محظور" if data.get("banned") else (f"🟢 {int(rem_time/86400)} يوم" if rem_time > 0 else "⚪ منتهي")
        full_list += f"🆔: `{cid}` | {stat}\n"
    bot.send_message(m.chat.id, full_list, parse_mode="Markdown")

def user_dashboard(m):
    uid = str(m.chat.id)
    user_apps_ref = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not user_apps_ref: return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة.")
    msg = "👤 **حالة اشتراكاتك ورصيدك:**\n"
    for doc in user_apps_ref:
        cid = doc.id
        data = doc.to_dict()
        rem_time = data.get("end_time", 0) - time.time()
        status = f"✅ متبقي {int(rem_time/86400)} يوم" if rem_time > 0 else "❌ منتهي"
        msg += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📦 جهاز: `{cid}`\nالرصيد المتبقي: {status}\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

def process_trial(m):
    uid = str(m.chat.id)
    user_apps_ref = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not user_apps_ref: return bot.send_message(m.chat.id, "❌ لا يوجد تطبيق مرتبط.")
    markup = types.InlineKeyboardMarkup(row_width=1)
    for doc in user_apps_ref: markup.add(types.InlineKeyboardButton(f"📦 {doc.id}", callback_data=f"trial_select_{doc.id}"))
    bot.send_message(m.chat.id, "🛠️ اختر التطبيق للتجربة:", reply_markup=markup) 

def trial_select_app(m, selected_cid):
    data = get_app_link(selected_cid)
    if not data: return
    if time.time() - data.get("trial_last_time", 0) < 86400:
        return bot.send_message(m.chat.id, "❌ التجربة متاحة مرة كل 24 ساعة.")
    new_end_time = max(time.time(), data.get("end_time", 0)) + (3 * 86400)
    update_app_link(selected_cid, {"trial_last_time": time.time(), "end_time": new_end_time})
    bot.send_message(m.chat.id, "✅ تم تفعيل 3 أيام تجربة بنجاح!")

def redeem_code_step(m):
    code = m.text.strip()
    days = get_voucher(code)
    if not days: return bot.send_message(m.chat.id, "❌ الكود غير صحيح.")
    uid = str(m.from_user.id)
    user_apps_ref = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not user_apps_ref: return bot.send_message(m.chat.id, "❌ اربط جهازك أولاً.")
    update_user(uid, {"temp_code": code})
    markup = types.InlineKeyboardMarkup()
    for doc in user_apps_ref: markup.add(types.InlineKeyboardButton(f"📦 {doc.id}", callback_data=f"redeem_select_{doc.id}"))
    bot.send_message(m.chat.id, "🛠️ اختر الجهاز للتفعيل:", reply_markup=markup)

def redeem_select_app(m, selected_cid):
    uid = str(m.chat.id)
    user_data = get_user(uid)
    code = user_data.get("temp_code")
    days = get_voucher(code)
    if days:
        link_data = get_app_link(selected_cid)
        update_app_link(selected_cid, {"end_time": max(time.time(), link_data.get("end_time", 0)) + (days * 86400)})
        delete_voucher(code)
        update_user(uid, {"temp_code": firestore.DELETE_FIELD})
        bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم!")

def send_payment(m):
    uid = str(m.chat.id)
    user_data = get_user(uid)
    cid = user_data.get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ افتح التطبيق أولاً.")
    bot.send_invoice(m.chat.id, title="اشتراك 30 يوم", description=f"تفعيل الجهاز: {cid}", 
                     invoice_payload=f"pay_{cid}", provider_token="", currency="XTR",
                     prices=[types.LabeledPrice(label="VIP الاشتراك السريع", amount=100)]) 

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 المشتركين", callback_data="list_all"),
        types.InlineKeyboardButton("🎫 كود جديد", callback_data="gen_key"),
        types.InlineKeyboardButton("📢 إعلان التطبيق", callback_data="bc_app"),
        types.InlineKeyboardButton("🚫 حظر", callback_data="ban_op"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="unban_op")
    )
    bot.send_message(m.chat.id, "👑 لوحة التحكم:", reply_markup=markup)

def show_logs(m):
    logs_ref = db_fs.collection("logs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(10).get()
    logs_text = "\n".join([doc.to_dict().get("text") for doc in logs_ref]) or "لا توجد سجلات."
    bot.send_message(m.chat.id, f"📝 **السجلات:**\n\n{logs_text}")

def show_top_referrers(m):
    users_ref = db_fs.collection("users").order_by("referral_count", direction=firestore.Query.DESCENDING).limit(5).get()
    msg = "🏆 **الأكثر دعوة:**\n"
    for i, doc in enumerate(users_ref, 1): msg += f"{i}- {doc.to_dict().get('name')} ({doc.to_dict().get('referral_count')})\n"
    bot.send_message(m.chat.id, msg)

def show_referral_info(m):
    uid = str(m.chat.id)
    user_data = get_user(uid)
    ref_link = f"https://t.me/{bot.get_me().username}?start={uid}"
    bot.send_message(m.chat.id, f"🔗 رابط إحالتك:\n`{ref_link}`\n\nستحصل على 7 أيام لكل شخص يربط جهازه.", parse_mode="Markdown")

def do_bc_tele(m):
    for doc in db_fs.collection("users").get():
        try: bot.send_message(doc.id, m.text)
        except: pass
    bot.send_message(m.chat.id, "✅ تم الإرسال.")

def do_bc_app(m):
    set_global_news(m.text)
    bot.send_message(m.chat.id, "✅ تم تحديث الخبر.")

def process_gen_key(m):
    if not m.text.isdigit(): return
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db_fs.collection("vouchers").document(code).set({"days": int(m.text)})
    bot.send_message(m.chat.id, f"🎫 كود جديد:\n`{code}`", parse_mode="Markdown")

def process_ban_unban(m, mode):
    target = m.text.strip()
    if get_app_link(target):
        update_app_link(target, {"banned": (mode == "ban_op")})
        bot.send_message(m.chat.id, "✅ تمت العملية.")

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True) 

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    cid = m.successful_payment.invoice_payload.replace("pay_", "")
    link_data = get_app_link(cid)
    if link_data:
        new_time = max(time.time(), link_data.get("end_time", 0)) + (30 * 86400)
        update_app_link(cid, {"end_time": new_time})
        bot.send_message(m.chat.id, "✅ تم تفعيل الاشتراك لمدة شهر بنجاح!")

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))) 

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
