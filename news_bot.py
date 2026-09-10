import os
import re
import html
import hashlib
import feedparser
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
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
    ("Entekhab", "https://www.entekhab.ir/fa/rss/allnews"),
    ("Tasnim", "https://www.tasnimnews.ir/fa/rss"),
    ("IRNA", "https://www.irna.ir/rss"),
    ("Mehr", "https://en.mehrnews.com/rss"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
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

    # ==========================================
    # موضوعات اصلی کانال
    # ==========================================

    core_topics = [
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
        "ارز",
        "تورم",
        "بانک مرکزی",
        "بودجه",
        "اعتراض",
        "اعتصاب",
        "انتخابات",
        "اقتصاد",
        "معیشت",
        "تجارت خارجی",
        "روابط خارجی",
        "سیاست خارجی",
        "امنیت ملی",
        "انفجار",
        "زلزله",
        "سیل",
        "آتش سوزی",
        "قطعی برق",
        "خاموشی"
    ]

    # ==========================================
    # نشانه‌های مشخص ایران
    # ==========================================

    iran_context = [
        "ایران",
        "تهران",
        "ایرانی",
        "جمهوری اسلامی",
        "دولت ایران",
        "مجلس ایران",
        "بانک مرکزی ایران",
        "وزیر خارجه ایران",
        "رئیس جمهور ایران",
        "رئیس‌جمهور ایران",
        "سپاه پاسداران",
        "نیروهای مسلح ایران",
        "ارتش ایران"
    ]

    # ==========================================
    # مسئولان و نهادهای مهم
    # ==========================================

    important_people_orgs = [
        "خامنه‌ای",
        "رهبر",
        "رئیس جمهور",
        "رئیس‌جمهور",
        "رئیس مجلس",
        "وزیر امور خارجه",
        "وزیر کشور",
        "وزیر نفت",
        "رئیس بانک مرکزی",
        "شورای عالی امنیت ملی",
        "سپاه پاسداران",
        "قوه قضائیه"
    ]

    # ==========================================
    # مواردی که ذاتاً نامرتبط‌اند
    # ==========================================

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
        "اپیزود",
        "گردشگری",
        "گردشگر",
        "تور گردشگری",
        "میراث فرهنگی",
        "صنایع دستی",
        "جشنواره",
        "کنسرت"
    ]

    # ==========================================
    # خبرهای کاملاً سرگرمی/ورزشی/فرهنگی
    # مگر اینکه موضوع مهم سیاسی یا اقتصادی داشته باشند
    # ==========================================

    for keyword in excluded_keywords:

        if normalize(keyword) in text:

            has_core_topic = False

            for topic in core_topics:

                if normalize(topic) in text:
                    has_core_topic = True
                    break

            if not has_core_topic:
                return False

    # ==========================================
    # منابع خارجی
    # ==========================================

    if source == "Al Jazeera":

        english_text = (
            title + " " + summary
        ).lower()

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

        return False

    # ==========================================
    # منابع ایرانی
    # ==========================================

    has_iran_context = False

    for keyword in iran_context:

        if normalize(keyword) in text:
            has_iran_context = True
            break

    has_core_topic = False

    for keyword in core_topics:

        if normalize(keyword) in text:
            has_core_topic = True
            break

    # ==========================================
    # خبرهای مرتبط مستقیم با ایران
    # ==========================================

    if has_iran_context and has_core_topic:
        return True

    # ==========================================
    # اخبار بسیار مهم سیاسی/امنیتی
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
        "نفت",
        "بنزین",
        "دلار",
        "تورم",
        "اعتراض",
        "انفجار",
    ]

    for keyword in very_important:

        if normalize(keyword) in text:

            if has_iran_context:
                return True

    # ==========================================
    # مسئولان و نهادهای مهم
    # فقط وقتی موضوع واقعاً سیاسی باشد
    # ==========================================

    has_important_person = False

    for keyword in important_people_orgs:

        if normalize(keyword) in text:
            has_important_person = True
            break

    political_topics = [
        "دولت",
        "مجلس",
        "قانون",
        "وزارت",
        "سیاست",
        "روابط خارجی",
        "سیاست خارجی",
        "امنیت",
        "انتخابات",
        "بودجه"
    ]

    has_political_topic = False

    for keyword in political_topics:

        if normalize(keyword) in text:
            has_political_topic = True
            break

    if has_important_person and has_political_topic:

        if has_iran_context:
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
    # فقط برای تقویت امتیاز، نه تعیین اهمیت
    # ==========================================

    if "ایران" in title_text or "تهران" in title_text:
        score += 2

    elif "ایران" in text or "تهران" in text:
        score += 1

    # ==========================================
    # موضوعات بسیار مهم
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
        "انفجار",
        "آتش‌سوزی"
    ]

    for word in very_important:

        word = normalize(word)

        if word in title_text:
            score += 3

        elif word in text:
            score += 1

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
        "ارتش",
        "اقتصاد",
        "ارز",
        "بودجه",
        "بورس",
        "اعتصاب",
        "قطعی برق",
        "خاموشی",
        "معیشت",
        "تولید",
        "تجارت",
        "سیاست خارجی",
        "روابط خارجی",
        "امنیت ملی"
    ]

    for word in important:

        word = normalize(word)

        if word in title_text:
            score += 1

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
            score += 1

    # ==========================================
    # اعتبار منبع
    # امتیاز بسیار کم تا منبع به‌تنهایی
    # باعث انتشار خبر نشود
    # ==========================================

    trusted = {
        "IRNA": 1,
        "Tasnim": 1,
        "Entekhab": 1,
        "Mehr": 1,
        "Al Jazeera": 1
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
        "جدیدترین",
        "ایران",
        "ایرانی",
        "تهران"
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

    if ratio >= 0.68:
        return True

    # استخراج کلمات معنادار
    stop_words = {
        "به",
        "از",
        "در",
        "با",
        "برای",
        "که",
        "را",
        "و",
        "یا",
        "این",
        "آن",
        "یک",
        "بر",
        "تا",
        "کرد",
        "کرده",
        "شد",
        "شده",
        "است",
        "هست",
        "خواهد",
        "می‌شود",
        "می‌شود",
        "درباره",
        "پس",
        "هم",
        "نیز"
    }

    words_a = {
        word
        for word in a.split()
        if len(word) >= 4
        and word not in stop_words
    }

    words_b = {
        word
        for word in b.split()
        if len(word) >= 4
        and word not in stop_words
    }

    if not words_a or not words_b:
        return False

    common = words_a & words_b

    # اگر چند کلمه کلیدی مهم مشترک باشند
    smaller_set = min(
        len(words_a),
        len(words_b)
    )

    if smaller_set >= 4:

        if len(common) >= 3:

            common_ratio = (
                len(common) / smaller_set
            )

            if common_ratio >= 0.60:
                return True

    return False


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

    # حذف بعضی عبارت‌های کلیشه‌ای
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

    # جدا کردن بخش‌های مختلف تیتر
    if "/" in title:
       title = title.split("/", 1)[0].strip()

    if "|" in title:
       title = title.split("|", 1)[0].strip()

    # حذف فاصله‌های اضافی
    title = re.sub(
        r"\s+",
        " ",
        title
    ).strip()

    # حذف فاصله قبل از علائم نگارشی
    title = re.sub(
        r"\s+([،؛:؟!])",
        r"\1",
        title
    ).strip()

    # اگر تیتر خیلی طولانی بود
    if len(title) > 90:

        shortened = title[:90]

        # اولویت با جداکننده‌های طبیعی
        last_break = max(
            shortened.rfind("؛"),
            shortened.rfind("،"),
            shortened.rfind("؟"),
            shortened.rfind("!")
        )

        if last_break >= 45:

            title = shortened[
                :last_break + 1
            ].strip()

        else:

            # اگر جداکننده مناسبی نبود،
            # از آخرین فاصله استفاده می‌کنیم
            title = (
                shortened
                .rsplit(" ", 1)[0]
                .strip()
            )

    # حذف سه‌نقطه‌های باقی‌مانده از انتهای تیتر
    title = re.sub(
        r"\.{3,}$",
        "",
        title
    ).strip()

    title = re.sub(
        r"…+$",
        "",
        title
    ).strip()

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

    print(
        "make_summary input:",
        summary[:200]
    )

    print(
        "make_summary input length:",
        len(summary)
    )

    if not summary:
        return ""

    # اگر خلاصه تقریباً همان تیتر است، دوباره تکرارش نکن
    if similar(title, summary):

       if len(summary) < 120:
          return summary

       return ""

    # یکدست کردن فاصله‌ها
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

    # حذف عبارت‌های تبلیغاتی یا ادبی
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

    # یکدست کردن فاصله‌ها بعد از حذف
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

    # اگر متن خیلی کوتاه است، همان را نگه دار
    if len(summary) <= 180:
        return summary

    # اگر متن طولانی است، ابتدا فقط تا حدود 240 کاراکتر نگه دار
    shortened = summary[:240]

    # ترجیح با پایان طبیعی جمله یا عبارت است
    last_break = max(
        shortened.rfind("،"),
        shortened.rfind("."),
        shortened.rfind("؛"),
        shortened.rfind("؟")
    )

    if last_break >= 120:

        summary = shortened[
            :last_break + 1
        ].strip()

    else:

        summary = (
            shortened
            .rsplit(" ", 1)[0]
            .strip()
        )

    return summary


def rewrite_summary_with_ai(
    title,
    summary
):

    if not summary:
        return ""

    prompt = f"""
تو ویراستار ارشد یک کانال خبری فارسی هستی.

عنوان خبر:
{title}

متن خبر:
{summary}

وظیفه:
متن خبر را به یک خلاصه کوتاه، طبیعی و حرفه‌ای برای انتشار در تلگرام تبدیل کن.

قوانین بسیار مهم:

- معنی و واقعیت خبر را دقیقاً حفظ کن.
- هیچ اطلاعات جدیدی اضافه نکن.
- درباره چیزی که در متن منبع گفته نشده حدس نزن.
- نام افراد، سمت‌ها، سازمان‌ها، کشورها، مکان‌ها، اعداد و تاریخ‌ها را تغییر نده.
- اگر متن شامل «مدعی شد»، «به گفته»، «ادعا کرد»، «بر اساس گزارش» یا عبارت مشابه است، این نسبت دادن را حذف نکن.
- اگر خبر درباره یک ادعاست، آن را به‌عنوان واقعیت قطعی ننویس.
- نقل‌قول‌های طولانی را به شکل غیرمستقیم و کوتاه خلاصه کن.
- از تکرار عنوان در خلاصه خودداری کن.
- لحن خبری، روان، خنثی و طبیعی باشد.
- از عبارت‌های تبلیغاتی، هیجانی، زرد و کلیشه‌ای استفاده نکن.
- خلاصه معمولاً 1 یا 2 جمله باشد.
- خلاصه ترجیحاً بین 120 تا 250 کاراکتر باشد.
- فقط متن خلاصه را برگردان.
- هیچ توضیحی درباره کاری که انجام دادی ننویس.

خلاصه نهایی:
"""

    try:

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openrouter/free",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 180
            },
            timeout=30
        )

        data = response.json()

        result = (
            data["choices"][0]["message"]["content"]
            .strip()
        )

        if result:
            return result

    except Exception:
        pass

    return summary


def rewrite_title_with_ai(
    title,
    summary
):

    prompt = f"""
تو یک دبیر حرفه‌ای خبر برای یک کانال تلگرامی فارسی هستی.

عنوان خام:
{title}

خلاصه خبر:
{summary}

وظیفه:
عنوان خبر را به یک تیتر فارسی کوتاه، کامل، طبیعی و خبری تبدیل کن.

قوانین بسیار مهم:
- فقط بر اساس اطلاعات موجود در عنوان و خلاصه بنویس.
- هیچ اطلاعات جدیدی اضافه نکن.
- معنی خبر را تغییر نده.
- نام افراد، کشورها، سازمان‌ها، مکان‌ها و اعداد را حفظ کن.
- اگر عنوان خام ناقص یا بریده شده، آن را با استفاده از اطلاعات موجود در خلاصه کامل کن.
- نام خبرگزاری یا منبع را از ابتدای تیتر حذف کن.
- تیتر حداکثر 90 کاراکتر باشد.
- از لحن تبلیغاتی، احساسی، زرد یا طنز استفاده نکن.
- فقط خود تیتر را بنویس و هیچ توضیح دیگری نده.

تیتر نهایی:
"""

    try:

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization":
                    f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                "Content-Type":
                    "application/json"
            },
            json={
                "model": "openrouter/free",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 100
            },
            timeout=30
        )

        if response.status_code != 200:
            return title

        data = response.json()

        result = (
            data["choices"][0]["message"]["content"]
            .strip()
        )

        if not result:
            return title

        result = result.replace(
            "تیتر نهایی:",
            ""
        ).strip()

        if len(result) > 100:
            result = result[:100].rsplit(
                " ",
                1
            )[0].strip()

        return result

    except Exception:
        return title


def translate_foreign_news_with_ai(
    title,
    summary
):

    prompt = f"""
تو یک مترجم و ویراستار حرفه‌ای خبر برای یک کانال تلگرامی فارسی هستی.

عنوان انگلیسی:
{title}

خلاصه انگلیسی:
{summary}

وظیفه:
این خبر را به فارسی روان و خبری ترجمه کن.

قوانین:
- معنی خبر را دقیق حفظ کن.
- هیچ اطلاعات جدیدی اضافه نکن.
- نام افراد، سازمان‌ها، مکان‌ها، عددها و تاریخ‌ها را حفظ کن.
- لحن خبری، ساده و بی‌طرف باشد.
- از لحن تبلیغاتی یا احساسی استفاده نکن.
- عنوان فارسی کوتاه و طبیعی باشد.
- خلاصه حداکثر 2 جمله باشد.
- فقط در قالب زیر پاسخ بده:

TITLE:
عنوان فارسی

SUMMARY:
خلاصه فارسی
"""

    try:

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization":
                    f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                "Content-Type":
                    "application/json"
            },
            json={
                "model": "openrouter/free",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 250
            },
            timeout=30
        )

        if response.status_code != 200:
            return None

        data = response.json()

        result = (
            data["choices"][0]["message"]["content"]
            .strip()
        )

        if "TITLE:" not in result:
            return None

        if "SUMMARY:" not in result:
            return None

        title_part = result.split(
            "TITLE:",
            1
        )[1]

        title_part, summary_part = title_part.split(
            "SUMMARY:",
            1
        )

        translated_title = title_part.strip()
        translated_summary = summary_part.strip()

        if not translated_title:
            return None

        return {
            "title": translated_title,
            "summary": translated_summary
        }

    except Exception:
        return None


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
    summary,
    source
):

    original_title = title

    title = clean_title(title)

    summary = make_summary(
        title,
        summary
    )
    print(
        "Clean title:",
        title
    )

    print(
        "Clean summary:",
        summary
    )

    if summary and len(title) > 70:

       title = rewrite_title_with_ai(
           title,
           summary
    )

       title = clean_title(title)

    if not title:
        return None

    # خبر خارجی انگلیسی
    if is_english(original_title):

        translated = translate_foreign_news_with_ai(
            original_title,
            summary
        )

        if not translated:
            return None

        title = translated["title"]
        summary = translated["summary"]

    # خبرهای فارسی
    else:

        if summary and len(summary) > 180:

            summary = rewrite_summary_with_ai(
                title,
                summary
            )

    if not title:
        return None

    if summary:

        if not quality_check(
            title,
            summary
        ):
            return None

        return (
            f"<b>{html.escape(title)}</b>"
            f"\n\n"
            f"{html.escape(summary)}"
            f"\n\n"
            f"@MeRan_ir | {html.escape(source)}"
        )

    if not quality_check(title, ""):
        return None

    return (
        f"<b>{html.escape(title)}</b>"
        f"\n\n"
        f"@MeRan_ir | {html.escape(source)}"
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
            
            print(
                "Raw summary:",
                summary[:200]
            )

            print(
                "Summary length:",
                len(summary)
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


def fetch_article_text(link):

    try:

        response = requests.get(
            link,
            timeout=20,
            headers={
                "User-Agent":
                "Mozilla/5.0 (NewsBot)"
            }
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.content,
            "html.parser",
            from_encoding="utf-8"
        )
        
        print(
            "HTML preview:",
            response.text[:1500]
        )

        print(
            "Article page status:",
            response.status_code
        )

        print(
            "Article page size:",
            len(response.text)
        )

        # حذف بخش‌های غیرمتنی
        for tag in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header"
        ]):

            tag.decompose()

        paragraphs = []

        for tag in soup.find_all(
            ["p", "div", "article"]
        ):

            text = clean_text(
                tag.get_text(" ", strip=True)
            )

            if len(text) >= 50:
               paragraphs.append(text)

        article_text = "\n".join(
            paragraphs
        )

        return article_text[:10000]

    except Exception as e:

        print(
            "[ARTICLE ERROR]:",
            e
        )

        return ""


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

def save_news_history(item):

    history_file = "news_history.json"

    try:

        if os.path.exists(history_file):

            with open(
                history_file,
                "r",
                encoding="utf-8"
            ) as f:

                history = json.load(f)

        else:

            history = []

        history.append({
            "title": item["title"],
            "summary": item["summary"],
            "source": item["source"],
            "link": item["link"],
            "published_at": datetime.now().isoformat()
        })

        # فقط 100 خبر اخیر نگه داشته شود
        history = history[-100:]

        with open(
            history_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                history,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception as e:

        print(
            "Could not save news history:",
            e
        )

def load_news_history():

    history_file = "news_history.json"

    try:

        if not os.path.exists(history_file):
            return []

        with open(
            history_file,
            "r",
            encoding="utf-8"
        ) as f:

            history = json.load(f)

        if not isinstance(history, list):
            return []

        return history

    except Exception as e:

        print(
            "Could not load news history:",
            e
        )

        return []

def find_previous_similar_news(
    title,
    history
):

    for old_news in history:

        old_title = old_news.get(
            "title",
            ""
        )

        if similar(
            title,
            old_title
        ):

            return old_news

    return None

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
    # با اولویت خبر مهم‌تر
    # =========================

    unique_news = []

    for item in all_news:

        news_id = make_id(
            item["title"],
            item["link"]
        )

        if news_id in posted:
            continue

        duplicate_index = None

        for index, old_item in enumerate(unique_news):

            if similar(
                item["title"],
                old_item["title"]
            ):

                duplicate_index = index
                break

        if duplicate_index is None:

            unique_news.append(
                item
            )

        else:

            old_item = unique_news[
                duplicate_index
            ]

            old_score = importance_score(
                old_item["title"],
                old_item["summary"],
                old_item["source"]
            )

            new_score = importance_score(
                item["title"],
                item["summary"],
                item["source"]
            )

            # اگر خبر جدید مهم‌تر بود،
            # جای خبر قبلی را می‌گیرد.
            if new_score > old_score:

                unique_news[
                    duplicate_index
                ] = item

    print(
        f"New unique news: "
        f"{len(unique_news)}"
    )

    # =========================
    # امتیازدهی
    # =========================

    history = load_news_history()

    scored = []

    for item in unique_news:

        previous_news = find_previous_similar_news(
            item["title"],
            history
        )

        if previous_news:
            print(
                "Previous similar news:",
                previous_news["title"]
            )
            print(
                "Current news:",
                item["title"]
            )
            print(
                "Current source:",
                item["source"]
            )

        if not is_relevant(
            item["title"],
            item["summary"],
            item["source"]
        ):
            print(
                "Rejected by relevance:",
                item["title"],
                "| Source:",
                item["source"]
            )
            continue

        score = importance_score(
            item["title"],
            item["summary"],
            item["source"]
        )

        item["score"] = score
        print(
            "Candidate:",
            item["title"],
            "| Score:",
             score,
            "| Source:",
            item["source"]
        )

        if score >= 4:
            scored.append(item)

    # مهم‌ترین خبرها اول
    scored.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    scored = scored[:3]

    print(
        f"Selected news: "
        f"{len(scored)}"
    )

    # =========================
    # انتشار
    # =========================

    for item in scored:

        article_text = fetch_article_text(
            item["link"]
        )

        print(
            "Article text length:",
            len(article_text)
        )

        print(
            "Article text preview:",
            article_text[:500]
        )

        post = make_post(
            item["title"],
            item["summary"],
            item["source"]
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
            save_news_history(item)

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
