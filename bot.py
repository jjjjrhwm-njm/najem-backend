import telebot
from telebot import types
from flask import Flask, request, jsonify
import json, os, time, uuid, requests
import google.generativeai as genai
from threading import Thread, Lock 

# --- [ إعدادات الهوية ] ---
# نجم الإبداع - njm
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_control.json"

# --- [ إعدادات واتساب و Gemini ] ---
WHATSAPP_TOKEN = 'EAAPog02BAUMBQSY48vvLZBOoGdt8yWSzEc26yr3EFYavrZA7Osfo2XMmkJAPtckpzfncvv10ReyWxp7yuT92fIYWUwY2oz5ugNWDppaN6mnX9UDuM7gZATvXEaDrhnxGnZBEWzRwvjVjcBzTvvqhz0PYpQGgrHX7sprQBkI5ZBrfNSEKePzjZApbVbyDtFTv4MS5ZAbNOcR5KP24XXQX1bhaOFi98gEN0lfOOyjU2eRhzVj8FNZChxvTbfy1r4qvDVgMv9MDkEflpiYRUtjqJAbLep9G'
PHONE_NUMBER_ID = '969461516243161'
GEMINI_KEY = 'AIzaSyD7z3i-eKGO8_CxSobufqdQgdhlCBBl9xg'
VERIFY_TOKEN = 'NJM_CREATIVE_TOKEN'

# تشغيل Gemini
genai.configure(api_key=GEMINI_KEY)
ai_model = genai.GenerativeModel('gemini-pro')

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock() 

# --- [ وظيفة إرسال الواتساب المطورة للتصحيح ] ---
def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        # هذه الأسطر ستظهر لك في Render Logs لتعرف سبب الفشل
        print(f"--- [واتساب] حالة الإرسال: {response.status_code}")
        print(f"--- [واتساب] الرد الفني: {response.text}")
    except Exception as e:
        print(f"--- [واتساب] خطأ فادح في الاتصال: {e}")

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): 
            return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار"}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار"}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4) 

# --- [ واجهات الـ Webhooks ] ---

@app.route('/whatsapp', methods=['GET'])
def verify_whatsapp():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN: return challenge, 200
    return "Forbidden", 403

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    data = request.get_json()
    try:
        if "messages" in data["entry"][0]["changes"][0]["value"]:
            msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
            user_msg = msg["text"]["body"]
            user_phone = msg["from"]
            
            print(f"--- [واتساب] رسالة جديدة من {user_phone}: {user_msg}")
            
            # استدعاء Gemini مع حماية من الأخطاء
            try:
                chat_response = ai_model.generate_content(user_msg)
                bot_reply = chat_response.text
            except:
                bot_reply = "عذراً، أنا أواجه ضغطاً حالياً. حاول مراسلتي لاحقاً."
            
            send_whatsapp_message(user_phone, bot_reply)
    except: pass
    return "ok", 200

# --- [ أوامر التليجرام ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db(); uid = str(m.from_user.id)
    if uid not in db["users"]: db["users"][uid] = {"current_app": None}
    save_db(db)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
               types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
               types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
               types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy"))
    bot.send_message(m.chat.id, "مرحباً بك في لوحة تحكم **نجم الإبداع** 🌟\nالبوت شغال الآن على تليجرام وواتساب!", reply_markup=markup, parse_mode="Markdown")

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    # تشغيل Flask في خيط منفصل
    Thread(target=run_flask).start()
    # تشغيل تليجرام مع حل مشكلة التضارب 409
    print("--- البوت بدأ العمل الآن بنجاح ---")
    bot.infinity_polling(skip_pending=True)
