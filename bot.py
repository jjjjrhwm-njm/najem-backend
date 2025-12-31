import telebot
from telebot import types
import json, os, time, datetime
from flask import Flask, request
from threading import Thread

# --- إعدادات نجم الإبداع ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "njm_database.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- إدارة قاعدة البيانات ---
def load_db():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "config": {"mt": "0", "msg": "أهلاً بك", "ver": "1.0", "url": "https://t.me/nejm_njm"}}
    with open(DATA_FILE, "r") as f: return json.load(f)

def save_db(db):
    with open(DATA_FILE, "w") as f: json.dump(db, f, indent=4)

# --- بروتوكول الربط (API) ---
@app.route('/check')
def check():
    aid = request.args.get('aid', 'unknown')
    db = load_db()
    
    if aid not in db["users"]:
        db["users"][aid] = {"points": 0, "exp": 0, "banned": False, "refs": 0}
        save_db(db)
    
    user = db["users"][aid]
    status = "FREE"
    if user["banned"]: status = "BANNED"
    elif user["exp"] > time.time(): status = "PREMIUM"
    
    # تنسيق الرد الاحترافي: صيانة|رسالة|نسخة|رابط|حالة|نقاط|وقت_الانتهاء
    res = f"{db['config']['mt']}|{db['config']['msg']}|{db['config']['ver']}|{db['config']['url']}|{status}|{user['points']}|{user['exp']}"
    return res

# --- لوحة المدير العليا (njm5) ---
@bot.message_handler(func=lambda m: m.text == "njm5")
def admin_menu(m):
    if m.from_user.id != ADMIN_ID: return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 الإحصائيات", "🛠 تبديل الصيانة")
    markup.add("📢 تحديث الإذاعة", "🆙 وضع رابط تحديث")
    markup.add("🎁 إهداء اشتراك", "🚫 حظر/فك حظر")
    bot.send_message(m.chat.id, "👑 أهلاً يا نجم الإبداع. اختر أمر التحكم:", reply_markup=markup)

# --- لوحة المستخدمين (كود) ---
@bot.message_handler(func=lambda m: m.text == "كود")
def user_menu(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💎 شراء (100 نجمة)", callback_data="buy_month"))
    markup.add(types.InlineKeyboardButton("🎁 تجربة (يوم مجاني)", callback_data="free_trial"))
    markup.add(types.InlineKeyboardButton("🔗 تجميع نقاط", callback_data="collect_points"))
    bot.send_message(m.chat.id, "📱 لوحة التحكم في اشتراكك:", reply_markup=markup)

# --- ميزة أدهشني: نظام الإحالة (Referral) ---
@bot.callback_query_handler(func=lambda call: call.data == "collect_points")
def referral_link(call):
    ref_link = f"https://t.me/{bot.get_me().username}?start={call.from_user.id}"
    bot.send_message(call.message.chat.id, f"🔗 شارك رابطك: {ref_link}\nادعُ 2 من أصدقائك للحصول على 3 أيام اشتراك مجاناً!")

# --- معالجة الدفع والاشتراكات ---
@bot.callback_query_handler(func=lambda call: call.data in ["buy_month", "free_trial"])
def handle_subs(call):
    db = load_db()
    # هنا يتم إضافة المنطق الخاص بمعرف الجهاز المرتبط بالتليجرام
    bot.answer_callback_query(call.id, "سيتم التفعيل فور ربط الـ Android ID")

# --- تشغيل السيرفر المتوافق مع Render ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    bot.infinity_polling()
