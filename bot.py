import telebot
from telebot import types
import json, os, random, string
from flask import Flask
from threading import Thread

# --- إعدادات البقاء حياً للسيرفر ---
app = Flask('')
@app.route('/')
def home(): return "نظام نجم الإبداع نشط!"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive():
    t = Thread(target=run)
    t.start()

# --- إعدادات البوت ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
CHANNEL_ID = "@nejm_njm" 
ADMIN_ID = 7650083401 
DATA_FILE = "bot_data.json"

bot = telebot.TeleBot(API_TOKEN)

# --- إدارة البيانات ---
def load_data():
    if not os.path.exists(DATA_FILE): return {"trials": [], "users": {}}
    try:
        with open(DATA_FILE, "r", encoding='utf-8') as f: return json.load(f)
    except: return {"trials": [], "users": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding='utf-8') as f: 
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_user(data, uid):
    uid = str(uid)
    if uid not in data["users"]:
        data["users"][uid] = {"points": 0, "aid": "غير معروف", "invited_by": None}
    return data["users"][uid]

# --- أوامر البوت ---
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
            bot.send_message(inviter_id, "🌟 حصلت على 50 نقطة لدعوة شخص جديد!")

    if "code_" in message.text:
        user["aid"] = message.text.split("code_")[1]
        bot.reply_to(message, f"✅ تم ربط جهازك بنجاح:\n`{user['aid']}`", parse_mode="Markdown")
    
    save_data(data)
    txt = "👋 أهلاً بك! أرسل (كود) لفتح القائمة."
    if message.from_user.id == ADMIN_ID: txt += "\n\n🛠 أرسل (njm5) للوحة التحكم."
    bot.send_message(message.chat.id, txt)

@bot.message_handler(func=lambda m: m.text == "كود")
def user_menu(message):
    data = load_data()
    user = get_user(data, message.from_user.id)
    link = f"https://t.me/{(bot.get_me()).username}?start=ref_{message.from_user.id}"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="free"),
        types.InlineKeyboardButton("🔄 تحويل النقاط", callback_data="swap"),
        types.InlineKeyboardButton("👤 حسابي", callback_data="my_acc")
    )
    bot.send_message(message.chat.id, f"💰 نقاطك: `{user['points']}`\n🆔 جهازك: `{user['aid']}`\n\n🔗 رابط الدعوة الخاص بك:\n`{link}`", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "njm5")
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🎁 تفعيل جهاز (هدية)", callback_data="a_gift"),
        types.InlineKeyboardButton("🔴 إيقاف التطبيق للجميع", callback_data="a_kill"),
        types.InlineKeyboardButton("🟢 تشغيل التطبيق للجميع", callback_data="a_on"),
        types.InlineKeyboardButton("📢 إرسال تنبيه جماعي", callback_data="a_alert")
    )
    bot.send_message(message.chat.id, "🛠 **لوحة تحكم المدير**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_calls(call):
    data = load_data()
    user = get_user(data, call.from_user.id)

    if call.data == "free":
        if str(call.from_user.id) in data["trials"]:
            bot.answer_callback_query(call.id, "❌ استخدمت التجربة سابقاً!", show_alert=True)
        elif user["aid"] == "غير معروف":
            bot.answer_callback_query(call.id, "❌ اربط جهازك من التطبيق أولاً!", show_alert=True)
        else:
            data["trials"].append(str(call.from_user.id))
            bot.send_message(CHANNEL_ID, f"Device:{user['aid']} Life:24H")
            bot.send_message(call.message.chat.id, "✅ تم تفعيل 24 ساعة!")
            save_data(data)

    elif call.data == "swap":
        if user["points"] >= 500 and user["aid"] != "غير معروف":
            user["points"] -= 500
            bot.send_message(CHANNEL_ID, f"Device:{user['aid']} Life:FOREVER")
            bot.send_message(call.message.chat.id, "✅ تم استبدال النقاط بتفعيل دائم!")
            save_data(data)
        else:
            bot.answer_callback_query(call.id, "❌ نقاط غير كافية!", show_alert=True)

    elif call.data == "a_kill":
        bot.send_message(CHANNEL_ID, "APP_STATUS:OFF")
        bot.answer_callback_query(call.id, "🚫 تم إغلاق التطبيق عند الجميع!", show_alert=True)

    elif call.data == "a_on":
        bot.send_message(CHANNEL_ID, "APP_STATUS:ON")
        bot.answer_callback_query(call.id, "✅ تم إعادة التشغيل للجميع!", show_alert=True)

    elif call.data == "a_alert":
        msg = bot.send_message(call.message.chat.id, "أرسل نص التنبيه الذي سيظهر للمستخدمين:")
        bot.register_next_step_handler(msg, process_alert)

    elif call.data == "a_gift":
        msg = bot.send_message(call.message.chat.id, "أرسل الـ Android ID للتفعيل الفوري:")
        bot.register_next_step_handler(msg, admin_gift)

    bot.answer_callback_query(call.id)

def process_alert(message):
    bot.send_message(CHANNEL_ID, f"ALERT_MSG:{message.text}")
    bot.reply_to(message, "📢 تم نشر التنبيه الجماعي!")

def admin_gift(message):
    bot.send_message(CHANNEL_ID, f"Device:{message.text.strip()} Life:FOREVER")
    bot.reply_to(message, "✅ تم منح التفعيل الهدية!")

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
    bot.send_message(message.chat.id, welcome_text)

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
    msg = f"🌟 **قائمة المستخدم**\n\n💰 نقاطك: `{user['points']}`\n🆔 جهازك: `{user['aid']}`\n\n🔗 رابط الدعوة الخاص بك لجمع النقاط:\n`{bot_link}`"
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "njm5")
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🎁 تفعيل جهاز (هدية)", callback_data="a_gift"),
        types.InlineKeyboardButton("📊 إحصائيات", callback_data="a_stats"),
        types.InlineKeyboardButton("📢 إذاعة", callback_data="a_bc")
    )
    bot.send_message(message.chat.id, "🛠 **لوحة تحكم المدير الصارمة**", reply_markup=markup)

# --- معالجة الضغطات ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = load_data()
    uid = str(call.from_user.id)
    user = get_user(data, uid)

    if call.data == "free":
        if uid in data["trials"]:
            bot.answer_callback_query(call.id, "❌ استخدمت التجربة سابقاً!", show_alert=True)
        elif user["aid"] == "غير معروف":
            bot.answer_callback_query(call.id, "❌ يجب الربط عبر التطبيق أولاً!", show_alert=True)
        else:
            data["trials"].append(uid)
            if post_to_channel(user["aid"], "24H"):
                bot.send_message(call.message.chat.id, "✅ تم تفعيل 24 ساعة! اذهب للتطبيق واضغط (تحقق).")
                save_data(data)

    elif call.data == "swap_pts":
        if user["points"] >= 500 and user["aid"] != "غير معروف":
            user["points"] -= 500
            post_to_channel(user["aid"], "FOREVER")
            bot.send_message(call.message.chat.id, "✅ تم استهلاك 500 نقطة وتحويل اشتراكك إلى دائم!")
            save_data(data)
        else:
            bot.answer_callback_query(call.id, "❌ نقاطك غير كافية (تحتاج 500) أو لم تربط جهازك!", show_alert=True)

    elif call.data == "buy_stars":
        prices = [types.LabeledPrice(label="اشتراك دائم", amount=100)] # 100 نجمة
        bot.send_invoice(call.message.chat.id, "تفعيل دائم", "تفعيل التطبيق للأبد", "stars_pay", "", "XTR", prices)

    elif call.data == "a_gift":
        msg = bot.send_message(call.message.chat.id, "أرسل الـ Android ID للتفعيل الفوري:")
        bot.register_next_step_handler(msg, admin_gift_step)

    bot.answer_callback_query(call.id)

def admin_gift_step(message):
    aid = message.text.strip()
    if post_to_channel(aid, "FOREVER"):
        bot.reply_to(message, f"🎁 تم منح تفعيل دائم للجهاز:\n`{aid}`", parse_mode="Markdown")

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_success(message):
    data = load_data()
    user = get_user(data, message.from_user.id)
    post_to_channel(user["aid"], "FOREVER")
    bot.send_message(message.chat.id, "💎 تم استلام النجوم وتفعيل جهازك للأبد!")

bot.infinity_polling()
