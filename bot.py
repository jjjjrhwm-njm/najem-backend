import telebot
from telebot import types
from flask import Flask, request, jsonify
from flask_cors import CORS # مضاف لخدمة المسلسلات
import json, os, time, uuid, requests # مضاف requests
from threading import Thread, Lock 

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
CHANNEL_ID = "@jrhwm0njm" 
DATA_FILE = "master_control.json" # تم التعديل حسب ملفك

# مفتاح TMDB الخاص بمشروع المسلسلات
TMDB_API_KEY = "4765acb8727abd98a0ef375f4f2ec8bf"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
CORS(app) # مضاف للسماح بفتح المسلسلات داخل التطبيق
db_lock = Lock() 

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE): 
            return {"users": {}, "app_links": {}, "vouchers": {}, "app_news": {}, "logs": [], "referrals": {}, "app_updates": {}}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: 
                db = json.load(f)
                keys = ["app_news", "vouchers", "logs", "referrals", "users", "app_links", "app_updates"]
                for key in keys:
                    if key not in db: db[key] = {} if key != "logs" else []
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "app_news": {}, "logs": [], "referrals": {}, "app_updates": {}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4) 

def add_log(text):
    db = load_db()
    db["logs"].append(f"[{time.strftime('%Y-%m-%d %H:%M')}] {text}")
    if len(db["logs"]) > 100: db["logs"].pop(0)
    save_db(db)

def check_membership(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False

# --- [ واجهة API المحدثة + ميزة المسلسلات ] ---

@app.route('/get-drama', methods=['GET'])
def get_automated_drama():
    tmdb_url = f"https://api.themoviedb.org/3/discover/tv?api_key={TMDB_API_KEY}&with_original_language=zh&sort_by=popularity.desc"
    try:
        response = requests.get(tmdb_url)
        data = response.json()
        library = []
        for item in data.get('results', []):
            library.append({
                "title": item.get('name') or item.get('original_name'),
                "poster": f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}",
                "episodes": [
                    {"name": "سيرفر 1", "url": f"https://vidsrc.to/embed/tv/{item.get('id')}/1/1"},
                    {"name": "سيرفر 2", "url": f"https://embed.su/embed/tv/{item.get('id')}/1/1"}
                ]
            })
        return jsonify(library)
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

@app.route('/get_news') 
def get_news():
    pkg = request.args.get('pkg')
    if not pkg: return "لا توجد أخبار"
    db = load_db()
    return db.get("app_news", {}).get(pkg, "لا توجد أخبار لهذا التطبيق")

@app.route('/check_update')
def check_update():
    pkg = request.args.get('pkg')
    if not pkg: return json.dumps({"v": "1.0", "url": "none"})
    db = load_db()
    return json.dumps(db.get("app_updates", {}).get(pkg, {"v": "1.0", "url": "none"}))

# --- [ واجهة البوت - البداية ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    username = f"@{m.from_user.username}" if m.from_user.username else m.from_user.first_name
    
    args = m.text.split()
    is_new_user = uid not in db["users"]
    
    if is_new_user:
        inviter_id = args[1] if len(args) > 1 and args[1].isdigit() and args[1] != uid else None
        db["users"][uid] = {"current_app": None, "name": username, "invited_by": inviter_id, "referral_count": 0, "claimed_channel_gift": False, "join_date": time.time()}
    else:
        db["users"][uid]["name"] = username

    if len(args) > 1 and "_" in args[1]:
        cid = args[1]
        if cid not in db["app_links"]:
            db["app_links"][cid] = {"end_time": 0, "banned": False, "trial_last_time": 0, "telegram_id": uid, "gift_claimed": False}
        db["app_links"][cid]["telegram_id"] = uid
        db["users"][uid]["current_app"] = cid
        
        if check_membership(uid) and not db["app_links"][cid].get("gift_claimed"):
            db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (3 * 86400)
            db["app_links"][cid]["gift_claimed"] = True
            bot.send_message(m.chat.id, "🎁 **مبروك! حصلت على 3 أيام مجانية.**", parse_mode="Markdown")
    
    save_db(db)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🔴 انضم للقناه 🔴", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}"))
    markup.add(
        types.InlineKeyboardButton("📱 تطبيقاتي ورصيدي", callback_data="u_dashboard"),
        types.InlineKeyboardButton("🎫 تفعيل كود", callback_data="u_redeem"),
        types.InlineKeyboardButton("🔗 إحالاتي ومكافآتي", callback_data="u_referral"),
        types.InlineKeyboardButton("🎁 تجربة مجانية", callback_data="u_trial"),
        types.InlineKeyboardButton("🛒 شراء اشتراك", callback_data="u_buy")
    )
    bot.send_message(m.chat.id, f"مرحباً بك يا **{username}** 🌟", reply_markup=markup, parse_mode="Markdown")

# --- [ بقية وظائف الكود كما هي تماماً ] ---

@bot.callback_query_handler(func=lambda q: True)
def handle_calls(q):
    uid = str(q.from_user.id)
    db = load_db()

    if q.data == "u_dashboard": user_dashboard(q.message)
    elif q.data == "u_referral": show_referral_info(q.message)
    elif q.data == "u_redeem":
        msg = bot.send_message(q.message.chat.id, "🎫 **أرسل كود التفعيل:**")
        bot.register_next_step_handler(msg, redeem_code_step)
    elif q.data.startswith("redeem_select_"): redeem_select_app(q.message, q.data.replace("redeem_select_", ""))
    elif q.data == "u_trial": process_trial(q.message)
    elif q.data.startswith("trial_select_"): trial_select_app(q.message, q.data.replace("trial_select_", ""))
    elif q.data == "u_buy": send_payment(q.message)
    elif q.from_user.id == ADMIN_ID:
        if q.data == "list_all": show_detailed_users(q.message)
        elif q.data == "admin_logs": show_logs(q.message)
        elif q.data == "gen_key":
            msg = bot.send_message(q.message.chat.id, "كم يوم؟")
            bot.register_next_step_handler(msg, process_gen_key)
        elif q.data == "db_backup":
            with open(DATA_FILE, "rb") as f: bot.send_document(q.message.chat.id, f)

# (تكملة الوظائف بنفس المنطق السابق...)
def user_dashboard(m):
    db = load_db(); uid = str(m.chat.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps: return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات.")
    msg = "👤 **حالة اشتراكاتك:**\n"
    for cid in user_apps:
        data = db["app_links"][cid]; pkg = cid.split('_', 1)[-1].replace("_", ".")
        rem_time = data.get("end_time", 0) - time.time()
        status = f"✅ {int(rem_time/86400)} يوم" if rem_time > 0 else "❌ منتهي"
        msg += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📦 `{pkg}`\nالحالة: {status}\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

def redeem_code_step(m):
    code = m.text.strip(); db = load_db()
    if code not in db["vouchers"]: return bot.send_message(m.chat.id, "❌ كود خطأ.")
    uid = str(m.from_user.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps: return bot.send_message(m.chat.id, "❌ اربط جهازك أولاً.")
    db["users"][uid]["temp_code"] = code; save_db(db)
    markup = types.InlineKeyboardMarkup(); [markup.add(types.InlineKeyboardButton(f"📦 {c.split('_')[-1]}", callback_data=f"redeem_select_{c}")) for c in user_apps]
    bot.send_message(m.chat.id, "🛠️ اختر التطبيق:", reply_markup=markup)

def redeem_select_app(m, selected_cid):
    db = load_db(); uid = str(m.chat.id); code = db["users"].get(uid, {}).pop("temp_code", None)
    if not code: return
    days = db["vouchers"].pop(code); db["app_links"][selected_cid]["end_time"] = max(time.time(), db["app_links"][selected_cid].get("end_time", 0)) + (days * 86400)
    save_db(db); bot.send_message(m.chat.id, f"✅ تم تفعيل {days} يوم!")

def show_referral_info(m):
    uid = str(m.chat.id); db = load_db(); ref_link = f"https://t.me/{bot.get_me().username}?start={uid}"
    bot.send_message(m.chat.id, f"🔗 رابط إحالتك:\n`{ref_link}`", parse_mode="Markdown")

def process_trial(m):
    db = load_db(); uid = str(m.chat.id); user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps: return bot.send_message(m.chat.id, "❌ لا يوجد تطبيق.")
    markup = types.InlineKeyboardMarkup(); [markup.add(types.InlineKeyboardButton(f"📦 {c.split('_')[-1]}", callback_data=f"trial_select_{c}")) for c in user_apps]
    bot.send_message(m.chat.id, "🛠️ اختر تطبيق التجربة:", reply_markup=markup)

def trial_select_app(m, selected_cid):
    db = load_db(); data = db["app_links"].get(selected_cid)
    if not data: return
    data["end_time"] = max(time.time(), data.get("end_time", 0)) + 604800 # أسبوع
    save_db(db); bot.send_message(m.chat.id, "✅ تم تفعيل أسبوع مجاني!")

def send_payment(m):
    bot.send_message(m.chat.id, "🛒 تواصل مع الإدارة للشراء حالياً.")

def process_gen_key(m):
    if not m.text.isdigit(): return
    days = int(m.text); code = f"NJM-{str(uuid.uuid4())[:8].upper()}"; db = load_db(); db["vouchers"][code] = days; save_db(db)
    bot.send_message(m.chat.id, f"🎫 كود: `{code}`", parse_mode="Markdown")

def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
