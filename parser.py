# parser.py
# Запуск для теста: python parser.py
# Зависимости: pip install selenium webdriver-manager

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


# --- Настройки ---
BASE_URL = "https://www.avito.ru"
MAX_LISTINGS = 20  # Сколько объявлений собираем. Начнём с 20 - этого хватит для аналитики.


def _build_driver() -> webdriver.Chrome:
    """
    Создаёт и настраивает экземпляр Chrome-драйвера.
    Вынесено в отдельную функцию, чтобы не засорять основную логику.
    """
    options = webdriver.ChromeOptions()

    # --- Маскировка под обычного пользователя ---
    # Убираем флаг, по которому сайты определяют автоматизацию
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Подставляем реальный User-Agent (строку можно обновить на актуальную)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    # Headless = браузер работает без окна (нужно для сервера и бота)
    # Пока закомментировано — при первом тесте лучше видеть, что происходит в браузере
    # options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    # webdriver-manager сам скачивает нужную версию chromedriver — не нужно делать это вручную
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # Дополнительно скрываем webdriver через JavaScript
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    return driver


def _slow_scroll(driver: webdriver.Chrome) -> None:
    """
    Плавно прокручивает страницу вниз, имитируя живого пользователя.
    Это нужно для двух вещей:
    1. Обмануть защиту сайта (боты обычно не скроллят).
    2. Подгрузить ленивые (lazy-load) элементы страницы.
    """
    # Узнаём полную высоту страницы
    total_height = driver.execute_script("return document.body.scrollHeight")
    current_position = 0
    step = 300  # Скроллим по 300px за раз

    while current_position < total_height:
        current_position += step
        driver.execute_script(f"window.scrollTo(0, {current_position});")
        # Случайная пауза между скроллами — имитирует чтение
        time.sleep(random.uniform(0.1, 0.4))


def _extract_price(price_text: str) -> float | None:
    numbers = re.findall(r"\d+", price_text.replace(" ", ""))
    if not numbers:
        return None
    return float("".join(numbers))


def _extract_rating(rating_text: str) -> float | None:
    try:
        return float(rating_text.replace(",", "."))
    except:
        return None


def _extract_reviews(reviews_text: str) -> int:
    numbers = re.findall(r"\d+", reviews_text)
    if not numbers:
        return 0
    return int(numbers[0])


def _parse_listing(card) -> dict | None:
    """
    Извлекает данные из одной карточки объявления.
    Все селекторы проверены на реальном HTML Avito (май 2026).
    """
    result = {}

    # --- Название + Ссылка ---
    # data-marker='item-title' — это тег <a>, поэтому сразу берём и текст и href
    try:
        title_el = card.find_element(By.CSS_SELECTOR, "[data-marker='item-title']")
        result["title"] = title_el.text.strip()
        href = title_el.get_attribute("href")
        # Avito возвращает относительные ссылки вида /moskva/..., добавляем домен
        result["url"] = href if href.startswith("http") else BASE_URL + href
    except NoSuchElementException:
        # Нет заголовка = это не объявление (баннер, реклама), пропускаем
        return None

    # --- Цена ---
    # data-marker='item-price-value' содержит текст вида "от 500₽" или "Цена договорная"
    # Важно: используем .text, а НЕ .get_attribute("content") — у этого элемента нет атрибута content
    try:
        price_el = card.find_element(By.CSS_SELECTOR, "[data-marker='item-price-value']")
        price_text = price_el.text.strip()
        result["price_raw"] = price_text
        result["price"] = _extract_price(price_text)
    except NoSuchElementException:
        result["price_raw"] = None

    # --- Имя продавца ---
    # Блок продавца — это <a href="/brands/..."> или <a href="/user/...">
    # Внутри этой ссылки первый <p> содержит имя продавца.
    # У части карточек (новые продавцы без профиля) этого блока нет вообще — это нормально.
    try:
        # href*='/brands/' означает "href содержит /brands/" — CSS-селектор substring
        seller_link = card.find_element(
            By.CSS_SELECTOR, "a[href*='/brands/'], a[href*='/user/']"
        )
        # Внутри ссылки ищем первый <p> — это имя. Рейтинг и отзывы идут после.
        seller_name_el = seller_link.find_element(By.TAG_NAME, "p")
        result["seller_name"] = seller_name_el.text.strip()
    except NoSuchElementException:
        result["seller_name"] = None

    # --- Рейтинг ---
    # ИСПРАВЛЕНО: был 'seller-info/rating' — такого маркера не существует на Avito
    # Правильный маркер: 'seller-info/score' (содержит число вида "4,7")
    try:
        rating_el = card.find_element(By.CSS_SELECTOR, "[data-marker='seller-info/score']")
        rating_text = rating_el.text.strip()
        result["rating_raw"] = rating_text
        result["rating"] = _extract_rating(rating_text)
    except NoSuchElementException:
        result["rating"] = None

    # --- Количество отзывов ---
    # ИСПРАВЛЕНО: был 'seller-info/score' — это рейтинг, а не отзывы
    # Правильный маркер: 'seller-info/summary' (содержит текст вида "124 отзыва")
    try:
        reviews_el = card.find_element(By.CSS_SELECTOR, "[data-marker='seller-info/summary']")
        reviews_text = reviews_el.text.strip()
        result["reviews_raw"] = reviews_text
        result["reviews_count"] = _extract_reviews(reviews_text)
    except NoSuchElementException:
        result["reviews_count"] = 0

    return result


def parse_avito(query: str, city: str) -> list[dict]:
    """
    Главная публичная функция модуля.
    Принимает поисковый запрос и город, возвращает список словарей с данными.

    Пример вызова:
        data = parse_avito(query="ремонт ноутбуков", city="Москва")
    """
    print(f"[Parser] Запуск. Запрос: '{query}', Город: '{city}'")
    driver = _build_driver()
    listings = []

    try:
        # Формируем URL поиска. Avito принимает город и запрос прямо в URL.
        # Пробелы в запросе заменяем на '+' — стандартный URL-формат.
        formatted_query = query.replace(" ", "+")

        # Словарь самых популярных городов: русское название → URL-slug для Avito
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

        if not formatted_city:
            print(f"[Parser] Город '{city}' не найден в справочнике. Доступные города: {list(CITY_SLUGS.keys())}")
            return []

        url = f"{BASE_URL}/{formatted_city}?q={formatted_query}"

        print(f"[Parser] Открываем: {url}")
        driver.get(url)

        # Ждём, пока появится хотя бы одна карточка объявления.
        # Таймаут 15 секунд — если страница не загрузится, получим TimeoutException.
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-marker='item']"))
        )

        # Небольшая пауза после загрузки — даём странице "устояться"
        time.sleep(random.uniform(1.5, 3.0))

        # Скроллим страницу, чтобы подгрузить все объявления
        _slow_scroll(driver)
        # Собираем все найденные карточки объявлений
        cards = driver.find_elements(By.CSS_SELECTOR, "[data-marker='item']")
        print(f"[Parser] Найдено карточек на странице: {len(cards)}")

        # Парсим каждую карточку, пока не наберём нужное количество
        for card in cards[:MAX_LISTINGS]:
            listing_data = _parse_listing(card)
            if listing_data:  # Пропускаем карточки, которые вернули None
                listings.append(listing_data)

        print(f"[Parser] Успешно собрано объявлений: {len(listings)}")

    except TimeoutException:
        # Страница не загрузилась или объявлений нет — возвращаем пустой список
        print(f"[Parser] Таймаут! Страница не загрузилась или объявления не найдены.")
    except Exception as e:
        # Ловим любые другие непредвиденные ошибки — скрипт не падает, а сообщает о проблеме
        print(f"[Parser] Непредвиденная ошибка: {e}")
    finally:
        # Блок finally выполняется ВСЕГДА — браузер закроется даже при ошибке
        driver.quit()
        print("[Parser] Браузер закрыт.")

    return listings


# --- Блок для самостоятельного тестирования ---
# Этот код выполняется только при запуске файла напрямую: python parser.py
# При импорте модуля в bot.py он не запустится.
if __name__ == "__main__":
    test_data = parse_avito(query="ремонт ноутбуков", city="Москва")

    if test_data:
        #print("\n--- Первые 3 результата ---")
        for item in test_data:
            print(item)
    else:
        print("\nДанные не собраны. Проверь подключение или селекторы.")