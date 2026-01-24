import google.generativeai as genai
import requests
from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# --- [ بياناتك الخاصة التي استخرجناها ] ---
GEMINI_KEY = "AIzaSyD7z3i-eKGO8_CxSobufqdQgdhlCBBl9xg"
INSTANCE_ID = "159896"
TOKEN = "3a2kuk39wf15ejiu"

# إعداد Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-pro')

def send_whatsapp_reply(to_number, message_text):
    """إرسال الرد عبر UltraMsg"""
    url = f"https://api.ultramsg.com/instance{INSTANCE_ID}/messages/chat"
    payload = {
        "token": TOKEN,
        "to": to_number,
        "body": message_text
    }
    requests.post(url, data=payload)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    
    # فحص الرسائل الواردة من UltraMsg
    if data and data.get('event_type') == 'message_received':
        msg_body = data['data'].get('body')
        sender_id = data['data'].get('from')
        from_me = data['data'].get('fromMe')

        # الرد فقط إذا كانت الرسالة ليست من رقمك الشخصي
        if msg_body and not from_me:
            try:
                # تخصيص شخصية الرد (راشد مطور نجم الإبداع)
                prompt = f"أنت مساعد ذكي لراشد علي محسن صالح، مطور نجم الإبداع. رد بلهجة سعودية ودودة على: {msg_body}"
                ai_response = model.generate_content(prompt)
                
                # إرسال الرد للواتساب
                send_whatsapp_reply(sender_id, ai_response.text)
            except Exception as e:
                print(f"Error in Gemini: {e}")
                
    return "OK", 200

if __name__ == "__main__":
    # تشغيل السيرفر على المنفذ الذي يحدده Render
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
