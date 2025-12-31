import telebot
from telebot import types
import json, os
from flask import Flask
from threading import Thread

# --- إعدادات بقاء البوت حياً ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running!"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive():
    t = Thread(target=run)
    t.start()

# --- إعدادات البوت الأساسية ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
CHANNEL_ID = "@nejm_njm" 
ADMIN_ID = 7650083401 
DATA_FILE = "bot_data.json"

bot = telebot.TeleBot(API_TOKEN)

# --- إدارة البيانات ---
def load_data():
    if not os.path.exists(DATA_FILE): return {"trials": [], "users": {}, "banned": []}
    try:
        with open(DATA_FILE, "r", encoding='utf-8') as f: return json.load(f)
    except: return {"trials": [], "users": {}, "banned": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def get_user(data, uid):
    uid = str(uid)
    if uid not in data["users"]:
        data["users"][uid] = {"points": 0, "is_sub": False, "aid": "غير معروف", "invited_by": None}
    return data["users"][uid]

# --- دالة الإرسال للقناة (مزامنة مع Smali) ---
def post_to_channel(android_id, plan="FOREVER"):
    try:
        # ملاحظة: تم تعديل النص ليتطابق مع فحص الـ Smali
        msg = f"🚀 تفعيل جديد لنجم الإبداع\n\nDevice:{android_id}\nLife:{plan}"
        bot.send_message(CHANNEL_ID, msg)
        return True
    except: return False

# --- فحص الحظر ---
def is_banned(uid, data):
    return str(uid) in data.get("banned", [])

# --- الأوامر ---
@bot.message_handler(commands=['start'])
def start(message):
    data = load_data()
    uid = str(message.from_user.id)
    
    if is_banned(uid, data):
        return bot.reply_to(message, "❌ نأسف، لقد تم حظرك.")

    user = get_user(data, uid)
    
    if "ref_" in message.text and user["invited_by"] is None:
        inviter_id = message.text.split("ref_")[1]
        if inviter_id != uid:
            inviter = get_user(data, inviter_id)
            inviter["points"] += 50 
            user["invited_by"] = inviter_id
            bot.send_message(inviter_id, "🌟 حصلت على 50 نقطة من إحالة جديدة!")

    if "code_" in message.text:
        user["aid"] = message.text.split("code_")[1]
        bot.reply_to(message, f"✅ تم ربط جهازك بنجاح:\n`{user['aid']}`", parse_mode="Markdown")
    
    save_data(data)
    bot.send_message(message.chat.id, f"👋 أهلاً {message.from_user.first_name}\nأرسل كلمة (كود) للتحكم.")

@bot.message_handler(func=lambda m: m.text == "كود")
def user_menu(message):
    data = load_data()
    uid = str(message.from_user.id)
    user = get_user(data, uid)
    bot_link = f"https://t.me/{(bot.get_me()).username}?start=ref_{uid}"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎁 تجربة 24 ساعة", callback_data="free"),
        types.InlineKeyboardButton("⭐ شراء تفعيل (النجوم)", callback_data="buy_stars"),
        types.InlineKeyboardButton("👤 حسابي", callback_data="my_acc")
    )
    msg = f"📊 **معلوماتك:**\n💰 نقاطك: `{user['points']}`\n🆔 جهازك: `{user['aid']}`\n🔗 الرابط: `{bot_link}`"
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- معالجة الدفع والعمليات ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = load_data()
    uid = str(call.from_user.id)
    user = get_user(data, uid)

    if call.data == "free":
        if uid in data["trials"]:
            bot.answer_callback_query(call.id, "❌ استخدمت التجربة سابقاً!", show_alert=True)
        elif user["aid"] == "غير معروف":
            bot.answer_callback_query(call.id, "❌ اربط جهازك أولاً!", show_alert=True)
        else:
            data["trials"].append(uid)
            post_to_channel(user["aid"], "24H")
            bot.send_message(call.message.chat.id, "✅ تم تفعيل 24 ساعة! اذهب للتطبيق واضغط (تحقق).")
            save_data(data)

    elif call.data == "buy_stars":
        if user["aid"] == "غير معروف":
            bot.answer_callback_query(call.id, "❌ اربط جهازك أولاً!", show_alert=True)
        else:
            prices = [types.LabeledPrice(label="تفعيل دائم", amount=50)]
            bot.send_invoice(call.message.chat.id, "تفعيل نجم الإبداع", f"جهاز: {user['aid']}", "forever_sub", "", "XTR", prices)

    bot.answer_callback_query(call.id)

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(query): bot.answer_pre_checkout_query(query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    data = load_data()
    user = get_user(data, message.from_user.id)
    post_to_channel(user["aid"], "FOREVER")
    bot.send_message(message.chat.id, "🌟 مبروك! تم التفعيل الدائم بنجاح.")

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
