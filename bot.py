import telebot
from telebot import types
from flask import Flask, request
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
            return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً"}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: 
                db = json.load(f)
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً"}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4) 

# --- [ واجهة API للتطبيقات ] ---
@app.route('/check')
def check_status():
    aid, pkg = request.args.get('aid'), request.args.get('pkg')
    if not aid or not pkg: return "EXPIRED"
    uid = f"{aid}_{pkg.replace('.', '_')}"
    db = load_db()
    data = db["app_links"].get(uid)
    if not data: return "EXPIRED"
    if data.get("banned"): return "BANNED"
    if time.time() > data.get("end_time", 0): return "EXPIRED"
    return "ACTIVE" 

@app.route('/get_news') 
def get_news():
    return load_db().get("global_news", "لا توجد أخبار")

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
        bot.send_message(m.chat.id, "✅ **تم ربط الجهاز الجديد بنجاح!**", parse_mode="Markdown")

    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add("📱 تطبيقاتي ورصيدي", "🎫 تفعيل كود")
    menu.add("🎁 تجربة مجانية", "🛒 شراء اشتراك")
    bot.send_message(m.chat.id, f"مرحباً بك يا **نجم الإبداع** في لوحة التحكم الخاصة بك.", reply_markup=menu, parse_mode="Markdown")

# --- [ لوحة المستخدم النصية (كشف الحساب) ] ---
@bot.message_handler(func=lambda m: m.text == "📱 تطبيقاتي ورصيدي")
def user_dashboard(m):
    db = load_db()
    uid = str(m.from_user.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    
    if not user_apps:
        return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة بحسابك حالياً.")
    
    msg = "👤 **لوحة اشتراكاتك الشخصية**\n"
    msg += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    
    for cid in user_apps:
        data = db["app_links"][cid]
        pkg_name = cid.split('_', 1)[-1].replace("_", ".")
        rem_time = data.get("end_time", 0) - time.time()
        
        if data.get("banned"): status = "🚫 محظور"
        elif rem_time > 0:
            days = int(rem_time / 86400)
            hours = int((rem_time % 86400) / 3600)
            status = f"✅ نشط (متبقي {days} يوم و {hours} ساعة)"
        else: status = "❌ منتهي"
        
        msg += f"📦 **التطبيق:** `{pkg_name}`\n"
        msg += f"Status: {status}\n"
        msg += f"ID: `{cid}`\n"
        msg += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

# --- [ لوحة المدير الاحترافية - نجم1 ] ---
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    active_now = sum(1 for x in db["app_links"].values() if x.get("end_time", 0) > time.time())
    msg = (f"👑 **إدارة نجم الإبداع العلويّة**\n\n"
           f"👥 إجمالي المستخدمين: `{len(db['users'])}`\n"
           f"⚡ أجهزة مرتبطة: `{len(db['app_links'])}`\n"
           f"🟢 اشتراكات نشطة: `{active_now}`\n"
           f"🎫 أكواد جاهزة: `{len(db['vouchers'])}`")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 عرض كل المستخدمين", callback_data="list_all"),
        types.InlineKeyboardButton("🎫 توليد كود", callback_data="gen_key"),
        types.InlineKeyboardButton("🚫 حظر", callback_data="ban_op"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="unban_op"),
        types.InlineKeyboardButton("📢 إذاعة (تطبيق)", callback_data="bc_app"),
        types.InlineKeyboardButton("📢 إذاعة (تلجرام)", callback_data="bc_tele")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda q: True)
def admin_logic(q):
    if q.from_user.id != ADMIN_ID: return
    
    if q.data == "list_all":
        db = load_db()
        if not db["app_links"]: return bot.send_message(q.message.chat.id, "قاعدة البيانات فارغة.")
        
        full_list = "📂 **كافة المستخدمين والأجهزة:**\n\n"
        for cid, data in db["app_links"].items():
            pkg = cid.split('_', 1)[-1].replace("_", ".")
            u_id = data.get("telegram_id", "غير معروف")
            stat = "🔴" if data.get("banned") else ("🟢" if data.get("end_time", 0) > time.time() else "⚪")
            full_list += f"{stat} `{cid}`\n👤 المستخدم: `{u_id}`\n📦 التطبيق: `{pkg}`\n\n"
            if len(full_list) > 3500: # تجنب خطأ طول الرسالة
                bot.send_message(q.message.chat.id, full_list, parse_mode="Markdown")
                full_list = ""
        bot.send_message(q.message.chat.id, full_list, parse_mode="Markdown")

    elif q.data in ["ban_op", "unban_op"]:
        action = "لحظره" if q.data == "ban_op" else "لفك حظره"
        msg = bot.send_message(q.message.chat.id, f"ارسل المعرف (AID_PKG) {action}:")
        bot.register_next_step_handler(msg, process_ban_unban, q.data)

    elif q.data == "gen_key":
        code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
        db = load_db(); db["vouchers"][code] = 30; save_db(db)
        bot.send_message(q.message.chat.id, f"🎫 كود 30 يوم جاهز:\n`{code}`", parse_mode="Markdown")

def process_ban_unban(m, mode):
    db = load_db(); target = m.text.strip()
    if target in db["app_links"]:
        db["app_links"][target]["banned"] = (mode == "ban_op")
        save_db(db)
        status = "محظور الآن 🚫" if mode == "ban_op" else "نشط الآن ✅"
        bot.send_message(m.chat.id, f"تم التحديث: `{target}` أصبح {status}", parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, "❌ المعرف غير موجود.")

# --- [ بقية الوظائف المدمجة ] ---
@bot.message_handler(func=lambda m: m.text == "🎫 تفعيل كود")
def redeem_start(m):
    msg = bot.send_message(m.chat.id, "أرسل كود التفعيل:")
    bot.register_next_step_handler(msg, redeem_final)

def redeem_final(m):
    code, db = m.text.strip(), load_db()
    if code in db["vouchers"]:
        days = db["vouchers"].pop(code)
        cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
        if cid:
            db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (days * 86400)
            save_db(db); bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم!")
        else: bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    else: bot.send_message(m.chat.id, "❌ كود خطأ.")

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية")
def trial(m):
    db = load_db(); cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    if db["app_links"][cid].get("trial_used"): bot.send_message(m.chat.id, "❌ استخدمت التجربة سابقاً.")
    else:
        db["app_links"][cid].update({"trial_used": True, "end_time": time.time() + 7200})
        save_db(db); bot.send_message(m.chat.id, "✅ تم تفعيل ساعتين تجربة!")

# --- [ تشغيل النظام ] ---
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
