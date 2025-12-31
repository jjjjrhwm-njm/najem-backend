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

def post_to_channel(android_id, plan="FOREVER"):
    try:
        msg = f"🚀 تفعيل جديد!\n🆔 الجهاز: `{android_id}`\n⏳ النوع: `{plan}`"
        bot.send_message(CHANNEL_ID, msg, parse_mode="Markdown")
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
        return bot.reply_to(message, "❌ نأسف، لقد تم حظرك من استخدام البوت.")

    user = get_user(data, uid)
    
    # نظام الإحالة
    if "ref_" in message.text and user["invited_by"] is None:
        inviter_id = message.text.split("ref_")[1]
        if inviter_id != uid:
            inviter = get_user(data, inviter_id)
            inviter["points"] += 50 
            user["invited_by"] = inviter_id
            bot.send_message(inviter_id, "🌟 شخص جديد دخل عبر رابطك! حصلت على 50 نقطة.")

    # ربط الجهاز عبر الرابط
    if "code_" in message.text:
        user["aid"] = message.text.split("code_")[1]
        bot.reply_to(message, f"✅ تم ربط جهازك: `{user['aid']}`", parse_mode="Markdown")
    
    save_data(data)
    welcome = f"👋 أهلاً بك يا {message.from_user.first_name} في بوت نجم الإبداع.\n\nأرسل كلمة (كود) لفتح قائمة التحكم بجهازك."
    bot.send_message(message.chat.id, welcome)

@bot.message_handler(func=lambda m: m.text == "كود")
def user_menu(message):
    data = load_data()
    if is_banned(message.from_user.id, data): return
    
    uid = str(message.from_user.id)
    user = get_user(data, uid)
    bot_link = f"https://t.me/{(bot.get_me()).username}?start=ref_{uid}"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎁 تجربة 24 ساعة", callback_data="free"),
        types.InlineKeyboardButton("⭐ شراء تفعيل (النجوم)", callback_data="buy_stars"),
        types.InlineKeyboardButton("🔄 استبدال النقاط", callback_data="swap_pts"),
        types.InlineKeyboardButton("👤 حسابي", callback_data="my_acc")
    )
    msg = f"📊 **معلومات حسابك:**\n\n💰 نقاطك: `{user['points']}`\n🆔 جهازك: `{user['aid']}`\n\n🔗 رابط الدعوة:\n`{bot_link}`"
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- لوحة المدير الاحترافية ---
@bot.message_handler(func=lambda m: m.text == "njm5")
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    data = load_data()
    total_users = len(data["users"])
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎁 إهداء تفعيل", callback_data="a_gift"),
        types.InlineKeyboardButton("🚫 حظر مستخدم", callback_data="a_ban"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="a_unban"),
        types.InlineKeyboardButton("📢 إذاعة", callback_data="a_bc"),
        types.InlineKeyboardButton("📈 إحصائيات", callback_data="a_stats")
    )
    bot.send_message(message.chat.id, f"🛠 **لوحة الإدارة - نجم الإبداع**\n\nعدد المستخدمين: {total_users}", reply_markup=markup)

# --- معالج الأزرار (Callback) ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = load_data()
    uid = str(call.from_user.id)
    user = get_user(data, uid)

    if call.data == "free":
        if uid in data["trials"]:
            bot.answer_callback_query(call.id, "❌ استخدمت التجربة سابقاً!", show_alert=True)
        elif user["aid"] == "غير معروف":
            bot.answer_callback_query(call.id, "❌ اربط جهازك من التطبيق أولاً!", show_alert=True)
        else:
            data["trials"].append(uid)
            post_to_channel(user["aid"], "24H")
            bot.send_message(call.message.chat.id, "✅ تم تفعيل 24 ساعة لجهازك!")
            save_data(data)

    elif call.data == "buy_stars":
        if user["aid"] == "غير معروف":
            bot.answer_callback_query(call.id, "❌ اربط جهازك أولاً!", show_alert=True)
        else:
            # إرسال فاتورة نجوم تليجرام
            prices = [types.LabeledPrice(label="تفعيل مدى الحياة", amount=50)] # 50 نجمة
            bot.send_invoice(
                call.message.chat.id,
                title="تفعيل تطبيق نجم الإبداع",
                description=f"تفعيل دائم للجهاز: {user['aid']}",
                provider_token="", # يترك فارغاً للنجوم
                currency="XTR",
                prices=prices,
                invoice_payload="forever_sub"
            )

    elif call.data == "a_ban":
        msg = bot.send_message(call.message.chat.id, "أرسل ID المستخدم لحظره:")
        bot.register_next_step_handler(msg, admin_ban_step)

    elif call.data == "a_unban":
        msg = bot.send_message(call.message.chat.id, "أرسل ID المستخدم لفك حظره:")
        bot.register_next_step_handler(msg, admin_unban_step)

    elif call.data == "a_gift":
        msg = bot.send_message(call.message.chat.id, "أرسل Android ID لإهدائه تفعيل دائم:")
        bot.register_next_step_handler(msg, admin_gift_step)

    bot.answer_callback_query(call.id)

# --- خطوات المدير (Next Step Handlers) ---
def admin_ban_step(message):
    data = load_data()
    target_id = message.text.strip()
    if target_id not in data["banned"]:
        data["banned"].append(target_id)
        save_data(data)
        bot.reply_to(message, f"🚫 تم حظر المستخدم {target_id} بنجاح.")
    else:
        bot.reply_to(message, "هذا المستخدم محظور بالفعل.")

def admin_unban_step(message):
    data = load_data()
    target_id = message.text.strip()
    if target_id in data["banned"]:
        data["banned"].remove(target_id)
        save_data(data)
        bot.reply_to(message, f"✅ تم فك حظر المستخدم {target_id}.")
    else:
        bot.reply_to(message, "المستخدم ليس في قائمة الحظر.")

def admin_gift_step(message):
    if post_to_channel(message.text.strip(), "FOREVER (GIFT)"):
        bot.reply_to(message, "🎁 تم تفعيل الجهاز بنجاح كهدية!")

# --- معالجة دفع النجوم (Stars Payment) ---
@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    data = load_data()
    user = get_user(data, message.from_user.id)
    
    if message.successful_payment.invoice_payload == "forever_sub":
        post_to_channel(user["aid"], "FOREVER (STARS)")
        bot.send_message(message.chat.id, "🌟 شكراً لك! تم تفعيل اشتراكك الدائم بنجاح.")

# --- تشغيل البوت ---
if __name__ == "__main__":
    keep_alive()
    print("نجم الإبداع يعمل الآن...")
    bot.infinity_polling()
