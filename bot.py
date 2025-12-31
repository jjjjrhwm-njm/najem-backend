import telebot
from telebot import types
import json, os, time
from flask import Flask, request
from threading import Thread

# --- الإعدادات (ضع توكن بوتك ومعرفك هنا) ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_control.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- إدارة البيانات ---
def get_data():
    if not os.path.exists(DATA_FILE):
        return {
            "banned": [], 
            "config": {"mt": "0", "bc": "لا يوجد إعلانات", "ver": "1.0", "url": "https://t.me/nejm_njm"},
            "active": {}
        }
    with open(DATA_FILE, "r") as f: return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f: json.dump(data, f, indent=4)

# --- API الاحترافي (بروتوكول النص السريع) ---
@app.route('/check')
def check():
    aid = request.args.get('aid', 'unknown')
    db = get_data()
    
    # تسجيل النشاط اللحظي
    db["active"][aid] = time.time()
    save_data(db)
    
    # فحص الحظر
    if aid in db["banned"]: return "BAN:1"
    
    # إرسال الحالة الكاملة (MT|BC|VER|URL)
    # MT: الصيانة (0 أو 1)، BC: الإذاعة، VER: النسخة، URL: رابط التحديث
    res = f"MT:{db['config']['mt']}|BC:{db['config']['bc']}|VER:{db['config']['ver']}|URL:{db['config']['url']}"
    return res

# --- لوحة التحكم (البوت) ---
@bot.message_handler(commands=['start'])
def welcome(m):
    if m.from_user.id != ADMIN_ID: return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 الإحصائيات", "🛠 الصيانة", "📢 إذاعة")
    markup.add("🚫 حظر جهاز", "✅ فك حظر", "🆙 تحديث")
    bot.send_message(m.chat.id, "👑 مرحباً بك يا مدير نجم الإبداع. المنظومة جاهزة.", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📊 الإحصائيات")
def stats(m):
    db = get_data()
    # تنظيف المتصلين (من لم يتصل منذ دقيقة نعتبره غير متصل)
    online = [t for t in db["active"].values() if time.time() - t < 60]
    bot.send_message(m.chat.id, f"👥 عدد المتصلين الآن: `{len(online)}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🛠 الصيانة")
def toggle_mt(m):
    db = get_data()
    db["config"]["mt"] = "1" if db["config"]["mt"] == "0" else "0"
    save_data(db)
    status = "شغالة 🟢" if db["config"]["mt"] == "1" else "متوقفة 🔴"
    bot.send_message(m.chat.id, f"⚙️ وضع الصيانة الآن: {status}")

@bot.message_handler(func=lambda m: m.text == "📢 إذاعة")
def bc_ask(m):
    msg = bot.send_message(m.chat.id, "✍️ أرسل الإذاعة (ستظهر للجميع فوراً):")
    bot.register_next_step_handler(msg, bc_save)

def bc_save(m):
    db = get_data()
    db["config"]["bc"] = m.text
    save_data(db)
    bot.send_message(m.chat.id, "✅ تم تحديث رسالة الإذاعة في كل التطبيقات.")

@bot.message_handler(func=lambda m: m.text == "🚫 حظر جهاز")
def ban_ask(m):
    msg = bot.send_message(m.chat.id, "🆔 أرسل الـ Android ID للحظر:")
    bot.register_next_step_handler(msg, ban_save)

def ban_save(m):
    db = get_data()
    db["banned"].append(m.text.strip())
    save_data(db)
    bot.send_message(m.chat.id, "🚫 تم حظر الجهاز بنجاح.")

# --- تشغيل السيرفر ---
def run_api(): app.run(host='0.0.0.0', port=8080)
if __name__ == "__main__":
    Thread(target=run_api).start()
    bot.infinity_polling()
