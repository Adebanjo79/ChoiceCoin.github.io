#!/usr/bin/env python3
"""
trend_winner_bot.py

Source real dropshipping product ideas from:
  - eBay UK (search results with real sold badges)
  - Amazon UK Best Sellers (category charts)

Filters out junk (business-for-sale, "100k sold" title spam, crazy prices).
Scores Sold %, Confidence %, optional Google Trends.
Telegram: /status /run | Schedule: Mon/Wed/Fri 09:00
"""

import math
import os
import re
import sys
import threading
import time
from datetime import datetime

import pandas as pd
import requests
import schedule
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pytrends.request import TrendReq
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from urllib3.util.retry import Retry
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

# =============================================================================
# CONFIG
# =============================================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

EBAY_FEE_RATE = 0.13
SHIPPING_BUFFER = 2.0
ALI_PRICE_RATIO = 0.25  # estimate; replace with real Ali scrape later

# Dropship-friendly money filters
MIN_SOLD = 100
MIN_PROFIT = 5.0
MIN_MARGIN = 0.35  # 35%
MIN_PRICE = 4.0
MAX_PRICE = 79.0  # skip business sales / luxury junk
MIN_TREND_CHANGE = 0.0  # Trends is a bonus, not a hard gate
TREND_REQUIRED_WHEN_LIMITED = 0.0

MEGA_SOLD_THRESHOLD = 100_000
# eBay often caps public badges around 10,000+; treat higher as suspicious
MAX_TRUSTED_EBAY_SOLD_BADGE = 20_000

# Real product searches (NOT "100k sold" keyword spam)
EBAY_SEARCHES = {
    "Car Accessories": [
        "car phone holder",
        "car organisers",
        "car LED lights",
    ],
    "Pet Supplies": [
        "dog toys chew",
        "cat litter mat",
        "pet grooming brush",
    ],
    "Home": [
        "led strip lights",
        "kitchen organiser",
        "storage organiser",
    ],
}

# Amazon UK Best Seller category pages
AMAZON_BESTSELLERS = {
    "Car Accessories": "https://www.amazon.co.uk/gp/bestsellers/automotive/",
    "Pet Supplies": "https://www.amazon.co.uk/gp/bestsellers/pet-supplies/",
    "Home": "https://www.amazon.co.uk/gp/bestsellers/kitchen/",
}

# Title junk that is almost never good dropshipping inventory
JUNK_TITLE_RE = re.compile(
    r"("
    r"business\s+for\s+sale|for\s+sale\s+business|with\s+proof|"
    r"excellent\s+opportunity|wholesale\s+lot|job\s+lot|"
    r"pdf\b|ebook\b|download\b|course\b|coaching\b|"
    r"100\s*k\+?\s*sold|100,?000\+?\s*sold|100000\+?\s*sold|"
    r"over\s+£?\s*100\s*k\s*sold"
    r")",
    re.I,
)

CSV_PATH = "trend_winners.csv"
SLEEP_BETWEEN_PAGES = 3
SLEEP_BETWEEN_TRENDS = 8
MAX_ITEMS_PER_SEARCH = 24
MAX_AMAZON_ITEMS = 20

_TRENDS_RATE_LIMITED = False
_TRENDS_CACHE = {}
_RUN_LOCK = threading.Lock()
BOT_STATUS = {
    "running": False,
    "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "last_run": None,
    "last_trigger": None,
    "last_winners": None,
    "last_error": None,
    "last_trends_limited": False,
}


# =============================================================================
# Browser
# =============================================================================
def make_driver():
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
    options.add_argument("--lang=en-GB")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def accept_cookies(driver, selectors=None):
    selectors = selectors or (
        "#gdpr-banner-accept",
        "button#consent-banner-btn-accept",
        "#sp-cc-accept",
        "input#sp-cc-accept",
    )
    for sel in selectors:
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, sel)
            if buttons:
                buttons[0].click()
                time.sleep(1)
                return
        except Exception:
            continue


def warm_up_ebay(driver):
    print("Warming up eBay UK...")
    driver.get("https://www.ebay.co.uk/")
    time.sleep(SLEEP_BETWEEN_PAGES)
    accept_cookies(driver)


# =============================================================================
# Parsers / filters
# =============================================================================
def parse_price(text):
    if not text:
        return None
    match = re.search(r"[£$]?([\d,]+(?:\.\d+)?)", text.replace("\xa0", " "))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_sold(text):
    """Parse sold badges like '713+ sold', '1.2K sold', '10,000+ sold'."""
    if not text:
        return 0
    text = text.strip().lower()
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

    return 0


def clean_product_name(title):
    if not title:
        return ""
    title = re.sub(r"Opens in a new window or tab", "", title, flags=re.I)
    words = re.sub(r"[^\w\s]", " ", title).split()
    skip = {"for", "with", "and", "the", "a", "an", "of", "to", "in", "on", "or"}
    keep = [w for w in words if w.lower() not in skip][:5]
    return " ".join(keep) if keep else " ".join(words[:5])


def is_junk_title(title):
    """Reject business sales and fake '100k sold' title spam."""
    if not title:
        return True
    if JUNK_TITLE_RE.search(title):
        return True
    # Titles that are mainly marketing claims
    if re.search(r"\b(opportunity|franchise|turnkey)\b", title, re.I):
        return True
    return False


def extract_ebay_sold_badge(card):
    """
    ONLY read sold counts from badge/attribute rows — never from the title.
    This stops '100K Sold' title spam from becoming Sold=100000.
    """
    for sel in (
        ".s-card__attribute-row",
        ".s-item__hotness",
        ".s-item__quantitySold",
        ".s-item__caption",
        ".su-card-container__attributes",
    ):
        for row in card.select(sel):
            text = row.get_text(" ", strip=True)
            if re.search(r"\d.*sold", text, re.I) and len(text) < 40:
                # Ignore rows that look like title fragments
                if "opportunity" in text.lower() or "business" in text.lower():
                    continue
                return text
    return ""


def estimate_ali_price(ebay_price):
    """
    Estimate AliExpress cost as 25% of eBay price.

    TODO: Replace with real Aliexpress scraping:
      scrape_aliexpress_price(product_title) -> float
    """
    return round(ebay_price * ALI_PRICE_RATIO, 2)


def calc_profit_and_margin(ebay_price, ali_price):
    ebay_fee = ebay_price * EBAY_FEE_RATE
    profit = ebay_price - ali_price - ebay_fee - SHIPPING_BUFFER
    margin = (profit / ebay_price) if ebay_price else 0.0
    return round(profit, 2), round(margin, 4)


def calc_sold_percent(sold, max_sold_in_batch):
    if not max_sold_in_batch or max_sold_in_batch <= 0:
        return 0.0
    return round(min(100.0, (float(sold) / float(max_sold_in_batch)) * 100.0), 1)


def calc_confidence_percent(
    sold,
    profit,
    margin,
    trend_change,
    source="ebay",
    amazon_rank=None,
    trends_limited=False,
):
    """Ranking confidence 0-100 (not a profit guarantee)."""
    sold_cap = 10_000  # realistic eBay public badge scale
    sold_score = min(100.0, (math.log10(max(sold, 1)) / math.log10(sold_cap)) * 100.0)

    profit_score = min(100.0, max(0.0, (profit / 15.0) * 100.0))
    margin_pct = margin * 100.0 if margin <= 1.5 else float(margin)
    margin_score = min(100.0, max(0.0, ((margin_pct - 25.0) / 35.0) * 100.0))

    if trends_limited and trend_change <= 0:
        trend_score = 40.0
    else:
        trend_score = min(100.0, max(0.0, (float(trend_change) / 40.0) * 100.0))

    # Amazon bestseller rank bonus (rank 1 = strong)
    amazon_score = 50.0
    if amazon_rank is not None and not (isinstance(amazon_rank, float) and math.isnan(amazon_rank)):
        try:
            rank_i = int(amazon_rank)
            amazon_score = max(20.0, 100.0 - (rank_i - 1) * 3.5)
        except (TypeError, ValueError):
            amazon_score = 50.0

    if source == "amazon":
        confidence = (
            0.35 * amazon_score
            + 0.20 * profit_score
            + 0.20 * margin_score
            + 0.25 * trend_score
        )
    else:
        confidence = (
            0.30 * sold_score
            + 0.25 * profit_score
            + 0.20 * margin_score
            + 0.15 * trend_score
            + 0.10 * amazon_score
        )
    return round(min(100.0, confidence), 1)


# =============================================================================
# Google Trends
# =============================================================================
def _patch_pytrends_urllib3():
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
    global _TRENDS_RATE_LIMITED

    if not keyword:
        return 0.0
    if keyword in _TRENDS_CACHE:
        return _TRENDS_CACHE[keyword]
    if _TRENDS_RATE_LIMITED:
        print(f"  Trends skipped (rate-limited earlier): {keyword}")
        return 0.0

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
    }

    for attempt in range(2):
        try:
            pytrends = TrendReq(
                hl="en-GB",
                tz=0,
                retries=0,
                backoff_factor=0.1,
                requests_args={"headers": headers},
            )
            pytrends.build_payload([keyword], timeframe="today 3-m", geo="GB")
            df = pytrends.interest_over_time()
            time.sleep(SLEEP_BETWEEN_TRENDS)

            if df is None or df.empty or keyword not in df.columns:
                _TRENDS_CACHE[keyword] = 0.0
                return 0.0

            series = df[keyword].astype(float)
            mid = len(series) // 2
            if mid == 0:
                _TRENDS_CACHE[keyword] = 0.0
                return 0.0

            first_avg = float(series.iloc[:mid].mean())
            second_avg = float(series.iloc[mid:].mean())
            if first_avg <= 0:
                change = 100.0 if second_avg > 0 else 0.0
            else:
                change = round(((second_avg - first_avg) / first_avg) * 100.0, 2)

            _TRENDS_CACHE[keyword] = change
            return change
        except Exception as e:
            err = str(e).lower()
            print(f"  Trends error for '{keyword}' (try {attempt + 1}/2): {e}")
            if "429" in err or "too many" in err or "sorry" in err:
                _TRENDS_RATE_LIMITED = True
                print("  Google Trends rate-limited. Continuing without hard trend gate.")
                _TRENDS_CACHE[keyword] = 0.0
                return 0.0
            if attempt == 0:
                time.sleep(10)

    _TRENDS_CACHE[keyword] = 0.0
    return 0.0


# =============================================================================
# eBay scrape
# =============================================================================
def search_ebay(driver, query):
    print(f"  eBay search: {query}")
    try:
        driver.get("https://www.ebay.co.uk/")
        time.sleep(2)
        accept_cookies(driver)
        box = driver.find_element(By.CSS_SELECTOR, "#gh-ac")
        box.clear()
        box.send_keys(query)
        box.send_keys(Keys.ENTER)
        time.sleep(SLEEP_BETWEEN_PAGES)
        soup = BeautifulSoup(driver.page_source, "lxml")
        cards = soup.select("li.s-card") or soup.select(".s-card") or soup.select("li.s-item")
        print(f"    cards: {len(cards)}")
        return cards[:MAX_ITEMS_PER_SEARCH]
    except Exception as e:
        print(f"    eBay search error: {e}")
        return []


def parse_ebay_card(card, category_name):
    title_el = card.select_one(".s-card__title, .s-item__title, [role='heading']")
    price_el = card.select_one(".s-card__price, .s-item__price")
    link_el = card.select_one("a[href*='/itm/'], a.s-card__link, a.s-item__link")

    title = title_el.get_text(" ", strip=True) if title_el else ""
    title = re.sub(r"Opens in a new window or tab", "", title, flags=re.I).strip()
    if not title or title.lower() == "shop on ebay":
        return None
    if is_junk_title(title):
        return None

    price = parse_price(price_el.get_text(" ", strip=True) if price_el else "")
    sold_text = extract_ebay_sold_badge(card)
    sold = parse_sold(sold_text)

    # Guard: absurd sold badges are usually spam/misreads
    if sold > MAX_TRUSTED_EBAY_SOLD_BADGE:
        print(f"    skip suspicious sold badge ({sold}): {title[:60]}")
        return None

    link = ""
    if link_el and link_el.has_attr("href"):
        link = link_el["href"].split("?")[0]

    if sold < MIN_SOLD or price is None or not link:
        return None
    if price < MIN_PRICE or price > MAX_PRICE:
        return None

    return {
        "Source": "eBay UK",
        "Category": category_name,
        "Title": title,
        "Price": price,
        "Sold": sold,
        "Amazon_Rank": None,
        "Link": link,
        "Mega_Seller": sold >= MEGA_SOLD_THRESHOLD,
    }


def scrape_ebay(driver):
    items = []
    for category, queries in EBAY_SEARCHES.items():
        print(f"\n[eBay / {category}]")
        for query in queries:
            for card in search_ebay(driver, query):
                try:
                    item = parse_ebay_card(card, category)
                    if item:
                        items.append(item)
                except Exception as e:
                    print(f"    skip card: {e}")
            time.sleep(SLEEP_BETWEEN_PAGES)
    return items


# =============================================================================
# Amazon UK Best Sellers
# =============================================================================
def scrape_amazon_bestsellers(driver):
    items = []
    print("\nWarming up Amazon UK...")
    try:
        driver.get("https://www.amazon.co.uk/")
        time.sleep(3)
        accept_cookies(driver)
    except Exception as e:
        print(f"Amazon warm-up error: {e}")

    for category, url in AMAZON_BESTSELLERS.items():
        print(f"\n[Amazon / {category}] {url}")
        try:
            driver.get(url)
            time.sleep(SLEEP_BETWEEN_PAGES + 1)
            accept_cookies(driver)
            soup = BeautifulSoup(driver.page_source, "lxml")

            cards = (
                soup.select("div#gridItemRoot")
                or soup.select("div.zg-grid-general-faceout")
                or soup.select("div[id^='p13n-asin']")
                or soup.select("li.zg-item-immersion")
            )
            print(f"  cards: {len(cards)}")

            for idx, card in enumerate(cards[:MAX_AMAZON_ITEMS], start=1):
                try:
                    title_el = (
                        card.select_one("div._cDEzb_p13n-sc-css-line-clamp-3_g3dy1")
                        or card.select_one(".p13n-sc-truncate")
                        or card.select_one("a.a-link-normal span div")
                        or card.select_one("img.a-dynamic-image")
                    )
                    if title_el and title_el.name == "img":
                        title = (title_el.get("alt") or "").strip()
                    else:
                        title = title_el.get_text(" ", strip=True) if title_el else ""

                    if not title:
                        # fallback: any product link text / img alt
                        img = card.select_one("img")
                        title = (img.get("alt") if img else "") or ""
                    title = title.strip()
                    if not title or is_junk_title(title):
                        continue

                    price_el = (
                        card.select_one("span._cDEzb_p13n-sc-price_3mJ9Z")
                        or card.select_one(".p13n-sc-price")
                        or card.select_one(".a-price .a-offscreen")
                        or card.select_one(".a-color-price")
                    )
                    price = parse_price(price_el.get_text(" ", strip=True) if price_el else "")

                    link_el = card.select_one("a.a-link-normal[href*='/dp/'], a[href*='/dp/']")
                    link = ""
                    if link_el and link_el.has_attr("href"):
                        href = link_el["href"]
                        if href.startswith("/"):
                            href = "https://www.amazon.co.uk" + href.split("?")[0]
                        else:
                            href = href.split("?")[0]
                        link = href

                    # Reviews count as demand proxy when sold count isn't public
                    review_el = card.select_one("span.a-size-small") or card.select_one(
                        "a.a-link-normal .a-size-small"
                    )
                    review_text = review_el.get_text(" ", strip=True) if review_el else ""
                    review_match = re.search(r"([\d,]+)", review_text)
                    reviews = int(review_match.group(1).replace(",", "")) if review_match else 0

                    if not link or price is None:
                        continue
                    if price < MIN_PRICE or price > MAX_PRICE:
                        continue

                    # Map reviews -> synthetic "sold proxy" for scoring only
                    sold_proxy = max(reviews, 100)

                    items.append(
                        {
                            "Source": "Amazon UK",
                            "Category": category,
                            "Title": title,
                            "Price": price,
                            "Sold": sold_proxy,  # reviews used as demand proxy
                            "Amazon_Rank": idx,
                            "Link": link,
                            "Mega_Seller": False,
                            "Reviews": reviews,
                        }
                    )
                except Exception as e:
                    print(f"  skip amazon card: {e}")
            time.sleep(SLEEP_BETWEEN_PAGES)
        except Exception as e:
            print(f"  Amazon category error: {e}")

    print(f"Amazon items kept: {len(items)}")
    return items


# =============================================================================
# Telegram
# =============================================================================
def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("\n[Telegram] Skipping send — set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in .env")
        print(message)
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        # Telegram hard limit ~4096 chars
        text = message[:4000]
        resp = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": False},
            timeout=30,
        )
        if resp.ok:
            print("[Telegram] Message sent.")
            return True
        print(f"[Telegram] Failed: {resp.status_code} {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"[Telegram] Failed: {e}")
        return False


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    return int(_safe_float(value, default))


def format_top_results_message(df_top):
    lines = ["Dropship Sources (eBay + Amazon UK)\n"]
    for i, row in enumerate(df_top.itertuples(index=False), start=1):
        title = str(row.Title)[:80]
        source = getattr(row, "Source", "eBay UK")
        sold_pct = _safe_float(getattr(row, "Sold_Percent", 0))
        conf = _safe_float(getattr(row, "Confidence", 0))
        rank = getattr(row, "Amazon_Rank", None)
        rank_val = _safe_float(rank, default=float("nan"))
        rank_bit = "" if math.isnan(rank_val) or rank_val <= 0 else f" | AMZ#{int(rank_val)}"
        sold_label = "Reviews~" if str(source).startswith("Amazon") else "Sold"
        profit = _safe_float(getattr(row, "Profit", 0))
        trend = _safe_float(getattr(row, "Trend_Change", 0))
        sold = _safe_int(getattr(row, "Sold", 0))
        lines.append(
            f"{i}. [{source}] {title}\n"
            f"   Profit: £{profit:.2f} | Trend: {trend}%{rank_bit}\n"
            f"   {sold_label}: {sold} ({sold_pct}%) | Confidence: {conf}%\n"
            f"   {row.Link}\n"
        )
    return "\n".join(lines)


def _authorized(update: Update) -> bool:
    if not TELEGRAM_CHAT_ID or update.effective_chat is None:
        return False
    return str(update.effective_chat.id) == str(TELEGRAM_CHAT_ID)


def build_status_text() -> str:
    running = "YES — scan in progress" if BOT_STATUS["running"] else "No — idle"
    return (
        "Dropship Source Bot status\n"
        f"Running now: {running}\n"
        f"Bot started: {BOT_STATUS['started_at']}\n"
        f"Last run: {BOT_STATUS['last_run'] or 'never'}\n"
        f"Last trigger: {BOT_STATUS['last_trigger'] or '-'}\n"
        f"Last winners: {BOT_STATUS['last_winners'] if BOT_STATUS['last_winners'] is not None else '-'}\n"
        f"Trends limited last run: {BOT_STATUS['last_trends_limited']}\n"
        f"Last error: {BOT_STATUS['last_error'] or 'none'}\n"
        "Sources: eBay UK + Amazon UK Best Sellers\n"
        "Schedule: Mon/Wed/Fri 09:00\n"
        "Commands: /status /run"
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    await update.message.reply_text(
        "Dropship Source Bot online.\n"
        "/status — status\n"
        "/run — scan eBay + Amazon now"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        await update.message.reply_text("Unauthorized chat.")
        return
    await update.message.reply_text(build_status_text())


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        await update.message.reply_text("Unauthorized chat.")
        return
    if BOT_STATUS["running"] or _RUN_LOCK.locked():
        await update.message.reply_text("A scan is already running. Try /status.")
        return
    await update.message.reply_text("Starting eBay + Amazon scan...")
    threading.Thread(target=job, kwargs={"trigger": "/run"}, daemon=True).start()


# =============================================================================
# Pipeline
# =============================================================================
def find_winners():
    global _TRENDS_RATE_LIMITED, _TRENDS_CACHE
    _TRENDS_RATE_LIMITED = False
    _TRENDS_CACHE = {}

    print("=" * 60)
    print(f"Dropship Source Bot started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    all_items = []
    driver = None
    try:
        driver = make_driver()
        warm_up_ebay(driver)
        all_items.extend(scrape_ebay(driver))
        all_items.extend(scrape_amazon_bestsellers(driver))
    except Exception as e:
        print(f"Driver/scrape error: {e}")
        BOT_STATUS["last_error"] = str(e)
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    empty_cols = [
        "Source",
        "Category",
        "Title",
        "Price",
        "Sold",
        "Sold_Percent",
        "Amazon_Rank",
        "Link",
        "Mega_Seller",
        "Ali_Price",
        "Profit",
        "Margin",
        "Trend_Change",
        "Confidence",
        "Trend_Keyword",
    ]

    if not all_items:
        pd.DataFrame(columns=empty_cols).to_csv(CSV_PATH, index=False)
        send_telegram_message("Dropship bot: no products scraped this run.")
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

    max_sold = max((i["Sold"] for i in all_items), default=0)
    print(f"\nUnique sourced products: {len(all_items)} (max demand proxy: {max_sold})")

    winners = []
    for item in all_items:
        try:
            if is_junk_title(item["Title"]):
                continue
            if item["Price"] < MIN_PRICE or item["Price"] > MAX_PRICE:
                continue

            ali_price = estimate_ali_price(item["Price"])
            profit, margin = calc_profit_and_margin(item["Price"], ali_price)

            if item["Sold"] < MIN_SOLD or profit < MIN_PROFIT or margin < MIN_MARGIN:
                print(
                    f"skip: {item['Source']} | {item['Title'][:45]} | "
                    f"sold/proxy={item['Sold']} profit=£{profit} margin={margin*100:.1f}%"
                )
                continue

            keyword = clean_product_name(item["Title"])
            print(f"Trends: {keyword} | {item['Source']} | £{item['Price']}")
            trend_change = get_trend_change(keyword)

            required_trend = (
                TREND_REQUIRED_WHEN_LIMITED if _TRENDS_RATE_LIMITED else MIN_TREND_CHANGE
            )
            if trend_change < required_trend:
                print(f"  skip trend {trend_change}% < {required_trend}%")
                continue

            sold_pct = calc_sold_percent(item["Sold"], max_sold)
            confidence = calc_confidence_percent(
                item["Sold"],
                profit,
                margin,
                trend_change,
                source="amazon" if item["Source"].startswith("Amazon") else "ebay",
                amazon_rank=item.get("Amazon_Rank"),
                trends_limited=_TRENDS_RATE_LIMITED,
            )

            winners.append(
                {
                    **item,
                    "Sold_Percent": sold_pct,
                    "Ali_Price": ali_price,
                    "Profit": profit,
                    "Margin": round(margin * 100, 2),
                    "Trend_Change": trend_change,
                    "Confidence": confidence,
                    "Trend_Keyword": keyword,
                }
            )
            print(
                f"  WINNER [{item['Source']}] conf={confidence}% "
                f"profit=£{profit} sold%={sold_pct}"
            )
        except Exception as e:
            print(f"  item error: {e}")

    df = pd.DataFrame(winners)
    if not df.empty:
        df = df.sort_values(
            by=["Confidence", "Profit", "Sold"],
            ascending=[False, False, False],
        )
    else:
        df = pd.DataFrame(columns=empty_cols)

    df.to_csv(CSV_PATH, index=False)
    print(f"\nSaved {len(df)} winners to {CSV_PATH}")

    if not df.empty:
        send_telegram_message(format_top_results_message(df.head(5)))
    else:
        send_telegram_message(
            "Dropship bot: no clean winners this run "
            "(junk filtered / money filters / scrape blocked)."
        )

    BOT_STATUS["last_trends_limited"] = _TRENDS_RATE_LIMITED
    print(f"Bot Finished. Found {len(df)} winners")
    return len(df)


def job(trigger="schedule"):
    if not _RUN_LOCK.acquire(blocking=False):
        print("Scan already running — skip.")
        send_telegram_message("Scan already running. Try /status.")
        return

    BOT_STATUS["running"] = True
    BOT_STATUS["last_trigger"] = trigger
    BOT_STATUS["last_error"] = None
    try:
        winners = find_winners()
        BOT_STATUS["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        BOT_STATUS["last_winners"] = winners
    except Exception as e:
        print(f"Job failed: {e}")
        BOT_STATUS["last_error"] = str(e)
        BOT_STATUS["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        send_telegram_message(f"Dropship bot error: {e}")
    finally:
        BOT_STATUS["running"] = False
        _RUN_LOCK.release()


def _schedule_loop():
    schedule.every().monday.at("09:00").do(job, trigger="schedule")
    schedule.every().wednesday.at("09:00").do(job, trigger="schedule")
    schedule.every().friday.at("09:00").do(job, trigger="schedule")
    print("Schedule armed: Monday, Wednesday, Friday at 09:00")
    while True:
        schedule.run_pending()
        time.sleep(20)


def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in .env before starting.")
        sys.exit(1)

    BOT_STATUS["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    threading.Thread(target=_schedule_loop, daemon=True).start()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("run", cmd_run))

    send_telegram_message(
        "Dropship Source Bot online (eBay + Amazon UK).\n"
        "Commands: /status /run\n"
        "Schedule: Mon/Wed/Fri 09:00"
    )
    print("Telegram bot polling... commands: /status /run")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        job(trigger="once")
    else:
        main()
