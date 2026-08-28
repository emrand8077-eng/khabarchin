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

def summarize(text, n=3):
    sents = [s.strip() for s in re.split(r"[.!?؟]+", text) if len(s.strip()) > 15]
    sents.sort(key=lambda s: -sum(1 for w in KEYWORDS if w in s))
    return " ".join(sents[:n])[:300]

def get_image(entry):
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
    for pat in ("thumb_", "_thumb", "/t_", "/tn_", "thumbs/"):
        if pat in url:
            return url.replace(pat, "")
    return url

def build_post(e):
    text = e.get("title", "") + " " + e.get("summary", "")
    if not is_relevant(text):
        return None
    important = sum(1 for w in KEYWORDS if w in text) >= 2
    return {
        "title": clean(e.get("title", ""), 120),
        "summ": summarize(e.get("summary", "")) or clean(e.get("summary", ""), 200),
        "img": get_image(e),
        "important": important,
    }

def collect_posts():
    posts = []
    seen = set()
    for url in FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as ex:
            print("ERR", url, ex)
            continue
        for e in feed.entries[:10]:
            p = build_post(e)
            if not p:
                continue
            key = hashlib.md5(e.get("link", e.get("title", "")).encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            posts.append(p)

posts.sort(key=lambda p: p["important"], reverse=True)
    return posts

def send(base, cap, img):
    if img:
        data = requests.get(img, timeout=15).content
        return requests.post(base + "/sendPhoto",
                             data={"chat_id": CHANNEL, "caption": cap, "parse_mode": "HTML"},
                             files={"photo": data})
    return requests.post(base + "/sendMessage",
                         data={"chat_id": CHANNEL, "text": cap, "parse_mode": "HTML"})

def main():
    posted = set()
    if os.path.exists("posted.txt"):
        posted = set(open("posted.txt").read().split())
    base = f"https://api.telegram.org/bot{TOKEN}"
    new = 0
    for p in collect_posts():
        k = hashlib.md5(p["title"].encode()).hexdigest()
        if k in posted:
            continue
        cap = f"{p['title']}\n\n{p['summ']}"
        try:
            send(base, cap, p["img"])
            posted.add(k)
            new += 1
            print("POSTED:", p["title"][:50])
        except Exception as ex:
            print("POST_ERR", ex)
    open("posted.txt", "w").write("\n".join(posted))
    print(f"Done. {new} new posts.")

main()
