import telebot
from telebot import types
from flask import Flask, request, jsonify
import json, os, time, uuid
import requests
import google.generativeai as genai
from threading import Thread, Lock 

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json" 

# --- [ إعدادات الواتساب و Gemini ] ---
# أضف هذه القيم في إعدادات Render (Environment Variables)
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = "969461516243161"
GEMINI_KEY = os.getenv("GEMINI_KEY")
VERIFY_TOKEN = "NJM_CREATIVE_TOKEN" # هذا تضعه في فيسبوك للتحقق

# إعداد ذكاء Gemini
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    ai_model = genai.GenerativeModel('gemini-pro')

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock() 

# --- [ وظيفة إرسال رسائل واتساب ] ---
def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    requests.post(url, headers=headers, json=data)

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): 
            return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً"}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: 
                db = json.load(f)
                if "global_news" not in db: db["global_news"] = "لا توجد أخبار حالياً"
                if "vouchers" not in db: db["vouchers"] = {}
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً"}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4) 

# --- [ واجهة الـ API والـ Webhooks ] ---

@app.route('/whatsapp', methods=['GET'])
def verify_whatsapp():
    # للتحقق من فيسبوك عند الربط لأول مرة
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    data = request.get_json()
    try:
        if "messages" in data["entry"][0]["changes"][0]["value"]:
            msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
            from_num = msg["from"]
            text = msg["text"]["body"]
            
            # الرد باستخدام Gemini
            response = ai_model.generate_content(text)
            send_whatsapp_message(from_num, response.text)
    except: pass
    return "ok", 200

@app.route('/check')
def check_status():
    aid, pkg = request.args.get('aid'), request.args.get('pkg')
    if not aid or not pkg: return "EXPIRED"
    uid = f"{aid}_{pkg.replace('.', '_')}"
    db = load_db(); data = db["app_links"].get(uid)
    if not data: return "EXPIRED"
    if data.get("banned"): return "BANNED"
    if time.time() > data.get("end_time", 0): return "EXPIRED"
    return "ACTIVE" 

@app.route('/get_news') 
def get_news():
    return load_db().get("global_news", "لا توجد أخبار")

# --- [ كود التليجرام (كما هو بدون تغيير) ] ---
@bot.message_handler(commands=['start'])
def start(m):
    # ... (نفس كود التليجرام الذي أرسلته أنت تماماً) ...
    db = load_db(); uid = str(m.from_user.id)
    if uid not in db["users"]: db["users"][uid] = {"current_app": None}
    args = m.text.split()
    if len(args) > 1:
        cid = args[1]
        if cid not in db["app_links"]:
            db["app_links"][cid] = {"end_time": 0, "banned": False, "trial_used": False, "telegram_id": uid}
        db["app_links"][cid]["telegram_id"] = uid; db["users"][uid]["current_app"] = cid; save_db(db)
        bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**", parse_mode="Markdown")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
               types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
               types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
               types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy"))
    bot.send_message(m.chat.id, f"مرحباً بك يا **نجم الإبداع** 🌟\nاستخدم القائمة أدناه للتحكم في اشتراكاتك:", reply_markup=markup, parse_mode="Markdown")

# (بقية دوال الإدارة والمدير "نجم1" تضاف هنا كما هي في كودك الأصلي)
# [ملاحظة: لقد قمت بدمج المنطقين في ملف واحد ليعمل السيرفر على تليجرام وواتساب معاً]

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    # ... (نفس كود لوحة الإدارة الخاص بك) ...
    db = load_db(); active_now = sum(1 for x in db["app_links"].values() if x.get("end_time", 0) > time.time())
    msg = (f"👑 **إدارة نجم الإبداع**\n\n👥 المستخدمين: `{len(db['users'])}`\n⚡ الأجهزة: `{len(db['app_links'])}`\n"
           f"🟢 النشطين: `{active_now}`\n🎫 الأكواد: `{len(db['vouchers'])}` \n")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📋 عرض وتفاصيل المشتركين", callback_data="list_all"),
               types.InlineKeyboardButton("🎫 توليد كود مخصص", callback_data="gen_key"),
               types.InlineKeyboardButton("🚫 حظر جهاز", callback_data="ban_op"),
               types.InlineKeyboardButton("✅ فك حظر", callback_data="unban_op"),
               types.InlineKeyboardButton("📢 إعلان تطبيق", callback_data="bc_app"),
               types.InlineKeyboardButton("📢 إعلان تلجرام", callback_data="bc_tele"))
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- [ التشغيل ] ---
def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
