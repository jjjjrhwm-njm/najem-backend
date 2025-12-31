import telebot
from telebot import types
from flask import Flask, request
import json, os, time
from threading import Thread

# --- إعدادات البوت ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_control.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- إدارة قاعدة البيانات ---
def get_data():
    if not os.path.exists(DATA_FILE):
        return {
            "users": {},
            "config": {
                "maintenance": False,
                "announcement": "لا يوجد إعلانات حالياً",
                "latest_version": "1.0",
                "update_url": "https://t.me/nejm_njm"
            }
        }
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- API للتطبيق ---
@app.route('/check')
def check():
    aid = request.args.get('aid', 'unknown')
    db = get_data()

    if aid not in db['users']:
        db['users'][aid] = {
            "subscription_type": "free",
            "start_time": time.time(),
            "end_time": time.time() + 86400,
            "points": 0,
            "banned": False
        }
        save_data(db)

    user = db['users'][aid]

    if user['banned']:
        return "STATUS:BANNED"

    maintenance = db['config']['maintenance']
    latest_version = db['config']['latest_version']
    update_url = db['config']['update_url']

    now = time.time()
    if now > user['end_time']:
        user['subscription_type'] = "free"
        save_data(db)

    return f"MT:{int(maintenance)}|BC:{db['config']['announcement']}|VER:{latest_version}|URL:{update_url}|SUB:{user['subscription_type']}|POINTS:{user['points']}"

# --- إدارة أوامر المدير ---
def is_admin(m):
    return m.from_user.id == ADMIN_ID

@bot.message_handler(commands=['start'])
def start_cmd(m):
    if is_admin(m):
        admin_panel(m)
    else:
        bot.send_message(m.chat.id,
            "👋 مرحباً، لإظهار القائمة أرسل كلمة: كود\n💎 للحصول على اشتراك أو ميزات أخرى.")

# --- لوحة المدير ---
def admin_panel(m):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 إحصائيات المتصلين", "🛠 وضع الصيانة")
    markup.add("📢 نشر إذاعة", "🆙 تحديث التطبيق")
    markup.add("🚫 حظر جهاز", "✅ فك حظر")
    markup.add("🎁 إهداء اشتراك")
    bot.send_message(m.chat.id, "👑 أهلاً بك يا مدير.\nالمنظومة متصلة والتطبيق تحت سيطرتك الآن.", reply_markup=markup)

# --- إدارة أوامر المستخدم ---
@bot.message_handler(func=lambda m: m.text.lower() == "كود")
def user_panel(m):
    db = get_data()
    aid = str(m.from_user.id)
    user = db['users'].setdefault(aid, {
        "subscription_type": "free",
        "start_time": time.time(),
        "end_time": time.time() + 86400,
        "points": 0,
        "banned": False
    })
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("💎 شراء اشتراك 100 نجمة", "🎁 اشتراك تجريبي يوم واحد")
    keyboard.add("⭐ جمع نقاط / دعوة أصدقاء", "📊 عرض بياناتي")
    bot.send_message(m.chat.id, "📋 اختر ما تريد من ميزات المستخدم:", reply_markup=keyboard)

# --- عمليات المستخدم ---
@bot.message_handler(func=lambda m: True)
def handle_user(m):
    db = get_data()
    aid = str(m.from_user.id)
    user = db['users'].setdefault(aid, {
        "subscription_type": "free",
        "start_time": time.time(),
        "end_time": time.time() + 86400,
        "points": 0,
        "banned": False
    })

    text = m.text
    if text == "💎 شراء اشتراك 100 نجمة":
        bot.send_message(m.chat.id, "💰 افتح الرابط لشراء الاشتراك: https://t.me/nejm_njm_bot?start=pay100stars")
    elif text == "🎁 اشتراك تجريبي يوم واحد":
        user["subscription_type"] = "free"
        user["start_time"] = time.time()
        user["end_time"] = time.time() + 86400
        save_data(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل الاشتراك التجريبي ليوم واحد")
    elif text == "⭐ جمع نقاط / دعوة أصدقاء":
        bot.send_message(m.chat.id, "📌 ادعُ صديقين واكسب 3 أيام اشتراك مجاناً")
    elif text == "📊 عرض بياناتي":
        sub = user["subscription_type"]
        points = user["points"]
        bot.send_message(m.chat.id, f"💎 نوع الاشتراك: {sub}\n⭐ نقاطك: {points}")
    elif is_admin(m):
        admin_panel(m)
    else:
        bot.send_message(m.chat.id, "❌ أرسل كلمة: كود لإظهار ميزات المستخدم")

# --- تشغيل Flask و البوت ---
def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    print("MASTER CORE IS RUNNING...")
    bot.infinity_polling()
