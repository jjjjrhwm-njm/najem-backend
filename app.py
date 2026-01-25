import google.generativeai as genai
import requests
from flask import Flask, request
import os

app = Flask(__name__)

# الإعدادات الخاصة بك
GEMINI_KEY = "AIzaSyD7z3i-eKGO8_CxSobufqdQgdhlCBBl9xg"
INSTANCE_ID = "159896"
TOKEN = "3a2kuk39wf15ejiu"

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-pro')

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print(f"📥 وصلت رسالة جديدة: {data}") # سيظهر هذا في Logs رندر
    
    if data and data.get('event_type') == 'message_received':
        msg_body = data['data'].get('body')
        sender_id = data['data'].get('from')
        from_me = data['data'].get('fromMe')

        if from_me:
            print("⚠️ هذه الرسالة صادرة مني، لن أرد عليها.")
            return "OK", 200

        if msg_body:
            try:
                print(f"🧠 جاري استشارة Gemini للرد على: {msg_body}")
                prompt = f"أنت مساعد راشد مطور نجم الإبداع. رد باختصار: {msg_body}"
                ai_response = model.generate_content(prompt)
                
                print(f"📤 جاري إرسال الرد: {ai_response.text}")
                url = f"https://api.ultramsg.com/instance{INSTANCE_ID}/messages/chat"
                payload = {"token": TOKEN, "to": sender_id, "body": ai_response.text}
                
                res = requests.post(url, data=payload)
                print(f"📡 نتيجة الإرسال لـ UltraMsg: {res.text}")
                
            except Exception as e:
                print(f"❌ خطأ برمي: {e}")
                
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
