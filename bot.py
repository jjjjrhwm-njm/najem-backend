import telebot
from telebot import types
from flask import Flask, request, jsonify
import json, os, time, uuid
import requests
import google.generativeai as genai
from threading import Thread, Lock 

# --- [ إعدادات تليجرام - نجم الإبداع ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json" 

# --- [ إعدادات واتساب - njm_ai ] ---
WHATSAPP_TOKEN = 'EAAPog02BAUMBQfVGjaxZChGdUjDwhLLrb6nA8G6opjsAwNqcCk5T3sc2ajs3Vllnq6w8ZAdy7bXhodz8FgiJ5yVfdS7F4EBEK9sAO2uvGjpCPrPNsZB58fKLpiyygIeFyTY2Og8mNis1ZBM1tp5E2EqjUYfjmg2OnNgSHhlZAGNR495RXt9ZCCnkCtdi1izqDb7aX9rHAJm3aruTE9x1gNShPf6gf49akVVdeYULnfZAaZAsOzVLHJ6bZC78eZAwVZCmo8kI8jZAtM7WTK4X9N9cO0oAQ5nc'
PHONE_NUMBER_ID = '969461516243161'
VERIFY_TOKEN = 'NJM_CREATIVE_TOKEN'

# --- [ إعدادات Gemini الذكية ] ---
GEMINI_KEY = 'AIzaSyD7z3i-eKGO8_CxSobufqdQgdhlCBBl9xg' 

# تشغيل محرك الذكاء الاصطناعي
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
    try:
        requests.post(url, headers=headers, json=data)
    except Exception as e:
        print(f"WhatsApp Send Error: {e}")

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): 
            return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً"}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: 
                db = json.load(f)
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار حالياً"}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4) 

# --- [ واجهات الـ Webhooks لربط واتساب وتليجرام ] ---

@app.route('/whatsapp', methods=['GET'])
def verify_whatsapp():
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
            
            # الرد الذكي باستخدام Gemini
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
    if not data or data.get("banned") or time.time() > data.get("end_time", 0): return "EXPIRED"
    return "ACTIVE" 

@app.route('/get_news') 
def get_news():
    return load_db().get("global_news", "لا توجد أخبار")

# --- [ كود تليجرام وإدارة المشتركين ] ---

@bot.message_handler(commands=['start'])
def start(m):
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

@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id); db = load_db()
    if q.data == "u_dashboard": user_dashboard(q.message)
    elif q.data == "u_redeem":
        msg = bot.send_message(q.message.chat.id, "🎫 **أرسل كود التفعيل الآن:**")
        bot.register_next_step_handler(msg, redeem_final)
    elif q.data == "u_trial": process_trial(q.message)
    elif q.data == "u_buy": send_payment(q.message)
    elif q.from_user.id == ADMIN_ID:
        if q.data == "list_all": show_detailed_users(q.message)
        elif q.data == "gen_key":
            msg = bot.send_message(q.message.chat.id, "كم عدد الأيام؟")
            bot.register_next_step_handler(msg, process_gen_key)
        elif q.data == "bc_tele":
            msg = bot.send_message(q.message.chat.id, "ارسل الإذاعة:")
            bot.register_next_step_handler(msg, do_bc_tele)
        elif q.data == "bc_app":
            msg = bot.send_message(q.message.chat.id, "ارسل الخبر:")
            bot.register_next_step_handler(msg, do_bc_app)

@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db(); active_now = sum(1 for x in db["app_links"].values() if x.get("end_time", 0) > time.time())
    msg = (f"👑 **إدارة نجم الإبداع**\n\n👥 المستخدمين: `{len(db['users'])}`\n⚡ الأجهزة: `{len(db['app_links'])}`\n"
           f"🟢 النشطين: `{active_now}`\n🎫 الأكواد: `{len(db['vouchers'])}` \n")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📋 عرض وتفاصيل المشتركين", callback_data="list_all"),
               types.InlineKeyboardButton("🎫 توليد كود مخصص", callback_data="gen_key"),
               types.InlineKeyboardButton("📢 إعلان تطبيق", callback_data="bc_app"),
               types.InlineKeyboardButton("📢 إعلان تلجرام", callback_data="bc_tele"))
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- وظائف المستخدم والإدارة (تكملة) ---
def user_dashboard(m):
    db = load_db(); uid = str(m.chat.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps: return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة.")
    msg = "👤 **حالة اشتراكاتك:**\n"
    for cid in user_apps:
        data = db["app_links"][cid]; pkg = cid.split('_', 1)[-1].replace("_", ".")
        rem_time = data.get("end_time", 0) - time.time()
        status = f"✅ {int(rem_time/86400)} يوم" if rem_time > 0 else "❌ منتهي"
        msg += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📦 `{pkg}`\nStatus: {status}\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

def redeem_final(m):
    code, db = m.text.strip(), load_db()
    if code in db["vouchers"]:
        days = db["vouchers"].pop(code); cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
        if cid:
            db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (days * 86400)
            save_db(db); bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم!")
        else: bot.send_message(m.chat.id, "❌ ادخل للتطبيق أولاً.")
    else: bot.send_message(m.chat.id, "❌ كود خاطئ.")

def process_trial(m):
    db = load_db(); cid = db["users"].get(str(m.chat.id), {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ اربط التطبيق.")
    if db["app_links"][cid].get("trial_used"): bot.send_message(m.chat.id, "❌ استخدمت التجربة.")
    else:
        db["app_links"][cid].update({"trial_used": True, "end_time": time.time() + 7200})
        save_db(db); bot.send_message(m.chat.id, "✅ تم تفعيل ساعتين تجربة!")

def do_bc_tele(m):
    db = load_db(); count = 0
    for uid in db["users"]:
        try: bot.send_message(uid, f"📢 **إشعار:**\n\n{m.text}"); count += 1
        except: pass
    bot.send_message(m.chat.id, f"✅ تم الإرسال لـ {count}")

def do_bc_app(m):
    db = load_db(); db["global_news"] = m.text; save_db(db)
    bot.send_message(m.chat.id, "✅ تم تحديث خبر التطبيق.")

def process_gen_key(m):
    if not m.text.isdigit(): return bot.send_message(m.chat.id, "⚠️ ارسل رقم فقط.")
    days = int(m.text); code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
    db = load_db(); db["vouchers"][code] = days; save_db(db)
    bot.send_message(m.chat.id, f"🎫 كود جديد: `{code}`", parse_mode="Markdown")

def show_detailed_users(m):
    db = load_db()
    if not db["app_links"]: return bot.send_message(m.chat.id, "لا توجد أجهزة.")
    res = "📂 المشتركين:\n"
    for cid, data in db["app_links"].items():
        rem = data.get("end_time", 0) - time.time()
        res += f"`{cid}` -> {int(rem/86400) if rem > 0 else 0} يوم\n"
    bot.send_message(m.chat.id, res[:4000], parse_mode="Markdown")

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
