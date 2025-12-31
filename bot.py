import telebot
from telebot import types
import json, os, time
from flask import Flask, request, jsonify
from threading import Thread

# --- إعدادات النظام ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
CHANNEL_ID = "@nejm_njm"
DATA_FILE = "njm_master_db.json"
bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- قاعدة البيانات ---
def get_db():
    if not os.path.exists(DATA_FILE):
        return {
            "users": {}, "banned": [], "trials": [],
            "config": {
                "maintenance": False,
                "broadcast": "",
                "version": "1.0",
                "update_url": "https://t.me/nejm_njm",
                "active_pings": {}
            }
        }
    with open(DATA_FILE, "r") as f: return json.load(f)

def save_db(db):
    with open(DATA_FILE, "w") as f: json.dump(db, f, indent=4)

# --- API للتطبيق (انسجام تام) ---
@app.route('/njm_api', methods=['GET'])
def njm_api():
    db = get_db()
    aid = request.args.get('aid')
    uid = request.args.get('uid')
    
    # تحديث النشاط (Active Users)
    if aid: db["config"]["active_pings"][aid] = time.time()
    save_db(db)
    
    # تجهيز الرد الذكي للتطبيق
    res = {
        "maintenance": db["config"]["maintenance"],
        "broadcast": db["config"]["broadcast"],
        "version": db["config"]["version"],
        "update_url": db["config"]["update_url"],
        "is_banned": aid in db["banned"],
        "active_users": len([t for t in db["config"]["active_pings"].values() if time.time() - t < 60])
    }
    return jsonify(res)

# --- لوحة التحكم (Telegram Bot) ---
@bot.message_handler(commands=['start'])
def start(m):
    db = get_db()
    uid = str(m.from_user.id)
    if uid not in db["users"]: db["users"][uid] = {"pts": 0, "aid": "NONE"}
    if "code_" in m.text:
        db["users"][uid]["aid"] = m.text.split("code_")[1]
        bot.reply_to(m, "🎯 تم ربط الجهاز بالمنظومة.")
    save_db(db)
    bot.send_message(m.chat.id, "👋 نظام نجم الإبداع المتكامل.\nأرسل (كود) للمستخدم أو (njm5) للمدير.")

@bot.message_handler(func=lambda m: m.text == "كود")
def user_menu(m):
    db = get_db()
    u = db["users"].get(str(m.from_user.id), {"pts": 0, "aid": "NONE"})
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎁 تجربة 24 ساعة", callback_data="trial"))
    markup.add(types.InlineKeyboardButton("⭐ شراء شهر (100 نجمة)", callback_data="buy"))
    bot.send_message(m.chat.id, f"👤 حسابك:\n🆔 جهازك: `{u['aid']}`\n💰 نقاطك: `{u['pts']}`", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "njm5" and m.from_user.id == ADMIN_ID)
def admin_menu(m):
    db = get_db()
    active = len([t for t in db["config"]["active_pings"].values() if time.time() - t < 60])
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📢 إذاعة", callback_data="m_bc"),
        types.InlineKeyboardButton("🛠 صيانة: " + ("ON" if db["config"]["maintenance"] else "OFF"), callback_data="m_mt"),
        types.InlineKeyboardButton("🚫 حظر جهاز", callback_data="m_ban"),
        types.InlineKeyboardButton("✅ فك حظر", callback_data="m_unban"),
        types.InlineKeyboardButton("🆙 تحديث الإصدار", callback_data="m_upd")
    )
    bot.send_message(m.chat.id, f"👑 **لوحة السيادة**\n👥 المتصلون الآن: `{active}`", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("m_"))
def admin_actions(c):
    db = get_db()
    if c.data == "m_mt":
        db["config"]["maintenance"] = not db["config"]["maintenance"]
        save_db(db)
        bot.answer_callback_query(c.id, "تم تغيير حالة الصيانة")
        admin_menu(c.message) # تحديث اللوحة
    elif c.data == "m_bc":
        msg = bot.send_message(c.message.chat.id, "✍️ أرسل رسالة الإذاعة (ستظهر فوراً في التطبيق):")
        bot.register_next_step_handler(msg, set_bc)

def set_bc(m):
    db = get_db()
    db["config"]["broadcast"] = m.text
    save_db(db)
    bot.send_message(m.chat.id, "✅ تم النشر بنجاح.")

# --- تشغيل النظام ---
def run_flask(): app.run(host='0.0.0.0', port=8080)
if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot.infinity_polling()
