#!/usr/bin/env python3
"""
Telegram Bot @DTP24_bot — Убыток дежурного
WebApp форма + сбор фото после записи
"""

import json
import logging
import functools
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, WebAppInfo,
    InputMediaPhoto, InputMediaDocument
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from config import BOT_TOKEN, ALLOWED_USERS, WEBAPP_URL

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
PHOTO_KEY  = "collecting_photos"
LOSS_KEY   = "loss_data"


# ── Авторизация ──────────────────────────────────────────────────────────────
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
    # KeyboardButton — обязательно для tg.sendData() в WebApp
    keyboard = [[KeyboardButton("📋 Новый убыток", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! 👋\n\n"
        "Нажмите кнопку чтобы открыть форму убытка.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )


# ── Получение данных из WebApp ───────────────────────────────────────────────
@auth_required
async def web_app_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        data = json.loads(update.message.web_app_data.data)
        number = data.get("number", "?")
    except Exception as e:
        logger.error(f"web_app_data parse error: {e}")
        await update.message.reply_text("❌ Ошибка при получении данных формы. Попробуйте ещё раз.")
        return

    ctx.user_data[PHOTO_KEY] = True
    ctx.user_data[LOSS_KEY]  = data
    ctx.user_data["photos"]  = []

    keyboard = [[InlineKeyboardButton("✅ Готово, фото не нужны", callback_data="photos_done")]]
    await update.message.reply_text(
        f"✅ *Убыток №{number} записан!*\n\n"
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
        photos.append(("doc", update.message.document.file_id))

    keyboard = [[InlineKeyboardButton(f"✅ Готово ({len(photos)} фото)", callback_data="photos_done")]]
    await update.message.reply_text(
        f"📎 Получено: *{len(photos)}* фото. Отправьте ещё или нажмите «Готово».",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── Завершение — текст + фото одним блоком ───────────────────────────────────
async def photos_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    photos = ctx.user_data.get("photos", [])
    d      = ctx.user_data.get(LOSS_KEY, {})
    number = d.get("number", "?")
    chat_id = update.effective_chat.id

    # Текстовая карточка убытка
    text = (
        f"📋 *Убыток №{number}*\n\n"
        f"🏢 ПАРК: `{d.get('park', '—').upper()}`\n"
        f"🚗 МАРКА ТС: `{d.get('brand', '—').upper()}`\n"
        f"🔢 ГОС.НОМЕР: `{d.get('grz', '—').upper()}`\n"
        f"📄 ПОЛИС ОСАГО: `{d.get('policy', '—').upper()}`\n"
        f"📅 ДАТА ДТП: `{d.get('date_dtp', '—')}`\n"
        f"🏦 СК: `{d.get('insurance', '—').upper()}`\n"
        f"📎 Фото: {len(photos)} шт."
    )

    try:
        await ctx.bot.send_message(chat_id, text, parse_mode="Markdown")
        if photos:
            media = []
            for p in photos:
                if p[0] == "photo":
                    media.append(InputMediaPhoto(media=p[1]))
                elif p[0] == "doc":
                    media.append(InputMediaDocument(media=p[1]))
            if media:
                await ctx.bot.send_media_group(chat_id, media)
    except Exception as e:
        logger.error(f"photos_done send error: {e}")
        await ctx.bot.send_message(chat_id, "❌ Ошибка при отправке. Данные в таблице сохранены.")

    # Очищаем состояние
    ctx.user_data.pop(PHOTO_KEY, None)
    ctx.user_data.pop(LOSS_KEY, None)
    ctx.user_data.pop("photos", None)

    # Убираем кнопку из старого сообщения
    await query.edit_message_reply_markup(reply_markup=None)


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
