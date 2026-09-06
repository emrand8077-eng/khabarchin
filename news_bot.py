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
    raise RuntimeError(
        "BOT_TOKEN یا CHANNEL_ID در GitHub Secrets پیدا نشد."
    )

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

POSTED_FILE = "posted.txt"
MAX_POSTED = 1000

# =========================
# کلمات مرتبط با ایران
# =========================

KEYWORDS = [
    "ایران", "تهران", "دولت", "مجلس",
    "رئیس جمهور", "رئیس‌جمهور",
    "خامنه‌ای", "رهبر",
    "سپاه", "ارتش", "نیروی انتظامی",
    "تحریم", "برجام", "مذاکره",
    "آمریکا", "اسرائیل",
    "اقتصاد", "تورم", "دلار", "ارز",
    "بانک مرکزی", "نفت", "گاز", "بنزین",
    "بودجه", "بورس", "انتخابات",
    "وزیر", "وزارت", "قوه قضائیه",
    "اعتراض", "اعتصاب",
    "زلزله", "سیل", "حادثه",
    "انفجار", "آتش‌سوزی",
    "قطعی برق", "خاموشی",
    "تنگه هرمز", "هرمز",
    "غزه", "لبنان", "عراق", "سوریه",
    "خلیج فارس"
]

# =========================
# کلمات خبرهای مهم
# =========================

IMPORTANT_WORDS = [
    "تحریم",
    "جنگ",
    "حمله",
    "موشک",
    "هسته‌ای",
    "هسته ای",
    "مذاکره",
    "برجام",
    "دلار",
    "تورم",
    "نفت",
    "بنزین",
    "انتخابات",
    "رئیس جمهور",
    "رئیس‌جمهور",
    "خامنه‌ای",
    "سپاه",
    "مجلس",
    "اعتراض",
    "زلزله",
    "سیل",
    "انفجار",
    "آمریکا",
    "اسرائیل",
    "بانک مرکزی",
    "بودجه",
    "تنگه هرمز",
    "هرمز"
]

# =========================
# منابع
# =========================

FEEDS = [
    (
        "Entekhab",
        "https://www.entekhab.ir/fa/rss/allnews"
    ),
    (
        "Tasnim",
        "https://www.tasnimnews.ir/fa/rss"
    ),
    (
        "IRNA",
        "https://www.irna.ir/rss"
    ),
    (
        "Mehr",
        "https://en.mehrnews.com/rss"
    ),
    (
        "Al Jazeera",
        "https://www.aljazeera.com/xml/rss/all.xml"
    ),
]

# =========================
# پاک‌سازی متن
# =========================

def clean_text(text):

    if not text:
        return ""

    text = html.unescape(text)

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================
# نرمال‌سازی فارسی
# =========================

def normalize(text):

    text = clean_text(text).lower()

    replacements = {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "‌": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


# =========================
# شناسه خبر
# =========================

def make_id(title, link):

    value = (
        normalize(title)
        + "|"
        + link
    )

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


# =========================
# خبرهای قبلی
# =========================

def load_posted():

    if not os.path.exists(
        POSTED_FILE
    ):
        return set()

    try:

        with open(
            POSTED_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return {
                line.strip()
                for line in f
                if line.strip()
            }

    except Exception:

        return set()


def save_posted(posted):

    items = list(posted)[
        -MAX_POSTED:
    ]

    with open(
        POSTED_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        for item in items:
            f.write(
                item + "\n"
            )


# =========================
# تشخیص زبان
# =========================

def is_english(text):

    if not text:
        return False

    english_chars = len(
        re.findall(
            r"[A-Za-z]",
            text
        )
    )

    persian_chars = len(
        re.findall(
            r"[\u0600-\u06FF]",
            text
        )
    )

    return (
        english_chars > persian_chars
    )


# =========================
# مرتبط بودن خبر
# =========================

def is_relevant(
    title,
    summary,
    source
):

    text = normalize(
        title + " " + summary
    )

    # کلمات مرتبط با ایران و موضوعات موردنظر
    iran_keywords = [
        "ایران",
        "تهران",
        "دولت",
        "مجلس",
        "رئیس جمهور",
        "رئیس‌جمهور",
        "خامنه‌ای",
        "رهبر",
        "سپاه",
        "ارتش",
        "تحریم",
        "برجام",
        "مذاکره",
        "آمریکا",
        "اسرائیل",
        "اقتصاد",
        "تورم",
        "دلار",
        "ارز",
        "بانک مرکزی",
        "نفت",
        "گاز",
        "بنزین",
        "بودجه",
        "بورس",
        "انتخابات",
        "وزیر",
        "وزارت",
        "قوه قضائیه",
        "اعتراض",
        "اعتصاب",
        "زلزله",
        "سیل",
        "حادثه",
        "انفجار",
        "آتش‌سوزی",
        "قطعی برق",
        "خاموشی",
        "تنگه هرمز",
        "هرمز",
        "غزه",
        "لبنان",
        "عراق",
        "سوریه",
        "خلیج فارس"
    ]

    # خبرهای خارجی فقط وقتی پذیرفته شوند
    # که ارتباط مشخصی با ایران یا منطقه داشته باشند
    if source == "Al Jazeera":

        english_text = (
            title + " " + summary
        ).lower()

        english_keywords = [
            "iran",
            "iranian",
            "tehran",
            "israel",
            "israeli",
            "trump",
            "sanctions",
            "nuclear",
            "missile",
            "strait of hormuz",
            "hormuz",
            "iraq",
            "lebanon",
            "gaza",
            "iranian economy"
        ]

        for keyword in english_keywords:

            if keyword in english_text:
                return True

        return False

    # منابع ایرانی فقط اگر موضوع خبر
    # در حوزه‌های موردنظر ما باشد
    for keyword in iran_keywords:

        if normalize(keyword) in text:
            return True

    return False


# =========================
# امتیاز اهمیت
# =========================

def importance_score(
    title,
    summary,
    source
):

    text = normalize(
        title + " " + summary
    )

    score = 0

    # ارتباط مستقیم با ایران
    if "ایران" in text or "تهران" in text:
        score += 3

    # موضوعات بسیار مهم
    very_important = [
        "جنگ",
        "حمله",
        "موشک",
        "تحریم",
        "هسته‌ای",
        "هسته ای",
        "مذاکره",
        "برجام",
        "تنگه هرمز",
        "هرمز",
        "آمریکا",
        "اسرائیل",
        "نفت",
        "بنزین",
        "دلار",
        "تورم",
        "بانک مرکزی",
        "اعتراض",
        "زلزله",
        "انفجار"
    ]

    for word in very_important:

        if normalize(word) in text:
            score += 3

    # موضوعات مهم سیاسی و اقتصادی
    important = [
        "دولت",
        "مجلس",
        "رئیس جمهور",
        "رئیس‌جمهور",
        "خامنه‌ای",
        "رهبر",
        "سپاه",
        "ارتش",
        "وزیر",
        "وزارت",
        "اقتصاد",
        "ارز",
        "بودجه",
        "بورس",
        "انتخابات",
        "قوه قضائیه",
        "اعتصاب",
        "قطعی برق",
        "خاموشی"
    ]

    for word in important:

        if normalize(word) in text:
            score += 1

    # اعتبار منبع
    trusted = {
        "IRNA": 2,
        "Tasnim": 2,
        "Entekhab": 2,
        "Mehr": 2,
        "Al Jazeera": 2,
    }

    score += trusted.get(
        source,
        0
    )

    # امتیاز پایه منابع ایرانی
    if source in [
        "IRNA",
        "Tasnim",
        "Entekhab",
        "Mehr"
    ]:
        score += 2

    return score

    # =========================
    # ارتباط مستقیم با ایران
    # =========================

    if "ایران" in text or "تهران" in text:
        score += 3

    # =========================
    # موضوعات بسیار مهم
    # =========================

    very_important = [
        "جنگ",
        "حمله",
        "موشک",
        "تحریم",
        "هسته‌ای",
        "هسته ای",
        "مذاکره",
        "برجام",
        "تنگه هرمز",
        "هرمز",
        "آمریکا",
        "اسرائیل",
        "نفت",
        "بنزین",
        "دلار",
        "تورم",
        "بانک مرکزی",
        "اعتراض",
        "زلزله",
        "انفجار"
    ]

    for word in very_important:

        if normalize(word) in text:
            score += 3

    # =========================
    # موضوعات مهم سیاسی و اقتصادی
    # =========================

    important = [
        "دولت",
        "مجلس",
        "رئیس جمهور",
        "رئیس‌جمهور",
        "خامنه‌ای",
        "رهبر",
        "سپاه",
        "ارتش",
        "وزیر",
        "وزارت",
        "اقتصاد",
        "ارز",
        "بودجه",
        "بورس",
        "انتخابات",
        "قوه قضائیه",
        "اعتصاب",
        "قطعی برق",
        "خاموشی"
    ]

    for word in important:

        if normalize(word) in text:
            score += 1

    # =========================
    # اعتبار منبع
    # =========================

    trusted = {
        "IRNA": 2,
        "Tasnim": 2,
        "Entekhab": 2,
        "Mehr": 2,
        "Al Jazeera": 2,
    }

    score += trusted.get(
        source,
        0
    )

    # =========================
    # امتیاز پایه منابع ایرانی
    # =========================

    if source in [
        "IRNA",
        "Tasnim",
        "Entekhab",
        "Mehr"
    ]:
        score += 2

    return score


# =========================
# تشخیص خبرهای مشابه
# =========================

def similar(a, b):

    a = normalize(a)
    b = normalize(b)

    if not a or not b:
        return False

    # اگر یکی تقریباً شامل دیگری باشد
    shorter = min(len(a), len(b))
    longer = max(len(a), len(b))

    if shorter >= 35:
        if shorter / longer >= 0.70:
            if a in b or b in a:
                return True

    # مقایسه شباهت کلی
    ratio = SequenceMatcher(
        None,
        a,
        b
    ).ratio()

    return ratio >= 0.72


# =========================
# تمیز کردن تیتر
# =========================

def clean_title(title):

    title = clean_text(title)

    # اگر تیتر چند بخش با / داشته باشد،
    # فقط بخش اول را نگه می‌داریم.
    if " / " in title:
        title = title.split(" / ")[0].strip()

    # حذف بخش‌های بعد از |
    if " | " in title:
        title = title.split(" | ")[0].strip()

    # حذف فاصله‌های اضافی
    title = re.sub(
        r"\s+",
        " ",
        title
    ).strip()

    # حداکثر طول تیتر
    if len(title) > 130:
        title = (
            title[:127]
            .rsplit(" ", 1)[0]
            + "..."
        )

    return title


# =========================
# ساخت خلاصه
# =========================

def make_summary(
    title,
    summary
):

    title = clean_text(title)
    summary = clean_text(summary)

    if not summary:
        return ""

    # اگر خلاصه خیلی شبیه تیتر است، حذف شود
    if similar(title, summary):
        return ""

    # فاصله‌های اضافی
    summary = re.sub(
        r"\s+",
        " ",
        summary
    ).strip()

    # حذف عبارت‌های تبلیغاتی و غیرضروری ابتدای متن
    prefixes = [
        "به گزارش ",
        "به نقل از ",
        "در این گزارش ",
        "در همین رابطه "
    ]

    for prefix in prefixes:

        if summary.startswith(prefix):
            summary = summary[len(prefix):].strip()

    # حداکثر طول خلاصه
    if len(summary) > 320:

        shortened = summary[:320]

        # ترجیحاً از آخرین جمله کامل استفاده کن
        last_dot = max(
            shortened.rfind("،"),
            shortened.rfind("."),
            shortened.rfind("؛")
        )

        if last_dot > 180:
            summary = shortened[:last_dot + 1].strip()
        else:
            summary = (
                shortened
                .rsplit(" ", 1)[0]
                + "..."
            )

    return summary


# =========================
# ساخت پست
# =========================

def make_post(
    title,
    summary
):

    title = clean_title(
        title
    )

    summary = make_summary(
        title,
        summary
    )

    if not title:
        return None

    # اگر خبر انگلیسی است،
    # فعلاً منتشر نمی‌کنیم تا متن انگلیسی
    # وارد کانال فارسی نشود.
    if is_english(title):

        return None

    if summary:

        return (
            f"<b>{html.escape(title)}</b>"
            f"\n\n"
            f"{html.escape(summary)}"
        )

    return (
        f"<b>{html.escape(title)}</b>"
    )


# =========================
# دریافت فید
# =========================

def fetch_feed(
    source,
    url
):

    try:

        response = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent":
                "Mozilla/5.0 (NewsBot)"
            }
        )

        response.raise_for_status()

        feed = feedparser.parse(
            response.content
        )

        results = []

        for entry in feed.entries[:20]:

            title = clean_text(
                entry.get(
                    "title",
                    ""
                )
            )

            link = entry.get(
                "link",
                ""
            )

            summary = clean_text(
                entry.get(
                    "summary",
                    ""
                )
                or entry.get(
                    "description",
                    ""
                )
            )

            if (
                not title
                or not link
            ):
                continue

            results.append({
                "source": source,
                "title": title,
                "link": link,
                "summary": summary
            })

        return results

    except Exception as e:

        print(
            f"[ERROR] {source}: {e}"
        )

        return []


# =========================
# ارسال تلگرام
# =========================

def send_message(text):

    url = (
        f"{TELEGRAM_API}"
        f"/sendMessage"
    )

    try:

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

            print(
                "Telegram error:",
                response.text
            )

            return False

        return True

    except Exception as e:

        print(
            "Telegram exception:",
            e
        )

        return False


# =========================
# اجرای اصلی
# =========================

def main():

    print(
        "News bot started."
    )

    posted = load_posted()

    all_news = []

    # =========================
    # دریافت خبرها
    # =========================

    for source, url in FEEDS:

        news = fetch_feed(
            source,
            url
        )

        print(
            f"{source}: "
            f"{len(news)} news"
        )

        all_news.extend(
            news
        )

    # =========================
    # حذف خبرهای تکراری
    # =========================

    unique_news = []

    titles = []

    for item in all_news:

        news_id = make_id(
            item["title"],
            item["link"]
        )

        if news_id in posted:
            continue

        duplicate = False

        for old_title in titles:

            if similar(
                item["title"],
                old_title
            ):

                duplicate = True
                break

        if duplicate:
            continue

        titles.append(
            item["title"]
        )

        unique_news.append(
            item
        )

    print(
        f"New unique news: "
        f"{len(unique_news)}"
    )

    # =========================
    # امتیازدهی
    # =========================

    scored = []

    for item in unique_news:

        if not is_relevant(
            item["title"],
            item["summary"],
            item["source"]
        ):
            continue

        score = importance_score(
            item["title"],
            item["summary"],
            item["source"]
        )

        item["score"] = score

        if score >= 4:

            scored.append(
                item
            )

    # مهم‌ترین خبرها اول
    scored.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # حداکثر 3 خبر در هر اجرا
    scored = scored[:3]

    print(
        f"Selected news: "
        f"{len(scored)}"
    )

    # =========================
    # انتشار
    # =========================

    for item in scored:

        post = make_post(
            item["title"],
            item["summary"]
        )

        # خبر انگلیسی فعلاً رد می‌شود
        if not post:

            print(
                "Skipped non-Persian:",
                item["title"]
            )

            continue

        print(
            "Publishing:",
            item["title"]
        )

        success = send_message(
            post
        )

        if success:

            news_id = make_id(
                item["title"],
                item["link"]
            )

            posted.add(
                news_id
            )

            print(
                "Published successfully."
            )

        else:

            print(
                "Publish failed."
            )

    # ذخیره خبرهای منتشرشده
    save_posted(
        posted
    )

    print(
        "News bot finished."
    )


# =========================
# شروع
# =========================

if __name__ == "__main__":
    main()
