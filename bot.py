#!/usr/bin/env python3
"""
Telegram Bot @DTP24_bot — Убыток дежурного
WebApp форма + запись в Google Sheets (Лист1)
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, filters, ContextTypes
)
from config import BOT_TOKEN, ALLOWED_USERS

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

WEBAPP_URL = "https://SaimonUrtaev.github.io/DTP24/form.html"


# ── Авторизация ────────────────────────────────────────────────────────────
def auth_required(func):
    import functools
    @functools.wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ALLOWED_USERS:
            await update.effective_message.reply_text(
                "⛔️ Доступ запрещён.\n"
                "Обратитесь к администратору, чтобы вас добавили в список сотрудников."
            )
            return
        return await func(update, ctx)
    return wrapper


# ── /start ─────────────────────────────────────────────────────────────────
@auth_required
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton(
            "📋 Новый убыток",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
    ]]
    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! 👋\n\n"
        "Нажмите кнопку чтобы открыть форму убытка.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── Запуск ─────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    logger.info("Бот @DTP24_bot запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
