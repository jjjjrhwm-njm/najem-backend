import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread
import firebase_admin
from firebase_admin import credentials, firestore

# --- [ الإعدادات الأساسية ] ---
# الإعدادات الجديدة لبوت متجر نجم الإبداع
API_TOKEN = '7521759893:AAEGWIKj17Q4AZ07DLuZXmpa8fus1C9Bnic'
ADMIN_ID = 7650083401
CHANNEL_ID = "@jrhwm0njm"

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

# --- [ واجهة الويب الإضافية لحل مشكلة الكرون ] ---

@app.route('/')
def home():
    return "Bot is Running Successfully!", 200

# --- [ إدارة قاعدة البيانات باستخدام Firestore ] ---

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
    log_data = {
        "text": f"[{time.strftime('%Y-%m-%d %H:%M')}] {text}",
        "timestamp": time.time()
    }
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

# --- [ واجهة API ] ---
@app.route('/check')
def check_status():
    aid, pkg = request.args.get('aid'), request.args.get('pkg')
    if not aid or not pkg: return "EXPIRED"
    cid = f"{aid}_{pkg.replace('.', '_')}"
    data = get_app_link(cid)
    if not data: return "EXPIRED"
    if data.get("banned"): return "BANNED"
    if time.time() > data.get("end_time", 0): return "EXPIRED"
    return "ACTIVE" 

@app.route('/get_news') 
def get_news():
    return get_global_news()

# --- [ واجهة البوت - البداية ] ---
@bot.message_handler(commands=['start'])
def start(m):
    uid = str(m.from_user.id)
    username = f"@{m.from_user.username}" if m.from_user.username else m.from_user.first_name
    
    args = m.text.split()
    user_data = get_user(uid)
    
    if not user_data:
        inviter_id = args[1] if len(args) > 1 and args[1].isdigit() and args[1] != uid else None
        user_data = {
            "current_app": None, 
            "name": username, 
            "invited_by": inviter_id,
            "referral_count": 0,
            "claimed_channel_gift": False,
            "join_date": time.time()
        }
        update_user(uid, user_data)
        if inviter_id:
            inviter_data = get_user(inviter_id)
            if inviter_data:
                update_user(inviter_id, {"referral_count": inviter_data.get("referral_count", 0) + 1})
    else:
        user_data["name"] = username 
        update_user(uid, {"name": username})

    if len(args) > 1:
        param = args[1]
        action = None
        cid = None

        if param.startswith("trial_"):
            action = "trial"; cid = param.replace("trial_", "")
        elif param.startswith("buy_"):
            action = "buy"; cid = param.replace("buy_", "")
        elif param.startswith("redeem_"):
            action = "redeem"; cid = param.replace("redeem_", "")
        else:
            cid = param 

        if cid and "_" in cid:
            link_data = get_app_link(cid)
            if not link_data:
                link_data = {"end_time": 0, "banned": False, "trial_last_time": 0, "telegram_id": uid, "gift_claimed": False}
            
            link_data["telegram_id"] = uid
            update_user(uid, {"current_app": cid})
            update_app_link(cid, link_data)

            if action == "trial":
                return trial_select_app(m, cid)
            elif action == "buy":
                return send_payment(m)
            elif action == "redeem":
                update_user(uid, {"temp_code": "WAITING"})
                msg = bot.send_message(m.chat.id, "🎫 **أرسل كود التفعيل الآن للجهاز المرتبط:**")
                return bot.register_next_step_handler(msg, redeem_code_step)

            if check_membership(uid) and not link_data.get("gift_claimed"):
                link_data["end_time"] = max(time.time(), link_data.get("end_time", 0)) + (3 * 86400)
                link_data["gift_claimed"] = True
                update_app_link(cid, link_data)
                bot.send_message(m.chat.id, "🎁 **مبروك! حصلت على 3 أيام مجانية.**")
            
            bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
        types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
        types.InlineKeyboardButton("🔗 إحالاتي ومكافآتي", callback_data="u_referral"),
        types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
        types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy")
    )
    bot.send_message(m.chat.id, f"مرحباً بك يا **{username}** 🌟\nاستخدم القائمة أدناه للتحكم في اشتراكاتك:", reply_markup=markup, parse_mode="Markdown") 

# --- [ الأوامر النصية المباشرة ] ---
@bot.message_handler(func=lambda m: m.text == "تجربه")
def cmd_trial(m): process_trial(m)

@bot.message_handler(func=lambda m: m.text == "اشتراك")
def cmd_buy(m): send_payment(m)

@bot.message_handler(func=lambda m: m.text == "اشتراكاتي")
def cmd_dash(m): user_dashboard(m)

@bot.message_handler(func=lambda m: m.text == "تفعيل كود")
def cmd_redeem(m):
    msg = bot.send_message(m.chat.id, "🎫 **أرسل كود التفعيل الآن:**")
    bot.register_next_step_handler(msg, redeem_code_step)

# --- [ معالجة ضغطات الأزرار ] ---
@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    if q.data == "u_dashboard": user_dashboard(q.message)
    elif q.data == "u_referral": show_referral_info(q.message)
    elif q.data == "u_redeem":
        msg = bot.send_message(q.message.chat.id, "🎫 **أرسل كود التفعيل الآن:**")
        bot.register_next_step_handler(msg, redeem_code_step)
    elif q.data.startswith("redeem_select_"):
        redeem_select_app(q.message, q.data.replace("redeem_select_", ""))
    elif q.data == "u_trial": process_trial(q.message)
    elif q.data.startswith("trial_select_"):
        trial_select_app(q.message, q.data.replace("trial_select_", ""))
    elif q.data == "u_buy": send_payment(q.message) 
    elif q.from_user.id == ADMIN_ID:
        if q.data == "list_all": show_detailed_users(q.message)
        elif q.data == "admin_logs": show_logs(q.message)
        elif q.data == "top_ref": show_top_referrers(q.message)
        elif q.data == "gen_key":
            msg = bot.send_message(q.message.chat.id, "كم عدد الأيام؟")
            bot.register_next_step_handler(msg, process_gen_key)
        elif q.data == "bc_tele":
            msg = bot.send_message(q.message.chat.id, "ارسل الإذاعة:")
            bot.register_next_step_handler(msg, do_bc_tele)
        elif q.data == "bc_app":
            msg = bot.send_message(q.message.chat.id, "ارسل الخبر:")
            bot.register_next_step_handler(msg, do_bc_app)
        elif q.data == "reset_db_op": confirm_reset(q.message)
        elif q.data == "confirm_full_reset": do_full_reset(q.message)
        elif q.data in ["ban_op", "unban_op"]:
            msg = bot.send_message(q.message.chat.id, "ارسل المعرف:")
            bot.register_next_step_handler(msg, process_ban_unban, q.data) 

# --- [ وظائف الإدارة ] --- 
def show_detailed_users(m):
    links = db_fs.collection("app_links").stream()
    full_list = "📂 **إحصائيات الأجهزة:**\n\n"
    found = False
    for doc in links:
        found = True
        cid = doc.id; data = doc.to_dict()
        rem = data.get("end_time", 0) - time.time()
        stat = "🔴 محظور" if data.get("banned") else (f"🟢 {int(rem/86400)} يوم" if rem > 0 else "⚪ منتهي")
        full_list += f"🆔: `{cid}`\nالحالة: {stat}\n⎯⎯⎯⎯⎯\n"
        if len(full_list) > 3500:
            bot.send_message(m.chat.id, full_list, parse_mode="Markdown")
            full_list = ""
    
    if not found: return bot.send_message(m.chat.id, "لا توجد أجهزة مسجلة.")
    if full_list: bot.send_message(m.chat.id, full_list, parse_mode="Markdown") 

def show_logs(m):
    logs_ref = db_fs.collection("logs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(20).stream()
    logs_list = [d.to_dict().get("text") for d in logs_ref]
    text = "\n".join(logs_list) if logs_list else "لا توجد سجلات."
    bot.send_message(m.chat.id, f"📝 **آخر العمليات:**\n\n{text}") 

def show_top_referrers(m):
    users = db_fs.collection("users").order_by("referral_count", direction=firestore.Query.DESCENDING).limit(10).get()
    msg = "🏆 **أفضل 10 داعين:**\n\n"
    for i, doc in enumerate(users, 1):
        msg += f"{i}- {doc.to_dict().get('name')} ⮕ `{doc.to_dict().get('referral_count', 0)}` إحالة\n"
    bot.send_message(m.chat.id, msg) 

def confirm_reset(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⚠️ نعم، احذف كل شيء", callback_data="confirm_full_reset"))
    markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel_back"))
    bot.send_message(m.chat.id, "❗ **تحذير:** سيتم حذف جميع (الأكواد، السجلات، واشتراكات الأجهزة) نهائياً. هل أنت متأكد؟", reply_markup=markup)

def do_full_reset(m):
    collections = ["vouchers", "app_links", "logs"]
    for coll in collections:
        docs = db_fs.collection(coll).list_documents()
        for doc in docs: doc.delete()
    bot.send_message(m.chat.id, "✅ **تم تصفير البيانات بنجاح!**")
    add_log("قام المسؤول بتصفير قاعدة البيانات")

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    links_all = db_fs.collection("app_links").get()
    active = sum(1 for d in links_all if d.to_dict().get("end_time", 0) > time.time())
    msg = (f"👑 **إدارة نجم الإبداع**\n\n"
           f"👥 المستخدمين: `{len(db_fs.collection('users').get())}` | الأجهزة: `{len(links_all)}`\n"
           f"🟢 النشطين: `{active}`\n")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 المشتركين", callback_data="list_all"),
        types.InlineKeyboardButton("📝 السجلات", callback_data="admin_logs"),
        types.InlineKeyboardButton("🏆 المتصدرين", callback_data="top_ref"),
        types.InlineKeyboardButton("🎫 كود جديد", callback_data="gen_key"),
        types.InlineKeyboardButton("🚫 حظر", callback_data="ban_op"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="unban_op"),
        types.InlineKeyboardButton("📢 إعلان التطبيق", callback_data="bc_app"),
        types.InlineKeyboardButton("📢 إعلان تلجرام", callback_data="bc_tele"),
        types.InlineKeyboardButton("🗑️ تصفير البيانات", callback_data="reset_db_op")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown") 

# --- [ منطق المستخدم ] --- 
def show_referral_info(m):
    uid = str(m.chat.id); data = get_user(uid)
    if not data: return
    ref_link = f"https://t.me/{bot.get_me().username}?start={uid}"
    count = data.get("referral_count", 0)
    msg = (f"🔗 **نظام الإحالات:**\n\n"
           f"👥 عدد إحالاتك: `{count}`\n"
           f"رابط دعوتك:\n`{ref_link}`")
    bot.send_message(m.chat.id, msg, parse_mode="Markdown") 

def user_dashboard(m):
    uid = str(m.chat.id)
    apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not apps: return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة.")
    msg = "👤 **حالة اشتراكاتك:**\n"
    for doc in apps:
        data = doc.to_dict(); rem = data.get("end_time", 0) - time.time()
        stat = f"✅ {int(rem/86400)} يوم" if rem > 0 else "❌ منتهي"
        if data.get("banned"): stat = "🚫 محظور"
        msg += f"⎯⎯⎯⎯⎯\n📦 `{doc.id.split('_')[-1]}`\nالحالة: {stat}\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown") 

def redeem_code_step(m):
    code = m.text.strip(); days = get_voucher(code)
    if not days: return bot.send_message(m.chat.id, "❌ الكود غير صحيح.")
    uid = str(m.from_user.id)
    apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not apps: return bot.send_message(m.chat.id, "❌ اربط جهازك أولاً.")
    update_user(uid, {"temp_code": code})
    markup = types.InlineKeyboardMarkup(row_width=1)
    for doc in apps: markup.add(types.InlineKeyboardButton(f"📦 {doc.id.split('_')[-1]}", callback_data=f"redeem_select_{doc.id}"))
    bot.send_message(m.chat.id, "🛠️ اختر التطبيق:", reply_markup=markup) 

def redeem_select_app(m, cid):
    uid = str(m.chat.id); code = get_user(uid).get("temp_code")
    days = get_voucher(code); data = get_app_link(cid)
    new_end = max(time.time(), data.get("end_time", 0)) + (days * 86400)
    update_app_link(cid, {"end_time": new_end})
    delete_voucher(code)
    bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم!")
    add_log(f"تفعيل كود {days} يوم للجهاز {cid}")

def process_trial(m):
    uid = str(m.chat.id)
    apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not apps: return bot.send_message(m.chat.id, "❌ لا يوجد تطبيق.")
    markup = types.InlineKeyboardMarkup(row_width=1)
    for doc in apps: markup.add(types.InlineKeyboardButton(f"📦 {doc.id.split('_')[-1]}", callback_data=f"trial_select_{doc.id}"))
    bot.send_message(m.chat.id, "🛠️ اختر تطبيق التجربة:", reply_markup=markup) 

def trial_select_app(m, cid):
    data = get_app_link(cid)
    if time.time() - data.get("trial_last_time", 0) < 86400:
        return bot.send_message(m.chat.id, "❌ التجربة متاحة مرة كل 24 ساعة.")
    new_end = max(time.time(), data.get("end_time", 0)) + 259200
    update_app_link(cid, {"trial_last_time": time.time(), "end_time": new_end})
    bot.send_message(m.chat.id, "✅ تم تفعيل 3 أيام تجربة!") 

def send_payment(m):
    uid = str(m.chat.id); cid = get_user(uid).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ افتح التطبيق أولاً.")
    bot.send_invoice(m.chat.id, title="اشتراك 30 يوم", description=f"الحساب: {cid}", 
                     invoice_payload=f"pay_{cid}", provider_token="", currency="XTR",
                     prices=[types.LabeledPrice(label="VIP", amount=100)]) 

# --- [ الوظائف الأخرى ] ---
def do_bc_tele(m):
    count = 0
    for doc in db_fs.collection("users").get():
        try: bot.send_message(doc.id, f"📢 **إعلان:**\n\n{m.text}"); count += 1
        except: pass
    bot.send_message(m.chat.id, f"✅ تم الإرسال لـ {count}") 

def do_bc_app(m):
    set_global_news(m.text)
    bot.send_message(m.chat.id, "✅ تم التحديث.") 

def process_gen_key(m):
    if not m.text.isdigit(): return
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db_fs.collection("vouchers").document(code).set({"days": int(m.text)})
    bot.send_message(m.chat.id, f"🎫 كود: `{code}`") 

def process_ban_unban(m, mode):
    update_app_link(m.text.strip(), {"banned": (mode == "ban_op")})
    bot.send_message(m.chat.id, "✅ تم.") 

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True) 

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    cid = m.successful_payment.invoice_payload.replace("pay_", "")
    data = get_app_link(cid)
    new_time = max(time.time(), data.get("end_time", 0)) + (30 * 86400)
    update_app_link(cid, {"end_time": new_time})
    bot.send_message(m.chat.id, "✅ تم الشراء!") 

def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))) 

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
