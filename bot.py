import telebot
from telebot import types
import json, os, time
from flask import Flask, request
from threading import Thread

# --- المنظومة مبرمجة ببياناتك الخاصة (جاهزة 100%) ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
CHANNEL_ID = "@nejm_njm"
DATA_FILE = "master_control.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- إدارة قاعدة البيانات اللحظية ---
def get_data():
    if not os.path.exists(DATA_FILE):
        return {
            "banned": [], 
            "config": {"mt": "0", "bc": "لا يوجد إعلانات حالياً", "ver": "1.0", "url": "https://t.me/nejm_njm"},
            "active": {}
        }
    try:
        with open(DATA_FILE, "r") as f: return json.load(f)
    except:
        return {"banned": [], "config": {"mt": "0", "bc": "لا يوجد إعلانات", "ver": "1.0", "url": "https://t.me/nejm_njm"}, "active": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f: json.dump(data, f, indent=4)

# --- بروتوكول الربط مع التطبيق (API) ---
@app.route('/check')
def check():
    aid = request.args.get('aid', 'unknown')
    db = get_data()
    
    # تسجيل دخول المستخدم (الرادار)
    db["active"][aid] = time.time()
    save_data(db)
    
    # التحقق من الحظر
    if aid in db["banned"]: return "STATUS:BANNED"
    
    # إرسال بيانات التحكم (صيانة|إذاعة|نسخة|رابط)
    res = f"MT:{db['config']['mt']}|BC:{db['config']['bc']}|VER:{db['config']['ver']}|URL:{db['config']['url']}"
    return res

# --- لوحة التحكم العليا (Telegram) ---
@bot.message_handler(commands=['start'])
def welcome(m):
    if m.from_user.id != ADMIN_ID:
        return bot.reply_to(m, "❌ أنت لست المدير المخول.")
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 إحصائيات المتصلين", "🛠 وضع الصيانة")
    markup.add("📢 نشر إذاعة", "🆙 تحديث التطبيق")
    markup.add("🚫 حظر جهاز", "✅ فك حظر")
    bot.send_message(m.chat.id, "👑 أهلاً بك يا مدير **نجم الإبداع**.\nالمنظومة متصلة والتطبيق تحت سيطرتك الآن.", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📊 إحصائيات المتصلين")
def stats(m):
    db = get_data()
    # جرد المستخدمين النشطين في آخر دقيقة
    online_count = len([t for t in db["active"].values() if time.time() - t < 60])
    bot.send_message(m.chat.id, f"👥 **المستخدمين المتواجدين الآن:** `{online_count}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🛠 وضع الصيانة")
def toggle_mt(m):
    db = get_data()
    db["config"]["mt"] = "1" if db["config"]["mt"] == "0" else "0"
    save_data(db)
    status = "🟢 تفعيل الصيانة (التطبيق مغلق)" if db["config"]["mt"] == "1" else "🔴 إيقاف الصيانة (التطبيق مفتوح)"
    bot.send_message(m.chat.id, f"⚙️ {status}")

@bot.message_handler(func=lambda m: m.text == "📢 نشر إذاعة")
def bc_ask(m):
    msg = bot.send_message(m.chat.id, "✍️ أرسل الإعلان الذي سيظهر للمستخدمين فوراً:")
    bot.register_next_step_handler(msg, bc_save)

def bc_save(m):
    db = get_data()
    db["config"]["bc"] = m.text
    save_data(db)
    bot.send_message(m.chat.id, "✅ تم تحديث الإذاعة بنجاح.")

@bot.message_handler(func=lambda m: m.text == "🚫 حظر جهاز")
def ban_ask(m):
    msg = bot.send_message(m.chat.id, "🆔 أرسل الـ Android ID للجهاز المطلوب طرده:")
    bot.register_next_step_handler(msg, ban_save)

def ban_save(m):
    db = get_data()
    db["banned"].append(m.text.strip())
    save_data(db)
    bot.send_message(m.chat.id, "🚫 تم حظر الجهاز. لن يتمكن من فتح التطبيق ثانية.")

# --- تشغيل المحرك ---
def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    print("NJM MASTER CORE IS RUNNING...")
    bot.infinity_polling()
