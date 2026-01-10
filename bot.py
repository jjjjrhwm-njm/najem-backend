import os
import time
import json
from flask import Flask
from threading import Thread
from neonize.client import NewClient
from neonize.events import MessageEvent
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, firestore

# --- [ 1. إعدادات الذكاء الاصطناعي وقاعدة البيانات ] ---
genai.configure(api_key="AIzaSyD7z3i-eKGO8_CxSobufqdQgdhlCBBl9xg")
model = genai.GenerativeModel('gemini-pro')

if not firebase_admin._apps:
    cred_val = os.environ.get('FIREBASE_CREDENTIALS')
    if cred_val:
        cred = credentials.Certificate(json.loads(cred_val))
        firebase_admin.initialize_app(cred)
db_fs = firestore.client()

# --- [ 2. إعداد سيرفر الويب (Flask) ] ---
app = Flask(__name__)

@app.route('/')
def home():
    return "WhatsApp Open Source Bot is Running!"

# --- [ 3. محرك الواتساب (Neonize) ] ---
def on_message(client: NewClient, message: MessageEvent):
    # تجاهل الرسائل التي نرسلها نحن
    if message.Info.IsFromMe:
        return

    # استخراج نص الرسالة
    text = message.Message.conversation or message.Message.extendedTextMessage.text
    sender = message.Info.Sender.String()

    if text:
        print(f"وصلت رسالة من {sender}: {text}")
        try:
            # إرسال النص لـ Gemini
            response = model.generate_content(text)
            ai_reply = response.text

            # الرد على المستخدم في واتساب
            client.send_message(message.Info.Sender, ai_reply)
            
            # حفظ العملية في Firestore
            db_fs.collection("wa_open_source_logs").add({
                "sender": sender,
                "msg": text,
                "reply": ai_reply,
                "time": time.time()
            })
        except Exception as e:
            print(f"خطأ في معالجة الرسالة: {e}")

# تهيئة العميل (سيحفظ بيانات الدخول في ملف محلي باسم wa_session.db)
client = NewClient("wa_session.db")
client.event_handlers.append(on_message)

def start_whatsapp():
    # هذا السطر هو المسؤول عن طباعة الـ QR Code في الـ Logs
    client.connect()

def start_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    # تشغيل Flask في الخلفية ليبقى السيرفر يعمل
    Thread(target=start_flask).start()
    # تشغيل محرك الواتساب
    start_whatsapp()
