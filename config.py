# config.py
# Читает токен бота из файла .env и проверяет что он не пустой.

import os
from dotenv import load_dotenv

# load_dotenv() ищет файл .env в текущей папке и загружает переменные в os.environ.
# Если файл не найден — молча продолжает (переменные просто не появятся).
load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

if not BOT_TOKEN:
    raise ValueError("\n\nТокен бота не найден!\n")