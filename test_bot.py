"""
Юнит-тесты для @DTP24_bot.
Все запросы к Telegram API и Google Sheets замоканы — сеть не используется.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Окружение до импорта модулей ──────────────────────────────────────────────
os.environ.setdefault("BOT_TOKEN",               "test:TOKEN123")
os.environ.setdefault("SPREADSHEET_ID",          "test_spreadsheet_id")
os.environ.setdefault("ALLOWED_USERS",           "111111")
os.environ.setdefault("WEBAPP_URL",              "https://example.com/form.html")
os.environ.setdefault("SHEET_NAME",              "Лист1")
os.environ.setdefault("GOOGLE_CREDENTIALS_FILE", "credentials.json")

import google_sheets
from google_sheets import get_next_number, append_loss, reset_sheet_cache
import bot
from bot import (
    cmd_start, start_photos, skip_photos,
    receive_photo, photos_done, restore_keyboard,
    PHOTO_KEY, LOSS_KEY,
)

ALLOWED = 111111   # пользователь из ALLOWED_USERS
BLOCKED = 999999   # посторонний


# ── Фабрики mock-объектов ─────────────────────────────────────────────────────

def make_update(user_id=ALLOWED, message_text="", has_photo=False, has_document=False):
    """Создаёт Update с Message (для обычных сообщений и команд)."""
    user = MagicMock()
    user.id = user_id
    user.first_name = "Тест"

    msg = MagicMock()
    msg.reply_text  = AsyncMock()
    msg.text        = message_text
    msg.message_id  = 1

    if has_photo:
        photo = MagicMock()
        photo.file_id = "photo_file_123"
        msg.photo     = [photo]
        msg.document  = None
    elif has_document:
        doc = MagicMock()
        doc.file_id   = "doc_file_456"
        msg.document  = doc
        msg.photo     = None
    else:
        msg.photo     = None
        msg.document  = None

    upd = MagicMock()
    upd.effective_user    = user
    upd.effective_message = msg
    upd.message           = msg
    upd.effective_chat    = MagicMock()
    upd.effective_chat.id = user_id
    return upd


def make_callback_update(user_id=ALLOWED, data="", msg_text=""):
    """Создаёт Update с CallbackQuery (для нажатий inline-кнопок)."""
    user = MagicMock()
    user.id = user_id

    msg = MagicMock()
    msg.text        = msg_text
    msg.message_id  = 1
    msg.reply_text  = AsyncMock()

    query = MagicMock()
    query.answer                    = AsyncMock()
    query.data                      = data
    query.message                   = msg
    query.edit_message_reply_markup = AsyncMock()

    upd = MagicMock()
    upd.effective_user    = user
    upd.callback_query    = query
    upd.effective_message = msg
    upd.effective_chat    = MagicMock()
    upd.effective_chat.id = user_id
    return upd


def make_ctx(user_data=None):
    """Создаёт Context с замоканным bot."""
    ctx              = MagicMock()
    ctx.user_data    = user_data if user_data is not None else {}
    ctx.bot          = MagicMock()
    ctx.bot.send_message    = AsyncMock()
    ctx.bot.send_media_group = AsyncMock()
    ctx.bot.edit_message_text = AsyncMock()
    return ctx


# ════════════════════════════════════════════════════════════════════════════
# 1. Декоратор auth_required
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_auth_blocks_unknown_user():
    """Посторонний пользователь получает «Доступ запрещён» и дальше не идёт."""
    upd = make_update(user_id=BLOCKED)
    ctx = make_ctx()
    await cmd_start(upd, ctx)
    upd.effective_message.reply_text.assert_called_once()
    assert "запрещён" in upd.effective_message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_auth_allows_known_user():
    """Авторизованный пользователь проходит декоратор и получает ответ."""
    upd = make_update(user_id=ALLOWED)
    ctx = make_ctx()
    await cmd_start(upd, ctx)
    upd.message.reply_text.assert_called_once()


# ════════════════════════════════════════════════════════════════════════════
# 2. /start
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_start_greets_by_name():
    """/start содержит имя пользователя."""
    upd = make_update(user_id=ALLOWED)
    upd.effective_user.first_name = "Саймон"
    ctx = make_ctx()
    await cmd_start(upd, ctx)
    text = upd.message.reply_text.call_args[0][0]
    assert "Саймон" in text


@pytest.mark.asyncio
async def test_cmd_start_sends_reply_markup():
    """/start отправляет сообщение с клавиатурой."""
    upd = make_update(user_id=ALLOWED)
    ctx = make_ctx()
    await cmd_start(upd, ctx)
    assert "reply_markup" in upd.message.reply_text.call_args.kwargs


# ════════════════════════════════════════════════════════════════════════════
# 3. start_photos — нажатие «Прикрепить фото»
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_start_photos_sets_state():
    """PHOTO_KEY, LOSS_KEY и пустой список photos выставляются в user_data."""
    upd = make_callback_update(data="start_photos_42")
    ctx = make_ctx()
    await start_photos(upd, ctx)
    assert ctx.user_data[PHOTO_KEY] is True
    assert ctx.user_data[LOSS_KEY]  == 42
    assert ctx.user_data["photos"]  == []


@pytest.mark.asyncio
async def test_start_photos_extracts_admin_note():
    """АДМИН МАТЕРИАЛ извлекается из текста уведомления."""
    upd = make_callback_update(
        data="start_photos_10",
        msg_text="✅ Убыток №10\n📝 АДМИН МАТЕРИАЛ: `нужен протокол`\n",
    )
    ctx = make_ctx()
    await start_photos(upd, ctx)
    assert ctx.user_data["admin_note"] == "нужен протокол"


@pytest.mark.asyncio
async def test_start_photos_empty_admin_note_when_absent():
    """Если АДМИН МАТЕРИАЛ не указан — admin_note пустая строка."""
    upd = make_callback_update(data="start_photos_5", msg_text="✅ Убыток №5")
    ctx = make_ctx()
    await start_photos(upd, ctx)
    assert ctx.user_data["admin_note"] == ""


@pytest.mark.asyncio
async def test_start_photos_blocked_user_no_state():
    """Посторонний пользователь не создаёт фото-сессию."""
    upd = make_callback_update(user_id=BLOCKED, data="start_photos_1")
    ctx = make_ctx()
    await start_photos(upd, ctx)
    assert PHOTO_KEY not in ctx.user_data


@pytest.mark.asyncio
async def test_start_photos_invalid_number_no_state():
    """Некорректный номер убытка не создаёт фото-сессию."""
    upd = make_callback_update(data="start_photos_abc")
    ctx = make_ctx()
    await start_photos(upd, ctx)
    assert PHOTO_KEY not in ctx.user_data


# ════════════════════════════════════════════════════════════════════════════
# 4. skip_photos — нажатие «Без фото — завершить»
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_skip_photos_removes_inline_keyboard():
    """Inline-клавиатура из уведомления убирается."""
    upd = make_callback_update(data="skip_photos_7")
    ctx = make_ctx()
    await skip_photos(upd, ctx)
    upd.callback_query.edit_message_reply_markup.assert_called_once_with(reply_markup=None)


@pytest.mark.asyncio
async def test_skip_photos_message_contains_loss_number():
    """В сообщении о завершении упоминается номер убытка."""
    upd = make_callback_update(data="skip_photos_7")
    ctx = make_ctx()
    await skip_photos(upd, ctx)
    text = upd.callback_query.message.reply_text.call_args[0][0]
    assert "7" in text


@pytest.mark.asyncio
async def test_skip_photos_sends_new_loss_keyboard():
    """После пропуска фото отправляется клавиатура с кнопкой нового убытка."""
    upd = make_callback_update(data="skip_photos_3")
    ctx = make_ctx()
    await skip_photos(upd, ctx)
    assert "reply_markup" in upd.callback_query.message.reply_text.call_args.kwargs


# ════════════════════════════════════════════════════════════════════════════
# 5. receive_photo — приём фото
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_receive_photo_blocked_user_silent():
    """Фото от постороннего игнорируется без ответа."""
    upd = make_update(user_id=BLOCKED, has_photo=True)
    ctx = make_ctx()
    await receive_photo(upd, ctx)
    assert "photos" not in ctx.user_data
    upd.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_receive_photo_no_session_shows_hint():
    """Фото без активной сессии → подсказка «нажмите кнопку»."""
    upd = make_update(has_photo=True)
    ctx = make_ctx()   # PHOTO_KEY не установлен
    await receive_photo(upd, ctx)
    upd.message.reply_text.assert_called_once()
    assert "кнопку" in upd.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_receive_photo_appends_photo():
    """Сжатое фото добавляется в список как ('photo', file_id)."""
    upd = make_update(has_photo=True)
    ctx = make_ctx({PHOTO_KEY: True, "photos": [], "done_msg_id": None})
    await receive_photo(upd, ctx)
    assert ctx.user_data["photos"] == [("photo", "photo_file_123")]


@pytest.mark.asyncio
async def test_receive_photo_appends_document():
    """Файл-изображение добавляется как ('doc', file_id)."""
    upd = make_update(has_document=True)
    ctx = make_ctx({PHOTO_KEY: True, "photos": [], "done_msg_id": None})
    await receive_photo(upd, ctx)
    assert ctx.user_data["photos"] == [("doc", "doc_file_456")]


@pytest.mark.asyncio
async def test_receive_photo_counter_increments():
    """После добавления фото счётчик в сообщении «Готово» обновляется."""
    upd = make_update(has_photo=True)
    ctx = make_ctx({PHOTO_KEY: True, "photos": [("photo", "old")], "done_msg_id": 99})
    await receive_photo(upd, ctx)
    ctx.bot.edit_message_text.assert_called_once()
    text = ctx.bot.edit_message_text.call_args.kwargs["text"]
    assert "2" in text


@pytest.mark.asyncio
async def test_receive_photo_accumulates_multiple():
    """Несколько последовательных фото накапливаются в списке."""
    upd1 = make_update(has_photo=True)
    upd2 = make_update(has_document=True)
    ctx  = make_ctx({PHOTO_KEY: True, "photos": [], "done_msg_id": None})

    await receive_photo(upd1, ctx)
    await receive_photo(upd2, ctx)

    assert len(ctx.user_data["photos"]) == 2


# ════════════════════════════════════════════════════════════════════════════
# 6. photos_done — кнопка «Готово»
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_photos_done_resets_all_state():
    """После завершения user_data полностью очищается."""
    upd = make_callback_update(data="photos_done")
    ctx = make_ctx({PHOTO_KEY: True, LOSS_KEY: 5, "photos": [],
                    "done_msg_id": 1, "admin_note": ""})
    with patch("bot._get_sheet") as m:
        m.return_value.get_all_values.return_value = [["№"]]
        await photos_done(upd, ctx)
    assert PHOTO_KEY      not in ctx.user_data
    assert LOSS_KEY       not in ctx.user_data
    assert "photos"       not in ctx.user_data
    assert "done_msg_id"  not in ctx.user_data
    assert "admin_note"   not in ctx.user_data


@pytest.mark.asyncio
async def test_photos_done_sends_card_with_sheet_data():
    """Карточка содержит данные, прочитанные из Google Sheets."""
    upd = make_callback_update(data="photos_done")
    ctx = make_ctx({PHOTO_KEY: True, LOSS_KEY: 3, "photos": [],
                    "done_msg_id": 1, "admin_note": ""})
    with patch("bot._get_sheet") as m:
        m.return_value.get_all_values.return_value = [
            ["№", "ПАРК", "МАРКА", "ГОС.НОМ", "", "ПОЛИС", "ДАТА", "", "", "", "СК"],
            ["3", "ПАРК1", "LADA",  "А001АА77","","ХХХ1","01.01.2026","","","","РЕСО"],
        ]
        await photos_done(upd, ctx)
    first_text = ctx.bot.send_message.call_args_list[0][0][1]
    assert "ПАРК1" in first_text
    assert "LADA"  in first_text


@pytest.mark.asyncio
async def test_photos_done_no_photos_skips_media_group():
    """Если фото не было — send_media_group не вызывается."""
    upd = make_callback_update(data="photos_done")
    ctx = make_ctx({PHOTO_KEY: True, LOSS_KEY: 1, "photos": [],
                    "done_msg_id": 1, "admin_note": ""})
    with patch("bot._get_sheet") as m:
        m.return_value.get_all_values.return_value = [["№"]]
        await photos_done(upd, ctx)
    ctx.bot.send_media_group.assert_not_called()


@pytest.mark.asyncio
async def test_photos_done_separates_photos_and_docs():
    """Фото и документы отправляются двумя отдельными группами."""
    upd = make_callback_update(data="photos_done")
    ctx = make_ctx({PHOTO_KEY: True, LOSS_KEY: 1,
                    "photos": [("photo","p1"),("doc","d1"),("photo","p2")],
                    "done_msg_id": 1, "admin_note": ""})
    with patch("bot._get_sheet") as m:
        m.return_value.get_all_values.return_value = [["№"]]
        await photos_done(upd, ctx)
    assert ctx.bot.send_media_group.call_count == 2


@pytest.mark.asyncio
async def test_photos_done_includes_admin_note_in_card():
    """АДМИН МАТЕРИАЛ из user_data попадает в карточку."""
    upd = make_callback_update(data="photos_done")
    ctx = make_ctx({PHOTO_KEY: True, LOSS_KEY: 2, "photos": [],
                    "done_msg_id": 1, "admin_note": "срочный материал"})
    with patch("bot._get_sheet") as m:
        m.return_value.get_all_values.return_value = [["№"]]
        await photos_done(upd, ctx)
    first_text = ctx.bot.send_message.call_args_list[0][0][1]
    assert "срочный материал" in first_text


@pytest.mark.asyncio
async def test_photos_done_sheet_error_resets_cache():
    """При ошибке Google Sheets кэш сбрасывается и карточка всё равно уходит."""
    upd = make_callback_update(data="photos_done")
    ctx = make_ctx({PHOTO_KEY: True, LOSS_KEY: 1, "photos": [],
                    "done_msg_id": 1, "admin_note": ""})
    with patch("bot._get_sheet", side_effect=Exception("Sheet unavailable")):
        with patch("bot.reset_sheet_cache") as mock_reset:
            await photos_done(upd, ctx)
    mock_reset.assert_called_once()
    ctx.bot.send_message.assert_called()


@pytest.mark.asyncio
async def test_photos_done_sends_new_loss_button():
    """После завершения отправляется кнопка «Новый убыток»."""
    upd = make_callback_update(data="photos_done")
    ctx = make_ctx({PHOTO_KEY: True, LOSS_KEY: 1, "photos": [],
                    "done_msg_id": 1, "admin_note": ""})
    with patch("bot._get_sheet") as m:
        m.return_value.get_all_values.return_value = [["№"]]
        await photos_done(upd, ctx)
    # последнее сообщение содержит reply_markup с кнопкой
    last_call = ctx.bot.send_message.call_args_list[-1]
    assert "reply_markup" in last_call.kwargs


# ════════════════════════════════════════════════════════════════════════════
# 7. restore_keyboard
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_restore_keyboard_shows_button():
    """Текстовое сообщение без сессии восстанавливает кнопку."""
    upd = make_update(message_text="привет")
    ctx = make_ctx()
    await restore_keyboard(upd, ctx)
    upd.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_restore_keyboard_silent_during_photo_session():
    """Во время загрузки фото кнопка не восстанавливается."""
    upd = make_update(message_text="ещё одно фото?")
    ctx = make_ctx({PHOTO_KEY: True})
    await restore_keyboard(upd, ctx)
    upd.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_restore_keyboard_blocked_user_gets_denied():
    """Посторонний пользователь получает «Доступ запрещён», а не клавиатуру."""
    upd = make_update(user_id=BLOCKED, message_text="привет")
    ctx = make_ctx()
    await restore_keyboard(upd, ctx)
    upd.message.reply_text.assert_called_once()
    assert "запрещён" in upd.message.reply_text.call_args[0][0]


# ════════════════════════════════════════════════════════════════════════════
# 8. google_sheets
# ════════════════════════════════════════════════════════════════════════════

def test_reset_sheet_cache_clears_object():
    """reset_sheet_cache обнуляет глобальный _sheet_cache."""
    google_sheets._sheet_cache = MagicMock()
    reset_sheet_cache()
    assert google_sheets._sheet_cache is None


def test_get_next_number_returns_max_plus_one():
    """get_next_number возвращает максимальный номер + 1."""
    mock_sheet = MagicMock()
    mock_sheet.col_values.return_value = ["№", "1", "2", "5", "3"]
    with patch("google_sheets._get_sheet", return_value=mock_sheet):
        assert get_next_number() == 6


def test_get_next_number_returns_one_for_empty_sheet():
    """Для пустой таблицы get_next_number возвращает 1."""
    mock_sheet = MagicMock()
    mock_sheet.col_values.return_value = ["№"]
    with patch("google_sheets._get_sheet", return_value=mock_sheet):
        assert get_next_number() == 1


def test_get_next_number_ignores_non_numeric_values():
    """Нечисловые ячейки (пустые, текст) пропускаются."""
    mock_sheet = MagicMock()
    mock_sheet.col_values.return_value = ["№", "1", "abc", "", "3"]
    with patch("google_sheets._get_sheet", return_value=mock_sheet):
        assert get_next_number() == 4


def test_append_loss_writes_correct_columns():
    """append_loss пишет данные в правильные колонки строки."""
    mock_sheet = MagicMock()
    mock_sheet.col_values.return_value = ["№", "10"]
    mock_sheet.get_all_values.return_value = [["h"]] * 12
    with patch("google_sheets._get_sheet", return_value=mock_sheet):
        number = append_loss({
            "park": "ПАРК", "brand": "LADA", "grz": "а001аа77",
            "policy": "ХХХ111", "date_dtp": "01.01.2026", "insurance": "РЕСО",
        })
    assert number == 11
    row = mock_sheet.append_row.call_args[0][0]
    assert row[0]  == 11          # №
    assert row[1]  == "ПАРК"      # ПАРК
    assert row[2]  == "LADA"      # МАРКА ТС
    assert row[3]  == "а001аа77"  # ГОС.НОМЕР
    assert row[5]  == "ХХХ111"    # ПОЛИС
    assert row[6]  == "01.01.2026" # ДАТА ДТП
    assert row[10] == "РЕСО"      # СК


def test_append_loss_resets_cache_on_error():
    """При ошибке записи кэш сбрасывается и исключение пробрасывается выше."""
    mock_sheet = MagicMock()
    mock_sheet.col_values.return_value = ["№", "1"]
    mock_sheet.append_row.side_effect  = Exception("connection lost")
    with patch("google_sheets._get_sheet", return_value=mock_sheet):
        with pytest.raises(Exception, match="connection lost"):
            append_loss({"park": "test"})
    assert google_sheets._sheet_cache is None
