#!/usr/bin/env python3
"""
Telegram Bot @DTP24_bot — Убыток дежурного
"""

import logging
import functools
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, WebAppInfo,
    InputMediaPhoto, InputMediaDocument,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from config import BOT_TOKEN, ALLOWED_USERS, WEBAPP_URL
from google_sheets import _get_sheet

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

PHOTO_KEY = "collecting_photos"
LOSS_KEY  = "loss_number"


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


# ── Кнопка «Прикрепить фото» из уведомления ─────────────────────────────────
async def start_photos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id not in ALLOWED_USERS:
        return

    try:
        number = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        return

    ctx.user_data[PHOTO_KEY] = True
    ctx.user_data[LOSS_KEY]  = number
    ctx.user_data["photos"]  = []

    # Убираем кнопки из исходного сообщения
    await query.edit_message_reply_markup(reply_markup=None)

    keyboard = [[InlineKeyboardButton("✅ Готово (0 фото)", callback_data="photos_done")]]
    await query.message.reply_text(
        "📎 Отправляйте фото по одному.\n"
        "Когда закончите — нажмите «Готово».",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ── Кнопка «Без фото» из уведомления ────────────────────────────────────────
async def skip_photos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id not in ALLOWED_USERS:
        return

    try:
        number = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        return

    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"✅ Убыток №{number} оформлен без фото.")


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


# ── Кнопка «Готово» — текст + фото одним блоком ─────────────────────────────
async def photos_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id not in ALLOWED_USERS:
        return

    photos  = ctx.user_data.get("photos", [])
    number  = ctx.user_data.get(LOSS_KEY, "?")
    chat_id = update.effective_chat.id

    # Получаем данные убытка из таблицы
    row_data = {}
    try:
        sheet = _get_sheet()
        for row in sheet.get_all_values()[1:]:
            if row[0] == str(number):
                row_data = {
                    "park":      row[1],
                    "brand":     row[2],
                    "grz":       row[3],
                    "policy":    row[5],
                    "date_dtp":  row[6],
                    "insurance": row[10],
                }
                break
    except Exception as e:
        logger.error(f"Ошибка получения данных из таблицы: {e}")

    text = (
        f"📋 *Убыток №{number}*\n\n"
        f"🏢 ПАРК: `{row_data.get('park', '—')}`\n"
        f"🚗 МАРКА ТС: `{row_data.get('brand', '—')}`\n"
        f"🔢 ГОС.НОМЕР: `{row_data.get('grz', '—')}`\n"
        f"📄 ПОЛИС ОСАГО: `{row_data.get('policy', '—')}`\n"
        f"📅 ДАТА ДТП: `{row_data.get('date_dtp', '—')}`\n"
        f"🏦 СК: `{row_data.get('insurance', '—')}`\n"
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
        logger.error(f"Ошибка отправки итога: {e}")
        await ctx.bot.send_message(
            chat_id,
            "❌ Ошибка при отправке. Данные в таблице сохранены.",
        )

    # Сброс состояния
    ctx.user_data.pop(PHOTO_KEY, None)
    ctx.user_data.pop(LOSS_KEY, None)
    ctx.user_data.pop("photos", None)

    # Убираем кнопку из последнего сообщения
    await query.edit_message_reply_markup(reply_markup=None)


# ── Запуск ───────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(start_photos, pattern=r"^start_photos_\d+$"))
    app.add_handler(CallbackQueryHandler(skip_photos,  pattern=r"^skip_photos_\d+$"))
    app.add_handler(CallbackQueryHandler(photos_done,  pattern="^photos_done$"))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receive_photo))
    logger.info("Бот @DTP24_bot запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
