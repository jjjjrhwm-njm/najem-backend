import google.generativeai as genai
import requests
from flask import Flask, request
import os

app = Flask(__name__)

# بياناتك الخاصة بمشروع نجم الإبداع
GEMINI_KEY = "AIzaSyD7z3i-eKGO8_CxSobufqdQgdhlCBBl9xg"
INSTANCE_ID = "159896"
TOKEN = "3a2kuk39wf15ejiu"

# إعداد Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-pro')

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    # هذا السطر سيطبع البيانات الواردة في سجلات Render لنراها بوضوح
    print(f"📥 بيانات واردة من UltraMsg: {data}")

    # التحقق من وجود بيانات الرسالة
    if data and 'data' in data:
        msg_body = data['data'].get('body')
        sender_id = data['data'].get('from')
        
        if msg_body:
            try:
                print(f"🧠 جاري توليد رد ذكي للرسالة: {msg_body}")
                prompt = f"أنت مساعد ذكي لراشد مطور نجم الإبداع. رد بلهجة سعودية: {msg_body}"
                ai_response = model.generate_content(prompt)
                
                print(f"📤 الرد الجاهز من Gemini: {ai_response.text}")
                
                # إرسال الرد عبر UltraMsg
                url = f"https://api.ultramsg.com/instance{INSTANCE_ID}/messages/chat"
                payload = {
                    "token": TOKEN,
                    "to": sender_id,
                    "body": ai_response.text
                }
                
                # إرسال الطلب كـ Form Data (أفضل توافق مع UltraMsg)
                response = requests.post(url, data=payload)
                print(f"📡 رد UltraMsg على طلبنا: {response.text}")
                
            except Exception as e:
                print(f"❌ خطأ داخلي في المعالجة: {str(e)}")
    else:
        print("⚠️ البيانات المستلمة لا تحتوي على رسالة صالحة.")
                
    return "OK", 200

if __name__ == "__main__":
    # Render يتطلب الاستماع للمنفذ الذي يحدده تلقائياً
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
