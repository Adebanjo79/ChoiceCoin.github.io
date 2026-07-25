#!/usr/bin/env python3
"""
trend_winner_bot.py
Find dropshipping product winners on eBay UK using Best Selling-style
search results, Google Trends, and simple profit filters.
Sends top results to Telegram. Runs Mon/Wed/Fri at 09:00.
"""

import asyncio
import re
import sys
import time
from datetime import datetime

import pandas as pd
import schedule
from bs4 import BeautifulSoup
from pytrends.request import TrendReq
from urllib3.util.retry import Retry
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from telegram import Bot
from webdriver_manager.chrome import ChromeDriverManager

# =============================================================================
# CONFIG — put your real Telegram credentials here
# =============================================================================
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # <-- replace with your bot token
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"  # <-- replace with your chat id

EBAY_FEE_RATE = 0.13
SHIPPING_BUFFER = 2.0  # flat £2 buffer
ALI_PRICE_RATIO = 0.25  # estimate AliExpress cost as 25% of eBay price

# Filters
MIN_SOLD = 100
MIN_PROFIT = 8.0
MIN_MARGIN = 0.40  # 40%
MIN_TREND_CHANGE = 20.0  # %

# Also track mega-sellers (100k+ sold)
MEGA_SOLD_THRESHOLD = 100_000

# Category searches that surface "Best Selling" style results with sold counts
CATEGORIES = {
    "Car Accessories": ["car accessories", "car phone holder"],
    "Pet Supplies": ["pet supplies", "dog toys"],
    "Home": ["home decor", "led strip lights"],
    # Extra: trending / viral products that often show 100k+ sold
    "Trending 100k+": ["100000+ sold", "100k sold", "best seller"],
}

CSV_PATH = "trend_winners.csv"
SLEEP_BETWEEN_PAGES = 3
SLEEP_BETWEEN_TRENDS = 5
MAX_ITEMS_PER_SEARCH = 20


# =============================================================================
# Selenium helper
# =============================================================================
def make_driver():
    """Create a headless Chrome driver with light anti-bot options."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def accept_cookies(driver):
    """Click the GDPR accept button if it appears."""
    for sel in ("#gdpr-banner-accept", "button#consent-banner-btn-accept"):
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, sel)
            if buttons:
                buttons[0].click()
                time.sleep(1)
                return
        except Exception:
            continue


def warm_up(driver):
    """Open eBay UK homepage first so search pages load properly."""
    print("Warming up eBay UK session...")
    driver.get("https://www.ebay.co.uk/")
    time.sleep(SLEEP_BETWEEN_PAGES)
    accept_cookies(driver)


# =============================================================================
# Parsing helpers
# =============================================================================
def parse_price(text):
    """Extract a float price from strings like '£12.99' or 'GBP 12.99'."""
    if not text:
        return None
    # Prefer the first standalone price (ignore ranges like £10 to £20 by taking first)
    match = re.search(r"[£$]?([\d,]+(?:\.\d+)?)", text.replace("\xa0", " "))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_sold(text):
    """
    Parse sold counts like '100+ sold', '1.2K sold', '100,000+ sold', '100K+ sold'.
    Returns an integer estimate (lower bound).
    """
    if not text:
        return 0
    text = text.strip().lower()

    # Keep commas out for numeric parse, but detect k/m first on original-ish text
    compact = text.replace(",", "").replace(" ", "")

    def _to_float(num_str):
        try:
            if not num_str or num_str == ".":
                return None
            return float(num_str)
        except ValueError:
            return None

    match = re.search(r"(\d+(?:\.\d+)?)k\+?sold", compact)
    if match:
        value = _to_float(match.group(1))
        if value is not None:
            return int(value * 1000)

    match = re.search(r"(\d+(?:\.\d+)?)m\+?sold", compact)
    if match:
        value = _to_float(match.group(1))
        if value is not None:
            return int(value * 1_000_000)

    match = re.search(r"(\d+(?:\.\d+)?)\+?sold", compact)
    if match:
        value = _to_float(match.group(1))
        if value is not None:
            return int(value)

    # Fallback with spaces: "100 000+ sold" / "100,000+ sold"
    match = re.search(r"(\d[\d,\.\s]*)\+?\s*sold", text)
    if match:
        digits = re.sub(r"[^\d.]", "", match.group(1))
        value = _to_float(digits)
        if value is not None:
            return int(value)

    return 0


def clean_product_name(title):
    """Shorten title for Google Trends (first ~5 meaningful words)."""
    if not title:
        return ""
    title = re.sub(r"Opens in a new window or tab", "", title, flags=re.I)
    words = re.sub(r"[^\w\s]", " ", title).split()
    skip = {"for", "with", "and", "the", "a", "an", "of", "to", "in", "on", "or"}
    keep = [w for w in words if w.lower() not in skip][:5]
    return " ".join(keep) if keep else " ".join(words[:5])


def extract_sold_text(card):
    """Find sold-count text inside a result card."""
    for row in card.select(".s-card__attribute-row, .s-card__caption, span, div"):
        text = row.get_text(" ", strip=True)
        if re.search(r"\d.*sold", text, re.I) and len(text) < 40:
            return text
    blob = card.get_text(" ", strip=True)
    match = re.search(r"[\d.,]+\s*[km]?\+?\s*sold", blob, re.I)
    return match.group(0) if match else ""


# =============================================================================
# Scrape eBay UK
# =============================================================================
def search_ebay(driver, query):
    """
    Search eBay UK via the homepage search box (more reliable than deep links)
    and return parsed listing cards.
    """
    print(f"  Searching: {query}")
    items_html = []

    try:
        driver.get("https://www.ebay.co.uk/")
        time.sleep(2)
        accept_cookies(driver)

        box = driver.find_element(By.CSS_SELECTOR, "#gh-ac")
        box.clear()
        box.send_keys(query)
        box.send_keys(Keys.ENTER)
        time.sleep(SLEEP_BETWEEN_PAGES)

        # Prefer Best Match / popularity order (sold badges show up here)
        soup = BeautifulSoup(driver.page_source, "lxml")
        cards = soup.select("li.s-card") or soup.select(".s-card") or soup.select("li.s-item")
        print(f"    cards found: {len(cards)}")
        items_html = cards[:MAX_ITEMS_PER_SEARCH]
    except Exception as e:
        print(f"    Search error for '{query}': {e}")

    return items_html


def parse_card(card, category_name):
    """Pull Title, Price, Sold Count, Link from one result card."""
    title_el = card.select_one(".s-card__title, .s-item__title, [role='heading']")
    price_el = card.select_one(".s-card__price, .s-item__price")
    link_el = card.select_one("a[href*='/itm/'], a.s-card__link, a.s-item__link")

    title = title_el.get_text(" ", strip=True) if title_el else ""
    title = re.sub(r"Opens in a new window or tab", "", title, flags=re.I).strip()
    if not title or title.lower() == "shop on ebay":
        return None

    price = parse_price(price_el.get_text(" ", strip=True) if price_el else "")
    sold = parse_sold(extract_sold_text(card))
    link = ""
    if link_el and link_el.has_attr("href"):
        link = link_el["href"].split("?")[0]

    if sold < MIN_SOLD or price is None or not link:
        return None

    return {
        "Category": category_name,
        "Title": title,
        "Price": price,
        "Sold": sold,
        "Link": link,
        "Mega_Seller": sold >= MEGA_SOLD_THRESHOLD,
    }


def scrape_all_categories(driver):
    """Scrape all configured categories / trending searches."""
    all_items = []
    for category_name, queries in CATEGORIES.items():
        print(f"\n[{category_name}]")
        for query in queries:
            cards = search_ebay(driver, query)
            kept = 0
            for card in cards:
                try:
                    item = parse_card(card, category_name)
                    if item:
                        all_items.append(item)
                        kept += 1
                except Exception as e:
                    print(f"    Skip card error: {e}")
            print(f"    kept with {MIN_SOLD}+ sold: {kept}")
            time.sleep(SLEEP_BETWEEN_PAGES)
    return all_items


# =============================================================================
# Google Trends
# =============================================================================
def _patch_pytrends_urllib3():
    """
    pytrends still passes method_whitelist= which urllib3 v2 removed.
    Patch Retry so both old and new kwargs work.
    """
    if getattr(Retry, "_trend_winner_patched", False):
        return

    original_init = Retry.__init__

    def patched_init(self, *args, **kwargs):
        if "method_whitelist" in kwargs and "allowed_methods" not in kwargs:
            kwargs["allowed_methods"] = kwargs.pop("method_whitelist")
        elif "method_whitelist" in kwargs:
            kwargs.pop("method_whitelist")
        return original_init(self, *args, **kwargs)

    Retry.__init__ = patched_init
    Retry._trend_winner_patched = True


_patch_pytrends_urllib3()


def get_trend_change(keyword):
    """
    Check Google Trends (UK, last ~90 days) and return % change
    from first half of the window to the second half.
    """
    if not keyword:
        return 0.0

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }

    for attempt in range(3):
        try:
            pytrends = TrendReq(
                hl="en-GB",
                tz=0,
                retries=1,
                backoff_factor=0.5,
                requests_args={"headers": headers},
            )
            pytrends.build_payload([keyword], timeframe="today 3-m", geo="GB")
            df = pytrends.interest_over_time()
            time.sleep(SLEEP_BETWEEN_TRENDS)  # avoid rate limits / blocks

            if df is None or df.empty or keyword not in df.columns:
                return 0.0

            series = df[keyword].astype(float)
            mid = len(series) // 2
            if mid == 0:
                return 0.0

            first_avg = float(series.iloc[:mid].mean())
            second_avg = float(series.iloc[mid:].mean())

            if first_avg <= 0:
                return 100.0 if second_avg > 0 else 0.0

            change = ((second_avg - first_avg) / first_avg) * 100.0
            return round(change, 2)
        except Exception as e:
            wait = 15 * (attempt + 1)
            print(f"  Trends error for '{keyword}' (try {attempt + 1}/3): {e}")
            print(f"  Waiting {wait}s before retry...")
            time.sleep(wait)

    return 0.0


# =============================================================================
# Profit math
# =============================================================================
def estimate_ali_price(ebay_price):
    """
    Estimate Aliexpress cost as 25% of eBay price.

    TODO: Replace this estimate with real Aliexpress scraping.
    Suggested place to add real scraping:
      - Search Aliexpress for the product title
      - Parse the lowest / average supplier price
      - Use that value instead of ebay_price * 0.25
    Example entry point: scrape_aliexpress_price(product_title) -> float
    """
    return round(ebay_price * ALI_PRICE_RATIO, 2)


def calc_profit_and_margin(ebay_price, ali_price):
    """Profit = Ebay - Ali - Ebay_Fee_13% - 2; Margin = Profit / Ebay."""
    ebay_fee = ebay_price * EBAY_FEE_RATE
    profit = ebay_price - ali_price - ebay_fee - SHIPPING_BUFFER
    margin = (profit / ebay_price) if ebay_price else 0.0
    return round(profit, 2), round(margin, 4)


# =============================================================================
# Telegram
# =============================================================================
async def _send_telegram_async(message):
    """Internal async send using python-telegram-bot."""
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=message,
        disable_web_page_preview=False,
    )


def send_telegram_message(message):
    """
    Send a Telegram message.
    Replace TELEGRAM_TOKEN and TELEGRAM_CHAT_ID at the top of this file.
    """
    if TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or TELEGRAM_CHAT_ID == "YOUR_CHAT_ID":
        print("\n[Telegram] Skipping send — set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID first.")
        print("--- Message that would be sent ---")
        print(message)
        print("----------------------------------")
        return False

    try:
        asyncio.run(_send_telegram_async(message))
        print("[Telegram] Message sent.")
        return True
    except Exception as e:
        print(f"[Telegram] Failed to send: {e}")
        return False


def format_top_results_message(df_top):
    """Build a simple Telegram message for the top 3 winners."""
    lines = ["eBay UK Trend Winners\n"]
    for i, row in enumerate(df_top.itertuples(index=False), start=1):
        mega = " | 100k+ sold" if getattr(row, "Mega_Seller", False) else ""
        title = str(row.Title)[:80]
        lines.append(
            f"{i}. {title}\n"
            f"   Profit: £{row.Profit:.2f} | Trend: {row.Trend_Change}%{mega}\n"
            f"   {row.Link}\n"
        )
    return "\n".join(lines)


# =============================================================================
# Main pipeline
# =============================================================================
def find_winners():
    """Scrape → trends → profit filter → CSV → Telegram."""
    print("=" * 60)
    print(f"Trend Winner Bot started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    all_items = []
    driver = None

    try:
        driver = make_driver()
        warm_up(driver)
        all_items = scrape_all_categories(driver)
    except Exception as e:
        print(f"Driver/scrape error: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    empty_cols = [
        "Category",
        "Title",
        "Price",
        "Sold",
        "Link",
        "Mega_Seller",
        "Ali_Price",
        "Profit",
        "Margin",
        "Trend_Change",
        "Trend_Keyword",
    ]

    if not all_items:
        print("No items scraped. Saving empty CSV and finishing.")
        pd.DataFrame(columns=empty_cols).to_csv(CSV_PATH, index=False)
        print("Bot Finished. Found 0 winners")
        return 0

    # Deduplicate by link
    seen = set()
    unique = []
    for item in all_items:
        if item["Link"] in seen:
            continue
        seen.add(item["Link"])
        unique.append(item)
    all_items = unique

    mega_count = sum(1 for i in all_items if i["Mega_Seller"])
    print(f"\nUnique items with 100+ sold: {len(all_items)} (100k+ sold: {mega_count})")

    winners = []
    for item in all_items:
        try:
            ali_price = estimate_ali_price(item["Price"])
            # TODO(aliexpress): swap estimate_ali_price() for real scrape here
            profit, margin = calc_profit_and_margin(item["Price"], ali_price)

            # Cheap pre-filter before hitting Google Trends
            if item["Sold"] < MIN_SOLD or profit < MIN_PROFIT or margin < MIN_MARGIN:
                print(
                    f"skip money filter: {item['Title'][:50]} | "
                    f"sold={item['Sold']} profit=£{profit} margin={margin * 100:.1f}%"
                )
                continue

            keyword = clean_product_name(item["Title"])
            print(
                f"Trends: {keyword} | sold={item['Sold']} "
                f"price=£{item['Price']} profit=£{profit}"
            )
            trend_change = get_trend_change(keyword)

            # Keep if: Sold >= 100 AND Profit >= 8 AND Margin >= 40% AND Trend >= 20%
            # Mega sellers (100k+) use the same quality filters.
            if trend_change >= MIN_TREND_CHANGE:
                winners.append(
                    {
                        **item,
                        "Ali_Price": ali_price,
                        "Profit": profit,
                        "Margin": round(margin * 100, 2),  # store as %
                        "Trend_Change": trend_change,
                        "Trend_Keyword": keyword,
                    }
                )
                print(
                    f"  WINNER: profit=£{profit} margin={margin * 100:.1f}% "
                    f"trend={trend_change}% mega={item['Mega_Seller']}"
                )
            else:
                print(f"  skip trend: {trend_change}% < {MIN_TREND_CHANGE}%")
        except Exception as e:
            print(f"  Item error: {e}")
            continue

    df = pd.DataFrame(winners)
    if not df.empty:
        df = df.sort_values(
            by=["Mega_Seller", "Profit", "Trend_Change", "Sold"],
            ascending=[False, False, False, False],
        )
    else:
        df = pd.DataFrame(columns=empty_cols)

    df.to_csv(CSV_PATH, index=False)
    print(f"\nSaved {len(df)} winners to {CSV_PATH}")

    if not df.empty:
        top3 = df.head(3)
        send_telegram_message(format_top_results_message(top3))
    else:
        send_telegram_message("eBay UK Trend Bot: no winners this run.")

    print(f"Bot Finished. Found {len(df)} winners")
    return len(df)


def job():
    """Scheduled job wrapper with error handling."""
    try:
        find_winners()
    except Exception as e:
        print(f"Job failed: {e}")
        try:
            send_telegram_message(f"Trend Winner Bot error: {e}")
        except Exception:
            pass


def main():
    print("Scheduling bot for Monday, Wednesday, Friday at 09:00")
    schedule.every().monday.at("09:00").do(job)
    schedule.every().wednesday.at("09:00").do(job)
    schedule.every().friday.at("09:00").do(job)

    # Run once now so you can test immediately
    print("Running once now...")
    job()

    print("Waiting for schedule (Mon/Wed/Fri 09:00). Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    # `python trend_winner_bot.py once` → single run, no schedule loop
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        job()
    else:
        main()
