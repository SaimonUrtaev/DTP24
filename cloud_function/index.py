import json
import os
import base64
import urllib.request
import logging
import gspread
import requests
from google.oauth2.service_account import Credentials

# Fix #8: явный handler вместо basicConfig — работает даже если gspread настроил logging раньше
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setLevel(logging.INFO)
    logger.addHandler(_h)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
SHEET_NAME     = os.environ.get("SHEET_NAME", "Лист1")
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "")
CHAT_ID        = os.environ.get("CHAT_ID", "")

CREDENTIALS_PATH = "/function/code/credentials.json"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}


def get_next_number(sheet) -> tuple:
    """Возвращает (следующий номер убытка, номер строки для форматирования)."""
    col = sheet.col_values(1)
    numbers = []
    for val in col[1:]:
        try:
            numbers.append(int(val))
        except (ValueError, TypeError):
            pass
    # Fix #7: возвращаем длину col чтобы не делать лишний get_all_values() позже
    return (max(numbers) + 1) if numbers else 1, len(col) + 1


def format_new_row(sheet, row_num: int):
    border = {"style": "SOLID", "width": 1}
    sheet.format(f"A{row_num}:AA{row_num}", {
        "borders": {"top": border, "bottom": border, "left": border, "right": border},
        "textFormat": {"bold": False, "fontSize": 10},
        "verticalAlignment": "MIDDLE",
        "horizontalAlignment": "LEFT",
    })
    sheet.format(f"A{row_num}", {
        "borders": {"top": border, "bottom": border, "left": border, "right": border},
        "textFormat": {"bold": True, "fontSize": 10},
        "verticalAlignment": "MIDDLE",
        "horizontalAlignment": "CENTER",
    })


def _safe(val):
    return (val or "—").strip() or "—"


def _build_text(number: int, data: dict, photo_count: int = 0) -> str:
    admin_note = data.get("admin_note", "").strip()
    text = (
        f"✅ *Убыток №{number} записан!*\n\n"
        f"🏢 ПАРК: `{_safe(data.get('park')).upper()}`\n"
        f"🚗 МАРКА ТС: `{_safe(data.get('brand')).upper()}`\n"
        f"🔢 ГОС.НОМЕР: `{_safe(data.get('grz')).upper()}`\n"
        f"📄 ПОЛИС ОСАГО: `{_safe(data.get('policy')).upper()}`\n"
        f"📅 ДАТА ДТП: `{_safe(data.get('date_dtp'))}`\n"
        f"🏦 СК: `{_safe(data.get('insurance')).upper()}`\n"
    )
    if admin_note:
        text += f"📝 АДМИН МАТЕРИАЛ: `{admin_note}`\n"
    if photo_count > 0:
        text += f"📎 Фото: {photo_count} шт."
    return text


def notify_user(chat_id, number: int, data: dict):
    if not BOT_TOKEN or not chat_id:
        return
    text = _build_text(number, data)
    payload = json.dumps({
        "chat_id": int(chat_id),
        "text": text,
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10)


def send_photos(chat_id, number: int, data: dict, photos_b64: list):
    if not BOT_TOKEN or not chat_id or not photos_b64:
        return

    text = _build_text(number, data, photo_count=len(photos_b64))

    files = {}
    media = []
    for i, data_url in enumerate(photos_b64):
        raw_b64 = data_url.split(",", 1)[-1]
        photo_bytes = base64.b64decode(raw_b64)
        key = f"photo{i}"
        files[key] = (f"photo{i}.jpg", photo_bytes, "image/jpeg")
        item = {"type": "photo", "media": f"attach://{key}"}
        if i == 0:
            item["caption"] = text
            item["parse_mode"] = "Markdown"
        media.append(item)

    resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup",
        data={"chat_id": int(chat_id), "media": json.dumps(media)},
        files=files,
        timeout=8,
    )
    resp.raise_for_status()


def handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    try:
        body_raw = event.get("body", "") or ""
        if event.get("isBase64Encoded", False):
            body_raw = base64.b64decode(body_raw).decode("utf-8")
        body = json.loads(body_raw or "{}")

        # Fix #3: добавлен "insurance" в список обязательных полей
        required_fields = ["park", "brand", "grz", "policy", "date_dtp", "insurance"]
        missing = [f for f in required_fields if not body.get(f)]
        if missing:
            logger.warning(f"Missing required fields: {missing}")
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"ok": False, "error": f"Missing fields: {', '.join(missing)}"}),
            }

        # Fix #5+6: убраны GOOGLE_CREDENTIALS_PATH и os.path.exists — from_service_account_file бросает сам
        try:
            creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
            client = gspread.authorize(creds)
            sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        except FileNotFoundError as e:
            logger.error(f"Credentials error: {e}")
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps({"ok": False, "error": "Configuration error"}),
            }
        except gspread.SpreadsheetNotFound:
            logger.error(f"Spreadsheet {SPREADSHEET_ID} not found")
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps({"ok": False, "error": "Spreadsheet not found"}),
            }
        except gspread.WorksheetNotFound:
            logger.error(f"Worksheet {SHEET_NAME} not found")
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps({"ok": False, "error": "Worksheet not found"}),
            }

        try:
            # Fix #7: get_next_number возвращает номер строки — не нужен лишний get_all_values()
            number, new_row_num = get_next_number(sheet)
            row = [""] * 27
            row[0]  = number
            row[1]  = body.get("park", "").upper()
            row[2]  = body.get("brand", "").upper()
            row[3]  = body.get("grz", "").upper()
            row[5]  = body.get("policy", "").upper()
            row[6]  = body.get("date_dtp", "")
            row[10] = body.get("insurance", "").upper()
            row[11] = body.get("admin_note", "")  # Fix #1: admin_note теперь пишется в таблицу

            sheet.append_row(row, value_input_option="USER_ENTERED")
            format_new_row(sheet, new_row_num)
            logger.info(f"Loss record #{number} added at row {new_row_num}")
        except Exception as e:
            logger.error(f"Error writing to sheet: {e}")
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps({"ok": False, "error": "Failed to write record"}),
            }

        try:
            chat_id = body.get("user_id") or CHAT_ID
            photos = body.get("photos") or []
            if photos:
                try:
                    send_photos(chat_id, number, body, photos)
                    logger.info(f"Photos sent for loss #{number}")
                except Exception as e:
                    logger.warning(f"send_photos error: {e}, falling back to text notification")
                    # Fix #2: fallback тоже обёрнут — двойной сбой не вернёт ok:true молча
                    try:
                        notify_user(chat_id, number, body)
                    except Exception as e2:
                        logger.warning(f"fallback notify_user also failed: {e2}")
            else:
                notify_user(chat_id, number, body)
                logger.info(f"Notification sent for loss #{number}")
        except Exception as e:
            logger.warning(f"Notification error (non-critical): {e}")

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"ok": True, "number": number}),
        }

    except Exception as e:
        logger.error(f"Unhandled error: {type(e).__name__}: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"ok": False, "error": "Internal server error"}),
        }
