import telebot
from telebot import types
from flask import Flask, request
import json, os, time, uuid
from threading import Thread, Lock

# --- [ الإعدادات الأساسية ] ---
API_TOKEN = '8322095833:AAEq5gd2R3HiN9agRdX-R995vHXeWx2oT7g'
ADMIN_ID = 7650083401
DATA_FILE = "master_data.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
db_lock = Lock()

# --- [ إدارة قاعدة البيانات ] ---
def load_db():
    with db_lock:
        if not os.path.exists(DATA_FILE):
            return {
                "users": {}, "app_links": {}, "vouchers": {}, 
                "settings": {"news": "مرحباً بكم في تطبيق نجم الإبداع", "price": 100, "trial_days": 2},
                "stats": {"total_revenue": 0}
            }
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
                for key in ["users", "app_links", "vouchers", "settings", "stats"]:
                    if key not in db: db[key] = {}
                return db
        except: return {"users": {}, "app_links": {}, "vouchers": {}, "settings": {}, "stats": {}}

def save_db(db):
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)

# --- [ واجهة API للتطبيقات ] ---
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
    return load_db()["settings"].get("news", "لا توجد أخبار حالياً")

# --- [ واجهة البوت - البداية ] ---
@bot.message_handler(commands=['start'])
def start(m):
    db = load_db()
    uid = str(m.from_user.id)
    if uid not in db["users"]: db["users"][uid] = {"current_app": None}
    
    args = m.text.split()
    if len(args) > 1:
        cid = args[1]
        pkg = cid.split('_', 1)[1].replace('_', '.') if '_' in cid else "غير معروف"
        db["app_links"].setdefault(cid, {"end_time": 0, "banned": False, "trial_used": False, "app_name": pkg})
        db["app_links"][cid]["telegram_id"] = uid
        db["users"][uid]["current_app"] = cid
        save_db(db)
        bot.send_message(m.chat.id, "✅ **تم ربط جهازك بنجاح!**", parse_mode="Markdown")

    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add("📱 تطبيقاتي ورصيدي", "🎫 تفعيل كود")
    menu.add("🎁 تجربة مجانية", "🛒 شراء اشتراك")
    bot.send_message(m.chat.id, f"مرحباً بك يا **نجم الإبداع** في لوحة التحكم.", reply_markup=menu, parse_mode="Markdown")

# --- [ لوحة المستخدم ] ---
@bot.message_handler(func=lambda m: m.text == "📱 تطبيقاتي ورصيدي")
def user_dashboard(m):
    db = load_db()
    uid = str(m.from_user.id)
    user_apps = [k for k, v in db["app_links"].items() if v.get("telegram_id") == uid]
    if not user_apps: return bot.send_message(m.chat.id, "❌ لا توجد أجهزة مرتبطة.")
    
    msg = "👤 **لوحة اشتراكاتك الشخصية**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    for cid in user_apps:
        data = db["app_links"][cid]
        rem_time = data.get("end_time", 0) - time.time()
        status = "✅ نشط" if rem_time > 0 else "❌ منتهي"
        if data.get("banned"): status = "🚫 محظور"
        msg += f"🖥️ تطبيق: `{data.get('app_name')}`\n📊 الحالة: {status}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

# --- [ نظام التفعيل المطور بالأزرار ] ---
@bot.message_handler(func=lambda m: m.text == "🎫 تفعيل كود")
def redeem_start(m):
    msg = bot.send_message(m.chat.id, "أرسل كود التفعيل الخاص بك:")
    bot.register_next_step_handler(msg, redeem_check_code)

def redeem_check_code(m):
    code = m.text.strip()
    db = load_db()
    if code not in db["vouchers"]:
        return bot.send_message(m.chat.id, "❌ الكود غير صحيح أو منتهي.")
    
    uid = str(m.from_user.id)
    user_apps = {k: v for k, v in db["app_links"].items() if v.get("telegram_id") == uid}
    
    if not user_apps:
        return bot.send_message(m.chat.id, "❌ لا يوجد تطبيق مرتبطة بحسابك لشحن الكود.")
    
    markup = types.InlineKeyboardMarkup()
    for cid, data in user_apps.items():
        app_name = data.get("app_name", "تطبيق غير معروف")
        markup.add(types.InlineKeyboardButton(f"✅ شحن في: {app_name}", callback_data=f"rd_app_{code}_{cid}"))
    
    bot.send_message(m.chat.id, "اختر التطبيق المراد شحن الكود فيه:", reply_markup=markup)

# --- [ نظام التجربة المجانية المطور ] ---
@bot.message_handler(func=lambda m: m.text == "🎁 تجربة مجانية")
def trial_selection(m):
    db = load_db()
    uid = str(m.from_user.id)
    user_apps = {k: v for k, v in db["app_links"].items() if v.get("telegram_id") == uid}
    if not user_apps: return bot.send_message(m.chat.id, "❌ لا توجد تطبيقات مرتبطة.")
    
    markup = types.InlineKeyboardMarkup()
    for cid, data in user_apps.items():
        markup.add(types.InlineKeyboardButton(f"🎁 تجربة: {data.get('app_name')}", callback_data=f"tr_use_{cid}"))
    bot.send_message(m.chat.id, "اختر التطبيق لتفعيل التجربة (يومين):", reply_markup=markup)

# --- [ معالجة ضغطات الأزرار ] ---
@bot.callback_query_handler(func=lambda q: q.data.startswith(('tr_use_', 'rd_app_')))
def process_callback_actions(q):
    db = load_db()
    if q.data.startswith('tr_use_'):
        cid = q.data.replace('tr_use_', '')
        if db["app_links"][cid].get("trial_used"):
            bot.answer_callback_query(q.id, "❌ استخدمت التجربة سابقاً لهذا التطبيق!", show_alert=True)
        else:
            days = db["settings"].get("trial_days", 2)
            db["app_links"][cid].update({"trial_used": True, "end_time": time.time() + (days * 86400)})
            save_db(db); bot.edit_message_text(f"✅ تم تفعيل {days} أيام تجربة بنجاح!", q.message.chat.id, q.message.message_id)
            
    elif q.data.startswith('rd_app_'):
        parts = q.data.split('_'); code = parts[2]; cid = "_".join(parts[3:])
        if code not in db["vouchers"]: return bot.answer_callback_query(q.id, "❌ الكود غير صالح.")
        voucher_data = db["vouchers"][code]
        days = voucher_data.get("days", 0)
        db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (days * 86400)
        db["vouchers"].pop(code); save_db(db)
        bot.edit_message_text(f"✅ تم الشحن بنجاح لمدة {days} يوم!", q.message.chat.id, q.message.message_id)

# --- [ لوحة الإدارة المتطورة ] ---
@bot.message_handler(func=lambda m: m.text == "نجم1" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    db = load_db()
    active = sum(1 for x in db["app_links"].values() if x.get("end_time", 0) > time.time() and not x.get("banned"))
    msg = (f"👑 **إدارة نجم الإبداع**\n\n"
           f"👥 المستخدمين: `{len(db['users'])}` | ⚡ الأجهزة: `{len(db['app_links'])}`\n"
           f"🟢 نشط حالياً: `{active}`")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎫 توليد كود", callback_data="adm_gen"),
        types.InlineKeyboardButton("🚫 حظر/فك", callback_data="adm_ban"),
        types.InlineKeyboardButton("📊 عرض الأجهزة", callback_data="adm_list"),
        types.InlineKeyboardButton("📈 إحصائيات مفصلة", callback_data="adm_stats")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda q: q.data.startswith("adm_"))
def admin_actions(q):
    if q.from_user.id != ADMIN_ID: return
    if q.data == "adm_gen":
        msg = bot.send_message(q.message.chat.id, "كم يوماً تريد للكود؟:")
        bot.register_next_step_handler(msg, process_gen_key_days)
    elif q.data == "adm_stats":
        db = load_db()
        txt = "📈 **إحصائيات المستخدمين والتطبيقات:**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        for cid, v in db["app_links"].items():
            uid = v.get("telegram_id", "0")
            try:
                user = bot.get_chat(uid)
                u_name = f"[{user.first_name}](tg://user?id={uid})"
            except: u_name = f"`{uid}`"
            
            exp = time.strftime('%Y-%m-%d', time.localtime(v.get('end_time', 0)))
            status = "🟢" if v.get('end_time', 0) > time.time() else "🔴"
            if v.get('banned'): status = "🚫"
            
            txt += f"👤: {u_name}\n🖥️: `{v.get('app_name')}`\n📅: `{exp}` {status}\n⎯⎯⎯⎯⎯⎯⎯\n"
        bot.send_message(q.message.chat.id, txt, parse_mode="Markdown")
    # بقية الأوامر كما هي في كودك...
    elif q.data == "adm_list":
        db = load_db(); txt = "📋 **آخر 10 أجهزة:**\n"
        for k, v in list(db["app_links"].items())[-10:]:
            txt += f"🔹 `{k[:10]}..` | `{v.get('app_name')}`\n"
        bot.send_message(q.message.chat.id, txt, parse_mode="Markdown")

# --- [ وظائف الإدارة ] ---
def process_gen_key_days(m):
    try:
        days = int(m.text)
        code = f"NJM-{str(uuid.uuid4())[:8].upper()}"
        db = load_db(); db["vouchers"][code] = {"days": days, "target": "عام"}; save_db(db)
        bot.send_message(m.chat.id, f"✅ تم توليد كود لـ (عام):\n`{code}`\nالمدة: {days} يوم", parse_mode="Markdown")
    except: bot.send_message(m.chat.id, "❌ خطأ في الرقم.")

def process_ban_unban(m):
    try:
        cid, action = m.text.split(); db = load_db()
        if cid in db["app_links"]:
            db["app_links"][cid]["banned"] = (action.lower() == "ban"); save_db(db)
            bot.send_message(m.chat.id, f"✅ تم التحديث بنجاح.")
        else: bot.send_message(m.chat.id, "❌ غير موجود.")
    except: bot.send_message(m.chat.id, "❌ الصيغة: cid ban")

# --- [ نظام الشراء ] ---
@bot.message_handler(func=lambda m: m.text == "🛒 شراء اشتراك")
def send_payment(m):
    db = load_db(); cid = db["users"].get(str(m.from_user.id), {}).get("current_app")
    if not cid: return bot.send_message(m.chat.id, "❌ اربط التطبيق أولاً.")
    price = db["settings"].get("price", 100)
    bot.send_invoice(m.chat.id, title="اشتراك 30 يوم", description=f"تفعيل: {cid}", 
                     invoice_payload=f"pay_{cid}", provider_token="", currency="XTR",
                     prices=[types.LabeledPrice(label="برو", amount=price)])

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_success(m):
    db = load_db(); cid = m.successful_payment.invoice_payload.replace("pay_", "")
    db["app_links"][cid]["end_time"] = max(time.time(), db["app_links"][cid].get("end_time", 0)) + (30 * 86400)
    save_db(db); bot.send_message(m.chat.id, "✅ تم الشراء!")

if __name__ == "__main__":
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))).start()
    bot.infinity_polling()
