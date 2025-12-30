import telebot
from telebot import types
import json, os, random, string
from flask import Flask
from threading import Thread

# --- إعدادات بقاء البوت حياً (للموقع الجديد) ---
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

def post_to_channel(android_id, plan="FOREVER"):
    try:
        msg = f"Device:{android_id} Life:{plan}"
        bot.send_message(CHANNEL_ID, msg)
        return True
    except: return False

# --- الأوامر ---
@bot.message_handler(commands=['start'])
def start(message):
    data = load_data()
    uid = str(message.from_user.id)
    user = get_user(data, uid)
    
    if "ref_" in message.text and user["invited_by"] is None:
        inviter_id = message.text.split("ref_")[1]
        if inviter_id != uid:
            inviter = get_user(data, inviter_id)
            inviter["points"] += 50 
            user["invited_by"] = inviter_id
            bot.send_message(inviter_id, "🌟 شخص جديد دخل عبر رابطك! حصلت على 50 نقطة.")

    if "code_" in message.text:
        user["aid"] = message.text.split("code_")[1]
        bot.reply_to(message, f"✅ تم ربط جهازك: `{user['aid']}`", parse_mode="Markdown")
    
    save_data(data)
    welcome = "👋 أهلاً بك! أرسل (كود) لفتح القائمة."
    if message.from_user.id == ADMIN_ID: welcome += "\n\n🛠 أرسل (njm5) للوحة التحكم."
    bot.send_message(message.chat.id, welcome)

@bot.message_handler(func=lambda m: m.text == "كود")
def user_menu(message):
    uid = str(message.from_user.id)
    data = load_data()
    user = get_user(data, uid)
    bot_link = f"https://t.me/{(bot.get_me()).username}?start=ref_{uid}"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎁 تجربة (24 ساعة)", callback_data="free"),
        types.InlineKeyboardButton("💎 شراء نجوم", callback_data="buy_stars"),
        types.InlineKeyboardButton("🔄 استبدال 500 نقطة", callback_data="swap_pts"),
        types.InlineKeyboardButton("👤 حسابي", callback_data="my_acc")
    )
    msg = f"💰 نقاطك: `{user['points']}`\n🆔 جهازك: `{user['aid']}`\n\n🔗 رابط دعوة الأصدقاء لجمع النقاط:\n`{bot_link}`"
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "njm5")
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🎁 تفعيل جهاز (هدية)", callback_data="a_gift"),
        types.InlineKeyboardButton("📢 إذاعة", callback_data="a_bc")
    )
    bot.send_message(message.chat.id, "🛠 لوحة المدير", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = load_data()
    user = get_user(data, call.from_user.id)

    if call.data == "free":
        if str(call.from_user.id) in data["trials"]:
            bot.answer_callback_query(call.id, "❌ استخدمت التجربة سابقاً!", show_alert=True)
        elif user["aid"] == "غير معروف":
            bot.answer_callback_query(call.id, "❌ اربط جهازك من التطبيق أولاً!", show_alert=True)
        else:
            data["trials"].append(str(call.from_user.id))
            if post_to_channel(user["aid"], "24H"):
                bot.send_message(call.message.chat.id, "✅ تم تفعيل 24 ساعة!")
                save_data(data)

    elif call.data == "swap_pts":
        if user["points"] >= 500 and user["aid"] != "غير معروف":
            user["points"] -= 500
            post_to_channel(user["aid"], "FOREVER")
            bot.send_message(call.message.chat.id, "✅ تم استبدال النقاط بتفعيل دائم!")
            save_data(data)
        else:
            bot.answer_callback_query(call.id, "❌ نقاطك غير كافية أو لم تربط جهازك!", show_alert=True)

    elif call.data == "a_gift":
        msg = bot.send_message(call.message.chat.id, "أرسل الـ Android ID للتفعيل:")
        bot.register_next_step_handler(msg, admin_gift_step)

    bot.answer_callback_query(call.id)

def admin_gift_step(message):
    if post_to_channel(message.text.strip(), "FOREVER"):
        bot.reply_to(message, "✅ تم منح التفعيل الهدية!")

# --- تشغيل البوت ---
if __name__ == "__main__":
    keep_alive() # تشغيل السيرفر الصغير لضمان عدم التوقف
    print("Bot is starting...")
    bot.infinity_polling()
