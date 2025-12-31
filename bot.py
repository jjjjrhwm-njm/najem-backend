import telebot
from telebot import types
from flask import Flask, request
import json
import os
import time
from threading import Thread, Lock

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json"

# إعدادات الأسعار والمكافآت
STAR_PRICE_MONTH = 100 
TRIAL_DAYS = 1
REFERRAL_REWARD_DAYS = 3
REQUIRED_REFERRALS = 3

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock() # حماية البيانات من التداخل

# --- [ إدارة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE):
            return {"users": {}, "config": {"maintenance": False, "announcement": "مرحباً", "ver": "1.0", "url": ""}}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"users": {}, "config": {"maintenance": False, "announcement": "مرحباً", "ver": "1.0", "url": ""}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)

# --- [ منطق API التطبيق ] ---
@app.route('/')
def home():
    return "SERVER IS ALIVE 🟢"

@app.route('/check')
def check_status():
    aid = request.args.get('aid')
    db = load_db()
    if not aid or aid not in db["users"]:
        return "ERROR:NOT_FOUND"
    
    user = db["users"][aid]
    if user.get("banned"): return "STATUS:BANNED"
    
    now = time.time()
    sub_status = user["subscription_type"]
    if now > user["end_time"]:
        sub_status = "free"
    
    cfg = db["config"]
    return f"MT:{int(cfg['maintenance'])}|BC:{cfg['announcement']}|VER:{cfg['ver']}|URL:{cfg['url']}|SUB:{sub_status}"

# --- [ واجهة المستخدم - تلجرام ] ---

@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    aid = str(m.from_user.id)
    
    # نظام الإحالة (Referral)
    args = m.text.split()
    if len(args) > 1 and args[1] != aid:
        referrer_id = args[1]
        if aid not in db["users"]:
            if referrer_id in db["users"]:
                db["users"][referrer_id]["ref_count"] = db["users"][referrer_id].get("ref_count", 0) + 1
                if db["users"][referrer_id]["ref_count"] >= REQUIRED_REFERRALS:
                    db["users"][referrer_id]["end_time"] = max(db["users"][referrer_id].get("end_time", time.time()), time.time()) + (REFERRAL_REWARD_DAYS * 86400)
                    db["users"][referrer_id]["ref_count"] = 0
                    bot.send_message(referrer_id, f"🎁 تهانينا! حصلت على {REFERRAL_REWARD_DAYS} أيام مكافأة.")

    if aid not in db["users"]:
        db["users"][aid] = {
            "subscription_type": "free",
            "end_time": time.time(),
            "trial_used": False,
            "ref_count": 0,
            "banned": False
        }
    save_db(db)
    bot.send_message(m.chat.id, "مرحباً بك! أرسل كلمة ( **كود** ) لفتح لوحة التحكم.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "كود")
def user_menu(m):
    db = load_db()
    user = db["users"].get(str(m.from_user.id), {})
    rem_seconds = user.get("end_time", 0) - time.time()
    rem_days = max(0, int(rem_seconds / 86400))
    
    status_text = f"👤 **معلوماتك:**\nاشتراكك: `{user.get('subscription_type')}`\nالمتبقي: `{rem_days}` يوم\nدعواتك: `{user.get('ref_count', 0)}/3`"
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🎁 تجربة يوم مجاني", "💎 شراء شهر (100 نجمة)")
    markup.add("🔗 رابط الدعوة الخاص بي")
    bot.send_message(m.chat.id, status_text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة يوم مجاني")
def claim_trial(m):
    db = load_db()
    user = db["users"].get(str(m.from_user.id))
    if not user: return
    if user.get("trial_used"):
        bot.send_message(m.chat.id, "❌ لقد استخدمت الفترة التجريبية مسبقاً.")
    else:
        user["trial_used"] = True
        user["end_time"] = time.time() + 86400
        user["subscription_type"] = "trial"
        save_db(db)
        bot.send_message(m.chat.id, "✅ تم تفعيل اشتراكك لمدة 24 ساعة.")

@bot.message_handler(func=lambda m: m.text == "🔗 رابط الدعوة الخاص بي")
def send_ref_link(m):
    bot_username = bot.get_me().username
    bot.send_message(m.chat.id, f"انشر هذا الرابط، وإذا اشترك {REQUIRED_REFERRALS} من طرفك ستحصل على {REFERRAL_REWARD_DAYS} أيام مجانية:\nhttps://t.me/{bot_username}?start={m.from_user.id}")

# --- [ واجهة المدير ] ---

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_menu(m):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🛠 وضع الصيانة", "📢 إعلان جديد")
    markup.add("🎁 إهداء اشتراك", "🚫 حظر/فك حظر")
    markup.add("🆕 تحديث التطبيق")
    bot.send_message(m.chat.id, "👑 أهلاً يا مدير. اختر المهمة:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🎁 إهداء اشتراك" and m.from_user.id == ADMIN_ID)
def gift_start(m):
    msg = bot.send_message(m.chat.id, "أرسل ID المستخدم ثم الأيام (مثال: `123456 30`):")
    bot.register_next_step_handler(msg, gift_process)

def gift_process(m):
    try:
        aid, days = m.text.split()
        db = load_db()
        if aid in db["users"]:
            db["users"][aid]["end_time"] = max(db["users"][aid].get("end_time", time.time()), time.time()) + (int(days) * 86400)
            db["users"][aid]["subscription_type"] = "premium"
            save_db(db)
            bot.send_message(m.chat.id, f"✅ تم إهداء {days} يوم لـ {aid}")
        else: bot.send_message(m.chat.id, "❌ المستخدم غير موجود.")
    except: bot.send_message(m.chat.id, "❌ خطأ في الصيغة.")

# --- [ نظام الدفع ] ---
@bot.message_handler(func=lambda m: m.text == "💎 شراء شهر (100 نجمة)")
def pay_month(m):
    bot.send_invoice(m.chat.id, "اشتراك شهر برو", "تفعيل كافة ميزات التطبيق", f"pay_{m.from_user.id}", "", "XTR", [types.LabeledPrice("برو", 100)])

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db()
    aid = str(m.from_user.id)
    db["users"][aid]["end_time"] = max(db["users"][aid].get("end_time", time.time()), time.time()) + (30 * 86400)
    db["users"][aid]["subscription_type"] = "premium"
    save_db(db)
    bot.send_message(m.chat.id, "✅ تم تفعيل اشتراكك الشهري بنجاح!")

# --- [ التشغيل النهائي لـ Render ] ---
def run_flask():
    # هذا السطر ضروري جداً لـ Render ليتعرف على المنفذ المتغير
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    # تشغيل Flask في الخلفية
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    # تشغيل البوت في الواجهة
    print("Bot started successfully...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
