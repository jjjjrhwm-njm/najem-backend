import telebot
from telebot import types
from flask import Flask, request, jsonify
import json, os, time, uuid
from threading import Thread, Lock 

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json" 

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock() 

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): 
            return {
                "users": {}, 
                "app_links": {}, 
                "vouchers": {}, 
                "global_news": "لا توجد أخبار حالياً",
                "ui_config": { # إعدادات النافذة التي تظهر في التطبيق
                    "title": "نظام نجم الإبداع",
                    "msg": "يرجى تفعيل الاشتراك لاستخدام التطبيق",
                    "btn_text": "تواصل مع الدعم",
                    "btn_link": "https://t.me/rashed"
                }
            }
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: 
                db = json.load(f)
                # التأكد من وجود المفاتيح الجديدة لتجنب الأخطاء
                if "ui_config" not in db:
                    db["ui_config"] = {"title": "تنبيه", "msg": "يجب التفعيل", "btn_text": "دعم", "btn_link": "t.me/.."}
                if "vouchers" not in db: db["vouchers"] = {}
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار"}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4, ensure_ascii=False) 

# --- [ واجهة API المحدثة ] ---
# هذا الرابط هو ما سيطلبه التطبيق عند الفتح ليحصل على كل شيء (الحالة + نصوص النافذة)
@app.route('/app_sync')
def app_sync():
    aid, pkg = request.args.get('aid'), request.args.get('pkg')
    db = load_db()
    
    if not aid or not pkg: 
        return jsonify({"status": "EXPIRED", "ui": db["ui_config"]})
    
    uid = f"{aid}_{pkg.replace('.', '_')}"
    data = db["app_links"].get(uid)
    
    # تحديد الحالة البرمجية
    status = "EXPIRED"
    if data:
        if data.get("banned"): status = "BANNED"
        elif time.time() < data.get("end_time", 0): status = "ACTIVE"
    
    # إرسال الحالة + إعدادات الواجهة كـ JSON واحد
    return jsonify({
        "status": status,
        "ui": db["ui_config"],
        "news": db.get("global_news", "")
    })

# --- [ واجهة البوت - البداية ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    if uid not in db["users"]: db["users"][uid] = {"current_app": None}
    
    args = m.text.split()
    if len(args) > 1:
        cid = args[1]
        if cid not in db["app_links"]:
            db["app_links"][cid] = {"end_time": 0, "banned": False, "trial_used": False, "telegram_id": uid}
        db["app_links"][cid]["telegram_id"] = uid
        db["users"][uid]["current_app"] = cid
        save_db(db)
        bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**", parse_mode="Markdown")

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
        types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
        types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
        types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy")
    )
    bot.send_message(m.chat.id, f"مرحباً بك يا **نجم الإبداع** 🌟\nاستخدم القائمة أدناه للتحكم في اشتراكاتك:", reply_markup=markup, parse_mode="Markdown")

# --- [ معالجة ضغطات الأزرار ] ---
@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    db = load_db()

    # --- خيارات المستخدم ---
    if q.data == "u_dashboard":
        user_dashboard(q.message)
    elif q.data == "u_redeem":
        msg = bot.send_message(q.message.chat.id, "🎫 **أرسل كود التفعيل الآن:**")
        bot.register_next_step_handler(msg, redeem_final)
    elif q.data == "u_trial":
        process_trial(q.message)
    elif q.data == "u_buy":
        send_payment(q.message)

    # --- خيارات المدير (نجم1) ---
    elif q.from_user.id == ADMIN_ID:
        if q.data == "list_all":
            show_detailed_users(q.message)
        elif q.data == "edit_ui":
            msg = bot.send_message(q.message.chat.id, "🖼 **أرسل بيانات النافذة بالتنسيق التالي:**\n\nالعنوان | الرسالة | نص الزر | الرابط")
            bot.register_next_step_handler(msg, process_edit_ui)
        elif q.data == "gen_key":
            msg = bot.send_message(q.message.chat.id, "كم عدد الأيام التي تريدها لهذا الكود؟ (أرسل رقماً فقط)")
            bot.register_next_step_handler(msg, process_gen_key)
        elif q.data == "bc_app":
            msg = bot.send_message(q.message.chat.id, "ارسل الخبر الجديد للتطبيق:")
            bot.register_next_step_handler(msg, do_bc_app)
        elif q.data in ["ban_op", "unban_op"]:
            action = "لحظره" if q.data == "ban_op" else "لفك حظره"
            msg = bot.send_message(q.message.chat.id, f"ارسل المعرف {action}:")
            bot.register_next_step_handler(msg, process_ban_unban, q.data)

# --- [ وظائف الإدارة المضافة والمحدثة ] ---

def process_edit_ui(m):
    try:
        parts = m.text.split("|")
        if len(parts) < 4: return bot.send_message(m.chat.id, "⚠️ خطأ! يجب كتابة 4 أقسام مفصولة بـ |")
        
        db = load_db()
        db["ui_config"] = {
            "title": parts[0].strip(),
            "msg": parts[1].strip(),
            "btn_text": parts[2].strip(),
            "btn_link": parts[3].strip()
        }
        save_db(db)
        bot.send_message(m.chat.id, "✅ **تم تحديث واجهة التطبيق والنافذة فوراً!**")
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ حدث خطأ: {e}")

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    active_now = sum(1 for x in db["app_links"].values() if x.get("end_time", 0) > time.time())
    msg = (f"👑 **إدارة نجم الإبداع**\n\n"
           f"👥 المستخدمين: `{len(db['users'])}`\n"
           f"⚡ الأجهزة: `{len(db['app_links'])}`\n"
           f"🟢 النشطين: `{active_now}`\n")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🖼 تعديل نافذة التطبيق", callback_data="edit_ui"),
        types.InlineKeyboardButton("📋 قائمة المشتركين", callback_data="list_all"),
        types.InlineKeyboardButton("🎫 توليد كود", callback_data="gen_key"),
        types.InlineKeyboardButton("📢 إعلان تطبيق", callback_data="bc_app"),
        types.InlineKeyboardButton("🚫 حظر جهاز", callback_data="ban_op"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="unban_op")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- [ بقية وظائف المستخدم (كما هي في كودك) ] ---

def show_detailed_users(m):
    db = load_db()
    if not db["app_links"]: return bot.send_message(m.chat.id, "لا توجد أجهزة مسجلة.")
    full_list = "📂 **قائمة المشتركين:**\n\n"
    for cid, data in db["app_links"].items():
        rem_time = data.get("end_time", 0) - time.time()
        stat = "🔴 محظور" if data.get("banned") else ("🟢 نشط" if rem_time > 0 else "⚪ منتهي")
        full_list += f"🆔 `{cid}`\nالحالة: {stat}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    bot.send_message(m.chat.id, full_list, parse_mode="Markdown")

def process_gen_key(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "⚠️ رقم فقط!")
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db = load_db(); db["vouchers"][code] = int(m.text); save_db(db)
    bot.send_message(m.chat.id, f"🎫 كود: `{code}` لمدة {m.text} يوم")

def redeem_final(m):
    code, db = m.text.strip(), load_db()
    if code in db["vouchers"]:
        days = db["vouchers"].pop(code)
        cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
        if cid:
            db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (days * 86400)
            save_db(db); bot.send_message(m.chat.id, "✅ تم التفعيل!")
        else: bot.send_message(m.chat.id, "❌ اربط جهازك أولاً")
    else: bot.send_message(m.chat.id, "❌ كود خطأ")

def process_trial(m):
    db = load_db(); cid = db["users"].get(str(m.chat.id), {}).get("current_app")
    if cid and not db["app_links"][cid].get("trial_used"):
        db["app_links"][cid].update({"trial_used": True, "end_time": time.time() + 7200})
        save_db(db); bot.send_message(m.chat.id, "✅ تفعيل تجربة ساعتين")
    else: bot.send_message(m.chat.id, "❌ غير متاح")

def do_bc_app(m):
    db = load_db(); db["global_news"] = m.text; save_db(db)
    bot.send_message(m.chat.id, "✅ تم تحديث الخبر.")

def process_ban_unban(m, mode):
    db = load_db(); target = m.text.strip()
    if target in db["app_links"]:
        db["app_links"][target]["banned"] = (mode == "ban_op")
        save_db(db); bot.send_message(m.chat.id, "✅ تم التحديث.")

# --- [ تشغيل ] ---
def run(): app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
