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
def cln(t, l=250):
    t = re.sub(r"<[^>]+>", " ", t or "")
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:l] + ("…" if len(t) > l else "")
def rel(t):
    return any(w in t for w in KEYWORDS)
def summ(t, n=3):
    s = [x.strip() for x in re.split(r"[.!?؟]+", t) if len(x.strip()) > 15]
    s.sort(key=lambda x: -sum(1 for w in KEYWORDS if w in x))
    return " ".join(s[:n])[:300]
def imgurl(e):
    u = None
    for k in ("media_content", "media_thumbnail", "links"):
        for m in e.get(k) or []:
            u = m.get("url") or m.get("href")
            if u:
                break
        if u:
            break
    if not u:
        m = re.search(r'<img[^>]+src="([^"]+)"', e.get("summary", ""))
        u = m.group(1) if m else None
    if not u:
        return None
    for p in ("thumb_", "_thumb", "/t_", "/tn_", "thumbs/"):
        if p in u:
            return u.replace(p, "")
    return u
posted = set()
if os.path.exists("posted.txt"):
    posted = set(open("posted.txt").read().split())
base = f"https://api.telegram.org/bot{TOKEN}"
posts = []
seen = set()
for url in FEEDS:
    try:
        feed = feedparser.parse(url)
    except Exception as ex:
        print("ERR", url, ex)
        continue
    for e in feed.entries[:10]:
        tx = e.get("title", "") + " " + e.get("summary", "")
        if not rel(tx):
            continue
        key = hashlib.md5(e.get("link", e.get("title", "")).encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        posts.append((sum(1 for w in KEYWORDS if w in tx), cln(e.get("title", ""), 120), summ(e.get("summary", "")) or cln(e.get("summary", ""), 200), imgurl(e)))
posts.sort(key=lambda p: p[0], reverse=True)
for imp, title, sum_, img in posts:
    key = hashlib.md5(title.encode()).hexdigest()
    if key in posted:
        continue
    cap = f"<b>{title}</b>\n\n{sum_}"
    try:
        if img:
            photo = requests.get(img, timeout=15).content
            requests.post(base + "/sendPhoto", data={"chat_id": CHANNEL, "caption": cap, "parse_mode": "HTML"}, files={"photo": photo})
        else:
            requests.post(base + "/sendMessage", data={"chat_id": CHANNEL, "text": cap, "parse_mode": "HTML"})
        posted.add(key)
        print("POSTED:", title[:50])
    except Exception as ex:
        print("POST_ERR", ex)
open("posted.txt", "w").write("\n".join(posted))
print("Done.", len(posts), "candidates")
