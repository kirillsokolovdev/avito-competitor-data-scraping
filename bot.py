# bot.py
# Run: python bot.py
# Dependencies: pip install aiogram python-dotenv

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


# Configure application-wide logging.
# Example output:
# 2026-01-01 12:00:00 [INFO] Bot started
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# Main router for registering all message handlers.
# In aiogram 3.x handlers are attached to Router objects,
# which are later included into Dispatcher.
router = Router()


class SearchStates(StatesGroup):
    """
    Finite State Machine for the search dialog.

    Flow:
        waiting_for_query -> waiting_for_city
    """

    # Step 1: waiting for the user's search query
    waiting_for_query = State()

    # Step 2: waiting for the city name
    waiting_for_city = State()


def _format_summary(summary: dict, query: str, city: str) -> str:
    """
    Convert analytics results into a human-readable Telegram message.

    Parameters:
        summary: Dictionary returned from analytics.py
        query: Original search query
        city: Selected city

    Returns:
        Formatted Markdown string for Telegram.
    """

    lines = [
        f"📊 *Анализ рынка: «{query}» в {city}*\n",
        f"📦 Найдено объявлений: *{summary['total_listings']}*",
        f"💰 С указанной ценой: *{summary['listings_with_price']}*",
    ]

    # Add price statistics only if values exist.
    # Some searches may return listings without prices.
    if summary["median_price"]:
        lines.append(f"📊 Медианная цена: *{int(summary['median_price'])} ₽*")

    if summary["min_price"]:
        lines.append(f"📉 Минимальная цена: *{summary['min_price']} ₽*")

    if summary["max_price"]:
        lines.append(f"📈 Максимальная цена: *{summary['max_price']} ₽*")

    # Top sellers block
    top = summary["top_sellers"]

    if not top.empty:
        lines.append("\n🏆 *Топ продавцов:*")

        for i, row in top.iterrows():

            # Pandas stores missing numeric values as NaN.
            # pd.notna() is the safest way to validate them.
            rating_str = (
                str(row["rating"]).replace(".", ",")
                if pd.notna(row["rating"])
                else "—"
            )

            reviews_str = (
                str(int(row["reviews_count"]))
                if pd.notna(row["reviews_count"])
                else "—"
            )

            lines.append(
                f"{i + 1}. {row['seller_name']} — "
                f"рейтинг {rating_str} · {reviews_str} отзывов"
            )

    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """
    Entry point for the bot.

    Actions:
        1. Reset any previous FSM state
        2. Switch user to waiting_for_query state
        3. Ask for a search query
    """

    # Clear unfinished dialogs from previous sessions.
    # This prevents users from getting stuck in old states.
    await state.clear()

    # Move FSM to the first dialog step.
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
    Handle the user's search query.

    Actions:
        1. Validate input
        2. Save query into FSM storage
        3. Switch to waiting_for_city state
    """

    query = message.text.strip()

    # Prevent empty or whitespace-only messages.
    if not query:
        await message.answer("⚠️ Запрос не может быть пустым. Введи текст:")
        return

    # Save query in FSM storage for the next step.
    await state.update_data(query=query)

    # Move dialog to the next state.
    await state.set_state(SearchStates.waiting_for_city)

    await message.answer(
        "🏙️ *В каком городе искать?*\n"
        "Введи название города, например: _Москва_",
        parse_mode="Markdown",
    )


@router.message(SearchStates.waiting_for_query)
async def handle_query_wrong_type(message: Message) -> None:
    """
    Handle non-text messages during the query step.

    Example:
        stickers, photos, voice messages, files
    """

    await message.answer("⚠️ Пожалуйста, введи текстовый запрос:")


@router.message(SearchStates.waiting_for_city, F.text)
async def handle_city(message: Message, state: FSMContext) -> None:
    """
    Main business-logic handler.

    Flow:
        1. Receive city
        2. Run parser
        3. Run analytics
        4. Send summary
        5. Send Excel report
    """

    city = message.text.strip()

    # Validate city name.
    if not city:
        await message.answer("⚠️ Название города не может быть пустым. Введи текст:")
        return

    # Retrieve previously saved query from FSM storage.
    data = await state.get_data()
    query = data["query"]

    # Clear FSM state before heavy operations.
    # If something crashes later, the user can safely restart via /start.
    await state.clear()

    # Send temporary status message so the user understands
    # that long-running parsing is currently in progress.
    status_msg = await message.answer(
        f"⏳ Собираю данные по запросу *«{query}»* в *{city}*...\n"
        "Это займёт около минуты, пожалуйста подожди.",
        parse_mode="Markdown",
    )

    # parse_avito() is synchronous and blocking because Selenium
    # controls a real browser instance.
    #
    # asyncio.to_thread() runs it in a separate thread,
    # preventing the event loop from freezing.
    try:
        listings = await asyncio.to_thread(parse_avito, query, city)

    except Exception as e:
        log.error(f"Parser error for query '{query}' in '{city}': {e}")

        await status_msg.edit_text(
            "❌ Не удалось собрать данные. Попробуй позже или "
            "проверь правильность написания города.\n\n"
            "Начать заново: /start"
        )

        return

    # Empty result usually means:
    # - city not found
    # - no listings
    # - page structure changed
    if not listings:
        await status_msg.edit_text(
            f"😔 По запросу *«{query}»* в *{city}* ничего не найдено.\n\n"
            "Проверь правильность написания города и попробуй снова.\n"
            "Начать заново: /start",
            parse_mode="Markdown",
        )

        return

    # analyze() is also synchronous because Pandas and Excel export
    # are CPU/file-system bound operations.
    try:
        summary, excel_path = await asyncio.to_thread(
            analyze,
            listings,
            query,
            city,
        )

    except Exception as e:
        log.error(f"Analytics error for query '{query}' in '{city}': {e}")

        await status_msg.edit_text(
            "❌ Данные собраны, но не удалось построить отчёт. "
            "Попробуй позже.\n\n"
            "Начать заново: /start"
        )

        return

    # Remove temporary status message before sending final results.
    await status_msg.delete()

    summary_text = _format_summary(summary, query, city)

    await message.answer(
        summary_text,
        parse_mode="Markdown",
    )

    # Build safe and readable filename.
    # Limit length to avoid filesystem and Telegram issues.
    safe_query = query.replace(" ", "_")[:20]
    safe_city = city.replace(" ", "_")[:15]

    filename = f"avito_{safe_query}_{safe_city}.xlsx"

    # FSInputFile is the standard aiogram 3.x way
    # to upload local files.
    excel_file = FSInputFile(
        excel_path,
        filename=filename,
    )

    await message.answer_document(
        excel_file,
        caption="📎 Полный отчёт в Excel",
    )


@router.message(SearchStates.waiting_for_city)
async def handle_city_wrong_type(message: Message) -> None:
    """
    Handle non-text messages during the city input step.
    """

    await message.answer("⚠️ Пожалуйста, введи название города текстом:")


# Entry point
async def main() -> None:
    """
    Configure and start the Telegram bot.
    """

    # Main Telegram Bot API client.
    bot = Bot(token=BOT_TOKEN)

    # In-memory FSM storage.
    #
    # Suitable for MVPs and local development.
    # All active dialogs will be lost after restart.
    storage = MemoryStorage()

    # Main update dispatcher.
    dp = Dispatcher(storage=storage)

    # Register router with all handlers.
    dp.include_router(router)

    log.info("Bot started. Press Ctrl+C to stop.")

    # Start long polling.
    #
    # skip_updates=True ignores messages accumulated while
    # the bot was offline.
    await dp.start_polling(
        bot,
        skip_updates=True,
    )


if __name__ == "__main__":
    asyncio.run(main())