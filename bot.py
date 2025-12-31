import telebot, json, os, time, secrets
from flask import Flask, request, jsonify
from threading import Thread

API_TOKEN = "PUT_YOUR_TOKEN"
ADMIN_ID = 7650083401
DATA_FILE = "njm_db.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# ================= DATABASE =================
def load():
    if not os.path.exists(DATA_FILE):
        return {
            "users": {},
            "banned": [],
            "codes": {},
            "config": {
                "maintenance": False,
                "version": "1.0",
                "update_url": "https://t.me/nejm_njm",
                "broadcast": "مرحبا بك 🌟"
            }
        }
    return json.load(open(DATA_FILE))

def save(d): json.dump(d, open(DATA_FILE,"w"), indent=2)

# ================= API =================
@app.route("/check")
def check():
    aid = request.args.get("aid")
    ver = request.args.get("ver")
    db = load()

    if aid in db["banned"]:
        return jsonify({"status":"banned"})

    if db["config"]["maintenance"]:
        return jsonify({"status":"maintenance"})

    if ver != db["config"]["version"]:
        return jsonify({
            "status":"update",
            "url": db["config"]["update_url"]
        })

    user = db["users"].get(aid)
    if not user:
        return jsonify({"status":"no_sub"})

    if time.time() > user["expire"]:
        return jsonify({"status":"expired"})

    return jsonify({
        "status":"ok",
        "expire": user["expire"],
        "points": user["points"],
        "broadcast": db["config"]["broadcast"]
    })

# ================= BOT =================
@bot.message_handler(commands=["start"])
def start(m):
    if m.from_user.id == ADMIN_ID:
        bot.send_message(m.chat.id,
        "👑 لوحة تحكم NJM\n\n"
        "/broadcast\n"
        "/maintenance\n"
        "/update\n"
        "/gift\n"
        "/ban\n"
        "/unban\n"
        "/stats")
    else:
        bot.send_message(m.chat.id,
        "👋 مرحبا\n"
        "💎 اشتراك شهري = 100 نجمة\n"
        "🎁 تجريبي يوم واحد\n"
        "🧩 اجمع نقاط بالدعوة")

# ---------- ADMIN ----------
@bot.message_handler(commands=["broadcast"])
def bc(m):
    if m.from_user.id!=ADMIN_ID: return
    msg = bot.send_message(m.chat.id,"اكتب الإذاعة:")
    bot.register_next_step_handler(msg,save_bc)

def save_bc(m):
    db=load()
    db["config"]["broadcast"]=m.text
    save(db)
    bot.send_message(m.chat.id,"✅ تم")

@bot.message_handler(commands=["maintenance"])
def mt(m):
    if m.from_user.id!=ADMIN_ID: return
    db=load()
    db["config"]["maintenance"]=not db["config"]["maintenance"]
    save(db)
    bot.send_message(m.chat.id,f"🛠 الصيانة = {db['config']['maintenance']}")

@bot.message_handler(commands=["update"])
def upd(m):
    if m.from_user.id!=ADMIN_ID: return
    msg=bot.send_message(m.chat.id,"الإصدار الجديد:")
    bot.register_next_step_handler(msg,upd2)

def upd2(m):
    db=load()
    db["config"]["version"]=m.text
    save(db)
    bot.send_message(m.chat.id,"⬆️ تحديث إجباري جاهز")

@bot.message_handler(commands=["gift"])
def gift(m):
    if m.from_user.id!=ADMIN_ID: return
    msg=bot.send_message(m.chat.id,"AndroidID + أيام")
    bot.register_next_step_handler(msg,gift2)

def gift2(m):
    aid,days=m.text.split()
    db=load()
    db["users"][aid]={
        "expire":time.time()+int(days)*86400,
        "points":0
    }
    save(db)
    bot.send_message(m.chat.id,"🎁 تم الإهداء")

@bot.message_handler(commands=["ban"])
def ban(m):
    if m.from_user.id!=ADMIN_ID: return
    msg=bot.send_message(m.chat.id,"AndroidID:")
    bot.register_next_step_handler(msg,ban2)

def ban2(m):
    db=load()
    db["banned"].append(m.text)
    save(db)
    bot.send_message(m.chat.id,"🚫 محظور")

@bot.message_handler(commands=["unban"])
def unban(m):
    if m.from_user.id!=ADMIN_ID: return
    msg=bot.send_message(m.chat.id,"AndroidID:")
    bot.register_next_step_handler(msg,unban2)

def unban2(m):
    db=load()
    db["banned"].remove(m.text)
    save(db)
    bot.send_message(m.chat.id,"✅ فك الحظر")

# ================= RUN =================
def run():
    app.run("0.0.0.0",8080)

Thread(target=run).start()
bot.infinity_polling()
