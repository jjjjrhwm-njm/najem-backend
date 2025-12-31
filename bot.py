import telebot
from telebot import types
import json, os, time
from flask import Flask
from threading import Thread

# --- إعدادات السيرفر ---
app = Flask('')
@app.route('/')
def home(): return "NJM Bot is Online!"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive():
    Thread(target=run).start()

# --- البيانات الأساسية ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
CHANNEL_ID = "@nejm_njm" 
ADMIN_ID = 7650083401 
DATA_FILE = "njm_database.json"

bot = telebot.TeleBot(API_TOKEN)

def load_data():
    if not os.path.exists(DATA_FILE): return {"users": {}, "trials": [], "banned": []}
    with open(DATA_FILE, "r", encoding='utf-8') as f: return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def get_user(data, uid):
    uid = str(uid)
    if uid not in data["users"]:
        data["users"][uid] = {"points": 0, "aid": "غير معروف", "invited_by": None, "sub_end": 0}
    return data["users"][uid]

def sync_to_channel(aid, days):
    # الصيغة التي سيفهمها الـ Smali (Device:ID Plan:Days)
    msg = f"✨ تفعيل ذكي جديد\n━━━━━━━━━━━━━\nDevice:{aid}\nPlan:{days}\n━━━━━━━━━━━━━\nبواسطة: نجم الإبداع"
    bot.send_message(CHANNEL_ID, msg)

# --- الأوامر الرئيسية ---

@bot.message_handler(commands=['start'])
def start_cmd(message):
    data = load_data()
    uid = str(message.from_user.id)
    if uid in data["banned"]: return
    
    user = get_user(data, uid)
    if "ref_" in message.text and not user["invited_by"]:
        inviter_id = message.text.split("ref_")[1]
        if inviter_id != uid:
            inviter = get_user(data, inviter_id)
            inviter["points"] += 100
            user["invited_by"] = inviter_id
            bot.send_message(inviter_id, "🔥 مبروك! حصلت على 100 نقطة من دعوة صديق.")

    if "code_" in message.text:
        user["aid"] = message.text.split("code_")[1]
        bot.reply_to(message, f"🎯 تم ربط جهازك: `{user['aid']}`", parse_mode="Markdown")
    
    save_data(data)
    bot.send_message(message.chat.id, f"🚀 أهلاً بك في عالم نجم الإبداع.\n\nأرسل كلمة (كود) للتحكم.")

@bot.message_handler(func=lambda m: m.text == "كود")
def user_menu(message):
    data = load_data()
    uid = str(message.from_user.id)
    user = get_user(data, uid)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎁 تجربة (يوم)", callback_data="trial_1"),
        types.InlineKeyboardButton("⭐ شراء شهر (100 نجمة)", callback_data="buy_30"),
        types.InlineKeyboardButton("🔄 استبدال النقاط (1000=شهر)", callback_data="points_30"),
        types.InlineKeyboardButton("👤 حسابي", callback_data="my_info")
    )
    
    bot_link = f"https://t.me/{bot.get_me().username}?start=ref_{uid}"
    msg = f"🛡 **لوحة تحكم المستخدم**\n\n💰 نقاطك: `{user['points']}`\n🆔 جهازك: `{user['aid']}`\n🔗 رابطك: `{bot_link}`"
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- لوحة المدير njm5 ---
@bot.message_handler(func=lambda m: m.text == "njm5")
def admin_panel(message):
    if int(message.from_user.id) != ADMIN_ID: return
    data = load_data()
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📢 إذاعة للجميع", callback_data="admin_bc"),
        types.InlineKeyboardButton("🎁 إهداء تفعيل", callback_data="admin_gift"),
        types.InlineKeyboardButton("🚫 حظر", callback_data="admin_ban"),
        types.InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")
    )
    bot.send_message(message.chat.id, "👑 **مرحباً بك يا مدير (نجم الإبداع)**", reply_markup=markup)

# --- معالجة الضغطات ---
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    data = load_data()
    uid = str(call.from_user.id)
    user = get_user(data, uid)

    if call.data == "trial_1":
        if uid in data["trials"]:
            bot.answer_callback_query(call.id, "❌ استخدمت التجربة سابقاً", show_alert=True)
        elif user["aid"] == "غير معروف":
            bot.answer_callback_query(call.id, "❌ اربط جهازك أولاً", show_alert=True)
        else:
            data["trials"].append(uid)
            sync_to_channel(user["aid"], 1)
            bot.send_message(call.message.chat.id, "✅ تم تفعيل يوم واحد مجاناً!")
            save_data(data)

    elif call.data == "buy_30":
        if user["aid"] == "غير معروف":
            bot.answer_callback_query(call.id, "❌ اربط جهازك أولاً")
        else:
            prices = [types.LabeledPrice(label="تفعيل شهر", amount=100)] # 100 نجمة
            bot.send_invoice(call.message.chat.id, "تفعيل 30 يوم", f"للجهاز: {user['aid']}", "sub_30", "", "XTR", prices)

    elif call.data == "points_30":
        if user["points"] >= 1000:
            user["points"] -= 1000
            sync_to_channel(user["aid"], 30)
            bot.send_message(call.message.chat.id, "🎉 مبروك! تم استبدال النقاط بتفعيل شهر.")
            save_data(data)
        else:
            bot.answer_callback_query(call.id, "❌ تحتاج 1000 نقطة على الأقل", show_alert=True)

    elif call.data == "admin_bc":
        msg = bot.send_message(call.message.chat.id, "✍️ أرسل رسالة الإذاعة الآن:")
        bot.register_next_step_handler(msg, bc_step)

    elif call.data == "admin_gift":
        msg = bot.send_message(call.message.chat.id, "🆔 أرسل الـ Android ID للإهداء:")
        bot.register_next_step_handler(msg, gift_step)

    bot.answer_callback_query(call.id)

# --- خطوات المدير ---
def bc_step(message):
    data = load_data()
    count = 0
    for user_id in data["users"]:
        try:
            bot.send_message(user_id, f"📢 **رسالة من الإدارة:**\n\n{message.text}")
            count += 1
        except: pass
    bot.send_message(message.chat.id, f"✅ تم الإرسال لـ {count} مستخدم.")

def gift_step(message):
    aid = message.text.strip()
    sync_to_channel(aid, 30)
    bot.send_message(message.chat.id, f"🎁 تم إهداء تفعيل شهر للجهاز:\n`{aid}`", parse_mode="Markdown")

# --- الدفع ---
@bot.pre_checkout_query_handler(func=lambda query: True)
def pre_checkout(query): bot.answer_pre_checkout_query(query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_ok(message):
    data = load_data()
    user = get_user(data, message.from_user.id)
    sync_to_channel(user["aid"], 30)
    bot.send_message(message.chat.id, "🌟 شكراً لك! تم تفعيل الشهر بنجاح.")

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
