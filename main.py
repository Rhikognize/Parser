from requests import Session
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import time
from MoveToExcel import create_excel, save_to_excel
import re
import os
from concurrent.futures import ThreadPoolExecutor
import threading

# Constants for CSS selectors, headers, base URL, and filename
CSS = {
    "data_container": "space-y-6 md:space-y-10",
    "text": "text-[13px] md:text-base text-gray-600 leading-relaxed whitespace-pre-line",
    "price": "text-4xl xl:text-5xl font-black text-gray-900 tracking-tight leading-none mb-4",
    "title": "text-xl sm:text-2xl md:text-3xl font-black text-gray-900 mb-1 md:mb-2 leading-tight",
    "location": "flex items-center text-sm md:text-base text-slate-500 font-medium",
    "additional": "flex justify-between py-1.5 md:py-2 border-b border-gray-50",
    "key": "text-slate-500 text-[13px] md:text-sm",
    "value": "text-sm md:text-base text-gray-900 font-medium",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BASE_URL = "https://immobiliare.md"
FILENAME = "Real_estate_data.xlsx"

# Thread-local storage for sessions to ensure thread safety in parallel processing
thread_local = threading.local()


def request(link, session):
    """Makes an HTTP GET request to the specified link using the provided session."""
    response = session.get(link, headers=HEADERS)
    if response.status_code != 200:
        print(
            f"Failed to retrieve data for URL: {link} with status code: {response.status_code}"
        )
        return None
    return response.text


def parsing(soup):
    """Parses the BeautifulSoup object to extract real estate information."""
    info = {}
    data = soup.find("div", class_=CSS["data_container"])
    if not data:
        print("Could not find data in the soup")
        return None

    text = safe_text(
        data.find(
            "div",
            class_=CSS["text"],
        )
    )

    price = safe_text(
        soup.find(
            "div",
            class_=CSS["price"],
        )
    )

    title = safe_text(
        data.find(
            "h1",
            class_=CSS["title"],
        )
    )

    location = safe_text(
        data.find(
            "div",
            class_=CSS["location"],
        )
    )

    additional = data.find_all(
        "div",
        class_=CSS["additional"],
    )
    for item in additional:
        key = item.find(
            "span",
            class_=CSS["key"],
        )
        val = item.find("span", class_=CSS["value"])
        if key and val:
            info[key.text] = val.text
    return {
        "title": title,
        "location": location,
        "price": price,
        "text": text,
        "info": info,
    }


def safe_text(element):
    return element.text.strip() if element else ""


def extract_features(text):
    """Extracts specific features from the given text and returns a dictionary with boolean values indicating the presence of each feature."""
    t = text.lower()
    return {
        "has_double_glazed_windows": "geamă termopan" in t,
        "has_AC": "aer condiționat" in t,
        "has_underfloor_heating": "încălzire în pardoseală" in t,
        "has_furniture": "toată mobila" in t,
    }


def extract_floor(text):
    """Extracts the floor information from the given text using a regular expression. Returns the floor information if found, otherwise returns an empty string."""
    match = re.search(r"Nivelul\s+(\d/\d)", text)
    if match:
        return match.group(1)
    return ""


def get_info(link, session):
    """Fetches the HTML content of the given link using the provided session, parses it to extract real estate information, and returns a dictionary containing the extracted data."""
    html = request(link, session)
    if html is None:
        print(f"Skipping URL {link} due to request issues.")
        return None
    soup = BeautifulSoup(html, "lxml")
    p = parsing(soup)
    if p is None:
        print(f"Skipping URL {link} due to parsing issues.")
        return None
    title = p.get("title", "")
    location = p.get("location", "")
    price = p.get("price", "")
    text = p.get("text", "")
    info = p.get("info", {})
    type_ = info.get("Tip proprietate", "")
    area = info.get("Suprafață", "")
    rooms = info.get("Camere", "")
    shower_rooms = info.get("Băi", "")
    housing_stock = info.get("Fond locativ", "")
    heating = info.get("Încălzire", "")
    destination = info.get("Destinație", "")
    floor = info.get("Etaj") or extract_floor(text)
    features = extract_features(text)
    return {
        "title": title,
        "location": location,
        "rooms": rooms,
        "shower_rooms": shower_rooms,
        "area": area,
        "type_": type_,
        "housing_stock": housing_stock,
        "price": price,
        "floor": floor,
        "heating": heating,
        **features,
        "destination": destination,
        "link": link,
    }


def scroll_and_load(url):
    """Scrolls through the webpage at the given URL, clicking the 'Încarcă' button to load more content until all content is loaded. Extracts and returns a list of URLs for individual real estate listings found on the page."""
    with sync_playwright() as p:
        previous_height = 0
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        button = page.locator("button:has-text('Încarcă')")
        time.sleep(3)
        while True:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == previous_height:
                break
            previous_height = new_height
            if button.count() > 0 and button.is_visible():
                try:
                    button.click()
                    page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"Error clicking button: {e}")
                    break
        print("Scrolling finished, extracting links...")
        links = page.locator("a.p-5.flex-1")
        urls = []
        for i in range(links.count()):
            href = links.nth(i).get_attribute("href")
            if href:
                full_url = BASE_URL + href
                urls.append(full_url)
        browser.close()
        return urls


def get_session():
    """One session per thread — reusing sessions improves performance
    while avoiding thread-safety issues with shared state."""
    if not hasattr(thread_local, "session"):
        thread_local.session = Session()
    return thread_local.session


def wrapper(link):
    session = get_session()
    try:
        return get_info(link, session)
    except Exception as e:
        print(f"Error occurred while processing link {link}: {e}")
        return None


if __name__ == "__main__":
    choice = input("Press S for sales-only or R for rent-only: ")
    start = time.perf_counter()
    if choice.lower() == "s":
        additional_url = BASE_URL + "/sale"
    elif choice.lower() == "r":
        additional_url = BASE_URL + "/rent"
    else:
        print("Invalid choice, defaulting to sales-only.")
        additional_url = BASE_URL + "/sale"

    wb, ws = create_excel()
    row = 2
    links = scroll_and_load(additional_url)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(wrapper, links))
    for result in results:
        if result is not None:
            save_to_excel(ws, row, result)
            row += 1
    if os.path.exists(FILENAME):
        os.remove(FILENAME)
    wb.save(FILENAME)
    print(f"{row - 1} rows of data saved to {FILENAME}")
    end = time.perf_counter()
    print(f"Elapsed time: {end - start:.6f} seconds")
