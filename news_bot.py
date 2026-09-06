import os
import re
import html
import hashlib
import feedparser
import requests
from difflib import SequenceMatcher

# =========================
# تنظیمات
# =========================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

if not BOT_TOKEN or not CHANNEL_ID:
    raise RuntimeError("BOT_TOKEN یا CHANNEL_ID در GitHub Secrets پیدا نشد.")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

POSTED_FILE = "posted.txt"
MAX_POSTED = 1000

# فقط خبرهایی که واقعاً به موضوعات مهم ایران مربوط باشند
KEYWORDS = [
    "ایران", "تهران", "دولت", "مجلس", "رئیس جمهور", "رئیس‌جمهور",
    "خامنه‌ای", "رهبر", "سپاه", "ارتش", "نیروی انتظامی",
    "تحریم", "برجام", "مذاکره", "آمریکا", "اسرائیل",
    "اقتصاد", "تورم", "دلار", "ارز", "بانک مرکزی",
    "نفت", "گاز", "بنزین", "بودجه", "بورس",
    "انتخابات", "وزیر", "وزارت", "قوه قضائیه",
    "اعتراض", "اعتصاب", "زلزله", "سیل", "حادثه",
    "انفجار", "آتش‌سوزی", "قطعی برق", "خاموشی"
]

IMPORTANT_WORDS = [
    "تحریم", "جنگ", "حمله", "موشک", "هسته‌ای", "هسته ای",
    "مذاکره", "برجام", "دلار", "تورم", "نفت", "بنزین",
    "انتخابات", "رئیس جمهور", "خامنه‌ای", "سپاه", "مجلس",
    "اعتراض", "زلزله", "سیل", "انفجار"
]

# منابع فعلی پروژه
FEEDS = [
    ("Entekhab", "https://news.google.com/rss/search?q=site%3Aentekhab.ir+Iran&hl=fa&gl=IR&ceid=IR%3Afa"),
    ("Tasnim", "https://news.google.com/rss/search?q=site%3Atasnimnews.com+Iran&hl=fa&gl=IR&ceid=IR%3Afa"),
    ("IRNA", "https://news.google.com/rss/search?q=site%3Airna.ir+Iran&hl=fa&gl=IR&ceid=IR%3Afa"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
]

# =========================
# ابزارها
# =========================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize(text):
    text = clean_text(text).lower()

    replacements = {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def make_id(title, link):
    value = normalize(title) + "|" + link
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()

    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except Exception:
        return set()


def save_posted(posted):
    items = list(posted)[-MAX_POSTED:]

    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        for item in items:
            f.write(item + "\n")


def is_relevant(title, summary):
    text = normalize(title + " " + summary)

    matches = 0

    for keyword in KEYWORDS:
        if normalize(keyword) in text:
            matches += 1

    return matches >= 1


def importance_score(title, summary, source):
    text = normalize(title + " " + summary)

    score = 0

    # ارتباط با ایران
    if "ایران" in text or "تهران" in text:
        score += 3

    # کلمات مهم
    for word in IMPORTANT_WORDS:
        if normalize(word) in text:
            score += 2

    # اعتبار نسبی منبع
    trusted = {
        "IRNA": 2,
        "Tasnim": 2,
        "Entekhab": 2,
        "Al Jazeera": 2,
    }

    score += trusted.get(source, 0)

    return score


def similar(a, b):
    a = normalize(a)
    b = normalize(b)

    if not a or not b:
        return False

    ratio = SequenceMatcher(None, a, b).ratio()

    return ratio >= 0.78


def make_post(title, summary):
    title = clean_text(title)
    summary = clean_text(summary)

    # کوتاه کردن تیتر
    if len(title) > 180:
        title = title[:177].rstrip() + "..."

    # کوتاه کردن خلاصه
    if len(summary) > 500:
        summary = summary[:497].rstrip() + "..."

    # اگر خلاصه خیلی شبیه تیتر بود، حذفش می‌کنیم
    if similar(title, summary):
        return f"<b>{html.escape(title)}</b>"

    return (
        f"<b>{html.escape(title)}</b>\n\n"
        f"{html.escape(summary)}"
    )


# =========================
# دریافت خبر
# =========================

def fetch_feed(source, url):
    try:
        response = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0 (NewsBot)"
            }
        )

        response.raise_for_status()

        feed = feedparser.parse(response.content)

        results = []

        for entry in feed.entries[:20]:
            title = clean_text(entry.get("title", ""))

            link = entry.get("link", "")

            summary = clean_text(
                entry.get("summary", "")
                or entry.get("description", "")
            )

            if not title or not link:
                continue

            results.append({
                "source": source,
                "title": title,
                "link": link,
                "summary": summary
            })

        return results

    except Exception as e:
        print(f"[ERROR] {source}: {e}")
        return []


# =========================
# ارسال به تلگرام
# =========================

def send_message(text):
    url = f"{TELEGRAM_API}/sendMessage"

    response = requests.post(
        url,
        json={
            "chat_id": CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        timeout=20
    )

    if not response.ok:
        print("Telegram error:", response.text)
        return False

    return True


# =========================
# اجرای اصلی
# =========================

def main():

    print("News bot started.")

    posted = load_posted()

    all_news = []

    for source, url in FEEDS:
        news = fetch_feed(source, url)

        print(f"{source}: {len(news)} news")

        all_news.extend(news)

    # حذف خبرهای تکراری داخل همین اجرا
    unique_news = []
    titles = []

    for item in all_news:

        news_id = make_id(item["title"], item["link"])

        if news_id in posted:
            continue

        duplicate = False

        for old_title in titles:
            if similar(item["title"], old_title):
                duplicate = True
                break

        if duplicate:
            continue

        titles.append(item["title"])
        unique_news.append(item)

    print(f"New unique news: {len(unique_news)}")

    # امتیازدهی
    scored = []

    for item in unique_news:

        if not is_relevant(item["title"], item["summary"]):
            continue

        score = importance_score(
            item["title"],
            item["summary"],
            item["source"]
        )

        item["score"] = score

        # فعلاً فقط خبرهای نسبتاً مهم
        if score >= ۴:
            scored.append(item)

    # مهم‌ترین‌ها اول
    scored.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # حداکثر 3 خبر در هر اجرا
    scored = scored[:3]

    print(f"Selected news: {len(scored)}")

    for item in scored:

        post = make_post(
            item["title"],
            item["summary"]
        )

        print("Publishing:", item["title"])

        success = send_message(post)

        if success:
            news_id = make_id(
                item["title"],
                item["link"]
            )

            posted.add(news_id)

            print("Published successfully.")

        else:
            print("Publish failed.")

    save_posted(posted)

    print("News bot finished.")


if __name__ == "__main__":
    main()
