import json
import os
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
SHEET_NAME     = os.environ.get("SHEET_NAME", "Лист1")

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
    cell_fmt = {
        "borders": {"top": border, "bottom": border, "left": border, "right": border},
        "textFormat": {"bold": False, "fontSize": 10},
        "verticalAlignment": "MIDDLE",
        "horizontalAlignment": "LEFT",
    }
    # Вся строка
    sheet.format(f"A{row_num}:AA{row_num}", cell_fmt)
    # Столбец № — жирный и по центру как в шаблоне
    sheet.format(f"A{row_num}", {
        "borders": {"top": border, "bottom": border, "left": border, "right": border},
        "textFormat": {"bold": True, "fontSize": 10},
        "verticalAlignment": "MIDDLE",
        "horizontalAlignment": "CENTER",
    })


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
        today = datetime.now().strftime("%d.%m.%Y")

        row = [""] * 27
        row[0]  = number
        row[1]  = body.get("park", "").upper()
        row[2]  = body.get("brand", "").upper()
        row[3]  = body.get("grz", "").upper()
        row[5]  = body.get("policy", "").upper()
        row[6]  = body.get("date_dtp", "")
        row[7]  = today                           # ДАТА ПОДАЧИ — сегодня
        row[10] = body.get("insurance", "").upper()

        sheet.append_row(row, value_input_option="USER_ENTERED")

        new_row_num = len(sheet.get_all_values())
        format_new_row(sheet, new_row_num)

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
