import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread
import firebase_admin
from firebase_admin import credentials, firestore

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
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
    else:
        user_data["name"] = username 
        update_user(uid, {"name": username})

    if len(args) > 1 and "_" in args[1]:
        cid = args[1]
        link_data = get_app_link(cid)
        if not link_data:
            link_data = {"end_time": 0, "banned": False, "trial_last_time": 0, "telegram_id": uid, "gift_claimed": False}
        
        link_data["telegram_id"] = uid
        update_user(uid, {"current_app": cid})
        
        if check_membership(uid) and not link_data.get("gift_claimed"):
            link_data["end_time"] = max(time.time(), link_data.get("end_time", 0)) + (3 * 86400)
            link_data["gift_claimed"] = True
            bot.send_message(m.chat.id, "🎁 **مبروك! حصلت على 3 أيام مجانية لانضمامك لقناتنا.**", parse_mode="Markdown")
            
            inviter = user_data.get("invited_by")
            if inviter:
                inv_data = get_user(inviter)
                if inv_data:
                    inv_app_cid = inv_data.get("current_app")
                    if inv_app_cid:
                        inv_link = get_app_link(inv_app_cid)
                        if inv_link:
                            inv_link["end_time"] = inv_link.get("end_time", 0) + (7 * 86400)
                            update_app_link(inv_app_cid, {"end_time": inv_link["end_time"]})
                            update_user(inviter, {"referral_count": inv_data.get("referral_count", 0) + 1})
                            try: bot.send_message(inviter, f"🎊 شخص دعوته انضم وربط جهازه! حصلت على **7 أيام** إضافية.", parse_mode="Markdown")
                            except: pass
        
        update_app_link(cid, link_data)
        bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**", parse_mode="Markdown")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
        types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
        types.InlineKeyboardButton("🔗 إحالاتي ومكافآتي", callback_data="u_referral"),
        types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
        types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy")
    )
    bot.send_message(m.chat.id, f"مرحباً بك يا **{username}** 🌟\nقناتنا: {CHANNEL_ID}\nاستخدم القائمة أدناه للتحكم في اشتراكاتك:", reply_markup=markup, parse_mode="Markdown") 

# --- [ تعديل الأوامر النصية المباشرة ] ---

@bot.message_handler(func=lambda m: m.text == "تجربه")
def cmd_trial(m):
    process_trial(m)

@bot.message_handler(func=lambda m: m.text == "اشتراك")
def cmd_buy(m):
    send_payment(m)

@bot.message_handler(func=lambda m: m.text == "اشتراكاتي")
def cmd_dash(m):
    user_dashboard(m)

@bot.message_handler(func=lambda m: m.text == "تفعيل كود")
def cmd_redeem(m):
    msg = bot.send_message(m.chat.id, "🎫 **أرسل كود التفعيل الآن:**")
    bot.register_next_step_handler(msg, redeem_code_step)

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel_text(m):
    admin_panel(m)

# --- [ معالجة ضغطات الأزرار ] ---
@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)

    if q.data == "u_dashboard":
        user_dashboard(q.message)
    elif q.data == "u_referral":
        show_referral_info(q.message)
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
        send_payment(q.message) 

    elif q.from_user.id == ADMIN_ID:
        if q.data == "list_all":
            show_detailed_users(q.message)
        elif q.data == "admin_logs":
            show_logs(q.message)
        elif q.data == "top_ref":
            show_top_referrers(q.message)
        elif q.data == "gen_key":
            msg = bot.send_message(q.message.chat.id, "كم عدد الأيام التي تريدها لهذا الكود؟")
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

# --- [ وظائف الإدارة - تم إصلاح "المشتركين" و "السجلات" هنا ] --- 

def show_detailed_users(m):
    try:
        links = db_fs.collection("app_links").get()
        if not links: return bot.send_message(m.chat.id, "لا توجد أجهزة مسجلة.")
        full_list = "📂 <b>إحصائيات الأجهزة:</b>\n\n"
        for doc in links:
            cid = doc.id
            data = doc.to_dict()
            owner_data = get_user(data.get("telegram_id", ""))
            owner_name = owner_data.get("name", "غير معروف") if owner_data else "غير معروف"
            rem_time = data.get("end_time", 0) - time.time()
            stat = "🔴 محظور" if data.get("banned") else (f"🟢 {int(rem_time/86400)} يوم" if rem_time > 0 else "⚪ منتهي")
            
            # تم استخدام HTML لتجنب أخطاء الرموز الخاصة في المعرفات
            full_list += f"👤: {owner_name} | {stat}\n🆔: <code>{cid}</code>\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            
            if len(full_list) > 3000:
                bot.send_message(m.chat.id, full_list, parse_mode="HTML")
                full_list = ""
        if full_list: bot.send_message(m.chat.id, full_list, parse_mode="HTML")
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ حدث خطأ في جلب البيانات: {str(e)}")

def show_logs(m):
    try:
        logs_ref = db_fs.collection("logs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(15).get()
        logs_list = [doc.to_dict().get("text") for doc in logs_ref]
        logs_text = "\n".join(logs_list) if logs_list else "لا توجد سجلات."
        # استخدام HTML لضمان عدم توقف الزر عند وجود رموز خاصة في السجلات
        bot.send_message(m.chat.id, f"📝 <b>آخر العمليات:</b>\n\n{logs_text}", parse_mode="HTML")
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ حدث خطأ في السجلات: {str(e)}")

def show_top_referrers(m):
    users_ref = db_fs.collection("users").order_by("referral_count", direction=firestore.Query.DESCENDING).limit(10).get()
    msg = "🏆 **أفضل 10 داعين للبوت:**\n\n"
    for i, doc in enumerate(users_ref, 1):
        data = doc.to_dict()
        msg += f"{i}- {data.get('name', 'User')} ⮕ `{data.get('referral_count', 0)}` إحالة\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown") 

def admin_panel(m):
    users_count = len(db_fs.collection("users").get())
    links_all = db_fs.collection("app_links").get()
    links_count = len(links_all)
    active_now = sum(1 for doc in links_all if doc.to_dict().get("end_time", 0) > time.time())
    
    msg = (f"👑 **إدارة نجم الإبداع**\n\n"
           f"👥 المستخدمين: `{users_count}` | الأجهزة: `{links_count}`\n"
           f"🟢 النشطين: `{active_now}`\n")
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
    uid = str(m.chat.id)
    user_data = get_user(uid)
    if not user_data: return
    ref_link = f"https://t.me/{bot.get_me().username}?start={uid}"
    count = user_data.get("referral_count", 0)
    msg = (f"🔗 **نظام الإحالات:**\n\n"
           f"كل شخص يدخل من رابطك وينضم للقناة ويربط جهازه، ستحصل أنت على **7 أيام مجانية!**\n\n"
           f"👥 عدد إحالاتك الناجحة: `{count}`\n"
           f"🎁 إجمالي الأيام المكتسبة: `{count * 7}` يوم\n\n"
           f"رابط دعوتك:\n`{ref_link}`")
    bot.send_message(m.chat.id, msg, parse_mode="Markdown") 

def user_dashboard(m):
    uid = str(m.chat.id)
    user_apps_ref = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not user_apps_ref: return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة.")
    
    msg = "👤 **حالة اشتراكاتك:**\n"
    for doc in user_apps_ref:
        cid = doc.id
        data = doc.to_dict()
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        rem_time = data.get("end_time", 0) - time.time()
        status = f"✅ {int(rem_time/86400)} يوم" if rem_time > 0 else "❌ منتهي"
        if data.get("banned"): status = "🚫 محظور"
        msg += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📦 `{pkg}`\nالحالة: {status}\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown") 

def redeem_code_step(m):
    code = m.text.strip()
    days = get_voucher(code)
    if not days: return bot.send_message(m.chat.id, "❌ الكود غير صحيح.")
    
    uid = str(m.from_user.id)
    user_apps_ref = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not user_apps_ref: return bot.send_message(m.chat.id, "❌ اربط جهازك أولاً.")
    
    update_user(uid, {"temp_code": code})
    markup = types.InlineKeyboardMarkup(row_width=1)
    for doc in user_apps_ref:
        cid = doc.id
        markup.add(types.InlineKeyboardButton(f"📦 {cid.split('_')[-1]}", callback_data=f"redeem_select_{cid}"))
    bot.send_message(m.chat.id, "🛠️ اختر التطبيق لتفعيل الكود:", reply_markup=markup) 

def redeem_select_app(m, selected_cid):
    uid = str(m.chat.id)
    user_data = get_user(uid)
    code = user_data.get("temp_code")
    if not code: return bot.send_message(m.chat.id, "❌ انتهت الجلسة.")
    
    days = get_voucher(code)
    if not days: return bot.send_message(m.chat.id, "❌ الكود مستخدم أو غير صالح.")
    
    link_data = get_app_link(selected_cid)
    new_end_time = max(time.time(), link_data.get("end_time", 0)) + (days * 86400)
    update_app_link(selected_cid, {"end_time": new_end_time})
    delete_voucher(code)
    update_user(uid, {"temp_code": firestore.DELETE_FIELD})
    
    add_log(f"تفعيل كود ({days} يوم) للمستخدم {user_data.get('name')}")
    bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم بنجاح!") 

def process_trial(m):
    uid = str(m.chat.id)
    user_apps_ref = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not user_apps_ref: return bot.send_message(m.chat.id, "❌ لا يوجد تطبيق مرتبط.")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for doc in user_apps_ref:
        cid = doc.id
        markup.add(types.InlineKeyboardButton(f"📦 {cid.split('_')[-1]}", callback_data=f"trial_select_{cid}"))
    bot.send_message(m.chat.id, "🛠️ اختر تطبيق التجربة:", reply_markup=markup) 

def trial_select_app(m, selected_cid):
    data = get_app_link(selected_cid)
    if not data: return
    if time.time() - data.get("trial_last_time", 0) < 86400:
        return bot.send_message(m.chat.id, "❌ التجربة متاحة مرة كل 24 ساعة.")
    
    new_end_time = max(time.time(), data.get("end_time", 0)) + 259200
    update_app_link(selected_cid, {"trial_last_time": time.time(), "end_time": new_end_time})
    bot.send_message(m.chat.id, "✅ تم تفعيل 3 أيام تجربة!") 

def send_payment(m):
    uid = str(m.chat.id)
    user_data = get_user(uid)
    cid = user_data.get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ افتح التطبيق أولاً.")
    bot.send_invoice(m.chat.id, title="اشتراك 30 يوم", description=f"الحساب: {cid}", 
                     invoice_payload=f"pay_{cid}", provider_token="", currency="XTR",
                     prices=[types.LabeledPrice(label="VIP", amount=100)]) 

# --- [ خيوط الخلفية (Background Threads) ] --- 

def expiry_notifier():
    while True:
        try:
            now = time.time()
            links = db_fs.collection("app_links").get()
            for doc in links:
                data = doc.to_dict()
                cid = doc.id
                rem = data.get("end_time", 0) - now
                if 82800 < rem < 86400:
                    uid = data.get("telegram_id")
                    if uid:
                        try: bot.send_message(uid, f"⚠️ تنبيه: اشتراكك في التطبيق `{cid.split('_')[-1]}` سينتهي خلال 24 ساعة!")
                        except: pass
            time.sleep(3600)
        except: time.sleep(60) 

# --- [ وظائف مساعدة ] ---
def do_bc_tele(m):
    users = db_fs.collection("users").get()
    count = 0
    for doc in users:
        try: bot.send_message(doc.id, f"📢 **إعلان:**\n\n{m.text}"); count += 1
        except: pass
    bot.send_message(m.chat.id, f"✅ تم الإرسال لـ {count}") 

def do_bc_app(m):
    set_global_news(m.text)
    bot.send_message(m.chat.id, "✅ تم تحديث خبر التطبيق.") 

def process_gen_key(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "⚠️ أرسل رقماً.")
    days = int(m.text)
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db_fs.collection("vouchers").document(code).set({"days": days})
    add_log(f"توليد كود جديد {days} يوم")
    bot.send_message(m.chat.id, f"🎫 كود جديد ({days} يوم):\n`{code}`", parse_mode="Markdown") 

def process_ban_unban(m, mode):
    target = m.text.strip()
    link_data = get_app_link(target)
    if link_data:
        update_app_link(target, {"banned": (mode == "ban_op")})
        add_log(f"{'حظر' if mode=='ban_op' else 'فك حظر'} الجهاز {target}")
        bot.send_message(m.chat.id, "✅ تمت العملية.")
    else: bot.send_message(m.chat.id, "❌ المعرف غير موجود.") 

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True) 

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    cid = m.successful_payment.invoice_payload.replace("pay_", "")
    link_data = get_app_link(cid)
    if link_data:
        new_time = max(time.time(), link_data.get("end_time", 0)) + (30 * 86400)
        update_app_link(cid, {"end_time": new_time})
        add_log(f"شراء اشتراك 30 يوم للجهاز {cid}")
        bot.send_message(m.chat.id, "✅ تم الشراء بنجاح!") 

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))) 

if __name__ == "__main__":
    Thread(target=run).start()
    Thread(target=expiry_notifier).start()
    bot.infinity_polling()
