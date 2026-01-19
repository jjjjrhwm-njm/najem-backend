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

# مخزن مؤقت لعملية رفع التطبيقات
upload_cache = {}

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

def check_membership(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False 

# --- [ واجهة API المحدثة - مع إضافة ميزة التسجيل التلقائي ] ---

@app.route('/app_update')
def app_update():
    pkg = request.args.get('pkg')
    aid = request.args.get('aid') # استقبال معرف الجهاز من التطبيق
    
    if not pkg: return "1\nhttps://t.me/your_channel"
    
    # --- [ "المخ": تسجيل الجهاز تلقائياً إذا كان أول مرة يفتح التطبيق ] ---
    if aid:
        cid = f"{aid}_{pkg.replace('.', '_')}"
        doc_ref = db_fs.collection("app_links").document(cid)
        if not doc_ref.get().exists:
            # إذا لم يكن السجل موجوداً، ننشئه لكي يظهر في البوت فوراً
            doc_ref.set({
                "telegram_id": None,
                "end_time": 0,
                "banned": False,
                "trial_last_time": 0,
                "gift_claimed": False,
                "created_at": time.time()
            })
    # -----------------------------------------------------------

    # جلب بيانات التحديث المخصصة لهذا التطبيق من Firebase
    doc = db_fs.collection("app_updates").document(pkg).get()
    if doc.exists:
        data = doc.to_dict()
        return f"{data.get('version', '1')}\n{data.get('url', '')}"
    
    return "1\nhttps://t.me/your_channel"

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
        
        elif q.data == "admin_update_app_start":
            list_apps_for_update(q.message)
            
        elif q.data.startswith("set_up_pkg_"):
            pkg = q.data.replace("set_up_pkg_", "")
            msg = bot.send_message(q.message.chat.id, f"تحديث التطبيق: `{pkg}`\n\nأرسل رقم الإصدار الجديد (أرقام فقط):")
            bot.register_next_step_handler(msg, process_update_version, pkg)

        elif q.data == "admin_upload_app":
            msg = bot.send_message(q.message.chat.id, "🖼️ أرسل **صورة** التطبيق الآن:")
            bot.register_next_step_handler(msg, process_upload_photo)

        elif q.data.startswith("set_target_"):
            process_key_type_selection(q)
        elif q.data.startswith("pick_u_list_"):
            list_users_for_key(q.message, q.data.split('_')[-1])
        elif q.data.startswith("pick_u_manual_"):
            days = q.data.split('_')[-1]
            msg = bot.send_message(q.message.chat.id, "ارسل ايدي (ID) المستخدم:")
            bot.register_next_step_handler(msg, lambda m: create_final_key(m, days, "user", m.text.strip()))
        elif q.data.startswith("pick_a_list_"):
            list_apps_for_key(q.message, q.data.split('_')[-1])
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
            bot.send_message(q.message.chat.id, "❗ هل أنت متأكد؟ سيتم مسح جميع المستخدمين والأجهزة والأكواد!", reply_markup=mk)
        elif q.data == "confirm_full_reset":
            wipe_all_data(q.message)
        elif q.data == "bc_tele":
            msg = bot.send_message(q.message.chat.id, "ارسل الإعلان:")
            bot.register_next_step_handler(msg, do_bc_tele)
        elif q.data == "bc_app":
            msg = bot.send_message(q.message.chat.id, "ارسل الخبر:")
            bot.register_next_step_handler(msg, do_bc_app)
        
        elif q.data in ["ban_op", "unban_op"]:
            m_type = "الحظر" if q.data == "ban_op" else "فك الحظر"
            mk = types.InlineKeyboardMarkup(row_width=1)
            mk.add(
                types.InlineKeyboardButton("📋 اختر من القائمة", callback_data=f"choice_list_{q.data}"),
                types.InlineKeyboardButton("⌨️ أرسل الآيدي يدوياً", callback_data=f"choice_manual_{q.data}")
            )
            bot.send_message(q.message.chat.id, f"يرجى تحديد طريقة {m_type}:", reply_markup=mk)
        
        elif q.data.startswith("choice_list_"):
            mode = q.data.replace("choice_list_", "")
            list_apps_for_ban(q.message, mode)
            
        elif q.data.startswith("choice_manual_"):
            mode = q.data.replace("choice_manual_", "")
            msg = bot.send_message(q.message.chat.id, "ارسل معرف الجهاز (CID) المراد معالجته:")
            bot.register_next_step_handler(msg, process_ban_unban, mode)
            
        elif q.data.startswith("exec_ban_"):
            parts = q.data.split('_')
            mode = f"{parts[2]}_{parts[3]}"
            cid = "_".join(parts[4:])
            update_app_link(cid, {"banned": (mode == "ban_op")})
            bot.send_message(q.message.chat.id, f"✅ تم تنفيذ العملية بنجاح على `{cid}`")

# --- [ بقية وظائف الإدارة ] --- 

def list_apps_for_update(m):
    apps = db_fs.collection("app_links").get()
    seen_pkgs = set()
    markup = types.InlineKeyboardMarkup()
    for a in apps:
        pkg = a.id.split('_')[-1]
        if pkg not in seen_pkgs:
            markup.add(types.InlineKeyboardButton(f"📦 {pkg}", callback_data=f"set_up_pkg_{pkg}"))
            seen_pkgs.add(pkg)
    if not seen_pkgs:
        return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة حالياً لاختيارها.")
    bot.send_message(m.chat.id, "اختر التطبيق الذي تريد تحديث إصدارة:", reply_markup=markup)

def process_update_version(m, pkg):
    version = m.text.strip()
    msg = bot.send_message(m.chat.id, "الآن أرسل رابط التحديث الجديد:")
    bot.register_next_step_handler(msg, finalize_app_update_db, pkg, version)

def finalize_app_update_db(m, pkg, version):
    url = m.text.strip()
    db_fs.collection("app_updates").document(pkg).set({
        "version": version,
        "url": url,
        "last_updated": time.time()
    })
    bot.send_message(m.chat.id, f"✅ تم اعتماد التحديث بنجاح!")

def list_apps_for_ban(m, mode):
    apps = db_fs.collection("app_links").limit(50).get()
    if not apps: return bot.send_message(m.chat.id, "لا توجد أجهزة مسجلة.")
    mk = types.InlineKeyboardMarkup(row_width=1)
    for a in apps:
        cid = a.id
        pkg = cid.split('_')[-1]
        is_banned = a.to_dict().get("banned", False)
        status_icon = "🔴" if is_banned else "🟢"
        mk.add(types.InlineKeyboardButton(f"{status_icon} {pkg} ({cid[:10]}...)", callback_data=f"exec_ban_{mode}_{cid}"))
    bot.send_message(m.chat.id, "اختر الجهاز المستهدف من القائمة:", reply_markup=mk)

def show_detailed_users(m):
    try:
        all_users = db_fs.collection("users").get()
        if not all_users: return bot.send_message(m.chat.id, "لا يوجد مستخدمين.")
        
        all_links = db_fs.collection("app_links").get()
        links_map = {}
        for l in all_links:
            ld = l.to_dict()
            u_id = ld.get("telegram_id")
            if u_id:
                if u_id not in links_map: links_map[u_id] = []
                links_map[u_id].append({"id": l.id, "data": ld})

        msg = "📂 **قائمة المشتركين وتطبيقاتهم:**\n\n"
        for user_doc in all_users:
            uid = user_doc.id
            udata = user_doc.to_dict()
            u_name = udata.get("name", "غير معروف")
            user_apps = links_map.get(uid, [])
            
            msg += f"👤 **المستخدم:** {u_name} (`{uid}`)\n"
            if not user_apps:
                msg += "└ 🚫 لا توجد تطبيقات\n"
            else:
                for app_item in user_apps:
                    rem = app_item['data'].get("end_time", 0) - time.time()
                    pkg = app_item['id'].split('_')[-1]
                    stat = "🔴 محظور" if app_item['data'].get("banned") else (f"🟢 {int(rem/86400)} يوم" if rem > 0 else "⚪ منتهي")
                    msg += f"└ 📦 `{pkg}` ⮕ {stat}\n"
            msg += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            
            if len(msg) > 3000:
                bot.send_message(m.chat.id, msg, parse_mode="Markdown")
                msg = ""
        if msg: bot.send_message(m.chat.id, msg, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(m.chat.id, f"حدث خطأ: {e}")

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
        types.InlineKeyboardButton("🆙 تحديث تطبيق", callback_data="admin_update_app_start"),
        types.InlineKeyboardButton("📤 نشر تطبيق بالقناة", callback_data="admin_upload_app"),
        types.InlineKeyboardButton("🚫 حظر", callback_data="ban_op"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="unban_op"),
        types.InlineKeyboardButton("📢 إعلان التطبيق", callback_data="bc_app"),
        types.InlineKeyboardButton("📢 إعلان تلجرام", callback_data="bc_tele"),
        types.InlineKeyboardButton("🗑️ تصفير البيانات", callback_data="reset_data_ask")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown") 

# --- [ وظائف الرفع والنشر والاشتراكات ] ---

def process_upload_photo(m):
    if not m.photo: return bot.send_message(m.chat.id, "❌ يرجى إرسال صورة.")
    upload_cache[m.from_user.id] = {"photo": m.photo[-1].file_id}
    msg = bot.send_message(m.chat.id, "📂 الآن أرسل **ملف التطبيق (APK)**:")
    bot.register_next_step_handler(msg, process_upload_file)

def process_upload_file(m):
    if not m.document: return bot.send_message(m.chat.id, "❌ يرجى إرسال ملف APK.")
    upload_cache[m.from_user.id]["file"] = m.document.file_id
    msg = bot.send_message(m.chat.id, "✍️ أرسل **وصف التطبيق**:")
    bot.register_next_step_handler(msg, process_upload_desc)

def process_upload_desc(m):
    uid = m.from_user.id
    if uid not in upload_cache: return
    decorated_desc = f"🌟 **نجم الإبداع يقدم لكم** 🌟\n\n🚀 **{m.text}**\n\n📥 **حمل الآن واستمتع بالتجربة!**"
    try:
        file_msg = bot.send_document(CHANNEL_ID, upload_cache[uid]["file"], disable_notification=True)
        file_link = f"https://t.me/{CHANNEL_ID.replace('@','')}/{file_msg.message_id}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📥 تنزيل التطبيق الآن", url=file_link))
        bot.send_photo(CHANNEL_ID, upload_cache[uid]["photo"], caption=decorated_desc, reply_markup=markup, parse_mode="Markdown")
        bot.send_message(m.chat.id, "✅ تم النشر!")
        del upload_cache[uid]
    except Exception as e: bot.send_message(m.chat.id, f"❌ خطأ: {e}")

def show_referral_info(m):
    user_data = get_user(m.chat.id)
    ref_link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    bot.send_message(m.chat.id, f"🔗 **نظام الإحالات:**\n\nإحالاتك: `{user_data.get('referral_count', 0)}`\nرابط دعوتك:\n`{ref_link}`", parse_mode="Markdown") 

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
    vdata = get_voucher(code)
    if not vdata: return bot.send_message(m.chat.id, "❌ الكود غير صحيح.")
    uid = str(m.from_user.id)
    user_data = get_user(uid)
    apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not apps: return bot.send_message(m.chat.id, "❌ اربط جهازك أولاً.")
    update_user(uid, {"temp_code": code})
    markup = types.InlineKeyboardMarkup(row_width=1)
    for doc in apps: markup.add(types.InlineKeyboardButton(f"📦 {doc.id.split('_')[-1]}", callback_data=f"redeem_select_{doc.id}"))
    bot.send_message(m.chat.id, "🛠️ اختر التطبيق لتفعيله:", reply_markup=markup) 

def redeem_select_app(m, cid):
    uid = str(m.chat.id)
    user_data = get_user(uid)
    vdata = get_voucher(user_data.get("temp_code"))
    if vdata:
        days = vdata.get("days")
        link = get_app_link(cid)
        update_app_link(cid, {"end_time": max(time.time(), link.get("end_time", 0)) + (days * 86400)})
        delete_voucher(user_data["temp_code"])
        update_user(uid, {"temp_code": firestore.DELETE_FIELD})
        bot.send_message(m.chat.id, f"✅ تم التفعيل!")

def process_trial(m):
    uid = str(m.chat.id)
    apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not apps: return bot.send_message(m.chat.id, "❌ لا يوجد تطبيق مرتبط.")
    markup = types.InlineKeyboardMarkup(row_width=1)
    for doc in apps: markup.add(types.InlineKeyboardButton(f"📦 {doc.id.split('_')[-1]}", callback_data=f"trial_select_{doc.id}"))
    bot.send_message(m.chat.id, "🛠️ اختر تطبيق التجربة:", reply_markup=markup) 

def trial_select_app(m, cid):
    data = get_app_link(cid)
    if not data: return
    if time.time() - data.get("trial_last_time", 0) < 86400:
        return bot.send_message(m.chat.id, "❌ التجربة متاحة كل 24 ساعة.")
    update_app_link(cid, {"trial_last_time": time.time(), "end_time": max(time.time(), data.get("end_time", 0)) + 259200})
    bot.send_message(m.chat.id, "✅ تم تفعيل التجربة!") 

def send_payment(m):
    user_data = get_user(str(m.chat.id))
    cid = user_data.get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    bot.send_invoice(m.chat.id, title="اشتراك 30 يوم", description=f"تفعيل: {cid.split('_')[-1]}", 
                     invoice_payload=f"pay_{cid}", provider_token="", currency="XTR",
                     prices=[types.LabeledPrice(label="VIP", amount=100)]) 

def wipe_all_data(m):
    for coll in ["users", "app_links", "logs", "vouchers", "app_updates"]:
        for d in db_fs.collection(coll).get(): d.reference.delete()
    bot.send_message(m.chat.id, "✅ تم التصفير.")

def process_gen_key_start(m):
    if not m.text.isdigit(): return
    days = int(m.text)
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("🌍 كود عام", callback_data=f"set_target_all_{days}"))
    mk.add(types.InlineKeyboardButton("📦 لتطبيق معين", callback_data=f"set_target_app_{days}"))
    mk.add(types.InlineKeyboardButton("👤 لشخص معين", callback_data=f"set_target_user_{days}"))
    bot.send_message(m.chat.id, "اختر نوع الكود:", reply_markup=mk)

def process_key_type_selection(q):
    _, _, target, days = q.data.split('_')
    if target == "all": create_final_key(q.message, days, "all", None)
    elif target == "app": list_apps_for_key(q.message, days)
    elif target == "user": list_users_for_key(q.message, days)

def list_users_for_key(m, days):
    users = db_fs.collection("users").limit(30).get()
    mk = types.InlineKeyboardMarkup(row_width=1)
    for u in users: mk.add(types.InlineKeyboardButton(f"👤 {u.to_dict().get('name')}", callback_data=f"gen_for_u_{u.id}_{days}"))
    bot.send_message(m.chat.id, "اختر المستخدم:", reply_markup=mk)

def list_apps_for_key(m, days):
    apps = db_fs.collection("app_links").limit(30).get()
    mk = types.InlineKeyboardMarkup(row_width=1)
    seen = set()
    for a in apps:
        p = a.id.split('_')[-1]
        if p not in seen:
            mk.add(types.InlineKeyboardButton(f"📦 {p}", callback_data=f"gen_for_a_{a.id}_{days}"))
            seen.add(p)
    bot.send_message(m.chat.id, "اختر التطبيق:", reply_markup=mk)

def create_final_key(m, days, target, target_id):
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db_fs.collection("vouchers").document(code).set({"days": int(days), "target": target, "target_id": target_id})
    bot.send_message(m.chat.id, f"🎫 **كود جديد:** `{code}`")

def expiry_notifier():
    while True:
        try:
            for doc in db_fs.collection("app_links").get():
                data = doc.to_dict()
                if 82800 < (data.get("end_time", 0) - time.time()) < 86400:
                    if data.get("telegram_id"): bot.send_message(data["telegram_id"], f"⚠️ ينتهي اشتراكك في {doc.id.split('_')[-1]} غداً!")
            time.sleep(3600)
        except: time.sleep(60) 

def do_bc_tele(m):
    for d in db_fs.collection("users").get():
        try: bot.send_message(d.id, f"📢 **إعلان:**\n\n{m.text}")
        except: pass

def do_bc_app(m): set_global_news(m.text)

def process_ban_unban(m, mode):
    update_app_link(m.text.strip(), {"banned": (mode == "ban_op")})
    bot.send_message(m.chat.id, "✅ تم.")

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True) 

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    cid = m.successful_payment.invoice_payload.replace("pay_", "")
    update_app_link(cid, {"end_time": max(time.time(), get_app_link(cid).get("end_time", 0)) + (30 * 86400)})
    bot.send_message(m.chat.id, "✅ تم الشراء!") 

def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))) 

if __name__ == "__main__":
    Thread(target=run).start()
    Thread(target=expiry_notifier).start()
    bot.infinity_polling()
