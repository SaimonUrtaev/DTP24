import json
import os
import base64
import urllib.request
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
SHEET_NAME     = os.environ.get("SHEET_NAME", "Лист1")
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "")
CHAT_ID        = os.environ.get("CHAT_ID", "")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}


def get_next_number(sheet) -> int:
    col = sheet.col_values(1)
    numbers = []
    for val in col[1:]:
        try:
            numbers.append(int(val))
        except (ValueError, TypeError):
            pass
    return (max(numbers) + 1) if numbers else 1


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
    """Уведомление без фото — отправляем текстовую карточку."""
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
    """Отправить фото альбомом — текст карточки как caption первого фото."""
    import requests as req_lib

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

    resp = req_lib.post(
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

        creds = Credentials.from_service_account_file(
            "/function/code/credentials.json", scopes=SCOPES
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

        number = get_next_number(sheet)
        today  = datetime.now().strftime("%d.%m.%Y")

        row = [""] * 27
        row[0]  = number
        row[1]  = body.get("park", "").upper()
        row[2]  = body.get("brand", "").upper()
        row[3]  = body.get("grz", "").upper()
        row[5]  = body.get("policy", "").upper()
        row[6]  = body.get("date_dtp", "")
        row[10] = body.get("insurance", "").upper()

        sheet.append_row(row, value_input_option="USER_ENTERED")
        format_new_row(sheet, len(sheet.get_all_values()))

        # Уведомить пользователя — не прерываем основной ответ при ошибке
        try:
            chat_id = body.get("user_id") or CHAT_ID
            photos = body.get("photos") or []
            if photos:
                try:
                    send_photos(chat_id, number, body, photos)
                except Exception as e:
                    print(f"send_photos error: {e}")
                    notify_user(chat_id, number, body)
            else:
                notify_user(chat_id, number, body)
        except Exception as e:
            print(f"notify error: {e}")

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"ok": True, "number": number}),
        }

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"ok": False, "error": type(e).__name__ + ": " + str(e)}),
        }
