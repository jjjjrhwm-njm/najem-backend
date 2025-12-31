import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread, Lock

API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock()

def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): return {"users": {}, "app_links": {}, "vouchers": {}}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {"users": {}, "app_links": {}, "vouchers": {}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4)

@app.route('/check')
def check_status():
    aid = request.args.get('aid')
    db = load_db()
    user_data = db["app_links"].get(aid)
    if not user_data or time.time() > user_data.get("end_time", 0): return "EXPIRED"
    if user_data.get("banned"): return "BANNED"
    return "ACTIVE"

@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    args = m.text.split()
    
    if uid not in db["users"]: db["users"][uid] = {"app_id": None}
    
    # ربط تلقائي عند الدخول من التطبيق
    if len(args) > 1:
        aid = args[1]
        db["app_links"][aid] = db["app_links"].get(aid, {"end_time": 0, "banned": False, "trial_used": False, "telegram_id": uid})
        db["app_links"][aid]["telegram_id"] = uid
        db["users"][uid]["app_id"] = aid
        save_db(db)
        bot.send_message(m.chat.id, f"✅ **تم ربط جهازك تلقائياً!**\nمعرفك: `{aid}`", parse_mode="Markdown")

    main_menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    main_menu.add("🎁 تجربة مجانية (24س)", "🎫 تفعيل كود")
    main_menu.add("📊 حالتي", "🛒 شراء اشتراك")
    bot.send_message(m.chat.id, "أهلاً بك في بوت **نجم الإبداع**. اختر من القائمة أدناه:", reply_markup=main_menu, parse_mode="Markdown")

# --- [ قسم المستخدم ] ---
@bot.message_handler(func=lambda m: m.text == "📊 حالتي")
def my_status(m):
    db = load_db()
    uid = str(m.from_user.id)
    aid = db["users"].get(uid, {}).get("app_id")
    if not aid: return bot.send_message(m.chat.id, "❌ لم يتم ربط أي جهاز بعد. ادخل من التطبيق.")
    
    status = db["app_links"].get(aid, {})
    rem = max(0, int((status.get("end_time", 0) - time.time()) / 3600)) # بالساعات
    bot.send_message(m.chat.id, f"👤 معرف الجهاز: `{aid}`\n⏳ المتبقي: {rem} ساعة.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية (24س)")
def free_trial(m):
    db = load_db()
    uid = str(m.from_user.id)
    aid = db["users"].get(uid, {}).get("app_id")
    if not aid: return bot.send_message(m.chat.id, "❌ اربط جهازك أولاً (ادخل من التطبيق).")
    
    if db["app_links"][aid].get("trial_used"):
        bot.send_message(m.chat.id, "❌ لقد استخدمت الفترة التجريبية سابقاً.")
    else:
        db["app_links"][aid]["trial_used"] = True
        db["app_links"][aid]["end_time"] = time.time() + 86400
        save_db(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل 24 ساعة مجانية!")

# --- [ لوحة المدير الاحترافية ] ---
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_pnl(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎫 توليد كود اشتراك", callback_data="gen_code"))
    markup.add(types.InlineKeyboardButton("🚫 حظر جهاز", callback_data="ban_ui"), types.InlineKeyboardButton("🟢 فك حظر", callback_data="unban_ui"))
    bot.send_message(m.chat.id, "👑 **لوحة تحكم المدير**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda q: True)
def calls(q):
    if q.data == "gen_code":
        code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
        db = load_db()
        db["vouchers"][code] = 30 # افتراضياً 30 يوم
        save_db(db)
        bot.edit_message_text(f"🎫 كود جديد (30 يوم):\n`{code}`", q.message.chat.id, q.message.message_id, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎫 تفعيل كود")
def redeem_init(m):
    msg = bot.send_message(m.chat.id, "أرسل كود التفعيل الذي حصلت عليه:")
    bot.register_next_step_handler(msg, redeem_done)

def redeem_done(m):
    code = m.text.strip()
    db = load_db()
    if code in db["vouchers"]:
        days = db["vouchers"].pop(code)
        uid = str(m.from_user.id)
        aid = db["users"].get(uid, {}).get("app_id")
        if aid:
            db["app_links"][aid]["end_time"] = max(time.time(), db["app_links"][aid]["end_time"]) + (days * 86400)
            save_db(db)
            bot.send_message(m.chat.id, f"✅ تم تفعيل اشتراكك لمدة {days} يوم!")
        else: bot.send_message(m.chat.id, "❌ اربط جهازك أولاً.")
    else: bot.send_message(m.chat.id, "❌ كود غير صحيح أو مستخدم.")

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
