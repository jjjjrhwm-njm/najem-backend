import telebot
from telebot import types
from flask import Flask, request, jsonify
from flask_cors import CORS
import json, os, time, uuid, requests
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from threading import Thread, Lock

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
CHANNEL_ID = "@jrhwm0njm" 
DATA_FILE = "master_control.json"

# إعدادات شت شورت المستخرجة
SSH_BASE_URL = "https://dramapi.mediaradiance.com"
SSH_KEY = b"a!cd(f1h6jk0m7o3"
SSH_HEADERS = {
    "Content-Type": "application/json",
    "signCode": "549586425795197647284a19129c8086",
    "packageId": "5",
    "os": "1",
    "version": "1.1.0"
}

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
CORS(app)
db_lock = Lock() 

# --- [ دالة فك التشفير الخاصة بـ شت شورت ] ---
def decrypt_ssh(encrypted_base64):
    try:
        raw_data = base64.b64decode(encrypted_base64)
        iv = raw_data[:16]
        ciphertext = raw_data[16:]
        cipher = AES.new(SSH_KEY, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return json.loads(decrypted.decode('utf-8'))
    except Exception as e:
        print(f"Decryption Error: {e}")
        return None

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): 
            return {"users": {}, "app_links": {}, "vouchers": {}, "app_news": {}, "logs": [], "referrals": {}, "app_updates": {}}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: 
                db = json.load(f)
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "app_news": {}, "logs": [], "referrals": {}, "app_updates": {}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4) 

# --- [ واجهة API للمسلسلات - شت شورت ] ---

@app.route('/get-drama', methods=['GET'])
def get_shotshort_list():
    payload = {"page": 1, "pageSize": 30}
    try:
        response = requests.post(f"{SSH_BASE_URL}/app/drama/list", json=payload, headers=SSH_HEADERS)
        res_json = response.json()
        
        # فك التشفير إذا كان السيرفر يرسل بيانات مشفرة
        if res_json.get("isEncrypt"):
            data = decrypt_ssh(res_json.get("data"))
        else:
            data = res_json.get("data")
            
        # تنظيف البيانات للتطبيق
        clean_library = []
        for item in data.get('list', []):
            clean_library.append({
                "id": item.get('bookId'),
                "title": item.get('bookName'),
                "poster": item.get('coverUrl'),
                "desc": item.get('plot')
            })
        return jsonify(clean_library)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get-episodes', methods=['GET'])
def get_shotshort_episodes():
    book_id = request.args.get('id')
    payload = {"bookId": book_id}
    try:
        response = requests.post(f"{SSH_BASE_URL}/app/drama/episodes", json=payload, headers=SSH_HEADERS)
        res_json = response.json()
        
        if res_json.get("isEncrypt"):
            data = decrypt_ssh(res_json.get("data"))
        else:
            data = res_json.get("data")
            
        clean_episodes = []
        for ep in data:
            clean_episodes.append({
                "name": f"الحلقة {ep.get('chapterOrder')}",
                "url": ep.get('sdUrl'), # هذا هو رابط الفيديو المباشر
                "is_vip": ep.get('isVipEpisode')
            })
        return jsonify(clean_episodes)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- [ بقية وظائف البوت الأصلية ] ---
@app.route('/check')
def check_status():
    aid, pkg = request.args.get('aid'), request.args.get('pkg')
    if not aid or not pkg: return "EXPIRED"
    uid = f"{aid}_{pkg.replace('.', '_')}"
    db = load_db()
    data = db["app_links"].get(uid)
    if not data: return "EXPIRED"
    if data.get("banned"): return "BANNED"
    if time.time() > data.get("end_time", 0): return "EXPIRED"
    return "ACTIVE" 

@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    username = f"@{m.from_user.username}" if m.from_user.username else m.from_user.first_name
    db["users"][uid] = {"name": username}
    save_db(db)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
               types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"))
    bot.send_message(m.chat.id, f"مرحباً بك في دراما الإبداع 🌟", reply_markup=markup)

def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
