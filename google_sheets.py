"""
Интеграция с Google Sheets через Service Account.
Таблица: Лист1, колонки соответствуют существующей структуре.
"""

import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_CREDENTIALS_FILE, SPREADSHEET_ID, SHEET_NAME

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Порядок колонок в таблице (27 штук)
HEADERS = [
    "№", "ПАРК", "МАРКА ТС", "ГОС.НОМЕР", "ГОД ТС", "ПОЛИС ОСАГО",
    "ДАТА ДТП", "ДАТА ПОДАЧИ", "ДАТА ОСМОТРА", "№ УБЫТКА", "СК",
    "ЛИЗИНГ", "ВЫРАБОТКА", "ЗАДАЧА НА", "УТС", "СУММА",
    "КАЛЬКУЛЯЦИЯ", "НАМ 15%", "СТАТУС ОПЛАТЫ", "ПРИМЕЧАНИЕ",
    "ГОРОД", "ГИБДД", "ГДЕ АДМИНКА", "ПРИВЕЗ АДМИНКУ",
    "ОСМОТР ПОД НЭ", "ВИНОВНИКИ ДТП", "УСЛОВИЯ",
]

_sheet_cache = None


def _get_sheet():
    global _sheet_cache
    if _sheet_cache is not None:
        return _sheet_cache
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    try:
        sheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=27)
    _sheet_cache = sheet
    return sheet


def get_next_number() -> int:
    """Получить следующий порядковый номер (последний № + 1)."""
    sheet = _get_sheet()
    col = sheet.col_values(1)  # колонка №
    numbers = []
    for val in col[1:]:  # пропускаем заголовок
        try:
            numbers.append(int(val))
        except (ValueError, TypeError):
            pass
    return (max(numbers) + 1) if numbers else 1


def append_loss(data: dict) -> int:
    """
    Записать новый убыток в таблицу.
    data — словарь с ключами: park, brand, grz, year, policy, date_dtp, insurance
    Возвращает присвоенный номер.
    """
    global _sheet_cache
    try:
        number = get_next_number()
        # Строим строку из 27 колонок, заполняем только известные поля
        row = [""] * 27
        row[0]  = number                    # №
        row[1]  = data.get("park", "")      # ПАРК
        row[2]  = data.get("brand", "")     # МАРКА ТС
        row[3]  = data.get("grz", "")       # ГОС.НОМЕР
        row[4]  = data.get("year", "")      # ГОД ТС
        row[5]  = data.get("policy", "")    # ПОЛИС ОСАГО
        row[6]  = data.get("date_dtp", "")  # ДАТА ДТП
        row[10] = data.get("insurance", "") # СК (колонка 11, индекс 10)

        sheet = _get_sheet()
        sheet.append_row(row, value_input_option="USER_ENTERED")
        return number
    except Exception:
        _sheet_cache = None
        raise
