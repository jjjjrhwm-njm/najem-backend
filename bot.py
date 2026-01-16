import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread
import firebase_admin
from firebase_admin import credentials, firestore

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
CHANNEL_ID = os.environ.get('CHANNEL_ID') 

if not firebase_admin._apps:
    cred_val = os.environ.get('FIREBASE_CREDENTIALS')
    if cred_val:
        try:
            cred_dict = json.loads(cred_val)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            print(f"Error: {e}")

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
    return doc.to_dict().get("days") if doc.exists else None

def delete_voucher(code):
    db_fs.collection("vouchers").document(str(code)).delete()

def add_log(text):
    db_fs.collection("logs").add({
        "text": f"[{time.strftime('%Y-%m-%d %H:%M')}] {text}",
        "timestamp": time.time()
    })

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

# --- [ واجهة البوت - البداية والربط التلقائي ] ---
@bot.message_handler(commands=['start'])
def start(m):
    uid = str(m.from_user.id)
    username = f"@{m.from_user.username}" if m.from_user.username else m.from_user.first_name
    
    args = m.text.split()
    user_data = get_user(uid)
    
    if not user_data:
        inviter_id = args[1] if len(args) > 1 and args[1].isdigit() and args[1] != uid else None
        user_data = {
            "current_app": None, "name": username, "invited_by": inviter_id,
            "referral_count": 0, "claimed_channel_gift": False, "join_date": time.time()
        }
        update_user(uid, user_data)
    else:
        update_user(uid, {"name": username})

    # --- المنطق الجديد للتعامل مع أوامر التطبيق التلقائية ---
    if len(args) > 1:
        param = args[1]
        action = "LINK" # الافتراضي
        cid = ""

        # تحديد الإجراء واستخراج الـ CID (معرف الجهاز والباكيج)
        if param.startswith("TRIAL_"):
            action = "TRIAL"; cid = param.replace("TRIAL_", "")
        elif param.startswith("BUY_"):
            action = "BUY"; cid = param.replace("BUY_", "")
        elif param.startswith("DASH_"):
            action = "DASH"; cid = param.replace("DASH_", "")
        elif param.startswith("REDEEM_"):
            action = "REDEEM"; cid = param.replace("REDEEM_", "")
        else:
            cid = param # في حالة الربط العادي فقط

        if "_" in cid:
            # ربط الجهاز بالمستخدم أولاً
            link_data = get_app_link(cid) or {"end_time": 0, "banned": False, "trial_last_time": 0, "gift_claimed": False}
            link_data["telegram_id"] = uid
            update_app_link(cid, link_data)
            update_user(uid, {"current_app": cid})
            
            # منح هدية القناة تلقائياً عند أول ربط
            if check_membership(uid) and not link_data.get("gift_claimed"):
                link_data["end_time"] = max(time.time(), link_data.get("end_time", 0)) + (3 * 86400)
                link_data["gift_claimed"] = True
                update_app_link(cid, link_data)
                bot.send_message(m.chat.id, "🎁 تم منحك 3 أيام مجان ارجع الا التطبيق وضقط دخول!")
                
                # مكافأة الداعي
                inviter = user_data.get("invited_by")
                if inviter:
                    inv_data = get_user(inviter)
                    if inv_data and inv_data.get("current_app"):
                        inv_link = get_app_link(inv_data["current_app"])
                        if inv_link:
                            new_time = max(time.time(), inv_link.get("end_time", 0)) + (7 * 86400)
                            update_app_link(inv_data["current_app"], {"end_time": new_time})
                            update_user(inviter, {"referral_count": inv_data.get("referral_count", 0) + 1})
                            try: bot.send_message(inviter, "🎊 حصلت على 7 أيام إضافية بسبب دعوة صديق!")
                            except: pass

            # تنفيذ الطلب القادم من التطبيق بشكل فوري وتلقائي
            if action == "TRIAL":
                return trial_select_app(m, cid) # تفعيل التجربة فوراً
            elif action == "BUY":
                return send_payment(m) # فتح فاتورة الدفع فوراً
            elif action == "DASH":
                return user_dashboard(m) # عرض حالة الاشتراك فوراً
            elif action == "REDEEM":
                msg = bot.send_message(m.chat.id, f"🎫 **الجهاز المستهدف:** `{cid.split('_')[-1]}`\n**أرسل كود التفعيل الآن:**")
                bot.register_next_step_handler(msg, redeem_code_step)
                return
            else:
                bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**")
                return user_dashboard(m)

    show_main_menu(m, username)

def show_main_menu(m, username):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
        types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
        types.InlineKeyboardButton("🔗 إحالاتي ومكافآتي", callback_data="u_referral"),
        types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
        types.InlineKeyboardButton("🛒شرا اشتراك شهر ب8ريال", callback_data="u_buy")
    )
    bot.send_message(m.chat.id, f"مرحباً بك يا **{username}** 🌟\nاستخدم القائمة للتحكم أو اطلب من داخل التطبيق:", reply_markup=markup, parse_mode="Markdown")

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
            msg = bot.send_message(q.message.chat.id, "ارسل الإعلان:")
            bot.register_next_step_handler(msg, do_bc_tele)
        elif q.data == "bc_app":
            msg = bot.send_message(q.message.chat.id, "ارسل الخبر:")
            bot.register_next_step_handler(msg, do_bc_app)
        elif q.data in ["ban_op", "unban_op"]:
            msg = bot.send_message(q.message.chat.id, "ارسل المعرف:")
            bot.register_next_step_handler(msg, process_ban_unban, q.data)

# --- [ وظائف الإدارة ] --- 

def show_detailed_users(m):
    all_users = db_fs.collection("users").get()
    if not all_users: return bot.send_message(m.chat.id, "لا يوجد مستخدمين.")
    
    all_links = db_fs.collection("app_links").get()
    links_map = {}
    for l in all_links:
        u_id = l.to_dict().get("telegram_id")
        if u_id not in links_map: links_map[u_id] = []
        links_map[u_id].append({"id": l.id, "data": l.to_dict()})

    msg = "📂 **قائمة المشتركين وتطبيقاتهم:**\n\n"
    for user_doc in all_users:
        uid = user_doc.id
        udata = user_doc.to_dict()
        u_name = udata.get("name", "غير معروف")
        user_apps = links_map.get(uid, [])
        
        msg += f"👤 **المستخدم:** {u_name} (`{uid}`)\n"
        if not user_apps:
            msg += "└ 🚫 لا توجد تطبيقات مرتبطة\n"
        else:
            for app_item in user_apps:
                rem = app_item['data'].get("end_time", 0) - time.time()
                stat = "🔴 محظور" if app_item['data'].get("banned") else (f"🟢 {int(rem/86400)} يوم" if rem > 0 else "⚪ منتهي")
                msg += f"└ 📦 `{app_item['id'].split('_')[-1]}` ⮕ {stat}\n"
        msg += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        
        if len(msg) > 3500:
            bot.send_message(m.chat.id, msg, parse_mode="Markdown")
            msg = ""
            
    if msg: bot.send_message(m.chat.id, msg, parse_mode="Markdown")

def show_logs(m):
    logs = db_fs.collection("logs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(15).get()
    text = "\n".join([d.to_dict().get("text") for d in logs]) if logs else "لا توجد سجلات."
    bot.send_message(m.chat.id, f"📝 **آخر العمليات:**\n\n{text}") 

def show_top_referrers(m):
    users = db_fs.collection("users").order_by("referral_count", direction=firestore.Query.DESCENDING).limit(10).get()
    msg = "🏆 **أفضل 10 داعين:**\n\n"
    for i, d in enumerate(users, 1):
        msg += f"{i}- {d.to_dict().get('name')} ⮕ `{d.to_dict().get('referral_count', 0)}` إحالة\n"
    bot.send_message(m.chat.id, msg) 

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    users_count = len(db_fs.collection("users").get())
    links_all = db_fs.collection("app_links").get()
    active = sum(1 for d in links_all if d.to_dict().get("end_time", 0) > time.time())
    
    msg = (f"👑 **إدارة نجم الإبداع**\n\n"
           f"👥 المستخدمين: `{users_count}` | الأجهزة: `{len(links_all)}`\n"
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
        types.InlineKeyboardButton("📢 إعلان تلجرام", callback_data="bc_tele")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown") 

# --- [ منطق المستخدم ] --- 

def show_referral_info(m):
    user_data = get_user(m.chat.id)
    ref_link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    msg = (f"🔗 **نظام الإحالات:**\n\nإحالاتك: `{user_data.get('referral_count', 0)}`\n"
           f"رابط دعوتك:\n`{ref_link}`")
    bot.send_message(m.chat.id, msg, parse_mode="Markdown") 

def user_dashboard(m):
    uid = str(m.chat.id)
    apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not apps: return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة.")
    
    msg = "👤 **حالة اشتراكاتك:**\n"
    for doc in apps:
        data = doc.to_dict()
        rem = data.get("end_time", 0) - time.time()
        status = f"✅ {int(rem/86400)} يوم" if rem > 0 else "❌ منتهي"
        if data.get("banned"): status = "🚫 محظور"
        msg += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📦 `{doc.id.split('_')[-1]}`\nالحالة: {status}\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown") 

def redeem_code_step(m):
    code = m.text.strip()
    days = get_voucher(code)
    if not days: return bot.send_message(m.chat.id, "❌ الكود غير صحيح.")
    uid = str(m.from_user.id)
    
    # محاولة تفعيل الكود للجهاز الحالي المفتوح من التطبيق تلقائياً
    user_data = get_user(uid)
    current_cid = user_data.get("current_app")
    
    if current_cid:
        # تنفيذ التفعيل مباشرة دون سؤال
        link = get_app_link(current_cid)
        new_time = max(time.time(), link.get("end_time", 0)) + (days * 86400)
        update_app_link(current_cid, {"end_time": new_time})
        delete_voucher(code)
        bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم لجهازك بنجاح!")
        add_log(f"تفعيل كود {days} يوم لـ {user_data.get('name')}")
    else:
        # إذا لم يكن هناك جهاز مرتبط حالياً نطلب الاختيار
        apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
        if not apps: return bot.send_message(m.chat.id, "❌ اربط جهازك أولاً.")
        update_user(uid, {"temp_code": code})
        markup = types.InlineKeyboardMarkup(row_width=1)
        for doc in apps:
            markup.add(types.InlineKeyboardButton(f"📦 {doc.id.split('_')[-1]}", callback_data=f"redeem_select_{doc.id}"))
        bot.send_message(m.chat.id, "🛠️ اختر التطبيق لتفعيله:", reply_markup=markup) 

def redeem_select_app(m, cid):
    uid = str(m.chat.id)
    user_data = get_user(uid)
    days = get_voucher(user_data.get("temp_code"))
    if days:
        link = get_app_link(cid)
        update_app_link(cid, {"end_time": max(time.time(), link.get("end_time", 0)) + (days * 86400)})
        delete_voucher(user_data["temp_code"])
        update_user(uid, {"temp_code": firestore.DELETE_FIELD})
        bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم!")
        add_log(f"تفعيل كود {days} يوم لـ {user_data.get('name')}")

def process_trial(m):
    uid = str(m.chat.id)
    apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not apps: return bot.send_message(m.chat.id, "❌ لا يوجد تطبيق مرتبط.")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for doc in apps:
        markup.add(types.InlineKeyboardButton(f"📦 {doc.id.split('_')[-1]}", callback_data=f"trial_select_{doc.id}"))
    bot.send_message(m.chat.id, "🛠️ اختر تطبيق التجربة:", reply_markup=markup) 

def trial_select_app(m, cid):
    data = get_app_link(cid)
    if not data: return
    # التحقق من مرور 24 ساعة
    if time.time() - data.get("trial_last_time", 0) < 86400:
        return bot.send_message(m.chat.id, f"❌ التجربة متاحة كل 24 ساعة لجهازك: `{cid.split('_')[-1]}`")
    
    new_time = max(time.time(), data.get("end_time", 0)) + 259200 # +3 أيام
    update_app_link(cid, {"trial_last_time": time.time(), "end_time": new_time})
    bot.send_message(m.chat.id, f"✅ تم تفعيل 3 أيام تجربة للجهاز: `{cid.split('_')[-1]}`") 

def send_payment(m):
    uid = str(m.chat.id)
    user_data = get_user(uid)
    cid = user_data.get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    
    bot.send_invoice(m.chat.id, title="اشتراك 30 يوم", description=f"تفعيل الجهاز: {cid.split('_')[-1]}", 
                     invoice_payload=f"pay_{cid}", provider_token="", currency="XTR",
                     prices=[types.LabeledPrice(label="VIP", amount=100)]) 

# --- [ خيوط الخلفية ووظائف المساعدة ] --- 

def expiry_notifier():
    while True:
        try:
            now = time.time()
            links = db_fs.collection("app_links").get()
            for doc in links:
                data = doc.to_dict()
                if 82800 < (data.get("end_time", 0) - now) < 86400:
                    uid = data.get("telegram_id")
                    if uid:
                        try: bot.send_message(uid, f"⚠️ اشتراكك في `{doc.id.split('_')[-1]}` ينتهي غداً!")
                        except: pass
            time.sleep(3600)
        except: time.sleep(60) 

def do_bc_tele(m):
    users = db_fs.collection("users").get()
    for d in users:
        try: bot.send_message(d.id, f"📢 **إعلان:**\n\n{m.text}")
        except: pass
    bot.send_message(m.chat.id, "✅ تم الإرسال.") 

def do_bc_app(m):
    set_global_news(m.text)
    bot.send_message(m.chat.id, "✅ تم تحديث الخبر.") 

def process_gen_key(m):
    if not m.text.isdigit(): return
    days = int(m.text)
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db_fs.collection("vouchers").document(code).set({"days": days})
    bot.send_message(m.chat.id, f"🎫 كود ({days} يوم):\n`{code}`", parse_mode="Markdown") 

def process_ban_unban(m, mode):
    target = m.text.strip()
    if get_app_link(target):
        update_app_link(target, {"banned": (mode == "ban_op")})
        bot.send_message(m.chat.id, "✅ تم.")
    else: bot.send_message(m.chat.id, "❌ غير موجود.") 

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True) 

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    cid = m.successful_payment.invoice_payload.replace("pay_", "")
    link = get_app_link(cid)
    if link:
        new_time = max(time.time(), link.get("end_time", 0)) + (30 * 86400)
        update_app_link(cid, {"end_time": new_time})
        bot.send_message(m.chat.id, f"✅ تم الشراء بنجاح لجهازك: {cid.split('_')[-1]}") 

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))) 

if __name__ == "__main__":
    Thread(target=run).start()
    Thread(target=expiry_notifier).start()
    bot.infinity_polling()
