Ali:
import os, re, html, hashlib, feedparser, requests

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL_ID")

FEEDS = [
    "https://www.entekhab.ir/fa/rss/allnews",          # انتخاب
    "https://www.mehrnews.com/rss",                     # مهر
    "https://feeds.bbci.co.uk/persian/rss.xml",         # بی‌بی‌سی فارسی
    "https://www.radiofarda.com/rssfeeds",              # رادیو فردا
    "https://www.aljazeera.com/xml/rss/all.xml",        # الجزیره
    "https://news.google.com/rss/search?q=site:reuters.com+Iran&hl=fa&gl=IR&ceid=IR:fa",
    "https://news.google.com/rss/search?q=site:axios.com+Middle+East&hl=fa&gl=IR&ceid=IR:fa",
    "https://news.google.com/rss/search?q=site:farsnews.ir&hl=fa&gl=IR&ceid=IR:fa",
    "https://news.google.com/rss/search?q=site:tasnimnews.com&hl=fa&gl=IR&ceid=IR:fa",
]

KEYWORDS = ["سیاست", "اقتصاد", "جنگ", "ارتش", "تحریم", "نفت", "دلار", "طلا", "سکه",
            "انتخابات", "دولت", "مجلس", "بودجه", "تورم", "سهام", "بورس",
            "ایران", "اسرائیل", "آمریکا", "روسیه", "اوکراین", "چین",
            "غزه", "لبنان", "سوریه", "عراق", "یمن", "افغانستان", "فلسطین",
            "توافق", "هسته‌ای", "موشکی", "حمله", "بمباران", "آتش‌بس"]

def clean(text, limit=250):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")

def is_relevant(text):
    return any(w in text for w in KEYWORDS)

def important_score(text):
    return sum(1 for w in KEYWORDS if w in text)

def summarize(text, n=3):
    """خلاصه‌ساز ساده: جمله‌های دارای کلیدواژه اول میان"""
    sents = [s.strip() for s in re.split(r"[.!?؟]+", text) if len(s.strip()) > 15]
    sents.sort(key=lambda s: -sum(1 for w in KEYWORDS if w in s))
    return " ".join(sents[:n])[:300]

def pick_image(entry):
    for key in ("media_content", "media_thumbnail", "links"):
        for m in entry.get(key, []) or []:
            url = m.get("url") or m.get("href")
            if url:
                return url
    m = re.search(r'<img[^>]+src="([^"]+)"', entry.get("summary", ""))
    return m.group(1) if m else None

def main():
    posted = set()
    if os.path.exists("posted.txt"):
        posted = set(open("posted.txt").read().split())

    posts, seen = [], set()
    for url in FEEDS:
        try:
            for e in feedparser.parse(url).entries[:10]:
                text = e.get("title", "") + " " + e.get("summary", "")
                if not is_relevant(text):
                    continue
                key = hashlib.md5(e.get("link", e.get("title", "")).encode()).hexdigest()
                if key in seen:
                    continue
                seen.add(key)
                posts.append({
                    "title": clean(e.get("title", ""), 120),
                    "summ": summarize(e.get("summary", "")) or clean(e.get("summary", ""), 200),
                    "img": pick_image(e),
                    "important": important_score(text) >= 2,
                })
        except Exception as ex:
            print("ERR", url, ex)

    posts.sort(key=lambda p: p["important"], reverse=True)

    base = f"https://api.telegram.org/bot{TOKEN}"
    new = 0
    for p in posts:
        k = hashlib.md5(p["title"].encode()).hexdigest()
        if k in posted:
            continue

tag = "🔴 خبر مهم\n\n" if p["important"] else ""
        cap = f"{tag}{p['title']}\n\n{p['summ']}"
        try:
            if p["img"]:
                img = requests.get(p["img"], timeout=15).content
                requests.post(base + "/sendPhoto",
                              data={"chat_id": CHANNEL, "caption": cap, "parse_mode": "HTML"},
                              files={"photo": img})
            else:
                requests.post(base + "/sendMessage",
                              data={"chat_id": CHANNEL, "text": cap, "parse_mode": "HTML"})
            posted.add(k)
            new += 1
            print("POSTED:", p["title"][:50])
        except Exception as ex:
            print("POST_ERR", ex)

    open("posted.txt", "w").write("\n".join(posted))
    print(f"Done. {new} new posts.")

if name == "main":
    main()

📁 .github/workflows/news.yml — اینم عوض کن:

name: News Bot

on:
  schedule:
    - cron: '*/20 * * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  post-news:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install feedparser requests
      - run: python news_bot.py
        env:
          BOT_TOKEN: ${{ secrets.BOT_TOKEN }}
          CHANNEL_ID: ${{ secrets.CHANNEL_ID }}
      - name: ذخیره خبرهای ارسال‌شده
        run: |
          git config user.name "news-bot"
          git config user.email "news-bot@users.noreply.github.com"
          git add posted.txt
          git commit -m "update posted" || echo "nothing to save"
          git push
