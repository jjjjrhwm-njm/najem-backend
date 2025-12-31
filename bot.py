import telebot
from telebot import types
import json, os, threading
from flask import Flask

# --- إعدادات السيرفر (Render) ---
app = Flask('')
@app.route('/')
def home(): return "البوت يعمل بكفاءة عالية!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    threading.Thread(target=run).start()

# --- الإعدادات الأساسية (ضع بياناتك هنا) ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401 
CHANNEL_ID = "@nejm_njm"
DATA_FILE = "bot_data.json"

bot = telebot.TeleBot(API_TOKEN)

# --- إدارة البيانات ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"trials": [], "users": {}, "banned": []}
    with open(DATA_FILE, "r", encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def is_banned(uid, data):
    return str(uid) in data.get("banned", [])

# --- إرسال التفعيل للقناة ---
def post_to_channel(android_id, plan="لأبد"):
    try:
        msg = f"🚀 **تم تفعيل جهاز جديد!**\n\n📱 الجهاز: `{android_id}`\n⏳ المدة: {plan}\n✅ الحالة: نشط"
        bot.send_message(CHANNEL_ID, msg, parse_mode="Markdown")
        return True
    except: return False

# --- الأوامر الرئيسية ---
@bot.message_handler(commands=['start'])
def start(message):
    data = load_data()
    uid = str(message.from_user.id)
    
    if is_banned(uid, data):
        return bot.reply_to(message, "❌ أنت محظور من استخدام البوت.")

    if uid not in data["users"]:
        data["users"][uid] = {"points": 0, "aid": "غير مربوط", "invited_by": None}
    
    # نظام الإحالة (Referral)
    if "ref_" in message.text:
        inviter_id = message.text.split("ref_")[1]
        if inviter_id != uid and data["users"][uid]["invited_by"] is None:
            data["users"][uid]["invited_by"] = inviter_id
            data["users"][inviter_id]["points"] += 50
            bot.send_message(inviter_id, "🌟 ربحت 50 نقطة لدعوتك صديق جديد!")

    save_data(data)
    
    welcome_text = (
        f"👋 أهلاً بك يا {message.from_user.first_name} في بوت نجم الإبداع.\n\n"
        "هذا البوت يساعدك على تفعيل تطبيقك بسرعة وسهولة."
    )
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📱 قائمة الأكواد", "🛠 لوحة التحكم" if message.from_user.id == ADMIN_ID else None)
    markup.add("👤 حسابي", "🎁 كود مجاني")
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

# --- معالجة الأزرار النصية ---
@bot.message_handler(func=lambda m: True)
def handle_text(message):
    data = load_data()
    uid = str(message.from_user.id)
    
    if is_banned(uid, data): return

    if message.text == "📱 قائمة الأكواد":
        user = data["users"].get(uid)
        bot_link = f"https://t.me/{(bot.get_me()).username}?start=ref_{uid}"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⭐ شراء نجوم", callback_data="buy_stars"),
            types.InlineKeyboardButton("🔄 استبدال النقاط (500)", callback_data="swap_pts"),
            types.InlineKeyboardButton("🔗 رابط الدعوة", callback_data="my_ref")
        )
        msg = f"💰 نقاطك: `{user['points']}`\n🆔 جهازك: `{user['aid']}`\n\nاستخدم رابطك لجمع النقاط:\n`{bot_link}`"
        bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

    elif message.text == "👤 حسابي":
        user = data["users"].get(uid)
        info = (
            "👤 **معلومات حسابك:**\n"
            f"— — — — — — — — —\n"
            f"🆔 معرفك: `{uid}`\n"
            f"📱 جهازك: `{user['aid']}`\n"
            f"💰 النقاط: `{user['points']}`\n"
            f"🌍 الحالة: {'متصل' if not is_banned(uid, data) else 'محظور'}"
        )
        bot.send_message(message.chat.id, info, parse_mode="Markdown")

    elif message.text == "🎁 كود مجاني":
        if uid in data["trials"]:
            bot.reply_to(message, "❌ لقد حصلت على كود تجريبي من قبل!")
        else:
            bot.reply_to(message, "ارسل الان الـ Android ID الخاص بجهازك للحصول على 24 ساعة:")
            bot.register_next_step_handler(message, process_free_trial)

    elif message.text == "🛠 لوحة التحكم" and message.from_user.id == ADMIN_ID:
        admin_panel(message)

# --- وظائف المدير ---
def admin_panel(message):
    data = load_data()
    total_users = len(data["users"])
    total_banned = len(data["banned"])
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚫 حظر مستخدم", callback_data="a_ban"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="a_unban"),
        types.InlineKeyboardButton("🎁 إهداء تفعيل", callback_data="a_gift"),
        types.InlineKeyboardButton("📢 إذاعة", callback_data="a_bc")
    )
    msg = f"🛠 **لوحة تحكم المدير**\n\n👥 مستخدمين: {total_users}\n🚫 محظورين: {total_banned}"
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- معالجة الأزرار المضمنة (Callback) ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    data = load_data()
    uid = str(call.from_user.id)

    if call.data == "buy_stars":
        # إرسال فاتورة دفع بنجوم تليجرام (XTR)
        # السعر: 50 نجمة مقابل تفعيل دائم (مثال)
        bot.send_invoice(
            call.message.chat.id,
            title="تفعيل دائم",
            description="شراء اشتراك دائم في التطبيق باستخدام النجوم",
            provider_token="", # يترك فارغاً للنجوم
            currency="XTR",
            prices=[types.LabeledPrice("تفعيل", 50)],
            invoice_payload="pay_forever"
        )

    elif call.data == "swap_pts":
        user = data["users"].get(uid)
        if user["points"] >= 500 and user["aid"] != "غير مربوط":
            user["points"] -= 500
            post_to_channel(user["aid"], "دائم (نقاط)")
            bot.send_message(call.message.chat.id, "✅ تم التفعيل بنجاح!")
            save_data(data)
        else:
            bot.answer_callback_query(call.id, "❌ نقاطك غير كافية أو لم تربط جهازك!", show_alert=True)

    elif call.data == "a_ban":
        msg = bot.send_message(call.message.chat.id, "أرسل ID المستخدم لحظره:")
        bot.register_next_step_handler(msg, lambda m: process_ban(m, True))

    elif call.data == "a_unban":
        msg = bot.send_message(call.message.chat.id, "أرسل ID المستخدم لفك الحظر:")
        bot.register_next_step_handler(msg, lambda m: process_ban(m, False))

    elif call.data == "a_gift":
        msg = bot.send_message(call.message.chat.id, "أرسل الـ Android ID لإهدائه تفعيل:")
        bot.register_next_step_handler(msg, process_gift)

    bot.answer_callback_query(call.id)

# --- وظائف الخطوات التالية (Next Step Handlers) ---
def process_free_trial(message):
    data = load_data()
    aid = message.text.strip()
    uid = str(message.from_user.id)
    if post_to_channel(aid, "24 ساعة"):
        data["trials"].append(uid)
        data["users"][uid]["aid"] = aid
        save_data(data)
        bot.reply_to(message, "✅ تم تفعيل جهازك لمدة 24 ساعة تجريبية!")

def process_ban(message, ban=True):
    data = load_data()
    target_id = message.text.strip()
    if ban:
        if target_id not in data["banned"]: data["banned"].append(target_id)
        bot.reply_to(message, f"🚫 تم حظر {target_id}")
    else:
        if target_id in data["banned"]: data["banned"].remove(target_id)
        bot.reply_to(message, f"✅ تم فك حظر {target_id}")
    save_data(data)

def process_gift(message):
    aid = message.text.strip()
    if post_to_channel(aid, "إهداء دائم"):
        bot.reply_to(message, "✅ تم إرسال التفعيل بنجاح!")

# --- معالجة الدفع بالنجوم ---
@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.successful_payment_handler(func=lambda payment: True)
def got_payment(message):
    data = load_data()
    uid = str(message.from_user.id)
    user = data["users"].get(uid)
    if user["aid"] != "غير مربوط":
        post_to_channel(user["aid"], "دائم (نجوم)")
        bot.send_message(message.chat.id, "🎉 شكراً لك! تم التفعيل الدائم بنجاح.")
    else:
        bot.send_message(message.chat.id, "⚠️ تم الدفع ولكن جهازك غير مربوط! تواصل مع المدير.")

# --- التشغيل ---
if __name__ == "__main__":
    keep_alive()
    print("البوت يعمل الآن...")
    bot.infinity_polling()
            f"🌍 الحالة: {'متصل' if not is_banned(uid, data) else 'محظور'}"
        )
        bot.send_message(message.chat.id, info, parse_mode="Markdown")

    elif message.text == "🎁 كود مجاني":
        if uid in data["trials"]:
            bot.reply_to(message, "❌ لقد حصلت على كود تجريبي من قبل!")
        else:
            bot.reply_to(message, "ارسل الان الـ Android ID الخاص بجهازك للحصول على 24 ساعة:")
            bot.register_next_step_handler(message, process_free_trial)

    elif message.text == "🛠 لوحة التحكم" and message.from_user.id == ADMIN_ID:
        admin_panel(message)

# --- وظائف المدير ---
def admin_panel(message):
    data = load_data()
    total_users = len(data["users"])
    total_banned = len(data["banned"])
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚫 حظر مستخدم", callback_data="a_ban"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="a_unban"),
        types.InlineKeyboardButton("🎁 إهداء تفعيل", callback_data="a_gift"),
        types.InlineKeyboardButton("📢 إذاعة", callback_data="a_bc")
    )
    msg = f"🛠 **لوحة تحكم المدير**\n\n👥 مستخدمين: {total_users}\n🚫 محظورين: {total_banned}"
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- معالجة الأزرار المضمنة (Callback) ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    data = load_data()
    uid = str(call.from_user.id)

    if call.data == "buy_stars":
        # إرسال فاتورة دفع بنجوم تليجرام (XTR)
        # السعر: 50 نجمة مقابل تفعيل دائم (مثال)
        bot.send_invoice(
            call.message.chat.id,
            title="تفعيل دائم",
            description="شراء اشتراك دائم في التطبيق باستخدام النجوم",
            provider_token="", # يترك فارغاً للنجوم
            currency="XTR",
            prices=[types.LabeledPrice("تفعيل", 50)],
            invoice_payload="pay_forever"
        )

    elif call.data == "swap_pts":
        user = data["users"].get(uid)
        if user["points"] >= 500 and user["aid"] != "غير مربوط":
            user["points"] -= 500
            post_to_channel(user["aid"], "دائم (نقاط)")
            bot.send_message(call.message.chat.id, "✅ تم التفعيل بنجاح!")
            save_data(data)
        else:
            bot.answer_callback_query(call.id, "❌ نقاطك غير كافية أو لم تربط جهازك!", show_alert=True)

    elif call.data == "a_ban":
        msg = bot.send_message(call.message.chat.id, "أرسل ID المستخدم لحظره:")
        bot.register_next_step_handler(msg, lambda m: process_ban(m, True))

    elif call.data == "a_unban":
        msg = bot.send_message(call.message.chat.id, "أرسل ID المستخدم لفك الحظر:")
        bot.register_next_step_handler(msg, lambda m: process_ban(m, False))

    elif call.data == "a_gift":
        msg = bot.send_message(call.message.chat.id, "أرسل الـ Android ID لإهدائه تفعيل:")
        bot.register_next_step_handler(msg, process_gift)

    bot.answer_callback_query(call.id)

# --- وظائف الخطوات التالية (Next Step Handlers) ---
def process_free_trial(message):
    data = load_data()
    aid = message.text.strip()
    uid = str(message.from_user.id)
    if post_to_channel(aid, "24 ساعة"):
        data["trials"].append(uid)
        data["users"][uid]["aid"] = aid
        save_data(data)
        bot.reply_to(message, "✅ تم تفعيل جهازك لمدة 24 ساعة تجريبية!")

def process_ban(message, ban=True):
    data = load_data()
    target_id = message.text.strip()
    if ban:
        if target_id not in data["banned"]: data["banned"].append(target_id)
        bot.reply_to(message, f"🚫 تم حظر {target_id}")
    else:
        if target_id in data["banned"]: data["banned"].remove(target_id)
        bot.reply_to(message, f"✅ تم فك حظر {target_id}")
    save_data(data)

def process_gift(message):
    aid = message.text.strip()
    if post_to_channel(aid, "إهداء دائم"):
        bot.reply_to(message, "✅ تم إرسال التفعيل بنجاح!")

# --- معالجة الدفع بالنجوم ---
@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.successful_payment_handler(func=lambda payment: True)
def got_payment(message):
    data = load_data()
    uid = str(message.from_user.id)
    user = data["users"].get(uid)
    if user["aid"] != "غير مربوط":
        post_to_channel(user["aid"], "دائم (نجوم)")
        bot.send_message(message.chat.id, "🎉 شكراً لك! تم التفعيل الدائم بنجاح.")
    else:
        bot.send_message(message.chat.id, "⚠️ تم الدفع ولكن جهازك غير مربوط! تواصل مع المدير.")

# --- التشغيل ---
if __name__ == "__main__":
    keep_alive()
    print("البوت يعمل الآن...")
    bot.infinity_polling()
