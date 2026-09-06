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

    # موضوعات کاملاً نامرتبط با کانال
    excluded_keywords = [
        "فوتبال",
        "ورزش",
        "بازیکن",
        "بازیگر",
        "بازیگران",
        "سینما",
        "فیلم",
        "سریال",
        "تلویزیون",
        "موسیقی",
        "خواننده",
        "کنسرت",
        "جشنواره فیلم",
        "گیشه",
        "تئاتر",
        "پرسپولیس",
        "استقلال",
        "لیگ برتر",
        "جام جهانی",
        "مسابقه فوتبال",
        "فیفا",
        "اینفانتینو",
        "المپیک",
        "مدال",
        "قهرمان",
        "مسابقات",
        "اپیزود"
    ]

    # موضوعات مهمی که می‌توانند یک خبر مرزی را قابل انتشار کنند
    important_context = [
        "تحریم",
        "جنگ",
        "حمله",
        "موشک",
        "هسته‌ای",
        "هسته ای",
        "مذاکره",
        "برجام",
        "تنگه هرمز",
        "هرمز",
        "نفت",
        "بنزین",
        "دلار",
        "تورم",
        "اعتراض",
        "انتخابات",
        "دولت",
        "مجلس",
        "رئیس جمهور",
        "رئیس‌جمهور",
        "خامنه‌ای",
        "سپاه",
        "بانک مرکزی",
        "بودجه"
    ]

    # حذف خبرهای سرگرمی، ورزشی و فرهنگی نامرتبط
    for keyword in excluded_keywords:

        if normalize(keyword) in text:

            has_important_context = False

            for important in important_context:

                if normalize(important) in text:
                    has_important_context = True
                    break

            if not has_important_context:
                return False

    # ==========================================
    # منابع خارجی
    # ==========================================

    if source == "Al Jazeera":

        english_text = (
            title + " " + summary
        ).lower()

        # ارتباط مستقیم با ایران
        iran_related_english = [
            "iran",
            "iranian",
            "tehran",
            "iran's",
            "iran’s",
            "iran nuclear",
            "iranian nuclear",
            "iran sanctions",
            "sanctions on iran",
            "iranian economy",
            "iranian government",
            "iranian president",
            "iranian foreign minister",
            "iranian military",
            "iranian oil",
            "iranian missiles",
            "iranian talks",
            "iran nuclear deal",
            "nuclear deal with iran",
            "strait of hormuz",
            "hormuz"
        ]

        for keyword in iran_related_english:

            if keyword in english_text:
                return True

        # در خبرهای خارجی، صرف وجود این کلمات کافی نیست:
        # america / israel / trump / gaza / lebanon و...
        return False

    # ==========================================
    # منابع ایرانی
    # ==========================================

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
        "نیروی انتظامی",
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

    title_text = normalize(title)

    text = normalize(
        title + " " + summary
    )

    score = 0

    # ==========================================
    # ارتباط با ایران
    # ==========================================

    if "ایران" in title_text or "تهران" in title_text:
        score += 4

    elif "ایران" in text or "تهران" in text:
        score += 2

    # ==========================================
    # خبرهای بسیار مهم
    # ==========================================

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
        "نفت",
        "بنزین",
        "دلار",
        "تورم",
        "بانک مرکزی",
        "اعتراض",
        "زلزله",
        "انفجار",
        "آتش‌سوزی"
    ]

    for word in very_important:

        word = normalize(word)

        if word in title_text:
            score += 4

        elif word in text:
            score += 2

    # ==========================================
    # موضوعات مهم سیاسی و اقتصادی
    # ==========================================

    important = [
        "دولت",
        "مجلس",
        "رئیس جمهور",
        "رئیس‌جمهور",
        "خامنه‌ای",
        "رهبر",
        "سپاه",
        "ارتش",
        "اقتصاد",
        "ارز",
        "بودجه",
        "بورس",
        "انتخابات",
        "قوه قضائیه",
        "اعتصاب",
        "قطعی برق",
        "خاموشی",
        "معیشت",
        "تولید",
        "تجارت"
    ]

    for word in important:

        word = normalize(word)

        if word in title_text:
            score += 2

        elif word in text:
            score += 1

    # ==========================================
    # مقام‌های ارشد
    # ==========================================

    senior_officials = [
        "رئیس جمهور",
        "رئیس‌جمهور",
        "رهبری",
        "رهبر",
        "رئیس مجلس",
        "وزیر کشور",
        "وزیر امور خارجه",
        "وزیر نفت",
        "رئیس بانک مرکزی",
        "دبیر شورای عالی امنیت ملی"
    ]

    for word in senior_officials:

        word = normalize(word)

        if word in title_text:
            score += 2

    # ==========================================
    # اعتبار منبع
    # ==========================================

    trusted = {
        "IRNA": 2,
        "Tasnim": 2,
        "Entekhab": 2,
        "Mehr": 2,
        "Al Jazeera": 2
    }

    score += trusted.get(
        source,
        0
    )

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

    if shorter >= 30:

        if shorter / longer >= 0.65:

            if a in b or b in a:
                return True

    # حذف بعضی کلمات عمومی برای مقایسه بهتر
    common_words = [
        "گفت",
        "اعلام کرد",
        "خبر داد",
        "اظهار کرد",
        "تاکید کرد",
        "تأکید کرد",
        "عنوان کرد",
        "افزود",
        "در گفت‌وگو",
        "در گفتگو",
        "آخرین",
        "جدیدترین"
    ]

    for word in common_words:

        a = a.replace(
            normalize(word),
            " "
        )

        b = b.replace(
            normalize(word),
            " "
        )

    a = re.sub(
        r"\s+",
        " ",
        a
    ).strip()

    b = re.sub(
        r"\s+",
        " ",
        b
    ).strip()

    # مقایسه شباهت کلی
    ratio = SequenceMatcher(
        None,
        a,
        b
    ).ratio()

    return ratio >= 0.68


# =========================
# تمیز کردن تیتر
# =========================

def clean_title(title):

    title = clean_text(title)

    if not title:
        return ""

    # حذف نام خبرگزاری یا عبارت‌های ابتدایی تیتر
    prefixes = [
        "تهران - ایرنا -",
        "تهران- ایرنا-",
        "تهران – ایرنا -",
        "تهران – ایرنا –",
        "ایرنا -",
        "ایرنا:",
        "رویترز:",
        "رویترز -",
        "به گزارش ایرنا:",
        "به گزارش ایرنا -"
    ]

    for prefix in prefixes:

        if title.startswith(prefix):
            title = title[len(prefix):].strip()

    # حذف عبارت‌های زرد یا غیرخبری از ابتدای تیتر
    soft_prefixes = [
        "پست عجیب ",
        "واکنش عجیب ",
        "تصمیم عجیب ",
        "خبر عجیب ",
        "ماجرای عجیب ",
        "تصویر عجیب ",
        "حرکت عجیب ",
        "اظهارنظر عجیب ",
        "حرف عجیب "
    ]

    for prefix in soft_prefixes:

        if title.startswith(prefix):
            title = title[len(prefix):].strip()

    # حذف بعضی عبارت‌های کلیشه‌ای که ارزش خبری اضافه نمی‌کنند
    soft_words = [
        "عجیب و غریب",
        "باورنکردنی",
        "جنجالی",
        "خبرساز",
        "شوکه‌کننده",
        "شوک‌آور"
    ]

    for word in soft_words:

        title = title.replace(
            word,
            ""
        )

    # اگر حذف عبارت باعث فاصله اضافی شد
    title = re.sub(
        r"\s+",
        " ",
        title
    ).strip()

    # اگر تیتر چند بخش با / یا | داشته باشد،
    # فقط بخش اصلی را نگه می‌داریم.
    if " / " in title:
        title = title.split(" / ")[0].strip()

    if " | " in title:
        title = title.split(" | ")[0].strip()

    # حذف فاصله قبل از علائم نگارشی
    title = re.sub(
        r"\s+([،؛:؟!])",
        r"\1",
        title
    ).strip()

    # اگر تیتر خیلی طولانی بود
    if len(title) > 110:

        shortened = title[:110]

        last_break = max(
            shortened.rfind("؛"),
            shortened.rfind("،"),
            shortened.rfind(":"),
            shortened.rfind("-"),
            shortened.rfind("–")
        )

        if last_break > 55:
            title = shortened[:last_break].strip()

        else:
            title = (
                shortened
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

    # اگر خلاصه تقریباً همان تیتر است، دوباره تکرارش نکن
    if similar(title, summary):
        return ""

    summary = re.sub(
        r"\s+",
        " ",
        summary
    ).strip()

    # حذف عبارت‌های رایج خبرگزاری‌ها
    prefixes = [
        "به گزارش ",
        "به نقل از ",
        "در این گزارش ",
        "در همین رابطه ",
        "به گزارش خبرنگار ",
        "به نقل از خبرنگار ",
        "وی در ادامه گفت:",
        "وی افزود:",
        "او افزود:"
    ]

    for prefix in prefixes:

        if summary.startswith(prefix):
            summary = summary[len(prefix):].strip()

    # حذف عبارت‌های تبلیغاتی یا ادبی رایج
    soft_phrases = [
        "حماسه‌آفرینی",
        "حماسه آفرینی",
        "حماسه‌ها",
        "حماسه ها",
        "لحظه‌ای تردید نمی‌کنند",
        "لحظه ای تردید نمی کنند",
        "با افتخار",
        "مایه افتخار",
        "دشمن‌شکن",
        "دشمن شکن",
        "تاریخی و ماندگار"
    ]

    for phrase in soft_phrases:

        summary = summary.replace(
            phrase,
            ""
        )

    # مرتب کردن فاصله‌ها بعد از حذف عبارت‌ها
    summary = re.sub(
        r"\s+",
        " ",
        summary
    ).strip()

    # حذف نشانه‌های اضافی ابتدای متن
    summary = re.sub(
        r"^[،؛:.\-–—]+\s*",
        "",
        summary
    ).strip()

    # کوتاه کردن متن
    if len(summary) > 300:

        shortened = summary[:300]

        last_break = max(
            shortened.rfind("،"),
            shortened.rfind("."),
            shortened.rfind("؛"),
            shortened.rfind("؟")
        )

        if last_break > 160:
            summary = shortened[:last_break + 1].strip()

        else:
            summary = (
                shortened
                .rsplit(" ", 1)[0]
                + "..."
            )

    return summary


def rewrite_summary_with_ai(
    title,
    summary
):

    api_key = os.environ.get(
        "OPENROUTER_API_KEY"
    )

    if not api_key or not summary:
        return summary

    prompt = f"""
تو ویراستار یک کانال خبری فارسی هستی.

تیتر:
{title}

متن خبر:
{summary}

متن را به یک خلاصه کوتاه، روان و خبری برای تلگرام تبدیل کن.

قوانین:
- معنی و اطلاعات اصلی خبر را تغییر نده.
- هیچ اطلاعات جدیدی اضافه نکن.
- نظر شخصی یا تحلیل سیاسی اضافه نکن.
- لحن تبلیغاتی، احساسی و اغراق‌آمیز را حذف کن.
- نام اشخاص، اعداد، تاریخ‌ها و مکان‌های مهم را حفظ کن.
- متن را فارسی طبیعی و قابل فهم بنویس.
- حداکثر 3 جمله.
- فقط متن خلاصه را برگردان؛ هیچ توضیح اضافه‌ای نده.
"""

    try:

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openrouter/free",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            },
            timeout=30
        )

        if response.status_code != 200:
            return summary

        data = response.json()

        rewritten = (
            data["choices"][0]["message"]["content"]
            .strip()
        )

        if not rewritten:
            return summary

        return rewritten

    except Exception:
        return summary


def quality_check(
    title,
    summary
):

    title = normalize(title)
    summary = normalize(summary)

    # تیتر خیلی کوتاه یا بی‌معنی
    if len(title) < 15:
        return False

    # خلاصه خیلی کوتاه
    if summary and len(summary) < 35:
        return False

    # تیتر نباید فقط چند کلمه عمومی باشد
    weak_titles = [
        "آخرین خبر",
        "خبر مهم",
        "جزئیات بیشتر",
        "واکنش جدید",
        "خبر جدید",
        "آخرین اخبار"
    ]

    for weak in weak_titles:

        if title == normalize(weak):
            return False

    return True


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

    if is_english(title):
        return None

    if summary:

        summary = rewrite_summary_with_ai(
            title,
            summary
        )

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
