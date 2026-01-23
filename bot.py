```python
import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread, Lock
import firebase_admin
from firebase_admin import credentials, firestore
from functools import wraps, lru_cache
from collections import defaultdict
from datetime import datetime, timedelta
import logging
from logging.handlers import RotatingFileHandler
import hmac
import hashlib

# --- [ إعداد Logging ] ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = RotatingFileHandler('bot.log', maxBytes=10000000, backupCount=5)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
CHANNEL_ID = os.environ.get('CHANNEL_ID')
API_SECRET = os.environ.get('API_SECRET', 'default-secret-change-me')

if not firebase_admin._apps:
    cred_val = os.environ.get('FIREBASE_CREDENTIALS')
    if cred_val:
        try:
            cred_dict = json.loads(cred_val)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            logger.error(f"Firebase initialization error: {e}")

db_fs = firestore.client()
bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# مخزن مؤقت لعملية رفع التطبيقات مع حماية Thread-safe
upload_cache = {}
cache_lock = Lock()

# Rate limiting
rate_limits = defaultdict(list)
RATE_LIMIT = 30

# --- [ وظائف الحماية ] ---

def verify_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-API-Key')
        if not token or not hmac.compare_digest(token, API_SECRET):
            logger.warning(f"Unauthorized API access attempt from {request.remote_addr}")
            return "Unauthorized", 401
        return f(*args, **kwargs)
    return decorated

def check_rate_limit(user_id):
    now = datetime.now()
    with cache_lock:
        rate_limits[user_id] = [
            t for t in rate_limits[user_id] 
            if now - t < timedelta(minutes=1)
        ]
        
        if len(rate_limits[user_id]) >= RATE_LIMIT:
            return False
        
        rate_limits[user_id].append(now)
        return True

def validate_input(text, max_length=500, allow_special=False):
    if not text or not isinstance(text, str):
        return False
    if len(text) > max_length:
        return False
    if not allow_special and any(c in text for c in ['<', '>', ';', '&', '|']):
        return False
    return True

# --- [ إدارة قاعدة البيانات ] ---

def get_user(uid):
    try:
        doc = db_fs.collection("users").document(str(uid)).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        logger.error(f"Error getting user {uid}: {e}")
        return None

def update_user(uid, data):
    try:
        db_fs.collection("users").document(str(uid)).set(data, merge=True)
    except Exception as e:
        logger.error(f"Error updating user {uid}: {e}")

def get_app_link(cid):
    try:
        doc = db_fs.collection("app_links").document(str(cid)).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        logger.error(f"Error getting app link {cid}: {e}")
        return None

def update_app_link(cid, data):
    try:
        db_fs.collection("app_links").document(str(cid)).set(data, merge=True)
    except Exception as e:
        logger.error(f"Error updating app link {cid}: {e}")

def get_user_and_link(uid, cid):
    try:
        refs = [
            db_fs.collection("users").document(str(uid)),
            db_fs.collection("app_links").document(cid)
        ]
        docs = db_fs.get_all(refs)
        return (
            docs[0].to_dict() if docs[0].exists else None,
            docs[1].to_dict() if docs[1].exists else None
        )
    except Exception as e:
        logger.error(f"Error batch getting user and link: {e}")
        return None, None

def get_voucher(code):
    try:
        doc = db_fs.collection("vouchers").document(str(code)).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        logger.error(f"Error getting voucher {code}: {e}")
        return None

def delete_voucher(code):
    try:
        db_fs.collection("vouchers").document(str(code)).delete()
    except Exception as e:
        logger.error(f"Error deleting voucher {code}: {e}")

def add_log(text):
    try:
        db_fs.collection("logs").add({
            "text": f"[{time.strftime('%Y-%m-%d %H:%M')}] {text}",
            "timestamp": time.time()
        })
    except Exception as e:
        logger.error(f"Error adding log: {e}")

def get_global_news():
    try:
        doc = db_fs.collection("config").document("global").get()
        return doc.to_dict().get("global_news", "لا توجد أخبار") if doc.exists else "لا توجد أخبار"
    except Exception as e:
        logger.error(f"Error getting global news: {e}")
        return "لا توجد أخبار"

def set_global_news(text):
    try:
        db_fs.collection("config").document("global").set({"global_news": text}, merge=True)
    except Exception as e:
        logger.error(f"Error setting global news: {e}")

def check_membership(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except telebot.apihelper.ApiTelegramException as e:
        if "user not found" in str(e).lower() or "chat not found" in str(e).lower():
            logger.info(f"User {user_id} not found in channel")
            return False
        logger.error(f"Error checking membership for {user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking membership: {e}")
        return False

@lru_cache(maxsize=128)
def get_bot_names_map_cached(cache_time):
    try:
        docs = db_fs.collection("bot_names_manifest").get()
        return {d.id: d.to_dict().get("display_name", d.id) for d in docs}
    except Exception as e:
        logger.error(f"Error getting bot names map: {e}")
        return {}

def get_bot_names_map():
    current_cache_time = int(time.time() / 300)
    return get_bot_names_map_cached(current_cache_time)

@lru_cache(maxsize=128)
def get_all_app_names_cached(cache_time):
    try:
        apps = db_fs.collection("update_manifest").get()
        return {a.id: a.to_dict().get("display_name", a.id) for a in apps}
    except Exception as e:
        logger.error(f"Error getting all app names: {e}")
        return {}

def get_all_app_names():
    current_cache_time = int(time.time() / 300)
    return get_all_app_names_cached(current_cache_time)

# --- [ واجهة API المحدثة ] ---

@app.route('/app_update')
@verify_api_key
def app_update():
    pkg = request.args.get('pkg')
    if not pkg or not validate_input(pkg, 200):
        logger.warning(f"Invalid package name in app_update: {pkg}")
        return "Invalid request", 400
    
    try:
        manifest_ref = db_fs.collection("update_manifest").document(pkg)
        doc = manifest_ref.get()
        
        if not doc.exists:
            manifest_ref.set({
                "display_name": pkg,
                "version": "1",
                "url": "https://t.me/your_channel",
                "registered_at": time.time()
            })
            logger.info(f"New app registered: {pkg}")
            return "1\nhttps://t.me/your_channel"
        
        data = doc.to_dict()
        return f"{data.get('version', '1')}\n{data.get('url', '')}"
    except Exception as e:
        logger.error(f"Error in app_update: {e}")
        return "Error", 500

@app.route('/get_ads')
@verify_api_key
def get_ads():
    pkg = request.args.get('pkg')
    if not pkg or not validate_input(pkg, 200):
        logger.warning(f"Invalid package name in get_ads: {pkg}")
        return "Invalid request", 400

    try:
        ads_ref = db_fs.collection("ads_manifest").document(pkg)
        doc = ads_ref.get()

        if not doc.exists:
            ads_ref.set({
                "display_name": pkg,
                "ads_type": "1",
                "ads_link": "https://t.me/your_channel",
                "ads_text": "مرحباً بك في تطبيقات نجم الإبداع",
                "registered_at": time.time()
            })
            logger.info(f"New ad registered: {pkg}")
            return "1\nhttps://t.me/your_channel\nمرحباً بك في تطبيقات نجم الإبداع"

        d = doc.to_dict()
        return f"{d.get('ads_type', '1')}\n{d.get('ads_link', '#')}\n{d.get('ads_text', '...')}"
    except Exception as e:
        logger.error(f"Error in get_ads: {e}")
        return "Error", 500

@app.route('/check')
@verify_api_key
def check_status():
    aid = request.args.get('aid')
    pkg = request.args.get('pkg')
    
    if not aid or not pkg or not validate_input(aid, 50) or not validate_input(pkg, 200):
        logger.warning(f"Invalid parameters in check_status")
        return "Invalid request", 400
    
    try:
        cid = f"{aid}_{pkg.replace('.', '_')}"
        data = get_app_link(cid)
        if not data:
            return "EXPIRED"
        if data.get("banned"):
            return "BANNED"
        if time.time() > data.get("end_time", 0):
            return "EXPIRED"
        return "ACTIVE"
    except Exception as e:
        logger.error(f"Error in check_status: {e}")
        return "Error", 500

@app.route('/get_news')
@verify_api_key
def get_news():
    try:
        return get_global_news()
    except Exception as e:
        logger.error(f"Error in get_news: {e}")
        return "Error", 500

@app.route('/health')
def health_check():
    return "OK", 200

# --- [ واجهة البوت ] ---

@bot.message_handler(commands=['start'])
def start(m):
    uid = str(m.from_user.id)
    
    if not check_rate_limit(uid):
        return bot.send_message(m.chat.id, "⚠️ الرجاء الانتظار قليلاً قبل إرسال طلبات جديدة.")
    
    username = f"@{m.from_user.username}" if m.from_user.username else m.from_user.first_name
    
    args = m.text.split()
    user_data = get_user(uid)
    
    try:
        if not user_data:
            inviter_id = args[1] if len(args) > 1 and args[1].isdigit() and args[1] != uid else None
            user_data = {
                "current_app": None, "name": username, "invited_by": inviter_id,
                "referral_count": 0, "claimed_channel_gift": False, "join_date": time.time()
            }
            update_user(uid, user_data)
            logger.info(f"New user registered: {uid}")
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

            if "_" in cid and validate_input(cid, 200):
                link_data = get_app_link(cid) or {"end_time": 0, "banned": False, "trial_last_time": 0, "gift_claimed": False}
                link_data["telegram_id"] = uid
                update_app_link(cid, link_data)
                update_user(uid, {"current_app": cid})
                
                if check_membership(uid) and not link_data.get("gift_claimed"):
                    link_data["end_time"] = max(time.time(), link_data.get("end_time", 0)) + (3 * 86400)
                    link_data["gift_claimed"] = True
                    update_app_link(cid, link_data)
                    bot.send_message(m.chat.id, "🎁 تم منحك 3 أيام هدية لانضمامك للقناة!")
                    logger.info(f"Gift claimed by user {uid}")
                    
                    inviter = user_data.get("invited_by")
                    if inviter:
                        inv_data = get_user(inviter)
                        if inv_data and inv_data.get("current_app"):
                            inv_link = get_app_link(inv_data["current_app"])
                            if inv_link:
                                new_time = max(time.time(), inv_link.get("end_time", 0)) + (7 * 86400)
                                update_app_link(inv_data["current_app"], {"end_time": new_time})
                                update_user(inviter, {"referral_count": inv_data.get("referral_count", 0) + 1})
                                try: 
                                    bot.send_message(inviter, "🎊 حصلت على 7 أيام إضافية بسبب دعوة صديق!")
                                    logger.info(f"Referral bonus given to {inviter}")
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
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ، الرجاء المحاولة مرة أخرى.")

def show_main_menu(m, username):
    try:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
            types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
            types.InlineKeyboardButton("🔗 إحالاتي ومكافآتي", callback_data="u_referral"),
            types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
            types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy")
        )
        bot.send_message(m.chat.id, f"مرحباً بك يا **{username}** 🌟\nاستخدم القائمة للتحكم أو اطلب من داخل التطبيق:", reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error showing main menu: {e}")

# --- [ معالجة ضغطات الأزرار ] ---

@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    
    if not check_rate_limit(uid):
        return bot.answer_callback_query(q.id, "⚠️ الرجاء الانتظار قليلاً", show_alert=True)
    
    try:
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
                
    except Exception as e:
        logger.error(f"Error handling callback: {e}")
        bot.answer_callback_query(q.id, "❌ حدث خطأ", show_alert=True)

# --- [ وظائف الإدارة ] ---

def list_apps_for_update(m):
    try:
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
    except Exception as e:
        logger.error(f"Error listing apps for update: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ أثناء جلب التطبيقات.")

def show_update_options(m, pkg):
    try:
        mk = types.InlineKeyboardMarkup()
        mk.add(
            types.InlineKeyboardButton("🆙 تحديث الإصدار والرابط", callback_data=f"exec_update_{pkg}"),
            types.InlineKeyboardButton("✏️ تغيير اللقب (الاسم الظاهر)", callback_data=f"change_alias_{pkg}")
        )
        bot.send_message(m.chat.id, f"إدارة التطبيق: `{pkg}`\nاختر الإجراء:", reply_markup=mk)
    except Exception as e:
        logger.error(f"Error showing update options: {e}")

def save_alias(m, pkg):
    try:
        alias = m.text.strip()
        if not validate_input(alias, 100):
            return bot.send_message(m.chat.id, "❌ الاسم غير صالح.")
        db_fs.collection("update_manifest").document(pkg).update({"display_name": alias})
        bot.send_message(m.chat.id, f"✅ تم تغيير لقب التطبيق إلى: {alias}")
        logger.info(f"Alias updated for {pkg}: {alias}")
    except Exception as e:
        logger.error(f"Error saving alias: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ أثناء حفظ الاسم.")

def process_update_version(m, pkg):
    try:
        version = m.text.strip()
        if not validate_input(version, 20):
            return bot.send_message(m.chat.id, "❌ رقم الإصدار غير صالح.")
        msg = bot.send_message(m.chat.id, "الآن أرسل رابط التحديث الجديد:")
        bot.register_next_step_handler(msg, finalize_app_update_db, pkg, version)
    except Exception as e:
        logger.error(f"Error processing update version: {e}")

def finalize_app_update_db(m, pkg, version):
    try:
        url = m.text.strip()
        if not validate_input(url, 500) or not url.startswith('http'):
            return bot.send_message(m.chat.id, "❌ الرابط غير صالح.")
        db_fs.collection("update_manifest").document(pkg).set({
            "version": version,
            "url": url,
            "last_updated": time.time()
        }, merge=True)
        bot.send_message(m.chat.id, f"✅ تم اعتماد التحديث بنجاح للتطبيق `{pkg}`")
        logger.info(f"App updated: {pkg} v{version}")
    except Exception as e:
        logger.error(f"Error finalizing app update: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ أثناء الحفظ.")

# --- [ وظائف إدارة الإعلانات ] ---

def list_apps_for_ads(m):
    try:
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
    except Exception as e:
        logger.error(f"Error listing apps for ads: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ أثناء جلب التطبيقات.")

def show_ad_options(m, pkg):
    try:
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("📝 تغيير النص", callback_data=f"ad_set_text_{pkg}"),
               types.InlineKeyboardButton("🔗 تغيير الرابط", callback_data=f"ad_set_link_{pkg}"))
        mk.add(types.InlineKeyboardButton("✏️ تغيير اللقب", callback_data=f"ad_change_alias_{pkg}"))
        mk.add(types.InlineKeyboardButton("🔘 نوع: إلغاء (1)", callback_data=f"ad_set_type_{pkg}|1"),
               types.InlineKeyboardButton("🔘 نوع: ذهاب (2)", callback_data=f"ad_set_type_{pkg}|2"))
        mk.add(types.InlineKeyboardButton("🚫 إخفاء الإعلان (3)", callback_data=f"ad_set_type_{pkg}|3"))
        bot.send_message(m.chat.id, f"إدارة إعلان: `{pkg}`\nنوع 1: زر إغلاق\nنوع 2: زر يفتح الرابط\nنوع 3: لا يظهر شيء", reply_markup=mk)
    except Exception as e:
        logger.error(f"Error showing ad options: {e}")

def save_ad_text(m, pkg):
    try:
        text = m.text.strip()
        if not validate_input(text, 500, True):
            return bot.send_message(m.chat.id, "❌ النص غير صالح.")
        db_fs.collection("ads_manifest").document(pkg).update({"ads_text": text})
        bot.send_message(m.chat.id, "✅ تم حفظ نص الإعلان الجديد.")
        logger.info(f"Ad text updated for {pkg}")
    except Exception as e:
        logger.error(f"Error saving ad text: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def save_ad_link(m, pkg):
    try:
        link = m.text.strip()
        if not validate_input(link, 500) or not link.startswith('http'):
            return bot.send_message(m.chat.id, "❌ الرابط غير صالح.")
        db_fs.collection("ads_manifest").document(pkg).update({"ads_link": link})
        bot.send_message(m.chat.id, "✅ تم حفظ رابط الإعلان الجديد.")
        logger.info(f"Ad link updated for {pkg}")
    except Exception as e:
        logger.error(f"Error saving ad link: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def save_ad_alias(m, pkg):
    try:
        alias = m.text.strip()
        if not validate_input(alias, 100):
            return bot.send_message(m.chat.id, "❌ الاسم غير صالح.")
        db_fs.collection("ads_manifest").document(pkg).update({"display_name": alias})
        bot.send_message(m.chat.id, f"✅ تم تغيير لقب الإعلان لـ `{pkg}` إلى: {alias}")
        logger.info(f"Ad alias updated for {pkg}")
    except Exception as e:
        logger.error(f"Error saving ad alias: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

# --- [ قسم إدارة أسماء تطبيقات البوت ] ---

def list_apps_for_bot_names(m):
    try:
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
    except Exception as e:
        logger.error(f"Error listing apps for bot names: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def save_bot_app_name(m, pkg):
    try:
        new_name = m.text.strip()
        if not validate_input(new_name, 100):
            return bot.send_message(m.chat.id, "❌ الاسم غير صالح.")
        db_fs.collection("bot_names_manifest").document(pkg).set({"display_name": new_name})
        bot.send_message(m.chat.id, f"✅ تم اعتماد الاسم الظاهر الجديد: `{new_name}` لتطبيق `{pkg}`")
        logger.info(f"Bot app name updated for {pkg}: {new_name}")
    except Exception as e:
        logger.error(f"Error saving bot app name: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

# --- [ بقية الوظائف ] ---

def list_apps_for_ban(m, mode):
    try:
        apps = db_fs.collection("app_links").limit(50).get()
        if not apps:
            return bot.send_message(m.chat.id, "لا توجد أجهزة مسجلة.")
        names_map = get_bot_names_map()
        mk = types.InlineKeyboardMarkup(row_width=1)
        for a in apps:
            cid = a.id
            pkg = cid.split('_')[-1]
            display = names_map.get(pkg, pkg)
            is_banned = a.to_dict().get("banned", False)
            status_icon = "🔴" if is_banned else "🟢"
            mk.add(types.InlineKeyboardButton(f"{status_icon} {display} ({cid[:15]}...)", callback_data=f"exec_ban_{mode}_{cid}"))
        bot.send_message(m.chat.id, "اختر الجهاز المستهدف من القائمة:", reply_markup=mk)
    except Exception as e:
        logger.error(f"Error listing apps for ban: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def show_detailed_users(m, page=0, limit=20):
    try:
        offset = page * limit
        all_users = db_fs.collection("users").order_by("join_date").limit(limit).offset(offset).get()
        if not all_users:
            return bot.send_message(m.chat.id, "لا يوجد مستخدمين.")
        
        all_links = db_fs.collection("app_links").get()
        names_map = get_bot_names_map()
        links_map = {}
        for l in all_links:
            ld = l.to_dict()
            u_id = ld.get("telegram_id")
            if u_id:
                if u_id not in links_map:
                    links_map[u_id] = []
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
                
        if msg:
            bot.send_message(m.chat.id, msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error showing detailed users: {e}")
        bot.send_message(m.chat.id, f"❌ حدث خطأ أثناء جلب القائمة.")

def show_logs(m):
    try:
        logs = db_fs.collection("logs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(15).get()
        text = "\n".join([d.to_dict().get("text") for d in logs]) if logs else "لا توجد سجلات."
        bot.send_message(m.chat.id, f"📝 **آخر العمليات:**\n\n{text}")
    except Exception as e:
        logger.error(f"Error showing logs: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def show_top_referrers(m):
    try:
        users = db_fs.collection("users").order_by("referral_count", direction=firestore.Query.DESCENDING).limit(10).get()
        msg = "🏆 **أفضل 10 داعين:**\n\n"
        for i, d in enumerate(users, 1):
            msg += f"{i}- {d.to_dict().get('name')} ⮕ `{d.to_dict().get('referral_count', 0)}` إحالة\n"
        bot.send_message(m.chat.id, msg)
    except Exception as e:
        logger.error(f"Error showing top referrers: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    try:
        users_count = len(db_fs.collection("users").get())
        links_all = db_fs.collection("app_links").get()
        active = sum(1 for d in links_all if d.to_dict().get("end_time", 0) > time.time())
        
        msg = (f"👑 **إدارة نجم الإبداع**\n\n"
               f"👥 المستخدمين: `{users_count}` | الأجهزة: `{len(links_all)}`\n"
               f"🟢 النشطين: `{active}`\n")
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📋 المشتركين", callback_data="list_all"),
            types.InlineKeyboardButton("🆙 تحديث تطبيق", callback_data="admin_update_app_start"),
            types.InlineKeyboardButton("📢 إدارة الإعلانات", callback_data="admin_manage_ads"),
            types.InlineKeyboardButton("🏷️ تسمية تطبيقات البوت", callback_data="admin_manage_bot_names"),
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
    except Exception as e:
        logger.error(f"Error in admin panel: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def process_upload_photo(m):
    try:
        if not m.photo:
            return bot.send_message(m.chat.id, "❌ يرجى إرسال صورة صحيحة.")
        
        with cache_lock:
            upload_cache[m.from_user.id] = {"photo": m.photo[-1].file_id}
        
        msg = bot.send_message(m.chat.id, "📂 الآن أرسل **ملف التطبيق (APK)**:")
        bot.register_next_step_handler(msg, process_upload_file)
    except Exception as e:
        logger.error(f"Error processing upload photo: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def process_upload_file(m):
    try:
        if not m.document:
            return bot.send_message(m.chat.id, "❌ يرجى إرسال ملف APK.")
        
        with cache_lock:
            if m.from_user.id not in upload_cache:
                return bot.send_message(m.chat.id, "❌ حدث خطأ، ابدأ من جديد.")
            upload_cache[m.from_user.id]["file"] = m.document.file_id
        
        msg = bot.send_message(m.chat.id, "✍️ أرسل **وصف التطبيق**:")
        bot.register_next_step_handler(msg, process_upload_desc)
    except Exception as e:
        logger.error(f"Error processing upload file: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def process_upload_desc(m):
    uid = m.from_user.id
    
    try:
        with cache_lock:
            if uid not in upload_cache or not m.text:
                return bot.send_message(m.chat.id, "❌ حدث خطأ، حاول مجدداً.")
            
            if not validate_input(m.text, 1000, True):
                return bot.send_message(m.chat.id, "❌ الوصف غير صالح.")
        
        user_desc = m.text
        decorated_desc = (
            f"🌟 **نجم الإبداع يقدم لكم** 🌟\n\n"
            f"🚀 **{user_desc}**\n\n"
            f"✅ **الحالة:** شغال وآمن 🛡️\n"
            f"✨ **الميزة:** نسخة حصرية مطورة\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"📥 **حمل الآن واستمتع بالتجربة!**"
        )
        
        with cache_lock:
            photo = upload_cache[uid]["photo"]
            file_id = upload_cache[uid]["file"]
        
        file_msg = bot.send_document(CHANNEL_ID, file_id, disable_notification=True, thumb=photo)
        file_link = f"https://t.me/{CHANNEL_ID.replace('@','')}/{file_msg.message_id}"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📥 تنزيل التطبيق الآن", url=file_link))
        
        bot.send_photo(CHANNEL_ID, photo, caption=decorated_desc, reply_markup=markup, parse_mode="Markdown")
        bot.send_message(m.chat.id, "✅ تم النشر باحترافية وسلاسة في القناة!")
        
        with cache_lock:
            del upload_cache[uid]
        
        logger.info(f"App uploaded to channel by admin {uid}")
        
    except Exception as e:
        logger.error(f"Error processing upload description: {e}")
        bot.send_message(m.chat.id, f"❌ خطأ أثناء النشر: {str(e)[:100]}")

def show_referral_info(m):
    try:
        user_data = get_user(m.chat.id)
        ref_link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
        msg = (f"🔗 **نظام الإحالات:**\n\nإحالاتك: `{user_data.get('referral_count', 0) if user_data else 0}`\n"
               f"رابط دعوتك:\n`{ref_link}`")
        bot.send_message(m.chat.id, msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error showing referral info: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def user_dashboard(m):
    try:
        uid = str(m.chat.id)
        apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
        if not apps:
            return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة.")
        
        names_map = get_bot_names_map()
        msg = "👤 **حالة اشتراكاتك:**\n"
        for doc in apps:
            data = doc.to_dict()
            pkg = doc.id.split('_')[-1]
            display = names_map.get(pkg, pkg)
            rem = data.get("end_time", 0) - time.time()
            status = f"✅ {int(rem/86400)} يوم" if rem > 0 else "❌ منتهي"
            if data.get("banned"):
                status = "🚫 محظور"
            msg += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📦 `{display}`\nالحالة: {status}\n"
        bot.send_message(m.chat.id, msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in user dashboard: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def redeem_code_step(m):
    try:
        code = m.text.strip()
        if not validate_input(code, 50):
            return bot.send_message(m.chat.id, "❌ الكود غير صالح.")
        
        vdata = get_voucher(code)
        if not vdata:
            return bot.send_message(m.chat.id, "❌ الكود غير صحيح.")
        
        uid = str(m.from_user.id)
        days = vdata.get("days")
        target_type = vdata.get("target", "all")
        target_id = vdata.get("target_id")

        if target_type == "user" and target_id != uid:
            return bot.send_message(m.chat.id, "❌ هذا الكود مخصص لمستخدم آخر.")

        user_data = get_user(uid)
        current_cid = user_data.get("current_app") if user_data else None
        
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
            logger.info(f"Voucher redeemed: {code} by user {uid}")
            return True

        if current_cid:
            apply_redeem(current_cid)
        else:
            apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
            if not apps:
                return bot.send_message(m.chat.id, "❌ اربط جهازك أولاً.")
            update_user(uid, {"temp_code": code})
            names_map = get_bot_names_map()
            markup = types.InlineKeyboardMarkup(row_width=1)
            for doc in apps:
                pkg = doc.id.split('_')[-1]
                display = names_map.get(pkg, pkg)
                markup.add(types.InlineKeyboardButton(f"📦 {display}", callback_data=f"redeem_select_{doc.id}"))
            bot.send_message(m.chat.id, "🛠️ اختر التطبيق لتفعيله:", reply_markup=markup)
    except Exception as e:
        logger.error(f"Error in redeem code step: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def redeem_select_app(m, cid):
    try:
        uid = str(m.chat.id)
        user_data = get_user(uid)
        if not user_data:
            return
        
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
            logger.info(f"Voucher applied to app {cid} by user {uid}")
    except Exception as e:
        logger.error(f"Error in redeem select app: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def process_trial(m):
    try:
        uid = str(m.chat.id)
        apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
        if not apps:
            return bot.send_message(m.chat.id, "❌ لا يوجد تطبيق مرتبط.")
        
        names_map = get_bot_names_map()
        markup = types.InlineKeyboardMarkup(row_width=1)
        for doc in apps:
            pkg = doc.id.split('_')[-1]
            display = names_map.get(pkg, pkg)
            markup.add(types.InlineKeyboardButton(f"📦 {display}", callback_data=f"trial_select_{doc.id}"))
        bot.send_message(m.chat.id, "🛠️ اختر تطبيق التجربة:", reply_markup=markup)
    except Exception as e:
        logger.error(f"Error in process trial: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def trial_select_app(m, cid):
    try:
        data = get_app_link(cid)
        if not data:
            return
        pkg = cid.split('_')[-1]
        display = get_bot_names_map().get(pkg, pkg)
        if time.time() - data.get("trial_last_time", 0) < 86400:
            return bot.send_message(m.chat.id, f"❌ التجربة متاحة كل 24 ساعة لـ: `{display}`")
        
        new_time = max(time.time(), data.get("end_time", 0)) + 259200
        update_app_link(cid, {"trial_last_time": time.time(), "end_time": new_time})
        bot.send_message(m.chat.id, f"✅ تم تفعيل التجربة لـ: `{display}`")
        logger.info(f"Trial activated for {cid}")
    except Exception as e:
        logger.error(f"Error in trial select app: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def send_payment(m):
    try:
        uid = str(m.chat.id)
        user_data = get_user(uid)
        if not user_data:
            return bot.send_message(m.chat.id, "❌ حدث خطأ.")
        
        cid = user_data.get("current_app")
        if not cid
            return bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
        
        bot.send_invoice(
            m.chat.id,
            title="اشتراك 30 يوم",
            description=f"تفعيل الجهاز: {cid.split('_')[-1]}",
            invoice_payload=f"pay_{cid}",
            provider_token="",
            currency="XTR",
            prices=[types.LabeledPrice(label="VIP", amount=100)]
        )
        logger.info(f"Payment invoice sent to user {uid}")
    except Exception as e:
        logger.error(f"Error sending payment: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ في إرسال الفاتورة.")

def wipe_all_data(m):
    try:
        collections = ["users", "app_links", "logs", "vouchers", "app_updates", "update_manifest", "ads_manifest", "bot_names_manifest"]
        for coll in collections:
            docs = db_fs.collection(coll).get()
            for d in docs:
                d.reference.delete()
        bot.send_message(m.chat.id, "✅ تم تصفير جميع قواعد البيانات بنجاح.")
        logger.warning("Database wiped by admin")
    except Exception as e:
        logger.error(f"Error wiping data: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def process_gen_key_start(m):
    try:
        if not m.text.isdigit():
            return bot.send_message(m.chat.id, "أرسل أرقام فقط.")
        days = int(m.text)
        if days <= 0 or days > 3650:
            return bot.send_message(m.chat.id, "❌ عدد الأيام غير صالح (1-3650).")
        
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("🌍 كود عام", callback_data=f"set_target_all_{days}"))
        mk.add(types.InlineKeyboardButton("📦 لتطبيق معين", callback_data=f"set_target_app_{days}"))
        mk.add(types.InlineKeyboardButton("👤 لشخص معين", callback_data=f"set_target_user_{days}"))
        bot.send_message(m.chat.id, "اختر نوع الكود:", reply_markup=mk)
    except Exception as e:
        logger.error(f"Error in process gen key start: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def process_key_type_selection(q):
    try:
        _, _, target, days = q.data.split('_')
        if target == "all":
            create_final_key(q.message, days, "all", None)
        elif target == "app":
            mk = types.InlineKeyboardMarkup(row_width=1)
            mk.add(
                types.InlineKeyboardButton("🔍 عرض التطبيقات للاختيار", callback_data=f"pick_a_list_{days}"),
                types.InlineKeyboardButton("⌨️ ارسل اسم التطبيق يدوياً", callback_data=f"pick_a_manual_{days}")
            )
            bot.send_message(q.message.chat.id, "كيف تريد تحديد التطبيق؟", reply_markup=mk)
        elif target == "user":
            mk = types.InlineKeyboardMarkup(row_width=1)
            mk.add(
                types.InlineKeyboardButton("👥 عرض المستخدمين للاختيار", callback_data=f"pick_u_list_{days}"),
                types.InlineKeyboardButton("⌨️ ارسل ايدي الشخص يدوياً", callback_data=f"pick_u_manual_{days}")
            )
            bot.send_message(q.message.chat.id, "كيف تريد تحديد الشخص؟", reply_markup=mk)
    except Exception as e:
        logger.error(f"Error in process key type selection: {e}")

def list_users_for_key(m, days):
    try:
        users = db_fs.collection("users").limit(30).get()
        if not users:
            return bot.send_message(m.chat.id, "لا يوجد مستخدمين.")
        mk = types.InlineKeyboardMarkup(row_width=1)
        for u in users:
            ud = u.to_dict()
            mk.add(types.InlineKeyboardButton(f"👤 {ud.get('name')} ({u.id})", callback_data=f"gen_for_u_{u.id}_{days}"))
        bot.send_message(m.chat.id, "اختر المستخدم:", reply_markup=mk)
    except Exception as e:
        logger.error(f"Error listing users for key: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def list_apps_for_key(m, days):
    try:
        apps = db_fs.collection("app_links").limit(30).get()
        if not apps:
            return bot.send_message(m.chat.id, "لا توجد تطبيقات مسجلة.")
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
    except Exception as e:
        logger.error(f"Error listing apps for key: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def create_final_key(m, days, target, target_id):
    try:
        if not str(days).isdigit():
            return bot.send_message(m.chat.id, "❌ عدد الأيام غير صالح.")
        
        if target_id and not validate_input(str(target_id), 200):
            return bot.send_message(m.chat.id, "❌ معرف الهدف غير صالح.")
        
        code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
        db_fs.collection("vouchers").document(code).set({
            "days": int(days),
            "target": target,
            "target_id": target_id,
            "created_at": time.time()
        })
        
        txt = f"🎫 **كود جديد ({days} يوم)**\nالنوع: {target}\n"
        if target_id:
            pkg = target_id.split('_')[-1] if "_" in str(target_id) else target_id
            display = get_bot_names_map().get(pkg, pkg)
            txt += f"الهدف: `{display}`\n"
        txt += f"الكود: `{code}`"
        bot.send_message(m.chat.id, txt, parse_mode="Markdown")
        logger.info(f"Voucher created: {code} for {days} days, target: {target}")
    except Exception as e:
        logger.error(f"Error creating final key: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ في إنشاء الكود.")

def expiry_notifier():
    while True:
        try:
            now = time.time()
            links = db_fs.collection("app_links").get()
            names_map = get_bot_names_map()
            for doc in links:
                data = doc.to_dict()
                time_remaining = data.get("end_time", 0) - now
                if 82800 < time_remaining < 86400:
                    uid = data.get("telegram_id")
                    if uid:
                        pkg = doc.id.split('_')[-1]
                        display = names_map.get(pkg, pkg)
                        try:
                            bot.send_message(uid, f"⚠️ اشتراكك في `{display}` ينتهي غداً!")
                            logger.info(f"Expiry notification sent to {uid} for {display}")
                        except Exception as e:
                            logger.error(f"Error sending expiry notification to {uid}: {e}")
            time.sleep(3600)
        except Exception as e:
            logger.error(f"Error in expiry notifier: {e}")
            time.sleep(60)

def do_bc_tele(m):
    try:
        if not validate_input(m.text, 2000, True):
            return bot.send_message(m.chat.id, "❌ نص الإعلان غير صالح.")
        
        users = db_fs.collection("users").get()
        success_count = 0
        fail_count = 0
        for d in users:
            try:
                bot.send_message(d.id, f"📢 **إعلان:**\n\n{m.text}")
                success_count += 1
                time.sleep(0.05)
            except Exception as e:
                fail_count += 1
                logger.warning(f"Failed to send broadcast to {d.id}: {e}")
        
        bot.send_message(m.chat.id, f"✅ تم الإرسال.\n✅ نجح: {success_count}\n❌ فشل: {fail_count}")
        logger.info(f"Telegram broadcast sent: {success_count} success, {fail_count} failed")
    except Exception as e:
        logger.error(f"Error in telegram broadcast: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def do_bc_app(m):
    try:
        if not validate_input(m.text, 2000, True):
            return bot.send_message(m.chat.id, "❌ نص الخبر غير صالح.")
        
        set_global_news(m.text)
        bot.send_message(m.chat.id, "✅ تم تحديث الخبر.")
        logger.info("Global news updated")
    except Exception as e:
        logger.error(f"Error in app broadcast: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def process_ban_unban(m, mode):
    try:
        target = m.text.strip()
        if not validate_input(target, 200):
            return bot.send_message(m.chat.id, "❌ المعرف غير صالح.")
        
        if get_app_link(target):
            update_app_link(target, {"banned": (mode == "ban_op")})
            bot.send_message(m.chat.id, "✅ تم.")
            logger.info(f"App {'banned' if mode == 'ban_op' else 'unbanned'}: {target}")
        else:
            bot.send_message(m.chat.id, "❌ غير موجود.")
    except Exception as e:
        logger.error(f"Error in ban/unban: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q):
    try:
        bot.answer_pre_checkout_query(q.id, ok=True)
    except Exception as e:
        logger.error(f"Error in pre-checkout: {e}")
        bot.answer_pre_checkout_query(q.id, ok=False, error_message="حدث خطأ")

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    try:
        cid = m.successful_payment.invoice_payload.replace("pay_", "")
        if not validate_input(cid, 200):
            return
        
        link = get_app_link(cid)
        if link:
            new_time = max(time.time(), link.get("end_time", 0)) + (30 * 86400)
            update_app_link(cid, {"end_time": new_time})
            pkg = cid.split('_')[-1]
            display = get_bot_names_map().get(pkg, pkg)
            bot.send_message(m.chat.id, f"✅ تم الشراء بنجاح لـ: `{display}`")
            add_log(f"دفعة ناجحة: {m.from_user.id} لـ {cid}")
            logger.info(f"Successful payment by {m.from_user.id} for {cid}")
    except Exception as e:
        logger.error(f"Error in payment success: {e}")

def run():
    try:
        app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    except Exception as e:
        logger.critical(f"Flask app crashed: {e}")

if __name__ == "__main__":
    try:
        logger.info("Bot starting...")
        Thread(target=run, daemon=True).start()
        Thread(target=expiry_notifier, daemon=True).start()
        logger.info("Bot started successfully")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Bot crashed: {e}")
```
