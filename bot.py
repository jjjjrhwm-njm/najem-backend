import telebot
from telebot import types
from flask import Flask, request, jsonify, render_template
import json, os, time, uuid, csv, io, base64, qrcode
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
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dateutil.relativedelta import relativedelta
import schedule

# --- [ إعداد Logging المتقدم ] ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Handler للملفات
file_handler = RotatingFileHandler('bot.log', maxBytes=10*1024*1024, backupCount=10)
file_handler.setLevel(logging.INFO)

# Handler للكونسول
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)

# Formatter
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
CHANNEL_ID = os.environ.get('CHANNEL_ID')
API_SECRET = os.environ.get('API_SECRET', 'default-secret-change-me')
BACKUP_BUCKET = os.environ.get('BACKUP_BUCKET', '')
SUPPORT_CHAT_ID = os.environ.get('SUPPORT_CHAT_ID', '')

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

# --- [ هياكل بيانات جديدة ] ---
upload_cache = {}
cache_lock = Lock()
rate_limits = defaultdict(list)
violations = defaultdict(list)
user_sessions = {}
wallet_transactions = []

# إعدادات Rate Limit
RATE_LIMIT = 30
VIOLATION_LIMIT = 5
WALLET_INITIAL_BALANCE = 0

# مستويات المستخدمين
USER_LEVELS = {
    1: {"name": "مبتدئ", "min_refs": 0, "discount": 0},
    2: {"name": "عادي", "min_refs": 5, "discount": 5},
    3: {"name": "نشيط", "min_refs": 15, "discount": 10},
    4: {"name": "مميز", "min_refs": 30, "discount": 15},
    5: {"name": "VIP", "min_refs": 50, "discount": 20}
}

# --- [ واجهة ويب للمراقبة ] ---
@app.route('/admin_dashboard')
@verify_api_key
def admin_dashboard():
    """لوحة تحكم ويب للمشرف"""
    try:
        stats = get_system_statistics()
        recent_activities = get_recent_activities(20)
        top_apps = get_top_apps(10)
        
        return render_template('dashboard.html',
                             stats=stats,
                             activities=recent_activities,
                             top_apps=top_apps,
                             admin_id=ADMIN_ID)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats')
@verify_api_key
def api_stats():
    """API للإحصائيات"""
    stats = get_system_statistics()
    return jsonify(stats)

@app.route('/api/export/<data_type>')
@verify_api_key
def export_data(data_type):
    """تصدير البيانات"""
    try:
        if data_type == 'users':
            data = export_users_csv()
        elif data_type == 'transactions':
            data = export_transactions_csv()
        elif data_type == 'apps':
            data = export_apps_csv()
        else:
            return "Invalid type", 400
            
        return data
    except Exception as e:
        logger.error(f"Export error: {e}")
        return "Error", 500

# --- [ وظائف الحماية المحسنة ] ---
def verify_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-API-Key')
        if not token or not hmac.compare_digest(token, API_SECRET):
            ip = request.remote_addr
            logger.warning(f"Unauthorized API access from {ip}")
            log_violation(ip, "unauthorized_api_access")
            return "Unauthorized", 401
        return f(*args, **kwargs)
    return decorated

def check_rate_limit(user_id):
    """Rate limit مع تسجيل الانتهاكات"""
    now = datetime.now()
    with cache_lock:
        # تنظيف السجلات القديمة
        rate_limits[user_id] = [
            t for t in rate_limits[user_id] 
            if now - t < timedelta(minutes=1)
        ]
        
        if len(rate_limits[user_id]) >= RATE_LIMIT:
            log_violation(user_id, "rate_limit_exceeded")
            
            # إذا تجاوز الحد بشكل كبير، حظر مؤقت
            if len(rate_limits[user_id]) >= RATE_LIMIT * 2:
                temp_ban_user(user_id, 300)  # حظر 5 دقائق
                
            return False
        
        rate_limits[user_id].append(now)
        return True

def log_violation(user_id, violation_type):
    """تسجيل الانتهاكات"""
    try:
        violations[user_id].append({
            "type": violation_type,
            "timestamp": time.time(),
            "ip": request.remote_addr if 'request' in globals() else None
        })
        
        # إذا تجاوز عدد الانتهاكات الحد
        if len(violations[user_id]) >= VIOLATION_LIMIT:
            notify_admin_violation(user_id, violation_type)
            
        db_fs.collection("violations").add({
            "user_id": str(user_id),
            "type": violation_type,
            "timestamp": time.time(),
            "ip": request.remote_addr if 'request' in globals() else None
        })
    except Exception as e:
        logger.error(f"Error logging violation: {e}")

def temp_ban_user(user_id, seconds):
    """حظر مؤقت"""
    try:
        ban_until = time.time() + seconds
        db_fs.collection("temp_bans").document(str(user_id)).set({
            "ban_until": ban_until,
            "reason": "rate_limit_exceeded"
        })
        logger.warning(f"User {user_id} temp banned for {seconds} seconds")
    except Exception as e:
        logger.error(f"Error temp banning user: {e}")

# --- [ نظام المحفظة ] ---
def get_wallet_balance(user_id):
    """الحصول على رصيد المحفظة"""
    try:
        doc = db_fs.collection("wallets").document(str(user_id)).get()
        if doc.exists:
            return doc.to_dict().get("balance", 0)
        else:
            # إنشاء محفظة جديدة
            db_fs.collection("wallets").document(str(user_id)).set({
                "balance": WALLET_INITIAL_BALANCE,
                "created_at": time.time(),
                "last_updated": time.time()
            })
            return WALLET_INITIAL_BALANCE
    except Exception as e:
        logger.error(f"Error getting wallet balance: {e}")
        return 0

def update_wallet(user_id, amount, transaction_type, description=""):
    """تحديد رصيد المحفظة"""
    try:
        current_balance = get_wallet_balance(user_id)
        new_balance = current_balance + amount
        
        # تحديث الرصيد
        db_fs.collection("wallets").document(str(user_id)).update({
            "balance": new_balance,
            "last_updated": time.time()
        })
        
        # تسجيل المعاملة
        transaction_id = str(uuid.uuid4())
        db_fs.collection("transactions").document(transaction_id).set({
            "user_id": str(user_id),
            "amount": amount,
            "type": transaction_type,
            "description": description,
            "old_balance": current_balance,
            "new_balance": new_balance,
            "timestamp": time.time()
        })
        
        wallet_transactions.append({
            "user_id": user_id,
            "amount": amount,
            "type": transaction_type,
            "timestamp": time.time()
        })
        
        logger.info(f"Wallet updated for {user_id}: {amount} ({transaction_type})")
        return new_balance
    except Exception as e:
        logger.error(f"Error updating wallet: {e}")
        return current_balance

def apply_user_discount(user_id, original_price):
    """تطبيق خصم حسب مستوى المستخدم"""
    try:
        user_data = get_user(user_id)
        if not user_data:
            return original_price
        
        ref_count = user_data.get("referral_count", 0)
        user_level = 1
        
        # تحديد مستوى المستخدم
        for level, info in sorted(USER_LEVELS.items(), reverse=True):
            if ref_count >= info["min_refs"]:
                user_level = level
                break
        
        discount_percent = USER_LEVELS[user_level]["discount"]
        discount_amount = original_price * discount_percent / 100
        final_price = original_price - discount_amount
        
        return final_price, discount_percent, user_level
    except Exception as e:
        logger.error(f"Error applying discount: {e}")
        return original_price, 0, 1

# --- [ نظام التذاكر ] ---
class SupportTicket:
    """نظام تذاكر الدعم"""
    
    def __init__(self):
        self.tickets = {}
        
    def create_ticket(self, user_id, subject, message):
        """إنشاء تذكرة جديدة"""
        try:
            ticket_id = f"TICKET_{int(time.time())}_{user_id}"
            
            ticket_data = {
                "id": ticket_id,
                "user_id": user_id,
                "subject": subject,
                "message": message,
                "status": "open",  # open, in_progress, closed
                "priority": "medium",  # low, medium, high, urgent
                "created_at": time.time(),
                "updated_at": time.time(),
                "messages": []
            }
            
            # حفظ في قاعدة البيانات
            db_fs.collection("support_tickets").document(ticket_id).set(ticket_data)
            
            # إرسال إشعار للمشرف
            self.notify_admin_new_ticket(ticket_id, user_id, subject)
            
            logger.info(f"New ticket created: {ticket_id} by {user_id}")
            return ticket_id
            
        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            return None
    
    def add_message(self, ticket_id, sender_id, message, is_admin=False):
        """إضافة رد إلى التذكرة"""
        try:
            msg_data = {
                "sender_id": sender_id,
                "message": message,
                "is_admin": is_admin,
                "timestamp": time.time()
            }
            
            # إضافة إلى قاعدة البيانات
            db_fs.collection("support_tickets").document(ticket_id).update({
                "messages": firestore.ArrayUnion([msg_data]),
                "updated_at": time.time(),
                "status": "in_progress" if is_admin else "open"
            })
            
            # إرسال إشعار للطرف الآخر
            self.notify_ticket_update(ticket_id, sender_id, message, is_admin)
            
            return True
        except Exception as e:
            logger.error(f"Error adding message to ticket: {e}")
            return False
    
    def notify_admin_new_ticket(self, ticket_id, user_id, subject):
        """إشعار المشرف بتذكرة جديدة"""
        try:
            user_data = get_user(user_id)
            user_name = user_data.get("name", "مستخدم") if user_data else "مستخدم"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "📩 الرد على التذكرة", 
                callback_data=f"reply_ticket_{ticket_id}"
            ))
            
            bot.send_message(
                ADMIN_ID,
                f"📢 **تذكرة دعم جديدة**\n\n"
                f"👤 المستخدم: {user_name} ({user_id})\n"
                f"📌 الموضوع: {subject}\n"
                f"🆔 رقم التذكرة: `{ticket_id}`",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error notifying admin: {e}")
    
    def notify_ticket_update(self, ticket_id, sender_id, message, is_admin):
        """إشعار تحديث التذكرة"""
        try:
            ticket_ref = db_fs.collection("support_tickets").document(ticket_id)
            ticket_data = ticket_ref.get().to_dict()
            
            if not ticket_data:
                return
            
            target_id = ADMIN_ID if not is_admin else ticket_data["user_id"]
            sender_text = "المشرف" if is_admin else "أنت"
            
            bot.send_message(
                target_id,
                f"📩 **رد جديد على التذكرة #{ticket_id}**\n\n"
                f"👤 المرسل: {sender_text}\n"
                f"💬 الرسالة: {message[:200]}...\n\n"
                f"للرد استخدم: /reply_{ticket_id}"
            )
        except Exception as e:
            logger.error(f"Error notifying ticket update: {e}")

support_system = SupportTicket()

# --- [ إحصائيات وتحليلات ] ---
def get_system_statistics():
    """جمع إحصائيات النظام"""
    try:
        stats = {}
        
        # إحصائيات المستخدمين
        users = db_fs.collection("users").get()
        stats["total_users"] = len(users)
        
        # إحصائيات التطبيقات
        apps = db_fs.collection("app_links").get()
        stats["total_apps"] = len(apps)
        
        # التطبيقات النشطة
        active_apps = [a for a in apps if a.to_dict().get("end_time", 0) > time.time()]
        stats["active_apps"] = len(active_apps)
        
        # الإيرادات
        transactions = db_fs.collection("transactions").where("type", "==", "payment").get()
        stats["total_revenue"] = sum(t.to_dict().get("amount", 0) for t in transactions)
        
        # نمو المستخدمين (آخر 7 أيام)
        week_ago = time.time() - 7*86400
        new_users = [u for u in users if u.to_dict().get("join_date", 0) > week_ago]
        stats["new_users_7d"] = len(new_users)
        
        # أكثر التطبيقات شعبية
        app_counter = Counter()
        for app in apps:
            pkg = app.id.split('_')[-1]
            app_counter[pkg] += 1
        
        stats["top_apps"] = app_counter.most_common(5)
        
        # الانتهاكات
        violations = db_fs.collection("violations").get()
        stats["total_violations"] = len(violations)
        
        # محافظ المستخدمين
        wallets = db_fs.collection("wallets").get()
        stats["total_wallet_balance"] = sum(w.to_dict().get("balance", 0) for w in wallets)
        
        return stats
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        return {}

def generate_usage_graph():
    """إنشاء رسم بياني للاستخدام"""
    try:
        # جمع بيانات الشهر الماضي
        month_ago = datetime.now() - timedelta(days=30)
        dates = [(month_ago + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30)]
        
        # استعلام للبيانات (هنا مثال مبسط)
        # في التطبيق الفعلي تحتاج استعلامات أكثر تعقيدًا
        
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        
        # رسم بيانات مثال
        axes[0, 0].plot(range(30), range(30, 0, -1))
        axes[0, 0].set_title('المستخدمين الجدد')
        
        axes[0, 1].plot(range(30), [i*2 for i in range(30)])
        axes[0, 1].set_title('التطبيقات المنشطة')
        
        axes[1, 0].bar(range(5), [10, 15, 7, 20, 12])
        axes[1, 0].set_title('أفضل 5 تطبيقات')
        
        axes[1, 1].pie([40, 30, 20, 10], labels=['ممتاز', 'جيد', 'متوسط', 'ضعيف'])
        axes[1, 1].set_title('تقييمات المستخدمين')
        
        plt.tight_layout()
        
        # حفظ الصورة
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=100)
        buffer.seek(0)
        
        # تحويل إلى base64
        img_str = base64.b64encode(buffer.read()).decode()
        plt.close()
        
        return img_str
    except Exception as e:
        logger.error(f"Error generating graph: {e}")
        return None

# --- [ النسخ الاحتياطي ] ---
def backup_database():
    """نسخ احتياطي تلقائي للقاعدة"""
    try:
        if not bucket:
            logger.warning("No backup bucket configured")
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"backup_{timestamp}"
        
        # تصدير المستخدمين
        users = db_fs.collection("users").get()
        user_data = []
        for user in users:
            user_dict = user.to_dict()
            user_dict["id"] = user.id
            user_data.append(user_dict)
        
        # حفظ في ملف JSON مؤقت
        temp_file = f"/tmp/{backup_name}_users.json"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
        
        # رفع إلى Firebase Storage
        blob = bucket.blob(f"backups/{backup_name}_users.json")
        blob.upload_from_filename(temp_file)
        
        # حذف الملف المؤقت
        os.remove(temp_file)
        
        logger.info(f"Backup completed: {backup_name}")
        
        # الاحتفاظ بآخر 10 نسخ فقط
        self.cleanup_old_backups(10)
        
    except Exception as e:
        logger.error(f"Backup error: {e}")

def cleanup_old_backups(max_backups):
    """حذف النسخ القديمة"""
    try:
        blobs = list(bucket.list_blobs(prefix="backups/"))
        
        if len(blobs) > max_backups:
            # فرز حسب وقت الإنشاء
            blobs.sort(key=lambda x: x.time_created)
            
            # حذف الأقدم
            for blob in blobs[:-max_backups]:
                blob.delete()
                logger.info(f"Deleted old backup: {blob.name}")
                
    except Exception as e:
        logger.error(f"Error cleaning up backups: {e}")

# --- [ وظائف التصدير ] ---
def export_users_csv():
    """تصدير المستخدمين كملف CSV"""
    try:
        users = db_fs.collection("users").get()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # كتابة العنوان
        writer.writerow(['ID', 'Name', 'Referrals', 'Join Date', 'Wallet Balance', 'Level'])
        
        # كتابة البيانات
        for user in users:
            data = user.to_dict()
            wallet_balance = get_wallet_balance(user.id)
            user_level = calculate_user_level(data.get("referral_count", 0))
            
            writer.writerow([
                user.id,
                data.get('name', ''),
                data.get('referral_count', 0),
                datetime.fromtimestamp(data.get('join_date', time.time())).strftime('%Y-%m-%d %H:%M'),
                wallet_balance,
                user_level
            ])
        
        output.seek(0)
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"Error exporting users: {e}")
        return ""

def export_transactions_csv():
    """تصدير المعاملات"""
    try:
        transactions = db_fs.collection("transactions").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(1000).get()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Transaction ID', 'User ID', 'Amount', 'Type', 'Description', 'Date'])
        
        for t in transactions:
            data = t.to_dict()
            writer.writerow([
                t.id,
                data.get('user_id', ''),
                data.get('amount', 0),
                data.get('type', ''),
                data.get('description', '')[:50],
                datetime.fromtimestamp(data.get('timestamp', time.time())).strftime('%Y-%m-%d %H:%M')
            ])
        
        output.seek(0)
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"Error exporting transactions: {e}")
        return ""

# --- [ ميزات جديدة في القائمة الرئيسية ] ---
@bot.message_handler(commands=['support'])
def support_command(m):
    """إنشاء تذكرة دعم"""
    try:
        uid = str(m.from_user.id)
        
        if not check_rate_limit(uid):
            return
        
        msg = bot.send_message(m.chat.id, "📝 **نظام الدعم الفني**\n\nأدخل عنواناً للتذكرة:")
        bot.register_next_step_handler(msg, process_support_subject)
        
    except Exception as e:
        logger.error(f"Support command error: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ، حاول لاحقاً.")

def process_support_subject(m):
    """معالجة عنوان التذكرة"""
    try:
        subject = m.text.strip()
        if not validate_input(subject, 100):
            return bot.send_message(m.chat.id, "❌ العنوان غير صالح.")
        
        user_sessions[str(m.from_user.id)] = {"support_subject": subject}
        
        msg = bot.send_message(m.chat.id, "💬 **اكتب رسالتك الآن:**")
        bot.register_next_step_handler(msg, process_support_message)
        
    except Exception as e:
        logger.error(f"Support subject error: {e}")

def process_support_message(m):
    """معالجة رسالة الدعم"""
    try:
        uid = str(m.from_user.id)
        message = m.text.strip()
        
        if not validate_input(message, 1000, True):
            return bot.send_message(m.chat.id, "❌ الرسالة غير صالحة.")
        
        session_data = user_sessions.get(uid, {})
        subject = session_data.get("support_subject", "طلب دعم")
        
        # إنشاء التذكرة
        ticket_id = support_system.create_ticket(uid, subject, message)
        
        if ticket_id:
            bot.send_message(
                m.chat.id,
                f"✅ **تم إنشاء تذكرة الدعم**\n\n"
                f"🆔 رقم التذكرة: `{ticket_id}`\n"
                f"📌 العنوان: {subject}\n"
                f"⏰ تم إرسالها في: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"سيتم الرد عليك في أقرب وقت."
            )
        else:
            bot.send_message(m.chat.id, "❌ فشل إنشاء التذكرة، حاول لاحقاً.")
        
        # تنظيف الجلسة
        if uid in user_sessions:
            del user_sessions[uid]
            
    except Exception as e:
        logger.error(f"Support message error: {e}")

@bot.message_handler(commands=['wallet'])
def wallet_command(m):
    """عرض رصيد المحفظة"""
    try:
        uid = str(m.from_user.id)
        
        if not check_rate_limit(uid):
            return
        
        balance = get_wallet_balance(uid)
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("💳 شحن المحفظة", callback_data="wallet_deposit"),
            types.InlineKeyboardButton("📜 سجل المعاملات", callback_data="wallet_transactions"),
            types.InlineKeyboardButton("🎁 تحويل رصيد", callback_data="wallet_transfer"),
            types.InlineKeyboardButton("🎫 شراء بكود", callback_data="wallet_buy_code")
        )
        
        bot.send_message(
            m.chat.id,
            f"💰 **محفظتك الشخصية**\n\n"
            f"📊 الرصيد الحالي: **{balance:.2f}** نقطة\n"
            f"👤 مستواك: **{get_user_level(uid)}**\n"
            f"🎯 خصمك: **{get_user_discount(uid)}%**\n\n"
            f"اختر الإجراء المطلوب:",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Wallet command error: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ في تحميل المحفظة.")

def get_user_level(user_id):
    """الحصول على مستوى المستخدم"""
    user_data = get_user(user_id)
    if not user_data:
        return "مبتدئ"
    
    ref_count = user_data.get("referral_count", 0)
    
    for level, info in sorted(USER_LEVELS.items(), reverse=True):
        if ref_count >= info["min_refs"]:
            return info["name"]
    
    return "مبتدئ"

def get_user_discount(user_id):
    """الحصول على نسبة خصم المستخدم"""
    user_data = get_user(user_id)
    if not user_data:
        return 0
    
    ref_count = user_data.get("referral_count", 0)
    
    for level, info in sorted(USER_LEVELS.items(), reverse=True):
        if ref_count >= info["min_refs"]:
            return info["discount"]
    
    return 0

# --- [ معالجات جديدة للأزرار ] ---
@bot.callback_query_handler(func=lambda q: q.data.startswith('wallet_'))
def handle_wallet_calls(q):
    """معالجة طلبات المحفظة"""
    try:
        uid = str(q.from_user.id)
        
        if q.data == "wallet_deposit":
            show_deposit_options(q.message)
            
        elif q.data == "wallet_transactions":
            show_transactions(q.message, uid)
            
        elif q.data == "wallet_transfer":
            msg = bot.send_message(q.message.chat.id, "🔢 **أدخل مبلغ التحويل:**")
            bot.register_next_step_handler(msg, process_transfer_amount)
            
        elif q.data == "wallet_buy_code":
            show_buy_with_wallet(q.message)
            
    except Exception as e:
        logger.error(f"Wallet callback error: {e}")
        bot.answer_callback_query(q.id, "❌ حدث خطأ", show_alert=True)

def show_deposit_options(m):
    """عرض خيارات الشحن"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("100 نقطة - 10$", callback_data="deposit_100"),
        types.InlineKeyboardButton("500 نقطة - 45$", callback_data="deposit_500"),
        types.InlineKeyboardButton("1000 نقطة - 85$", callback_data="deposit_1000"),
        types.InlineKeyboardButton("5000 نقطة - 400$", callback_data="deposit_5000")
    )
    markup.add(types.InlineKeyboardButton("↩️ رجوع", callback_data="u_dashboard"))
    
    bot.send_message(
        m.chat.id,
        "💳 **شحن المحفظة**\n\n"
        "اختر المبلغ الذي تريد شحنه:\n\n"
        "✨ **المميزات:**\n"
        "• شحن آمن وسريع\n"
        "• رصيد فوري\n"
        "• استخدام متعدد\n"
        "• دعم جميع التطبيقات",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda q: q.data.startswith('deposit_'))
def handle_deposit(q):
    """معالجة طلب الشحن"""
    try:
        amount = int(q.data.replace('deposit_', ''))
        
        # إنشاء فاتورة الدفع
        bot.send_invoice(
            q.message.chat.id,
            title=f"شحن محفظة - {amount} نقطة",
            description=f"شحن رصيد محفظتك بمقدار {amount} نقطة",
            invoice_payload=f"deposit_{amount}_{q.from_user.id}",
            provider_token="",  # أضف التوكن هنا
            currency="USD",
            prices=[types.LabeledPrice(label="النقاط", amount=amount * 100)]  # تحويل الدولار إلى سنتات
        )
        
    except Exception as e:
        logger.error(f"Deposit error: {e}")
        bot.answer_callback_query(q.id, "❌ حدث خطأ", show_alert=True)

def show_transactions(m, user_id, page=0):
    """عرض سجل المعاملات"""
    try:
        limit = 10
        offset = page * limit
        
        transactions = db_fs.collection("transactions")\
            .where("user_id", "==", user_id)\
            .order_by("timestamp", direction=firestore.Query.DESCENDING)\
            .limit(limit)\
            .offset(offset)\
            .get()
        
        if not transactions:
            return bot.send_message(m.chat.id, "📭 **لا توجد معاملات سابقة.**")
        
        msg = "📜 **سجل معاملاتك:**\n\n"
        
        for t in transactions:
            data = t.to_dict()
            amount = data.get("amount", 0)
            trans_type = data.get("type", "")
            date = datetime.fromtimestamp(data.get("timestamp", time.time())).strftime('%Y-%m-%d %H:%M')
            
            icon = "📥" if amount > 0 else "📤"
            sign = "+" if amount > 0 else ""
            
            msg += f"{icon} **{date}**\n"
            msg += f"المبلغ: `{sign}{amount}` | النوع: `{trans_type}`\n"
            msg += f"الوصف: {data.get('description', '')[:50]}\n"
            msg += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        
        markup = types.InlineKeyboardMarkup()
        
        if page > 0:
            markup.add(types.InlineKeyboardButton("◀️ السابق", callback_data=f"trans_page_{page-1}"))
        
        if len(transactions) == limit:
            markup.add(types.InlineKeyboardButton("▶️ التالي", callback_data=f"trans_page_{page+1}"))
        
        bot.send_message(m.chat.id, msg, parse_mode="Markdown", reply_markup=markup)
        
    except Exception as e:
        logger.error(f"Show transactions error: {e}")
        bot.send_message(m.chat.id, "❌ حدث خطأ في تحميل السجل.")

def process_transfer_amount(m):
    """معالجة مبلغ التحويل"""
    try:
        uid = str(m.from_user.id)
        amount_text = m.text.strip()
        
        if not amount_text.replace('.', '').isdigit():
            return bot.send_message(m.chat.id, "❌ المبلغ غير صالح.")
        
        amount = float(amount_text)
        balance = get_wallet_balance(uid)
        
        if amount <= 0:
            return bot.send_message(m.chat.id, "❌ المبلغ يجب أن يكون أكبر من الصفر.")
        
        if amount > balance:
            return bot.send_message(m.chat.id, f"❌ رصيدك غير كافي. الرصيد المتاح: {balance}")
        
        user_sessions[uid] = {"transfer_amount": amount}
        
        msg = bot.send_message(m.chat.id, "👤 **أرسل معرف المستخدم الذي تريد التحويل إليه:**")
        bot.register_next_step_handler(msg, process_transfer_recipient)
        
    except Exception as e:
        logger.error(f"Transfer amount error: {e}")

def process_transfer_recipient(m):
    """معالجة المستلم"""
    try:
        uid = str(m.from_user.id)
        recipient_id = m.text.strip()
        
        session_data = user_sessions.get(uid, {})
        amount = session_data.get("transfer_amount", 0)
        
        if amount <= 0:
            return bot.send_message(m.chat.id, "❌ انتهت الجلسة، ابدأ من جديد.")
        
        # التحقق من وجود المستخدم
        recipient_data = get_user(recipient_id)
        if not recipient_data:
            return bot.send_message(m.chat.id, "❌ المستخدم غير موجود.")
        
        if recipient_id == uid:
            return bot.send_message(m.chat.id, "❌ لا يمكن التحويل لنفسك.")
        
        # تنفيذ التحويل
        sender_balance = get_wallet_balance(uid)
        
        if amount > sender_balance:
            return bot.send_message(m.chat.id, f"❌ رصيدك غير كافي. الرصيد المتاح: {sender_balance}")
        
        # خصم من المرسل
        update_wallet(uid, -amount, "transfer_out", f"تحويل إلى {recipient_id}")
        
        # إضافة للمستلم
        update_wallet(recipient_id, amount, "transfer_in", f"تحويل من {uid}")
        
        # إرسال إشعار للمستلم
        try:
            bot.send_message(
                recipient_id,
                f"💰 **تحويل جديد**\n\n"
                f"📥 استلمت مبلغ: **{amount}** نقطة\n"
                f"👤 من المستخدم: {
