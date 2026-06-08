import json
import os
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


def notify_user(chat_id, number: int, data: dict):
    """Отправить сообщение пользователю через Telegram Bot API."""
    if not BOT_TOKEN or not chat_id:
        return

    admin_note = data.get("admin_note", "").strip()
    text = (
        f"✅ *Убыток №{number} записан!*\n\n"
        f"🏢 ПАРК: `{data.get('park', '—').upper()}`\n"
        f"🚗 МАРКА ТС: `{data.get('brand', '—').upper()}`\n"
        f"🔢 ГОС.НОМЕР: `{data.get('grz', '—').upper()}`\n"
        f"📄 ПОЛИС ОСАГО: `{data.get('policy', '—').upper()}`\n"
        f"📅 ДАТА ДТП: `{data.get('date_dtp', '—')}`\n"
        f"🏦 СК: `{data.get('insurance', '—').upper()}`\n"
    )
    if admin_note:
        text += f"📝 АДМИН МАТЕРИАЛ: `{admin_note}`\n"
    text += "\n📎 Отправьте фото: место ДТП, СТС, полис, материалы."
    keyboard = {
        "inline_keyboard": [
            [{"text": "📎 Прикрепить фото",      "callback_data": f"start_photos_{number}"}],
            [{"text": "✅ Без фото — завершить", "callback_data": f"skip_photos_{number}"}],
        ]
    }
    payload = json.dumps({
        "chat_id": int(chat_id),
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard,
    }).encode()

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10)


def handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    try:
        body = json.loads(event.get("body", "{}"))

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
        row[7]  = today
        row[10] = body.get("insurance", "").upper()

        sheet.append_row(row, value_input_option="USER_ENTERED")
        format_new_row(sheet, len(sheet.get_all_values()))

        # Уведомить пользователя — не прерываем основной ответ при ошибке
        try:
            notify_user(body.get("user_id"), number, body)
        except Exception as e:
            print(f"notify_user error: {e}")

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"ok": True, "number": number}),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"ok": False, "error": str(e)}),
        }
