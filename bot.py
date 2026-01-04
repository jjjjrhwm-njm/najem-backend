import telebot
from telebot import types
from flask import Flask, request, jsonify
import json, os, time, uuid, requests
import google.generativeai as genai
from threading import Thread, Lock 

# --- [ إعدادات الهوية - نجم الإبداع ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_control.json"

# --- [ إعدادات واتساب و Gemini ] ---
WHATSAPP_TOKEN = 'EAAPog02BAUMBQffrWqnrx5pFCWVMYnLC3XQBwtqadJ9TMOLqzVRKbfXxXgtL85uwKoPR7CKNFGQvoeD5Dz48MpvdK66NXTgSnJdkUO3rQEmUWnqupRRZBAw0OHntNmmr6Kz9FvnZAxBMiph9w3kKYCrWRyHLHYwy0pGXOjXjEPc2clkFAZAGNkmdQalUKXSlkkFYpqLWhjqNlcp0EMlCiVhyM86NVehaGqZCGeQ4HvvOfNBB35A2iJlHPfVQtl8kujyAA8H0IW2560MBlzhk1slzjQZDZD'
PHONE_NUMBER_ID = '969461516243161'
GEMINI_KEY = 'AIzaSyD7z3i-eKGO8_CxSobufqdQgdhlCBBl9xg'
VERIFY_TOKEN = 'NJM_CREATIVE_TOKEN'

# تشغيل Gemini
genai.configure(api_key=GEMINI_KEY)
ai_model = genai.GenerativeModel('gemini-pro')

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock() 

# --- [ وظيفة إرسال الواتساب المطورة ] ---
def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try:
        response = requests.post(url, headers=headers, json=data)
        # سيطبع لك السبب الحقيقي للفشل في Render
        print(f"--- [واتساب] كود الحالة: {response.status_code}")
        print(f"--- [واتساب] رد فيسبوك: {response.text}")
    except Exception as e:
        print(f"--- [واتساب] خطأ اتصال: {e}")

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): return {"users": {}, "app_links": {}, "vouchers": {}, "global_news": "لا توجد أخبار"}
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
    # طالما لم يظهر هذا السطر في سجلات Render، ففيسبوك لم يصل إليك
    print("--- [واتساب] وصل طلب جديد من فيسبوك!") 
    data = request.get_json()
    try:
        if "messages" in data["entry"][0]["changes"][0]["value"]:
            msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
            user_msg = msg["text"]["body"]
            user_phone = msg["from"]
            
            # استدعاء Gemini
            try:
                chat_response = ai_model.generate_content(user_msg)
                reply = chat_response.text
            except: reply = "عذراً، Gemini مشغول حالياً."
            
            send_whatsapp_message(user_phone, reply)
    except Exception as e:
        print(f"--- [واتساب] خطأ معالجة: {e}")
    return "ok", 200

@app.route('/check')
def check_status(): return "ACTIVE"

# --- [ أوامر التليجرام ] ---
@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🌟 بوت **نجم الإبداع** شغال الآن!")

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    # تشغيل Flask أولاً لضمان استقبال رسائل واتساب
    Thread(target=run_flask).start()
    # حل مشكلة الـ 409: تجاهل الرسائل القديمة عند التشغيل
    print("--- البوت يستعد للعمل... ---")
    time.sleep(2) 
    bot.infinity_polling(skip_pending=True)
