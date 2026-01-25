import google.generativeai as genai
import requests
from flask import Flask, request
import os

app = Flask(__name__)

# إعدادات نجم الإبداع
GEMINI_KEY = "AIzaSyD7z3i-eKGO8_CxSobufqdQgdhlCBBl9xg"
INSTANCE_ID = "159896"
TOKEN = "3a2kuk39wf15ejiu"

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-pro')

# 1. صفحة اختبار (للتأكد أن الرابط يعمل في المتصفح)
@app.route('/')
def home():
    return "<h1>نجم الإبداع متصل الآن ✅</h1>", 200

# 2. مسار الواتساب (Webhook)
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True, silent=True)
    print(f"📥 بيانات مستلمة: {data}") # سيظهر هذا في Logs رندر
    
    if data and data.get('event_type') == 'message_received':
        msg_body = data['data'].get('body')
        sender_id = data['data'].get('from')
        if not data['data'].get('fromMe') and msg_body:
            try:
                # هنا فقط يبدأ عمل جيمني
                ai_res = model.generate_content(f"رد كخبير تقني سعودي: {msg_body}")
                url = f"https://api.ultramsg.com/instance{INSTANCE_ID}/messages/chat"
                requests.post(url, data={"token": TOKEN, "to": sender_id, "body": ai_res.text})
                print("✅ تم الرد بنجاح")
            except Exception as e:
                print(f"❌ خطأ جيمني: {e}")
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
