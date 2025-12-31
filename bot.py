import json, os, time
from flask import Flask, request
from threading import Thread
from datetime import datetime, timedelta
import telebot

# --- إعدادات البوت ---
API_TOKEN = 'ضع_توكنك_هنا'
ADMIN_ID = 7650083401
DATA_FILE = "master_control.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- إدارة قاعدة البيانات ---
def get_data():
    if not os.path.exists(DATA_FILE):
        return {
            "banned": [],
            "users": {},
            "config": {
                "mt": "0",  # 0: مفتوح، 1: صيانة
                "bc": "لا يوجد إعلانات حالياً",
                "ver": "1.0",
                "url": "https://example.com/update.apk"
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
    
    # تسجيل دخول المستخدم
    db["users"].setdefault(aid, {"last_seen": time.time(), "points":0, "plan": "free", "expiry": time.time()+86400})
    db["users"][aid]["last_seen"] = time.time()
    
    # التحقق من الحظر
    if aid in db["banned"]:
        return "STATUS:BANNED"
    
    # التحقق من الصيانة
    mt = db["config"]["mt"]
    bc = db["config"]["bc"]
    ver = db["config"]["ver"]
    url = db["config"]["url"]

    # بيانات الاشتراك
    user = db["users"][aid]
    plan = user.get("plan", "free")
    expiry = int(user.get("expiry", time.time()))
    points = user.get("points", 0)

    res = f"MT:{mt}|BC:{bc}|VER:{ver}|URL:{url}|PLAN:{plan}|EXP:{expiry}|POINTS:{points}"
    save_data(db)
    return res

# --- البوت ---
@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id != ADMIN_ID:
        return bot.reply_to(m, "❌ أنت لست المدير المخول.")
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 إحصائيات المتصلين", "🛠 وضع الصيانة")
    markup.add("📢 نشر إذاعة", "🆙 تحديث التطبيق")
    markup.add("🚫 حظر جهاز", "✅ فك حظر")
    markup.add("🎁 إدارة الاشتراكات", "⭐ إدارة النقاط")
    bot.send_message(m.chat.id, "👑 أهلاً بك يا مدير", reply_markup=markup)

# --- إحصائيات ---
@bot.message_handler(func=lambda m: m.text == "📊 إحصائيات المتصلين")
def stats(m):
    db = get_data()
    online_count = len([t for t in db["users"].values() if time.time() - t["last_seen"] < 60])
    bot.send_message(m.chat.id, f"👥 المتصلين الآن: {online_count}")

# --- الصيانة ---
@bot.message_handler(func=lambda m: m.text == "🛠 وضع الصيانة")
def toggle_mt(m):
    db = get_data()
    db["config"]["mt"] = "1" if db["config"]["mt"] == "0" else "0"
    save_data(db)
    status = "🟢 التفعيل (التطبيق مغلق)" if db["config"]["mt"] == "1" else "🔴 الإيقاف (التطبيق مفتوح)"
    bot.send_message(m.chat.id, f"⚙️ {status}")

# --- نشر إذاعة ---
@bot.message_handler(func=lambda m: m.text == "📢 نشر إذاعة")
def bc_ask(m):
    msg = bot.send_message(m.chat.id, "✍️ أرسل الإعلان للمستخدمين:")
    bot.register_next_step_handler(msg, bc_save)

def bc_save(m):
    db = get_data()
    db["config"]["bc"] = m.text
    save_data(db)
    bot.send_message(m.chat.id, "✅ تم تحديث الإعلان.")

# --- حظر وفك حظر ---
@bot.message_handler(func=lambda m: m.text == "🚫 حظر جهاز")
def ban_ask(m):
    msg = bot.send_message(m.chat.id, "🆔 أدخل Android ID للجهاز:")
    bot.register_next_step_handler(msg, ban_save)

def ban_save(m):
    db = get_data()
    db["banned"].append(m.text.strip())
    save_data(db)
    bot.send_message(m.chat.id, "🚫 تم حظر الجهاز.")

@bot.message_handler(func=lambda m: m.text == "✅ فك حظر")
def unban_ask(m):
    msg = bot.send_message(m.chat.id, "🆔 أدخل Android ID لفك الحظر:")
    bot.register_next_step_handler(msg, unban_save)

def unban_save(m):
    db = get_data()
    if m.text.strip() in db["banned"]:
        db["banned"].remove(m.text.strip())
        save_data(db)
        bot.send_message(m.chat.id, "✅ تم فك الحظر.")
    else:
        bot.send_message(m.chat.id, "❌ هذا الجهاز غير محظور.")

# --- إدارة الاشتراكات ---
@bot.message_handler(func=lambda m: m.text == "🎁 إدارة الاشتراكات")
def manage_plan(m):
    msg = bo
