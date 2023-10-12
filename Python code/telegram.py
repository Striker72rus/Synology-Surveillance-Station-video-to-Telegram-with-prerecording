import os
import threading
import telebot

class TelegramBot:
    def __init__(self, token): 
        self.tg_bot = telebot.TeleBot(token)

    def start(self, update, context):
        context.bot.send_message(chat_id=update.effective_chat.id, text="Hello, World!")

    def send_message(self, chat_id, message):
        self.tg_bot.send_message(chat_id, message)

    def send_video(self, chat_id, video, mycaption):
        self.tg_bot.send_video(chat_id, video, None, None, None, None, mycaption)

    def infinity_polling(self):
        threading.Thread(target=self.tg_bot.infinity_polling, name='bot_infinity_polling', daemon=True).start()
