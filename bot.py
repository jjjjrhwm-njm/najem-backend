import telebot
from telebot import types
from flask import Flask, request, jsonify
import json, os, time, uuid, requests
from threading import Thread
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai

# --- [ الإعدادات الأساسية ] ---
# واتساب (Meta)
WA_TOKEN = os.environ.get('WA_TOKEN') # التوكن الدائم الذي أرسلته
PHONE_NUMBER_ID = '969461516243161'
VERIFY_TOKEN = 'njm_secret_2026' # الكلمة السرية للتحقق في فيسبوك

# تلجرام
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
CHANNEL_ID = "@jrhwm0njm"

# ذكاء اصطناعي (Gemini)
genai.configure(api_key="AIzaSyD7z3i-eKGO8_CxSobufqdQgdhlCBBl9xg")
model = genai.GenerativeModel('gemini-pro')

# تهيئة Firebase
if not firebase_admin._apps:
    cred_val = os.environ.get('FIREBASE_CREDENTIALS')
    if cred_val:
        cred = credentials.Certificate(json.loads(cred_val))
        firebase_admin.initialize_app(cred)

db_fs = firestore.client()
bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- [ وظائف إدارة قاعدة البيانات ] ---
def get_user(uid):
    doc = db_fs.collection("users").document(str(uid)).get()
    return doc.to_dict() if doc.exists else None

def update_user(uid, data):
    db_fs.collection("users").document(str(uid)).set(data, merge=True)

def add_log(text):
    db_fs.collection("logs").add({"text": f"[{time.strftime('%Y-%m-%d %H:%M')}] {text}", "timestamp": time.time()})

# --- [ وظيفة إرسال رد واتساب ] ---
def send_whatsapp_reply(to, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    return requests.post(url, json=payload, headers=headers)

# --- [ مسار Webhook للواتساب ] ---
@app.route('/whatsapp', methods=['GET', 'POST'])
def whatsapp_webhook():
    if request.method == 'GET':
        # مرحلة التحقق من فيسبوك
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "خطأ في التحقق", 403

    # مرحلة استقبال الرسائل
    data = request.json
    try:
        if "messages" in data["entry"][0]["changes"][0]["value"]:
            message = data["entry"][0]["changes"][0]["value"]["messages"][0]
            sender_id = message["from"]
            user_text = message["text"]["body"]

            # توليد رد عبر Gemini
            response = model.generate_content(user_text)
            ai_reply = response.text

            # إرسال الرد للواتساب
            send_whatsapp_reply(sender_id, ai_reply)
            
            # حفظ المحادثة في Firestore
            db_fs.collection("wa_conversations").add({
                "sender": sender_id,
                "msg": user_text,
                "reply": ai_reply,
                "time": time.time()
            })
    except: pass
    return jsonify({"status": "ok"}), 200

# --- [ واجهة تلجرام - البداية ] ---
@bot.message_handler(commands=['start'])
def start(m):
    uid = str(m.from_user.id)
    username = f"@{m.from_user.username}" if m.from_user.username else m.from_user.first_name
    # (بقية كود التلجرام Start و Dashboard تبقى كما هي في مشروعك)
    bot.send_message(m.chat.id, f"مرحباً بك يا {username} 🌟\nتم ربط النظام بالذكاء الاصطناعي والواتساب بنجاح!")

# --- [ واجهة API للتطبيقات ] ---
@app.route('/check')
def check_status():
    aid, pkg = request.args.get('aid'), request.args.get('pkg')
    # منطق فحص الاشتراك القديم
    return "ACTIVE"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    # تشغيل Flask وتلجرام في نفس الوقت
    Thread(target=run).start()
    bot.infinity_polling()
