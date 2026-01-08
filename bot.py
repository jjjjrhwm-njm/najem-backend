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

# إعدادات شت شورت (SSH) المستخرجة
SSH_BASE_URL = "https://dramapi.mediaradiance.com"
SSH_KEY = b"a!cd(f1h6jk0m7o3" # مفتاح AES السري
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

# --- [ وظائف المساعدة والفك ] ---

def decrypt_ssh(encrypted_base64):
    """فك تشفير AES-CBC لبيانات شت شورت"""
    try:
        raw_data = base64.b64decode(encrypted_base64)
        iv = raw_data[:16] # أول 16 بايت هي IV
        ciphertext = raw_data[16:]
        cipher = AES.new(SSH_KEY, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return json.loads(decrypted.decode('utf-8'))
    except Exception as e:
        print(f"Decryption Error: {e}")
        return None

def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE):
            return {"users": {}, "app_links": {}, "vouchers": {}, "app_news": {}, "logs": [], "referrals": {}, "app_updates": {}, "config": {}}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"users": {}, "app_links": {}, "vouchers": {}, "app_news": {}, "logs": [], "referrals": {}, "app_updates": {}, "config": {}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)

def check_membership(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False

# --- [ واجهات الـ API للتطبيق ] ---

@app.route('/get-drama', methods=['GET'])
def get_shotshort_list():
    """جلب قائمة المسلسلات من شت شورت وفك تشفيرها"""
    payload = {"page": 1, "pageSize": 50}
    try:
        response = requests.post(f"{SSH_BASE_URL}/app/drama/list", json=payload, headers=SSH_HEADERS, timeout=10)
        res_json = response.json()
        
        # فك التشفير إذا كان الحقل مفعل
        if res_json.get("isEncrypt"):
            data = decrypt_ssh(res_json.get("data"))
        else:
            data = res_json.get("data")
            
        # تجهيز قائمة نظيفة للتطبيق
        library = []
        for item in data.get('list', []):
            library.append({
                "id": item.get('bookId'),
                "title": item.get('bookName'),
                "poster": item.get('coverUrl'),
                "desc": item.get('plot'),
                "status": "مكتمل" if item.get('isCompleted') == 1 else "مستمر"
            })
        return jsonify(library)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get-episodes', methods=['GET'])
def get_shotshort_episodes():
    """جلب الحلقات لمسلسل معين"""
    book_id = request.args.get('id')
    if not book_id: return jsonify([])
    
    payload = {"bookId": book_id}
    try:
        response = requests.post(f"{SSH_BASE_URL}/app/drama/episodes", json=payload, headers=SSH_HEADERS, timeout=10)
        res_json = response.json()
        
        if res_json.get("isEncrypt"):
            data = decrypt_ssh(res_json.get("data"))
        else:
            data = res_json.get("data")
            
        clean_episodes = []
        for ep in data:
            clean_episodes.append({
                "name": f"الحلقة {ep.get('chapterOrder')}",
                "url": ep.get('sdUrl'), # الرابط المباشر
                "is_vip": ep.get('isVipEpisode') == True
            })
        return jsonify(clean_episodes)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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

# --- [ واجهة البوت - التلجرام ] ---

@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    username = f"@{m.from_user.username}" if m.from_user.username else m.from_user.first_name
    
    # تسجيل المستخدم
    if uid not in db["users"]:
        db["users"][uid] = {"name": username, "join_date": time.time()}
    save_db(db)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📱 تطبيقاتي", callback_data="u_dashboard"),
        types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
        types.InlineKeyboardButton("📢 قناة التحديثات", url=f"https://t.me/{CHANNEL_ID.replace('@','')}")
    )
    
    bot.send_message(m.chat.id, f"🌟 مرحباً بك في **دراما الإبداع**\n\nإدارة اشتراكاتك والوصول للمسلسلات الحصرية من هنا.", 
                     reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    db = load_db()

    if q.data == "u_dashboard":
        user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
        if not user_apps:
            bot.send_message(q.message.chat.id, "❌ ليس لديك تطبيقات مرتبطة بعد.")
            return
        
        msg = "👤 **اشتراكاتك النشطة:**\n"
        for cid in user_apps:
            data = db["app_links"][cid]
            pkg = cid.split('_', 1)[-1].replace("_", ".")
            rem_time = data.get("end_time", 0) - time.time()
            days = int(rem_time/86400) if rem_time > 0 else 0
            msg += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📦 `{pkg}`\n⏳ المتبقي: {days} يوم\n"
        bot.send_message(q.message.chat.id, msg, parse_mode="Markdown")

    elif q.data == "u_redeem":
        msg = bot.send_message(q.message.chat.id, "🎫 **أرسل كود التفعيل الخاص بك الآن:**")
        bot.register_next_step_handler(msg, redeem_code_step)

def redeem_code_step(m):
    code = m.text.strip()
    db = load_db()
    if code not in db["vouchers"]:
        bot.send_message(m.chat.id, "❌ الكود غير صحيح أو تم استخدامه.")
        return
    
    # هنا يمكن إضافة منطق اختيار التطبيق أو التفعيل المباشر
    days = db["vouchers"].pop(code)
    save_db(db)
    bot.send_message(m.chat.id, f"✅ تم بنجاح! تم شحن {days} يوم في رصيدك.")

# --- [ تشغيل السيرفر ] ---
def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
