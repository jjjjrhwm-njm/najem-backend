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
            "end_time": time.time() + 86400,  # يوم مجاني مرة واحدة
            "points": 0,
            "banned": False,
            "trial_used": True
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

# --- رسائل المستخدم ---
def user_intro_message(aid):
    return ("👋 أهلاً بك!\n"
            "للحصول على اشتراك مجاني أو فتح الميزات، أرسل كلمة: كود\n"
            "لتجميع النقاط، ادعُ صديقك وستحصل على 3 أيام اشتراك")

# --- التعامل مع /start ---
@bot.message_handler(commands=['start'])
def start(m):
    if m.from_user.id == ADMIN_ID:
        admin_panel(m)
    else:
        bot.send_message(m.chat.id, user_intro_message(m.from_user.id))

# --- لوحة المدير ---
def admin_panel(m):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 إحصائيات المتصلين", "🛠 وضع الصيانة")
    markup.add("📢 نشر إذاعة", "🆙 تحديث التطبيق")
    markup.add("🚫 حظر جهاز", "✅ فك حظر")
    markup.add("🎁 إهداء اشتراك")
    bot.send_message(m.chat.id, "👑 أهلاً بك يا مدير.\nالمنظومة متصلة والتطبيق تحت سيطرتك الآن.", reply_markup=markup)

# --- التعامل مع الأزرار ---
@bot.message_handler(func=lambda m: True)
def handle_text(m):
    text = m.text.strip().lower()
    if text == "كود":
        offer_user_features(m)
    elif m.from_user.id == ADMIN_ID:
        handle_admin_buttons(m)
    else:
        bot.send_message(m.chat.id, "📌 أرسل كلمة: كود للحصول على الميزات.")

# --- ميزات المستخدم عند إرسال كود ---
def offer_user_features(m):
    aid = str(m.from_user.id)
    db = get_data()
    user = db['users'].setdefault(aid, {"subscription_type":"free", "start_time":time.time(),
                                        "end_time":time.time()+86400, "points":0, "banned":False, "trial_used":False})
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💎 شراء اشتراك 100 نجمة", "🎯 تجميع نقاط", "🎁 الاشتراك التجريبي")
    bot.send_message(m.chat.id, f"✨ ميزاتك:\nاشتراك: {user['subscription_type']}\nنقاط: {user['points']}", reply_markup=markup)

# --- زر شراء اشتراك مدفوع ---
@bot.message_handler(func=lambda m: m.text == "💎 شراء اشتراك 100 نجمة")
def buy_subscription(m):
    # رابط دفع رسمي داخل التليجرام (Telegram Payments)
    prices = [telebot.types.LabeledPrice(label='اشتراك شهر', amount=800)]  # 8 ريال = 800 هللة
    bot.send_invoice(m.chat.id, title="اشتراك شهري", description="اشتراك شهر كامل داخل التطبيق", provider_token="YOUR_PROVIDER_TOKEN", currency="SAR", prices=prices, start_parameter="monthly-subscription", payload="monthly")

# --- الاشتراك التجريبي (مرة واحدة لكل جهاز) ---
@bot.message_handler(func=lambda m: m.text == "🎁 الاشتراك التجريبي")
def trial_subscription(m):
    aid = str(m.from_user.id)
    db = get_data()
    user = db['users'].setdefault(aid, {"subscription_type":"free", "start_time":time.time(),
                                        "end_time":time.time()+86400, "points":0, "banned":False, "trial_used":False})
    if user.get("trial_used", False):
        bot.send_message(m.chat.id, "❌ لقد استخدمت الاشتراك التجريبي مسبقاً.")
    else:
        user["subscription_type"] = "trial"
        user["start_time"] = time.time()
        user["end_time"] = time.time() + 86400
        user["trial_used"] = True
        save_data(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل الاشتراك التجريبي لمدة يوم واحد.")

# --- تجميع النقاط ---
@bot.message_handler(func=lambda m: m.text == "🎯 تجميع نقاط")
def points_info(m):
    aid = str(m.from_user.id)
    db = get_data()
    user = db['users'].setdefault(aid, {"points":0})
    bot.send_message(m.chat.id, f"📌 نقاطك الحالية: {user['points']}\nادعُ صديقك للحصول على نقاط إضافية.")

# --- دفع الاشتراك الفعلي ---
@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(m):
    aid = str(m.from_user.id)
    db = get_data()
    user = db['users'].setdefault(aid, {"subscription_type":"free", "start_time":time.time(),
                                        "end_time":time.time(), "points":0, "banned":False, "trial_used":False})
    user["subscription_type"] = "paid"
    user["start_time"] = time.time()
    user["end_time"] = time.time() + 30*86400
    save_data(db)
    bot.send_message(m.chat.id, "✅ تم تفعيل اشتراكك الشهري بنجاح!")

# --- التعامل مع أزرار المدير ---
def handle_admin_buttons(m):
    db = get_data()
    if m.text == "📊 إحصائيات المتصلين":
        online_count = len([t for t in db["users"].values() if time.time() - t["start_time"] < 60])
        bot.send_message(m.chat.id, f"👥 المتواجدين الآن: {online_count}")
    elif m.text == "🛠 وضع الصيانة":
        db["config"]["maintenance"] = not db["config"]["maintenance"]
        save_data(db)
        status = "🟢 تفعيل الصيانة" if db["config"]["maintenance"] else "🔴 إيقاف الصيانة"
        bot.send_message(m.chat.id, status)
    elif m.text == "📢 نشر إذاعة":
        msg = bot.send_message(m.chat.id, "✍️ أرسل الإعلان:")
        bot.register_next_step_handler(msg, lambda m2: save_announcement(m2))
    elif m.text == "🚫 حظر جهاز":
        msg = bot.send_message(m.chat.id, "🆔 أرسل Android ID للحظر:")
        bot.register_next_step_handler(msg, lambda m2: ban_user(m2))
    elif m.text == "✅ فك حظر":
        msg = bot.send_message(m.chat.id, "🆔 أرسل Android ID لفك الحظر:")
        bot.register_next_step_handler(msg, lambda m2: unban_user(m2))
    elif m.text == "🎁 إهداء اشتراك":
        msg = bot.send_message(m.chat.id, "🆔 ارسل Android ID والأيام (مثال: 7650083401 7):")
        bot.register_next_step_handler(msg, lambda m2: gift_subscription(m2))

def save_announcement(m):
    db = get_data()
    db["config"]["announcement"] = m.text
    save_data(db)
    bot.send_message(m.chat.id, "✅ تم تحديث الإذاعة.")

def ban_user(m):
    db = get_data()
    aid = m.text.strip()
    db["users"].setdefault(aid, {"banned": True})
    db["users"][aid]["banned"] = True
    save_data(db)
    bot.send_message(m.chat.id, "🚫 تم حظر الجهاز.")

def unban_user(m):
    db = get_data()
    aid = m.text.strip()
    if aid in db["users"]:
        db["users"][aid]["banned"] = False
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
        user = db["users"].setdefault(aid, {"subscription_type":"gifted","start_time":time.time(),"end_time":time.time()+days*86400,"points":0,"banned":False,"trial_used":False})
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
