import telebot
from telebot import types
import json, os, time
from flask import Flask
from threading import Thread

# --- تشغيل السيرفر ---
app = Flask('')
@app.route('/')
def home(): return "NJM System Online"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

# --- إعدادات البوت ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
CHANNEL_ID = "@nejm_njm" # تأكد أنها قناة عامة Public
ADMIN_ID = 7650083401 

bot = telebot.TeleBot(API_TOKEN)

def load_db():
    if not os.path.exists("njm_pro.json"): return {"users": {}, "trials": [], "banned": []}
    with open("njm_pro.json", "r") as f: return json.load(f)

def save_db(db):
    with open("njm_pro.json", "w") as f: json.dump(db, f, indent=4)

# --- دالة الإرسال للقناة (معدلة لتجنب مشاكل HTML) ---
def post_status(aid, days):
    # نرسل النص بدون Markdown في الأسطر الحساسة لضمان قراءتها من Smali
    txt = "💎 NJM SYSTEM\n"
    txt += f"Device:{aid}\n"
    txt += f"Plan:{days}\n"
    txt += "Status:ACTIVE"
    bot.send_message(CHANNEL_ID, txt)

# --- الأوامر ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    if uid in db["banned"]: return
    if uid not in db["users"]: db["users"][uid] = {"pts": 0, "aid": "NONE"}
    
    if "code_" in m.text:
        db["users"][uid]["aid"] = m.text.split("code_")[1]
        bot.reply_to(m, "✅ تم ربط جهازك بنظام نجم الإبداع.")
    
    save_db(db)
    bot.send_message(m.chat.id, f"👋 أهلاً بك {m.from_user.first_name}\nأرسل كلمة (كود) لفتح اللوحة.")

@bot.message_handler(func=lambda m: m.text == "كود")
def menu(m):
    db = load_db()
    uid = str(m.from_user.id)
    u = db["users"].get(uid)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎁 تجربة (1 يوم)", callback_data="p_1"))
    markup.add(types.InlineKeyboardButton("⭐ شراء شهر (100 نجمة)", callback_data="p_30"))
    bot.send_message(m.chat.id, f"👤 حسابك:\n🆔 جهازك: `{u['aid']}`\n💰 نقاطك: `{u['pts']}`", reply_markup=markup, parse_mode="Markdown")

# --- لوحة المدير ---
@bot.message_handler(func=lambda m: m.text == "njm5" and m.from_user.id == ADMIN_ID)
def admin(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 إذاعة (نشر للكل)", callback_data="a_bc"))
    markup.add(types.InlineKeyboardButton("🎁 إهداء تفعيل", callback_data="a_gift"))
    bot.send_message(m.chat.id, "👑 لوحة الإدارة العليا - نجم الإبداع", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: True)
def calls(c):
    db = load_db()
    uid = str(c.from_user.id)
    u = db["users"].get(uid)
    
    if c.data == "p_1":
        if u["aid"] == "NONE": return bot.answer_callback_query(c.id, "❌ اربط جهازك أولاً")
        post_status(u["aid"], 1)
        bot.send_message(c.message.chat.id, "✅ تم إرسال طلب التفعيل لليوم! اضغط (تحقق) في التطبيق.")
    
    elif c.data == "p_30":
        if u["aid"] == "NONE": return bot.answer_callback_query(c.id, "❌ اربط جهازك أولاً")
        prices = [types.LabeledPrice(label="تفعيل 30 يوم", amount=100)]
        bot.send_invoice(c.message.chat.id, "اشتراك شهر", "تفعيل تطبيق نجم الإبداع", "sub_30", "", "XTR", prices)

    elif c.data == "a_bc":
        msg = bot.send_message(c.message.chat.id, "✍️ أرسل الرسالة التي تريد نشرها للجميع:")
        bot.register_next_step_handler(msg, broadcast_step)

    elif c.data == "a_gift":
        msg = bot.send_message(c.message.chat.id, "🆔 أرسل الـ Android ID للإهداء:")
        bot.register_next_step_handler(msg, gift_step)

    bot.answer_callback_query(c.id)

def broadcast_step(m):
    db = load_db()
    for uid in db["users"]:
        try: bot.send_message(uid, f"📢 رسالة من الإدارة:\n\n{m.text}")
        except: pass
    bot.send_message(m.chat.id, "✅ تمت الإذاعة بنجاح.")

def gift_step(m):
    post_status(m.text.strip(), 30)
    bot.send_message(m.chat.id, "🎁 تم إرسال تفعيل الشهر للجهاز المذكور.")

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_done(m):
    db = load_db()
    u = db["users"].get(str(m.from_user.id))
    post_status(u["aid"], 30)
    bot.send_message(m.chat.id, "🌟 تم الدفع بنجاح! تم إرسال تفعيل شهر لجهازك.")

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
