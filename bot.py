#!/usr/bin/env python3
"""
Telegram Bot @DTP24_bot — Убыток дежурного
WebApp форма + сбор фото после записи
"""

import json
import logging
import functools
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from config import BOT_TOKEN, ALLOWED_USERS

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

WEBAPP_URL = "https://SaimonUrtaev.github.io/DTP24/form.html"
PHOTO_KEY  = "collecting_photos"
LOSS_KEY   = "loss_number"


# ── Авторизация ─────────────────────────────────────────────────────────────
def auth_required(func):
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


# ── /start ───────────────────────────────────────────────────────────────────
@auth_required
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("📋 Новый убыток", web_app=WebAppInfo(url=WEBAPP_URL))
    ]]
    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! 👋\n\n"
        "Нажмите кнопку чтобы открыть форму убытка.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── Получение данных из WebApp ───────────────────────────────────────────────
@auth_required
async def web_app_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        data = json.loads(update.message.web_app_data.data)
        number = data.get("number", "?")
    except Exception:
        return

    ctx.user_data[PHOTO_KEY] = True
    ctx.user_data[LOSS_KEY]  = number
    ctx.user_data["photos"]  = []

    keyboard = [[InlineKeyboardButton("✅ Готово, фото не нужны", callback_data="photos_done")]]
    await update.message.reply_text(
        f"✅ *Убыток №{number} записан в таблицу!*\n\n"
        f"📎 Отправьте фото: место ДТП, полис, СТС, материалы.\n"
        f"Можно несколько. Когда закончите — нажмите кнопку.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── Приём фото ───────────────────────────────────────────────────────────────
async def receive_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.user_data.get(PHOTO_KEY):
        return
    if update.effective_user.id not in ALLOWED_USERS:
        return

    photos: list = ctx.user_data.setdefault("photos", [])

    if update.message.photo:
        photos.append(("photo", update.message.photo[-1].file_id))
    elif update.message.document:
        photos.append(("doc", update.message.document.file_id, update.message.document.file_name))

    keyboard = [[InlineKeyboardButton(f"✅ Готово ({len(photos)} фото)", callback_data="photos_done")]]
    await update.message.reply_text(
        f"📎 Получено: *{len(photos)}* фото. Отправьте ещё или нажмите «Готово».",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── Завершение сбора фото ────────────────────────────────────────────────────
async def photos_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    photos = ctx.user_data.get("photos", [])
    number = ctx.user_data.get(LOSS_KEY, "?")

    ctx.user_data.pop(PHOTO_KEY, None)
    ctx.user_data.pop(LOSS_KEY, None)
    ctx.user_data.pop("photos", None)

    keyboard = [[InlineKeyboardButton("📋 Новый убыток", web_app=WebAppInfo(url=WEBAPP_URL))]]

    if photos:
        text = (
            f"✅ *Убыток №{number} оформлен!*\n"
            f"📎 Прикреплено фото: {len(photos)} шт."
        )
    else:
        text = f"✅ *Убыток №{number} оформлен!*"

    await query.edit_message_text(text, parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(keyboard))


# ── Запуск ───────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receive_photo))
    app.add_handler(CallbackQueryHandler(photos_done, pattern="^photos_done$"))
    logger.info("Бот @DTP24_bot запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
