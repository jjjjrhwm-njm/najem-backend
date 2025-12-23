import telebot
from telebot import types

# ⚠️ تأكد من تغيير التوكن إذا قمت بعمل Revoke له
API_TOKEN = '7521759893:AAH28CRVEspDrmJR4ihqpsBViKorwO3kNlA'
CHANNEL_NAME = '@nejm_njm'
bot = telebot.TeleBot(API_TOKEN)

# 👑 قائمة المطورين
DEV_DEVICES = ["f647c0b0a1b2c3d4"]

@bot.message_handler(commands=['start'])
def start(message):
    text_parts = message.text.split()
    if len(text_parts) > 1 and "subscribe_" in text_parts[1]:
        device_id = text_parts[1].split("_")[1]
    else:
        bot.send_message(message.chat.id, "⚠️ يرجى فتح البوت من خلال التطبيق.")
        return

    if device_id in DEV_DEVICES:
        bot.send_message(CHANNEL_NAME, f"Life:FOREVER|Device:{device_id}")
        bot.send_message(message.chat.id, "👑 تم تفعيل جهازك مدى الحياة.")
        return

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🌟 شراء (30 يوم)", callback_data=f"pay_{device_id}"))
    markup.add(types.InlineKeyboardButton("⏳ تجربة مجانية", callback_data=f"trial_{device_id}"))
    bot.send_message(message.chat.id, f"📱 جهازك: `{device_id}`", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def handle_btns(call):
    data = call.data.split("_")
    action, device_id = data[0], data[1]
    if action == "trial":
        bot.send_message(CHANNEL_NAME, f"Life:24H|Device:{device_id}")
        bot.answer_callback_query(call.id, "تم التفعيل!")
        bot.edit_message_text("✅ تم تفعيل النسخة التجريبية.", call.message.chat.id, call.message.message_id)
    elif action == "pay":
        bot.send_invoice(call.message.chat.id, "اشتراك", "تفعيل 30 يوم", device_id, "", "XTR", [types.LabeledPrice("السعر", 100)])

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_ok(message):
    device_id = message.successful_payment.invoice_payload
    bot.send_message(CHANNEL_NAME, f"Life:30D|Device:{device_id}")
    bot.send_message(message.chat.id, "✅ تم الشراء بنجاح!")

bot.infinity_polling()
