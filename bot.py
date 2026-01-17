import telebot
from telebot import types
from flask import Flask, request, render_template_string
import json, os, time, uuid
from threading import Thread
import firebase_admin
from firebase_admin import credentials, firestore

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
CHANNEL_ID = os.environ.get('CHANNEL_ID') 

if not firebase_admin._apps:
    cred_val = os.environ.get('FIREBASE_CREDENTIALS')
    if cred_val:
        try:
            cred_dict = json.loads(cred_val)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            print(f"Error: {e}")

db_fs = firestore.client()
bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# --- [ إدارة قاعدة البيانات ] ---
def get_user(uid):
    doc = db_fs.collection("users").document(str(uid)).get()
    return doc.to_dict() if doc.exists else None

def update_user(uid, data):
    db_fs.collection("users").document(str(uid)).set(data, merge=True)

def get_app_link(cid):
    doc = db_fs.collection("app_links").document(str(cid)).get()
    return doc.to_dict() if doc.exists else None

def update_app_link(cid, data):
    db_fs.collection("app_links").document(str(cid)).set(data, merge=True)

def get_voucher(code):
    doc = db_fs.collection("vouchers").document(str(code)).get()
    return doc.to_dict() if doc.exists else None

def delete_voucher(code):
    db_fs.collection("vouchers").document(str(code)).delete()

def add_log(text):
    db_fs.collection("logs").add({
        "text": f"[{time.strftime('%Y-%m-%d %H:%M')}] {text}",
        "timestamp": time.time()
    })

def get_global_news():
    doc = db_fs.collection("config").document("global").get()
    return doc.to_dict().get("global_news", "لا توجد أخبار") if doc.exists else "لا توجد أخبار"

def set_global_news(text):
    db_fs.collection("config").document("global").set({"global_news": text}, merge=True)

def check_membership(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False 

@app.route('/check')
def check_status():
    aid, pkg = request.args.get('aid'), request.args.get('pkg')
    if not aid or not pkg: return "EXPIRED"
    cid = f"{aid}_{pkg.replace('.', '_')}"
    data = get_app_link(cid)
    if not data: return "EXPIRED"
    if data.get("banned"): return "BANNED"
    if time.time() > data.get("end_time", 0): return "EXPIRED"
    return "ACTIVE" 

@app.route('/ui')
def server_ui():
    aid = request.args.get('aid', 'UNKNOWN')
    pkg = request.args.get('pkg', 'UNKNOWN')
    news = get_global_news()
    html = f"""
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ background: #000; color: white; font-family: sans-serif; text-align: center; padding: 20px; }}
            .card {{ background: #111; border: 1px solid #333; padding: 20px; border-radius: 20px; }}
            .btn {{ display: block; background: #007aff; color: white; text-decoration: none; padding: 15px; margin: 10px 0; border-radius: 12px; font-weight: bold; }}
            .news {{ color: #00d2ff; font-size: 14px; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>🌟 نجم الإبداع</h2>
            <p class="news">{news}</p>
            <a href="tg://resolve?domain=Njm_Store_Bot&start=TRIAL_{aid}_{pkg.replace('.','_')}" class="btn">🎁 تجربة مجانية</a>
            <a href="tg://resolve?domain=Njm_Store_Bot&start=BUY_{aid}_{pkg.replace('.','_')}" class="btn">🛒 شراء اشتراك</a>
            <a href="tg://resolve?domain=Njm_Store_Bot&start=REDEEM_{aid}_{pkg.replace('.','_')}" class="btn">🎫 تفعيل كود</a>
            <a href="tg://resolve?domain=Njm_Store_Bot&start=DASH_{aid}_{pkg.replace('.','_')}" class="btn">💰 الحساب</a>
        </div>
    </body>
    </html>
    """
    return html

@bot.message_handler(commands=['start'])
def start(m):
    uid = str(m.from_user.id)
    username = f"@{m.from_user.username}" if m.from_user.username else m.from_user.first_name
    args = m.text.split()
    user_data = get_user(uid)
    if not user_data:
        inviter_id = args[1] if len(args) > 1 and args[1].isdigit() and args[1] != uid else None
        user_data = {"current_app": None, "name": username, "invited_by": inviter_id, "referral_count": 0, "claimed_channel_gift": False, "join_date": time.time()}
        update_user(uid, user_data)
    else: update_user(uid, {"name": username})
    if len(args) > 1:
        param = args[1]
        action = "LINK"; cid = ""
        if param.startswith("TRIAL_"): action = "TRIAL"; cid = param.replace("TRIAL_", "")
        elif param.startswith("BUY_"): action = "BUY"; cid = param.replace("BUY_", "")
        elif param.startswith("DASH_"): action = "DASH"; cid = param.replace("DASH_", "")
        elif param.startswith("REDEEM_"): action = "REDEEM"; cid = param.replace("REDEEM_", "")
        else: cid = param 
        if "_" in cid:
            link_data = get_app_link(cid) or {"end_time": 0, "banned": False, "trial_last_time": 0, "gift_claimed": False}
            link_data["telegram_id"] = uid
            update_app_link(cid, link_data)
            update_user(uid, {"current_app": cid})
            if check_membership(uid) and not link_data.get("gift_claimed"):
                link_data["end_time"] = max(time.time(), link_data.get("end_time", 0)) + (3 * 86400)
                link_data["gift_claimed"] = True
                update_app_link(cid, link_data)
                bot.send_message(m.chat.id, "🎁 تم منحك 3 أيام هدية!")
            if action == "TRIAL": return trial_select_app(m, cid)
            elif action == "BUY": return send_payment(m)
            elif action == "DASH": return user_dashboard(m)
            elif action == "REDEEM":
                msg = bot.send_message(m.chat.id, "🎫 أرسل الكود:")
                bot.register_next_step_handler(msg, redeem_code_step)
                return
    show_main_menu(m, username)

# --- [ بقية الدوال - تم إصلاح Syntax Error ] ---
def show_main_menu(m, username):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📱 تطبيقاتي", callback_data="u_dashboard"), types.InlineKeyboardButton("🎫 تفعيل", callback_data="u_redeem"))
    bot.send_message(m.chat.id, f"مرحباً {username} 🌟", reply_markup=markup)

@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    if q.data == "u_dashboard": user_dashboard(q.message)
    elif q.data == "u_redeem":
        msg = bot.send_message(q.message.chat.id, "🎫 أرسل الكود:")
        bot.register_next_step_handler(msg, redeem_code_step)

def user_dashboard(m):
    apps = db_fs.collection("app_links").where("telegram_id", "==", str(m.chat.id)).get()
    if not apps: return bot.send_message(m.chat.id, "❌ لا تطبيقات.")
    msg = "👤 اشتراكاتك:\n"
    for doc in apps: msg += f"⎯⎯⎯\n📦 `{doc.id}`\n"
    bot.send_message(m.chat.id, msg)

def redeem_code_step(m):
    code = m.text.strip()
    vdata = get_voucher(code)
    if vdata:
        bot.send_message(m.chat.id, "✅ تم التفعيل!")
        delete_voucher(code)
    else: bot.send_message(m.chat.id, "❌ خطأ.")

def trial_select_app(m, cid):
    update_app_link(cid, {"end_time": time.time() + 259200})
    bot.send_message(m.chat.id, "✅ تم تفعيل التجربة!")

def send_payment(m):
    bot.send_invoice(m.chat.id, "VIP", "اشتراك", "pay", "", "XTR", [types.LabeledPrice("VIP", 100)])

def expiry_notifier():
    while True:
        try:
            links = db_fs.collection("app_links").get()
            for d in links:
                if 0 < (d.to_dict().get("end_time", 0) - time.time()) < 86400:
                    bot.send_message(d.to_dict().get("telegram_id"), "⚠️ ينتهي غداً!")
            time.sleep(3600)
        except: time.sleep(60)

def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    Thread(target=expiry_notifier).start()
    bot.infinity_polling()
