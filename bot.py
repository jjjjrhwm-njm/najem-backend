import telebot
from telebot import types
import json, os, time, uuid
from flask import Flask, request, jsonify

# --- إعدادات أساسية ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401 # معرفك كمدير
DATA_FILE = "database.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- إدارة قاعدة البيانات ---
def load_db():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "config": {"mt": False, "msg": "أهلاً بكم", "ver": "1.0", "url": ""}}
    with open(DATA_FILE, "r") as f: return json.load(f)

def save_db(db):
    with open(DATA_FILE, "w") as f: json.dump(db, f, indent=4)

# --- بروتوكول الربط مع التطبيق (API) ---
@app.route('/api/check')
def check_user():
    aid = request.args.get('aid') # Android ID
    db = load_db()
    
    if aid not in db["users"]:
        db["users"][aid] = {"points": 0, "exp": 0, "banned": False, "ref_by": None}
        save_db(db)
    
    user = db["users"][aid]
    status = "EXPIRED"
    if user["banned"]: status = "BANNED"
    elif user["exp"] > time.time(): status = "PREMIUM"
    
    # ميزة "أدهشني": إرسال وقت الانتهاء المتبقي بدقة
    rem_days = max(0, int((user["exp"] - time.time()) / 86400))
    
    return jsonify({
        "status": status,
        "maintenance": db["config"]["mt"],
        "message": db["config"]["msg"],
        "version": db["config"]["ver"],
        "update_url": db["config"]["url"],
        "points": user["points"],
        "days_left": rem_days
    })

# --- أوامر البوت (Telegram) ---
@bot.message_handler(commands=['start'])
def start(m):
    # نظام الإحالة (دعوة الأصدقاء)
    args = m.text.split()
    db = load_db()
    uid = str(m.from_user.id)
    
    welcome_msg = "🌟 أهلاً بك في بوت نجم الإبداع\nأرسل 'كود' لفتح لوحة التحكم."
    bot.send_message(m.chat.id, welcome_msg)

@bot.message_handler(func=lambda m: m.text == "njm5")
def admin_panel(m):
    if m.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🛠 وضع الصيانة", callback_data="toggle_mt"))
    markup.add(types.InlineKeyboardButton("📢 إرسال رسالة للكل", callback_data="set_msg"))
    markup.add(types.InlineKeyboardButton("🆙 تحديث التطبيق", callback_data="set_ver"))
    bot.send_message(m.chat.id, "👑 لوحة المدير العليا:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "كود")
def user_panel(m):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👤 حسابي", "🎁 اشتراك مجاني")
    markup.add("💰 شراء اشتراك (100 نجوم)", "🔗 دعوة أصدقاء")
    bot.send_message(m.chat.id, "📱 لوحة التحكم الخاصة بك:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def my_account(m):
    # هنا يتم عرض النقاط وحالة الاشتراك
    bot.send_message(m.chat.id, f"🆔 معرفك: {m.from_user.id}\n💰 نقاطك: 0\n⏳ اشتراكك: منتهي")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    db = load_db()
    if call.data == "toggle_mt":
        db["config"]["mt"] = not db["config"]["mt"]
        save_db(db)
        bot.answer_callback_query(call.id, f"تم تغيير وضع الصيانة إلى: {db['config']['mt']}")

# --- تشغيل السيرفر ---
if __name__ == "__main__":
    # هذا الجزء لضمان عمل السيرفر على Render
    port = int(os.environ.get("PORT", 5000))
    from threading import Thread
    def run_bot(): bot.infinity_polling()
    Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=port)
