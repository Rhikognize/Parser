from requests import Session
import requests
from bs4 import BeautifulSoup
from math import ceil
from playwright.sync_api import sync_playwright
import time
from MoveToExcel import create_excel, save_to_excel
import re
import os

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BASE_URL = "https://immobiliare.md"
ADDITIONAL_URL = "https://immobiliare.md"
PAGE_COUNT = 0
CARD_COUNT = 0


def get_info(link, session, index):
    info = {}
    response = session.get(link, headers=HEADERS)

    soup = BeautifulSoup(response.text, "lxml")
    data = soup.find("div", class_="space-y-6 md:space-y-10")

    text = data.find(
        "div",
        class_="text-[13px] md:text-base text-gray-600 leading-relaxed whitespace-pre-line",
    ).text

    data_price = soup.find(
        "div",
        class_="text-4xl xl:text-5xl font-black text-gray-900 tracking-tight leading-none mb-4",
    )

    title = data.find(
        "h1",
        class_="text-xl sm:text-2xl md:text-3xl font-black text-gray-900 mb-1 md:mb-2 leading-tight",
    ).text

    location = data.find(
        "div",
        class_="flex items-center text-sm md:text-base text-slate-500 font-medium",
    ).text

    price = data_price.text
    additional = data.find_all(
        "div",
        class_="flex justify-between py-1.5 md:py-2 border-b border-gray-50",
    )

    for item in additional:
        key = item.find(
            "span",
            class_="text-slate-500 text-[13px] md:text-sm",
        )
        val = item.find(
            "span", class_="font-semibold text-gray-900 text-[13px] md:text-sm"
        )
        if key and val:
            info[key.text] = val.text
    type_ = info.get("Tip proprietate", "")
    area = info.get("Suprafață", "")
    rooms = info.get("Camere", "")
    shower_rooms = info.get("Băi", "")
    housing_stock = info.get("Fond locativ", "")
    heating = info.get("Încălzire", "")
    destination = info.get("Destinație", "")
    floor = info.get("Etaj", "")
    if floor == "":
        match = re.search(r"Nivelul\s+(\d/\d)", text)
        if match:
            floor = match.group(1)
    has_double_glazed_windows = "geamuri termopan" in text
    has_AC = "aparat de aer condiționat" in text
    has_underfloor_heating = "încălzire prin pardoseală" in text
    has_furniture = "toată mobila" in text
    print(
        f"URL: {link}\nTitle: {title}\n"
        + f"Location: {location}\nType: {type_}\nArea: {area}\nRooms: {rooms}\nShower rooms: {shower_rooms}\n"
        + f"Floor: {floor}\nHousing stock: {housing_stock}\nHeating: {heating}\nDestination: {destination}\n"
        + f"Price: {price}\nAre mobila: {has_furniture}\nAre geamuri termopan: {has_double_glazed_windows}\n"
        + f"Are aer condiționat: {has_AC}\nAre încălzire prin pardoseală: {has_underfloor_heating}\n"
        + f"{index + 1}/{CARD_COUNT}\n{'-' * 50}"
    )
    return (
        title,
        location,
        rooms,
        shower_rooms,
        area,
        type_,
        housing_stock,
        price,
        floor,
        heating,
        has_furniture,
        has_AC,
        has_underfloor_heating,
        has_double_glazed_windows,
        destination,
        link,
    )


def scroll_and_load():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(ADDITIONAL_URL, wait_until="networkidle")

        time.sleep(3)
        for i in range(PAGE_COUNT):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)
            button = page.locator("button:has-text('Încarcă')")
            if button.count() > 0 and button.is_visible():
                try:
                    button.click()
                    print(f"Clicked button {i + 1} time(s)")
                    page.wait_for_timeout(3000)
                except Exception as e:
                    print(f"Error clicking button: {e}")
                    break
            else:
                print("No more button to click")
                break
        print("Scrolling finished, extracting links...")
        links = page.locator("a.p-5.flex-1")
        urls = []
        for i in range(links.count()):
            href = links.nth(i).get_attribute("href")
            print(f"Extracted URL {i + 1}: {href}")
            if href:
                full_url = BASE_URL + href
                urls.append(full_url)
        browser.close()
        return urls


def count_page():
    response = requests.get(ADDITIONAL_URL, headers=HEADERS)
    soup = BeautifulSoup(response.text, "lxml")
    card_count = soup.find("span", class_="text-primary font-bold").text
    page_count = ceil(int(card_count) / 16)
    return page_count, int(card_count)


if __name__ == "__main__":
    choice = input("Press S for sales-only or R for rent-only: ")
    start = time.perf_counter()
    if choice.lower() == "s":
        ADDITIONAL_URL = BASE_URL + "/sale"
    elif choice.lower() == "r":
        ADDITIONAL_URL = BASE_URL + "/rent"
    else:
        print("Invalid choice, defaulting to sales-only.")
        ADDITIONAL_URL = BASE_URL + "/sale"
    PAGE_COUNT, CARD_COUNT = count_page()
    wb, ws = create_excel()
    row = 2
    links = scroll_and_load()
    session = Session()
    for i, link in enumerate(links):
        data = get_info(link, session, i)
        save_to_excel(ws, row, data)
        row += 1
    filename = "Real_estate_data.xlsx"
    if os.path.exists(filename):
        os.remove(filename)
    wb.save("Real_estate_data.xlsx")
    end = time.perf_counter()
    print(f"Elapsed time: {end - start:.6f} seconds")
