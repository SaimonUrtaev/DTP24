"""
Конфигурация бота — скопируйте этот файл в config.py и заполните своими данными.
ВАЖНО: config.py никогда не загружается в git (защита ключей).
"""

# Токен бота — получить у @BotFather в Telegram
BOT_TOKEN = "ВАШ_ТОКЕН_ЗДЕСЬ"

# Telegram user_id авторизованных сотрудников (узнать через @userinfobot)
ALLOWED_USERS = {
    123456789,  # Администратор
}

# Google Sheets
SPREADSHEET_ID = "ID_ВАШЕЙ_ТАБЛИЦЫ"   # из URL таблицы Google Sheets
SHEET_NAME = "Лист1"
GOOGLE_CREDENTIALS_FILE = "credentials.json"
