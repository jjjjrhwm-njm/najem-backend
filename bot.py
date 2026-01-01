import os
import time
import json
import uuid
from flask import Flask, request, jsonify
from telebot import TeleBot, types
from threading import Thread

# --- إعداداتك الخاصة التي حفظتها ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
BOT_USERNAME = 'Njm_jrhwm_bot'
ADMIN_PASSWORD_CMD = 'نجم1' # الأمر السري للدخول للوحة
DB_FILE = 'njm_database.json'

bot = TeleBot(API_TOKEN)
app = Flask(__name__)

# --- إدارة قاعدة البيانات ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {
            "users": {}, 
            "app_links": {}, 
            "vouchers": {}, 
            "admins": [], # لتخزين من ادخل الامر السري
            "settings": {"msg": "تنبيه من نجم الإبداع ⚠️\nعذراً، أنت غير مشترك. يرجى التفعيل عبر البوت."}
        }
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=4)

# --- نظام الـ API (فحص التفعيل من التطبيقات) ---
@app.route('/check')
def check():
    aid = request.args.get('aid') # معرف الجهاز
    pkg = request.args.get('pkg') # اسم الحزمة (لفصل التطبيقات)
    
    if not aid or not pkg:
        return jsonify({"status": "INVALID"})
    
    db = load_db()
    app_key = f"{aid}_{pkg}" # مفتاح فريد يربط الجهاز بالتطبيق المحدد
    
    status = "EXPIRED"
    if app_key in db["app_links"]:
        if db["app_links"][app_key]["end_time"] > time.time():
            status = "ACTIVE"
            
    return jsonify({
        "status": status,
        "message": db.get("settings", {}).get("msg")
    })

# --- معالجات البوت (Telegram Bot) ---

@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    args = m.text.split()
    
    # الربط التلقائي عبر الرابط الذكي
    if len(args) > 1:
        try:
            # البيانات بصيغة: AID_PKG
            aid_pkg = args[1].split("_", 1)
            aid, pkg = aid_pkg[0], aid_pkg[1]
            db["users"][str(m.from_user.id)] = {"aid": aid, "pkg": pkg}
            save_db(db)
            bot.send_message(m.chat.id, f"✅ **تم الربط بنجاح!**\n📦 التطبيق الحالي: `{pkg}`\n🆔 معرف جهازك: `{aid}`", parse_mode="Markdown")
        except:
            bot.send_message(m.chat.id, "⚠️ خطأ في بيانات الربط.")

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🎁 تجربة مجانية (3س)", "📊 حالتي")
    markup.add("🎫 تفعيل كود", "💎 شراء اشتراك")
    bot.send_message(m.chat.id, f"أهلاً بك في بوت نجم الإبداع 🌟\nيمكنك إدارة اشتراكاتك وتفعيل تطبيقاتك من هنا.", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية (3س)")
def trial(m):
    db = load_db()
    user = db["users"].get(str(m.from_user.id))
    
    if not user:
        return bot.send_message(m.chat.id, "❌ يرجى الدخول من التطبيق أولاً والضغط على 'تفعيل'.")
    
    app_key = f"{user['aid']}_{user['pkg']}"
    
    if app_key not in db["app_links"]:
        db["app_links"][app_key] = {"end_time": 0, "trial_used": False}
    
    if db["app_links"][app_key].get("trial_used"):
        bot.send_message(m.chat.id, f"❌ لقد استخدمت الفترة التجريبية لتطبيق `{user['pkg']}` سابقاً.")
    else:
        db["app_links"][app_key]["trial_used"] = True
        db["app_links"][app_key]["end_time"] = time.time() + 10800 # 3 ساعات فقط كما طلبت
        save_db(db)
        bot.send_message(m.chat.id, f"✅ تم تفعيل 3 ساعات تجريبية لـ `{user['pkg']}`!\nعد للتطبيق واضغط **دخول**.")

@bot.message_handler(func=lambda m: m.text == "📊 حالتي")
def status(m):
    db = load_db()
    user = db["users"].get(str(m.from_user.id))
    if not user: return bot.send_message(m.chat.id, "❌ لم يتم ربط جهازك.")
    
    app_key = f"{user['aid']}_{user['pkg']}"
    info = db["app_links"].get(app_key, {})
    rem_seconds = info.get("end_time", 0) - time.time()
    
    if rem_seconds <= 0:
        bot.send_message(m.chat.id, f"📦 التطبيق: `{user['pkg']}`\n🔴 حالتك: **غير مشترك**", parse_mode="Markdown")
    else:
        rem_mins = int(rem_seconds / 60)
        bot.send_message(m.chat.id, f"📦 التطبيق: `{user['pkg']}`\n⏳ المتبقي: {rem_mins // 60} ساعة و {rem_mins % 60} دقيقة.", parse_mode="Markdown")

# --- لوحة المدير بالأمر السري (نجم1) ---
@bot.message_handler(func=lambda m: m.text == ADMIN_PASSWORD_CMD)
def admin(m):
    db = load_db()
    if str(m.from_user.id) not in db["admins"]:
        db["admins"].append(str(m.from_user.id))
        save_db(db)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎫 توليد كود (30 يوم)", callback_data="gen_30"))
    bot.send_message(m.chat.id, "👑 أهلاً بك يا نجم الإبداع في لوحة الإدارة:", reply_markup=markup)

@bot.callback_query_handler(func=lambda q: q.data == "gen_30")
def generate(q):
    db = load_db()
    if str(q.from_user.id) not in db["admins"]: return
    
    code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db["vouchers"][code] = 30
    save_db(db)
    bot.edit_message_text(f"🎫 كود جديد تم توليده:\n`{code}`", q.message.chat.id, q.message.message_id, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎫 تفعيل كود")
def redeem_start(m):
    msg = bot.send_message(m.chat.id, "أرسل كود التفعيل الذي حصلت عليه:")
    bot.register_next_step_handler(msg, redeem_final)

def redeem_final(m):
    code = m.text.strip()
    db = load_db()
    if code in db["vouchers"]:
        days = db["vouchers"].pop(code)
        user = db["users"].get(str(m.from_user.id))
        if user:
            app_key = f"{user['aid']}_{user['pkg']}"
            if app_key not in db["app_links"]: db["app_links"][app_key] = {"end_time": 0, "trial_used": False}
            db["app_links"][app_key]["end_time"] = max(time.time(), db["app_links"][app_key]["end_time"]) + (days * 86400)
            save_db(db)
            bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم لتطبيق `{user['pkg']}` بنجاح!")
        else: bot.send_message(m.chat.id, "❌ ادخل من التطبيق أولاً لربط الكود بجهازك.")
    else:
        bot.send_message(m.chat.id, "❌ الكود غير صحيح أو منتهي الصلاحية.")

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
