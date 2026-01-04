import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid, random
from threading import Thread, Lock 
from datetime import datetime

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json" 

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock() 

# --- [ الأيقونات والزخارف ] ---
EMOJIS = {
    "star": "🌟",
    "user": "👤",
    "app": "📱",
    "coin": "🪙",
    "time": "⏳",
    "key": "🔑",
    "lock": "🔒",
    "unlock": "🔓",
    "gift": "🎁",
    "buy": "🛒",
    "list": "📋",
    "news": "📢",
    "ban": "🚫",
    "check": "✅",
    "error": "❌",
    "warning": "⚠️",
    "crown": "👑",
    "fire": "🔥",
    "rocket": "🚀",
    "diamond": "💎",
    "medal": "🏅",
    "trophy": "🏆",
    "heart": "❤️",
    "money": "💵",
    "card": "💳",
    "bell": "🔔",
    "gear": "⚙️",
    "chart": "📊",
    "link": "🔗",
    "code": "🎫",
    "device": "📱",
    "active": "🟢",
    "expired": "⚪",
    "banned": "🔴",
    "calendar": "📅",
    "hourglass": "⌛"
}

# --- [ أسماء مستخدمين زخرفية ] ---
USER_TITLES = [
    "🌟 نجم الإبداع",
    "🚀 رائد المستقبل",
    "💎 قطعة ثمينة",
    "🏅 البطل المتميز",
    "👑 ملك الإبتكار",
    "🔥 الشعلة المتوهجة",
    "❤️ القلب الذهبي",
    "🏆 الفائز الدائم",
    "✨ ساحر الأكواد",
    "🎯 الهدف الدقيق"
]

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): 
            return {
                "users": {}, 
                "app_links": {}, 
                "vouchers": {}, 
                "global_news": f"{EMOJIS['bell']} لا توجد أخبار حالياً",
                "user_stats": {},
                "short_ids": {},
                "last_activity": {}
            }
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: 
                db = json.load(f)
                # إضافة حقول جديدة إذا كانت غير موجودة
                defaults = {
                    "global_news": f"{EMOJIS['bell']} لا توجد أخبار حالياً",
                    "vouchers": {},
                    "user_stats": {},
                    "short_ids": {},
                    "last_activity": {}
                }
                for key, value in defaults.items():
                    if key not in db:
                        db[key] = value
                return db
        except: 
            return {
                "users": {}, 
                "app_links": {}, 
                "vouchers": {}, 
                "global_news": f"{EMOJIS['bell']} لا توجد أخبار حالياً",
                "user_stats": {},
                "short_ids": {},
                "last_activity": {}
            }

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: 
            json.dump(db, f, indent=4, ensure_ascii=False)

# --- [ توليد معرف قصير ] ---
def generate_short_id():
    """توليد معرف قصير (6-8 حرف)"""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ''.join(random.choice(chars) for _ in range(8))

def get_or_create_short_id(full_id):
    """الحصول على معرف قصير أو إنشاء جديد"""
    db = load_db()
    if full_id in db["short_ids"]:
        return db["short_ids"][full_id]
    
    short_id = generate_short_id()
    while short_id in [v for v in db["short_ids"].values()]:
        short_id = generate_short_id()
    
    db["short_ids"][full_id] = short_id
    save_db(db)
    return short_id

def get_full_id(short_id):
    """تحويل المعرف القصير للمعرف الكامل"""
    db = load_db()
    for full_id, s_id in db["short_ids"].items():
        if s_id == short_id:
            return full_id
    return None

# --- [ تزيين الرسائل ] ---
def decorate_message(text, emoji=None, border=False):
    """تزيين الرسائل بإطار وأيقونات"""
    if border:
        border_line = "━" * 40
        return f"{border_line}\n{text}\n{border_line}"
    
    if emoji:
        return f"{emoji} {text}"
    return text

def format_time(seconds):
    """تنسيق الوقت بالأيام والساعات"""
    if seconds <= 0:
        return f"{EMOJIS['expired']} منتهي"
    
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    
    if days > 0:
        return f"{EMOJIS['time']} {days} يوم {hours} ساعة"
    else:
        return f"{EMOJIS['hourglass']} {hours} ساعة"

def get_user_title(user_id):
    """الحصول على لقب مميز للمستخدم"""
    db = load_db()
    if str(user_id) in db.get("user_stats", {}):
        stats = db["user_stats"][str(user_id)]
        # بناء على النشاط
        if stats.get("total_days", 0) > 30:
            return f"{EMOJIS['diamond']} العضو الماسي"
        elif stats.get("total_days", 0) > 15:
            return f"{EMOJIS['medal']} العضو الذهبي"
        elif stats.get("redeemed_codes", 0) > 3:
            return f"{EMOJIS['trophy']} جامع الأكواد"
    
    # إرجاع لقب عشوائي للمستخدمين الجدد
    return random.choice(USER_TITLES)

# --- [ واجهة API ] ---
@app.route('/check')
def check_status():
    aid, pkg = request.args.get('aid'), request.args.get('pkg')
    if not aid or not pkg: 
        return "EXPIRED"
    
    full_id = f"{aid}_{pkg.replace('.', '_')}"
    db = load_db()
    data = db["app_links"].get(full_id)
    
    if not data: 
        return "EXPIRED"
    if data.get("banned"): 
        return "BANNED"
    if time.time() > data.get("end_time", 0): 
        return "EXPIRED"
    
    # تحديث آخر نشاط
    db["last_activity"][full_id] = time.time()
    save_db(db)
    
    return "ACTIVE"

@app.route('/get_news')
def get_news():
    return load_db().get("global_news", f"{EMOJIS['bell']} لا توجد أخبار")

@app.route('/get_user_info/<short_id>')
def get_user_info(short_id):
    """الحصول على معلومات المستخدم عبر المعرف القصير"""
    full_id = get_full_id(short_id)
    if not full_id:
        return json.dumps({"error": "المعرف غير موجود"})
    
    db = load_db()
    data = db["app_links"].get(full_id)
    if not data:
        return json.dumps({"error": "البيانات غير موجودة"})
    
    pkg = full_id.split('_', 1)[-1].replace("_", ".")
    rem_time = data.get("end_time", 0) - time.time()
    
    info = {
        "package": pkg,
        "status": "نشط" if rem_time > 0 else "منتهي",
        "remaining_days": int(rem_time / 86400) if rem_time > 0 else 0,
        "banned": data.get("banned", False),
        "last_activity": db["last_activity"].get(full_id, 0)
    }
    
    return json.dumps(info, ensure_ascii=False)

# --- [ واجهة البوت - البداية ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    
    # إنشاء المستخدم إذا كان جديداً
    if uid not in db["users"]:
        db["users"][uid] = {
            "current_app": None,
            "join_date": time.time(),
            "title": get_user_title(uid)
        }
        # إحصائيات المستخدم
        db["user_stats"][uid] = {
            "total_days": 0,
            "redeemed_codes": 0,
            "last_redeem": 0,
            "total_payments": 0
        }
    
    # تحديث آخر زيارة
    db["last_activity"][uid] = time.time()
    
    args = m.text.split()
    if len(args) > 1:
        cid = args[1]
        if cid not in db["app_links"]:
            db["app_links"][cid] = {
                "end_time": 0,
                "banned": False,
                "trial_used": False,
                "telegram_id": uid,
                "created_at": time.time()
            }
        
        # الحصول على معرف قصير
        short_id = get_or_create_short_id(cid)
        
        db["app_links"][cid]["telegram_id"] = uid
        db["users"][uid]["current_app"] = cid
        save_db(db)
        
        # رسالة الترحيب المزخرفة
        welcome_msg = decorate_message(
            f"**مرحباً {get_user_title(uid)}!**\n\n"
            f"{EMOJIS['check']} **تم ربط جهازك بنجاح!**\n"
            f"{EMOJIS['link']} **المعرف القصير:** `{short_id}`\n"
            f"{EMOJIS['key']} **المعرف الكامل:**\n`{cid}`\n\n"
            f"{EMOJIS['device']} يمكنك استخدام المعرف القصير للتحقق من حالة اشتراكك.",
            border=True
        )
        
        bot.send_message(m.chat.id, welcome_msg, parse_mode="Markdown")
    
    # أزرار القائمة الرئيسية (مزخرفة)
    user_title = get_user_title(m.from_user.id)
    welcome_text = decorate_message(
        f"**{user_title}**\n\n"
        f"{EMOJIS['heart']} مرحباً بك في نظام نجم الإبداع\n"
        f"{EMOJIS['gear']} اختر من القائمة أدناه:",
        emoji=EMOJIS['star']
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"{EMOJIS['app']} تطبيقاتي", callback_data="u_dashboard"),
        types.InlineKeyboardButton(f"{EMOJIS['coin']} رصيدي", callback_data="u_balance"),
        types.InlineKeyboardButton(f"{EMOJIS['code']} تفعيل كود", callback_data="u_redeem"),
        types.InlineKeyboardButton(f"{EMOJIS['gift']} تجربة مجانية", callback_data="u_trial"),
        types.InlineKeyboardButton(f"{EMOJIS['buy']} شراء اشتراك", callback_data="u_buy"),
        types.InlineKeyboardButton(f"{EMOJIS['chart']} إحصائياتي", callback_data="u_stats")
    )
    bot.send_message(m.chat.id, welcome_text, reply_markup=markup, parse_mode="Markdown")

# --- [ معالجة ضغطات الأزرار ] ---
@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    db = load_db()

    # --- خيارات المستخدم ---
    if q.data == "u_dashboard":
        user_dashboard(q.message)
    elif q.data == "u_balance":
        show_balance(q.message)
    elif q.data == "u_redeem":
        msg = bot.send_message(q.message.chat.id, 
            decorate_message("🎫 **أرسل كود التفعيل الآن:**", emoji=EMOJIS['key']))
        bot.register_next_step_handler(msg, redeem_final)
    elif q.data == "u_trial":
        process_trial(q.message)
    elif q.data == "u_buy":
        send_payment(q.message)
    elif q.data == "u_stats":
        user_statistics(q.message)

    # --- خيارات المدير (نجم1) ---
    elif q.from_user.id == ADMIN_ID:
        if q.data == "list_all":
            show_detailed_users(q.message)
        elif q.data == "gen_key":
            msg = bot.send_message(q.message.chat.id, 
                decorate_message("📅 كم عدد الأيام التي تريدها لهذا الكود؟", emoji=EMOJIS['calendar']))
            bot.register_next_step_handler(msg, process_gen_key)
        elif q.data == "bc_tele":
            msg = bot.send_message(q.message.chat.id, 
                decorate_message("📢 ارسل رسالة الإذاعة للتلجرام:", emoji=EMOJIS['news']))
            bot.register_next_step_handler(msg, do_bc_tele)
        elif q.data == "bc_app":
            msg = bot.send_message(q.message.chat.id, 
                decorate_message("🔔 ارسل الخبر الجديد للتطبيق:", emoji=EMOJIS['bell']))
            bot.register_next_step_handler(msg, do_bc_app)
        elif q.data in ["ban_op", "unban_op"]:
            action = "حظر" if q.data == "ban_op" else "فك حظر"
            msg = bot.send_message(q.message.chat.id, 
                decorate_message(f"🚫 ارسل المعرف {action}:", emoji=EMOJIS['ban']))
            bot.register_next_step_handler(msg, process_ban_unban, q.data)
        elif q.data == "admin_stats":
            show_admin_stats(q.message)

# --- [ وظائف المستخدم المزخرفة ] ---

def user_dashboard(m):
    """لوحة تحكم المستخدم المزخرفة"""
    db = load_db()
    uid = str(m.chat.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    
    if not user_apps:
        error_msg = decorate_message(
            f"{EMOJIS['error']} **لا توجد تطبيقات مرتبطة**\n\n"
            f"{EMOJIS['warning']} قم بفتح التطبيق أولاً لربطه بحسابك.",
            border=True
        )
        return bot.send_message(m.chat.id, error_msg, parse_mode="Markdown")
    
    user_title = get_user_title(m.chat.id)
    msg = decorate_message(f"**👤 {user_title}**\n\n", emoji=EMOJIS['app'])
    msg += "**📱 تطبيقاتك الحالية:**\n"
    msg += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
    
    for cid in user_apps:
        data = db["app_links"][cid]
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        rem_time = data.get("end_time", 0) - time.time()
        short_id = get_or_create_short_id(cid)
        
        # تحديد حالة الاشتراك
        if data.get("banned"):
            status_icon = EMOJIS['banned']
            status_text = "محظور"
        elif rem_time > 0:
            status_icon = EMOJIS['active']
            days_left = int(rem_time / 86400)
            status_text = f"نشط ({days_left} يوم)"
        else:
            status_icon = EMOJIS['expired']
            status_text = "منتهي"
        
        msg += f"{status_icon} **{pkg}**\n"
        msg += f"   {EMOJIS['key']} المعرف: `{short_id}`\n"
        msg += f"   {EMOJIS['time']} الحالة: {status_text}\n"
        
        if rem_time > 0:
            expire_date = time.strftime("%Y-%m-%d", time.localtime(data.get("end_time")))
            msg += f"   {EMOJIS['calendar']} الإنتهاء: {expire_date}\n"
        
        msg += "   ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    
    msg += f"\n{EMOJIS['info']} **مجموع التطبيقات:** {len(user_apps)}"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

def show_balance(m):
    """عرض رصيد وتفاصيل اشتراكات المستخدم"""
    db = load_db()
    uid = str(m.chat.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    
    total_days = 0
    active_apps = 0
    expired_apps = 0
    
    for cid in user_apps:
        data = db["app_links"][cid]
        rem_time = data.get("end_time", 0) - time.time()
        
        if data.get("banned"):
            continue
        elif rem_time > 0:
            active_apps += 1
            total_days += int(rem_time / 86400)
        else:
            expired_apps += 1
    
    balance_msg = decorate_message(
        f"**💰 رصيدك واحصائياتك**\n\n"
        f"{EMOJIS['coin']} **الأيام المتبقية:** {total_days} يوم\n"
        f"{EMOJIS['active']} **التطبيقات النشطة:** {active_apps}\n"
        f"{EMOJIS['expired']} **التطبيقات المنتهية:** {expired_apps}\n"
        f"{EMOJIS['app']} **المجموع الكلي:** {len(user_apps)}\n\n"
        f"{EMOJIS['gift']} **رموز التفعيل المستخدمة:** {db['user_stats'].get(uid, {}).get('redeemed_codes', 0)}",
        border=True
    )
    
    bot.send_message(m.chat.id, balance_msg, parse_mode="Markdown")

def user_statistics(m):
    """إحصائيات مفصلة للمستخدم"""
    db = load_db()
    uid = str(m.chat.id)
    stats = db.get("user_stats", {}).get(uid, {})
    user_data = db.get("users", {}).get(uid, {})
    
    if not stats:
        stats = {
            "total_days": 0,
            "redeemed_codes": 0,
            "last_redeem": 0,
            "total_payments": 0
        }
    
    # حساب إحصائيات إضافية
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    active_count = sum(1 for cid in user_apps if 
                      db["app_links"][cid].get("end_time", 0) > time.time() and 
                      not db["app_links"][cid].get("banned", False))
    
    join_date = user_data.get("join_date", time.time())
    days_since_join = int((time.time() - join_date) / 86400)
    
    stats_msg = decorate_message(
        f"**📊 إحصائياتك الشخصية**\n\n"
        f"{EMOJIS['medal']} **لقبك:** {get_user_title(m.chat.id)}\n"
        f"{EMOJIS['calendar']} **تاريخ الانضمام:** {time.strftime('%Y-%m-%d', time.localtime(join_date))}\n"
        f"{EMOJIS['time']} **مدة العضوية:** {days_since_join} يوم\n\n"
        f"{EMOJIS['chart']} **نشاطك:**\n"
        f"   • {EMOJIS['coin']} إجمالي الأيام: {stats.get('total_days', 0)}\n"
        f"   • {EMOJIS['code']} الأكواد المفعلة: {stats.get('redeemed_codes', 0)}\n"
        f"   • {EMOJIS['buy']} المشتريات: {stats.get('total_payments', 0)}\n"
        f"   • {EMOJIS['app']} التطبيقات النشطة: {active_count}\n\n"
        f"{EMOJIS['fire']} **مستواك:** {get_user_title(m.chat.id)}",
        border=True
    )
    
    bot.send_message(m.chat.id, stats_msg, parse_mode="Markdown")

def redeem_final(m):
    """تفعيل الكود النهائي"""
    code = m.text.strip().upper()
    db = load_db()
    uid = str(m.from_user.id)
    
    if code in db["vouchers"]:
        days = db["vouchers"].pop(code)
        cid = db["users"].get(uid, {}).get("current_app")
        
        if cid:
            current_end = db["app_links"][cid].get("end_time", 0)
            if current_end < time.time():
                current_end = time.time()
            
            db["app_links"][cid]["end_time"] = current_end + (days * 86400)
            
            # تحديث إحصائيات المستخدم
            if uid not in db["user_stats"]:
                db["user_stats"][uid] = {"total_days": 0, "redeemed_codes": 0}
            
            db["user_stats"][uid]["total_days"] = db["user_stats"][uid].get("total_days", 0) + days
            db["user_stats"][uid]["redeemed_codes"] = db["user_stats"][uid].get("redeemed_codes", 0) + 1
            db["user_stats"][uid]["last_redeem"] = time.time()
            
            save_db(db)
            
            success_msg = decorate_message(
                f"**🎉 تم التفعيل بنجاح!**\n\n"
                f"{EMOJIS['check']} **المدة المضافة:** {days} يوم\n"
                f"{EMOJIS['coin']} **الإجمالي الجديد:** {int((db['app_links'][cid]['end_time'] - time.time()) / 86400)} يوم\n"
                f"{EMOJIS['calendar']} **ينتهي في:** {time.strftime('%Y-%m-%d', time.localtime(db['app_links'][cid]['end_time']))}",
                emoji=EMOJIS['trophy']
            )
            
            bot.send_message(m.chat.id, success_msg, parse_mode="Markdown")
        else:
            error_msg = decorate_message(
                f"{EMOJIS['error']} **يجب ربط التطبيق أولاً**\n\n"
                f"{EMOJIS['warning']} افتح التطبيق على جهازك ثم ارجع هنا.",
                border=True
            )
            bot.send_message(m.chat.id, error_msg, parse_mode="Markdown")
    else:
        error_msg = decorate_message(
            f"{EMOJIS['error']} **الكود غير صحيح**\n\n"
            f"{EMOJIS['warning']} تأكد من كتابة الكود بشكل صحيح.",
            border=True
        )
        bot.send_message(m.chat.id, error_msg, parse_mode="Markdown")

def process_trial(m):
    """معالجة التجربة المجانية"""
    db = load_db()
    uid = str(m.chat.id)
    cid = db["users"].get(uid, {}).get("current_app")
    
    if not cid:
        error_msg = decorate_message(
            f"{EMOJIS['error']} **يجب ربط التطبيق أولاً**",
            emoji=EMOJIS['warning']
        )
        return bot.send_message(m.chat.id, error_msg, parse_mode="Markdown")
    
    if db["app_links"][cid].get("trial_used"):
        error_msg = decorate_message(
            f"{EMOJIS['warning']} **لقد استخدمت التجربة سابقاً**\n\n"
            f"{EMOJIS['buy']} يمكنك شراء اشتراك من القائمة الرئيسية.",
            border=True
        )
        return bot.send_message(m.chat.id, error_msg, parse_mode="Markdown")
    
    # تفعيل التجربة المجانية
    db["app_links"][cid].update({
        "trial_used": True,
        "end_time": time.time() + 7200,  # ساعتين
        "trial_activated": time.time()
    })
    save_db(db)
    
    trial_msg = decorate_message(
        f"**🎁 تم تفعيل التجربة المجانية!**\n\n"
        f"{EMOJIS['gift']} **المدة:** 2 ساعة\n"
        f"{EMOJIS['time']} **تبدأ من:** الآن\n"
        f"{EMOJIS['hourglass']} **تنتهي في:** {time.strftime('%H:%M', time.localtime(time.time() + 7200))}\n\n"
        f"{EMOJIS['info']} استمتع بالتجربة! يمكنك شراء اشتراك كامل بعد انتهائها.",
        border=True
    )
    
    bot.send_message(m.chat.id, trial_msg, parse_mode="Markdown")

def send_payment(m):
    """إرسال فاتورة الدفع"""
    db = load_db()
    uid = str(m.chat.id)
    cid = db["users"].get(uid, {}).get("current_app")
    
    if not cid:
        error_msg = decorate_message(
            f"{EMOJIS['error']} **يجب ربط التطبيق أولاً**",
            emoji=EMOJIS['warning']
        )
        return bot.send_message(m.chat.id, error_msg, parse_mode="Markdown")
    
    short_id = get_or_create_short_id(cid)
    pkg = cid.split('_', 1)[-1].replace("_", ".")
    
    # إنشاء فاتورة مزخرفة
    bot.send_invoice(
        m.chat.id,
        title=f"{EMOJIS['diamond']} اشتراك 30 يوم - {pkg}",
        description=f"{EMOJIS['app']} التطبيق: {pkg}\n{EMOJIS['key']} المعرف: {short_id}",
        invoice_payload=f"pay_{cid}",
        provider_token="",  # أضف التوكن الخاص بك هنا
        currency="XTR",
        prices=[types.LabeledPrice(f"{EMOJIS['crown']} اشتراك VIP", 100)],
        photo_url="https://via.placeholder.com/512x512/4A90E2/FFFFFF?text=⭐",
        photo_size=512,
        need_name=True
    )

# --- [ وظائف الإدارة المطورة ] ---

def show_detailed_users(m):
    """عرض المستخدمين بالتفصيل"""
    db = load_db()
    
    if not db["app_links"]:
        error_msg = decorate_message(
            f"{EMOJIS['warning']} **لا توجد أجهزة مسجلة**",
            border=True
        )
        return bot.send_message(m.chat.id, error_msg, parse_mode="Markdown")
    
    # تصنيف المستخدمين
    active = []
    expired = []
    banned = []
    
    for cid, data in db["app_links"].items():
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        rem_time = data.get("end_time", 0) - time.time()
        short_id = get_or_create_short_id(cid)
        
        user_info = {
            "id": short_id,
            "full_id": cid,
            "package": pkg,
            "telegram_id": data.get("telegram_id", "غير معروف"),
            "remaining": rem_time
        }
        
        if data.get("banned"):
            banned.append(user_info)
        elif rem_time > 0:
            active.append(user_info)
        else:
            expired.append(user_info)
    
    # إرسال التقرير
    report = decorate_message(
        f"**📊 تقرير المستخدمين**\n\n"
        f"{EMOJIS['active']} **النشطين:** {len(active)}\n"
        f"{EMOJIS['expired']} **المنتهين:** {len(expired)}\n"
        f"{EMOJIS['banned']} **المحظورين:** {len(banned)}\n"
        f"{EMOJIS['app']} **الإجمالي:** {len(db['app_links'])}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯",
        emoji=EMOJIS['chart']
    )
    
    bot.send_message(m.chat.id, report, parse_mode="Markdown")
    
    # عرض النشطين
    if active:
        active_list = f"{EMOJIS['active']} **المستخدمين النشطين:**\n"
        for i, user in enumerate(active[:10], 1):  # عرض أول 10 فقط
            days_left = int(user["remaining"] / 86400)
            active_list += f"{i}. `{user['id']}` - {user['package']} ({days_left} يوم)\n"
        
        if len(active) > 10:
            active_list += f"\n{EMOJIS['info']} وعرض {len(active) - 10} نشيط آخر..."
        
        bot.send_message(m.chat.id, active_list, parse_mode="Markdown")

def process_gen_key(m):
    """معالجة إنشاء كود جديد"""
    if not m.text.isdigit():
        error_msg = decorate_message(
            f"{EMOJIS['error']} **خطأ في الإدخال**\n\n"
            f"{EMOJIS['warning']} يجب إدخال رقم فقط.",
            border=True
        )
        return bot.send_message(m.chat.id, error_msg, parse_mode="Markdown")
    
    days = int(m.text)
    
    # توليد كود خاص
    prefixes = ["VIP", "GOLD", "PRO", "ULTRA", "MEGA"]
    prefix = random.choice(prefixes)
    code = f"{prefix}-{str(uuid.uuid4())[:6].upper()}-{random.randint(100, 999)}"
    
    db = load_db()
    db["vouchers"][code] = days
    save_db(db)
    
    success_msg = decorate_message(
        f"**🎫 تم إنشاء كود جديد!**\n\n"
        f"{EMOJIS['key']} **الكود:** `{code}`\n"
        f"{EMOJIS['calendar']} **المدة:** {days} يوم\n"
        f"{EMOJIS['time']} **تاريخ الإنشاء:** {time.strftime('%Y-%m-%d %H:%M')}\n"
        f"{EMOJIS['info']} **الاستخدامات:** مرة واحدة\n\n"
        f"{EMOJIS['warning']} **ملاحظة:** هذا الكود سينتهي بعد استخدامه.",
        border=True
    )
    
    bot.send_message(m.chat.id, success_msg, parse_mode="Markdown")

def show_admin_stats(m):
    """إحصائيات المدير"""
    db = load_db()
    
    # حساب الإحصائيات
    total_users = len(db["users"])
    total_devices = len(db["app_links"])
    active_devices = sum(1 for x in db["app_links"].values() if x.get("end_time", 0) > time.time())
    total_vouchers = len(db["vouchers"])
    
    # المستخدمين النشطين اليوم
    today = time.time() - 86400
    active_today = sum(1 for last_time in db["last_activity"].values() if last_time > today)
    
    stats_msg = decorate_message(
        f"**👑 إحصائيات المدير**\n\n"
        f"{EMOJIS['user']} **المستخدمين:** {total_users}\n"
        f"{EMOJIS['device']} **الأجهزة:** {total_devices}\n"
        f"{EMOJIS['active']} **النشطين:** {active_devices}\n"
        f"{EMOJIS['coin']} **الأكواد المتاحة:** {total_vouchers}\n"
        f"{EMOJIS['fire']} **النشطين اليوم:** {active_today}\n\n"
        f"{EMOJIS['chart']} **نسبة النشاط:** {int((active_devices/total_devices)*100) if total_devices > 0 else 0}%\n"
        f"{EMOJIS['time']} **آخر تحديث:** {time.strftime('%H:%M:%S')}",
        border=True
    )
    
    bot.send_message(m.chat.id, stats_msg, parse_mode="Markdown")

# --- [ لوحة المدير الرئيسية ] ---
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    active_now = sum(1 for x in db["app_links"].values() if x.get("end_time", 0) > time.time())
    
    msg = decorate_message(
        f"**👑 إدارة نجم الإبداع**\n\n"
        f"{EMOJIS['user']} **المستخدمين:** `{len(db['users'])}`\n"
        f"{EMOJIS['device']} **الأجهزة:** `{len(db['app_links'])}`\n"
        f"{EMOJIS['active']} **النشطين:** `{active_now}`\n"
        f"{EMOJIS['coin']} **الأكواد:** `{len(db['vouchers'])}`\n"
        f"{EMOJIS['fire']} **المستوى:** {get_user_title(ADMIN_ID)}",
        emoji=EMOJIS['crown']
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"{EMOJIS['chart']} إحصائيات", callback_data="admin_stats"),
        types.InlineKeyboardButton(f"{EMOJIS['list']} عرض المشتركين", callback_data="list_all"),
        types.InlineKeyboardButton(f"{EMOJIS['key']} توليد كود", callback_data="gen_key"),
        types.InlineKeyboardButton(f"{EMOJIS['ban']} حظر جهاز", callback_data="ban_op"),
        types.InlineKeyboardButton(f"{EMOJIS['unlock']} فك حظر", callback_data="unban_op"),
        types.InlineKeyboardButton(f"{EMOJIS['bell']} إعلان تطبيق", callback_data="bc_app"),
        types.InlineKeyboardButton(f"{EMOJIS['news']} إعلان تلجرام", callback_data="bc_tele"),
        types.InlineKeyboardButton(f"{EMOJIS['gear']} إعدادات", callback_data="admin_settings")
    )
    
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- [ وظائف مساعدة للإدارة ] ---
def do_bc_tele(m):
    """الإذاعة في التلجرام"""
    db = load_db()
    count = 0
    failed = 0
    
    broadcast_msg = decorate_message(
        f"**📢 إشعار من الإدارة**\n\n{m.text}\n\n"
        f"{EMOJIS['time']} {time.strftime('%Y-%m-%d %H:%M')}",
        border=True
    )
    
    for uid in db["users"]:
        try: 
            bot.send_message(uid, broadcast_msg, parse_mode="Markdown")
            count += 1
        except: 
            failed += 1
        time.sleep(0.1)  # تجنب حظر التلجرام
    
    result_msg = decorate_message(
        f"**✅ تم الإرسال بنجاح**\n\n"
        f"{EMOJIS['check']} **المرسل إليهم:** {count}\n"
        f"{EMOJIS['error']} **الفاشلين:** {failed}\n"
        f"{EMOJIS['chart']} **نسبة النجاح:** {int((count/(count+failed))*100) if count+failed > 0 else 0}%",
        emoji=EMOJIS['news']
    )
    
    bot.send_message(m.chat.id, result_msg, parse_mode="Markdown")

def do_bc_app(m):
    """تحديث خبر التطبيق"""
    db = load_db()
    db["global_news"] = decorate_message(m.text, emoji=EMOJIS['bell'])
    save_db(db)
    
    success_msg = decorate_message(
        f"**✅ تم تحديث خبر التطبيق**\n\n"
        f"{EMOJIS['bell']} **الخبر الجديد:**\n{m.text}",
        border=True
    )
    
    bot.send_message(m.chat.id, success_msg, parse_mode="Markdown")

def process_ban_unban(m, mode):
    """معالجة الحظر وفك الحظر"""
    target = m.text.strip()
    
    # التحقق إذا كان معرف قصير
    full_id = get_full_id(target)
    if not full_id:
        # إذا لم يكن معرف قصير، استخدمه كما هو
        full_id = target
    
    db = load_db()
    
    if full_id in db["app_links"]:
        action = "حظر" if mode == "ban_op" else "فك حظر"
        db["app_links"][full_id]["banned"] = (mode == "ban_op")
        save_db(db)
        
        result_msg = decorate_message(
            f"**✅ تم {action} الجهاز**\n\n"
            f"{EMOJIS['key']} **المعرف:** `{target}`\n"
            f"{EMOJIS['time']} **التاريخ:** {time.strftime('%Y-%m-%d %H:%M')}\n"
            f"{EMOJIS['info']} **الحالة:** {'محظور' if mode == 'ban_op' else 'نشط'}",
            emoji=EMOJIS['check'] if mode == 'unban_op' else EMOJIS['ban']
        )
        
        bot.send_message(m.chat.id, result_msg, parse_mode="Markdown")
    else:
        error_msg = decorate_message(
            f"{EMOJIS['error']} **المعرف غير موجود**\n\n"
            f"{EMOJIS['warning']} تأكد من صحة المعرف المطلوب.",
            border=True
        )
        bot.send_message(m.chat.id, error_msg, parse_mode="Markdown")

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): 
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    """معالجة الدفع الناجح"""
    db = load_db()
    cid = m.successful_payment.invoice_payload.replace("pay_", "")
    
    if cid in db["app_links"]:
        current_end = max(time.time(), db["app_links"][cid].get("end_time", 0))
        db["app_links"][cid]["end_time"] = current_end + (30 * 86400)
        
        # تحديث إحصائيات المستخدم
        uid = str(m.from_user.id)
        if uid in db["user_stats"]:
            db["user_stats"][uid]["total_payments"] = db["user_stats"][uid].get("total_payments", 0) + 1
            db["user_stats"][uid]["total_days"] = db["user_stats"][uid].get("total_days", 0) + 30
        
        save_db(db)
        
        short_id = get_or_create_short_id(cid)
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        
        success_msg = decorate_message(
            f"**🎉 تم الشراء بنجاح!**\n\n"
            f"{EMOJIS['check']} **تم تفعيل الاشتراك**\n"
            f"{EMOJIS['app']} **التطبيق:** {pkg}\n"
            f"{EMOJIS['key']} **المعرف:** {short_id}\n"
            f"{EMOJIS['calendar']} **المدة:** 30 يوم\n"
            f"{EMOJIS['time']} **ينتهي في:** {time.strftime('%Y-%m-%d', time.localtime(db['app_links'][cid]['end_time']))}\n\n"
            f"{EMOJIS['heart']} **شكراً لثقتك بنا!**",
            border=True
        )
        
        bot.send_message(m.chat.id, success_msg, parse_mode="Markdown")
    else:
        error_msg = decorate_message(
            f"{EMOJIS['error']} **حدث خطأ**\n\n"
            f"{EMOJIS['warning']} لم يتم العثور على الجهاز. يرجى التواصل مع الدعم.",
            border=True
        )
        bot.send_message(m.chat.id, error_msg, parse_mode="Markdown")

# --- [ التشغيل ] ---
def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    print(f"{EMOJIS['rocket']} بوت نجم الإبداع يعمل الآن...")
    print(f"{EMOJIS['crown']} المدير: {ADMIN_ID}")
    print(f"{EMOJIS['star']} بدأ التشغيل في: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    Thread(target=run).start()
    bot.infinity_polling()
