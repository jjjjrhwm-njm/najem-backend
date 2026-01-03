import telebot
from telebot import types
from flask import Flask, request, render_template_string
import json, os, time, uuid
from threading import Thread, Lock

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json"
BOT_USER = "Njm_jrhwm_bot"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock()

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE):
            return {"users": {}, "app_links": {}, "vouchers": {}, "settings": {"news": "مرحباً بك", "price": 100}}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "settings": {"news": "خبر جديد", "price": 100}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4, ensure_ascii=False)

# --- [ واجهة HTML التي ستظهر داخل التطبيق ] ---
HTML_UI = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>نجم الإبداع - حماية</title>
    <style>
        body { background: #0f0f0f; color: white; font-family: sans-serif; text-align: center; padding: 50px 20px; }
        .card { background: #1a1a1a; padding: 30px; border-radius: 20px; border: 1px solid #ff9800; box-shadow: 0 0 20px rgba(255,152,0,0.2); }
        h1 { color: #ff9800; font-size: 24px; }
        p { color: #ccc; line-height: 1.6; }
        .btn { display: inline-block; background: #ff9800; color: black; padding: 12px 25px; border-radius: 10px; 
               text-decoration: none; font-weight: bold; margin-top: 20px; box-shadow: 0 4px 10px rgba(255,152,0,0.3); }
        .footer { margin-top: 30px; font-size: 12px; color: #555; }
    </style>
</head>
<body>
    <div class="card">
        <h1>⚠️ الوصول مقيد</h1>
        <p>{{ message }}</p>
        <p>معرف جهازك: <br><strong style="color:#ff9800;">{{ aid }}</strong></p>
        <a href="https://t.me/{{ bot_user }}?start={{ aid }}" class="btn">تفعيل الاشتراك الآن</a>
    </div>
    <div class="footer">نظام حماية نجم الإبداع © 2026</div>
</body>
</html>
"""

# --- [ مسارات الـ API والواجهة ] ---
@app.route('/check')
def check():
    aid, pkg = request.args.get('aid'), request.args.get('pkg')
    db = load_db()
    uid = f"{aid}_{pkg.replace('.', '_')}" if aid and pkg else "unknown"
    data = db["app_links"].get(uid)
    
    if data and not data.get("banned") and time.time() < data.get("end_time", 0):
        return "ACTIVE"
    return "LOCKED"

@app.route('/ui')
def show_ui():
    aid = request.args.get('aid', 'غير معروف')
    msg = request.args.get('msg', 'اشتراكك منتهي أو الجهاز غير مسجل، يرجى التفعيل للمتابعة.')
    return render_template_string(HTML_UI, aid=aid, message=msg, bot_user=BOT_USER)

# --- [ البوت ولوحة نجم1 ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db(); uid = str(m.from_user.id)
    if uid not in db["users"]: db["users"][uid] = {"current_app": None}
    args = m.text.split()
    if len(args) > 1:
        cid = args[1]
        db["app_links"].setdefault(cid, {"end_time": 0, "banned": False, "trial_used": False})
        db["app_links"][cid]["telegram_id"] = uid
        db["users"][uid]["current_app"] = cid
        save_db(db)
        bot.send_message(m.chat.id, "✅ **تم ربط الجهاز بنجاح!**", parse_mode="Markdown")
    
    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add("📱 حالتي", "🎫 تفعيل كود", "🛒 شراء")
    bot.send_message(m.chat.id, "مرحباً بك في لوحة تحكم **نجم الإبداع**.", reply_markup=menu)

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎫 توليد كود", callback_data="gen"), 
               types.InlineKeyboardButton("📢 إذاعة", callback_data="bc"))
    bot.send_message(m.chat.id, "👑 **لوحة المدير**", reply_markup=markup)

# (بقية وظائف البوت كما في الكود السابق لضمان استقرار النظام)

def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
