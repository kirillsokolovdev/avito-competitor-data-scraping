# Competitor Radar Bot

🇷🇺 Russian version: [README.ru.md](README.ru.md)

Telegram bot for automated competitor analysis on Avito.

The bot collects listings from Avito using Selenium, analyzes seller and pricing data, generates market statistics, and exports the results into a formatted Excel report.

This project was built as a MVP portfolio project focused on simplicity, clean architecture, and practical business value.

---

# Features

* Telegram bot interface (Aiogram 3)
* Step-by-step user interaction via FSM
* Avito scraping with Selenium
* Headless Chrome browser automation
* Basic anti-detection configuration
* Market analytics with Pandas
* Styled Excel report generation
* Median price calculation
* Top sellers ranking
* Logging and error handling
* Clean modular architecture

---

# Tech Stack

* Python 3.11
* Aiogram 3
* Selenium
* Pandas
* Openpyxl
* WebDriver Manager
* Python-dotenv

---

# Project Structure

```text
avito-competitor-data-scraping
│
├── bot.py                  # Telegram bot entry point
├── parser.py               # Avito scraping module
├── analytics.py            # Analytics + Excel export
├── config.py               # Environment variables and config
│
├── requirements.txt        # Python dependencies
├── README.md               # English documentation
├── README.ru.md            # Russian documentation
├── LICENSE                 # MIT license
├── .gitignore
├── .env.example
│
├── output/
│   └── .gitkeep
│
└── docs/
    └── screenshots.zip/
        ├── excel_all_cards.png
        ├── excel_summary.png
        └── logs.png
    └── videos.zip/
        └── bot_working.mp4
```

---

# How It Works

## 1. Telegram Bot

The user interacts with the bot through a simple FSM flow:

1. Enter search query
2. Enter city
3. Wait for parsing and analytics
4. Receive market summary
5. Download Excel report

---

## 2. Parsing Module

The parser:

* launches headless Chrome via Selenium;
* opens Avito search pages;
* scrolls dynamically to load listings;
* extracts:

  * title,
  * price,
  * seller name,
  * rating,
  * review count,
  * URL.

The scraper includes:

* custom User-Agent;
* disabled AutomationControlled flag;
* randomized delays;
* graceful error handling.

---

## 3. Analytics Module

The analytics pipeline:

* converts raw data into a Pandas DataFrame;
* cleans and normalizes prices;
* calculates:

  * median market price,
  * min/max prices,
  * top sellers by rating/reviews;
* exports a formatted Excel workbook.

The generated workbook contains:

* full listings sheet;
* summary sheet;
* custom styling via Openpyxl.

---

# Installation

## 1. Clone repository

```bash
git clone https://github.com/kirillsokolovdev/avito-competitor-data-scraping.git
cd avito-competitor-data-scraping
```

---

## 2. Create virtual environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```


---

## 4. Configure environment variables

Create `.env` file from `.env.example`.

Example:

```env
BOT_TOKEN=your_telegram_bot_token_here
```

---

# Running the Project

Start the Telegram bot:

```bash
python bot.py
```

The bot will start polling Telegram updates.

---

# Example Workflow

1. User sends `/start`
2. Bot asks for a search query
3. User enters:

   ```
   iPhone 15
   ```
4. Bot asks for city
5. User enters:

   ```
   Казань
   ```
6. Bot:

   * parses Avito listings;
   * analyzes market data;
   * generates Excel report;
   * sends analytics summary and report file.

---

# Excel Report

Generated Excel reports include:

## Sheet 1 — All Listings

Contains:

* listing titles,
* prices,
* seller names,
* ratings,
* review counts,
* direct links.

Features:

* alternating row colors,
* borders,
* frozen header,
* hyperlink styling,
* optimized column widths.

---

## Sheet 2 — Summary

Contains:

* search query,
* city,
* total listings,
* listings with prices,
* median price,
* min/max prices,
* top sellers.

---

# Screenshots

Project screenshots are available in:

```text
docs/screenshots.zip/
```

Included:

* Excel listings sheet
* Excel summary sheet
* Application logs

---

# Demo Video

Demo video:

```text
docs/videos.zip/bot_working.mp4
```

---

# Logging

Example log output:

```text
2026-01-01 12:00:00 [INFO] Parser started
2026-01-01 12:00:03 [INFO] Listing cards found: 20
2026-01-01 12:00:10 [INFO] Excel report saved
```

---

# Error Handling

The project includes:

* Selenium timeout handling;
* missing field protection;
* unsupported city validation;
* empty search result handling;
* safe browser shutdown via `finally`.

---

# Limitations

This MVP version intentionally keeps the architecture simple.

Current limitations:

* supports only predefined Russian cities;
* parses only first-page listings;
* depends on Avito page structure;
* no database persistence;
* in-memory FSM storage only.

---

# Future Improvements

Possible future upgrades:

* async parsing;
* advanced seller analytics;
* historical price tracking;
* web dashboard;

---

# Educational Purpose

This project was created as:

* a portfolio MVP;
* a freelance showcase project;
* a practical Python automation exercise.

The focus was on:

* readable code,
* modular structure,
* maintainability,
* realistic business functionality.

---

# License

This project is licensed under the MIT License.

---

# Author

Kirill Sokolov

Junior Python Developer
