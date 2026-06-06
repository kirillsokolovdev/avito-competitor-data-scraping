# bot.py
# Запуск: python bot.py
# Зависимости: pip install aiogram python-dotenv

import asyncio
import logging

import pandas as pd
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile, Message

from config import BOT_TOKEN
from parser import parse_avito
from analytics import analyze


# Настраиваем логирование: время + уровень + сообщение в каждой строке
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# Router — в aiogram 3.x хэндлеры регистрируются на роутере, а не на dp напрямую.
# В конце main() роутер подключается к диспетчеру через dp.include_router(router).
router = Router()


# ─────────────────────────────────────────────
#  FSM: состояния диалога
# ─────────────────────────────────────────────

class SearchStates(StatesGroup):
    waiting_for_query = State()  # шаг 1 — ждём поисковый запрос
    waiting_for_city  = State()  # шаг 2 — ждём название города


# ─────────────────────────────────────────────
#  Хелпер: форматирование текстовой сводки
# ─────────────────────────────────────────────

def _format_summary(summary: dict, query: str, city: str) -> str:
    """
    Превращает словарь аналитики из analytics.py в читаемый текст для Telegram.
    Использует Markdown-разметку: *жирный*, _курсив_.
    """
    lines = [
        f"📊 *Анализ рынка: «{query}» в {city}*\n",
        f"📦 Найдено объявлений: *{summary['total_listings']}*",
        f"💰 С указанной ценой: *{summary['listings_with_price']}*",
    ]

    # Ценовую статистику добавляем только если данные есть (не None)
    if summary["median_price"]:
        lines.append(f"📊 Медианная цена: *{int(summary['median_price'])} ₽*")
    if summary["min_price"]:
        lines.append(f"📉 Минимальная цена: *{summary['min_price']} ₽*")
    if summary["max_price"]:
        lines.append(f"📈 Максимальная цена: *{summary['max_price']} ₽*")

    # Блок топ-продавцов
    top = summary["top_sellers"]
    if not top.empty:
        lines.append("\n🏆 *Топ продавцов:*")
        for i, row in top.iterrows():
            # pd.notna() — правильная проверка на NaN в Pandas.
            # Обычный `if row["rating"]` не работает с NaN: он не False и не None.
            rating_str  = str(row["rating"]).replace(".", ",") if pd.notna(row["rating"])        else "—"
            reviews_str = str(int(row["reviews_count"]))       if pd.notna(row["reviews_count"]) else "—"
            lines.append(
                f"{i + 1}. {row['seller_name']} — "
                f"рейтинг {rating_str} · {reviews_str} отзывов"
            )

    return "\n".join(lines)


# ─────────────────────────────────────────────
#  Хэндлеры
# ─────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """
    Шаг 0: команда /start.

    Сбрасываем любое старое состояние — пользователь мог прервать прошлый поиск.
    Переводим в первое состояние и просим ввести запрос.
    """
    await state.clear()
    await state.set_state(SearchStates.waiting_for_query)
    await message.answer(
        "👋 Привет! Я соберу данные о конкурентах на Avito.\n\n"
        "🔍 *Что ищем?*\n"
        "Введи поисковый запрос, например: _ремонт ноутбуков_",
        parse_mode="Markdown",
    )


@router.message(SearchStates.waiting_for_query, F.text)
async def handle_query(message: Message, state: FSMContext) -> None:
    """
    Шаг 1: получаем поисковый запрос.
    Сохраняем в FSMContext.data и переходим к следующему состоянию.
    Фильтр F.text гарантирует, что сюда не попадут стикеры, фото и т.д.
    """
    query = message.text.strip()

    # Защита от пустой строки (пробелы, невидимые символы)
    if not query:
        await message.answer("⚠️ Запрос не может быть пустым. Введи текст:")
        return

    # update_data сохраняет данные в хранилище FSM для этого пользователя.
    # state.get_data() достанет их в следующем хэндлере.
    await state.update_data(query=query)
    await state.set_state(SearchStates.waiting_for_city)
    await message.answer(
        "🏙️ *В каком городе искать?*\n"
        "Введи название города, например: _Москва_",
        parse_mode="Markdown",
    )


@router.message(SearchStates.waiting_for_query)
async def handle_query_wrong_type(message: Message) -> None:
    """
    Пользователь прислал не текст (фото, стикер, файл) на шаге запроса.
    Вежливо напоминаем что нужно ввести текст.
    """
    await message.answer("⚠️ Пожалуйста, введи текстовый запрос:")


@router.message(SearchStates.waiting_for_city, F.text)
async def handle_city(message: Message, state: FSMContext) -> None:
    """
    Шаг 2: получаем город, запускаем парсер и аналитику, отправляем результат.
    Это главный хэндлер — здесь происходит вся работа.
    """
    city = message.text.strip()

    if not city:
        await message.answer("⚠️ Название города не может быть пустым. Введи текст:")
        return

    # Достаём сохранённый запрос из FSMContext
    data  = await state.get_data()
    query = data["query"]

    # Сбрасываем состояние ДО тяжёлых операций.
    # Если что-то пойдёт не так — пользователь сможет начать заново через /start,
    # а не застрянет в состоянии waiting_for_city.
    await state.clear()

    # Отправляем статусное сообщение — пользователь видит что бот не завис
    status_msg = await message.answer(
        f"⏳ Собираю данные по запросу *«{query}»* в *{city}*...\n"
        "Это займёт около минуты, пожалуйста подожди.",
        parse_mode="Markdown",
    )

    # ── Шаг A: парсинг ─────────────────────────────────────
    # parse_avito — блокирующая функция: Selenium открывает браузер и ждёт загрузки.
    # asyncio.to_thread() запускает её в отдельном потоке, не блокируя event loop.
    # Без этого бот "завис" бы и не отвечал другим пользователям во время парсинга.
    try:
        listings = await asyncio.to_thread(parse_avito, query, city)
    except Exception as e:
        log.error(f"Ошибка парсера для запроса '{query}' в '{city}': {e}")
        await status_msg.edit_text(
            "❌ Не удалось собрать данные. Попробуй позже или "
            "проверь правильность написания города.\n\nНачать заново: /start"
        )
        return

    # Парсер вернул пустой список — город не найден или нет объявлений
    if not listings:
        await status_msg.edit_text(
            f"😔 По запросу *«{query}»* в *{city}* ничего не найдено.\n\n"
            "Проверь правильность написания города и попробуй снова.\n"
            "Начать заново: /start",
            parse_mode="Markdown",
        )
        return

    # ── Шаг B: аналитика ───────────────────────────────────
    # analyze тоже запускаем в потоке: Pandas и запись файла — синхронные операции.
    try:
        summary, excel_path = await asyncio.to_thread(analyze, listings, query, city)
    except Exception as e:
        log.error(f"Ошибка аналитики для запроса '{query}' в '{city}': {e}")
        await status_msg.edit_text(
            "❌ Данные собраны, но не удалось построить отчёт. "
            "Попробуй позже.\n\nНачать заново: /start"
        )
        return

    # Статусное сообщение выполнило свою роль — удаляем его перед отправкой результата
    await status_msg.delete()

    # ── Шаг C: отправляем текстовую сводку ─────────────────
    summary_text = _format_summary(summary, query, city)
    await message.answer(summary_text, parse_mode="Markdown")

    # ── Шаг D: отправляем Excel-файл ───────────────────────
    # Формируем читаемое имя файла для пользователя.
    # replace + срез — защита от слишком длинных имён.
    safe_query = query.replace(" ", "_")[:20]
    safe_city  = city.replace(" ", "_")[:15]
    filename   = f"avito_{safe_query}_{safe_city}.xlsx"

    # FSInputFile — правильный способ отправить локальный файл в aiogram 3.x.
    # path — путь к файлу на диске, filename — имя, которое увидит пользователь.
    excel_file = FSInputFile(excel_path, filename=filename)
    await message.answer_document(
        excel_file,
        caption="📎 Полный отчёт в Excel",
    )


@router.message(SearchStates.waiting_for_city)
async def handle_city_wrong_type(message: Message) -> None:
    """
    Пользователь прислал не текст на шаге города.
    """
    await message.answer("⚠️ Пожалуйста, введи название города текстом:")


# ─────────────────────────────────────────────
#  Точка входа
# ─────────────────────────────────────────────

async def main() -> None:
    # Bot — объект для отправки запросов к Telegram API
    bot = Bot(token=BOT_TOKEN)

    # MemoryStorage хранит состояния FSM в оперативной памяти.
    # При перезапуске бота все незавершённые диалоги сбрасываются — для MVP нормально.
    storage = MemoryStorage()
    dp      = Dispatcher(storage=storage)

    # Подключаем роутер с хэндлерами к диспетчеру.
    # include_router — стандартный способ в aiogram 3.x.
    dp.include_router(router)

    log.info("Бот запущен. Нажми Ctrl+C для остановки.")

    # start_polling запускает бесконечный цикл получения обновлений от Telegram.
    # skip_updates=True — игнорируем сообщения, пришедшие пока бот был выключен,
    # чтобы не обрабатывать "старые" команды при каждом перезапуске.
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())