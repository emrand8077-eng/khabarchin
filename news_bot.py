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
    ("ISNA", "https://www.isna.ir/rss"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("AP", "https://feeds.apnews.com/rss/apf-topnews"),
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

    text = text.strip()

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

    # اگر متن هیچ حرف انگلیسی نداشته باشد
    if english_chars == 0:
        return False

    # اگر هیچ حرف فارسی نداشته باشد،
    # وجود حروف انگلیسی یعنی متن انگلیسی است.
    if persian_chars == 0:
        return True

    # اگر حروف انگلیسی حداقل به اندازه حروف فارسی باشند،
    # متن را انگلیسی در نظر می‌گیریم.
    if english_chars >= persian_chars:
        return True

    # اگر بخش انگلیسی خیلی کوچک باشد،
    # متن فارسی محسوب می‌شود.
    return False


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

    english_text = (
        title + " " + summary
    ).lower()

    # ==========================================
    # موضوعات اصلی کانال
    # ==========================================

    core_topics = [
        "تحریم",
        "جنگ",
        "حمله",
        "موشک",
        "پهپاد",
        "هسته‌ای",
        "هسته ای",
        "مذاکره",
        "برجام",
        "توافق هسته‌ای",
        "توافق هسته ای",
        "تنگه هرمز",
        "هرمز",
        "خلیج فارس",
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
        "آتش‌سوزی",
        "قطعی برق",
        "خاموشی"
    ]

    # ==========================================
    # زمینه ایران
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
        "وزیر امور خارجه ایران",
        "رئیس جمهور ایران",
        "رئیس‌جمهور ایران",
        "سپاه پاسداران",
        "نیروهای مسلح ایران",
        "ارتش ایران",
        "پزشکیان",
        "قالیباف",
        "ظریف",
        "عراقچی",
        "خامنه‌ای",
        "خامنه ای",
        "رهبر ایران"
    ]

    # ==========================================
    # مسئولان و نهادهای مهم
    # ==========================================

    important_people_orgs = [
        "خامنه‌ای",
        "خامنه ای",
        "رهبر",
        "رئیس جمهور",
        "رئیس‌جمهور",
        "رئیس مجلس",
        "وزیر امور خارجه",
        "وزیر خارجه",
        "وزیر کشور",
        "وزیر نفت",
        "رئیس بانک مرکزی",
        "شورای عالی امنیت ملی",
        "سپاه پاسداران",
        "قوه قضائیه",
        "دولت",
        "مجلس",
        "بانک مرکزی"
    ]

    # ==========================================
    # موضوعات سرگرمی / ورزشی / فرهنگی
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
    # حذف خبرهای سرگرمی و ورزشی
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
    # تشخیص زمینه ایران
    # ==========================================

    has_iran_context = False

    for keyword in iran_context:

        if normalize(keyword) in text:
            has_iran_context = True
            break

    # ==========================================
    # تشخیص موضوع اصلی
    # ==========================================

    has_core_topic = False

    for keyword in core_topics:

        if normalize(keyword) in text:
            has_core_topic = True
            break

    # ==========================================
    # خبرهای خارجی
    # ==========================================

    if source in [
        "Al Jazeera",
        "Mehr"
    ]:

        # ==========================================
        # عبارت‌های مستقیم مربوط به ایران
        # ==========================================

        iran_related_english = [
            "iran",
            "iranian",
            "tehran",
            "iran's",
            "iran’s",
            "iranian government",
            "iranian president",
            "iranian foreign minister",
            "iranian military",
            "iranian army",
            "iranian revolutionary guard",
            "revolutionary guard",
            "iran nuclear",
            "iranian nuclear",
            "iran nuclear deal",
            "nuclear deal with iran",
            "iran sanctions",
            "sanctions on iran",
            "iranian economy",
            "iranian oil",
            "iranian missiles",
            "iranian drones",
            "iranian talks",
            "talks with iran",
            "negotiations with iran",
            "iran negotiations",
            "iran war",
            "war with iran",
            "iran conflict",
            "iran attack",
            "attack on iran",
            "iranian attack",
            "iranian strikes",
            "iran strikes",
            "iranian forces",
            "iranian-backed",
            "iran backed"
        ]

        has_english_iran = False

        for keyword in iran_related_english:

            if keyword in english_text:
                has_english_iran = True
                break

        if has_english_iran:
            return True

        # ==========================================
        # موضوعات منطقه‌ای مهم
        # ==========================================

        regional_topics = [
            "strait of hormuz",
            "hormuz",
            "persian gulf",
            "gulf",
            "red sea",
            "yemen",
            "houthis",
            "houthi",
            "iraq",
            "iraqi",
            "israel",
            "israeli",
            "lebanon",
            "hezbollah",
            "gaza",
            "syria",
            "syrian",
            "saudi arabia",
            "saudi",
            "qatar",
            "bahrain",
            "oman",
            "middle east",
            "middle eastern",
            "united arab emirates",
            "uae"
        ]

        has_regional_topic = False

        for keyword in regional_topics:

            if keyword in english_text:
                has_regional_topic = True
                break

        # ==========================================
        # موضوعات امنیتی / نظامی مرتبط با منطقه
        # ==========================================

        regional_security_topics = [
            "missile",
            "missiles",
            "drone",
            "drones",
            "airstrike",
            "airstrikes",
            "strike",
            "strikes",
            "attack",
            "attacks",
            "war",
            "military",
            "military operation",
            "naval",
            "ship",
            "shipping",
            "tanker",
            "oil tanker",
            "oil",
            "pipeline",
            "port",
            "rocket",
            "rockets",
            "bombing",
            "bombed",
            "ceasefire",
            "sanctions",
            "nuclear",
            "negotiations",
            "talks"
        ]

        has_security_topic = False

        for keyword in regional_security_topics:

            if keyword in english_text:
                has_security_topic = True
                break

        # ==========================================
        # خبرهای منطقه‌ای با ارتباط مستقیم به
        # مسیرهای انرژی، حمل‌ونقل یا امنیت
        # ==========================================

        strategic_regional_topics = [
            "strait of hormuz",
            "hormuz",
            "persian gulf",
            "red sea",
            "oil",
            "oil tanker",
            "tanker",
            "shipping",
            "shipping route",
            "pipeline",
            "energy",
            "naval"
        ]

        has_strategic_topic = False

        for keyword in strategic_regional_topics:

            if keyword in english_text:
                has_strategic_topic = True
                break

        # ==========================================
        # منطقه + موضوع امنیتی/استراتژیک
        # ==========================================

        if has_regional_topic and has_security_topic:

            return True

        if has_regional_topic and has_strategic_topic:

            return True

        # ==========================================
        # اگر خبر منطقه‌ای است اما صرفاً یک خبر
        # عادی و غیرمرتبط است، رد شود
        # ==========================================

        return False

    # ==========================================
    # خبر مستقیم درباره ایران
    # ==========================================

    if has_iran_context and has_core_topic:

        return True

    # ==========================================
    # خبرهای سیاسی درباره ایران
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
        "بودجه",
        "تصمیم",
        "مصوبه",
        "دیپلماسی"
    ]

    has_political_topic = False

    for keyword in political_topics:

        if normalize(keyword) in text:

            has_political_topic = True
            break

    if has_iran_context and has_important_person:

        return True

    if has_iran_context and has_political_topic:

        return True

    # ==========================================
    # موضوعات بسیار مهم مرتبط با ایران
    # ==========================================

    very_important = [
        "جنگ",
        "حمله",
        "موشک",
        "پهپاد",
        "تحریم",
        "هسته‌ای",
        "هسته ای",
        "مذاکره",
        "برجام",
        "تنگه هرمز",
        "هرمز",
        "خلیج فارس",
        "نفت",
        "بنزین",
        "دلار",
        "تورم",
        "اعتراض",
        "انفجار",
        "آتش سوزی",
        "آتش‌سوزی"
    ]

    for keyword in very_important:

        if normalize(keyword) in text:

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

    english_title = title.lower()
    english_text = (
        title + " " + summary
    ).lower()

    score = 0

    # ==========================================
    # ارتباط با ایران - فارسی
    # ==========================================

    if "ایران" in title_text or "تهران" in title_text:
        score += 2

    elif "ایران" in text or "تهران" in text:
        score += 1

    # ==========================================
    # ارتباط با ایران - انگلیسی
    # ==========================================

    english_iran_words = [
        "iran",
        "iranian",
        "tehran",
        "iran's",
        "iran’s"
    ]

    has_iran_english = False

    for word in english_iran_words:

        if word in english_title:

            score += 2
            has_iran_english = True
            break

    if not has_iran_english:

        for word in english_iran_words:

            if word in english_text:

                score += 1
                break

    # ==========================================
    # موضوعات بسیار مهم - فارسی
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
    # موضوعات بسیار مهم - انگلیسی
    # ==========================================

    very_important_english = [
        "war",
        "attack",
        "attacks",
        "missile",
        "missiles",
        "sanction",
        "sanctions",
        "nuclear",
        "nuclear deal",
        "negotiation",
        "negotiations",
        "talks",
        "hormuz",
        "strait of hormuz",
        "oil",
        "oil tanker",
        "tanker",
        "gasoline",
        "diesel",
        "dollar",
        "inflation",
        "central bank",
        "protest",
        "protests",
        "explosion",
        "explosions",
        "fire",
        "fires"
    ]

    for word in very_important_english:

        if word in english_title:
            score += 3

        elif word in english_text:
            score += 1

    # ==========================================
    # موضوعات مهم سیاسی و اقتصادی - فارسی
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
    # موضوعات مهم سیاسی و اقتصادی - انگلیسی
    # ==========================================

    important_english = [
        "government",
        "parliament",
        "president",
        "supreme leader",
        "military",
        "army",
        "economy",
        "economic",
        "currency",
        "budget",
        "stock market",
        "strike",
        "strikes",
        "livelihood",
        "trade",
        "foreign policy",
        "foreign relations",
        "national security",
        "energy",
        "shipping",
        "shipping route",
        "pipeline"
    ]

    for word in important_english:

        if word in english_title:
            score += 1

        elif word in english_text:
            score += 1

    # ==========================================
    # مقام‌های ارشد - فارسی
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
    # مقام‌های ارشد - انگلیسی
    # ==========================================

    senior_officials_english = [
        "president",
        "supreme leader",
        "foreign minister",
        "foreign ministry",
        "interior minister",
        "oil minister",
        "central bank governor",
        "national security council"
    ]

    for word in senior_officials_english:

        if word in english_title:
            score += 1

    # ==========================================
    # اعتبار منبع
    # ==========================================

    trusted = {
        "IRNA": 0,
        "Tasnim": 1,
        "Entekhab": 2,
        "Mehr": 1,
        "ISNA": 1,
        "Al Jazeera": 2,
        "AP": 2,
        "Reuters": 2
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

    # اگر دو متن خیلی کوتاه باشند،
    # مقایسه شباهت می‌تواند اشتباه باشد.
    if len(a) < 25 or len(b) < 25:
        return False

    # ==========================================
    # حذف عبارت‌های خبری عمومی
    # ==========================================

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

        word = normalize(word)

        a = a.replace(
            word,
            " "
        )

        b = b.replace(
            word,
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

    if not a or not b:
        return False

    # ==========================================
    # اگر یکی تقریباً همان متن دیگری باشد
    # ==========================================

    shorter = min(
        len(a),
        len(b)
    )

    longer = max(
        len(a),
        len(b)
    )

    if shorter >= 30:

        if shorter / longer >= 0.65:

            if a in b or b in a:
                return True

    # ==========================================
    # شباهت کلی متن
    # ==========================================

    ratio = SequenceMatcher(
        None,
        a,
        b
    ).ratio()

    if ratio >= 0.72:
        return True

    # ==========================================
    # استخراج کلمات معنادار
    # ==========================================

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
        "درباره",
        "پس",
        "هم",
        "نیز",
        "ایران",
        "ایرانی",
        "تهران"
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

    # ==========================================
    # شباهت بر اساس کلمات کلیدی
    # ==========================================

    smaller_set = min(
        len(words_a),
        len(words_b)
    )

    if smaller_set >= 4:

        common_ratio = (
            len(common) / smaller_set
        )

        if len(common) >= 3 and common_ratio >= 0.65:
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
        summary
    )

    if not summary:
        return ""

    # اگر خلاصه خیلی شبیه تیتر است،
    # آن را حذف نکن؛ چون ممکن است همان خلاصه واقعی خبر باشد.
    # در مرحله بعد، هوش مصنوعی آن را بازنویسی می‌کند.
    if similar(title, summary):

        if len(summary) < 120:
            return summary

        return summary

    # حذف عبارت‌های رایج ابتدای خلاصه
    prefixes = [
        "تهران- ایرنا-",
        "تهران - ایرنا -",
        "تهران-ایرنا-",
        "تهران - ایرنا-",
        "ایرنا-",
        "ایرنا -",
        "به گزارش ایرنا،",
        "به گزارش ایرنا:",
        "به گزارش ایرنا",
        "رویترز:",
        "رویترز -"
    ]

    for prefix in prefixes:

        if summary.startswith(prefix):

            summary = summary[
                len(prefix):
            ].strip()

    # فاصله‌های اضافی
    summary = re.sub(
        r"\s+",
        " ",
        summary
    ).strip()

    if not summary:
        return ""

    # خلاصه‌های کوتاه را بدون تغییر نگه می‌داریم
    if len(summary) <= 180:
        return summary

    # مهم:
    # اینجا دیگر متن را با [:240] یا مشابه آن قطع نمی‌کنیم.
    # متن کامل RSS باید به هوش مصنوعی برسد تا خودش
    # یک خلاصه کوتاه و کامل تولید کند.
    return summary


def is_summary_incomplete(
    title,
    summary
):

    title = clean_text(title)
    summary = clean_text(summary)

    if not summary:
        return True

    # خلاصه خیلی کوتاه فقط وقتی ناقص محسوب می‌شود
    # که جمله هم ناتمام به نظر برسد.
    if len(summary) < 80:

        incomplete_endings = [
            "،",
            ":",
            "؛",
            "-",
            "–",
            "—",
            "برای",
            "در",
            "به",
            "از",
            "که",
            "با",
            "و",
            "اما",
            "اگر",
            "تا"
        ]

        for ending in incomplete_endings:

            if summary.endswith(ending):
                return True

    # اگر خلاصه تقریباً همان تیتر باشد،
    # فقط در صورتی ناقص در نظر گرفته شود
    # که خیلی کوتاه باشد.
    if similar(title, summary):

        if len(summary) < 80:
            return True

    return False


def rewrite_news_with_ai(
    title,
    summary
):

    prompt = f"""
عنوان خبر:
{title}

متن خبر:
{summary}

این خبر را برای انتشار در یک کانال خبری فارسی بازنویسی کن.

قواعد تیتر:
- تیتر کوتاه، کامل، طبیعی و خبری باشد.
- مهم‌ترین اتفاق خبر را منتقل کند.
- جمله را نیمه‌کاره رها نکند.
- اگر عنوان خام ناقص است، با استفاده از متن خبر آن را کامل کن.
- نام خبرگزاری را از ابتدای تیتر حذف کن.
- اطلاعاتی که در خبر وجود ندارد اضافه نکن.
- تیتر نباید نتیجه‌ای فراتر از خبر القا کند.

قواعد متن:
- اصل خبر را از همان ابتدای متن بیان کن.
- متن روان و حرفه‌ای و مناسب تلگرام باشد.
- معمولاً 1 تا 3 پاراگراف کوتاه کافی است.
- اطلاعات مهم را حذف نکن.
- هیچ عدد، نام، تاریخ، مکان، سمت یا نقل‌قول جدیدی اضافه نکن.
- اگر خبر شامل «ادعا»، «به گفته»، «گزارش شده» یا عبارت مشابه است، همان میزان عدم قطعیت را حفظ کن.
- هیچ تحلیل یا نظر شخصی اضافه نکن.
- اگر خبر انگلیسی است، آن را به فارسی روان ترجمه کن و اطلاعات اصلی را دقیق حفظ کن.

فقط دو مقدار زیر را تولید کن:
title = تیتر نهایی خبر
summary = متن نهایی خبر
"""

    try:

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization":
                    f"Bearer {os.getenv('GROQ_API_KEY')}",
                "Content-Type":
                    "application/json"
            },
            json={
                "model": "openai/gpt-oss-20b",

                "messages": [
                    {
                        "role": "system",
                        "content":
                            "تو یک ویراستار حرفه‌ای اخبار فارسی هستی. "
                            "فقط اطلاعات موجود در خبر را بازنویسی کن "
                            "و هیچ اطلاعات جدیدی اضافه نکن."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],

                "temperature": 0.2,

                "reasoning_effort": "low",

                "max_completion_tokens": 700,

                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "news_post",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string"
                                },
                                "summary": {
                                    "type": "string"
                                }
                            },
                            "required": [
                                "title",
                                "summary"
                            ],
                            "additionalProperties": False
                        }
                    }
                }
            },

            timeout=30
        )

        if response.status_code != 200:

            print(
                "Groq error:",
                response.text
            )

            return {
                "title": title,
                "summary": summary
            }

        data = response.json()

        content = (
            data["choices"][0]["message"]["content"]
        )

        result = json.loads(content)

        new_title = result.get(
            "title",
            ""
        ).strip()

        new_summary = result.get(
            "summary",
            ""
        ).strip()

        if not new_title or not new_summary:

            print(
                "Groq returned empty title or summary"
            )

            return {
                "title": title,
                "summary": summary
            }

        return {
            "title": new_title,
            "summary": new_summary
        }

    except Exception as e:

        print(
            "Groq AI error:",
            e
        )

        return {
            "title": title,
            "summary": summary
        }


def quality_check(
    title,
    summary
):

    title = normalize(title)
    summary = normalize(summary)

    # تیتر خیلی کوتاه یا بی‌معنی
    if len(title) < 15:
        return False

    # خلاصه باید وجود داشته باشد
    if not summary:
        return False

    # خلاصه خیلی کوتاه
    if len(summary) < 35:
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

    if not title:
        return None

    # یک درخواست واحد به Groq برای تیتر و خلاصه
    ai_result = rewrite_news_with_ai(
        title,
        summary
    )

    if ai_result:

        title = ai_result.get(
            "title",
            title
        ).strip()

        summary = ai_result.get(
            "summary",
            summary
        ).strip()

    title = clean_title(title)

    if not title:
        return None

    print(
        "Original title:",
        original_title
    )

    print(
        "Is original title English:",
        is_english(original_title)
    )

    # اگر خبر انگلیسی بود، Groq باید آن را ترجمه کرده باشد.
    # اگر ترجمه ناموفق بود و هنوز عنوان انگلیسی بود، منتشر نکن.
    if is_english(original_title):

        if is_english(title):
            print(
                "Rejected: foreign news translation failed"
            )
            return None

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

            # بعضی RSSها متن کامل خبر را داخل content قرار می‌دهند
            if len(summary) < 180:

                contents = entry.get(
                    "content",
                    []
                )

                if contents:

                    content_text = clean_text(
                        " ".join(
                            item.get(
                                "value",
                                ""
                            )
                            for item in contents
                        )
                    )

                    if len(content_text) > len(summary):

                        summary = content_text

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
    history,
    summary=""
):

    title = title.strip()
    summary = summary.strip()

    for old_news in history:

        old_title = old_news.get(
            "title",
            ""
        ).strip()

        old_summary = old_news.get(
            "summary",
            ""
        ).strip()

        if not old_title:
            continue

        # ==========================================
        # 1. شباهت مستقیم تیترها
        # ==========================================

        if similar(
            title,
            old_title
        ):

            print(
                "Duplicate detected by title:",
                old_title
            )

            return old_news

        # ==========================================
        # 2. اگر خلاصه خبر جدید و قبلی موجود باشد،
        #    خلاصه‌ها را هم بررسی کن
        # ==========================================

        if summary and old_summary:

            if similar(
                summary,
                old_summary
            ):

                print(
                    "Duplicate detected by summary:",
                    old_title
                )

                return old_news

        # ==========================================
        # 3. بررسی ترکیبی عنوان + خلاصه
        # ==========================================

        current_text = (
            title + " " + summary
        )

        old_text = (
            old_title + " " + old_summary
        )

        if similar(
            current_text,
            old_text
        ):

            print(
                "Duplicate detected by full text:",
                old_title
            )

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
            history,
            item["summary"]
        )

        if previous_news:
            print(
                "Rejected old news:",
                item["title"]
            )
            print(
                "Previous similar news:",
                previous_news["title"]
            )
            continue

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
            break

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
