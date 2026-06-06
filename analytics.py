# analytics.py
# Run locally:
#     python analytics.py
#
# Required packages:
#     pip install pandas openpyxl

import os
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import (
    PatternFill, Font, Alignment, Border, Side
)


# Directory where generated Excel reports will be stored
OUTPUT_DIR = "output"

# Default output file path
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "competitor_report.xlsx")


def build_dataframe(listings: list[dict]) -> pd.DataFrame:
    """
    Convert raw parser output into a clean, structured DataFrame.

    Pipeline:
    1. Create DataFrame from list of dictionaries.
    2. Remove temporary/raw columns.
    3. Sort listings by price.
    4. Add user-friendly row numbering.
    5. Reorder columns for final export.
    """
    # Return empty DataFrame with predefined columns
    # to prevent downstream errors
    if not listings:
        return pd.DataFrame(columns=[
            "№", "title", "price", "seller_name",
            "rating", "reviews_count", "url"
        ])

    # Convert raw parser data into tabular structure
    df = pd.DataFrame(listings)

    # Remove raw string fields after preprocessing
    df = df.drop(columns=["price_raw", "rating_raw", "reviews_raw"])

    # Sort listings by ascending price
    # Rows with missing prices are moved to the end
    df = df.sort_values("price", ascending=True, na_position="last")

    # Reset DataFrame index after sorting
    df = df.reset_index(drop=True)

    # Insert human-readable numbering column
    df.insert(0, "№", df.index + 1)

    # Keep only required columns in final order
    df = df[["№", "title", "price", "seller_name", "rating", "reviews_count", "url"]]

    return df


def get_median_price(df: pd.DataFrame) -> float | None:
    """
    Calculate median market price.

    Median is preferred over average because it is
    resistant to extreme outliers.
    """
    # Exclude rows without price values
    prices = df["price"].dropna()

    if prices.empty:
        return None

    return float(prices.median())


def get_top_sellers(df: pd.DataFrame, top_n: int = 3) -> pd.DataFrame:
    """
    Return top-rated sellers.

    Ranking logic:
    1. Higher rating first.
    2. If ratings are equal -> seller with more reviews wins.
    """
    # Ignore listings without seller information
    sellers_df = df[df["seller_name"].notna()].copy()

    if sellers_df.empty:
        return pd.DataFrame()

    # Merge duplicate sellers into single rows
    # and keep their best metrics
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

    # Sort sellers by rating and reviews count
    sellers_df = sellers_df.sort_values(
        ["rating", "reviews_count"],
        ascending=[False, False],
        na_position="last"
    )

    # Return only requested number of sellers
    return sellers_df.head(top_n).reset_index(drop=True)


def build_summary(df: pd.DataFrame) -> dict:
    """
    Build aggregated analytics summary.

    The resulting dictionary is reused both
    for Excel generation and Telegram messages.
    """
    median = get_median_price(df)
    top_sellers = get_top_sellers(df)

    # Rows that contain valid price values
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


def _style_excel(filepath: str) -> None:
    """
    Apply visual formatting to generated Excel workbook.

    Pandas is used for fast export,
    while openpyxl handles styling and layout.
    """
    wb = load_workbook(filepath)

    # Shared border style for all workbook cells
    thin_side = Side(style="thin", color="CCCCCC")
    cell_border = Border(
        left=thin_side, right=thin_side,
        top=thin_side,  bottom=thin_side
    )

    ws_data = wb["Все объявления"]

    # Row background colors
    header_fill = PatternFill("solid", fgColor="1E3A5F")
    even_fill = PatternFill("solid", fgColor="D5E8F0")
    odd_fill = PatternFill("solid", fgColor="FFFFFF")

    # Font styles
    header_font = Font(bold=True, color="FFFFFF", size=11)
    normal_font = Font(size=10, color="1A1A1A")
    link_font = Font(size=10, color="2E75B6", underline="single")

    # Style header row
    for cell in ws_data[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.border = cell_border
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )

    # Increase header row height
    ws_data.row_dimensions[1].height = 30

    # URL column index (last column in worksheet)
    url_col_idx = ws_data.max_column

    # Style data rows
    for row in ws_data.iter_rows(min_row=2):
        # Alternate row colors for better readability
        row_fill = even_fill if row[0].row % 2 == 0 else odd_fill

        for cell in row:
            cell.fill = row_fill
            cell.border = cell_border

            # Make URL column visually look like hyperlinks
            if cell.column == url_col_idx and cell.value:
                cell.font = link_font
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.font = normal_font
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # Center-align numeric columns
    numeric_cols = {1, 3, 5, 6}

    for row in ws_data.iter_rows(min_row=2):
        for cell in row:
            if cell.column in numeric_cols:
                cell.alignment = Alignment(
                    horizontal="center", vertical="center"
                )

    # Manual column widths
    # Auto-sizing in openpyxl is unreliable
    col_widths = {
        "A": 5,
        "B": 45,
        "C": 12,
        "D": 28,
        "E": 10,
        "F": 12,
        "G": 55,
    }

    for col_letter, width in col_widths.items():
        ws_data.column_dimensions[col_letter].width = width

    # Freeze header row while scrolling
    ws_data.freeze_panes = "A2"

    ws_summary = wb["Сводка"]

    # Background fills
    summary_header_fill = PatternFill("solid", fgColor="1E3A5F")
    separator_fill = PatternFill("solid", fgColor="F0F4F8")

    # Font styles
    summary_header_font = Font(bold=True, color="FFFFFF", size=12)
    label_font = Font(size=11, color="444444")
    value_font = Font(bold=True, size=12, color="1E3A5F")
    separator_font = Font(size=9, color="AAAAAA")

    for row in ws_summary.iter_rows():
        label_cell = row[0]
        value_cell = row[1] if len(row) > 1 else None
        label_text = str(label_cell.value) if label_cell.value else ""

        # Header row generated automatically by Pandas
        if label_cell.row == 1:
            for cell in row:
                cell.fill = summary_header_fill
                cell.font = summary_header_font
                cell.border = cell_border
                cell.alignment = Alignment(
                    horizontal="center", vertical="center"
                )

        # Visual separators between logical sections
        elif "--" in label_text:
            for cell in row:
                cell.fill = separator_fill
                cell.font = separator_font
                cell.border = cell_border
                cell.alignment = Alignment(
                    horizontal="center", vertical="center"
                )

        # Standard data rows
        else:
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

        # Uniform row height
        ws_summary.row_dimensions[label_cell.row].height = 24

    # Summary worksheet column widths
    ws_summary.column_dimensions["A"].width = 32
    ws_summary.column_dimensions["B"].width = 35

    # Save styled workbook
    wb.save(filepath)


def save_to_excel(df: pd.DataFrame, summary: dict,
                  query: str, city: str,
                  filepath: str = OUTPUT_FILE) -> str:
    """
    Export analytics results into a styled Excel workbook.

    Workbook structure:
    - Sheet 1: Full listings table
    - Sheet 2: Market summary
    """
    # Create output directory if it does not exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Rename columns for end-user readability
    df_export = df.rename(columns={
        "title":         "Название",
        "price":         "Цена (₽)",
        "seller_name":   "Продавец",
        "rating":        "Рейтинг",
        "reviews_count": "Отзывы",
        "url":           "Ссылка",
    })

    # Build top sellers block for summary sheet
    top = summary["top_sellers"]
    top_rows = []

    for i, row in top.iterrows():
        rating_str = str(row["rating"]).replace(".", ",") if pd.notna(row["rating"]) else "--"
        reviews_str = str(int(row["reviews_count"])) if pd.notna(row["reviews_count"]) else "--"

        top_rows.append({
            "Показатель": f"Топ-{i + 1}: {row['seller_name']}",
            "Значение":   f"Рейтинг {rating_str} · {reviews_str} отзывов",
        })

    # Convert numeric values into formatted strings
    median_str = f"{int(summary['median_price'])} ₽" if summary["median_price"] else "--"
    min_str = f"{summary['min_price']} ₽" if summary["min_price"] else "--"
    max_str = f"{summary['max_price']} ₽" if summary["max_price"] else "--"

    # Summary worksheet rows
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

    # Write multiple worksheets into a single Excel file
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df_export.to_excel(writer, sheet_name="Все объявления", index=False)
        df_summary.to_excel(writer, sheet_name="Сводка", index=False)

    # Apply post-processing styles
    _style_excel(filepath)

    print(f"[Analytics] Excel saved: {filepath}")

    return filepath


def analyze(listings: list[dict],
            query: str = "запрос",
            city: str = "город") -> tuple[dict, str]:
    """
    Main public API of the analytics module.

    Input:
        Raw listings collected by parser.py

    Output:
        tuple(summary_dict, excel_file_path)

    This is the only function bot.py needs to call.
    """
    print(f"[Analytics] Processing {len(listings)} listings...")

    df = build_dataframe(listings)
    summary = build_summary(df)
    path = save_to_excel(df, summary, query, city)

    print(f"[Analytics] Median price: {summary['median_price']} ₽")

    print(
        f"[Analytics] Top sellers: "
        f"{list(summary['top_sellers']['seller_name']) if not summary['top_sellers'].empty else '--'}"
    )

    return summary, path


if __name__ == "__main__":

    # Fake dataset used for standalone analytics testing
    test_listings = [
        {'title': 'iPhone 15, 256 ГБ',
         'url': 'https://www.avito.ru/kazan/telefony/iphone_15_256_gb_7970944235?context=H4sIAAAAAAAA_wE_AMD_YToyOntzOjEzOiJsb2NhbFByaW9yaXR5IjtiOjA7czoxOiJ4IjtzOjE2OiJRZk84TFRZNzN0Mjl4cnF4Ijt9ddgDVD8AAAA',
         'price_raw': '38 490 ₽', 'price': 38490.0, 'seller_name': 'ONE HUB', 'rating_raw': '5,0', 'rating': 5.0,
         'reviews_raw': '846 отзывов', 'reviews_count': 846},
        {'title': 'iPhone 15, 128 ГБ',
         'url': 'https://www.avito.ru/kazan/telefony/iphone_15_128_gb_7907462028?context=H4sIAAAAAAAA_wE_AMD_YToyOntzOjEzOiJsb2NhbFByaW9yaXR5IjtiOjA7czoxOiJ4IjtzOjE2OiJRZk84TFRZNzN0Mjl4cnF4Ijt9ddgDVD8AAAA',
         'price_raw': '32 990 ₽', 'price': 32990.0, 'seller_name': 'ONE HUB', 'rating_raw': '5,0', 'rating': 5.0,
         'reviews_raw': '846 отзывов', 'reviews_count': 846},
    ]

    summary, excel_path = analyze(
        test_listings,
        query="iPhone 15",
        city="Казань"
    )

    print("\n--- Summary ---")
    print(f"Total listings: {summary['total_listings']}")
    print(f"Median price: {summary['median_price']} ₽")
    print(f"Price range: {summary['min_price']} - {summary['max_price']} ₽")

    print("\nTop sellers:")
    print(
        summary["top_sellers"][
            ["seller_name", "rating", "reviews_count"]
        ].to_string(index=False)
    )

    print(f"\nExcel report saved: {excel_path}")