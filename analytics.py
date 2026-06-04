# analytics.py
# Запуск для теста: python analytics.py
# Зависимости: pip install pandas openpyxl

import os
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import (
    PatternFill, Font, Alignment, Border, Side
)


# --- Настройки ---
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "competitor_report.xlsx")


def build_dataframe(listings: list[dict]) -> pd.DataFrame:
    """
    Принимает сырой список словарей из parser.py,
    возвращает чистый Pandas DataFrame.

    Что делает:
    1. Создаёт DataFrame из списка.
    2. Применяет функции очистки к каждому полю.
    3. Добавляет отсортированный порядковый номер.
    """
    if not listings:
        return pd.DataFrame(columns=[
            "№", "title", "price", "seller_name",
            "rating", "reviews_count", "url"
        ])

    df = pd.DataFrame(listings)

    df = df.drop(columns=["price_raw", "rating_raw", "reviews_raw"])

    df = df.sort_values("price", ascending=True, na_position="last")

    df = df.reset_index(drop=True)
    df.insert(0, "№", df.index + 1)

    df = df[["№", "title", "price", "seller_name", "rating", "reviews_count", "url"]]

    return df


def get_median_price(df: pd.DataFrame) -> float | None:
    """
    Считает медианную цену по всем объявлениям с указанной ценой.

    Медиана лучше среднего для цен: она не искажается
    выбросами (один мастер за 50 000₽ не "испортит" картину).
    """
    prices = df["price"].dropna()

    if prices.empty:
        return None

    return float(prices.median())


def get_top_sellers(df: pd.DataFrame, top_n: int = 3) -> pd.DataFrame:
    """
    Возвращает топ-N продавцов.

    Логика ранжирования:
    1. Сначала — те, у кого есть и рейтинг, и отзывы (самые надёжные данные).
    2. Сортируем по рейтингу (по убыванию), затем по отзывам (по убыванию).
       При одинаковом рейтинге — тот, у кого больше отзывов, ставится выше.
    """
    sellers_df = df[df["seller_name"].notna()].copy()

    if sellers_df.empty:
        return pd.DataFrame()

    sellers_df = (
        sellers_df
        .groupby("seller_name", as_index=False)
        .agg({
            "rating": "max",
            "reviews_count": "max",
            "title": "first",
            "url": "first",
        })
    )

    sellers_df = sellers_df.sort_values(
        ["rating", "reviews_count"],
        ascending=[False, False],
        na_position="last"
    )

    return sellers_df.head(top_n).reset_index(drop=True)


def build_summary(df: pd.DataFrame) -> dict:
    """
    Собирает всю аналитику в один словарь.
    Этот словарь будет использоваться и для Excel, и для текста в боте.
    """
    median = get_median_price(df)
    top_sellers = get_top_sellers(df)

    # Считаем дополнительную статистику
    prices_with_value = df["price"].dropna()

    summary = {
        "total_listings":      len(df),
        "listings_with_price": len(prices_with_value),
        "median_price":        median,
        "min_price":           int(prices_with_value.min()) if not prices_with_value.empty else None,
        "max_price":           int(prices_with_value.max()) if not prices_with_value.empty else None,
        "top_sellers":         top_sellers,
    }

    return summary


# ─────────────────────────────────────────────
#  Шаг 4. Сохранение в Excel
# ─────────────────────────────────────────────

def _style_excel(filepath: str) -> None:
    """
    Применяет визуальное оформление к готовому Excel-файлу.
    Вызывается после того как Pandas уже сохранил данные.
    """
    wb = load_workbook(filepath)

    # Граница — одна на весь файл, используется в каждой ячейке обоих листов
    thin_side = Side(style="thin", color="CCCCCC")
    cell_border = Border(
        left=thin_side, right=thin_side,
        top=thin_side,  bottom=thin_side
    )

    # ── Лист 1: Все объявления ──────────────────────────────
    ws_data = wb["Все объявления"]

    # Заливки строк
    header_fill = PatternFill("solid", fgColor="1E3A5F")  # тёмно-синий
    even_fill = PatternFill("solid", fgColor="D5E8F0")  # светло-голубой
    odd_fill = PatternFill("solid", fgColor="FFFFFF")  # белый

    # Шрифты
    header_font = Font(bold=True, color="FFFFFF", size=11)
    normal_font = Font(size=10, color="1A1A1A")
    link_font = Font(size=10, color="2E75B6", underline="single")

    # Строка 1 — заголовки таблицы
    for cell in ws_data[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.border = cell_border
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )
    ws_data.row_dimensions[1].height = 30

    # Индекс колонки с URL — последняя колонка листа
    url_col_idx = ws_data.max_column

    # Строки с данными (со строки 2)
    for row in ws_data.iter_rows(min_row=2):
        row_fill = even_fill if row[0].row % 2 == 0 else odd_fill

        for cell in row:
            cell.fill = row_fill
            cell.border = cell_border

            if cell.column == url_col_idx and cell.value:
                # Ссылки оформляем как гиперссылки
                cell.font = link_font
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.font = normal_font
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # Числовые колонки: № (1), Цена (3), Рейтинг (5), Отзывы (6) — по центру
    numeric_cols = {1, 3, 5, 6}
    for row in ws_data.iter_rows(min_row=2):
        for cell in row:
            if cell.column in numeric_cols:
                cell.alignment = Alignment(
                    horizontal="center", vertical="center"
                )

    # Ширина колонок
    col_widths = {
        "A": 5,   # №
        "B": 45,  # Название
        "C": 12,  # Цена
        "D": 28,  # Продавец
        "E": 10,  # Рейтинг
        "F": 12,  # Отзывы
        "G": 55,  # Ссылка
    }
    for col_letter, width in col_widths.items():
        ws_data.column_dimensions[col_letter].width = width

    # Первая строка зафиксирована — не уходит при прокрутке
    ws_data.freeze_panes = "A2"

    # ── Лист 2: Сводка ─────────────────────────────────────
    ws_summary = wb["Сводка"]

    # Заливки
    summary_header_fill = PatternFill("solid", fgColor="1E3A5F")  # тёмно-синий
    separator_fill = PatternFill("solid", fgColor="F0F4F8")  # светло-серый

    # Шрифты
    summary_header_font = Font(bold=True, color="FFFFFF", size=12)
    label_font = Font(size=11, color="444444")
    value_font = Font(bold=True, size=12, color="1E3A5F")
    separator_font = Font(size=9, color="AAAAAA")

    for row in ws_summary.iter_rows():
        label_cell = row[0]
        value_cell = row[1] if len(row) > 1 else None
        label_text = str(label_cell.value) if label_cell.value else ""

        if label_cell.row == 1:
            # Строка заголовка — Pandas пишет сюда названия колонок
            for cell in row:
                cell.fill = summary_header_fill
                cell.font = summary_header_font
                cell.border = cell_border
                cell.alignment = Alignment(
                    horizontal="center", vertical="center"
                )

        elif "--" in label_text: # ─
            # Визуальный разделитель между блоками
            for cell in row:
                cell.fill = separator_fill
                cell.font = separator_font
                cell.border = cell_border
                cell.alignment = Alignment(
                    horizontal="center", vertical="center"
                )

        else:
            # Обычная строка с данными
            label_cell.border = cell_border
            label_cell.font = label_font
            label_cell.alignment = Alignment(
                horizontal="left", vertical="center", indent=1
            )
            if value_cell:
                value_cell.border = cell_border
                value_cell.font = value_font
                value_cell.alignment = Alignment(
                    horizontal="left", vertical="center", indent=1
                )

        ws_summary.row_dimensions[label_cell.row].height = 24

    ws_summary.column_dimensions["A"].width = 32
    ws_summary.column_dimensions["B"].width = 35

    wb.save(filepath)


def save_to_excel(df: pd.DataFrame, summary: dict,
                  query: str, city: str,
                  filepath: str = OUTPUT_FILE) -> str:
    """
    Сохраняет DataFrame и сводку в Excel-файл с двумя листами.
    Возвращает путь к сохранённому файлу.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Переименовываем колонки для читаемости в Excel
    df_export = df.rename(columns={
        "title":         "Название",
        "price":         "Цена (₽)",
        "seller_name":   "Продавец",
        "rating":        "Рейтинг",
        "reviews_count": "Отзывы",
        "url":           "Ссылка",
    })

    # Строки топ-продавцов для листа "Сводка"
    top = summary["top_sellers"]
    top_rows = []
    for i, row in top.iterrows():
        rating_str = str(row["rating"]).replace(".", ",") if pd.notna(row["rating"]) else "--"
        reviews_str = str(int(row["reviews_count"])) if pd.notna(row["reviews_count"]) else "--"
        top_rows.append({
            "Показатель": f"Топ-{i + 1}: {row['seller_name']}",
            "Значение":   f"Рейтинг {rating_str} · {reviews_str} отзывов",
        })

    # Строковое представление цен
    median_str = f"{int(summary['median_price'])} ₽" if summary["median_price"] else "--"
    min_str = f"{summary['min_price']} ₽" if summary["min_price"] else "--"
    max_str = f"{summary['max_price']} ₽" if summary["max_price"] else "--"

    # Данные листа "Сводка".
    # Pandas автоматически сделает строку 1 из ключей словаря ("Показатель", "Значение"),
    # поэтому первую строку-заголовок добавлять вручную не нужно.
    summary_rows = [
        {"Показатель": "Запрос",             "Значение": query},
        {"Показатель": "Город",              "Значение": city},
        {"Показатель": "Всего объявлений",   "Значение": summary["total_listings"]},
        {"Показатель": "С указанной ценой",  "Значение": summary["listings_with_price"]},
        {"Показатель": "─" * 25,             "Значение": "─" * 20},
        {"Показатель": "Медианная цена",     "Значение": median_str},
        {"Показатель": "Минимальная цена",   "Значение": min_str},
        {"Показатель": "Максимальная цена",  "Значение": max_str},
        {"Показатель": "─" * 25,             "Значение": "─" * 20},
        *top_rows,
    ]
    df_summary = pd.DataFrame(summary_rows)

    # Записываем оба листа в один файл
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df_export.to_excel(writer, sheet_name="Все объявления", index=False)
        df_summary.to_excel(writer, sheet_name="Сводка", index=False)

    # Стилизуем уже сохранённый файл
    _style_excel(filepath)

    print(f"[Analytics] Excel сохранён: {filepath}")
    return filepath


# ─────────────────────────────────────────────
#  Главная публичная функция модуля
# ─────────────────────────────────────────────

def analyze(listings: list[dict],
            query: str = "запрос",
            city: str = "город") -> tuple[dict, str]:
    """
    Принимает сырые данные от парсера.
    Возвращает кортеж: (словарь с аналитикой, путь к Excel-файлу).

    Именно эту функцию будет вызывать bot.py:
        summary, excel_path = analyze(listings, query, city)
    """
    print(f"[Analytics] Обрабатываем {len(listings)} объявлений...")

    df = build_dataframe(listings)
    summary = build_summary(df)
    path = save_to_excel(df, summary, query, city)

    print(f"[Analytics] Медианная цена: {summary['median_price']} ₽")
    print(f"[Analytics] Топ продавцов: "
          f"{list(summary['top_sellers']['seller_name']) if not summary['top_sellers'].empty else '--'}")

    return summary, path


# ─────────────────────────────────────────────
#  Тест без бота
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # Тестовые данные — имитируют вывод parser.py
    # Используем их чтобы проверить analytics.py независимо от парсера
    test_listings = [
        {'title': 'iPhone 15, 256 ГБ',
         'url': 'https://www.avito.ru/kazan/telefony/iphone_15_256_gb_7970944235?context=H4sIAAAAAAAA_wE_AMD_YToyOntzOjEzOiJsb2NhbFByaW9yaXR5IjtiOjA7czoxOiJ4IjtzOjE2OiJRZk84TFRZNzN0Mjl4cnF4Ijt9ddgDVD8AAAA',
         'price_raw': '38 490 ₽', 'price': 38490.0, 'seller_name': 'ONE HUB', 'rating_raw': '5,0', 'rating': 5.0,
         'reviews_raw': '846 отзывов', 'reviews_count': 846},
        {'title': 'iPhone 15, 128 ГБ',
         'url': 'https://www.avito.ru/kazan/telefony/iphone_15_128_gb_7907462028?context=H4sIAAAAAAAA_wE_AMD_YToyOntzOjEzOiJsb2NhbFByaW9yaXR5IjtiOjA7czoxOiJ4IjtzOjE2OiJRZk84TFRZNzN0Mjl4cnF4Ijt9ddgDVD8AAAA',
         'price_raw': '32 990 ₽', 'price': 32990.0, 'seller_name': 'ONE HUB', 'rating_raw': '5,0', 'rating': 5.0,
         'reviews_raw': '846 отзывов', 'reviews_count': 846},
        {'title': 'iPhone 15, 128 ГБ',
         'url': 'https://www.avito.ru/kazan/telefony/iphone_15_128_gb_7907555236?context=H4sIAAAAAAAA_wE_AMD_YToyOntzOjEzOiJsb2NhbFByaW9yaXR5IjtiOjA7czoxOiJ4IjtzOjE2OiJRZk84TFRZNzN0Mjl4cnF4Ijt9ddgDVD8AAAA',
         'price_raw': '37 990 ₽', 'price': 37990.0, 'seller_name': 'ONE HUB', 'rating_raw': '5,0', 'rating': 5.0,
         'reviews_raw': '846 отзывов', 'reviews_count': 846},
        {'title': 'iPhone 15, 128 ГБ',
         'url': 'https://www.avito.ru/kazan/telefony/iphone_15_128_gb_7811845416?context=H4sIAAAAAAAA_wE_AMD_YToyOntzOjEzOiJsb2NhbFByaW9yaXR5IjtiOjA7czoxOiJ4IjtzOjE2OiJRZk84TFRZNzN0Mjl4cnF4Ijt9ddgDVD8AAAA',
         'price_raw': '37 990 ₽', 'price': 37990.0, 'seller_name': 'IRON APPLE', 'rating_raw': '5,0', 'rating': 5.0,
         'reviews_raw': '1 419 отзывов', 'reviews_count': 1},
        {'title': 'iPhone 15, 256 ГБ',
         'url': 'https://www.avito.ru/kazan/telefony/iphone_15_256_gb_7737598028?context=H4sIAAAAAAAA_wE_AMD_YToyOntzOjEzOiJsb2NhbFByaW9yaXR5IjtiOjA7czoxOiJ4IjtzOjE2OiJRZk84TFRZNzN0Mjl4cnF4Ijt9ddgDVD8AAAA',
         'price_raw': '44 990 ₽', 'price': 44990.0, 'seller_name': 'IMOFF', 'rating_raw': '4,9', 'rating': 4.9,
         'reviews_raw': '1 059 отзывов', 'reviews_count': 1},
        {'title': 'iPhone 15, 256 ГБ',
         'url': 'https://www.avito.ru/kazan/telefony/iphone_15_256_gb_7907001924?context=H4sIAAAAAAAA_wE_AMD_YToyOntzOjEzOiJsb2NhbFByaW9yaXR5IjtiOjA7czoxOiJ4IjtzOjE2OiJRZk84TFRZNzN0Mjl4cnF4Ijt9ddgDVD8AAAA',
         'price_raw': '38 490 ₽', 'price': 38490.0, 'seller_name': 'ONE HUB', 'rating_raw': '5,0', 'rating': 5.0,
         'reviews_raw': '846 отзывов', 'reviews_count': 846},
        {'title': 'iPhone 15, 256 ГБ, eSIM',
         'url': 'https://www.avito.ru/kazan/telefony/iphone_15_256_gb_esim_7911860396?context=H4sIAAAAAAAA_wE_AMD_YToyOntzOjEzOiJsb2NhbFByaW9yaXR5IjtiOjA7czoxOiJ4IjtzOjE2OiJRZk84TFRZNzN0Mjl4cnF4Ijt9ddgDVD8AAAA',
         'price_raw': '45 990 ₽', 'price': 45990.0, 'seller_name': 'ЛЮМО - магазин техники', 'rating_raw': '5,0',
         'rating': 5.0, 'reviews_raw': '64 отзыва', 'reviews_count': 64},
        {'title': 'iPhone 15, 128 ГБ',
         'url': 'https://www.avito.ru/kazan/telefony/iphone_15_128_gb_7769033310?context=H4sIAAAAAAAA_wE_AMD_YToyOntzOjEzOiJsb2NhbFByaW9yaXR5IjtiOjA7czoxOiJ4IjtzOjE2OiJRZk84TFRZNzN0Mjl4cnF4Ijt9ddgDVD8AAAA',
         'price_raw': '37 990 ₽', 'price': 37990.0, 'seller_name': 'IMOFF', 'rating_raw': '4,9', 'rating': 4.9,
         'reviews_raw': '1 059 отзывов', 'reviews_count': 1},
        {'title': 'iPhone 15, 256 ГБ',
         'url': 'https://www.avito.ru/kazan/telefony/iphone_15_256_gb_7907408837?context=H4sIAAAAAAAA_wE_AMD_YToyOntzOjEzOiJsb2NhbFByaW9yaXR5IjtiOjA7czoxOiJ4IjtzOjE2OiJRZk84TFRZNzN0Mjl4cnF4Ijt9ddgDVD8AAAA',
         'price_raw': '44 990 ₽', 'price': 44990.0, 'seller_name': 'ONE HUB', 'rating_raw': '5,0', 'rating': 5.0,
         'reviews_raw': '846 отзывов', 'reviews_count': 846},
        {'title': 'iPhone 15, 128 ГБ, SIM + eSIM',
         'url': 'https://www.avito.ru/kazan/telefony/iphone_15_128_gb_sim_esim_8192891764?context=H4sIAAAAAAAA_wE_AMD_YToyOntzOjEzOiJsb2NhbFByaW9yaXR5IjtiOjA7czoxOiJ4IjtzOjE2OiJRZk84TFRZNzN0Mjl4cnF4Ijt9ddgDVD8AAAA',
         'price_raw': '38 900 ₽', 'price': 38900.0, 'seller_name': 'UpStore - iPhone.', 'rating_raw': '4,9',
         'rating': 4.9, 'reviews_raw': '773 отзыва', 'reviews_count': 773},
    ]

    summary, excel_path = analyze(test_listings, query="iPhone 15", city="Казань")

    print("\n--- Сводка ---")
    print(f"Всего объявлений: {summary['total_listings']}")
    print(f"Медианная цена: {summary['median_price']} ₽")
    print(f"Диапазон цен: {summary['min_price']} - {summary['max_price']} ₽")
    print(f"\nТоп-3 продавца:")
    print(summary["top_sellers"][["seller_name", "rating", "reviews_count"]].to_string(index=False))
    print(f"\nФайл сохранён: {excel_path}")