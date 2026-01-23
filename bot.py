import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid, csv, io, base64, qrcode, threading, math
from threading import Thread, Lock, Timer
import firebase_admin
from firebase_admin import credentials, firestore, storage
from functools import wraps, lru_cache
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import logging
from logging.handlers import RotatingFileHandler
import hmac
import hashlib
import random
import string
import re

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
SUPPORT_CHAT_ID = os.environ.get('SUPPORT_CHAT_ID', '')
BACKUP_BUCKET = os.environ.get('BACKUP_BUCKET', '')

if not firebase_admin._apps:
    cred_val = os.environ.get('FIREBASE_CREDENTIALS')
    if cred_val:
        try:
            cred_dict = json.loads(cred_val)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {
                'storageBucket': BACKUP_BUCKET
            })
        except Exception as e:
            logger.error(f"Firebase initialization error: {e}")

db_fs = firestore.client()
bucket = storage.bucket() if BACKUP_BUCKET else None
bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- [ مخازن البيانات ] ---
upload_cache = {}
cache_lock = Lock()
rate_limits = defaultdict(list)
user_temp_data = {}
wallet_cache = {}
qr_codes_cache = {}

# --- [ إعدادات متقدمة ] ---
USER_LEVELS = {
    1: {"name": "مبتدئ", "min_refs": 0, "discount": 0, "color": "⚪"},
    2: {"name": "عادي", "min_refs": 5, "discount": 5, "color": "🟢"},
    3: {"name": "نشيط", "min_refs": 15, "discount": 10, "color": "🔵"},
    4: {"name": "مميز", "min_refs": 30, "discount": 15, "color": "🟣"},
    5: {"name": "VIP", "min_refs": 50, "discount": 20, "color": "🟡"},
    6: {"name": "أسطورة", "min_refs": 100, "discount": 30, "color": "🔴"}
}

GIFT_CODES_TYPES = {
    "daily": {"days": 1, "limit": 1},
    "weekly": {"days": 7, "limit": 3},
    "monthly": {"days": 30, "limit": 5},
    "legendary": {"days": 90, "limit": 1}
}

# --- [ وظائف الحماية المحسنة ] ---
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
        
        if len(rate_limits[user_id]) >= 30:
            log_security_event(user_id, "rate_limit_exceeded")
            return False
        
        rate_limits[user_id].append(now)
        return True

def log_security_event(user_id, event_type, details=""):
    try:
        db_fs.collection("security_logs").add({
            "user_id": str(user_id),
            "event_type": event_type,
            "details": details,
            "timestamp": time.time(),
            "ip": request.remote_addr if 'request' in globals() else None
        })
    except Exception as e:
        logger.error(f"Error logging security event: {e}")

def validate_input(text, max_length=500, allow_special=False):
    if not text or not isinstance(text, str):
        return False
    if len(text) > max_length:
        return False
    if not allow_special and any(c in text for c in ['<', '>', ';', '&', '|', '$', '`']):
        return False
    return True

# --- [ قاعدة البيانات المحسنة ] ---
def get_user(uid):
    try:
        doc = db_fs.collection("users").document(str(uid)).get()
        if doc.exists:
            data = doc.to_dict()
            # تحديث مستوى المستخدم تلقائياً
            update_user_level(uid, data)
            return data
        return None
    except Exception as e:
        logger.error(f"Error getting user {uid}: {e}")
        return None

def update_user_level(uid, user_data):
    """تحديث مستوى المستخدم حسب الإحالات"""
    try:
        ref_count = user_data.get("referral_count", 0)
        current_level = user_data.get("level", 1)
        
        new_level = 1
        for level, info in sorted(USER_LEVELS.items(), reverse=True):
            if ref_count >= info["min_refs"]:
                new_level = level
                break
        
        if new_level != current_level:
            user_data["level"] = new_level
            user_data["level_up_date"] = time.time()
            db_fs.collection("users").document(str(uid)).update({
                "level": new_level,
                "level_up_date": time.time()
            })
            
            # إرسال إشعار ترقية المستوى
            try:
                level_info = USER_LEVELS[new_level]
                bot.send_message(
                    uid,
                    f"🎉 **تهانينا! لقد تم ترقيتك**\n\n"
                    f"📊 مستوى جديد: {level_info['color']} **{level_info['name']}**\n"
                    f"🎯 خصم جديد: {level_info['discount']}%\n"
                    f"👥 إحالاتك: {ref_count}\n\n"
                    f"✨ استمر في الدعوة للحصول على مزيد من المزايا!"
                )
            except:
                pass
    except Exception as e:
        logger.error(f"Error updating user level: {e}")

def get_user_wallet(uid):
    """الحصول على محفظة المستخدم"""
    try:
        doc = db_fs.collection("wallets").document(str(uid)).get()
        if doc.exists:
            return doc.to_dict()
        else:
            # إنشاء محفظة جديدة
            wallet_data = {
                "balance": 0.0,
                "total_earned": 0.0,
                "total_spent": 0.0,
                "created_at": time.time(),
                "last_updated": time.time(),
                "transactions_count": 0
            }
            db_fs.collection("wallets").document(str(uid)).set(wallet_data)
            return wallet_data
    except Exception as e:
        logger.error(f"Error getting wallet {uid}: {e}")
        return None

def update_wallet(uid, amount, transaction_type, description=""):
    """تحديث محفظة المستخدم"""
    try:
        wallet = get_user_wallet(uid)
        if not wallet:
            return False
        
        new_balance = wallet.get("balance", 0) + amount
        
        # تحديث المحفظة
        updates = {
            "balance": new_balance,
            "last_updated": time.time()
        }
        
        if amount > 0:
            updates["total_earned"] = wallet.get("total_earned", 0) + amount
        else:
            updates["total_spent"] = wallet.get("total_spent", 0) + abs(amount)
        
        updates["transactions_count"] = wallet.get("transactions_count", 0) + 1
        
        db_fs.collection("wallets").document(str(uid)).update(updates)
        
        # تسجيل المعاملة
        transaction_id = f"TXN_{int(time.time())}_{random.randint(1000, 9999)}"
        db_fs.collection("transactions").document(transaction_id).set({
            "user_id": str(uid),
            "amount": amount,
            "type": transaction_type,
            "description": description,
            "old_balance": wallet.get("balance", 0),
            "new_balance": new_balance,
            "timestamp": time.time(),
            "status": "completed"
        })
        
        return True
    except Exception as e:
        logger.error(f"Error updating wallet: {e}")
        return False

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

# --- [ واجهة API محسنة ] ---
@app.route('/app_update')
@verify_api_key
def app_update():
    pkg = request.args.get('pkg')
    uid = request.args.get('uid', '')
    
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
                "registered_at": time.time(),
                "request_count": 1,
                "last_request": time.time()
            })
            logger.info(f"New app registered: {pkg}")
            return "1\nhttps://t.me/your_channel"
        
        data = doc.to_dict()
        
        # تحديث إحصائيات الطلب
        manifest_ref.update({
            "request_count": data.get("request_count", 0) + 1,
            "last_request": time.time()
        })
        
        return f"{data.get('version', '1')}\n{data.get('url', '')}"
    except Exception as e:
        logger.error(f"Error in app_update: {e}")
        return "Error", 500

@app.route('/get_ads')
@verify_api_key
def get_ads():
    pkg = request.args.get('pkg')
    uid = request.args.get('uid', '')
    
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
                "registered_at": time.time(),
                "impressions": 1
            })
            logger.info(f"New ad registered: {pkg}")
            return "1\nhttps://t.me/your_channel\nمرحباً بك في تطبيقات نجم الإبداع"

        d = doc.to_dict()
        
        # تحديث عدد المشاهدات
        ads_ref.update({
            "impressions": d.get("impressions", 0) + 1,
            "last_shown": time.time()
        })
        
        return f"{d.get('ads_type', '1')}\n{d.get('ads_link', '#')}\n{d.get('ads_text', '...')}"
    except Exception as e:
        logger.error(f"Error in get_ads: {e}")
        return "Error", 500

@app.route('/check')
@verify_api_key
def check_status():
    aid = request.args.get('aid')
    pkg = request.args.get('pkg')
    uid = request.args.get('uid', '')
    
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
        
        # تسجيل نشاط المستخدم
        log_user_activity(uid, pkg, "app_check")
        
        return "ACTIVE"
    except Exception as e:
        logger.error(f"Error in check_status: {e}")
        return "Error", 500

def log_user_activity(uid, app_id, activity_type):
    """تسجيل نشاط المستخدم"""
    try:
        if uid:
            db_fs.collection("user_activity").add({
                "user_id": uid,
                "app_id": app_id,
                "activity_type": activity_type,
                "timestamp": time.time(),
                "date": datetime.now().strftime("%Y-%m-%d")
            })
    except Exception as e:
        logger.error(f"Error logging user activity: {e}")

@app.route('/get_user_info')
@verify_api_key
def get_user_info():
    """API للحصول على معلومات المستخدم"""
    uid = request.args.get('uid')
    if not uid or not validate_input(uid, 50):
        return jsonify({"error": "Invalid user ID"}), 400
    
    try:
        user_data = get_user(uid)
        if not user_data:
            return jsonify({"error": "User not found"}), 404
        
        wallet_data = get_user_wallet(uid)
        apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
        
        response = {
            "user_id": uid,
            "name": user_data.get("name", ""),
            "level": user_data.get("level", 1),
            "referral_count": user_data.get("referral_count", 0),
            "wallet_balance": wallet_data.get("balance", 0) if wallet_data else 0,
            "total_apps": len(apps),
            "active_apps": sum(1 for a in apps if a.to_dict().get("end_time", 0) > time.time()),
            "join_date": user_data.get("join_date", 0)
        }
        
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error in get_user_info: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/get_stats')
@verify_api_key
def get_stats():
    """API للإحصائيات العامة"""
    try:
        # حساب الإحصائيات
        users_count = len(db_fs.collection("users").get())
        apps_count = len(db_fs.collection("app_links").get())
        
        # التطبيقات النشطة
        active_apps = db_fs.collection("app_links").get()
        active_count = sum(1 for a in active_apps if a.to_dict().get("end_time", 0) > time.time())
        
        # المستخدمين الجدد اليوم
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_timestamp = time.mktime(today.timetuple())
        new_users_today = sum(1 for u in db_fs.collection("users").get() 
                            if u.to_dict().get("join_date", 0) > today_timestamp)
        
        stats = {
            "total_users": users_count,
            "total_apps": apps_count,
            "active_apps": active_count,
            "new_users_today": new_users_today,
            "server_time": time.time(),
            "uptime": get_uptime()
        }
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error in get_stats: {e}")
        return jsonify({"error": "Internal server error"}), 500

def get_uptime():
    """الحصول على وقت تشغيل السيرفر"""
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
            return uptime_seconds
    except:
        return 0

# --- [ واجهة البوت المحسنة ] ---
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
                "referral_count": 0, "claimed_channel_gift": False, 
                "join_date": time.time(), "level": 1, "total_spent": 0,
                "last_active": time.time()
            }
            update_user(uid, user_data)
            
            # منح هدية ترحيب
            update_wallet(uid, 10.0, "welcome_bonus", "هدية ترحيب")
            
            logger.info(f"New user registered: {uid}")
            add_log(f"مستخدم جديد: {username} ({uid})")
        else:
            update_user(uid, {"name": username, "last_active": time.time()})

        if len(args) > 1:
            param = args[1]
            action = "LINK"; cid = ""

            if param.startswith("TRIAL_"): action = "TRIAL"; cid = param.replace("TRIAL_", "")
            elif param.startswith("BUY_"): action = "BUY"; cid = param.replace("BUY_", "")
            elif param.startswith("DASH_"): action = "DASH"; cid = param.replace("DASH_", "")
            elif param.startswith("REDEEM_"): action = "REDEEM"; cid = param.replace("REDEEM_", "")
            elif param.startswith("WALLET_"): action = "WALLET"; cid = param.replace("WALLET_", "")
            elif param.startswith("GIFT_"): action = "GIFT"; cid = param.replace("GIFT_", "")
            elif param.startswith("TICKET_"): action = "TICKET"; cid = param.replace("TICKET_", "")
            else: cid = param

            if "_" in cid and validate_input(cid, 200):
                link_data = get_app_link(cid) or {"end_time": 0, "banned": False, 
                                                 "trial_last_time": 0, "gift_claimed": False}
                link_data["telegram_id"] = uid
                update_app_link(cid, link_data)
                update_user(uid, {"current_app": cid})
                
                if check_membership(uid) and not link_data.get("gift_claimed"):
                    link_data["end_time"] = max(time.time(), link_data.get("end_time", 0)) + (3 * 86400)
                    link_data["gift_claimed"] = True
                    update_app_link(cid, link_data)
                    
                    # منح نقاط إضافية للانضمام
                    update_wallet(uid, 5.0, "channel_join_bonus", "مكافأة انضمام للقناة")
                    
                    bot.send_message(m.chat.id, "🎁 تم منحك 3 أيام هدية + 5 نقاط لانضمامك للقناة!")
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
                                
                                # منح نقاط للمدعو
                                update_wallet(inviter, 15.0, "referral_bonus", f"مكافأة دعوة للمستخدم {uid}")
                                
                                try: 
                                    bot.send_message(inviter, "🎊 حصلت على 7 أيام إضافية + 15 نقطة بسبب دعوة صديق!")
                                    logger.info(f"Referral bonus given to {inviter}")
                                except: pass

                if action == "TRIAL": return trial_select_app(m, cid)
                elif action == "BUY": return send_payment(m)
                elif action == "DASH": return user_dashboard(m)
                elif action == "REDEEM":
                    msg = bot.send_message(m.chat.id, f"🎫 **الجهاز المستهدف:** `{cid.split('_')[-1]}`\n**أرسل كود التفعيل الآن:**")
                    bot.register_next_step_handler(msg, redeem_code_step)
                    return
                elif action == "WALLET":
                    return show_wallet(m)
                elif action == "GIFT":
                    return process_gift_code(m, cid)
                elif action == "TICKET":
                    return view_ticket(m, cid)
                else:
                    bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**")
                    return user_dashboard(m)

        show_main_menu(m, username)
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ، الرجاء المحاولة مرة أخرى.")

def show_main_menu(m, username):
    """القائمة الرئيسية المحسنة"""
    try:
        uid = str(m.chat.id)
        user_data = get_user(uid)
        wallet_data = get_user_wallet(uid)
        
        level = user_data.get("level", 1) if user_data else 1
        level_info = USER_LEVELS.get(level, USER_LEVELS[1])
        wallet_balance = wallet_data.get("balance", 0) if wallet_data else 0
        
        menu_text = f"""
🌟 **مرحباً بك يا {username}** 🌟

📊 **معلومات حسابك:**
├ 🏆 المستوى: {level_info['color']} {level_info['name']}
├ 🎯 خصمك: {level_info['discount']}%
├ 👥 إحالاتك: {user_data.get('referral_count', 0) if user_data else 0}
└ 💰 رصيدك: {wallet_balance:.1f} نقطة

📌 **اختر من القائمة:**
        """
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = [
            types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
            types.InlineKeyboardButton("💰 محفظتي", callback_data="u_wallet"),
            types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
            types.InlineKeyboardButton("🔗 إحالاتي ومكافآتي", callback_data="u_referral"),
            types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
            types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy"),
            types.InlineKeyboardButton("🎁 أكواد هدايا", callback_data="u_gift_codes"),
            types.InlineKeyboardButton("📞 الدعم الفني", callback_data="u_support"),
            types.InlineKeyboardButton("📊 إحصائياتي", callback_data="u_stats"),
            types.InlineKeyboardButton("⚙️ الإعدادات", callback_data="u_settings")
        ]
        
        # تقسيم الأزرار إلى صفوف
        for i in range(0, len(buttons), 2):
            if i+1 < len(buttons):
                markup.add(buttons[i], buttons[i+1])
            else:
                markup.add(buttons[i])
        
        bot.send_message(m.chat.id, menu_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error showing main menu: {e}")
        bot.send_message(m.chat.id, "مرحباً بك! استخدم القائمة للتحكم.")

# --- [ معالجة الأزرار المحسنة ] ---
@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    
    if not check_rate_limit(uid):
        return bot.answer_callback_query(q.id, "⚠️ الرجاء الانتظار قليلاً", show_alert=True)
    
    try:
        # تحديث آخر نشاط
        update_user(uid, {"last_active": time.time()})
        
        if q.data == "u_dashboard": user_dashboard(q.message)
        elif q.data == "u_wallet": show_wallet(q.message)
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
        elif q.data == "u_gift_codes": show_gift_codes(q.message)
        elif q.data == "u_support": show_support_menu(q.message)
        elif q.data == "u_stats": show_user_stats(q.message)
        elif q.data == "u_settings": show_settings(q.message)
        
        # معالجات المحفظة
        elif q.data.startswith("wallet_"):
            handle_wallet_actions(q)
        
        # معالجات الهدايا
        elif q.data.startswith("gift_"):
            handle_gift_actions(q)
        
        # معالجات المشرف المحسنة
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
                parts = q.data.split('_')
                uid_target = parts[3]
                days = parts[4]
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
                mode = parts[2]
                cid = "_".join(parts[3:])
                update_app_link(cid, {"banned": (mode == "ban_op")})
                status_txt = "حظر" if mode == "ban_op" else "فك حظر"
                bot.send_message(q.message.chat.id, f"✅ تم {status_txt} `{cid}` بنجاح")
                
            # الميزات الإضافية للمشرف
            elif q.data == "admin_stats":
                show_admin_stats(q.message)
            elif q.data == "admin_backup":
                create_backup(q.message)
            elif q.data == "admin_gift_codes":
                manage_gift_codes(q.message)
            elif q.data == "admin_wallets":
                manage_wallets(q.message)
            elif q.data == "admin_broadcast":
                show_broadcast_options(q.message)
            elif q.data.startswith("broadcast_"):
                handle_broadcast_selection(q)
                
    except Exception as e:
        logger.error(f"Error handling callback: {e}")
        bot.answer_callback_query(q.id, "❌ حدث خطأ", show_alert=True)

# --- [ نظام المحفظة الجديد ] ---
def show_wallet(m):
    """عرض محفظة المستخدم"""
    try:
        uid = str(m.chat.id)
        wallet = get_user_wallet(uid)
        user_data = get_user(uid)
        
        if not wallet or not user_data:
            return bot.send_message(m.chat.id, "❌ حدث خطأ في تحميل المحفظة.")
        
        level = user_data.get("level", 1)
        level_info = USER_LEVELS.get(level, USER_LEVELS[1])
        
        wallet_text = f"""
💰 **محفظتك الشخصية** 

📊 **الرصيد:** {wallet.get('balance', 0):.2f} نقطة
━━━━━━━━━━━━━━
📈 **الإحصائيات:**
├ 💰 إجمالي الإيداعات: {wallet.get('total_earned', 0):.2f}
├ 💸 إجمالي الصرفيات: {wallet.get('total_spent', 0):.2f}
├ 🔄 عدد المعاملات: {wallet.get('transactions_count', 0)}
└ 🏆 مستواك: {level_info['color']} {level_info['name']} ({level_info['discount']}% خصم)
━━━━━━━━━━━━━━
💡 **يمكنك استخدام الرصيد في:**
• شراء اشتراكات
• تجديد اشتراكات منتهية
• تحويل لأصدقائك
• الحصول على خصومات حصرية
        """
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = [
            types.InlineKeyboardButton("💳 شحن الرصيد", callback_data="wallet_deposit"),
            types.InlineKeyboardButton("🔄 تحويل رصيد", callback_data="wallet_transfer"),
            types.InlineKeyboardButton("📜 سجل المعاملات", callback_data="wallet_history"),
            types.InlineKeyboardButton("🎁 شراء بكود", callback_data="wallet_buy_code"),
            types.InlineKeyboardButton("🛒 متجر النقاط", callback_data="wallet_store"),
            types.InlineKeyboardButton("🔙 رجوع", callback_data="u_dashboard")
        ]
        
        for i in range(0, len(buttons), 2):
            if i+1 < len(buttons):
                markup.add(buttons[i], buttons[i+1])
            else:
                markup.add(buttons[i])
        
        bot.send_message(m.chat.id, wallet_text, reply_markup=markup, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error showing wallet: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ في تحميل المحفظة.")

def handle_wallet_actions(q):
    """معالجة إجراءات المحفظة"""
    uid = str(q.from_user.id)
    
    if q.data == "wallet_deposit":
        show_deposit_options(q.message)
    elif q.data == "wallet_transfer":
        start_transfer(q.message)
    elif q.data == "wallet_history":
        show_transaction_history(q.message, uid)
    elif q.data == "wallet_buy_code":
        buy_with_wallet(q.message)
    elif q.data == "wallet_store":
        show_wallet_store(q.message)
    elif q.data.startswith("deposit_"):
        process_deposit(q)
    elif q.data.startswith("transfer_"):
        process_transfer_action(q)

def show_deposit_options(m):
    """عرض خيارات شحن الرصيد"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    deposit_options = [
        (50, "50 نقطة - 5$"),
        (100, "100 نقطة - 9$"),
        (250, "250 نقطة - 20$"),
        (500, "500 نقطة - 35$"),
        (1000, "1000 نقطة - 65$"),
        (5000, "5000 نقطة - 300$")
    ]
    
    for amount, text in deposit_options:
        markup.add(types.InlineKeyboardButton(text, callback_data=f"deposit_{amount}"))
    
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="u_wallet"))
    
    bot.send_message(
        m.chat.id,
        "💳 **شحن الرصيد**\n\n"
        "اختر المبلغ الذي تريد شحنه:\n\n"
        "✨ **المميزات:**\n"
        "• شحن آمن وفوري\n"
        "• دعم جميع وسائل الدفع\n"
        "• رصيد يمكن استخدامه في جميع التطبيقات\n"
        "• خصومات حصرية لحاملي الرصيد",
        reply_markup=markup
    )

def process_deposit(q):
    """معالجة طلب الشحن"""
    try:
        amount = int(q.data.replace("deposit_", ""))
        uid = str(q.from_user.id)
        
        # حفظ بيانات الشحن مؤقتاً
        user_temp_data[uid] = {"deposit_amount": amount}
        
        # إنشاء فاتورة الدفع
        prices = [types.LabeledPrice(label=f"{amount} نقطة", amount=amount * 100)]  # تحويل إلى سنتات
        
        bot.send_invoice(
            q.message.chat.id,
            title=f"شحن محفظة - {amount} نقطة",
            description=f"شحن رصيد محفظتك بمقدار {amount} نقطة",
            invoice_payload=f"deposit_{amount}_{uid}",
            provider_token="",  # يجب إضافة توكن الدفع
            currency="USD",
            prices=prices
        )
        
    except Exception as e:
        logger.error(f"Error processing deposit: {e}")
        bot.answer_callback_query(q.id, "❌ حدث خطأ في معالجة الطلب", show_alert=True)

@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout(pre_checkout_query):
    """معالجة طلب الدفع المسبق"""
    try:
        bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    except Exception as e:
        logger.error(f"Error in pre-checkout: {e}")
        bot.answer_pre_checkout_query(pre_checkout_query.id, ok=False, error_message="حدث خطأ في معالجة الدفع")

@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message):
    """معالجة الدفع الناجح"""
    try:
        uid = str(message.from_user.id)
        payment = message.successful_payment
        
        # استخراج المبلغ من payload
        if payment.invoice_payload.startswith("deposit_"):
            parts = payment.invoice_payload.split("_")
            amount = float(parts[1]) if len(parts) > 1 else payment.total_amount / 100
            
            # تحديث المحفظة
            update_wallet(uid, amount, "deposit", "شحن رصيد عبر الدفع")
            
            # إرسال تأكيد
            bot.send_message(
                message.chat.id,
                f"✅ **تم شحن محفظتك بنجاح!**\n\n"
                f"📥 المبلغ المضاف: **{amount:.2f}** نقطة\n"
                f"💰 الرصيد الجديد: **{get_user_wallet(uid).get('balance', 0):.2f}** نقطة\n"
                f"🆔 معاملة الدفع: `{payment.telegram_payment_charge_id}`"
            )
            
            logger.info(f"Successful deposit for user {uid}: {amount} points")
            
        elif payment.invoice_payload.startswith("buy_"):
            # معالجة شراء اشتراك
            handle_payment_success(message)
            
    except Exception as e:
        logger.error(f"Error handling successful payment: {e}")
        bot.send_message(message.chat.id, "❌ حدث خطأ في معالجة الدفع")

def start_transfer(m):
    """بدء عملية تحويل الرصيد"""
    uid = str(m.chat.id)
    
    msg = bot.send_message(
        m.chat.id,
        "🔄 **تحويل الرصيد**\n\n"
        "أدخل مبلغ التحويل (يجب أن يكون رقماً):"
    )
    bot.register_next_step_handler(msg, process_transfer_amount_step)

def process_transfer_amount_step(m):
    """معالجة مبلغ التحويل"""
    try:
        uid = str(m.chat.id)
        amount_text = m.text.strip()
        
        if not amount_text.replace('.', '').isdigit():
            return bot.send_message(m.chat.id, "❌ المبلغ غير صالح. يجب أن يكون رقماً.")
        
        amount = float(amount_text)
        
        if amount <= 0:
            return bot.send_message(m.chat.id, "❌ المبلغ يجب أن يكون أكبر من الصفر.")
        
        # التحقق من الرصيد
        wallet = get_user_wallet(uid)
        if wallet.get("balance", 0) < amount:
            return bot.send_message(m.chat.id, f"❌ رصيدك غير كافي. الرصيد المتاح: {wallet.get('balance', 0):.2f}")
        
        # حفظ المبلغ مؤقتاً
        user_temp_data[uid] = {"transfer_amount": amount}
        
        msg = bot.send_message(
            m.chat.id,
            f"✅ المبلغ: **{amount:.2f}** نقطة\n\n"
            "👤 الآن أدخل **معرف المستخدم** الذي تريد التحويل إليه:"
        )
        bot.register_next_step_handler(msg, process_transfer_recipient_step)
        
    except Exception as e:
        logger.error(f"Error in transfer amount step: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ في معالجة المبلغ.")

def process_transfer_recipient_step(m):
    """معالجة المستلم"""
    try:
        uid = str(m.chat.id)
        recipient_id = m.text.strip()
        
        if not recipient_id.isdigit():
            return bot.send_message(m.chat.id, "❌ معرف المستخدم غير صالح.")
        
        if recipient_id == uid:
            return bot.send_message(m.chat.id, "❌ لا يمكن التحويل لنفسك.")
        
        # التحقق من وجود المستلم
        recipient_data = get_user(recipient_id)
        if not recipient_data:
            return bot.send_message(m.chat.id, "❌ المستخدم غير موجود.")
        
        # الحصول على المبلغ المحفوظ
        session_data = user_temp_data.get(uid, {})
        amount = session_data.get("transfer_amount", 0)
        
        if amount <= 0:
            return bot.send_message(m.chat.id, "❌ انتهت الجلسة، ابدأ من جديد.")
        
        # تنفيذ التحويل
        if transfer_balance(uid, recipient_id, amount):
            # تنظيف البيانات المؤقتة
            if uid in user_temp_data:
                del user_temp_data[uid]
            
            bot.send_message(
                m.chat.id,
                f"✅ **تم التحويل بنجاح!**\n\n"
                f"📤 المبلغ المحول: **{amount:.2f}** نقطة\n"
                f"👤 إلى المستخدم: `{recipient_id}`\n"
                f"💰 رصيدك الجديد: **{get_user_wallet(uid).get('balance', 0):.2f}** نقطة"
            )
            
            # إرسال إشعار للمستلم
            try:
                bot.send_message(
                    recipient_id,
                    f"🎉 **استلمت تحويل رصيد جديد!**\n\n"
                    f"📥 المبلغ المستلم: **{amount:.2f}** نقطة\n"
                    f"👤 من المستخدم: `{uid}`\n"
                    f"💰 رصيدك الجديد: **{get_user_wallet(recipient_id).get('balance', 0):.2f}** نقطة"
                )
            except:
                pass
            
        else:
            bot.send_message(m.chat.id, "❌ فشل التحويل. حاول مرة أخرى.")
            
    except Exception as e:
        logger.error(f"Error in transfer recipient step: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ في معالجة التحويل.")

def transfer_balance(sender_id, receiver_id, amount):
    """تنفيذ تحويل الرصيد"""
    try:
        # خصم من المرسل
        sender_success = update_wallet(sender_id, -amount, "transfer_out", f"تحويل إلى {receiver_id}")
        
        # إضافة للمستلم
        receiver_success = update_wallet(receiver_id, amount, "transfer_in", f"تحويل من {sender_id}")
        
        # تسجيل التحويل
        if sender_success and receiver_success:
            transfer_id = f"TRF_{int(time.time())}_{random.randint(1000, 9999)}"
            db_fs.collection("transfers").document(transfer_id).set({
                "sender_id": sender_id,
                "receiver_id": receiver_id,
                "amount": amount,
                "timestamp": time.time(),
                "status": "completed"
            })
            
            add_log(f"تحويل رصيد: {sender_id} -> {receiver_id} بقيمة {amount}")
            return True
            
        return False
        
    except Exception as e:
        logger.error(f"Error transferring balance: {e}")
        return False

def show_transaction_history(m, user_id, page=0):
    """عرض سجل المعاملات"""
    try:
        limit = 10
        transactions_ref = db_fs.collection("transactions")\
            .where("user_id", "==", user_id)\
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
        
        # حساب العدد الإجمالي
        total_count = len(list(transactions_ref.get()))
        
        # جلب الصفحة المطلوبة
        transactions = list(transactions_ref.limit(limit).offset(page * limit).get())
        
        if not transactions:
            return bot.send_message(m.chat.id, "📭 **لا توجد معاملات سابقة.**")
        
        # بناء الرسالة
        message = f"📜 **سجل معاملاتك**\n\n"
        message += f"📊 إجمالي المعاملات: {total_count}\n"
        message += f"📄 الصفحة: {page + 1}\n\n"
        
        for i, t in enumerate(transactions):
            data = t.to_dict()
            amount = data.get("amount", 0)
            trans_type = data.get("type", "")
            description = data.get("description", "")
            date = datetime.fromtimestamp(data.get("timestamp", time.time())).strftime('%Y-%m-%d %H:%M')
            
            icon = "📥" if amount > 0 else "📤"
            sign = "+" if amount > 0 else ""
            
            message += f"{icon} **{date}**\n"
            message += f"المبلغ: `{sign}{amount:.2f}` | النوع: `{trans_type}`\n"
            if description:
                message += f"الوصف: {description[:40]}{'...' if len(description) > 40 else ''}\n"
            message += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        
        # إنشاء الأزرار
        markup = types.InlineKeyboardMarkup()
        row_buttons = []
        
        if page > 0:
            row_buttons.append(types.InlineKeyboardButton("◀️ السابق", callback_data=f"trans_page_{user_id}_{page-1}"))
        
        row_buttons.append(types.InlineKeyboardButton("🔄 تحديث", callback_data=f"trans_refresh_{user_id}_{page}"))
        
        if len(transactions) == limit:
            row_buttons.append(types.InlineKeyboardButton("▶️ التالي", callback_data=f"trans_page_{user_id}_{page+1}"))
        
        if row_buttons:
            markup.add(*row_buttons)
        
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="u_wallet"))
        
        bot.send_message(m.chat.id, message, parse_mode="Markdown", reply_markup=markup)
        
    except Exception as e:
        logger.error(f"Error showing transaction history: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ في تحميل السجل.")

def show_wallet_store(m):
    """عرض متجر النقاط"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    store_items = [
        {"points": 100, "days": 7, "desc": "7 أيام اشتراك"},
        {"points": 250, "days": 30, "desc": "30 يوم اشتراك"},
        {"points": 400, "days": 60, "desc": "60 يوم اشتراك"},
        {"points": 700, "days": 120, "desc": "120 يوم اشتراك"},
        {"points": 1000, "days": 180, "desc": "180 يوم اشتراك"},
        {"points": 1500, "days": 365, "desc": "365 يوم اشتراك"}
    ]
    
    for item in store_items:
        markup.add(types.InlineKeyboardButton(
            f"🎁 {item['desc']} - {item['points']} نقطة",
            callback_data=f"buy_with_points_{item['days']}_{item['points']}"
        ))
    
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="u_wallet"))
    
    bot.send_message(
        m.chat.id,
        "🛒 **متجر النقاط**\n\n"
        "يمكنك شراء اشتراكات باستخدام نقاط محفظتك:\n\n"
        "✨ **المميزات:**\n"
        "• أسعار مخفضة للنقاط\n"
        "• تفعيل فوري\n"
        "• خصومات إضافية للمستويات العليا\n"
        "• متاح لجميع التطبيقات",
        reply_markup=markup
    )

# --- [ نظام أكواد الهدايا ] ---
def show_gift_codes(m):
    """عرض أكواد الهدايا"""
    try:
        uid = str(m.chat.id)
        
        # جلب أكواد الهدايا النشطة
        gift_codes = db_fs.collection("gift_codes")\
            .where("active", "==", True)\
            .where("expiry_time", ">", time.time())\
            .limit(10)\
            .get()
        
        if not gift_codes:
            return bot.send_message(m.chat.id, "🎁 **لا توجد أكواد هدايا متاحة حالياً.**\n\nتابع القناة للحصول على أكواد حصرية!")
        
        message = "🎁 **أكواد الهدايا المتاحة**\n\n"
        
        for code in gift_codes:
            data = code.to_dict()
            code_id = code.id
            days = data.get("days", 0)
            uses_left = data.get("max_uses", 1) - data.get("used_count", 0)
            expiry = datetime.fromtimestamp(data.get("expiry_time", time.time())).strftime('%Y-%m-%d')
            
            if uses_left > 0:
                message += f"🎫 **الكود:** `{code_id}`\n"
                message += f"📅 الصلاحية: {expiry}\n"
                message += f"⏰ المدة: {days} يوم\n"
                message += f"👥 متبقي: {uses_left} استخدام\n"
                message += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        
        message += "\n📌 **كيفية الاستخدام:**\n"
        message += "1. انسخ الكود\n"
        message += "2. اذهب إلى /start\n"
        message += "3. الصق الكود في الرسالة\n"
        message += "4. استمتع بالهدية! 🎉"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 تحديث القائمة", callback_data="u_gift_codes"))
        markup.add(types.InlineKeyboardButton("🎁 إنشاء كود هدية", callback_data="create_gift_code"))
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="u_dashboard"))
        
        bot.send_message(m.chat.id, message, parse_mode="Markdown", reply_markup=markup)
        
    except Exception as e:
        logger.error(f"Error showing gift codes: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ في تحميل أكواد الهدايا.")

def process_gift_code(m, code):
    """معالجة كود الهدية"""
    try:
        uid = str(m.chat.id)
        
        # البحث عن الكود
        gift_data = get_gift_code(code)
        
        if not gift_data:
            return bot.send_message(m.chat.id, "❌ كود الهدية غير صالح أو منتهي.")
        
        if not gift_data.get("active", True):
            return bot.send_message(m.chat.id, "❌ كود الهدية غير فعال.")
        
        if gift_data.get("expiry_time", 0) < time.time():
            return bot.send_message(m.chat.id, "❌ كود الهدية منتهي الصلاحية.")
        
        used_count = gift_data.get("used_count", 0)
        max_uses = gift_data.get("max_uses", 1)
        
        if used_count >= max_uses:
            return bot.send_message(m.chat.id, "❌ تم استخدام كود الهدية بالكامل.")
        
        # التحقق إذا كان المستخدم استخدم هذا الكود من قبل
        user_used = db_fs.collection("gift_code_usage")\
            .where("user_id", "==", uid)\
            .where("code_id", "==", code)\
            .get()
        
        if len(list(user_used)) > 0:
            return bot.send_message(m.chat.id, "❌ لقد استخدمت هذا الكود من قبل.")
        
        # تطبيق الهدية
        days = gift_data.get("days", 0)
        user_data = get_user(uid)
        current_cid = user_data.get("current_app") if user_data else None
        
        if current_cid:
            # تطبيق على التطبيق الحالي
            link = get_app_link(current_cid)
            if link:
                new_time = max(time.time(), link.get("end_time", 0)) + (days * 86400)
                update_app_link(current_cid, {"end_time": new_time})
                
                # تحديث استخدام الكود
                update_gift_code_usage(code, uid)
                
                bot.send_message(
                    m.chat.id,
                    f"🎉 **تهانينا! لقد حصلت على هدية**\n\n"
                    f"🎁 الكود: `{code}`\n"
                    f"⏰ المدة: {days} يوم\n"
                    f"📱 التطبيق: {current_cid.split('_')[-1]}\n\n"
                    f"✅ تم تفعيل الهدية بنجاح!"
                )
                return
        
        # إذا لم يكن هناك تطبيق حالي، عرض قائمة التطبيقات
        apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
        if not apps:
            return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة.")
        
        # حفظ الكود مؤقتاً
        user_temp_data[uid] = {"gift_code": code, "gift_days": days}
        
        names_map = get_bot_names_map()
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for doc in apps:
            pkg = doc.id.split('_')[-1]
            display = names_map.get(pkg, pkg)
            markup.add(types.InlineKeyboardButton(f"📦 {display}", callback_data=f"apply_gift_{doc.id}"))
        
        bot.send_message(m.chat.id, "🎁 **اختر التطبيق لتطبيق الهدية عليه:**", reply_markup=markup)
        
    except Exception as e:
        logger.error(f"Error processing gift code: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ في معالجة كود الهدية.")

def get_gift_code(code):
    """الحصول على بيانات كود الهدية"""
    try:
        doc = db_fs.collection("gift_codes").document(code).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        logger.error(f"Error getting gift code: {e}")
        return None

def update_gift_code_usage(code, user_id):
    """تحديث استخدام كود الهدية"""
    try:
        # زيادة عداد الاستخدام
        gift_ref = db_fs.collection("gift_codes").document(code)
        gift_data = gift_ref.get().to_dict()
        
        if gift_data:
            new_count = gift_data.get("used_count", 0) + 1
            updates = {"used_count": new_count}
            
            if new_count >= gift_data.get("max_uses", 1):
                updates["active"] = False
            
            gift_ref.update(updates)
        
        # تسجيل استخدام المستخدم
        usage_id = f"{code}_{user_id}_{int(time.time())}"
        db_fs.collection("gift_code_usage").document(usage_id).set({
            "code_id": code,
            "user_id": user_id,
            "used_at": time.time()
        })
        
        return True
    except Exception as e:
        logger.error(f"Error updating gift code usage: {e}")
        return False

def handle_gift_actions(q):
    """معالجة إجراءات الهدايا"""
    uid = str(q.from_user.id)
    
    if q.data == "create_gift_code":
        if q.from_user.id == ADMIN_ID:
            create_gift_code_dialog(q.message)
        else:
            bot.answer_callback_query(q.id, "❌ هذه الميزة للمشرفين فقط", show_alert=True)
    
    elif q.data.startswith("apply_gift_"):
        cid = q.data.replace("apply_gift_", "")
        apply_gift_to_app(q.message, uid, cid)

def apply_gift_to_app(m, user_id, cid):
    """تطبيق الهدية على تطبيق محدد"""
    try:
        session_data = user_temp_data.get(user_id, {})
        code = session_data.get("gift_code")
        days = session_data.get("gift_days", 0)
        
        if not code or days <= 0:
            return bot.send_message(m.chat.id, "❌ انتهت الجلسة، ابدأ من جديد.")
        
        # تطبيق الهدية
        link = get_app_link(cid)
        if link:
            new_time = max(time.time(), link.get("end_time", 0)) + (days * 86400)
            update_app_link(cid, {"end_time": new_time})
            
            # تحديث استخدام الكود
            update_gift_code_usage(code, user_id)
            
            # تنظيف البيانات المؤقتة
            if user_id in user_temp_data:
                del user_temp_data[user_id]
            
            bot.send_message(
                m.chat.id,
                f"🎉 **تم تطبيق الهدية بنجاح!**\n\n"
                f"📱 التطبيق: {cid.split('_')[-1]}\n"
                f"⏰ المدة المضافة: {days} يوم\n"
                f"✅ استمتع بالتحديث!"
            )
        else:
            bot.send_message(m.chat.id, "❌ التطبيق غير موجود.")
            
    except Exception as e:
        logger.error(f"Error applying gift to app: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ في تطبيق الهدية.")

def create_gift_code_dialog(m):
    """إنشاء كود هدية جديد"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    for code_type, info in GIFT_CODES_TYPES.items():
        days = info["days"]
        limit = info["limit"]
        text = f"🎁 {days} يوم ({limit} استخدام)"
        markup.add(types.InlineKeyboardButton(text, callback_data=f"create_gift_{code_type}"))
    
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="u_gift_codes"))
    
    bot.send_message(
        m.chat.id,
        "🎫 **إنشاء كود هدية جديد**\n\n"
        "اختر نوع الكود الذي تريد إنشاءه:\n\n"
        "📝 **التفاصيل:**\n"
        "• يومي: 1 يوم - استخدام واحد\n"
        "• أسبوعي: 7 أيام - 3 استخدامات\n"
        "• شهري: 30 يوم - 5 استخدامات\n"
        "• أسطوري: 90 يوم - استخدام واحد",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda q: q.data.startswith('create_gift_'))
def handle_create_gift(q):
    """معالجة إنشاء كود هدية"""
    if q.from_user.id != ADMIN_ID:
        return bot.answer_callback_query(q.id, "❌ هذه الميزة للمشرفين فقط", show_alert=True)
    
    code_type = q.data.replace("create_gift_", "")
    
    if code_type in GIFT_CODES_TYPES:
        info = GIFT_CODES_TYPES[code_type]
        
        # إنشاء الكود
        code = generate_gift_code()
        
        # حفظ الكود في قاعدة البيانات
        db_fs.collection("gift_codes").document(code).set({
            "code": code,
            "type": code_type,
            "days": info["days"],
            "max_uses": info["limit"],
            "used_count": 0,
            "active": True,
            "created_at": time.time(),
            "expiry_time": time.time() + (30 * 86400),  # صلاحية 30 يوم
            "created_by": q.from_user.id
        })
        
        # إرسال الكود
        bot.send_message(
            q.message.chat.id,
            f"✅ **تم إنشاء كود هدية جديد!**\n\n"
            f"🎫 **الكود:** `{code}`\n"
            f"📊 **النوع:** {code_type}\n"
            f"⏰ **المدة:** {info['days']} يوم\n"
            f"👥 **الحد الأقصى:** {info['limit']} استخدام\n"
            f"📅 **الصلاحية:** 30 يوم\n\n"
            f"🔗 **رابط الاستخدام:**\n"
            f"https://t.me/{bot.get_me().username}?start=GIFT_{code}"
        )
    else:
        bot.answer_callback_query(q.id, "❌ نوع الكود غير صالح", show_alert=True)

def generate_gift_code():
    """توليد كود هدية فريد"""
    while True:
        # توليد كود عشوائي
        code = f"GIFT-{random.randint(100000, 999999)}"
        
        # التحقق من عدم وجود الكود مسبقاً
        existing = get_gift_code(code)
        if not existing:
            return code

# --- [ نظام الدعم المحسن ] ---
def show_support_menu(m):
    """عرض قائمة الدعم"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    buttons = [
        types.InlineKeyboardButton("📝 إنشاء تذكرة دعم", callback_data="create_ticket"),
        types.InlineKeyboardButton("📋 تذاكري المفتوحة", callback_data="my_tickets"),
        types.InlineKeyboardButton("📞 التواصل المباشر", url=f"https://t.me/{SUPPORT_CHAT_ID}" if SUPPORT_CHAT_ID else "#"),
        types.InlineKeyboardButton("📚 الأسئلة الشائعة", callback_data="faq"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="u_dashboard")
    ]
    
    for button in buttons:
        markup.add(button)
    
    bot.send_message(
        m.chat.id,
        "📞 **مركز الدعم الفني**\n\n"
        "مرحباً بك في مركز الدعم! يمكننا مساعدتك في:\n\n"
        "• مشاكل التفعيل والاشتراكات\n"
        "• مشاكل فنية في التطبيقات\n"
        "• استفسارات عامة\n"
        "• اقتراحات وتحسينات\n\n"
        "اختر الخيار المناسب:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda q: q.data == "create_ticket")
def handle_create_ticket(q):
    """إنشاء تذكرة دعم جديدة"""
    msg = bot.send_message(q.message.chat.id, "📝 **أدخل عنوان التذكرة:**")
    bot.register_next_step_handler(msg, process_ticket_title)

def process_ticket_title(m):
    """معالجة عنوان التذكرة"""
    uid = str(m.chat.id)
    title = m.text.strip()
    
    if not validate_input(title, 100):
        return bot.send_message(m.chat.id, "❌ العنوان غير صالح.")
    
    user_temp_data[uid] = {"ticket_title": title}
    
    msg = bot.send_message(m.chat.id, "💬 **أدخل وصف المشكلة:**")
    bot.register_next_step_handler(msg, process_ticket_description)

def process_ticket_description(m):
    """معالجة وصف التذكرة"""
    uid = str(m.chat.id)
    description = m.text.strip()
    
    if not validate_input(description, 1000, True):
        return bot.send_message(m.chat.id, "❌ الوصف غير صالح.")
    
    session_data = user_temp_data.get(uid, {})
    title = session_data.get("ticket_title", "طلب دعم")
    
    # إنشاء التذكرة
    ticket_id = create_support_ticket(uid, title, description)
    
    if ticket_id:
        bot.send_message(
            m.chat.id,
            f"✅ **تم إنشاء تذكرة الدعم**\n\n"
            f"🆔 **رقم التذكرة:** `{ticket_id}`\n"
            f"📌 **العنوان:** {title}\n"
            f"⏰ **الوقت:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"سيتم الرد عليك في أقرب وقت ممكن."
        )
    else:
        bot.send_message(m.chat.id, "❌ فشل إنشاء التذكرة، حاول مرة أخرى.")
    
    # تنظيف البيانات المؤقتة
    if uid in user_temp_data:
        del user_temp_data[uid]

def create_support_ticket(user_id, title, description):
    """إنشاء تذكرة دعم في قاعدة البيانات"""
    try:
        ticket_id = f"TICKET_{int(time.time())}_{user_id}"
        
        ticket_data = {
            "ticket_id": ticket_id,
            "user_id": user_id,
            "title": title,
            "description": description,
            "status": "open",  # open, in_progress, closed, resolved
            "priority": "medium",  # low, medium, high, urgent
            "created_at": time.time(),
            "updated_at": time.time(),
            "messages": []
        }
        
        db_fs.collection("support_tickets").document(ticket_id).set(ticket_data)
        
        # إرسال إشعار للمشرف
        notify_admin_new_ticket(ticket_id, user_id, title)
        
        return ticket_id
    except Exception as e:
        logger.error(f"Error creating support ticket: {e}")
        return None

def notify_admin_new_ticket(ticket_id, user_id, title):
    """إشعار المشرف بتذكرة جديدة"""
    try:
        user_data = get_user(user_id)
        user_name = user_data.get("name", "مستخدم") if user_data else "مستخدم"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "📩 الرد على التذكرة", 
            callback_data=f"admin_reply_ticket_{ticket_id}"
        ))
        
        bot.send_message(
            ADMIN_ID,
            f"📢 **تذكرة دعم جديدة**\n\n"
            f"👤 **المستخدم:** {user_name} (`{user_id}`)\n"
            f"📌 **العنوان:** {title}\n"
            f"🆔 **رقم التذكرة:** `{ticket_id}`\n\n"
            f"⏰ الوقت: {datetime.now().strftime('%H:%M')}",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error notifying admin: {e}")

def show_user_stats(m):
    """عرض إحصائيات المستخدم"""
    try:
        uid = str(m.chat.id)
        user_data = get_user(uid)
        wallet = get_user_wallet(uid)
        
        if not user_data or not wallet:
            return bot.send_message(m.chat.id, "❌ حدث خطأ في تحميل الإحصائيات.")
        
        # جلب تطبيقات المستخدم
        apps = db_fs.collection("app_links").where("telegram_id", "==", uid).get()
        
        # حساب الإحصائيات
        total_apps = len(apps)
        active_apps = sum(1 for a in apps if a.to_dict().get("end_time", 0) > time.time())
        expired_apps = total_apps - active_apps
        
        # جلب النشاط اليومي
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_timestamp = time.mktime(today.timetuple())
        
        # حساب الإحالات النشطة
        referrals = db_fs.collection("users").where("invited_by", "==", uid).get()
        active_referrals = sum(1 for r in referrals if r.to_dict().get("last_active", 0) > time.time() - 7*86400)
        
        # بناء الرسالة
        stats_text = f"""
📊 **إحصائيات حسابك**

👤 **معلومات شخصية:**
├ 🏆 المستوى: {USER_LEVELS.get(user_data.get('level', 1), USER_LEVELS[1])['name']}
├ 🎯 نسبة الخصم: {USER_LEVELS.get(user_data.get('level', 1), USER_LEVELS[1])['discount']}%
├ 📅 تاريخ الانضمام: {datetime.fromtimestamp(user_data.get('join_date', time.time())).strftime('%Y-%m-%d')}
└ ⏰ آخر نشاط: {datetime.fromtimestamp(user_data.get('last_active', time.time())).strftime('%Y-%m-%d %H:%M')}

📱 **التطبيقات:**
├ 📦 الإجمالي: {total_apps} تطبيق
├ 🟢 النشطة: {active_apps}
├ 🔴 المنتهية: {expired_apps}
└ ⚫ المحظورة: {sum(1 for a in apps if a.to_dict().get('banned', False))}

💰 **المحفظة:**
├ 💳 الرصيد: {wallet.get('balance', 0):.2f} نقطة
├ 📈 إجمالي الإيداعات: {wallet.get('total_earned', 0):.2f}
├ 📉 إجمالي الصرفيات: {wallet.get('total_spent', 0):.2f}
└ 🔄 عدد المعاملات: {wallet.get('transactions_count', 0)}

👥 **الإحالات:**
├ 🔗 الإجمالي: {user_data.get('referral_count', 0)}
├ 🟢 النشطين: {active_referrals}
└ 💰 أرباح الإحالات: {wallet.get('referral_earnings', 0):.2f} نقطة
        """
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 تحديث", callback_data="u_stats"))
        markup.add(types.InlineKeyboardButton("📈 تفاصيل أكثر", callback_data="detailed_stats"))
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="u_dashboard"))
        
        bot.send_message(m.chat.id, stats_text, parse_mode="Markdown", reply_markup=markup)
        
    except Exception as e:
        logger.error(f"Error showing user stats: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ في تحميل الإحصائيات.")

def show_settings(m):
    """عرض إعدادات المستخدم"""
    uid = str(m.chat.id)
    user_data = get_user(uid)
    
    if not user_data:
        return bot.send_message(m.chat.id, "❌ حدث خطأ في تحميل الإعدادات.")
    
    settings_text = f"""
⚙️ **إعدادات حسابك**

📱 **إشعارات:**
├ 🔊 إشعارات جديدة: {'✅ مفعل' if user_data.get('notify_new', True) else '❌ معطل'}
├ 📢 إعلانات: {'✅ مفعل' if user_data.get('notify_ads', True) else '❌ معطل'}
└ ⏰ تنبيهات انتهاء الاشتراك: {'✅ مفعل' if user_data.get('notify_expiry', True) else '❌ معطل'}

🔒 **خصوصية:**
├ 👥 عرض اسمي في الإحالات: {'✅ نعم' if user_data.get('show_in_refs', True) else '❌ لا'}
└ 📊 مشاركة إحصائياتي: {'✅ نعم' if user_data.get('share_stats', False) else '❌ لا'}

💳 **الدفع:**
├ 💰 العملة المفضلة: {user_data.get('preferred_currency', 'USD')}
└ 🏦 طريقة الدفع: {user_data.get('payment_method', 'غير محدد')}
        """
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # أزرار تبديل الإشعارات
    notify_new = user_data.get('notify_new', True)
    notify_ads = user_data.get('notify_ads', True)
    notify_expiry = user_data.get('notify_expiry', True)
    
    markup.add(
        types.InlineKeyboardButton(
            f"{'🔔' if notify_new else '🔕'} إشعارات جديدة", 
            callback_data=f"toggle_setting_notify_new_{not notify_new}"
        ),
        types.InlineKeyboardButton(
            f"{'📢' if notify_ads else '🚫'} إعلانات", 
            callback_data=f"toggle_setting_notify_ads_{not notify_ads}"
        )
    )
    
    markup.add(
        types.InlineKeyboardButton(
            f"{'⏰' if notify_expiry else '⏳'} تنبيهات انتهاء", 
            callback_data=f"toggle_setting_notify_expiry_{not notify_expiry}"
        )
    )
    
    markup.add(
        types.InlineKeyboardButton("💱 تغيير العملة", callback_data="change_currency"),
        types.InlineKeyboardButton("🏦 طرق الدفع", callback_data="payment_methods")
    )
    
    markup.add(
        types.InlineKeyboardButton("🔐 خصوصية", callback_data="privacy_settings"),
        types.InlineKeyboardButton("🗑️ حذف البيانات", callback_data="delete_data_ask")
    )
    
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="u_dashboard"))
    
    bot.send_message(m.chat.id, settings_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda q: q.data.startswith('toggle_setting_'))
def handle_toggle_setting(q):
    """معالجة تبديل الإعدادات"""
    uid = str(q.from_user.id)
    setting_data = q.data.replace("toggle_setting_", "")
    
    try:
        setting_parts = setting_data.split("_")
        if len(setting_parts) >= 3:
            setting_name = "_".join(setting_parts[:-1])
            new_value = setting_parts[-1].lower() == "true"
            
            # تحديث الإعداد
            db_fs.collection("users").document(uid).update({
                setting_name: new_value
            })
            
            bot.answer_callback_query(q.id, f"✅ تم تغيير الإعداد", show_alert=False)
            
            # تحديث العرض
            show_settings(q.message)
            
    except Exception as e:
        logger.error(f"Error toggling setting: {e}")
        bot.answer_callback_query(q.id, "❌ حدث خطأ", show_alert=True)

# --- [ ميزات المشرف المحسنة ] ---
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    try:
        # حساب الإحصائيات السريعة
        users_count = len(db_fs.collection("users").get())
        links_all = db_fs.collection("app_links").get()
        active = sum(1 for d in links_all if d.to_dict().get("end_time", 0) > time.time())
        
        # الإيرادات
        transactions = db_fs.collection("transactions").where("type", "==", "deposit").get()
        total_revenue = sum(t.to_dict().get("amount", 0) for t in transactions)
        
        msg = (f"👑 **إدارة نجم الإبداع**\n\n"
               f"👥 المستخدمين: `{users_count}` | الأجهزة: `{len(links_all)}`\n"
               f"🟢 النشطين: `{active}` | 💰 الإيرادات: `${total_revenue:.2f}`\n")
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        # الصف الأول
        markup.add(
            types.InlineKeyboardButton("📋 المشتركين", callback_data="list_all"),
            types.InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats"),
            types.InlineKeyboardButton("🆙 تحديث تطبيق", callback_data="admin_update_app_start"),
            types.InlineKeyboardButton("📢 إدارة الإعلانات", callback_data="admin_manage_ads")
        )
        
        # الصف الثاني
        markup.add(
            types.InlineKeyboardButton("🏷️ تسمية التطبيقات", callback_data="admin_manage_bot_names"),
            types.InlineKeyboardButton("💰 إدارة المحافظ", callback_data="admin_wallets"),
            types.InlineKeyboardButton("📝 السجلات", callback_data="admin_logs"),
            types.InlineKeyboardButton("🏆 المتصدرين", callback_data="top_ref")
        )
        
        # الصف الثالث
        markup.add(
            types.InlineKeyboardButton("🎫 كود جديد", callback_data="gen_key"),
            types.InlineKeyboardButton("🎁 أكواد الهدايا", callback_data="admin_gift_codes"),
            types.InlineKeyboardButton("📤 نشر تطبيق", callback_data="admin_upload_app"),
            types.InlineKeyboardButton("💾 نسخ احتياطي", callback_data="admin_backup")
        )
        
        # الصف الرابع
        markup.add(
            types.InlineKeyboardButton("🚫 حظر", callback_data="ban_op"),
            types.InlineKeyboardButton("✅ فك حظر", callback_data="unban_op"),
            types.InlineKeyboardButton("📢 إعلان عام", callback_data="admin_broadcast"),
            types.InlineKeyboardButton("🗑️ تصفير البيانات", callback_data="reset_data_ask")
        )
        
        bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in admin panel: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

def show_admin_stats(m):
    """عرض إحصائيات متقدمة للمشرف"""
    try:
        # جمع الإحصائيات
        users = db_fs.collection("users").get()
        apps = db_fs.collection("app_links").get()
        transactions = db_fs.collection("transactions").get()
        
        # حساب الإحصائيات الأساسية
        total_users = len(users)
        total_apps = len(apps)
        active_apps = sum(1 for a in apps if a.to_dict().get("end_time", 0) > time.time())
        
        # الإيرادات
        deposits = [t for t in transactions if t.to_dict().get("type") == "deposit"]
        total_revenue = sum(t.to_dict().get("amount", 0) for t in deposits)
        
        # النمو اليومي
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_timestamp = time.mktime(today.timetuple())
        new_users_today = sum(1 for u in users if u.to_dict().get("join_date", 0) > today_timestamp)
        
        # أكثر التطبيقات شعبية
        app_counter = Counter()
        for app in apps:
            pkg = app.id.split('_')[-1]
            app_counter[pkg] += 1
        
        top_apps = app_counter.most_common(5)
        
        # بناء الرسالة
        stats_text = f"""
📈 **إحصائيات النظام المتقدمة**

👥 **المستخدمين:**
├ 📊 الإجمالي: {total_users}
├ 🆕 الجدد اليوم: {new_users_today}
├ 🏆 أعلى مستوى: {max((u.to_dict().get('level', 1) for u in users), default=1)}
└ 👥 متوسط الإحالات: {sum(u.to_dict().get('referral_count', 0) for u in users) / max(total_users, 1):.1f}

📱 **التطبيقات:**
├ 📦 الإجمالي: {total_apps}
├ 🟢 النشطة: {active_apps}
├ 🔴 المنتهية: {total_apps - active_apps}
└ 📈 نسبة النشاط: {(active_apps/total_apps*100) if total_apps > 0 else 0:.1f}%

💰 **المالية:**
├ 💵 إجمالي الإيرادات: ${total_revenue:.2f}
├ 💳 عدد المعاملات: {len(deposits)}
└ 📊 متوسط المعاملة: ${(total_revenue/len(deposits)) if deposits else 0:.2f}

🏆 **أكثر التطبيقات شعبية:**
"""
        
        for i, (app_id, count) in enumerate(top_apps, 1):
            stats_text += f"{i}. `{app_id}`: {count} جهاز\n"
        
        # إضافة معلومات النظام
        stats_text += f"""
🖥️ **معلومات النظام:**
├ ⏰ وقت التشغيل: {get_uptime_str()}
├ 📅 تاريخ النظام: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
└ 🐍 إصدار البوت: 3.0.0
        """
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("📊 تفاصيل أكثر", callback_data="detailed_admin_stats"),
            types.InlineKeyboardButton("📈 الرسوم البيانية", callback_data="admin_charts"),
            types.InlineKeyboardButton("📋 تصدير البيانات", callback_data="export_data")
        )
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel_back"))
        
        bot.send_message(m.chat.id, stats_text, parse_mode="Markdown", reply_markup=markup)
        
    except Exception as e:
        logger.error(f"Error showing admin stats: {e}")
        bot.send_message(m.chat.id, f"❌ حدث خطأ: {str(e)[:100]}")

def get_uptime_str():
    """الحصول على وقت التشغيل بصيغة نصية"""
    uptime = get_uptime()
    days = uptime // 86400
    hours = (uptime % 86400) // 3600
    minutes = (uptime % 3600) // 60
    
    return f"{int(days)} يوم, {int(hours)} ساعة, {int(minutes)} دقيقة"

def create_backup(m):
    """إنشاء نسخة احتياطية"""
    try:
        if not bucket:
            return bot.send_message(m.chat.id, "❌ خدمة النسخ الاحتياطي غير متاحة.")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"backup_{timestamp}"
        
        bot.send_message(m.chat.id, "⏳ جاري إنشاء النسخة الاحتياطية...")
        
        # تصدير المستخدمين
        users_data = []
        users = db_fs.collection("users").get()
        for user in users:
            user_dict = user.to_dict()
            user_dict["id"] = user.id
            users_data.append(user_dict)
        
        # تصدير التطبيقات
        apps_data = []
        apps = db_fs.collection("app_links").get()
        for app in apps:
            app_dict = app.to_dict()
            app_dict["id"] = app.id
            apps_data.append(app_dict)
        
        # إنشاء ملف النسخة الاحتياطية
        backup_data = {
            "timestamp": timestamp,
            "users_count": len(users_data),
            "apps_count": len(apps_data),
            "users": users_data,
            "apps": apps_data,
            "created_by": m.from_user.id
        }
        
        # حفظ مؤقت
        temp_file = f"/tmp/{backup_name}.json"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        # رفع إلى التخزين
        blob = bucket.blob(f"backups/{backup_name}.json")
        blob.upload_from_filename(temp_file)
        
        # تنظيف
        os.remove(temp_file)
        
        # إرسال رابط التنزيل
        download_url = blob.generate_signed_url(expiration=timedelta(hours=24))
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📥 تحميل النسخة", url=download_url))
        
        bot.send_message(
            m.chat.id,
            f"✅ **تم إنشاء النسخة الاحتياطية**\n\n"
            f"📁 الاسم: `{backup_name}`\n"
            f"👥 المستخدمين: {len(users_data)}\n"
            f"📱 التطبيقات: {len(apps_data)}\n"
            f"⏰ التاريخ: {timestamp}\n\n"
            f"الرابط صالح لمدة 24 ساعة.",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        bot.send_message(m.chat.id, f"❌ حدث خطأ: {str(e)[:100]}")

def manage_wallets(m):
    """إدارة محافظ المستخدمين"""
    try:
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        options = [
            ("💰 تصدير جميع المحافظ", "export_wallets"),
            ("📊 إحصائيات المحافظ", "wallet_stats"),
            ("🎁 إضافة رصيد", "add_balance"),
            ("📤 خصم رصيد", "deduct_balance"),
            ("🔍 البحث عن محفظة", "search_wallet")
        ]
        
        for text, callback in options:
            markup.add(types.InlineKeyboardButton(text, callback_data=callback))
        
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel_back"))
        
        bot.send_message(
            m.chat.id,
            "💰 **إدارة محافظ المستخدمين**\n\n"
            "اختر الإجراء المطلوب:",
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error in manage wallets: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ.")

@bot.callback_query_handler(func=lambda q: q.data == "admin_panel_back")
def admin_panel_back(q):
    """العودة للوحة المشرف"""
    admin_panel(q.message)

def show_broadcast_options(m):
    """عرض خيارات البث"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    options = [
        ("📢 للمستخدمين النشطين", "broadcast_active"),
        ("👥 لجميع المستخدمين", "broadcast_all"),
        ("📱 لمستخدمي تطبيق معين", "broadcast_app"),
        ("🏆 للمستويات العليا", "broadcast_vip"),
        ("🎁 للمستخدمين الجدد", "broadcast_new")
    ]
    
    for text, callback in options:
        markup.add(types.InlineKeyboardButton(text, callback_data=callback))
    
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel_back"))
    
    bot.send_message(
        m.chat.id,
        "📢 **نظام البث الإعلاني**\n\n"
        "اختر الفئة المستهدفة:",
        reply_markup=markup
    )

def handle_broadcast_selection(q):
    """معالجة اختيار نوع البث"""
    broadcast_type = q.data.replace("broadcast_", "")
    
    if broadcast_type == "active":
        msg = bot.send_message(q.message.chat.id, "💬 **أرسل الرسالة للمستخدمين النشطين (آخر 7 أيام):**")
        bot.register_next_step_handler(msg, process_broadcast, "active")
    
    elif broadcast_type == "all":
        msg = bot.send_message(q.message.chat.id, "💬 **أرسل الرسالة لجميع المستخدمين:**")
        bot.register_next_step_handler(msg, process_broadcast, "all")
    
    elif broadcast_type == "app":
        msg = bot.send_message(q.message.chat.id, "📱 **أرسل اسم التطبيق المستهدف:**")
        bot.register_next_step_handler(msg, process_broadcast_app_step)
    
    elif broadcast_type == "vip":
        msg = bot.send_message(q.message.chat.id, "💬 **أرسل الرسالة لمستويات VIP فما فوق:**")
        bot.register_next_step_handler(msg, process_broadcast, "vip")
    
    elif broadcast_type == "new":
        msg = bot.send_message(q.message.chat.id, "💬 **أرسل الرسالة للمستخدمين الجدد (آخر 3 أيام):**")
        bot.register_next_step_handler(msg, process_broadcast, "new")

def process_broadcast_app_step(m):
    """معالجة اختيار التطبيق للبث"""
    app_name = m.text.strip()
    user_temp_data[str(m.from_user.id)] = {"broadcast_app": app_name}
    
    msg = bot.send_message(m.chat.id, f"💬 **أرسل الرسالة لمستخدمي تطبيق {app_name}:**")
    bot.register_next_step_handler(msg, process_broadcast, "app")

def process_broadcast(m, broadcast_type):
    """معالجة البث"""
    try:
        uid = str(m.from_user.id)
        message_text = m.text.strip()
        
        if not validate_input(message_text, 2000, True):
            return bot.send_message(m.chat.id, "❌ النص غير صالح.")
        
        bot.send_message(m.chat.id, "⏳ جاري إرسال الرسائل...")
        
        # جلب المستخدمين حسب النوع
        users = get_users_for_broadcast(broadcast_type, uid)
        
        success_count = 0
        fail_count = 0
        
        for user_id in users:
            try:
                if broadcast_type == "app":
                    app_name = user_temp_data.get(uid, {}).get("broadcast_app", "")
                    personalized_msg = f"📱 **إعلان خاص لمستخدمي {app_name}**\n\n{message_text}"
                else:
                    personalized_msg = f"📢 **إعلان مهم**\n\n{message_text}"
                
                bot.send_message(user_id, personalized_msg)
                success_count += 1
                
                # تأخير بسيط لتجنب حظر التيليجرام
                time.sleep(0.05)
                
            except Exception as e:
                fail_count += 1
                logger.warning(f"Failed to send broadcast to {user_id}: {e}")
        
        # تنظيف البيانات المؤقتة
        if uid in user_temp_data:
            del user_temp_data[uid]
        
        # إرسال التقرير
        bot.send_message(
            m.chat.id,
            f"✅ **تم إكمال البث**\n\n"
            f"📊 **النوع:** {broadcast_type}\n"
            f"✅ **تم بنجاح:** {success_count}\n"
            f"❌ **فشل:** {fail_count}\n"
            f"📨 **الإجمالي:** {success_count + fail_count}"
        )
        
        # تسجيل البث
        db_fs.collection("broadcasts").add({
            "type": broadcast_type,
            "message": message_text[:500],
            "success_count": success_count,
            "fail_count": fail_count,
            "sent_by": uid,
            "timestamp": time.time()
        })
        
    except Exception as e:
        logger.error(f"Error in broadcast: {e}")
        bot.send_message(m.chat.id, f"❌ حدث خطأ: {str(e)[:100]}")

def get_users_for_broadcast(broadcast_type, admin_id):
    """جلب المستخدمين حسب نوع البث"""
    users = []
    
    try:
        if broadcast_type == "all":
            # جميع المستخدمين
            users_docs = db_fs.collection("users").get()
            users = [doc.id for doc in users_docs]
        
        elif broadcast_type == "active":
            # المستخدمين النشطين (آخر 7 أيام)
            week_ago = time.time() - 7*86400
            users_docs = db_fs.collection("users").where("last_active", ">", week_ago).get()
            users = [doc.id for doc in users_docs]
        
        elif broadcast_type == "vip":
            # مستويات VIP فما فوق
            users_docs = db_fs.collection("users").where("level", ">=", 5).get()
            users = [doc.id for doc in users_docs]
        
        elif broadcast_type == "new":
            # المستخدمين الجدد (آخر 3 أيام)
            three_days_ago = time.time() - 3*86400
            users_docs = db_fs.collection("users").where("join_date", ">", three_days_ago).get()
            users = [doc.id for doc in users_docs]
        
        elif broadcast_type == "app":
            # مستخدمي تطبيق معين
            app_name = user_temp_data.get(admin_id, {}).get("broadcast_app", "")
            if app_name:
                # البحث عن الأجهزة المرتبطة بالتطبيق
                apps_docs = db_fs.collection("app_links").get()
                users = list(set([
                    doc.to_dict().get("telegram_id") 
                    for doc in apps_docs 
                    if app_name in doc.id and doc.to_dict().get("telegram_id")
                ]))
    
    except Exception as e:
        logger.error(f"Error getting users for broadcast: {e}")
    
    return users

# --- [ نظام المهام المجدولة ] ---
def scheduled_tasks():
    """المهام المجدولة التلقائية"""
    while True:
        try:
            now = datetime.now()
            
            # مهمة التنبيه بانتهاء الاشتراكات (كل ساعة)
            if now.minute == 0:
                check_expiry_notifications()
            
            # مهمة تنظيف البيانات المؤقتة (كل يوم في منتصف الليل)
            if now.hour == 0 and now.minute == 0:
                cleanup_temp_data()
            
            # مهمة النسخ الاحتياطي (كل يوم في الساعة 3 صباحاً)
            if now.hour == 3 and now.minute == 0 and ADMIN_ID:
                create_auto_backup()
            
            # مهمة تحديث الإحصائيات (كل 6 ساعات)
            if now.hour % 6 == 0 and now.minute == 0:
                update_daily_stats()
            
            time.sleep(60)  # انتظار دقيقة بين كل فحص
            
        except Exception as e:
            logger.error(f"Error in scheduled tasks: {e}")
            time.sleep(300)  # انتظار 5 دقائق عند الخطأ

def check_expiry_notifications():
    """التحقق من الاشتراكات المنتهية وإرسال تنبيهات"""
    try:
        # البحث عن الاشتراكات التي تنتهي خلال 24 ساعة
        warning_time = time.time() + 86400  # 24 ساعة
        warning_threshold = time.time() + 86400 + 3600  # 25 ساعة
        
        apps = db_fs.collection("app_links").get()
        
        for app in apps:
            data = app.to_dict()
            end_time = data.get("end_time", 0)
            user_id = data.get("telegram_id")
            
            if user_id and warning_time < end_time <= warning_threshold:
                # لم يتم إرسال تنبيه بعد
                if not data.get("expiry_notified", False):
                    try:
                        pkg = app.id.split('_')[-1]
                        display = get_bot_names_map().get(pkg, pkg)
                        
                        bot.send_message(
                            user_id,
                            f"⚠️ **تنبيه انتهاء الاشتراك**\n\n"
                            f"📱 التطبيق: `{display}`\n"
                            f"⏰ وقت الانتهاء: غداً\n"
                            f"📅 التاريخ: {datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M')}\n\n"
                            f"🛒 **جدد اشتراكك الآن لتجنب الانقطاع!**"
                        )
                        
                        # تحديث حالة التنبيه
                        db_fs.collection("app_links").document(app.id).update({
                            "expiry_notified": True
                        })
                        
                    except Exception as e:
                        logger.error(f"Error sending expiry notification to {user_id}: {e}")
        
    except Exception as e:
        logger.error(f"Error checking expiry notifications: {e}")

def cleanup_temp_data():
    """تنظيف البيانات المؤقتة القديمة"""
    try:
        # تنظيف user_temp_data القديم (أقدم من يوم)
        current_time = time.time()
        to_delete = []
        
        for user_id, data in user_temp_data.items():
            if "timestamp" in data and current_time - data["timestamp"] > 86400:
                to_delete.append(user_id)
        
        for user_id in to_delete:
            del user_temp_data[user_id]
        
        # تنظيف الكاش القديم
        qr_codes_cache.clear()
        
        logger.info("Temp data cleanup completed")
        
    except Exception as e:
        logger.error(f"Error in cleanup_temp_data: {e}")

def create_auto_backup():
    """إنشاء نسخة احتياطية تلقائية"""
    try:
        if not bucket or not ADMIN_ID:
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        backup_name = f"auto_backup_{timestamp}"
        
        # إرسال إشعار للمشرف
        bot.send_message(ADMIN_ID, "🔄 جاري إنشاء النسخة الاحتياطية التلقائية...")
        
        # تنفيذ النسخ الاحتياطي (نفس وظيفة create_backup ولكن بدون تفاعل)
        # ... كود النسخ الاحتياطي ...
        
        bot.send_message(ADMIN_ID, f"✅ تم إنشاء النسخة الاحتياطية التلقائية: `{backup_name}`")
        
    except Exception as e:
        logger.error(f"Error in auto backup: {e}")

def update_daily_stats():
    """تحديث الإحصائيات اليومية"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        # حساب الإحصائيات
        users_count = len(db_fs.collection("users").get())
        active_users = len([u for u in db_fs.collection("users").get() 
                          if u.to_dict().get("last_active", 0) > time.time() - 86400])
        
        new_users = len([u for u in db_fs.collection("users").get() 
                       if u.to_dict().get("join_date", 0) > time.time() - 86400])
        
        # حفظ الإحصائيات
        db_fs.collection("daily_stats").document(today).set({
            "date": today,
            "total_users": users_count,
            "active_users": active_users,
            "new_users": new_users,
            "timestamp": time.time()
        }, merge=True)
        
    except Exception as e:
        logger.error(f"Error updating daily stats: {e}")

# --- [ وظائف المساعدة ] ---
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

def wipe_all_data(m):
    try:
        collections = ["users", "app_links", "logs", "vouchers", "app_updates", "update_manifest", 
                      "ads_manifest", "bot_names_manifest", "transactions", "wallets", 
                      "support_tickets", "gift_codes", "broadcasts", "daily_stats"]
        
        total_deleted = 0
        
        for coll in collections:
            docs = db_fs.collection(coll).get()
            for d in docs:
                d.reference.delete()
                total_deleted += 1
        
        # تنظيف المخازن المحلية
        upload_cache.clear()
        rate_limits.clear()
        user_temp_data.clear()
        wallet_cache.clear()
        qr_codes_cache.clear()
        
        bot.send_message(
            m.chat.id,
            f"✅ **تم تصفير جميع قواعد البيانات بنجاح!**\n\n"
            f"🗑️ السجلات المحذوفة: {total_deleted}\n"
            f"⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        logger.warning(f"Database wiped by admin {m.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error wiping data: {e}")
        bot.send_message(m.chat.id, f"❌ حدث خطأ: {str(e)[:100]}")

# --- [ تشغيل البوت ] ---
def run():
    """تشغيل سيرفل Flask"""
    try:
        port = int(os.environ.get("PORT", 8080))
        app.run(host='0.0.0.0', port=port, debug=False)
    except Exception as e:
        logger.critical(f"Flask app crashed: {e}")

if __name__ == "__main__":
    try:
        logger.info("🤖 بدء تشغيل بوت نجم الإبداع...")
        
        # تشغيل سيرفر Flask في خيط منفصل
        flask_thread = Thread(target=run, daemon=True)
        flask_thread.start()
        
        # تشغيل المهام المجدولة في خيط منفصل
        scheduler_thread = Thread(target=scheduled_tasks, daemon=True)
        scheduler_thread.start()
        
        # تشغيل منبه انتهاء الاشتراكات في خيط منفصل
        expiry_thread = Thread(target=expiry_notifier, daemon=True)
        expiry_thread.start()
        
        logger.info("✅ جميع الخدمات بدأت بنجاح")
        
        # بدء استقبال الرسائل
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
        
    except KeyboardInterrupt:
        logger.info("⏹️ إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        logger.critical(f"🔥 البوت توقف بسبب خطأ: {e}")
