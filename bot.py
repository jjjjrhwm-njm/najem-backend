import telebot
from telebot import types
from flask import Flask, request
import json, os, time
from threading import Thread

# --- [ إعدادات النظام - نجم الإبداع ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_control.json"

# إعدادات الأسعار والاشتراك
PRICE_100_STARS = 100 
SUBSCRIPTION_DAYS = 30 # المدة الممنوحة عند الشراء

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- [ إدارة قاعدة البيانات ] ---
def get_data():
    if not os.path.exists(DATA_FILE):
        return {
            "users": {},
            "config": {
                "maintenance": False,
                "announcement": "مرحباً بكم في تطبيق نجم الإبداع",
                "latest_version": "1.0",
                "update_url": ""
            }
        }
    with open(DATA_FILE, "r", encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- [ API الخاص بالتطبيق الأندرويد ] ---
@app.route('/check')
def check():
    aid = request.args.get('aid', 'unknown')
    db = get_data()

    if aid not in db['users']:
        db['users'][aid] = {
            "subscription_type": "free",
            "start_time": time.time(),
            "end_time": time.time() + 86400, # يوم مجاني تلقائي
            "points": 0,
            "banned": False
        }
        save_data(db)

    user = db['users'][aid]

    if user['banned']:
        return "STATUS:BANNED"

    maintenance = db['config']['maintenance']
    announcement = db['config']['announcement']
    latest_version = db['config']['latest_version']
    update_url = db['config']['update_url']

    # التحقق من انتهاء الاشتراك
    now = time.time()
    if now > user['end_time']:
        user['subscription_type'] = "free"
        save_data(db)

    return f"MT:{int(maintenance)}|BC:{announcement}|VER:{latest_version}|URL:{update_url}|SUB:{user['subscription_type']}|POINTS:{user['points']}"

# --- [ لوحات التحكم (المدير والمستخدم) ] ---

@bot.message_handler(commands=['start'])
def welcome(m):
    if m.from_user.id == ADMIN_ID:
        show_admin_panel(m)
    else:
        bot.send_message(m.chat.id, "👋 مرحباً بك في بوت الإدارة.\nأرسل كلمة ( **كود** ) لإدارة اشتراكك.")

@bot.message_handler(func=lambda m: m.text.lower() == "كود")
def user_panel(m):
    db = get_data()
    aid = str(m.from_user.id)
    user = db["users"].setdefault(aid, {
        "subscription_type": "free",
        "start_time": time.time(),
        "end_time": time.time() + 86400,
        "points": 0,
        "banned": False
    })

    # حساب الأيام المتبقية
    remaining_days = int((user['end_time'] - time.time()) / 86400)
    remaining_days = max(0, remaining_days)

    msg = (f"👤 **ملف المستخدم**\n"
           f"🆔 معرفك: `{aid}`\n"
           f"💎 نوع الاشتراك: {user['subscription_type']}\n"
           f"⏳ المتبقي: {remaining_days} يوم\n"
           f"⭐ نقاطك: {user['points']}")

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💎 شراء اشتراك 100 نجمة", "🎁 اشتراك تجريبي يوم")
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

def show_admin_panel(m):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 إحصائيات المتصلين", "🛠 وضع الصيانة")
    markup.add("📢 نشر إذاعة", "🚫 حظر جهاز", "✅ فك حظر")
    markup.add("🎁 إهداء اشتراك")
    bot.send_message(m.chat.id, "👑 أهلاً بك يا مدير **نجم الإبداع**.\nالتحكم الكامل بين يديك الآن.", reply_markup=markup)

# --- [ نظام الدفع بنجوم تليجرام ] ---

@bot.message_handler(func=lambda m: m.text == "💎 شراء اشتراك 100 نجمة")
def send_stars_invoice(m):
    title = "تفعيل اشتراك برو"
    description = f"تفعيل ميزات التطبيق الكاملة لمدة {SUBSCRIPTION_DAYS} يوم."
    payload = f"stars_pay_{m.from_user.id}"
    currency = "XTR" 
    prices = [types.LabeledPrice(label="اشتراك برو", amount=PRICE_100_STARS)]

    bot.send_invoice(m.chat.id, title, description, payload, "", currency, prices)

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(m):
    db = get_data()
    aid = str(m.from_user.id)
    
    if aid in db["users"]:
        user = db["users"][aid]
        now = time.time()
        # إذا كان اشتراكه لسه شغال، نزود فوقه، لو منتهي نبدأ من الآن
        current_end = user["end_time"] if user["end_time"] > now else now
        
        user["subscription_type"] = "premium"
        user["end_time"] = current_end + (SUBSCRIPTION_DAYS * 86400)
        save_data(db)
        
        bot.send_message(m.chat.id, "✅ **تم تفعيل الاشتراك بنجاح!**\nشكرًا لثقتك بـ نجم الإبداع. استمتع بالتطبيق.")
        bot.send_message(ADMIN_ID, f"💰 **عملية دفع جديدة!**\nالمستخدم: {aid}\nالمبلغ: 100 نجمة")

# --- [ أوامر الإدارة ] ---

@bot.message_handler(func=lambda m: m.text == "📊 إحصائيات المتصلين")
def stats(m):
    db = get_data()
    total = len(db["users"])
    active = len([u for u in db["users"].values() if u["subscription_type"] == "premium"])
    bot.send_message(m.chat.id, f"👥 إجمالي المستخدمين: {total}\n💎 المشتركين برو: {active}")

@bot.message_handler(func=lambda m: m.text == "🛠 وضع الصيانة")
def toggle_mt(m):
    db = get_data()
    db["config"]["maintenance"] = not db["config"]["maintenance"]
    save_data(db)
    status = "🔴 تم فتح التطبيق للجميع" if not db["config"]["maintenance"] else "🟢 تم تفعيل وضع الصيانة (إغلاق)"
    bot.send_message(m.chat.id, status)

@bot.message_handler(func=lambda m: m.text == "📢 نشر إذاعة")
def bc_ask(m):
    msg = bot.send_message(m.chat.id, "✍️ أرسل نص الإعلان الجديد للتطبيق:")
    bot.register_next_step_handler(msg, bc_save)

def bc_save(m):
    db = get_data()
    db["config"]["announcement"] = m.text
    save_data(db)
    bot.send_message(m.chat.id, "✅ تم تحديث الإعلان في التطبيق.")

@bot.message_handler(func=lambda m: m.text == "🚫 حظر جهاز")
def ban_ask(m):
    msg = bot.send_message(m.chat.id, "🆔 أرسل الـ ID المراد حظره:")
    bot.register_next_step_handler(msg, ban_save)

def ban_save(m):
    db = get_data()
    target = m.text.strip()
    db["users"].setdefault(target, {"banned": True})
    db["users"][target]["banned"] = True
    save_data(db)
    bot.send_message(m.chat.id, "🚫 تم الحظر بنجاح.")

@bot.message_handler(func=lambda m: m.text == "✅ فك حظر")
def unban_ask(m):
    msg = bot.send_message(m.chat.id, "🆔 أرسل الـ ID لفك حظره:")
    bot.register_next_step_handler(msg, unban_save)

def unban_save(m):
    db = get_data()
    target = m.text.strip()
    if target in db["users"]:
        db["users"][target]["banned"] = False
        save_data(db)
        bot.send_message(m.chat.id, "✅ تم فك الحظر.")

@bot.message_handler(func=lambda m: m.text == "🎁 إهداء اشتراك")
def gift_ask(m):
    msg = bot.send_message(m.chat.id, "🆔 أرسل الـ ID ثم مسافة ثم عدد الأيام:\n(مثال: `7650083401 7`)")
    bot.register_next_step_handler(msg, gift_save)

def gift_save(m):
    try:
        aid, days = m.text.split()
        db = get_data()
        now = time.time()
        user = db["users"].setdefault(aid, {"end_time": now, "points": 0, "banned": False})
        current_end = user["end_time"] if user["end_time"] > now else now
        user["subscription_type"] = "gifted"
        user["end_time"] = current_end + (int(days) * 86400)
        save_data(db)
        bot.send_message(m.chat.id, f"🎁 تم إهداء {days} يوم للمستخدم {aid}")
    except:
        bot.send_message(m.chat.id, "❌ خطأ في الصيغة! تأكد من كتابة ID ثم مسافة ثم الرقم.")

# --- [ تشغيل السيرفر ] ---
def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    # تشغيل API في خلفية منفصلة
    Thread(target=run_flask).start()
    print("🚀 MASTER CORE IS ONLINE - STAR OF CREATIVITY")
    bot.infinity_polling()
