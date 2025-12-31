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

# --- التعامل مع الرسائل ---
@bot.message_handler(func=lambda m: True)
def handle_messages(m):
    aid = str(m.from_user.id)

    # --- لوحة المدير ---
    if m.text.strip().lower() == "نجم1" and m.from_user.id == ADMIN_ID:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("📊 إحصائيات المتصلين", "🛠 وضع الصيانة")
        markup.add("📢 نشر إذاعة", "🆙 تحديث التطبيق")
        markup.add("🚫 حظر جهاز", "✅ فك حظر")
        markup.add("🎁 إهداء اشتراك")
        bot.send_message(m.chat.id, "👑 أهلاً بك يا مدير.\nالمنظومة متصلة والتطبيق تحت سيطرتك الآن.", reply_markup=markup)
        return

    # --- واجهة المستخدم العادية ---
    if m.text.strip().lower() == "كود":
        db = get_data()
        db["users"].setdefault(aid, {
            "subscription_type": "free",
            "start_time": time.time(),
            "end_time": time.time() + 86400,
            "points": 0,
            "banned": False
        })
        save_data(db)
        user = db["users"][aid]

        # --- إنشاء لوحة أزرار المستخدم ---
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("💎 شراء اشتراك 100 نجمة")
        markup.add("🎁 اشتراك تجريبي يوم واحد")
        markup.add("⭐ جمع نقاط / دعوة أصدقاء")
        markup.add("📊 عرض بياناتي")

        bot.send_message(m.chat.id, f"🎉 مرحباً بك! ميزات حسابك:\n- نوع الاشتراك: {user['subscription_type']}\n- نقاطك: {user['points']}\n\nاختر خيار من الأسفل:", reply_markup=markup)
        return

    # --- أي رسالة أخرى للمستخدم العادي ---
    if m.from_user.id != ADMIN_ID:
        bot.send_message(m.chat.id, "مرحبًا! أرسل كلمة 'كود' للحصول على قائمة ميزاتك.")
        return

# --- لوحة مدير الزر ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def admin_buttons(m):
    db = get_data()
    if m.text == "📊 إحصائيات المتصلين":
        online_count = len([t for t in db["users"].values() if time.time() - t["start_time"] < 60])
        bot.send_message(m.chat.id, f"👥 المستخدمين المتواجدين الآن: {online_count}")
    elif m.text == "🛠 وضع الصيانة":
        db["config"]["maintenance"] = not db["config"]["maintenance"]
        save_data(db)
        status = "🟢 تفعيل الصيانة" if db["config"]["maintenance"] else "🔴 إيقاف الصيانة"
        bot.send_message(m.chat.id, f"⚙️ {status}")
    elif m.text == "📢 نشر إذاعة":
        msg = bot.send_message(m.chat.id, "✍️ أرسل الإعلان:")
        bot.register_next_step_handler(msg, bc_save)
    elif m.text == "🚫 حظر جهاز":
        msg = bot.send_message(m.chat.id, "🆔 أرسل Android ID:")
        bot.register_next_step_handler(msg, ban_save)
    elif m.text == "✅ فك حظر":
        msg = bot.send_message(m.chat.id, "🆔 أرسل Android ID لفك الحظر:")
        bot.register_next_step_handler(msg, unban_save)
    elif m.text == "🎁 إهداء اشتراك":
        msg = bot.send_message(m.chat.id, "🆔 أرسل Android ID وعدد الأيام (مثال: 7650083401 7):")
        bot.register_next_step_handler(msg, gift_subscription)

# --- دوال البوت ---
def bc_save(m):
    db = get_data()
    db["config"]["announcement"] = m.text
    save_data(db)
    bot.send_message(m.chat.id, "✅ تم تحديث الإذاعة.")

def ban_save(m):
    db = get_data()
    db["users"].setdefault(m.text.strip(), {"banned": True})
    db["users"][m.text.strip()]["banned"] = True
    save_data(db)
    bot.send_message(m.chat.id, "🚫 تم حظر الجهاز.")

def unban_save(m):
    db = get_data()
    if m.text.strip() in db["users"]:
        db["users"][m.text.strip()]["banned"] = False
        save_data(db)
        bot.send_message(m.chat.id, "✅ تم فك الحظر.")
    else:
        bot.send_message(m.chat.id, "❌ لم أجد هذا المستخدم.")

def gift_subscription(m):
    try:
        parts = m.text.split()
        aid = parts[0]
        days = int(parts[1])
        db = get_data()
        user = db["users"].setdefault(aid, {
            "subscription_type": "gifted",
            "start_time": time.time(),
            "end_time": time.time() + days*86400,
            "points": 0,
            "banned": False
        })
        user["subscription_type"] = "gifted"
        user["start_time"] = time.time()
        user["end_time"] = time.time() + days*86400
        save_data(db)
        bot.send_message(m.chat.id, f"🎁 تم منح {days} يوم اشتراك لـ {aid}")
    except:
        bot.send_message(m.chat.id, "❌ خطأ في الصيغة.")

# --- تشغيل Flask و البوت ---
def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    print("MASTER CORE IS RUNNING...")
    bot.infinity_polling()
