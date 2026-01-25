import google.generativeai as genai
import requests
from flask import Flask, request
import os

app = Flask(__name__)

# بياناتك الخاصة بمشروع نجم الإبداع
GEMINI_KEY = "AIzaSyD7z3i-eKGO8_CxSobufqdQgdhlCBBl9xg"
INSTANCE_ID = "159896"
TOKEN = "3a2kuk39wf15ejiu"

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-pro')

@app.route('/webhook', methods=['POST'])
def webhook():
    # استخدام force=True لضمان قراءة البيانات الواردة
    data = request.get_json(force=True, silent=True)
    
    if not data:
        print("⚠️ لم يتم استلام بيانات JSON صالحة.")
        return "No Data", 400

    print(f"📥 بيانات مستلمة: {data}")

    # استخراج تفاصيل الرسالة
    if 'data' in data:
        msg_body = data['data'].get('body')
        sender_id = data['data'].get('from')
        is_from_me = data['data'].get('fromMe')

        if is_from_me:
            print("🚫 هذه الرسالة صادرة مني، لن يتم الرد عليها.")
            return "OK", 200

        if msg_body and sender_id:
            try:
                print(f"🧠 جاري توليد رد لـ: {msg_body}")
                ai_response = model.generate_content(f"أنت مساعد ذكي لراشد مطور نجم الإبداع. رد باختصار: {msg_body}")
                
                print(f"📤 الرد الجاهز: {ai_response.text}")
                
                # إرسال الرد
                url = f"https://api.ultramsg.com/instance{INSTANCE_ID}/messages/chat"
                payload = {
                    "token": TOKEN,
                    "to": sender_id,
                    "body": ai_response.text
                }
                
                res = requests.post(url, data=payload)
                print(f"📡 نتيجة الإرسال لـ UltraMsg: {res.text}")
                
            except Exception as e:
                print(f"❌ خطأ برمي داخلي: {str(e)}")
                
    return "OK", 200

if __name__ == "__main__":
    # رندر يحتاج هذا المنفذ للعمل بشكل خارجي
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
