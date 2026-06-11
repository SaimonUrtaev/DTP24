#!/usr/bin/env python3
"""
Telegram Bot @DTP24_bot — Убыток дежурного
"""

import logging
import os
import functools
from telegram import (
    Update,
    KeyboardButton, ReplyKeyboardMarkup, WebAppInfo,
)
from telegram.ext import (
    Application, CommandHandler,
    ContextTypes, PicklePersistence,
)
from config import BOT_TOKEN, ALLOWED_USERS, WEBAPP_URL

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Авторизация ──────────────────────────────────────────────────────────────
def auth_required(func):
    @functools.wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ALLOWED_USERS:
            await update.effective_message.reply_text("⛔️ Доступ запрещён.")
            return
        return await func(update, ctx)
    return wrapper


# ── /start ───────────────────────────────────────────────────────────────────
@auth_required
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("📋 Новый убыток", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! 👋\n\n"
        "Нажмите кнопку чтобы открыть форму убытка.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )


# ── Запуск ───────────────────────────────────────────────────────────────────
def main():
    persistence = PicklePersistence(filepath=os.path.join(os.path.dirname(__file__), "bot_data.pickle"))
    app = Application.builder().token(BOT_TOKEN).persistence(persistence).build()
    app.add_handler(CommandHandler("start", cmd_start))
    logger.info("Бот @DTP24_bot запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
