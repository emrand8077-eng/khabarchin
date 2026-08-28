import os, re, html
import feedparser, requests
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL_ID")

FEEDS = ["https://feeds.bbci.co.uk/persian/rss.xml"]

IMPORTANT = ["دلار", "قیمت", "انتخابات", "نفت", "توافق", "بودجه",
             "تورم", "دولت", "مجلس", "سهام", "طلا", "حمله"]

def clean(text, limit=220):
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")

def score(entry):
    t = entry.get("title", "") + " " + entry.get("summary", "")
    return sum(1 for w in IMPORTANT if w in t)

def main():
    posts, seen = [], set()
    for url in FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception:
            continue
        for e in feed.entries:
            link = e.get("link", "")
            if link in seen:
                continue
            seen.add(link)
            if score(e) >= 1:
                posts.append((score(e), e))

    posts.sort(key=lambda x: -x[0])
    posts = posts[:3]

    if not posts:
        print("no important news")
        return

    now = datetime.now().strftime("%H:%M")
    msg = f"📰 <b>خلاصه اخبار مهم</b> — {now}\n\n"
    for i, (s, e) in enumerate(posts, 1):
        title = html.escape(e.get("title", ""))
        link = e.get("link", "")
        msg += f"{i}. <b>{title}</b>\n"
        msg += clean(e.get("summary", "")) + "\n"
        msg += f"🔗 {link}\n\n"

    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHANNEL, "text": msg, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=30)
    print(r.status_code)

if __name__ == "__main__":
    main()
