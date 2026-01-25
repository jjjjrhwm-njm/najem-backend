import google.generativeai as genai
import requests
from flask import Flask, request
import telebot
import os
from threading import Thread

app = Flask(__name__)

# --- [ إعدادات نجم الإبداع ] ---
GEMINI_KEY = "AIzaSyD7z3i-eKGO8_CxSobufqdQgdhlCBBl9xg"
INSTANCE_ID = "159896"
ULTRA_TOKEN = "3a2kuk39wf15ejiu"
TELE_TOKEN = "7917846549:AAGhKz_R96_BBy-6_n-uOly5vIis3T4Wc88"

# إعداد Gemini وبوت التليجرام
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-pro')
bot = telebot.TeleBot(TELE_TOKEN)

# --- [ مسار الواتساب - Webhook ] ---
@app.route('/webhook', methods=['POST'])
def whatsapp_webhook():
    data = request.get_json(force=True, silent=True)
    if data and data.get('event_type') == 'message_received':
        msg_body = data['data'].get('body')
        sender_id = data['data'].get('from')
        if not data['data'].get('fromMe') and msg_body:
            try:
                ai_res = model.generate_content(f"أنت مساعد راشد. رد باختصار: {msg_body}")
                url = f"https://api.ultramsg.com/instance{INSTANCE_ID}/messages/chat"
                requests.post(url, data={"token": ULTRA_TOKEN, "to": sender_id, "body": ai_res.text})
            except Exception as e:
                print(f"WhatsApp Error: {e}")
    return "OK", 200

# --- [ رد التليجرام ] ---
@bot.message_handler(func=lambda m: True)
def tele_reply(message):
    try:
        ai_res = model.generate_content(message.text)
        bot.reply_to(message, ai_res.text)
    except: pass

def run_tele():
    bot.infinity_polling()

if __name__ == "__main__":
    # تشغيل التليجرام في الخلفية
    Thread(target=run_tele).start()
    # تشغيل الواتساب كخدمة ويب أساسية
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
