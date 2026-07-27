#!/usr/bin/env python3
"""
trend_winner_bot.py
Find dropshipping product winners on eBay UK using Best Selling-style
search results, Google Trends, and simple profit filters.
Sends top results to Telegram. Runs Mon/Wed/Fri at 09:00.
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
from urllib3.util.retry import Retry
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from webdriver_manager.chrome import ChromeDriverManager

# Load secrets from .env (same folder as this script)
load_dotenv()

# =============================================================================
# CONFIG — set these in a .env file (do not hardcode secrets here)
# =============================================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

EBAY_FEE_RATE = 0.13
SHIPPING_BUFFER = 2.0  # flat £2 buffer
ALI_PRICE_RATIO = 0.25  # estimate AliExpress cost as 25% of eBay price

# Filters (loosened slightly so more realistic winners appear)
MIN_SOLD = 100
MIN_PROFIT = 5.0
MIN_MARGIN = 0.40  # 40%
MIN_TREND_CHANGE = 10.0  # %
# If Google Trends is rate-limited, do not block winners on trend %
TREND_REQUIRED_WHEN_LIMITED = 0.0

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
SLEEP_BETWEEN_TRENDS = 8  # Google Trends rate-limits aggressively
MAX_ITEMS_PER_SEARCH = 20

# If Google Trends returns 429, skip further trend calls for this run
_TRENDS_RATE_LIMITED = False
_TRENDS_CACHE = {}

# Shared runtime status for /status and /run
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

    If Google rate-limits (429), we stop calling Trends for the rest of
    this run so the bot can finish instead of hanging on retries.
    """
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
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }

    for attempt in range(2):
        try:
            pytrends = TrendReq(
                hl="en-GB",
                tz=0,
                retries=0,  # don't let urllib3 hammer Google
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
            is_rate_limit = "429" in err or "too many" in err or "sorry" in err
            print(f"  Trends error for '{keyword}' (try {attempt + 1}/2): {e}")

            if is_rate_limit:
                _TRENDS_RATE_LIMITED = True
                print(
                    "  Google Trends rate-limited this IP. "
                    "Skipping remaining Trends calls for this run "
                    "(sold/profit filters still apply)."
                )
                _TRENDS_CACHE[keyword] = 0.0
                return 0.0

            if attempt == 0:
                print("  Waiting 10s before one retry...")
                time.sleep(10)

    _TRENDS_CACHE[keyword] = 0.0
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


def calc_sold_percent(sold, max_sold_in_batch):
    """
    Sold % = this item's sold count vs the highest sold count in this scrape.
    100% = strongest seller in the current run.
    """
    if not max_sold_in_batch or max_sold_in_batch <= 0:
        return 0.0
    return round(min(100.0, (float(sold) / float(max_sold_in_batch)) * 100.0), 1)


def calc_confidence_percent(sold, profit, margin, trend_change, trends_limited=False):
    """
    Confidence % (0-100) from sold strength, profit, margin, and trend.
    This is a ranking score, not a guarantee of profit.
    """
    # Sold strength on a log scale (100 sold ~ low, 100k sold ~ 100)
    sold_score = min(100.0, (math.log10(max(sold, 1)) / math.log10(MEGA_SOLD_THRESHOLD)) * 100.0)

    # Profit: £5 ~ 33, £15+ ~ 100
    profit_score = min(100.0, max(0.0, (profit / 15.0) * 100.0))

    # Margin stored as fraction here
    margin_pct = margin * 100.0 if margin <= 1.5 else float(margin)
    margin_score = min(100.0, max(0.0, ((margin_pct - 30.0) / 30.0) * 100.0))

    # Trend: if Trends was blocked, use a neutral mid score instead of punishing
    if trends_limited and trend_change <= 0:
        trend_score = 45.0
    else:
        trend_score = min(100.0, max(0.0, (float(trend_change) / 50.0) * 100.0))

    confidence = (
        0.30 * sold_score
        + 0.25 * profit_score
        + 0.20 * margin_score
        + 0.25 * trend_score
    )
    return round(confidence, 1)


# =============================================================================
# Telegram helpers + commands
# =============================================================================
def send_telegram_message(message):
    """
    Send a Telegram message via HTTP API (safe from any thread).
    Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in your .env file.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("\n[Telegram] Skipping send — set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in .env")
        print("--- Message that would be sent ---")
        print(message)
        print("----------------------------------")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "disable_web_page_preview": False,
            },
            timeout=30,
        )
        if resp.ok:
            print("[Telegram] Message sent.")
            return True
        print(f"[Telegram] Failed to send: {resp.status_code} {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"[Telegram] Failed to send: {e}")
        return False


def format_top_results_message(df_top):
    """Build a simple Telegram message for the top 3 winners."""
    lines = ["eBay UK Trend Winners\n"]
    for i, row in enumerate(df_top.itertuples(index=False), start=1):
        mega = " | 100k+ sold" if getattr(row, "Mega_Seller", False) else ""
        title = str(row.Title)[:80]
        sold_pct = getattr(row, "Sold_Percent", 0)
        conf = getattr(row, "Confidence", 0)
        lines.append(
            f"{i}. {title}\n"
            f"   Profit: £{row.Profit:.2f} | Trend: {row.Trend_Change}%{mega}\n"
            f"   Sold: {row.Sold} ({sold_pct}%) | Confidence: {conf}%\n"
            f"   {row.Link}\n"
        )
    return "\n".join(lines)


def _authorized(update: Update) -> bool:
    """Only allow commands from your TELEGRAM_CHAT_ID."""
    if not TELEGRAM_CHAT_ID:
        return False
    chat = update.effective_chat
    if chat is None:
        return False
    return str(chat.id) == str(TELEGRAM_CHAT_ID)


def build_status_text() -> str:
    """Human-readable status for /status."""
    running = "YES — scan in progress" if BOT_STATUS["running"] else "No — idle"
    return (
        "Trend Winner Bot status\n"
        f"Running now: {running}\n"
        f"Bot started: {BOT_STATUS['started_at']}\n"
        f"Last run: {BOT_STATUS['last_run'] or 'never'}\n"
        f"Last trigger: {BOT_STATUS['last_trigger'] or '-'}\n"
        f"Last winners: {BOT_STATUS['last_winners'] if BOT_STATUS['last_winners'] is not None else '-'}\n"
        f"Trends limited last run: {BOT_STATUS['last_trends_limited']}\n"
        f"Last error: {BOT_STATUS['last_error'] or 'none'}\n"
        "Schedule: Mon/Wed/Fri 09:00\n"
        "Commands: /status /run"
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    await update.message.reply_text(
        "Trend Winner Bot is online.\n"
        "Commands:\n"
        "/status — bot status\n"
        "/run — start a scan now"
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

    await update.message.reply_text("Starting scan now... I'll message you when it finishes.")
    threading.Thread(target=job, kwargs={"trigger": "/run"}, daemon=True).start()


# =============================================================================
# Main pipeline
# =============================================================================
def find_winners():
    """Scrape → trends → profit filter → CSV → Telegram."""
    global _TRENDS_RATE_LIMITED, _TRENDS_CACHE
    _TRENDS_RATE_LIMITED = False
    _TRENDS_CACHE = {}

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
        "Sold_Percent",
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
        print("No items scraped. Saving empty CSV and finishing.")
        pd.DataFrame(columns=empty_cols).to_csv(CSV_PATH, index=False)
        BOT_STATUS["last_trends_limited"] = _TRENDS_RATE_LIMITED
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
    max_sold = max((i["Sold"] for i in all_items), default=0)
    print(
        f"\nUnique items with 100+ sold: {len(all_items)} "
        f"(100k+ sold: {mega_count}, max sold in batch: {max_sold})"
    )

    # Soften trend gate when Google Trends is blocked mid-run
    required_trend = (
        TREND_REQUIRED_WHEN_LIMITED if _TRENDS_RATE_LIMITED else MIN_TREND_CHANGE
    )

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

            # Re-check required trend if rate-limit flipped during this loop
            required_trend = (
                TREND_REQUIRED_WHEN_LIMITED if _TRENDS_RATE_LIMITED else MIN_TREND_CHANGE
            )

            # Keep if: Sold/Profit/Margin pass AND Trend meets current threshold
            if trend_change >= required_trend:
                sold_pct = calc_sold_percent(item["Sold"], max_sold)
                confidence = calc_confidence_percent(
                    item["Sold"],
                    profit,
                    margin,
                    trend_change,
                    trends_limited=_TRENDS_RATE_LIMITED,
                )
                winners.append(
                    {
                        **item,
                        "Sold_Percent": sold_pct,
                        "Ali_Price": ali_price,
                        "Profit": profit,
                        "Margin": round(margin * 100, 2),  # store as %
                        "Trend_Change": trend_change,
                        "Confidence": confidence,
                        "Trend_Keyword": keyword,
                    }
                )
                print(
                    f"  WINNER: profit=£{profit} margin={margin * 100:.1f}% "
                    f"trend={trend_change}% sold%={sold_pct} conf={confidence}% "
                    f"mega={item['Mega_Seller']}"
                )
            else:
                print(
                    f"  skip trend: {trend_change}% < {required_trend}% "
                    f"(limited={_TRENDS_RATE_LIMITED})"
                )
        except Exception as e:
            print(f"  Item error: {e}")
            continue

    df = pd.DataFrame(winners)
    if not df.empty:
        df = df.sort_values(
            by=["Confidence", "Mega_Seller", "Profit", "Trend_Change", "Sold"],
            ascending=[False, False, False, False, False],
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

    BOT_STATUS["last_trends_limited"] = _TRENDS_RATE_LIMITED
    print(f"Bot Finished. Found {len(df)} winners")
    return len(df)


def job(trigger="schedule"):
    """Scheduled / Telegram / CLI job wrapper with overlap protection."""
    if not _RUN_LOCK.acquire(blocking=False):
        print("Scan already running — skipping overlapping start.")
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
        try:
            send_telegram_message(f"Trend Winner Bot error: {e}")
        except Exception:
            pass
    finally:
        BOT_STATUS["running"] = False
        _RUN_LOCK.release()


def _schedule_loop():
    """Background thread: Mon/Wed/Fri 09:00."""
    schedule.every().monday.at("09:00").do(job, trigger="schedule")
    schedule.every().wednesday.at("09:00").do(job, trigger="schedule")
    schedule.every().friday.at("09:00").do(job, trigger="schedule")
    print("Schedule armed: Monday, Wednesday, Friday at 09:00")
    while True:
        schedule.run_pending()
        time.sleep(20)


def main():
    """Run Telegram command bot + schedule loop."""
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
        "Trend Winner Bot is online.\n"
        "Commands: /status /run\n"
        "Schedule: Mon/Wed/Fri 09:00"
    )
    print("Telegram bot polling... commands: /status /run")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    # `python trend_winner_bot.py once` → single run, no Telegram polling
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        job(trigger="once")
    else:
        main()
