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
    return doc.to_dict() if doc.exists else None

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

# وظائف التحديث المحسنة (لحل مشكلة NONE)
def get_update_info(pkg):
    if not pkg: return "NONE"
    # تنظيف النص وتحويل النقاط لشرطات للمطابقة
    pkg_fixed = pkg.strip().replace('.', '_')
    doc = db_fs.collection("updates").document(pkg_fixed).get()
    if doc.exists:
        url = doc.to_dict().get("url")
        if url and str(url).strip().upper() != "NONE":
            return str(url).strip()
    return "NONE"

def set_update_info(pkg, url):
    if not pkg: return
    pkg_fixed = pkg.strip().replace('.', '_')
    db_fs.collection("updates").document(pkg_fixed).set({"url": str(url).strip()}, merge=True)

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

# رابط التحديث للسمالي
@app.route('/get_update')
def get_update():
    pkg = request.args.get('pkg')
    return get_update_info(pkg)

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

    if len(args) > 1:
        param = args[1]
        action = "LINK"; cid = ""

        if param.startswith("TRIAL_"): action = "TRIAL"; cid = param.replace("TRIAL_", "")
        elif param.startswith("BUY_"): action = "BUY"; cid = param.replace("BUY_", "")
        elif param.startswith("DASH_"): action = "DASH"; cid = param.replace("DASH_", "")
        elif param.startswith("REDEEM_"): action = "REDEEM"; cid = param.replace("REDEEM_", "")
        else: cid = param 

        if "_" in cid:
            link_data = get_app_link(cid) or {"end_time": 0, "banned": False, "trial_last_time": 0, "gift_claimed": False}
            link_data["telegram_id"] = uid
            update_app_link(cid, link_data)
            update_user(uid, {"current_app": cid})
            
            if check_membership(uid) and not link_data.get("gift_claimed"):
                link_data["end_time"] = max(time.time(), link_data.get("end_time", 0)) + (3 * 86400)
                link_data["gift_claimed"] = True
                update_app_link(cid, link_data)
                bot.send_message(m.chat.id, "🎁 تم منحك 3 أيام هدية لانضمامك للقناة!")
                
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

            if action == "TRIAL": return trial_select_app(m, cid)
            elif action == "BUY": return send_payment(m)
            elif action == "DASH": return user_dashboard(m)
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
        types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy")
    )
    bot.send_message(m.chat.id, f"مرحباً بك يا **{username}** 🌟\nاستخدم القائمة للتحكم أو اطلب من داخل التطبيق:", reply_markup=markup, parse_mode="Markdown")

# --- [ معالجة ضغطات الأزرار ] ---
@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    # أوامر المستخدم
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
    
    # أوامر الأدمن
    elif q.from_user.id == ADMIN_ID:
        if q.data == "list_all": show_detailed_users(q.message)
        elif q.data == "admin_logs": show_logs(q.message)
        elif q.data == "top_ref": show_top_referrers(q.message)
        elif q.data == "gen_key":
            msg = bot.send_message(q.message.chat.id, "كم عدد الأيام؟")
            bot.register_next_step_handler(msg, process_gen_key_start)
        
        # --- [ نظام التحديثات الجديد ] ---
        elif q.data == "upd_manage":
            mk = types.InlineKeyboardMarkup(row_width=1)
            mk.add(types.InlineKeyboardButton("📋 اختيار من التطبيقات الحالية", callback_data="upd_list"),
                   types.InlineKeyboardButton("⌨️ إدخال اسم التطبيق يدوياً", callback_data="upd_manual"))
            bot.send_message(q.message.chat.id, "⚙️ **إدارة التحديثات:**\nاختر الطريقة لتحديد التطبيق:", reply_markup=mk)
        
        elif q.data == "upd_list":
            list_apps_for_update(q.message)
            
        elif q.data == "upd_manual":
            msg = bot.send_message(q.message.chat.id, "⌨️ ارسل اسم حزمة التطبيق (Package ID):\nمثال: `com.njm.rashed`")
            bot.register_next_step_handler(msg, process_upd_manual_pkg)
            
        elif q.data.startswith("exec_upd_"):
            pkg = q.data.replace("exec_upd_", "").replace('_', '.')
            msg = bot.send_message(q.message.chat.id, f"🔗 ارسل رابط التحديث الجديد لـ:\n`{pkg}`\n\n(ارسل `NONE` لإلغاء التحديث)")
            bot.register_next_step_handler(msg, lambda m: finalize_update_step(m, pkg))

        # باقي أوامر الأدمن الأصلية
        elif q.data.startswith("set_target_"): process_key_type_selection(q)
        elif q.data.startswith("pick_u_list_"): list_users_for_key(q.message, q.data.split('_')[-1])
        elif q.data.startswith("pick_u_manual_"):
            days = q.data.split('_')[-1]
            msg = bot.send_message(q.message.chat.id, "ارسل ايدي (ID) المستخدم:")
            bot.register_next_step_handler(msg, lambda m: create_final_key(m, days, "user", m.text.strip()))
        elif q.data.startswith("pick_a_list_"): list_apps_for_key(q.message, q.data.split('_')[-1])
        elif q.data.startswith("pick_a_manual_"):
            days = q.data.split('_')[-1]
            msg = bot.send_message(q.message.chat.id, "ارسل اسم حزمة التطبيق (Package ID):")
            bot.register_next_step_handler(msg, lambda m: create_final_key(m, days, "app", m.text.strip()))
        elif q.data.startswith("gen_for_u_"):
            _, _, _, uid_target, days = q.data.split('_')
            create_final_key(q.message, days, "user", uid_target)
        elif q.data.startswith("gen_for_a_"):
            parts = q.data.split('_')
            days = parts[-1]
            cid_target = "_".join(parts[3:-1])
            create_final_key(q.message, days, "app", cid_target)
        elif q.data == "reset_data_ask":
            mk = types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("⚠️ نعم، احذف كل شيء", callback_data="confirm_full_reset"))
            bot.send_message(q.message.chat.id, "❗ هل أنت متأكد؟", reply_markup=mk)
        elif q.data == "confirm_full_reset": wipe_all_data(q.message)
        elif q.data == "bc_tele":
            msg = bot.send_message(q.message.chat.id, "ارسل الإعلان:")
            bot.register_next_step_handler(msg, do_bc_tele)
        elif q.data == "bc_app":
            msg = bot.send_message(q.message.chat.id, "ارسل الخبر:")
            bot.register_next_step_handler(msg, do_bc_app)
        elif q.data in ["ban_op", "unban_op"]:
            m_type = "الحظر" if q.data == "ban_op" else "فك الحظر"
            mk = types.InlineKeyboardMarkup(row_width=1)
            mk.add(types.InlineKeyboardButton("📋 اختر من القائمة", callback_data=f"choice_list_{q.data}"),
                   types.InlineKeyboardButton("⌨️ أرسل الآيدي يدوياً", callback_data=f"choice_manual_{q.data}"))
            bot.send_message(q.message.chat.id, f"يرجى تحديد طريقة {m_type}:", reply_markup=mk)
        elif q.data.startswith("choice_list_"): list_apps_for_ban(q.message, q.data.replace("choice_list_", ""))
        elif q.data.startswith("choice_manual_"):
            mode = q.data.replace("choice_manual_", "")
            msg = bot.send_message(q.message.chat.id, "ارسل معرف الجهاز (CID):")
            bot.register_next_step_handler(msg, process_ban_unban, mode)
        elif q.data.startswith("exec_ban_"):
            parts = q.data.split('_')
            mode = f"{parts[2]}_{parts[3]}"
            cid = "_".join(parts[4:])
            update_app_link(cid, {"banned": (mode == "ban_op")})
            bot.send_message(q.message.chat.id, f"✅ تم تنفيذ العملية على `{cid}`")

# --- [ وظائف الإدارة ] --- 

def list_apps_for_update(m):
    apps = db_fs.collection("app_links").limit(30).get()
    if not apps: return bot.send_message(m.chat.id, "لا توجد تطبيقات.")
    mk = types.InlineKeyboardMarkup(row_width=1); seen_pkgs = set()
    for a in apps:
        pkg = a.id.split('_')[-1]
        if pkg not in seen_pkgs:
            mk.add(types.InlineKeyboardButton(f"📦 {pkg}", callback_data=f"exec_upd_{pkg.replace('.', '_')}"))
            seen_pkgs.add(pkg)
    bot.send_message(m.chat.id, "اختر التطبيق المراد تحديثه:", reply_markup=mk)

def process_upd_manual_pkg(m):
    pkg = m.text.strip(); msg = bot.send_message(m.chat.id, f"🔗 ارسل رابط التحديث لـ `{pkg}`:")
    bot.register_next_step_handler(msg, lambda m_url: finalize_update_step(m_url, pkg))

def finalize_update_step(m, pkg):
    url = m.text.strip(); set_update_info(pkg, url)
    bot.send_message(m.chat.id, f"✅ تم حفظ رابط التحديث لـ `{pkg}`")

def list_apps_for_ban(m, mode):
    apps = db_fs.collection("app_links").limit(50).get()
    mk = types.InlineKeyboardMarkup(row_width=1)
    for a in apps:
        cid = a.id; pkg = cid.split('_')[-1]; is_banned = a.to_dict().get("banned", False)
        status_icon = "🔴" if is_banned else "🟢"
        mk.add(types.InlineKeyboardButton(f"{status_icon} {pkg} ({cid[:10]}...)", callback_data=f"exec_ban_{mode}_{cid}"))
    bot.send_message(m.chat.id, "اختر الجهاز:", reply_markup=mk)

def show_detailed_users(m):
    try:
        all_users = db_fs.collection("users").get()
        msg = "📂 **قائمة المشتركين:**\n\n"
        for user_doc in all_users:
            msg += f"👤 {user_doc.to_dict().get('name')} (`{user_doc.id}`)\n"
        bot.send_message(m.chat.id, msg, parse_mode="Markdown")
    except: pass

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
    msg = f"👑 **إدارة نجم الإبداع**\n\n👥 المستخدمين: `{users_count}`"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 المشتركين", callback_data="list_all"),
        types.InlineKeyboardButton("📝 السجلات", callback_data="admin_logs"),
        types.InlineKeyboardButton("🏆 المتصدرين", callback_data="top_ref"),
        types.InlineKeyboardButton("🎫 كود جديد", callback_data="gen_key"),
        types.InlineKeyboardButton("🔄 إدارة التحديثات", callback_data="upd_manage"),
        types.InlineKeyboardButton("🚫 حظر", callback_data="ban_op"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="unban_op"),
        types.InlineKeyboardButton("📢 إعلان التطبيق", callback_data="bc_app"),
        types.InlineKeyboardButton("📢 إعلان تلجرام", callback_data="bc_tele"),
        types.InlineKeyboardButton("🗑️ تصفير البيانات", callback_data="reset_data_ask")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown") 

# --- [ منطق المستخدم ] --- 

def show_referral_info(m):
    ref_link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    bot.send_message(m.chat.id, f"🔗 رابط دعوتك:\n`{ref_link}`", parse_mode="Markdown") 

def user_dashboard(m):
    apps = db_fs.collection("app_links").where("telegram_id", "==", str(m.chat.id)).get()
    if not apps: return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة.")
    msg = "👤 **حالة اشتراكاتك:**\n"
    for doc in apps:
        rem = doc.to_dict().get("end_time", 0) - time.time(); status = f"✅ {int(rem/86400)} يوم" if rem > 0 else "❌ منتهي"
        msg += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📦 `{doc.id.split('_')[-1]}`\nالحالة: {status}\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown") 

def redeem_code_step(m):
    code = m.text.strip(); vdata = get_voucher(code)
    if not vdata: return bot.send_message(m.chat.id, "❌ الكود غير صحيح.")
    uid = str(m.from_user.id); days = vdata.get("days"); user_data = get_user(uid)
    cid = user_data.get("current_app")
    if cid:
        link = get_app_link(cid); new_time = max(time.time(), link.get("end_time", 0)) + (days * 86400)
        update_app_link(cid, {"end_time": new_time}); delete_voucher(code)
        bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم بنجاح!")
    else:
        apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
        if not apps: return bot.send_message(m.chat.id, "❌ اربط جهازك أولاً.")
        update_user(uid, {"temp_code": code}); markup = types.InlineKeyboardMarkup(row_width=1)
        for doc in apps: markup.add(types.InlineKeyboardButton(f"📦 {doc.id.split('_')[-1]}", callback_data=f"redeem_select_{doc.id}"))
        bot.send_message(m.chat.id, "🛠️ اختر التطبيق:", reply_markup=markup) 

def redeem_select_app(m, cid):
    vdata = get_voucher(get_user(m.chat.id).get("temp_code"))
    if vdata:
        update_app_link(cid, {"end_time": max(time.time(), get_app_link(cid).get("end_time", 0)) + (vdata.get("days") * 86400)})
        delete_voucher(get_user(m.chat.id).get("temp_code")); update_user(m.chat.id, {"temp_code": firestore.DELETE_FIELD})
        bot.send_message(m.chat.id, "✅ تم التفعيل!")

def process_trial(m):
    apps = db_fs.collection("app_links").where("telegram_id", "==", str(m.chat.id)).get()
    if not apps: return bot.send_message(m.chat.id, "❌ لا يوجد تطبيق.")
    markup = types.InlineKeyboardMarkup(row_width=1)
    for doc in apps: markup.add(types.InlineKeyboardButton(f"📦 {doc.id.split('_')[-1]}", callback_data=f"trial_select_{doc.id}"))
    bot.send_message(m.chat.id, "🛠️ اختر التطبيق:", reply_markup=markup) 

def trial_select_app(m, cid):
    data = get_app_link(cid)
    if time.time() - data.get("trial_last_time", 0) < 86400: return bot.send_message(m.chat.id, "❌ التجربة متاحة كل 24 ساعة.")
    update_app_link(cid, {"trial_last_time": time.time(), "end_time": max(time.time(), data.get("end_time", 0)) + 259200})
    bot.send_message(m.chat.id, "✅ تم تفعيل التجربة!") 

def send_payment(m):
    cid = get_user(m.chat.id).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ اربط التطبيق.")
    bot.send_invoice(m.chat.id, title="اشتراك 30 يوم", description=f"تفعيل: {cid.split('_')[-1]}", invoice_payload=f"pay_{cid}", provider_token="", currency="XTR", prices=[types.LabeledPrice(label="VIP", amount=100)]) 

def wipe_all_data(m):
    for coll in ["users", "app_links", "logs", "vouchers"]:
        for d in db_fs.collection(coll).get(): d.reference.delete()
    bot.send_message(m.chat.id, "✅ تم التصفير.")

def process_gen_key_start(m):
    if not m.text.isdigit(): return; days = int(m.text)
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db_fs.collection("vouchers").document(code).set({"days": days, "target": "all"})
    bot.send_message(m.chat.id, f"🎫 الكود: `{code}`", parse_mode="Markdown")

def expiry_notifier():
    while True:
        try:
            links = db_fs.collection("app_links").get()
            for doc in links:
                if 82800 < (doc.to_dict().get("end_time", 0) - time.time()) < 86400:
                    try: bot.send_message(doc.to_dict().get("telegram_id"), "⚠️ اشتراكك ينتهي غداً!")
                    except: pass
            time.sleep(3600)
        except: time.sleep(60) 

def do_bc_tele(m):
    for d in db_fs.collection("users").get():
        try: bot.send_message(d.id, f"📢 إعلان:\n\n{m.text}")
        except: pass

def do_bc_app(m): set_global_news(m.text)

def process_ban_unban(m, mode):
    update_app_link(m.text.strip(), {"banned": (mode == "ban_op")})
    bot.send_message(m.chat.id, "✅ تم.")

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True) 

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    cid = m.successful_payment.invoice_payload.replace("pay_", ""); link = get_app_link(cid)
    if link: update_app_link(cid, {"end_time": max(time.time(), link.get("end_time", 0)) + (30 * 86400)})

def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))) 

if __name__ == "__main__":
    Thread(target=run).start(); Thread(target=expiry_notifier).start(); bot.infinity_polling()
