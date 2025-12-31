import telebot
from telebot import types
from flask import Flask, request
import json, os, time
from threading import Thread

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json"

# إعدادات الأسعار
STAR_PRICE_MONTH = 100 # ما يعادل تقريباً 8-10 ريال عبر النجوم
TRIAL_DAYS = 1
REFERRAL_REWARD_DAYS = 3
REQUIRED_REFERRALS = 3

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- [ إدارة البيانات ] ---
def load_db():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "config": {"maintenance": False, "announcement": "مرحباً", "ver": "1.0", "url": ""}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

# --- [ منطق API التطبيق ] ---
@app.route('/check')
def check_status():
    aid = request.args.get('aid')
    db = load_db()
    if not aid or aid not in db["users"]:
        return "ERROR:NOT_FOUND"
    
    user = db["users"][aid]
    if user.get("banned"): return "STATUS:BANNED"
    
    # تحديث نوع الاشتراك إذا انتهى الوقت
    now = time.time()
    sub_status = user["subscription_type"]
    if now > user["end_time"]:
        sub_status = "free"
    
    cfg = db["config"]
    return f"MT:{int(cfg['maintenance'])}|BC:{cfg['announcement']}|VER:{cfg['ver']}|URL:{cfg['url']}|SUB:{sub_status}"

# --- [ واجهة المستخدم - أمر: كود ] ---

@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    aid = str(m.from_user.id)
    
    # منطق دعوة الأصدقاء (Referral)
    args = m.text.split()
    if len(args) > 1 and args[1] != aid:
        referrer_id = args[1]
        if aid not in db["users"]: # إذا كان المستخدم جديداً فعلاً
            db["users"].setdefault(referrer_id, {"ref_count": 0})
            db["users"][referrer_id]["ref_count"] = db["users"][referrer_id].get("ref_count", 0) + 1
            # إذا وصل لـ 3 دعوات
            if db["users"][referrer_id]["ref_count"] >= REQUIRED_REFERRALS:
                db["users"][referrer_id]["end_time"] = max(db["users"][referrer_id].get("end_time", time.time()), time.time()) + (REFERRAL_REWARD_DAYS * 86400)
                db["users"][referrer_id]["ref_count"] = 0 # تصفير العداد بعد المكافأة
                bot.send_message(referrer_id, f"🎁 تهانينا! دعوت 3 أصدقاء وحصلت على {REFERRAL_REWARD_DAYS} أيام مجانية.")

    # إنشاء حساب إذا لم يوجد
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
    rem = int((user.get("end_time", 0) - time.time()) / 86400)
    rem = max(0, rem)
    
    status_text = f"👤 **معلوماتك:**\nاشتراكك: `{user.get('subscription_type')}`\nالمتبقي: `{rem}` يوم\nدعواتك: `{user.get('ref_count', 0)}/3`"
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🎁 تجربة يوم مجاني", "💎 شراء شهر (100 نجمة)")
    markup.add("🔗 رابط الدعوة الخاص بي")
    bot.send_message(m.chat.id, status_text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة يوم مجاني")
def claim_trial(m):
    db = load_db()
    user = db["users"].get(str(m.from_user.id))
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
    bot.send_message(m.chat.id, f"انشر هذا الرابط، وإذا اشترك 3 من طرفك ستحصل على 3 أيام مجانية:\nhttps://t.me/{(bot.get_me()).username}?start={m.from_user.id}")

# --- [ واجهة المدير - أمر: نجم1 ] ---

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_menu(m):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🛠 وضع الصيانة", "📢 إعلان جديد")
    markup.add("🎁 إهداء اشتراك", "🚫 حظر/فك حظر")
    markup.add("🆕 تحديث التطبيق")
    bot.send_message(m.chat.id, "👑 أهلاً يا مدير. اختر المهمة:", reply_markup=markup)

# 1. إهداء اشتراك
@bot.message_handler(func=lambda m: m.text == "🎁 إهداء اشتراك" and m.from_user.id == ADMIN_ID)
def gift_start(m):
    msg = bot.send_message(m.chat.id, "أرسل ID المستخدم ثم الأيام (مثال: `123456 30`):")
    bot.register_next_step_handler(msg, gift_process)

def gift_process(m):
    try:
        aid, days = m.text.split()
        db = load_db()
        if aid in db["users"]:
            db["users"][aid]["end_time"] = max(db["users"][aid]["end_time"], time.time()) + (int(days) * 86400)
            db["users"][aid]["subscription_type"] = "premium"
            save_db(db)
            bot.send_message(m.chat.id, f"✅ تم إهداء {days} يوم لـ {aid}")
        else: bot.send_message(m.chat.id, "❌ المستخدم غير موجود.")
    except: bot.send_message(m.chat.id, "❌ خطأ في الصيغة.")

# 2. حظر وفك حظر
@bot.message_handler(func=lambda m: m.text == "🚫 حظر/فك حظر" and m.from_user.id == ADMIN_ID)
def ban_start(m):
    msg = bot.send_message(m.chat.id, "أرسل ID المستخدم للحظر أو فك الحظر:")
    bot.register_next_step_handler(msg, ban_process)

def ban_process(m):
    db = load_db()
    aid = m.text.strip()
    if aid in db["users"]:
        db["users"][aid]["banned"] = not db["users"][aid].get("banned", False)
        save_db(db)
        status = "محظور" if db["users"][aid]["banned"] else "نشط"
        bot.send_message(m.chat.id, f"✅ تم تغيير حالة المستخدم {aid} إلى: {status}")
    else: bot.send_message(m.chat.id, "❌ غير موجود.")

# 3. تحديث التطبيق
@bot.message_handler(func=lambda m: m.text == "🆕 تحديث التطبيق" and m.from_user.id == ADMIN_ID)
def update_start(m):
    msg = bot.send_message(m.chat.id, "أرسل رقم الإصدار الجديد ثم الرابط (مثال: `2.0 https://site.com/app.apk`):")
    bot.register_next_step_handler(msg, update_process)

def update_process(m):
    try:
        ver, url = m.text.split()
        db = load_db()
        db["config"]["ver"] = ver
        db["config"]["url"] = url
        save_db(db)
        bot.send_message(m.chat.id, "✅ تم تحديث بيانات الإصدار الجديد.")
    except: bot.send_message(m.chat.id, "❌ خطأ في الصيغة.")

# 4. الصيانة والإعلان
@bot.message_handler(func=lambda m: m.text == "🛠 وضع الصيانة" and m.from_user.id == ADMIN_ID)
def toggle_mt(m):
    db = load_db()
    db["config"]["maintenance"] = not db["config"]["maintenance"]
    save_db(db)
    bot.send_message(m.chat.id, f"وضع الصيانة الآن: {'مفعل 🟢' if db['config']['maintenance'] else 'معطل 🔴'}")

@bot.message_handler(func=lambda m: m.text == "📢 إعلان جديد" and m.from_user.id == ADMIN_ID)
def announce_start(m):
    msg = bot.send_message(m.chat.id, "أرسل نص الإعلان الذي سيظهر داخل التطبيق:")
    bot.register_next_step_handler(msg, announce_process)

def announce_process(m):
    db = load_db()
    db["config"]["announcement"] = m.text
    save_db(db)
    bot.send_message(m.chat.id, "✅ تم تحديث الإعلان.")

# --- [ نظام الدفع بالنجوم ] ---
@bot.message_handler(func=lambda m: m.text == "💎 شراء شهر (100 نجمة)")
def pay_month(m):
    bot.send_invoice(m.chat.id, "اشتراك شهر برو", "تفعيل كافة ميزات التطبيق", f"pay_{m.from_user.id}", "", "XTR", [types.LabeledPrice("برو", 100)])

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db()
    aid = str(m.from_user.id)
    db["users"][aid]["end_time"] = max(db["users"][aid]["end_time"], time.time()) + (30 * 86400)
    db["users"][aid]["subscription_type"] = "premium"
    save_db(db)
    bot.send_message(m.chat.id, "✅ تم تفعيل اشتراكك الشهري بنجاح!")

# --- [ التشغيل ] ---
def run_api(): app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run_api).start()
    bot.infinity_polling()
