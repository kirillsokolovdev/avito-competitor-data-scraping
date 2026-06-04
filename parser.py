# parser.py
# Run locally for testing:
# python parser.py

import time
import random
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager


# Base Avito domain
BASE_URL = "https://www.avito.ru"

# Maximum number of listings to parse per request
MAX_LISTINGS = 20


def _build_driver() -> webdriver.Chrome:
    """
    Create and configure a Chrome WebDriver instance.

    Includes:
    - basic anti-detection settings
    - custom User-Agent
    - browser window configuration
    """

    options = webdriver.ChromeOptions()

    # Hide common Selenium automation flags
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Set a realistic browser User-Agent
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    # Enable headless mode for production deployment
    # options.add_argument("--headless=new")

    # Recommended Chrome stability flags
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    # Automatically install a compatible ChromeDriver version
    service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=options)

    # Hide navigator.webdriver flag via JavaScript
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    return driver


def _slow_scroll(driver: webdriver.Chrome) -> None:
    """
    Scroll the page gradually to trigger lazy-loaded content
    and imitate human-like browsing behavior.
    """

    total_height = driver.execute_script(
        "return document.body.scrollHeight"
    )

    current_position = 0
    step = 300

    while current_position < total_height:
        current_position += step

        driver.execute_script(
            f"window.scrollTo(0, {current_position});"
        )

        # Randomized delay helps reduce bot-like behavior
        time.sleep(random.uniform(0.1, 0.4))


def _extract_price(price_text: str) -> float | None:
    """
    Extract numeric price value from raw Avito price text.

    Examples:
    - 'от 1 000 ₽' -> 1000.0
    - 'Цена договорная' -> None
    """

    numbers = re.findall(
        r"\d+",
        price_text.replace(" ", "")
    )

    if not numbers:
        return None

    return float("".join(numbers))


def _extract_rating(rating_text: str) -> float | None:
    """
    Convert Avito rating string to float.

    Example:
    - '4,7' -> 4.7
    """

    try:
        return float(rating_text.replace(",", "."))
    except:
        return None


def _extract_reviews(reviews_text: str) -> int:
    """
    Extract review count from seller summary text.

    Example:
    - '124 отзыва' -> 124
    """

    numbers = re.findall(r"\d+", reviews_text)

    if not numbers:
        return 0

    return int(numbers[0])


def _parse_listing(card) -> dict | None:
    """
    Parse a single Avito listing card.

    Returns:
        dict with normalized listing data
        or None if the card is invalid.
    """

    result = {}

    # Extract listing title and URL
    try:
        title_el = card.find_element(
            By.CSS_SELECTOR,
            "[data-marker='item-title']"
        )

        result["title"] = title_el.text.strip()

        href = title_el.get_attribute("href")

        # Convert relative URLs to absolute URLs
        result["url"] = (
            href if href.startswith("http")
            else BASE_URL + href
        )

    except NoSuchElementException:
        # Skip invalid cards without title
        return None

    # Extract listing price
    try:
        price_el = card.find_element(
            By.CSS_SELECTOR,
            "[data-marker='item-price-value']"
        )

        price_text = price_el.text.strip()

        result["price_raw"] = price_text
        result["price"] = _extract_price(price_text)

    except NoSuchElementException:
        result["price_raw"] = None

    # Extract seller name
    try:
        seller_link = card.find_element(
            By.CSS_SELECTOR,
            "a[href*='/brands/'], a[href*='/user/']"
        )

        seller_name_el = seller_link.find_element(
            By.TAG_NAME,
            "p"
        )

        result["seller_name"] = seller_name_el.text.strip()

    except NoSuchElementException:
        result["seller_name"] = None

    # Extract seller rating
    try:
        rating_el = card.find_element(
            By.CSS_SELECTOR,
            "[data-marker='seller-info/score']"
        )

        rating_text = rating_el.text.strip()

        result["rating_raw"] = rating_text
        result["rating"] = _extract_rating(rating_text)

    except NoSuchElementException:
        result["rating"] = None

    # Extract seller review count
    try:
        reviews_el = card.find_element(
            By.CSS_SELECTOR,
            "[data-marker='seller-info/summary']"
        )

        reviews_text = reviews_el.text.strip()

        result["reviews_raw"] = reviews_text
        result["reviews_count"] = _extract_reviews(reviews_text)

    except NoSuchElementException:
        result["reviews_count"] = 0

    return result


def parse_avito(query: str, city: str) -> list[dict]:
    """
    Main parser entry point.

    Args:
        query: search query text
        city: city name in Russian

    Returns:
        List of parsed listing dictionaries.
    """

    print(f"[Parser] Запуск. Запрос: '{query}', Город: '{city}'")

    driver = _build_driver()

    listings = []

    try:
        # Convert query string to URL format
        formatted_query = query.replace(" ", "+")

        # Mapping: Russian city names -> Avito URL slugs
        CITY_SLUGS = {
            "москва": "moskva",
            "санкт-петербург": "sankt-peterburg",
            "санкт петербург": "sankt-peterburg",
            "питер": "sankt-peterburg",
            "новосибирск": "novosibirsk",
            "екатеринбург": "ekaterinburg",
            "казань": "kazan",
            "нижний новгород": "nizhniy_novgorod",
            "челябинск": "chelyabinsk",
            "самара": "samara",
            "уфа": "ufa",
            "ростов-на-дону": "rostov-na-donu",
            "ростов на дону": "rostov-na-donu",
            "омск": "omsk",
            "краснодар": "krasnodar",
            "воронеж": "voronezh",
            "пермь": "perm",
            "волгоград": "volgograd",
        }

        city_key = city.lower().strip()

        formatted_city = CITY_SLUGS.get(city_key)

        # Stop execution if city slug is unsupported
        if not formatted_city:
            print(
                f"[Parser] Город '{city}' не найден в справочнике. "
                f"Доступные города: {list(CITY_SLUGS.keys())}"
            )
            return []

        # Build Avito search URL
        url = f"{BASE_URL}/{formatted_city}?q={formatted_query}"

        print(f"[Parser] Открываем: {url}")

        driver.get(url)

        # Wait until at least one listing card appears
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[data-marker='item']")
            )
        )

        # Small delay after page load stabilization
        time.sleep(random.uniform(1.5, 3.0))

        # Trigger lazy-loaded listing blocks
        _slow_scroll(driver)

        # Collect all visible listing cards
        cards = driver.find_elements(
            By.CSS_SELECTOR,
            "[data-marker='item']"
        )

        print(f"[Parser] Найдено карточек на странице: {len(cards)}")

        # Parse listing cards up to MAX_LISTINGS limit
        for card in cards[:MAX_LISTINGS]:

            listing_data = _parse_listing(card)

            # Skip invalid or empty cards
            if listing_data:
                listings.append(listing_data)

        print(
            f"[Parser] Успешно собрано объявлений: {len(listings)}"
        )

    except TimeoutException:
        # Page did not load or listings were not found
        print(
            "[Parser] Таймаут! "
            "Страница не загрузилась или объявления не найдены."
        )

    except Exception as e:
        # Catch unexpected runtime errors
        print(f"[Parser] Непредвиденная ошибка: {e}")

    finally:
        # Always close browser session
        driver.quit()

        print("[Parser] Браузер закрыт.")

    return listings


# Local test entry point
# This block runs only when parser.py is executed directly
if __name__ == "__main__":

    test_data = parse_avito(
        query="iPhone 15",
        city="Казань"
    )

    if test_data:
        for item in test_data:
            print(item)

    else:
        print(
            "\nДанные не собраны. "
            "Проверь подключение или селекторы."
        )
