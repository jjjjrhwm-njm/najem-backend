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

# وظيفة مساعدة لجلب أسماء التطبيقات المخصصة للبوت حصراً
def get_bot_names_map():
    docs = db_fs.collection("bot_names_manifest").get()
    return {d.id: d.to_dict().get("display_name", d.id) for d in docs}

# وظيفة مساعدة لجلب كافة الأسماء المستعارة (الألقاب) لضمان سرعة البوت
def get_all_app_names():
    apps = db_fs.collection("update_manifest").get()
    return {a.id: a.to_dict().get("display_name", a.id) for a in apps}

# --- [ واجهة API الجديدة لطلب القفل - السمالي ] ---

@app.route('/')
def lock_code_api():
    pkg = request.args.get('pkg')
    if not pkg: return "INFO\nINFO\nOFF\nhttps://t.me/jrhwm0njm"
    
    lock_ref = db_fs.collection("lock_manifest").document(pkg)
    doc = lock_ref.get()
    
    if not doc.exists:
        # تسجيل تلقائي للتطبيق في نظام القفل
        lock_ref.set({
            "display_name": pkg,
            "lock_code": "OFF",
            "lock_link": "https://t.me/jrhwm0njm",
            "registered_at": time.time()
        })
        return "INFO\nINFO\nOFF\nhttps://t.me/jrhwm0njm"
    
    d = doc.to_dict()
    # السمالي يتوقع الكود في السطر الثالث والرابط في الرابع
    return f"NJM\nSTORE\n{d.get('lock_code', 'OFF')}\n{d.get('lock_link', 'https://t.me/jrhwm0njm')}"

# --- [ واجهة API المحدثة - ميزة الفصل التلقائي ] ---

@app.route('/app_update')
def app_update():
    pkg = request.args.get('pkg')
    if not pkg: return "1\nhttps://t.me/your_channel"
    
    # [ ميزة الفصل ] : فحص هل التطبيق مسجل في قائمة التحديثات المنفصلة
    manifest_ref = db_fs.collection("update_manifest").document(pkg)
    doc = manifest_ref.get()
    
    if not doc.exists:
        # تسجيل تلقائي صامت للتطبيق الجديد في "درج التحديثات" فقط
        manifest_ref.set({
            "display_name": pkg,
            "version": "1",
            "url": "https://t.me/your_channel",
            "registered_at": time.time()
        })
        return "1\nhttps://t.me/your_channel"
    
    data = doc.to_dict()
    return f"{data.get('version', '1')}\n{data.get('url', '')}"

# --- [ واجهة API الجديدة - ميزة الإعلانات الذكية ] ---

@app.route('/get_ads')
def get_ads():
    pkg = request.args.get('pkg')
    if not pkg: return "3\n#\n#" 

    ads_ref = db_fs.collection("ads_manifest").document(pkg)
    doc = ads_ref.get()

    if not doc.exists:
        # تسجيل تلقائي صامت للتطبيق الجديد في درج الإعلانات فقط
        ads_ref.set({
            "display_name": pkg,
            "ads_type": "1",  # 1=إلغاء، 2=ذهاب، 3=إخفاء
            "ads_link": "https://t.me/your_channel",
            "ads_text": "مرحباً بك في تطبيقات نجم الإبداع",
            "registered_at": time.time()
        })
        return "1\nhttps://t.me/your_channel\nمرحباً بك في تطبيقات نجم الإبداع"

    d = doc.to_dict()
    # نرجع البيانات بنفس الترتيب الذي يتوقعه السمالي
    return f"{d.get('ads_type', '1')}\n{d.get('ads_link', '#')}\n{d.get('ads_text', '...')}"

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
            show_update_options(q.message, pkg) 

        elif q.data.startswith("change_alias_"):
            pkg = q.data.replace("change_alias_", "")
            msg = bot.send_message(q.message.chat.id, f"أرسل اللقب الجديد لتطبيق `{pkg}`:")
            bot.register_next_step_handler(msg, save_alias, pkg)

        elif q.data.startswith("exec_update_"):
            pkg = q.data.replace("exec_update_", "")
            msg = bot.send_message(q.message.chat.id, f"أرسل رقم الإصدار الجديد لـ `{pkg}`:")
            bot.register_next_step_handler(msg, process_update_version, pkg)

        elif q.data == "admin_manage_ads":
            list_apps_for_ads(q.message)
        elif q.data.startswith("ad_pkg_"):
            pkg = q.data.replace("ad_pkg_", "")
            show_ad_options(q.message, pkg)
        elif q.data.startswith("ad_set_text_"):
            pkg = q.data.replace("ad_set_text_", "")
            msg = bot.send_message(q.message.chat.id, "أرسل نص الإعلان الجديد:")
            bot.register_next_step_handler(msg, save_ad_text, pkg)
        elif q.data.startswith("ad_set_link_"):
            pkg = q.data.replace("ad_set_link_", "")
            msg = bot.send_message(q.message.chat.id, "أرسل رابط الإعلان الجديد:")
            bot.register_next_step_handler(msg, save_ad_link, pkg)
        elif q.data.startswith("ad_set_type_"):
            pkg, type_val = q.data.replace("ad_set_type_", "").split("|")
            db_fs.collection("ads_manifest").document(pkg).update({"ads_type": type_val})
            bot.send_message(q.message.chat.id, f"✅ تم تغيير نوع الإعلان إلى: {type_val}")
            
        elif q.data.startswith("ad_change_alias_"):
            pkg = q.data.replace("ad_change_alias_", "")
            msg = bot.send_message(q.message.chat.id, f"أرسل اللقب الجديد (الاسم الظاهر) لإعلان تطبيق `{pkg}`:")
            bot.register_next_step_handler(msg, save_ad_alias, pkg)

        # --- [ أوامر إدارة القفل المضافة ] ---
        elif q.data == "admin_manage_lock":
            list_apps_for_lock(q.message)
        elif q.data.startswith("lock_pkg_"):
            show_lock_options(q.message, q.data.replace("lock_pkg_", ""))
        elif q.data.startswith("lock_set_code_"):
            pkg = q.data.replace("lock_set_code_", "")
            msg = bot.send_message(q.message.chat.id, f"أرسل كود القفل الجديد لـ `{pkg}` (أرسل OFF للإلغاء):")
            bot.register_next_step_handler(msg, save_lock_code, pkg)
        elif q.data.startswith("lock_set_link_"):
            pkg = q.data.replace("lock_set_link_", "")
            msg = bot.send_message(q.message.chat.id, "أرسل رابط الفيديو الجديد:")
            bot.register_next_step_handler(msg, save_lock_link, pkg)
        elif q.data.startswith("lock_change_alias_"):
            pkg = q.data.replace("lock_change_alias_", "")
            msg = bot.send_message(q.message.chat.id, f"أرسل اللقب الجديد لنظام القفل لـ `{pkg}`:")
            bot.register_next_step_handler(msg, save_lock_alias, pkg)

        # ميزة تسمية تطبيقات البوت (القسم الجديد المستقل)
        elif q.data == "admin_manage_bot_names":
            list_apps_for_bot_names(q.message)
        elif q.data.startswith("bot_name_pkg_"):
            pkg = q.data.replace("bot_name_pkg_", "")
            msg = bot.send_message(q.message.chat.id, f"أرسل الاسم الظاهر الذي سيراه المستخدمون لتطبيق `{pkg}`:")
            bot.register_next_step_handler(msg, save_bot_app_name, pkg)

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
            status_txt = "بنجاح" if mode == "ban_op" else "بنجاح"
            bot.send_message(q.message.chat.id, f"✅ تم تنفيذ العملية على `{cid}` {status_txt}")

# --- [ وظائف الإدارة المحدثة للفصل التام ] --- 

def list_apps_for_update(m):
    apps = db_fs.collection("update_manifest").get()
    markup = types.InlineKeyboardMarkup()
    count = 0
    for a in apps:
        data = a.to_dict()
        display = data.get("display_name", a.id)
        markup.add(types.InlineKeyboardButton(f"📦 {display}", callback_data=f"set_up_pkg_{a.id}"))
        count += 1
    
    if count == 0:
        return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مسجلة تلقائياً بعد.")
    bot.send_message(m.chat.id, "اختر التطبيق لإدارته:", reply_markup=markup)

def show_update_options(m, pkg):
    mk = types.InlineKeyboardMarkup()
    mk.add(
        types.InlineKeyboardButton("🆙 تحديث الإصدار والرابط", callback_data=f"exec_update_{pkg}"),
        types.InlineKeyboardButton("✏️ تغيير اللقب (الاسم الظاهر)", callback_data=f"change_alias_{pkg}")
    )
    bot.send_message(m.chat.id, f"إدارة التطبيق: `{pkg}`\nاختر الإجراء:", reply_markup=mk)

def save_alias(m, pkg):
    alias = m.text.strip()
    db_fs.collection("update_manifest").document(pkg).update({"display_name": alias})
    bot.send_message(m.chat.id, f"✅ تم تغيير لقب التطبيق إلى: {alias}")

def process_update_version(m, pkg):
    version = m.text.strip()
    msg = bot.send_message(m.chat.id, "الآن أرسل رابط التحديث الجديد:")
    bot.register_next_step_handler(msg, finalize_app_update_db, pkg, version)

def finalize_app_update_db(m, pkg, version):
    url = m.text.strip()
    db_fs.collection("update_manifest").document(pkg).set({
        "version": version,
        "url": url,
        "last_updated": time.time()
    }, merge=True)
    bot.send_message(m.chat.id, f"✅ تم اعتماد التحديث بنجاح للتطبيق `{pkg}`")

# --- [ وظائف إدارة الإعلانات الجديدة والمحدثة ] ---

def list_apps_for_ads(m):
    apps = db_fs.collection("ads_manifest").get()
    markup = types.InlineKeyboardMarkup()
    count = 0
    for a in apps:
        data = a.to_dict()
        display = data.get("display_name", a.id)
        markup.add(types.InlineKeyboardButton(f"📢 {display}", callback_data=f"ad_pkg_{a.id}"))
        count += 1
    if count == 0:
        return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مسجلة للإعلانات بعد.")
    bot.send_message(m.chat.id, "اختر التطبيق لإدارة إعلانه:", reply_markup=markup)

def show_ad_options(m, pkg):
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("📝 تغيير النص", callback_data=f"ad_set_text_{pkg}"),
           types.InlineKeyboardButton("🔗 تغيير الرابط", callback_data=f"ad_set_link_{pkg}"))
    mk.add(types.InlineKeyboardButton("✏️ تغيير اللقب", callback_data=f"ad_change_alias_{pkg}")) 
    mk.add(types.InlineKeyboardButton("🔘 نوع: إلغاء (1)", callback_data=f"ad_set_type_{pkg}|1"),
           types.InlineKeyboardButton("🔘 نوع: ذهاب (2)", callback_data=f"ad_set_type_{pkg}|2"))
    mk.add(types.InlineKeyboardButton("🚫 إخفاء الإعلان (3)", callback_data=f"ad_set_type_{pkg}|3"))
    bot.send_message(m.chat.id, f"إدارة إعلان: `{pkg}`\nنوع 1: زر إغلاق\nنوع 2: زر يفتح الرابط\nنوع 3: لا يظهر شيء", reply_markup=mk)

def save_ad_text(m, pkg):
    db_fs.collection("ads_manifest").document(pkg).update({"ads_text": m.text.strip()})
    bot.send_message(m.chat.id, "✅ تم حفظ نص الإعلان الجديد.")

def save_ad_link(m, pkg):
    db_fs.collection("ads_manifest").document(pkg).update({"ads_link": m.text.strip()})
    bot.send_message(m.chat.id, "✅ تم حفظ رابط الإعلان الجديد.")

def save_ad_alias(m, pkg):
    alias = m.text.strip()
    db_fs.collection("ads_manifest").document(pkg).update({"display_name": alias})
    bot.send_message(m.chat.id, f"✅ تم تغيير لقب الإعلان لـ `{pkg}` إلى: {alias}")

# --- [ وظائف إدارة القفل المضافة ] ---

def list_apps_for_lock(m):
    apps = db_fs.collection("lock_manifest").get()
    markup = types.InlineKeyboardMarkup()
    for a in apps:
        d = a.to_dict()
        markup.add(types.InlineKeyboardButton(f"🔐 {d.get('display_name', a.id)}", callback_data=f"lock_pkg_{a.id}"))
    if not apps: return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات في نظام القفل.")
    bot.send_message(m.chat.id, "اختر التطبيق لإدارة القفل:", reply_markup=markup)

def show_lock_options(m, pkg):
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("🔑 تغيير الكود", callback_data=f"lock_set_code_{pkg}"),
           types.InlineKeyboardButton("🔗 تغيير الرابط", callback_data=f"lock_set_link_{pkg}"))
    mk.add(types.InlineKeyboardButton("✏️ تغيير اللقب", callback_data=f"lock_change_alias_{pkg}"))
    bot.send_message(m.chat.id, f"إدارة قفل: `{pkg}`", reply_markup=mk)

def save_lock_code(m, pkg):
    db_fs.collection("lock_manifest").document(pkg).update({"lock_code": m.text.strip()})
    bot.send_message(m.chat.id, "✅ تم حفظ كود القفل بنجاح.")

def save_lock_link(m, pkg):
    db_fs.collection("lock_manifest").document(pkg).update({"lock_link": m.text.strip()})
    bot.send_message(m.chat.id, "✅ تم حفظ رابط الفيديو بنجاح.")

def save_lock_alias(m, pkg):
    db_fs.collection("lock_manifest").document(pkg).update({"display_name": m.text.strip()})
    bot.send_message(m.chat.id, "✅ تم تغيير لقب القفل بنجاح.")

# --- [ قسم إدارة أسماء تطبيقات البوت (التحكم في العرض للمستخدم) ] ---

def list_apps_for_bot_names(m):
    # نعتمد على حزم التطبيقات المسجلة في الربط لمعرفة التطبيقات النشطة
    links = db_fs.collection("app_links").get()
    active_pkgs = set([l.id.split('_')[-1] for l in links])
    
    markup = types.InlineKeyboardMarkup()
    bot_names = get_bot_names_map()
    
    for pkg in active_pkgs:
        name = bot_names.get(pkg, pkg)
        markup.add(types.InlineKeyboardButton(f"🏷️ {name} ({pkg})", callback_data=f"bot_name_pkg_{pkg}"))
        
    if not active_pkgs:
        return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مسجلة بالربط بعد.")
    bot.send_message(m.chat.id, "اختر التطبيق لتغيير اسمه الظاهر داخل البوت:", reply_markup=markup)

def save_bot_app_name(m, pkg):
    new_name = m.text.strip()
    db_fs.collection("bot_names_manifest").document(pkg).set({"display_name": new_name})
    bot.send_message(m.chat.id, f"✅ تم اعتماد الاسم الظاهر الجديد: `{new_name}` لتطبيق `{pkg}`")

# --- [ بقية وظائف كودك الأصلي كما هي ] ---

def list_apps_for_ban(m, mode):
    apps = db_fs.collection("app_links").limit(50).get()
    if not apps: return bot.send_message(m.chat.id, "لا توجد أجهزة مسجلة.")
    names_map = get_bot_names_map() # استخدام أسماء البوت
    mk = types.InlineKeyboardMarkup(row_width=1)
    for a in apps:
        cid = a.id
        pkg = cid.split('_')[-1]
        display = names_map.get(pkg, pkg)
        is_banned = a.to_dict().get("banned", False)
        status_icon = "🔴" if is_banned else "🟢"
        mk.add(types.InlineKeyboardButton(f"{status_icon} {display} ({cid[:5]}...)", callback_data=f"exec_ban_{mode}_{cid}"))
    bot.send_message(m.chat.id, "اختر الجهاز المستهدف من القائمة:", reply_markup=mk)

def show_detailed_users(m):
    try:
        all_users = db_fs.collection("users").get()
        if not all_users: return bot.send_message(m.chat.id, "لا يوجد مستخدمين.")
        
        all_links = db_fs.collection("app_links").get()
        names_map = get_bot_names_map() # استخدام أسماء البوت
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
                    display = names_map.get(pkg, pkg)
                    stat = "🔴 محظور" if app_item['data'].get("banned") else (f"🟢 {int(rem/86400)} يوم" if rem > 0 else "⚪ منتهي")
                    msg += f"└ 📦 `{display}` ⮕ {stat}\n"
            msg += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            
            if len(msg) > 3000:
                bot.send_message(m.chat.id, msg, parse_mode="Markdown")
                msg = ""
                
        if msg: bot.send_message(m.chat.id, msg, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(m.chat.id, f"حدث خطأ أثناء جلب القائمة: {e}")

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
        types.InlineKeyboardButton("🔐 إدارة كود القفل", callback_data="admin_manage_lock"),
        types.InlineKeyboardButton("🆙 تحديث تطبيق", callback_data="admin_update_app_start"),
        types.InlineKeyboardButton("📢 إدارة الإعلانات", callback_data="admin_manage_ads"),
        types.InlineKeyboardButton("🏷️ تسمية تطبيقات البوت", callback_data="admin_manage_bot_names"), # الزر الجديد
        types.InlineKeyboardButton("📝 السجلات", callback_data="admin_logs"),
        types.InlineKeyboardButton("🏆 المتصدرين", callback_data="top_ref"),
        types.InlineKeyboardButton("🎫 كود جديد", callback_data="gen_key"),
        types.InlineKeyboardButton("📤 نشر تطبيق بالقناة", callback_data="admin_upload_app"),
        types.InlineKeyboardButton("🚫 حظر", callback_data="ban_op"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="unban_op"),
        types.InlineKeyboardButton("📢 إعلان التطبيق", callback_data="bc_app"),
        types.InlineKeyboardButton("📢 إعلان تلجرام", callback_data="bc_tele"),
        types.InlineKeyboardButton("🗑️ تصفير البيانات", callback_data="reset_data_ask")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown") 

def process_upload_photo(m):
    if not m.photo:
        return bot.send_message(m.chat.id, "❌ يرجى إرسال صورة صحيحة.")
    upload_cache[m.from_user.id] = {"photo": m.photo[-1].file_id}
    msg = bot.send_message(m.chat.id, "📂 الآن أرسل **ملف التطبيق (APK)**:")
    bot.register_next_step_handler(msg, process_upload_file)

def process_upload_file(m):
    if not m.document:
        return bot.send_message(m.chat.id, "❌ يرجى إرسال ملف APK.")
    upload_cache[m.from_user.id]["file"] = m.document.file_id
    msg = bot.send_message(m.chat.id, "✍️ أرسل **وصف التطبيق**:")
    bot.register_next_step_handler(msg, process_upload_desc)

def process_upload_desc(m):
    uid = m.from_user.id
    if uid not in upload_cache or not m.text:
        return bot.send_message(m.chat.id, "❌ حدث خطأ، حاول مجدداً.")
    
    user_desc = m.text
    decorated_desc = (
        f"🌟 **نجم الإبداع يقدم لكم** 🌟\n\n"
        f"🚀 **{user_desc}**\n\n"
        f"✅ **الحالة:** شغال وآمن 🛡️\n"
        f"✨ **الميزة:** نسخة حصرية مطورة\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"📥 **حمل الآن واستمتع بالتجربة!**"
    )
    
    photo = upload_cache[uid]["photo"]
    file_id = upload_cache[uid]["file"]
    
    try:
        file_msg = bot.send_document(CHANNEL_ID, file_id, disable_notification=True)
        file_link = f"https://t.me/{CHANNEL_ID.replace('@','')}/{file_msg.message_id}"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📥 تنزيل التطبيق الآن", url=file_link))
        
        bot.send_photo(CHANNEL_ID, photo, caption=decorated_desc, reply_markup=markup, parse_mode="Markdown")
        bot.send_message(m.chat.id, "✅ تم النشر باحترافية وسلاسة في القناة!")
        del upload_cache[uid]
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ خطأ أثناء النشر: {e}")

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
    
    names_map = get_bot_names_map() # استخدام أسماء البوت
    msg = "👤 **حالة اشتراكاتك:**\n"
    for doc in apps:
        data = doc.to_dict()
        pkg = doc.id.split('_')[-1]
        display = names_map.get(pkg, pkg)
        rem = data.get("end_time", 0) - time.time()
        status = f"✅ {int(rem/86400)} يوم" if rem > 0 else "❌ منتهي"
        if data.get("banned"): status = "🚫 محظور"
        msg += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📦 `{display}`\nالحالة: {status}\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown") 

def redeem_code_step(m):
    code = m.text.strip()
    vdata = get_voucher(code)
    if not vdata: return bot.send_message(m.chat.id, "❌ الكود غير صحيح.")
    
    uid = str(m.from_user.id)
    days = vdata.get("days")
    target_type = vdata.get("target", "all")
    target_id = vdata.get("target_id")

    if target_type == "user" and target_id != uid:
        return bot.send_message(m.chat.id, "❌ هذا الكود مخصص لمستخدم آخر.")

    user_data = get_user(uid)
    current_cid = user_data.get("current_app")
    
    def apply_redeem(cid):
        if target_type == "app" and target_id not in cid:
            bot.send_message(m.chat.id, f"❌ هذا الكود مخصص لتطبيق محدد.")
            return False
        link = get_app_link(cid)
        new_time = max(time.time(), link.get("end_time", 0)) + (days * 86400)
        update_app_link(cid, {"end_time": new_time})
        delete_voucher(code)
        bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم بنجاح!")
        add_log(f"تفعيل كود {days} يوم لـ {user_data.get('name')}")
        return True

    if current_cid:
        apply_redeem(current_cid)
    else:
        apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
        if not apps: return bot.send_message(m.chat.id, "❌ اربط جهازك أولاً.")
        update_user(uid, {"temp_code": code})
        names_map = get_bot_names_map() # استخدام أسماء البوت
        markup = types.InlineKeyboardMarkup(row_width=1)
        for doc in apps:
            pkg = doc.id.split('_')[-1]
            display = names_map.get(pkg, pkg)
            markup.add(types.InlineKeyboardButton(f"📦 {display}", callback_data=f"redeem_select_{doc.id}"))
        bot.send_message(m.chat.id, "🛠️ اختر التطبيق لتفعيله:", reply_markup=markup) 

def redeem_select_app(m, cid):
    uid = str(m.chat.id)
    user_data = get_user(uid)
    vdata = get_voucher(user_data.get("temp_code"))
    if vdata:
        days = vdata.get("days")
        target_id = vdata.get("target_id")
        if vdata.get("target") == "app" and target_id not in cid:
             return bot.send_message(m.chat.id, f"❌ الكود لا يصلح لهذا التطبيق.")
        
        link = get_app_link(cid)
        update_app_link(cid, {"end_time": max(time.time(), link.get("end_time", 0)) + (days * 86400)})
        delete_voucher(user_data["temp_code"])
        update_user(uid, {"temp_code": firestore.DELETE_FIELD})
        bot.send_message(m.chat.id, f"✅ تم التفعيل!")

def process_trial(m):
    uid = str(m.chat.id)
    apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
    if not apps: return bot.send_message(m.chat.id, "❌ لا يوجد تطبيق مرتبط.")
    
    names_map = get_bot_names_map() # استخدام أسماء البوت
    markup = types.InlineKeyboardMarkup(row_width=1)
    for doc in apps:
        pkg = doc.id.split('_')[-1]
        display = names_map.get(pkg, pkg)
        markup.add(types.InlineKeyboardButton(f"📦 {display}", callback_data=f"trial_select_{doc.id}"))
    bot.send_message(m.chat.id, "🛠️ اختر تطبيق التجربة:", reply_markup=markup) 

def trial_select_app(m, cid):
    data = get_app_link(cid)
    if not data: return
    pkg = cid.split('_')[-1]
    display = get_bot_names_map().get(pkg, pkg) # استخدام أسماء البوت
    if time.time() - data.get("trial_last_time", 0) < 86400:
        return bot.send_message(m.chat.id, f"❌ التجربة متاحة كل 24 ساعة لـ: `{display}`")
    
    new_time = max(time.time(), data.get("end_time", 0)) + 259200
    update_app_link(cid, {"trial_last_time": time.time(), "end_time": new_time})
    bot.send_message(m.chat.id, f"✅ تم تفعيل التجربة لـ: `{display}`") 

def send_payment(m):
    uid = str(m.chat.id)
    user_data = get_user(uid)
    cid = user_data.get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    
    bot.send_invoice(m.chat.id, title="اشتراك 30 يوم", description=f"تفعيل الجهاز: {cid.split('_')[-1]}", 
                     invoice_payload=f"pay_{cid}", provider_token="", currency="XTR",
                     prices=[types.LabeledPrice(label="VIP", amount=100)]) 

def wipe_all_data(m):
    collections = ["users", "app_links", "logs", "vouchers", "app_updates", "update_manifest", "ads_manifest", "bot_names_manifest", "lock_manifest"]
    for coll in collections:
        docs = db_fs.collection(coll).get()
        for d in docs: d.reference.delete()
    bot.send_message(m.chat.id, "✅ تم تصفير جميع قواعد البيانات بنجاح.")

def process_gen_key_start(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "أرسل أرقام فقط.")
    days = int(m.text)
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("🌍 كود عام", callback_data=f"set_target_all_{days}"))
    mk.add(types.InlineKeyboardButton("📦 لتطبيق معين", callback_data=f"set_target_app_{days}"))
    mk.add(types.InlineKeyboardButton("👤 لشخص معين", callback_data=f"set_target_user_{days}"))
    bot.send_message(m.chat.id, "اختر نوع الكود:", reply_markup=mk)

def process_key_type_selection(q):
    _, _, target, days = q.data.split('_')
    if target == "all":
        create_final_key(q.message, days, "all", None)
    elif target == "app":
        mk = types.InlineKeyboardMarkup(row_width=1)
        mk.add(types.InlineKeyboardButton("🔍 عرض التطبيقات للاختيار", callback_data=f"pick_a_list_{days}"),
               types.InlineKeyboardButton("⌨️ ارسل اسم التطبيق يدوياً", callback_data=f"pick_a_manual_{days}"))
        bot.send_message(q.message.chat.id, "كيف تريد تحديد التطبيق؟", reply_markup=mk)
    elif target == "user":
        mk = types.InlineKeyboardMarkup(row_width=1)
        mk.add(types.InlineKeyboardButton("👥 عرض المستخدمين للاختيار", callback_data=f"pick_u_list_{days}"),
               types.InlineKeyboardButton("⌨️ ارسل ايدي الشخص يدوياً", callback_data=f"pick_u_manual_{days}"))
        bot.send_message(q.message.chat.id, "كيف تريد تحديد الشخص؟", reply_markup=mk)

def list_users_for_key(m, days):
    users = db_fs.collection("users").limit(30).get()
    if not users: return bot.send_message(m.chat.id, "لا يوجد مستخدمين.")
    mk = types.InlineKeyboardMarkup(row_width=1)
    for u in users:
        ud = u.to_dict()
        mk.add(types.InlineKeyboardButton(f"👤 {ud.get('name')} ({u.id})", callback_data=f"gen_for_u_{u.id}_{days}"))
    bot.send_message(m.chat.id, "اختر المستخدم:", reply_markup=mk)

def list_apps_for_key(m, days):
    apps = db_fs.collection("app_links").limit(30).get()
    if not apps: return bot.send_message(m.chat.id, "لا توجد تطبيقات مسجلة.")
    names_map = get_bot_names_map()
    mk = types.InlineKeyboardMarkup(row_width=1)
    seen_pkgs = set()
    for a in apps:
        pkg = a.id.split('_')[-1]
        display = names_map.get(pkg, pkg)
        if pkg not in seen_pkgs:
            mk.add(types.InlineKeyboardButton(f"📦 {display}", callback_data=f"gen_for_a_{a.id}_{days}"))
            seen_pkgs.add(pkg)
    bot.send_message(m.chat.id, "اختر التطبيق:", reply_markup=mk)

def create_final_key(m, days, target, target_id):
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db_fs.collection("vouchers").document(code).set({
        "days": int(days), "target": target, "target_id": target_id
    })
    txt = f"🎫 **كود جديد ({days} يوم)**\nالنوع: {target}\n"
    if target_id: 
        pkg = target_id.split('_')[-1] if "_" in target_id else target_id
        display = get_bot_names_map().get(pkg, pkg)
        txt += f"الهدف: `{display}`\n"
    txt += f"الكود: `{code}`"
    bot.send_message(m.chat.id, txt, parse_mode="Markdown")

def expiry_notifier():
    while True:
        try:
            now = time.time()
            links = db_fs.collection("app_links").get()
            names_map = get_bot_names_map()
            for doc in links:
                data = doc.to_dict()
                if 82800 < (data.get("end_time", 0) - now) < 86400:
                    uid = data.get("telegram_id")
                    if uid:
                        pkg = doc.id.split('_')[-1]
                        display = names_map.get(pkg, pkg)
                        try: bot.send_message(uid, f"⚠️ اشتراكك في `{display}` ينتهي غداً!")
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
