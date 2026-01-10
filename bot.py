import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread, Lock 

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
CHANNEL_ID = "@jrhwm0njm" # معرف القناة المطلوب الانضمام لها
DATA_FILE = "master_data.json" 

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock() 

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): 
            return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار", "logs": [], "referrals": {}}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: 
                db = json.load(f)
                # تأكد من وجود المفاتيح الأساسية دائماً
                keys = ["global_news", "vouchers", "logs", "referrals", "users", "app_links"]
                for key in keys:
                    if key not in db: db[key] = [] if key == "logs" else {}
                return db
        except Exception as e:
            # إذا فشل التحميل والملف موجود، لا تعيد بيانات فارغة لكي لا تمسح القديم
            print(f"Error loading DB: {e}")
            # نحاول القراءة مرة أخرى أو نمرر البيانات الحالية
            return None 

def save_db(db):
    if db is None: return # منع حفظ بيانات فارغة في حال فشل التحميل
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: 
            json.dump(db, f, indent=4, ensure_ascii=False) 

def add_log(text):
    db = load_db()
    if db:
        db["logs"].append(f"[{time.strftime('%Y-%m-%d %H:%M')}] {text}")
        if len(db["logs"]) > 100: db["logs"].pop(0) 
        save_db(db) 

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
    uid = f"{aid}_{pkg.replace('.', '_')}"
    db = load_db()
    if not db: return "EXPIRED"
    data = db["app_links"].get(uid)
    if not data: return "EXPIRED"
    if data.get("banned"): return "BANNED"
    if time.time() > data.get("end_time", 0): return "EXPIRED"
    return "ACTIVE" 

@app.route('/get_news') 
def get_news():
    db = load_db()
    return db.get("global_news", "لا توجد أخبار") if db else "لا توجد أخبار"

# --- [ واجهة البوت - البداية ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    if not db: return
    uid = str(m.from_user.id)
    username = f"@{m.from_user.username}" if m.from_user.username else m.from_user.first_name
    
    args = m.text.split()
    is_new_user = uid not in db["users"]
    
    if is_new_user:
        inviter_id = args[1] if len(args) > 1 and args[1].isdigit() and args[1] != uid else None
        db["users"][uid] = {
            "current_app": None, 
            "name": username, 
            "invited_by": inviter_id,
            "referral_count": 0,
            "claimed_channel_gift": False,
            "join_date": time.time()
        }
    else:
        db["users"][uid]["name"] = username 

    if len(args) > 1 and "_" in args[1]:
        cid = args[1]
        if cid not in db["app_links"]:
            db["app_links"][cid] = {"end_time": 0, "banned": False, "trial_last_time": 0, "telegram_id": uid, "gift_claimed": False}
        
        db["app_links"][cid]["telegram_id"] = uid
        db["users"][uid]["current_app"] = cid
        
        if check_membership(uid) and not db["app_links"][cid].get("gift_claimed"):
            db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (3 * 86400)
            db["app_links"][cid]["gift_claimed"] = True
            bot.send_message(m.chat.id, "🎁 **مبروك! حصلت على 3 أيام مجانية لانضمامك لقناتنا.**", parse_mode="Markdown")
            
            inviter = db["users"][uid].get("invited_by")
            if inviter and inviter in db["users"]:
                inviter_app = db["users"][inviter].get("current_app")
                if inviter_app and inviter_app in db["app_links"]:
                    db["app_links"][inviter_app]["end_time"] += (7 * 86400)
                    db["users"][inviter]["referral_count"] += 1
                    try: bot.send_message(inviter, f"🎊 شخص دعوته انضم وربط جهازه! حصلت على **7 أيام** إضافية.", parse_mode="Markdown")
                    except: pass
        
        bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**", parse_mode="Markdown")
    
    save_db(db) 

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
        types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
        types.InlineKeyboardButton("🔗 إحالاتي ومكافآتي", callback_data="u_referral"),
        types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
        types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy")
    )
    bot.send_message(m.chat.id, f"مرحباً بك يا **{username}** 🌟\nقناتنا: {CHANNEL_ID}\nاستخدم القائمة أدناه للتحكم في اشتراكاتك:", reply_markup=markup, parse_mode="Markdown") 

# --- [ معالجة ضغطات الأزرار ] ---
@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    db = load_db()
    if not db: return

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

# --- [ وظائف الإدارة ] --- 

def show_detailed_users(m):
    db = load_db()
    if not db or not db["app_links"]: return bot.send_message(m.chat.id, "لا توجد أجهزة مسجلة.")
    full_list = "📂 **إحصائيات الأجهزة:**\n\n"
    for cid, data in db["app_links"].items():
        owner_name = db["users"].get(data.get("telegram_id", ""), {}).get("name", "غير معروف")
        rem_time = data.get("end_time", 0) - time.time()
        stat = "🔴 محظور" if data.get("banned") else (f"🟢 {int(rem_time/86400)} يوم" if rem_time > 0 else "⚪ منتهي")
        full_list += f"👤: {owner_name} | {stat}\n🆔: `{cid}`\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        if len(full_list) > 3000:
            bot.send_message(m.chat.id, full_list, parse_mode="Markdown"); full_list = ""
    if full_list: bot.send_message(m.chat.id, full_list, parse_mode="Markdown") 

def show_logs(m):
    db = load_db()
    if not db: return
    logs = "\n".join(db["logs"][-15:]) if db["logs"] else "لا توجد سجلات."
    bot.send_message(m.chat.id, f"📝 **آخر العمليات:**\n\n{logs}") 

def show_top_referrers(m):
    db = load_db()
    if not db: return
    sorted_users = sorted(db["users"].items(), key=lambda x: x[1].get("referral_count", 0), reverse=True)[:10]
    msg = "🏆 **أفضل 10 داعين للبوت:**\n\n"
    for i, (uid, data) in enumerate(sorted_users, 1):
        msg += f"{i}- {data['name']} ⮕ `{data.get('referral_count', 0)}` إحالة\n"
    bot.send_message(m.chat.id, msg) 

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    if not db: return
    active_now = sum(1 for x in db["app_links"].values() if x.get("end_time", 0) > time.time())
    msg = (f"👑 **إدارة نجم الإبداع**\n\n"
           f"👥 المستخدمين: `{len(db['users'])}` | الأجهزة: `{len(db['app_links'])}`\n"
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
    db = load_db()
    if not db: return
    user_data = db["users"].get(uid, {})
    ref_link = f"https://t.me/{bot.get_me().username}?start={uid}"
    count = user_data.get("referral_count", 0)
    msg = (f"🔗 **نظام الإحالات:**\n\n"
           f"كل شخص يدخل من رابطك وينضم للقناة ويربط جهازه، ستحصل أنت على **7 أيام مجانية!**\n\n"
           f"👥 عدد إحالاتك الناجحة: `{count}`\n"
           f"🎁 إجمالي الأيام المكتسبة: `{count * 7}` يوم\n\n"
           f"رابط دعوتك:\n`{ref_link}`")
    bot.send_message(m.chat.id, msg, parse_mode="Markdown") 

def user_dashboard(m):
    db = load_db()
    if not db: return
    uid = str(m.chat.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps: return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة.")
    msg = "👤 **حالة اشتراكاتك:**\n"
    for cid in user_apps:
        data = db["app_links"][cid]
        pkg = cid.split('_', 1)[-1].replace("_", ".")
        rem_time = data.get("end_time", 0) - time.time()
        status = f"✅ {int(rem_time/86400)} يوم" if rem_time > 0 else "❌ منتهي"
        if data.get("banned"): status = "🚫 محظور"
        msg += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📦 `{pkg}`\nالحالة: {status}\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown") 

def redeem_code_step(m):
    code = m.text.strip(); db = load_db()
    if not db: return
    if code not in db["vouchers"]: return bot.send_message(m.chat.id, "❌ الكود غير صحيح.")
    uid = str(m.from_user.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps: return bot.send_message(m.chat.id, "❌ اربط جهازك أولاً.")
    db["users"][uid]["temp_code"] = code; save_db(db)
    markup = types.InlineKeyboardMarkup(row_width=1)
    for cid in user_apps: markup.add(types.InlineKeyboardButton(f"📦 {cid.split('_')[-1]}", callback_data=f"redeem_select_{cid}"))
    bot.send_message(m.chat.id, "🛠️ اختر التطبيق لتفعيل الكود:", reply_markup=markup) 

def redeem_select_app(m, selected_cid):
    db = load_db()
    if not db: return
    uid = str(m.chat.id)
    code = db["users"].get(uid, {}).pop("temp_code", None)
    if not code or code not in db["vouchers"]: return bot.send_message(m.chat.id, "❌ انتهت الجلسة.")
    days = db["vouchers"].pop(code)
    db["app_links"][selected_cid]["end_time"] = max(time.time(), db["app_links"][selected_cid].get("end_time", 0)) + (days * 86400)
    add_log(f"تفعيل كود ({days} يوم) للمستخدم {db['users'][uid]['name']}")
    save_db(db); bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم بنجاح!") 

def process_trial(m):
    db = load_db()
    if not db: return
    uid = str(m.chat.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps: return bot.send_message(m.chat.id, "❌ لا يوجد تطبيق مرتبط.")
    markup = types.InlineKeyboardMarkup(row_width=1)
    for cid in user_apps: markup.add(types.InlineKeyboardButton(f"📦 {cid.split('_')[-1]}", callback_data=f"trial_select_{cid}"))
    bot.send_message(m.chat.id, "🛠️ اختر تطبيق التجربة:", reply_markup=markup) 

def trial_select_app(m, selected_cid):
    db = load_db()
    if not db: return
    data = db["app_links"].get(selected_cid)
    if not data: return
    if time.time() - data.get("trial_last_time", 0) < 86400:
        return bot.send_message(m.chat.id, "❌ التجربة متاحة مرة كل 24 ساعة.")
    data["trial_last_time"] = time.time()
    # تم تغيير المدة هنا لتصبح 3 أيام (259200 ثانية)
    data["end_time"] = max(time.time(), data.get("end_time", 0)) + 259200
    save_db(db); bot.send_message(m.chat.id, "✅ تم تفعيل 3 أيام تجربة!") 

def send_payment(m):
    db = load_db()
    if not db: return
    uid = str(m.chat.id)
    cid = db["users"].get(uid, {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ افتح التطبيق أولاً.")
    bot.send_invoice(m.chat.id, title="اشتراك 30 يوم", description=f"الحساب: {cid}", 
                     invoice_payload=f"pay_{cid}", provider_token="", currency="XTR",
                     prices=[types.LabeledPrice(label="VIP", amount=100)]) 

# --- [ خيوط الخلفية (Background Threads) ] --- 

def expiry_notifier():
    while True:
        try:
            db = load_db()
            if db:
                now = time.time()
                for cid, data in db["app_links"].items():
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
    db = load_db()
    if not db: return
    count = 0
    for uid in db["users"]:
        try: bot.send_message(uid, f"📢 **إعلان:**\n\n{m.text}"); count += 1
        except: pass
    bot.send_message(m.chat.id, f"✅ تم الإرسال لـ {count}") 

def do_bc_app(m):
    db = load_db()
    if not db: return
    db["global_news"] = m.text; save_db(db)
    bot.send_message(m.chat.id, "✅ تم تحديث خبر التطبيق.") 

def process_gen_key(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "⚠️ أرسل رقماً.")
    days = int(m.text); code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db = load_db()
    if not db: return
    db["vouchers"][code] = days; save_db(db)
    add_log(f"توليد كود جديد {days} يوم")
    bot.send_message(m.chat.id, f"🎫 كود جديد ({days} يوم):\n`{code}`", parse_mode="Markdown") 

def process_ban_unban(m, mode):
    db = load_db()
    if not db: return
    target = m.text.strip()
    if target in db["app_links"]:
        db["app_links"][target]["banned"] = (mode == "ban_op")
        save_db(db); add_log(f"{'حظر' if mode=='ban_op' else 'فك حظر'} الجهاز {target}")
        bot.send_message(m.chat.id, "✅ تمت العملية.")
    else: bot.send_message(m.chat.id, "❌ المعرف غير موجود.") 

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True) 

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db()
    if not db: return
    cid = m.successful_payment.invoice_payload.replace("pay_", "")
    db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (30 * 86400)
    add_log(f"شراء اشتراك 30 يوم للجهاز {cid}")
    save_db(db); bot.send_message(m.chat.id, "✅ تم الشراء بنجاح!") 

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))) 

if __name__ == "__main__":
    Thread(target=run).start()
    Thread(target=expiry_notifier).start()
    bot.infinity_polling()
