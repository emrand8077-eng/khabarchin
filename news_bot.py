import os, re, html, hashlib, feedparser, requests

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL_ID")

FEEDS = [
    "https://www.entekhab.ir/fa/rss/allnews",
    "https://www.mehrnews.com/rss",
    "https://feeds.bbci.co.uk/persian/rss.xml",
    "https://www.radiofarda.com/rssfeeds",
    "https://www.aljazeera.com/xml/rss/all.xml",
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
    sents = [s.strip() for s in re.split(r"[.!?؟]+", text) if len(s.strip()) > 15]
    sents.sort(key=lambda s: -sum(1 for w in KEYWORDS if w in s))
    return " ".join(sents[:n])[:300]

def pick_image(entry):
    url = None
    for key in ("media_content", "media_thumbnail", "links"):
        for m in entry.get(key, []) or []:
            url = m.get("url") or m.get("href")
            if url:
                break
        if url:
            break
    if not url:
        m = re.search(r'<img[^>]+src="([^"]+)"', entry.get("summary", ""))
        url = m.group(1) if m else None
    if not url:
        return None
    return hires(url)

def hires(url):
    """جایگزینی تصویر بندانگشتی با نسخهٔ باکیفیت"""
    for pat in ("thumb_", "_thumb", "/t_", "/tn_", "thumbs/"):
        if pat in url:
            return url.replace(pat, "")
    return url

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
        cap = f"{p['title']}\n\n{p['summ']}"
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

if __name__ == "__main__":
    main()
    
