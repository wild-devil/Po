import asyncio
import json
import time
import os
import random
import re
import sys
import unicodedata
import html
import urllib.parse
import urllib.request
import urllib.error
from collections import Counter, OrderedDict, deque
from datetime import datetime, timedelta, timezone

try:
    from spluspy import Client
except ImportError:
    print("❌ لطفاً ابتدا کتابخانه را نصب کنید: pip install spluspy")
    sys.exit(1)

try:
    from spluspy.tl.types import ChannelParticipantsAdmins
except ImportError:
    ChannelParticipantsAdmins = None

try:
    from spluspy.tl.types import ChannelParticipantsSearch
except ImportError:
    ChannelParticipantsSearch = None

try:
    from spluspy.tl.types import ChannelParticipantsRecent
except ImportError:
    ChannelParticipantsRecent = None

try:
    from spluspy.tl.types import ChannelParticipantsBots
except ImportError:
    ChannelParticipantsBots = None

try:
    from spluspy.tl.types import ChannelParticipantsKicked
except ImportError:
    ChannelParticipantsKicked = None

try:
    from spluspy.tl.types import ChannelParticipantsBanned
except ImportError:
    ChannelParticipantsBanned = None

try:
    from spluspy.tl.types import ChannelParticipantsContacts
except ImportError:
    ChannelParticipantsContacts = None

try:
    from spluspy.tl.types import InputMessagesFilterPinned
except ImportError:
    InputMessagesFilterPinned = None

try:
    from spluspy.tl.types import InputMessageEntityMentionName, MessageEntityCode
except ImportError:
    InputMessageEntityMentionName = None
    MessageEntityCode = None

try:
    from spluspy.tl.types import InputUser as _TLInputUser
except ImportError:
    _TLInputUser = None

try:
    from spluspy import utils as _spluspy_utils
except ImportError:
    _spluspy_utils = None


try:
    import uvloop
except ImportError:
    uvloop = None

try:
    import cryptg
    _HAS_CRYPTG = True
except ImportError:
    _HAS_CRYPTG = False

try:
    import orjson
except ImportError:
    orjson = None

try:
    import ahocorasick
except ImportError:
    ahocorasick = None

def _speed_libs_status() -> str:
    parts = [
        f"uvloop={'✅' if uvloop else '❌ (pip install uvloop)'}",
        f"cryptg={'✅' if _HAS_CRYPTG else '❌ (pip install cryptg)'}",
        f"orjson={'✅' if orjson else '❌ (pip install orjson)'}",
        f"pyahocorasick={'✅' if ahocorasick else '❌ (pip install pyahocorasick)'}",
    ]
    return " | ".join(parts)


LOG_ENABLED = False


def _log(*args, **kwargs) -> None:
    if not LOG_ENABLED:
        return
    try:
        print(*args, **kwargs, flush=True)
    except Exception:
        pass


def _log_conn(*args, **kwargs) -> None:
    """پیام‌های وضعیت اتصال (وصل/قطع/لاگین) - این‌ها به‌ندرت اتفاق می‌افتن، پس
    برخلاف _log همیشه چاپ می‌شن تا بشه فهمید ربات وصله یا نه."""
    try:
        print(*args, **kwargs, flush=True)
    except Exception:
        pass


_RPC_LOG_LAST: dict = {}
_RPC_LOG_SKIPPED: dict = {}
_RPC_LOG_EVERY_SECONDS = 5.0


def _rpc_err_kind(e) -> str:
    t = f"{e!r} {e}"
    sec = getattr(e, "seconds", None)
    if not sec and "wait of" in t:
        m = re.search(r"wait of (\d+)", t)
        sec = int(m.group(1)) if m else None
    if sec or "wait of" in t:
        return "🌊 فلود‌ویت" + (f" ({sec} ثانیه)" if sec else "")
    if type(e).__name__ == "ServerError" or "INTERNAL_SERVER_ERROR" in t or "RPCError 500" in t:
        return "🛠 خطای سرور سروش (۵۰۰)"
    return "⚠️ خطا"


def _log_rpc_error(where: str, e, chat_id=None, user_id=None, attempt: str = None) -> None:
    """لاگِ همیشه‌روشنِ خطاهای ارتباط با سرور (فلود‌ویت / ۵۰۰ / ...) با اسمِ بخش یا قفلی که
    باعثش شده. برای اینکه ترمینال تو حمله پر نشه، یه خطای مشابه (همون بخش+نوع+گروه) حداکثر
    هر ۵ ثانیه یک بار چاپ می‌شه و تعداد موارد جاافتاده کنارش میاد."""
    try:
        kind = _rpc_err_kind(e)
        key = (where, kind.split(" (")[0], chat_id)
        now = time.monotonic()
        last = _RPC_LOG_LAST.get(key)
        if last is not None and now - last < _RPC_LOG_EVERY_SECONDS:
            _RPC_LOG_SKIPPED[key] = _RPC_LOG_SKIPPED.get(key, 0) + 1
            return
        skipped = _RPC_LOG_SKIPPED.pop(key, 0)
        _RPC_LOG_LAST[key] = now
        parts = [f"{kind} | بخش: {where}"]
        if chat_id is not None:
            parts.append(f"گروه: {chat_id}")
        if user_id is not None:
            parts.append(f"کاربر: {user_id}")
        if attempt:
            parts.append(f"تلاش: {attempt}")
        if skipped:
            parts.append(f"(+{skipped} مورد مشابه در چند ثانیه‌ی قبل)")
        _log_conn(" | ".join(parts))
    except Exception:
        pass


PHONE_NUMBER = "+989196655818"
BOT_OWNER_ID = 66009832
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_NAME = os.path.join(BASE_DIR, "spy_bot_session")
DATA_FILE = os.path.join(BASE_DIR, "spy_config.json")
CLEANUP_INTERVAL_SECONDS = 35 * 60

BOT_BRAND = "ＭΞＨＤI"
BOT_BRAND_FOOTER = f"\n\n┄─── 『 {BOT_BRAND} 』 ───┄"


def _brand_text(text: str) -> str:
    """Append the bot's signature footer to any outgoing message.
    Centralized here so every message sent through safe_reply /
    send_moderation_alert automatically carries the same clean style."""
    if not text:
        return text
    if BOT_BRAND in text:
        return text
    return f"{text}{BOT_BRAND_FOOTER}"


def load_config() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            if orjson:
                with open(DATA_FILE, "rb") as f:
                    cfg = orjson.loads(f.read())
            else:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg.setdefault("bot_owners", [])
            cfg.setdefault("chats", {})
            return cfg
        except Exception as e:
            _log(f"⚠️ Error loading config: {e}")
    return {
        "bot_owners": [],
        "chats": {},
    }

def _write_config_sync(cfg: dict) -> None:
    tmp_path = DATA_FILE + ".tmp"
    if orjson:

        with open(tmp_path, "wb") as f:
            f.write(orjson.dumps(cfg, option=orjson.OPT_INDENT_2))
            f.flush()
            os.fsync(f.fileno())
    else:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
    os.replace(tmp_path, DATA_FILE)

async def save_config(cfg: dict) -> None:
    try:
        await asyncio.to_thread(_write_config_sync, cfg)
    except Exception as e:
        _log(f"⚠️ Error saving config: {e}")

config = load_config()


ANTI_SPAM_PRESET_WORDS = [
    "🥵", "🤤", "💦", "بــ‌یــ‌و چـ‌ک", "بیوچک", "بیو چک", "بیوو", "سکس", "فیلم", "🍆", "🔞",
]

# این‌ها به‌تنهایی ممکنه زیرمجموعه‌ی یه اسم واقعی باشن (مثلاً «بیو» تو «بیوک»)،
# پس برخلاف بقیه‌ی لیست بالا که substring خام چک می‌شن، این‌ها فقط وقتی می‌گیرن
# که به یه حرف فارسی/عربی دیگه نچسبیده باشن - یعنی نسخه‌ی جدانویسی/فونت‌فانتزی/
# تطویل‌شده‌شون گرفته می‌شه، ولی «بیوک» یا «داداش‌بیو» اشتباهی رد نمی‌شن.
ANTI_KHALE_BOUNDARY_WORDS = ["بیو", "بیوم"]

# نگاشت مشترک حروف عربی به معادل فارسی‌شون (ك→ک ، ي/ى→ی) - چون NFKC روی
# فونت‌های فانتزی/حروف جدانویسی‌شده‌ی عربی معمولاً به شکل عربیِ حرف decode
# می‌کنه نه شکل فارسیِ خودمون، این نگاشت بعد از NFKC اعمال می‌شه تا یکی بشن.
_FA_CHAR_MAP = str.maketrans({"ك": "ک", "ي": "ی", "ى": "ی"})

_ANTI_KHALE_SEP_RE = re.compile(r"[\s\u200b\u200c\u200d\ufeff\u0640.\-_*·•,،٬۔٫\u066b\u066c/|]+")
_ANTI_KHALE_SEP_OPT = r"[\s\u200b\u200c\u200d\ufeff\u0640.\-_*·•,،٬۔٫\u066b\u066c/|]*"
_FA_LETTER_CLASS = r"\u0600-\u06FF"


def _anti_khale_clean(s: str) -> str:
    """NFKC + حذف علامت‌های ترکیبیِ تزئینی + یکسان‌سازی حرف عربی→فارسی، بدون
    حذف فاصله/جداکننده‌ها (چون چک مرزی زیر بهشون نیاز داره)."""
    s = unicodedata.normalize("NFKC", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.translate(_FA_CHAR_MAP)


def _anti_khale_normalize(s: str) -> str:
    """برای قفل ضد تبچی: با NFKC اول فونت‌های تزئینی/حروف عربی جدا-نویسی‌شده
    را به حرف استاندارد فارسی برمی‌گرداند (مثلاً فونت‌های فانتزی که سایت‌های
    "متن قشنگ" تولید می‌کنن)، بعد علامت‌های ترکیبی (زیرخط/خط بالای حرف که با
    آن‌ها اسم رو انگار خط‌کشیده نشون می‌دن) رو حذف می‌کنه، بعد فاصله، نقطه،
    خط‌تیره، زیرخط، ستاره، تطویل عربی (ـ که حروف رو کش می‌ده) و جداکننده‌های
    نامرئی (ZWNJ/ZWJ) رو پاک می‌کنه تا «ب.ی.و»، «ب‌ی‌و»، «فـیـلـم» و مشابه،
    هرجوری نوشته بشن، با شکل ساده‌ی کلمه مطابقت کنن."""
    return _ANTI_KHALE_SEP_RE.sub("", _anti_khale_clean(s)).lower()


def _anti_khale_boundary_re(word: str) -> "re.Pattern":
    """رجکسی که حروفِ word رو با جداکننده‌ی اختیاری بینشون می‌پذیره (پس
    نسخه‌ی نقطه‌دار/ZWNJ/تطویل‌شده رو می‌گیره) ولی اگه بلافاصله (بدون هیچ
    جداکننده‌ای) به یه حرف فارسی/عربیِ دیگه چسبیده باشه - یعنی جزئی از یه
    کلمه‌ی دیگه‌ست - رد می‌کنه."""
    body = _ANTI_KHALE_SEP_OPT.join(re.escape(ch) for ch in word)
    return re.compile(rf"(?<![{_FA_LETTER_CLASS}]){body}(?![{_FA_LETTER_CLASS}])")


_ANTI_KHALE_BOUNDARY_RES = [(_anti_khale_boundary_re(w), w) for w in ANTI_KHALE_BOUNDARY_WORDS]

_ANTI_KHALE_INDEX = []
_seen_ak = set()
for _w in ANTI_SPAM_PRESET_WORDS:
    _wn = _anti_khale_normalize(_w)
    if _wn and _wn not in _seen_ak:
        _seen_ak.add(_wn)
        _ANTI_KHALE_INDEX.append((_wn, _w))
del _seen_ak

_ANTI_KHALE_AC = None  # بعد از ساخته‌شدن ahocorasick (پایین‌تر در فایل) مقداردهی می‌شود


def _anti_khale_match(text: str):
    """Returns the matched preset word if this name/bio should trip the
    anti-khale ('ضد تبچی') lock, else None. Font/dot/ZWNJ/tatweel
    obfuscation insensitive - see _anti_khale_normalize - while the
    boundary-checked short words (ANTI_KHALE_BOUNDARY_WORDS) won't false-
    trigger on a real name/word that merely contains them (e.g. 'بیوک')."""
    if not text:
        return None
    cleaned = _anti_khale_clean(text)
    for pat, orig in _ANTI_KHALE_BOUNDARY_RES:
        if pat.search(cleaned):
            return orig
    normalized = _ANTI_KHALE_SEP_RE.sub("", cleaned).lower()
    if _ANTI_KHALE_AC is not None:
        for _end, orig in _ANTI_KHALE_AC.iter(normalized):
            return orig
        return None
    for wn, orig in _ANTI_KHALE_INDEX:
        if wn in normalized:
            return orig
    return None


ANTI_JAGH_SUBSTRING_WORDS = [
    "ارباب", "برده پی", "سکس", "کص", "کیر", "جقی پی", "لز", "وطنی", "ننت", "کصمادرت",
    "تخم سگ", "کون", "کسمادرت", "فیلم", "بیغیرت", "بی غیرت", "تبادل", "بی پی", "تب پی",
    "ف ی ل م", "💦", "🤤", "🥵", "ف‌ی‌ل‌م", "ت‌ب‌", "ک‌ی‌ر", "خاله ام", "🔞", "س ک س", "س‌ک‌س",
    "ت ب", "یکی بیاد", "دختر بیاد", "پسر بیاد", "دخی حشری", "داغم", "فلیم", "film", "Film",
    "Lez", "pv", "lez pv", "تایم بالام", "ت بادل", "پسر زیر ۱۸", "دختر زیر ۱۸", "سیخ شده",
    "فل دارم", "کصلیسم", "شبادل", "ف میخ", "ف‌ی‌لم", "قیلم", "کلفت", "جنده", "رایگان",
    "فیتیش پا دارم", "ب ی و", "دخترا پی باشن", "لخترا پی باشن", "کال پی", "کال جق", "کال ج‌ق",
    "کال ج ق", "پی جق", "شوگر پی", "بی‌و‌م", "قیمت بیا", "گپ فیلم", "یکی میاد", "جرعت حقیقت موخوام",
    "جرعت حقیقت پی", "گیف پی", "هات ام", "هاتم", "نود میدم", "تنهام کی میاد پیشم", "پول میخام",
    "پول پی", "یکی کمکم میکنه", "چت پی", "ج ق", "مفعول", "مف‌عول", "مف عول", "بردع میخام",
    "برده میخام", "لایه پاهام خیسه", "خیسم", "بکن بیاد", "بیا p", "بردم ارباب پی", "هزینه میکنم",
    "هزینه پی", "متاهل پی", "طبادل", "ثبادل", "فی لم", "حال پی", "ح ا ل پ ی", "حال میدم", "حال بیا", "حال میخای", "حال میخوای", "حال میخوام", "حال میخام",
    "ح‌ا‌ل پی", "ح‌ا‌ل‌پ‌ی", "سن بالا", "سن پایین",
    "کم سن", "صوتی", "تصویر پی", "بکن پی", "بکنم پی", "داغ پی", "سسکی", "بی هستی پ", "بی پ",
    "بی هستی", "بی دوطرفه", "بی دو طرفع", "بی دو طرفه", "بی دو طرف", "شق شده", "ش قم", "ش‌قم",
    "فلم", "کس پی", "کسکش", "کسخول", "بکنمت", "دخ بیاد", "دخی بیاد", "دوطرفه", "دو طرفه",
    "ل ز", "کس میخام", "بی هس", "ابتو میارم با هزینه", "آبتو میارم با هزینه", "با هزینه",
    "با هزین", "چت پیوی", "ت صویری", "ت‌ص‌‌و‌ی‌ر‌ی", "ت ص و ی ر ی", "ت ب ا د ل",
    "د خی", "د خ ی", "د‌خ‌ی","ت پ","دختر خیس","ط ب",
"ث پ","گاییدمت","بگامت","ماساژ","ماسور","ف مخام",
"دو طرف یک پسر",
"بیو چک", "گذاشتم بیو", "سکس زوری", "زوری گذاشتم", "بچتیم", "بیاد بچت", "هوس بادمجون",
"بیومو", "بیوم گذاشتم", "🍆",
]

ANTI_JAGH_PREFIX_WORDS = [
    "تب", "گی", "بیو", "برده", "شقم", "طب", "داغ",
    "ثپ", "تپ", "شق",
]

_ANTI_JAGH_INVISIBLE_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_FA_LETTER_RE = re.compile(r"[\u0600-\u06FF]")


# فقط «شکل جدا-شده با ZWNJ/فاصله‌ی نامرئی»: چ‌ت — خودِ «چت» عادی رو نمی‌گیره.
# قبل از نرمال‌سازی (که ZWNJ رو برمی‌داره) روی متن خام چک می‌شه.
_ANTI_JAGH_OBFUSCATED_RES = [
    (re.compile(r"(?<![\u0600-\u06FF])\u0686[\u200b-\u200d\ufeff]+\u062a(?![\u0600-\u06FF])"), "چ\u200cت"),
]


def _anti_jagh_prepare(s: str):
    """متن رو نرمال می‌کنه (NFKC، حذف علامت ترکیبی/تطویل/ZWNJ، ك→ک، حروف کوچک)،
    جداکننده‌ها (فاصله . / * - _ ...) رو بین حرف‌ها برمی‌داره تا «س ک س» و
    «ب**/یو» هم گرفته بشن، و برای هر حرفِ باقی‌مانده نگه می‌داره که «اولِ کلمه»
    هست یا نه (حرف قبلیش توی متن اصلی جداکننده/غیرحرف بوده یا نه)."""
    s = _anti_khale_clean(s or "").lower()
    out, starts, prev_word = [], [], False
    for ch in s:
        if _ANTI_KHALE_SEP_RE.fullmatch(ch):
            prev_word = False
            continue
        out.append(ch)
        starts.append(not prev_word)
        prev_word = ch.isalnum()
    return "".join(out), starts


def _ac_build(pairs):
    """Builds an Aho-Corasick automaton from (pattern, value) pairs.
    Duplicate patterns keep the first value. Returns None if empty."""
    ac = ahocorasick.Automaton()
    for pat, val in pairs:
        if pat and pat not in ac:
            ac.add_word(pat, val)
    if len(ac) == 0:
        return None
    ac.make_automaton()
    return ac


_ANTI_JAGH_SUB_INDEX = []
_seen_aj = set()
for _w in ANTI_JAGH_SUBSTRING_WORDS:
    _wd = _anti_jagh_prepare(_w)[0]
    if _wd and _wd not in _seen_aj:
        _seen_aj.add(_wd)
        _ANTI_JAGH_SUB_INDEX.append((_wd, _w))
del _seen_aj
_ANTI_JAGH_AC = _ac_build((p, (o, len(p))) for p, o in _ANTI_JAGH_SUB_INDEX) if ahocorasick else None
_ANTI_KHALE_AC = _ac_build(_ANTI_KHALE_INDEX) if ahocorasick else None


def _anti_jagh_match(text: str):
    """Returns the matched word if the anti-jagh filter should delete this
    message, else None. Substring list matches anywhere (space/ZWNJ
    insensitive); prefix list only matches at the very start of the
    message and only if not glued to another letter right after it."""
    if not text:
        return None

    for _pat, _orig in _ANTI_JAGH_OBFUSCATED_RES:
        if _pat.search(text):
            return _orig

    despaced, starts = _anti_jagh_prepare(text)
    n = len(despaced)

    def _ok(pat, st):
        # فقط اولِ کلمه؛ کلمه‌های خیلی کوتاه (۲ حرف یا کمتر) باید کامل و
        # بدون چسبیدن به حرفِ بعدی هم باشن. ایموجی/غیرحرف مرز نمی‌خواد.
        if pat[0].isalnum() and not starts[st]:
            return False
        if len(pat) <= 2 and pat[-1].isalnum():
            en = st + len(pat)
            if en < n and not starts[en]:
                return False
        return True

    if _ANTI_JAGH_AC is not None:
        for _end, (orig, plen) in _ANTI_JAGH_AC.iter(despaced):
            if _ok(despaced[_end - plen + 1:_end + 1], _end - plen + 1):
                return orig
    else:
        for wd, orig in _ANTI_JAGH_SUB_INDEX:
            i = despaced.find(wd)
            while i != -1:
                if _ok(wd, i):
                    return orig
                i = despaced.find(wd, i + 1)

    stripped = _ANTI_JAGH_INVISIBLE_RE.sub("", text or "").lstrip()
    stripped_lower = stripped.lower()
    for w in ANTI_JAGH_PREFIX_WORDS:
        wl = w.lower()
        if stripped_lower.startswith(wl):
            next_ch = stripped[len(wl):len(wl) + 1]
            if not next_ch or not _FA_LETTER_RE.match(next_ch):
                return w
    return None


_WORD_FILTER_CACHE: dict = {}


def _word_filter_hit(chat_id, words, text: str) -> bool:
    """True اگر یکی از کلمه‌های فیلتر (بدون حساسیت به حروف بزرگ/کوچک) جایی از متن باشد."""
    if not words or not text:
        return False
    text_l = text.lower()
    if ahocorasick is None:
        return any(w and w.lower() in text_l for w in words)
    key = tuple(words)
    ent = _WORD_FILTER_CACHE.get(chat_id)
    if ent is None or ent[0] != key:
        ent = (key, _ac_build((w.lower(), w) for w in words if w))
        _WORD_FILTER_CACHE[chat_id] = ent
    ac = ent[1]
    if ac is None:
        return False
    for _ in ac.iter(text_l):
        return True
    return False


_AD_STRIP_RE = re.compile(r"[\u0640\u200b-\u200f\u2060\ufeff\u064b-\u065f\u0670]")
_AD_CHAR_MAP = _FA_CHAR_MAP
_AD_LETTERS = r"A-Za-z\u0621-\u063f\u0641-\u064a\u0671-\u06d3\u06fa-\u06ff"
_AD_SEP = r"[\s.]*"
_AD_RULES: list = []


def _ad_add_rule(label: str, word: str, *, flex: bool, standalone: bool) -> None:
    word = word.replace(" ", "")
    body = _AD_SEP.join(re.escape(ch) for ch in word) if flex else re.escape(word)
    if standalone:
        body = rf"(?<![{_AD_LETTERS}]){body}(?![{_AD_LETTERS}])"
    _AD_RULES.append((label, re.compile(body)))


_ad_add_rule("بیو", "بیو", flex=False, standalone=True)
_ad_add_rule("چک", "چک", flex=True, standalone=True)
_ad_add_rule("بیوم", "بیوم", flex=False, standalone=False)
_ad_add_rule("گپم", "گپم", flex=False, standalone=False)
_ad_add_rule("چنل", "چنل", flex=True, standalone=False)
_ad_add_rule("زیر پروفم", "زیر پروفم", flex=True, standalone=False)
_ad_add_rule("ممبر میزنم", "ممبر میزنم", flex=True, standalone=False)
_ad_add_rule("بیو چک", "بیو چک", flex=True, standalone=False)

AD_LOCK_MAX_HITS = 3
ad_tracker: dict = {}
ad_cooldown: dict = {}


def _ad_match(text: str):
    """اگر پیام تبلیغاتی باشد عبارت تطبیق‌یافته را برمی‌گرداند، وگرنه None."""
    if not text:
        return None
    t = _AD_STRIP_RE.sub("", text).translate(_AD_CHAR_MAP)
    for label, rx in _AD_RULES:
        if rx.search(t):
            return label
    return None


bio_flagged_users_memory: dict = {}


anti_khale_flagged_memory: dict = {}


member_stealer_flagged_memory: dict = {}

member_stealer_msg_cache: dict = {}
MEMBER_STEALER_CACHE_SECONDS = 5.0


def _event_send_ts(event) -> float:
    """Real timestamp the message was actually sent at (not when we got
    around to processing it). Falls back to 'now' if unavailable.
    This matters a lot right after startup/reconnect: the client can
    deliver a big backlog of missed messages within a split second of
    wall-clock processing time, even though users sent them minutes or
    hours apart in real life. Any 'N messages within X seconds' check
    must be measured against the message's own date, or a burst of
    normal backlog traffic looks identical to real flooding.

    BUG FIX: در این کتابخانه (spluspy) فیلد `date` روی بعضی ایونت‌ها
    یک عدد (Unix timestamp به ثانیه) است، نه یک شیء datetime. قبلاً کد
    فقط `d.timestamp()` را صدا می‌زد که روی int/float ارور می‌داد،
    این ارور بی‌سروصدا قورت داده می‌شد (`except: pass`) و در نتیجه به
    ساعتِ سیستمِ همین سرور (که می‌تواند چند ماه جلو/عقب باشد) سقوط
    می‌کرد - همان چیزی که باعث می‌شد مثلاً «سکوت ۱۰ دقیقه» عملاً
    برای چند ماه ثبت شود. حالا اگر عدد باشد مستقیم همان را برمی‌گردانیم."""
    msg = getattr(event, 'message', None)
    d = getattr(event, 'date', None) or (getattr(msg, 'date', None) if msg is not None else None)
    if d is not None:
        if isinstance(d, (int, float)):
            return float(d)
        try:
            return d.timestamp()
        except Exception:
            pass
    _log(
        "⚠️ نتونستم زمان واقعی ارسال پیام را از خودِ ایونت بخونم؛ موقتاً از "
        "ساعت سیستم سرور استفاده می‌شود - اگر ساعت سرور اشتباه باشد، مدت "
        "سکوت/بن زمان‌دار هم اشتباه محاسبه خواهد شد. لطفاً `date` را روی "
        "سرور چک کن."
    )
    return datetime.now(timezone.utc).timestamp()


def _accurate_now(event) -> datetime:
    """Authoritative 'now' for computing timed-mute/ban expirations.
    Uses the triggering message's own server timestamp (set by SoroushPlus,
    not by this VPS) whenever it's available, so mute durations stay correct
    even if this server's own system clock is wrong - a wrong local clock
    used to make e.g. a 10-minute mute actually last for months, because
    the expiry was computed from the wrong 'now'."""
    try:
        return datetime.fromtimestamp(_event_send_ts(event), tz=timezone.utc)
    except Exception:
        return check_system_clock_sanity()


def _member_stealer_cache_track(chat_id, user_id, msg_id, send_ts: float = None) -> None:
    """Keep a short rolling cache (like the spam lock's queue) of each
    user's recent message ids per chat, so that once they're flagged we
    can wipe everything they sent in the last few seconds - not just the
    single message that tripped the check."""
    if not msg_id:
        return
    now_ts = datetime.now(timezone.utc).timestamp()
    track_ts = send_ts if send_ts is not None else now_ts
    key = (chat_id, user_id)
    q = member_stealer_msg_cache.setdefault(key, [])
    q.append((track_ts, msg_id))
    while q and now_ts - q[0][0] > MEMBER_STEALER_CACHE_SECONDS:
        q.pop(0)


def _member_stealer_cache_pop(chat_id, user_id) -> list:
    """Pop and return the still-fresh (within the window) message ids
    cached for this user, clearing their cache entry."""
    now_ts = datetime.now(timezone.utc).timestamp()
    key = (chat_id, user_id)
    q = member_stealer_msg_cache.pop(key, [])
    return [mid for ts, mid in q if now_ts - ts <= MEMBER_STEALER_CACHE_SECONDS]

_recent_join_checks: dict = {}
_RECENT_JOIN_TTL_SECONDS = 5


def _mark_join_seen_recently(chat_id, user_id) -> bool:
    now = datetime.now(timezone.utc).timestamp()
    key = (chat_id, user_id)
    last = _recent_join_checks.get(key)
    _recent_join_checks[key] = now
    if len(_recent_join_checks) > 5000:
        cutoff = now - _RECENT_JOIN_TTL_SECONDS
        for k, t in list(_recent_join_checks.items()):
            if t < cutoff:
                _recent_join_checks.pop(k, None)
    return last is not None and (now - last) < _RECENT_JOIN_TTL_SECONDS


_UpdateChannelParticipant = None


def _get_update_channel_participant_cls():
    global _UpdateChannelParticipant
    if _UpdateChannelParticipant is not None:
        return _UpdateChannelParticipant
    for modpath in ("spluspy.tl.types",):
        try:
            mod = __import__(modpath, fromlist=["UpdateChannelParticipant"])
            cls = getattr(mod, "UpdateChannelParticipant", None)
            if cls:
                _UpdateChannelParticipant = cls
                return cls
        except ImportError:
            continue
    return None


cleanup_task = None

try:
    client = Client(SESSION_NAME, auto_reconnect=True, connection_retries=None, retry_delay=1,
                    sequential_updates=False, entity_cache_limit=200000)
except TypeError:
    try:
        client = Client(SESSION_NAME, auto_reconnect=True, connection_retries=None, retry_delay=1)
    except TypeError:
        client = Client(
            SESSION_NAME, api_id=1030400, api_hash="6edb16cf88714a4e9a805e928c39c937",
            auto_reconnect=True, connection_retries=None, retry_delay=1,
        )


_BG_TASKS: set = set()


def _spawn(coro, name: str = "task"):
    task = asyncio.ensure_future(coro)
    _BG_TASKS.add(task)

    def _done(t):
        _BG_TASKS.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            _log(f"⚠️ [{name}] error: {exc!r}")

    task.add_done_callback(_done)
    return task


_RAW_ON_MESSAGE = client.on_message

# هندلرهای سرگرمی؛ وقتی «سرگرمی خاموش» باشد برای غیرمدیران بی‌صدا نادیده گرفته می‌شوند
FUN_HANDLER_NAMES = frozenset({
    "ship_commands_handler", "challenge_handler", "joke_handler", "fact_handler",
    "hafez_handler", "fact200_handler", "dice_handler", "guess_number_handler",
    "rock_paper_scissors_handler", "scramble_word_handler", "duel_handler",
    "tictactoe_handler", "math_quiz_handler", "emoji_odd_handler",
    "slot_machine_handler", "roulette_handler", "quiz_handler",
    "code_breaker_handler", "hidden_word_handler", "time_now_handler",
    "voice_make_handler", "translate_handler", "weather_handler",
    "wiki_city_handler", "wiki_search_handler", "robot_roast_handler",
})


def _fun_blocked(event, func_name: str) -> bool:
    if func_name not in FUN_HANDLER_NAMES or getattr(event, 'is_private', False):
        return False
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id:
        return False
    chat = get_chat_cfg(chat_id)
    if chat.get("fun_enabled", True):
        return False
    return not (sender_id and is_admin(chat, sender_id))


def _gated_on_message(*deco_args, **deco_kwargs):
    raw_decorator = _RAW_ON_MESSAGE(*deco_args, **deco_kwargs)

    def _apply(func):
        async def _gated_func(_client, event):
            try:
                if not getattr(event, 'is_private', False):
                    chat_id = getattr(event, 'chat_id', None)
                    if chat_id and not is_chat_active(chat_id):
                        return
                if _fun_blocked(event, getattr(func, '__name__', '')):
                    return
            except Exception:
                pass
            _spawn(func(_client, event), getattr(func, '__name__', 'handler'))
        _gated_func.__name__ = getattr(func, '__name__', '_gated_func')
        return raw_decorator(_gated_func)

    return _apply


client.on_message = _gated_on_message

_RAW_ON_EDITED_MESSAGE = client.on_edited_message
_RAW_ON_CHAT_ACTION = client.on_chat_action


def _make_gated(raw_attr_getter):
    def _gated(*deco_args, **deco_kwargs):
        raw_decorator = raw_attr_getter(*deco_args, **deco_kwargs)

        def _apply(func):
            async def _gated_func(_client, event):
                try:
                    if not getattr(event, 'is_private', False):
                        chat_id = getattr(event, 'chat_id', None)
                        if chat_id and not is_chat_active(chat_id):
                            return
                except Exception:
                    pass
                _spawn(func(_client, event), getattr(func, '__name__', 'handler'))
            _gated_func.__name__ = getattr(func, '__name__', '_gated_func')
            return raw_decorator(_gated_func)

        return _apply
    return _gated


client.on_edited_message = _make_gated(_RAW_ON_EDITED_MESSAGE)
client.on_chat_action = _make_gated(_RAW_ON_CHAT_ACTION)


def extract_bio(full_user_obj) -> str:
    if not full_user_obj:
        return ""
    for attr in ('about', 'bio'):
        val = getattr(full_user_obj, attr, None)
        if val:
            return str(val)
    for inner_name in ('full_user', 'user'):
        inner = getattr(full_user_obj, inner_name, None)
        if inner:
            for attr in ('about', 'bio'):
                val = getattr(inner, attr, None)
                if val:
                    return str(val)
    return ""

_bio_cache: dict = {}
_BIO_CACHE_TTL = 120
_bio_inflight: dict = {}

ANTI_KHALE_CLEAN_CACHE_TTL = 0
anti_khale_clean_checked: dict = {}


_pchan_info: dict = {}
_pchan_text_cache: dict = {}
_PCHAN_TEXT_TTL = 60
_PCHAN_MSG_LIMIT = 5


def extract_personal_channel(full_user_obj):
    """(آی‌دی کانال, entity یا None) کانالِ داخل پروفایل کاربر (قسمت «کانال»)،
    یا None اگه نداشت. بدون جوین؛ entity از لیست chats خود پاسخ برمی‌داریم."""
    if not full_user_obj:
        return None
    cid = None
    for obj in (full_user_obj, getattr(full_user_obj, 'full_user', None)):
        if obj is None:
            continue
        v = getattr(obj, 'personal_channel_id', None)
        if v:
            cid = v
            break
    if not cid:
        return None
    ent = None
    for ch in (getattr(full_user_obj, 'chats', None) or []):
        if getattr(ch, 'id', None) == cid:
            ent = ch
            break
    return (cid, ent)


def _extract_chat_about(full_obj) -> str:
    if not full_obj:
        return ""
    for obj in (full_obj, getattr(full_obj, 'full_chat', None), getattr(full_obj, 'chat', None)):
        if obj is None:
            continue
        for attr in ('about', 'description', 'bio'):
            val = getattr(obj, attr, None)
            if val:
                return str(val)
    return ""


_BAD_EXTS = ('.apk', '.zip', '.rar')
_BAD_EXT_TEXT_RE = re.compile(r'\.(?:apk|zip|rar)(?:$|[\s?#/)\]"\'»،.])', re.IGNORECASE)


def _msg_has_apk(m) -> bool:
    """پیام فایل با پسوند apk یا zip یا rar داره؟ (فایل پیوست، یا لینک مستقیم)"""
    try:
        f = getattr(m, 'file', None)
        if f is not None:
            name = str(getattr(f, 'name', None) or '').lower()
            ext = str(getattr(f, 'ext', None) or '').lower()
            if name.endswith(_BAD_EXTS) or ext in _BAD_EXTS:
                return True
    except Exception:
        pass
    try:
        doc = getattr(m, 'document', None)
        if doc is None:
            media = getattr(m, 'media', None)
            doc = getattr(media, 'document', None) if media is not None else None
        if doc is not None:
            for at in (getattr(doc, 'attributes', None) or []):
                fn = getattr(at, 'file_name', None)
                if fn and str(fn).lower().endswith(_BAD_EXTS):
                    return True
    except Exception:
        pass
    try:
        t = getattr(m, 'message', None) or getattr(m, 'text', None) or getattr(m, 'raw_text', None) or ''
        if t and _BAD_EXT_TEXT_RE.search(str(t)):
            return True
        for en in (getattr(m, 'entities', None) or []):
            u = getattr(en, 'url', None)
            if u and _BAD_EXT_TEXT_RE.search(str(u)):
                return True
    except Exception:
        pass
    return False


async def _pchan_collect_text(cid, ent):
    """(متنِ کانالِ پروفایل، آیا توی ۵ پست آخر فایل apk/zip/rar بود) بدون جوین."""
    has_apk = False
    if ent is None:
        try:
            ent = await client.get_entity(cid)
        except Exception as e:
            _log(f"⚠️ personal-channel get_entity failed ({cid}): {e}")
            return "", False
    parts = []
    title = getattr(ent, 'title', None)
    if title:
        parts.append(str(title))
    try:
        full = await asyncio.wait_for(client.get_chat(ent), timeout=8)
        about = _extract_chat_about(full)
        if about:
            parts.append(about)
    except Exception as e:
        _log(f"⚠️ personal-channel about failed ({cid}): {e}")
    try:
        msgs = await asyncio.wait_for(client.get_messages(ent, limit=_PCHAN_MSG_LIMIT), timeout=8)
        if msgs is not None and not isinstance(msgs, (list, tuple)):
            msgs = [msgs]
        for m in (msgs or []):
            if _msg_has_apk(m):
                has_apk = True
            t = getattr(m, 'message', None) or getattr(m, 'text', None) or getattr(m, 'raw_text', None)
            if t:
                parts.append(str(t))
            for en in (getattr(m, 'entities', None) or []):
                u = getattr(en, 'url', None)
                if u:
                    parts.append(str(u))
    except Exception as e:
        _log(f"⚠️ personal-channel messages failed ({cid}): {e}")
    return "\n".join(parts), has_apk


async def _channel_reason(cid, ent, chat_id, where: str):
    """چک مشترکِ یه کانال (بدون جوین): فایل apk/zip/rar توی ۵ پست آخر، یا
    لینک/آیدیِ گروهِ دیگه توی متن/توضیحات/پست‌ها. دلیل (متن) یا None."""
    now = datetime.now(timezone.utc).timestamp()
    hit = _pchan_text_cache.get(cid)
    if hit and now - hit[0] < _PCHAN_TEXT_TTL:
        text, has_apk = hit[1], hit[2]
    else:
        text, has_apk = await _pchan_collect_text(cid, ent)
        if len(_pchan_text_cache) > 2000:
            _pchan_text_cache.clear()
        _pchan_text_cache[cid] = (now, text, has_apk)
    if has_apk:
        return f"فایل APK/ZIP/RAR (احتمال ویروس) توی {where} شناسایی شد."
    if text and await bio_foreign_group_reason(text, chat_id):
        return f"لینک/آیدی گروه در {where} شناسایی شد."
    return None


async def personal_channel_group_reason(user_id, chat_id):
    """کانالِ قسمت «کانال» پروفایل کاربر رو بدون جوین چک می‌کنه."""
    info = _pchan_info.get(user_id)
    if not info:
        return None
    cid, ent = info
    return await _channel_reason(cid, ent, chat_id, "کانالِ پروفایل")


_BIO_CHAN_ENT_CACHE: dict = {}


async def _bio_channel_entity(ident: str):
    """entity یه «کانالِ خالص» (نه گروه) از لینک splus.ir/... یا @یوزرنیم؛ وگرنه None."""
    key = ident.lower()
    now = datetime.now(timezone.utc).timestamp()
    hit = _BIO_CHAN_ENT_CACHE.get(key)
    if hit and now - hit[0] < _BIO_TARGET_CACHE_TTL:
        return hit[1]
    ent = None
    for cand in (ident, '@' + ident):
        try:
            ent = await client.get_entity(cand)
            break
        except Exception:
            continue
    if ent is not None:
        is_pure_channel = (getattr(ent, 'broadcast', False) is True
                           and getattr(ent, 'megagroup', False) is not True)
        if not is_pure_channel:
            ent = None
    if len(_BIO_CHAN_ENT_CACHE) > 3000:
        _BIO_CHAN_ENT_CACHE.clear()
    _BIO_CHAN_ENT_CACHE[key] = (now, ent)
    return ent


async def bio_channel_reason(bio: str, chat_id):
    """کانال‌های عمومیِ داخل بیو (لینک splus.ir/... یا @یوزرنیم) رو بدون جوین چک
    می‌کنه: ۵ پست آخر apk/zip/rar یا لینک/آیدی گروه داشت دلیل برمی‌گردونه."""
    if not bio:
        return None
    idents = []
    if "splus.ir" in bio.lower():
        for m in MEMBER_STEALER_LINK_RE.finditer(bio):
            ident = m.group(1).strip('/')
            if not ident or INVITE_PATH_RE.match(ident) or ident.startswith('+') or _is_non_group_path(ident):
                continue
            ident = ident.split('/')[0]
            if ident and ident not in idents:
                idents.append(ident)
            if len(idents) >= _BIO_MAX_LINKS:
                break
    if "@" in bio:
        n = 0
        for m in MEMBER_STEALER_MENTION_RE.finditer(bio):
            u = m.group(1)
            if u not in idents:
                idents.append(u)
                n += 1
            if n >= _BIO_MAX_MENTIONS:
                break
    if not idents:
        return None

    async def _one(ident):
        try:
            ent = await _bio_channel_entity(ident)
            if ent is None:
                return None
            cid = getattr(ent, 'id', None)
            if not cid:
                return None
            return await _channel_reason(cid, ent, chat_id, "کانالِ لینک‌شده در بیو")
        except Exception as e:
            _log(f"⚠️ bio-channel check failed ({ident}): {e}")
            return None

    results = await asyncio.gather(*(_one(i) for i in idents))
    for r in results:
        if r:
            return r
    return None


async def _bio_fetch(user_id) -> str:
    full_user = await client.get_full_user(user_id)
    try:
        pc = extract_personal_channel(full_user)
    except Exception:
        pc = None
    if pc:
        _pchan_info[user_id] = pc
    else:
        _pchan_info.pop(user_id, None)
    bio = extract_bio(full_user)
    _bio_cache[user_id] = (datetime.now(timezone.utc).timestamp(), bio)
    return bio


def _bio_fetch_done(user_id, task) -> None:
    if _bio_inflight.get(user_id) is task:
        _bio_inflight.pop(user_id, None)
    if not task.cancelled():
        task.exception()


async def get_bio_cached(user_id, force_fresh: bool = False) -> str:
    if not force_fresh:
        now = datetime.now(timezone.utc).timestamp()
        cached = _bio_cache.get(user_id)
        if cached and now - cached[0] < _BIO_CACHE_TTL:
            return cached[1]
    task = _bio_inflight.get(user_id)
    if task is None:
        task = asyncio.ensure_future(_bio_fetch(user_id))
        _bio_inflight[user_id] = task
        task.add_done_callback(lambda t, uid=user_id: _bio_fetch_done(uid, t))
    return await asyncio.shield(task)


def _discard_task(t) -> None:
    if t is None:
        return
    if not t.done():
        t.cancel()
    elif not t.cancelled():
        t.exception()


MEMBER_STEALER_LINK_RE = re.compile(r'(?:https?://)?splus\.ir/([\w+\-/]+)', re.IGNORECASE)
INVITE_PATH_RE = re.compile(r'^(?:joingroup|joinchat)/(.+)$', re.IGNORECASE)
_NON_GROUP_PATHS = ('meet',)


def _is_non_group_path(ident: str) -> bool:
    """لینک‌هایی مثل splus.ir/meet/xxx (میت/ویس‌چت) گروه نیستن؛ «meet» یوزرنیم نیست."""
    return ident.split('/')[0].lower() in _NON_GROUP_PATHS

_CheckChatInviteRequest = None

def _get_check_chat_invite_request():
    global _CheckChatInviteRequest
    if _CheckChatInviteRequest is not None:
        return _CheckChatInviteRequest
    for modpath in (
        "spluspy.tl.functions.messages",
        "spluspy.functions.messages",
        "spluspy.tl.functions",
        "spluspy.functions",
    ):
        try:
            mod = __import__(modpath, fromlist=["CheckChatInviteRequest"])
            cls = getattr(mod, "CheckChatInviteRequest", None)
            if cls:
                _CheckChatInviteRequest = cls
                return cls
        except ImportError:
            continue
    return None

MEMBER_STEALER_MENTION_RE = re.compile(r'(?<![\w@/.])@([A-Za-z][A-Za-z0-9_]{3,31})(?![\w@])')
_BIO_TARGET_CACHE: dict = {}
_BIO_TARGET_CACHE_TTL = 3600
_BIO_MAX_LINKS = 3
_BIO_MAX_MENTIONS = 3


def _raw_chat_id(chat_id) -> int:
    """آی‌دیِ «مارک‌شده‌ی» چت (مثل -100123...) رو به آی‌دیِ خام برمی‌گردونه تا با
    entity.id قابل مقایسه باشه."""
    cid = int(chat_id)
    if cid >= 0:
        return cid
    s = str(-cid)
    if s.startswith("100") and len(s) > 12:
        return int(s[3:])
    return -cid


def _target_info(entity):
    """(گروهه؟, آی‌دی خام یا None) از یه entity/chat. کانالِ خالص گروه حساب نمی‌شه."""
    is_broadcast = getattr(entity, 'broadcast', False) is True
    is_megagroup = getattr(entity, 'megagroup', False) is True
    raw_id = getattr(entity, 'id', None)
    return (not (is_broadcast and not is_megagroup)), raw_id


async def _resolve_invite_hash(invite_hash: str):
    """(گروهه؟, آی‌دی خام یا None). ربات عضوِ گروهِ لینک باشه آی‌دی برمی‌گرده
    (ChatInviteAlready)، وگرنه None. خطا: برای احتیاط «گروه» با آی‌دی نامعلوم."""
    key = ("inv", invite_hash)
    now = datetime.now(timezone.utc).timestamp()
    hit = _BIO_TARGET_CACHE.get(key)
    if hit and now - hit[0] < _BIO_TARGET_CACHE_TTL:
        return hit[1]
    cls = _get_check_chat_invite_request()
    if not cls:
        _log("⚠️ CheckChatInviteRequest در کتابخانه پیدا نشد؛ لینک دعوت خصوصی برای احتیاط «گروه» در نظر گرفته شد.")
        return (True, None)
    try:
        result = await client(cls(invite_hash))
    except Exception as e:
        _log(f"⚠️ _resolve_invite_hash: CheckChatInviteRequest failed for '{invite_hash}': {e}")
        return (True, None)
    inner = getattr(result, 'chat', None)
    info = _target_info(inner) if inner is not None else (_target_info(result)[0], None)
    if len(_BIO_TARGET_CACHE) > 3000:
        _BIO_TARGET_CACHE.clear()
    _BIO_TARGET_CACHE[key] = (now, info)
    return info


async def _resolve_username(username: str, tolerant: bool):
    """(گروهه؟, آی‌دی خام یا None). tolerant=True (لینک splus.ir/یوزرنیم): اگه
    resolve نشد «گروه» فرض می‌شه؛ tolerant=False (@ خالی): اگه resolve نشد گروه
    نیست تا آدم عادی اشتباهی گرفته نشه. برای @ خالی فقط megagroup گروه حساب می‌شه."""
    key = ("usr", username.lower(), tolerant)
    now = datetime.now(timezone.utc).timestamp()
    hit = _BIO_TARGET_CACHE.get(key)
    if hit and now - hit[0] < _BIO_TARGET_CACHE_TTL:
        return hit[1]
    entity = None
    last_err = None
    for candidate in (username, '@' + username):
        try:
            entity = await client.get_entity(candidate)
            break
        except Exception as e:
            last_err = e
            continue
    if entity is None:
        _log(f"⚠️ _resolve_username: get_entity('{username}') شکست خورد: {last_err}")
        return (True, None) if tolerant else (False, None)
    if tolerant:
        info = _target_info(entity)
    else:
        info = (getattr(entity, 'megagroup', False) is True, getattr(entity, 'id', None))
    if len(_BIO_TARGET_CACHE) > 3000:
        _BIO_TARGET_CACHE.clear()
    _BIO_TARGET_CACHE[key] = (now, info)
    return info


async def bio_foreign_group_reason(bio: str, chat_id):
    """اگه بیو لینک/@ِ یه گروهِ «غیر از همین گروه» داشته باشه دلیلش (متن) رو
    برمی‌گردونه، وگرنه None. لینک/آیدیِ خودِ همین گروه نادیده گرفته می‌شه؛ ولی
    اگه کنارش گروهِ دیگه‌ای هم باشه همون گروهِ دیگه می‌گیره."""
    if not bio:
        return None
    low = bio.lower()
    this_raw = _raw_chat_id(chat_id)

    def _foreign(info):
        is_group, raw_id = info
        return bool(is_group) and raw_id != this_raw

    if "splus.ir" in low:
        seen = []
        for m in MEMBER_STEALER_LINK_RE.finditer(bio):
            ident = m.group(1).strip('/')
            if not ident or _is_non_group_path(ident):
                continue
            if ident not in seen:
                seen.append(ident)
            if len(seen) >= _BIO_MAX_LINKS:
                break
        for ident in seen:
            invite_m = INVITE_PATH_RE.match(ident)
            invite_hash = invite_m.group(1) if invite_m else (ident[1:] if ident.startswith('+') else None)
            if invite_hash:
                info = await _resolve_invite_hash(invite_hash)
            else:
                info = await _resolve_username(ident.split('/')[0], tolerant=True)
            if _foreign(info):
                return "لینک دعوت گروه در بیو شناسایی شد."

    if "@" in bio:
        seen = []
        for m in MEMBER_STEALER_MENTION_RE.finditer(bio):
            u = m.group(1).lower()
            if u not in seen:
                seen.append(u)
            if len(seen) >= _BIO_MAX_MENTIONS:
                break
        for u in seen:
            if _foreign(await _resolve_username(u, tolerant=False)):
                return "آیدی گروه در بیو شناسایی شد."
    return None


def _utf16_len(s: str) -> int:
    """Message-entity offsets/lengths are counted in UTF-16 code units,
    not characters - same as Telegram's own protocol."""
    return len(s.encode('utf-16-le')) // 2


def display_name_for(user, user_id):
    """Plain visible text for a user - just the name (plus a small
    username/id hint), no link syntax. The tappable part is a real entity
    added by build_mention(), since Soroush's client renders
    [text](tg://user?id=..) markdown links as plain text, not a tappable
    mention - only an actual MessageEntityMentionName entity opens the
    profile like Telegram does.

    The real name is always shown when it exists - even for users who
    have a username - since it looks nicer than a bare "@username" and
    the mention entity works off the numeric id anyway, not the username."""
    fname = getattr(user, 'first_name', '') or ''
    lname = getattr(user, 'last_name', '') or ''
    username = getattr(user, 'username', None)
    name = f"{fname} {lname}".strip()
    if name:
        return name
    if username:
        return f"@{username}"
    return f"کاربر {user_id}"


async def _get_input_user(user_id):
    """Resolves a full InputUser (carries the access_hash a mention entity
    needs) for `user_id`. Tries a few routes since it's unclear which
    helper spluspy exposes for this under the hood."""
    try:
        peer = await client.get_input_entity(user_id)
    except Exception:
        peer = None

    if _TLInputUser is not None and isinstance(peer, _TLInputUser):
        return peer

    if _spluspy_utils is not None and hasattr(_spluspy_utils, 'get_input_user'):
        try:
            return _spluspy_utils.get_input_user(peer if peer is not None else user_id)
        except Exception:
            pass

    access_hash = getattr(peer, 'access_hash', None)
    if access_hash is None:
        try:
            user = await client.get_entity(user_id)
            access_hash = getattr(user, 'access_hash', None)
        except Exception:
            access_hash = None

    if access_hash is not None and _TLInputUser is not None:
        return _TLInputUser(user_id=user_id, access_hash=access_hash)

    return None


MENTION_LABEL = "﹝مشاهده نمایه﹞"


async def build_mention(user_id, user=None, label: str = None):
    """Returns (visible_text, entity) for a real tappable mention of
    user_id. `entity` has offset=0 - callers must shift it to wherever the
    text lands inside their final message (MentionTextBuilder does this
    automatically). `entity` is None if an InputUser couldn't be resolved,
    in which case the text is still shown, just not tappable.
    The visible text is MENTION_LABEL for every tag in the bot, unless
    `label` is given. The tappable entity/profile-link behavior is
    identical either way. (If no tappable entity could be built, the
    user's name/id is shown instead so the message still says who.)"""
    if user is None:
        try:
            user = await client.get_entity(user_id)
        except Exception:
            user = None
    name_text = display_name_for(user, user_id) if user is not None else f"کاربر {user_id}"
    text = label if label is not None else MENTION_LABEL
    mention_span = text[:text.rfind(" (")] if text.endswith(")") and " (" in text else text

    entity = None
    if InputMessageEntityMentionName is not None:
        input_user = None
        direct_access_hash = getattr(user, 'access_hash', None) if user is not None else None
        if direct_access_hash is not None and _TLInputUser is not None:
            input_user = _TLInputUser(user_id=user_id, access_hash=direct_access_hash)
        if input_user is None:
            input_user = await _get_input_user(user_id)
        if input_user is not None:
            entity = InputMessageEntityMentionName(
                offset=0, length=_utf16_len(mention_span), user_id=input_user
            )
    if entity is None and label is None:
        text = name_text
    return text, entity


class MentionTextBuilder:
    """Assembles a message out of plain-text chunks, user mentions, and
    monospace spans, while keeping every entity's UTF-16 offset correct
    inside the final combined text. Needed because a message can carry
    several real entities (mention + code spans) at once, and each one's
    offset depends on everything written before it."""

    def __init__(self):
        self._parts = []
        self._entities = []
        self._length = 0

    def text(self, chunk: str):
        self._parts.append(chunk)
        self._length += _utf16_len(chunk)
        return self

    def code(self, chunk: str):
        if MessageEntityCode is not None:
            self._entities.append(MessageEntityCode(offset=self._length, length=_utf16_len(chunk)))
        self.text(chunk)
        return self

    async def mention(self, user_id, user=None, label: str = None):
        mention_text, entity = await build_mention(user_id, user, label=label)
        if entity is not None:
            entity.offset = self._length
            self._entities.append(entity)
        self.text(mention_text)
        return self

    def build(self):
        return "".join(self._parts), (self._entities or None)


def _short_tag_name(name: str, max_len: int = 14) -> str:
    """اسمِ نمایشیِ تگ رو کوتاه می‌کنه اگه طولانی باشه - اول فقط کلمه‌ی اول،
    و اگه اون هم طولانی بود، max_len حرفِ اولش + «…»."""
    name = (name or "").strip()
    if len(name) <= max_len:
        return name
    first_word = name.split()[0] if name.split() else name
    if len(first_word) <= max_len:
        return first_word
    return first_word[:max_len].rstrip() + "…"


TAG_ALL_PHRASES = [
    "بیدار شو تا زنتو نگاییدم {تگ} ",
    "بیا چت کنیم {تگ} ",
    "کجایی؟ داری با کی چت می‌کنی 🗿 {تگ}",
    "بیا گپ پشمک {تگ} ",
    "هوی با توام  {تگ} ",
    " ک.صکش بیا گپ {تگ} ",
    "خجالتی نباش بیا 🗿 {تگ}",
    "هوی بیا دستمال کش بیا گپ {تگ} ",
    "کجایی پس تو پاچید {تگ} ",
    "یه سلام به ما هم بده {تگ} ",
    "چرا ساکتی هوی {تگ}؟ ",
    "بیا یه چیزی بگو {تگ} ",
    "تخم داری پیام بده {تگ}؟ ",
    "گمشو بیا نیومدم {تگ} ",
    "میای یا بیام {تگ}؟ ",
    "دلم هوا تو کرده 🤤 {تگ} ",
    "دلمون تنگ شده بیا یه ک.ون بده 🥹 {تگ} ",
    "داری به کی ک.ون میدی {تگ} ",
    "دکمه تو بزن بیا {تگ} ",
    "کجایی عشقم {تگ}؟ ",
    "بیا دیگه با توام تخمی {تگ} ",
    "بیا بریم پشت, گپ {تگ} ",
    "بریم حموم بزنیم ج.ق {تگ} ",
    "تنها موندیم بدون تو {تگ} ",
    "بیا یه خبری از خودت بده {تگ} ",
    "زنده ایییی {تگ}؟ ",
    "بیا غرشش بده س.کسی {تگ} ",
    "لبو بده بیاد {تگ} ",
    "میدی یا بکنم {تگ} ",
    "لب یا ک.ون {تگ}؟ ",
    "بپر بقلم عمو {تگ} ",
    "خوابه خوابه🤤 {تگ} ",
    "بیا گلم {تگ} ",
    "پیدات نیست {تگ} ",
    "م.مه میقام {تگ} ",
    "دیر اومدی ولی بیا {تگ} ",
    "عجقم کجایی {تگ} ",
    "نرو رو اعصابم {تگ}؟ ",
    "ک.یری فازشو دارم {تگ} ",
    "بیا چربش کنیم {تگ} ",
    "بیا فعالیت کن {تگ} ",
    "چرا فراری هستی از گپ {تگ}؟ ",
    "بیا یه پیام بده {تگ} ",
    "کجایی این‌همه وقت {تگ}؟ ",
    "ثروت بهتره یا م.مه {تگ} ",
    "دل عمو رو نشکن🥹 {تگ}؟ ",
    "بوس به قینت {تگ} ",
    "اوه بیبی {تگ} ",
    "وقت وقته چیه اگه گفتی {تگ}؟ ",
    "هر کی نیاد ک.ونیه {تگ} ",
]


def _tag_label_for(user_obj, uid) -> str:
    """متنِ نمایشیِ تگ: اسمِ خودِ فرد (کوتاه‌شده اگه طولانی بود)؛ اگه اصلاً اسم/یوزرنیم
    نداشت، به‌جای «کاربر 12345»ی زشت، یه برچسبِ تمیزِ «پروفایل» می‌ذاره که همچنان
    قابل‌کلیکه و پروفایلش رو باز می‌کنه."""
    name = display_name_for(user_obj, uid)
    if name.startswith("کاربر "):
        return "پروفایل"
    return _short_tag_name(name)


TAG_FAST_BATCH_SIZE = 50


async def _send_one_tag_message(event, uid, user_obj, template: str) -> None:
    """یه پیامِ جدا و مستقل برای یک نفر: تگِ واقعیِ قابل‌کلیک با اسمِ خودِ اون فرد
    (نه «مشاهده نمایه»)، وسطِ یه متنِ دلخواه. اگه template شامل {تگ} باشه، تگ دقیقاً
    همون‌جا جایگزین می‌شه؛ وگرنه تگ به‌آخرِ متن اضافه می‌شه."""
    label = _tag_label_for(user_obj, uid)
    mb = MentionTextBuilder()
    if "{تگ}" in template:
        before, _, after = template.partition("{تگ}")
        mb.text(before)
        await mb.mention(uid, user_obj, label=label)
        mb.text(after)
    else:
        mb.text(template.rstrip() + " ")
        await mb.mention(uid, user_obj, label=label)
    msg_text, entities = mb.build()
    await safe_reply(event, msg_text, entities=entities, brand=False)


async def _tag_all_individually(event, chat_id, template_fn) -> bool:
    """هرکس پیامِ جداگانه‌ی خودش رو می‌گیره (تیکه‌تیکه)، ولی پیام‌ها دسته‌دسته و
    هم‌زمان با هم فرستاده می‌شن (یکجا) تا سریع باشه، نه یکی‌یکی با فاصله.
    خروجی False یعنی عضوی برای تگ کردن پیدا نشد."""
    try:
        me = await client.get_me()
    except Exception:
        me = None
    my_id = getattr(me, 'id', None)
    seen, _real_admin_ids, _counts_log = await fetch_members_fast(chat_id, my_id)
    members = [(uid, u) for uid, u in seen.items() if uid != my_id]
    if not members:
        return False
    random.shuffle(members)
    for i in range(0, len(members), TAG_FAST_BATCH_SIZE):
        batch = members[i:i + TAG_FAST_BATCH_SIZE]
        await asyncio.gather(*(
            _send_one_tag_message(event, uid, user_obj, template_fn(uid, user_obj))
            for uid, user_obj in batch
        ))
    return True


PERSIAN_NUMBER_WORDS = {
    "نیم": 0.5, "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5,
    "شش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10, "یازده": 11,
    "دوازده": 12, "بیست": 20, "سی": 30, "چهل": 40, "پنجاه": 50, "شصت": 60,
}

def normalize_digits(s: str) -> str:
    persian = "۰۱۲۳۴۵۶۷۸۹"
    arabic = "٠١٢٣٤٥٦٧٨٩"
    for i, d in enumerate(persian):
        s = s.replace(d, str(i))
    for i, d in enumerate(arabic):
        s = s.replace(d, str(i))
    return s

def parse_time_to_minutes(text: str):
    text = normalize_digits(text.strip())
    if not text:
        return None

    text = re.sub(r'(\d)([^\d\s])', r'\1 \2', text)

    number = None
    unit = None
    for p in text.split():
        if re.fullmatch(r"\d+(\.\d+)?", p):
            number = float(p)
        elif p in PERSIAN_NUMBER_WORDS:
            number = PERSIAN_NUMBER_WORDS[p]
        elif p in ("ساعت", "ساعته"):
            unit = "hour"
        elif p in ("دقیقه", "دقیقه‌ای"):
            unit = "minute"
        elif p in ("روز", "روزه"):
            unit = "day"

    if number is None:
        return None

    if unit == "hour":
        return int(number * 60)
    if unit == "day":
        return int(number * 60 * 24)

    return int(number)

def format_minutes_fa(minutes: int) -> str:
    if minutes % (60 * 24) == 0 and minutes >= 60 * 24:
        return f"{minutes // (60 * 24)} روز"
    if minutes % 60 == 0:
        return f"{minutes // 60} ساعت"
    return f"{minutes} دقیقه"


def parse_time_to_seconds(text: str):
    """مثل parse_time_to_minutes ولی واحد «ثانیه» را هم می‌فهمد و به ثانیه
    برمی‌گرداند - برای بازه‌ی پاکسازی خودکار رسانه که ممکن است خیلی کوتاه
    (چند ثانیه) هم باشد. پیشوند اختیاری «هر» را هم نادیده می‌گیرد."""
    text = normalize_digits(text.strip())
    if not text:
        return None
    if text.startswith("هر"):
        text = text[2:].strip()

    text = re.sub(r'(\d)([^\d\s])', r'\1 \2', text)

    number = None
    unit = None
    for p in text.split():
        if re.fullmatch(r"\d+(\.\d+)?", p):
            number = float(p)
        elif p in PERSIAN_NUMBER_WORDS:
            number = PERSIAN_NUMBER_WORDS[p]
        elif p in ("ثانیه", "ثانیه‌ای"):
            unit = "second"
        elif p in ("دقیقه", "دقیقه‌ای"):
            unit = "minute"
        elif p in ("ساعت", "ساعته"):
            unit = "hour"
        elif p in ("روز", "روزه"):
            unit = "day"

    if number is None:
        return None

    if unit == "second":
        return int(number)
    if unit == "hour":
        return int(number * 3600)
    if unit == "day":
        return int(number * 86400)

    return int(number * 60)


def format_seconds_fa(seconds: int) -> str:
    if seconds % 86400 == 0 and seconds >= 86400:
        return f"{seconds // 86400} روز"
    if seconds % 3600 == 0 and seconds >= 3600:
        return f"{seconds // 3600} ساعت"
    if seconds % 60 == 0 and seconds >= 60:
        return f"{seconds // 60} دقیقه"
    return f"{seconds} ثانیه"


_EXPECTED_YEAR_RANGE = (2025, 2035)

def check_system_clock_sanity():
    now = datetime.now(timezone.utc)
    if not (_EXPECTED_YEAR_RANGE[0] <= now.year <= _EXPECTED_YEAR_RANGE[1]):
        _log(
            f"🚨 هشدار جدی: ساعت سیستم این سرور روی «{now.isoformat()}» تنظیم شده که "
            f"غیرمنطقی به‌نظر می‌رسد! تمام محاسبات سکوت/بن زمان‌دار (مثلاً «۱۰ دقیقه "
            f"سکوت») بر همین ساعتِ سیستم مبتنی هستند، پس اگر این ساعت اشتباه باشد، "
            f"مدت واقعیِ سکوت/بن هم اشتباه (خیلی زودتر یا خیلی دیرتر) خواهد بود. "
            f"لطفاً روی خودِ سرور دستور `date` یا `timedatectl` را بزنید و ساعت را با "
            f"NTP هماهنگ کنید."
        )
    return now


IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

def now_tehran() -> datetime:
    return datetime.now(IRAN_TZ)


_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def to_persian_digits(s: str) -> str:
    return "".join(_PERSIAN_DIGITS[int(c)] if c.isdigit() else c for c in s)


_JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]


def _gregorian_to_jalali(gy: int, gm: int, gd: int):
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]

    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1

    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    for i in range(gm2):
        g_day_no += g_days_in_month[i]
    if gm2 > 1 and ((gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)):
        g_day_no += 1
    g_day_no += gd2

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053

    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461

    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    jm, jd = 12, j_day_no - 335
    for i in range(11):
        if j_day_no < j_days_in_month[i]:
            jm, jd = i + 1, j_day_no + 1
            break
        j_day_no -= j_days_in_month[i]

    return jy, jm, jd


def format_jalali_dt(dt) -> str:
    """Convert a datetime (or an ISO string) to a Persian-calendar string
    in Tehran time, e.g. '۲۳ شهریور ۱۴۰۵ - ۱۴:۳۲'."""
    if not dt:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_t = dt.astimezone(IRAN_TZ)
    jy, jm, jd = _gregorian_to_jalali(dt_t.year, dt_t.month, dt_t.day)
    text = f"{jd} {_JALALI_MONTHS[jm - 1]} {jy} - {dt_t.hour:02d}:{dt_t.minute:02d}"
    return to_persian_digits(text)

def normalize_hhmm(text: str):
    text = normalize_digits(text.strip())
    m = re.fullmatch(r"(\d{1,2}):(\d{1,2})", text)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    return f"{h:02d}:{mi:02d}"

def default_chat_cfg() -> dict:
    return {
        "active": False,
        "admins": [],
        "group_owner": None,
        "exempt": [],
        "silent_mode": False,
        "ban_enabled": True,
        "word_filters": [],
        "media_filters": {},
        "locks": {
            "gif": False, "photo": False, "link": False, "phone": False,
            "forward": False, "id": False, "sticker": False,
            "voice": False, "video": False, "file": False,
            "unicode_spam": False, "spam": False, "group": False,
            "media": False,
        },
        "auto_cleanup": {"times": []},
        "auto_media_cleanup": {"interval_seconds": None, "times": []},
        "auto_unmute_time": None,
        "auto_unban_time": None,
        "group_auto_lock": {"lock_time": None, "unlock_time": None},
        "muted": {},
        "banned": {},
        "spam_punishment": {"type": "timed_mute", "minutes": 10},
        "mute_action_lock": None,
        "bio_filter_words": [],
        "bio_punishment": {"type": "normal"},
        "name_filter_words": [],
        "name_punishment": {"type": "normal"},
        "anti_khale_enabled": False,
        "anti_khale_punishment": {"type": "mute"},
        "member_stealer_lock_enabled": False,
        "anti_jagh_lock_enabled": False,
        "anti_ad_lock_enabled": False,
        "mute_reset_minutes": None,
        "auto_delete_messages_enabled": False,
        "auto_delete_delay_seconds": None,
        "learned_words": {},
        "learned_words_enabled": True,
        "fun_enabled": True,
        "lock_warn_settings": {},
        "warnings": {},
        "killed": {},
        "spam_settings": {},
        "_last_run": {},
    }

_migrated_chat_keys: set = set()


def get_chat_cfg(chat_id) -> dict:
    key = str(chat_id)
    chats = config.setdefault("chats", {})
    if key not in chats:
        chats[key] = default_chat_cfg()
        _migrated_chat_keys.add(key)
    elif key not in _migrated_chat_keys:
        entry = chats[key]
        for k, v in default_chat_cfg().items():
            entry.setdefault(k, v)
        ac = entry.get("auto_cleanup")
        if isinstance(ac, dict) and "times" not in ac:
            legacy_times = [t for t in (ac.get("time1"), ac.get("time2")) if t]
            entry["auto_cleanup"] = {"times": legacy_times}
        if isinstance(entry.get("banned"), list):
            entry["banned"] = {str(uid): None for uid in entry["banned"]}
        _migrated_chat_keys.add(key)
    return chats[key]


def is_bot_owner(uid) -> bool:
    return uid == BOT_OWNER_ID or uid in config.get("bot_owners", [])

def is_chat_active(chat_id) -> bool:
    """فقط گپ‌هایی که با install فعال شده‌اند اجازه دارند بقیه‌ی قابلیت‌های ربات را اجرا کنند."""
    return bool(get_chat_cfg(chat_id).get("active"))

def is_group_owner(chat: dict, uid) -> bool:
    return chat.get("group_owner") == uid

def is_owner_level(chat: dict, uid) -> bool:
    return is_bot_owner(uid) or is_group_owner(chat, uid)

def is_admin(chat: dict, uid) -> bool:
    return is_owner_level(chat, uid) or uid in chat.get("admins", [])

def is_exempt(chat: dict, uid) -> bool:
    return uid in chat.get("exempt", [])


async def sync_group_admins_from_soroush(chat_id, chat: dict) -> tuple:
    participants = []

    try:
        if ChannelParticipantsAdmins is None:
            raise RuntimeError("ChannelParticipantsAdmins در کتابخانه پیدا نشد")
        async for p in client.iter_participants(chat_id, filter=ChannelParticipantsAdmins):
            participants.append(p)
    except Exception as e:
        _log(f"⚠️ دریافت ادمین‌ها با فیلتر مستقیم ناموفق بود ({e})؛ تلاش با گرفتن کل اعضا...")
        try:
            async for p in client.iter_participants(chat_id):
                part = getattr(p, 'participant', None)
                cls_name = type(part).__name__ if part else ''
                if 'Creator' in cls_name or 'Admin' in cls_name:
                    participants.append(p)
        except Exception as e2:
            _log(f"⚠️ خطا در دریافت اعضای گپ برای بررسی ادمین: {e2}")
            return (0, 0)

    added = []
    found_admins = 0
    creator_id = None

    for p in participants:
        uid = getattr(p, 'id', None)
        if not uid:
            continue
        found_admins += 1
        part = getattr(p, 'participant', None)
        cls_name = type(part).__name__ if part else ''
        if 'Creator' in cls_name:
            creator_id = uid
            continue
        if uid not in chat["admins"]:
            chat["admins"].append(uid)
            added.append(uid)

    if creator_id and not chat.get("group_owner"):
        chat["group_owner"] = creator_id

    await save_config(config)
    return (len(added), found_admins)

async def notify(event, chat: dict, text: str, force: bool = False, warning: bool = False, entities=None):
    if force or not chat.get("silent_mode"):
        sent = await safe_reply(event, text, entities=entities)
        if warning:
            _schedule_bot_reply_auto_delete(event, sent)


_DOMAIN_LINK_PATTERN = re.compile(r'\b([a-zA-Z0-9-]+)\.(ir|com|net|org|io|me|co|app)\b')


async def safe_reply(event, text: str, entities=None, brand: bool = True):
    if brand:
        text = _brand_text(text)
    kwargs = {"formatting_entities": entities, "parse_mode": None} if entities else {}
    try:
        return await event.reply(text, **kwargs)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        if "CHAT_SEND_LINK_FORBIDDEN" in str(e):
            safe_text = _DOMAIN_LINK_PATTERN.sub(r'\1[.]\2', text)
            try:
                return await event.reply(safe_text, **kwargs)
            except Exception as e2:
                _log(f"⚠️ safe_reply (تلاش دوم بدون لینک) هم خطا داد: {e2}")
                return None
        _log(f"⚠️ reply error: {e}")
        return None


def _schedule_bot_reply_auto_delete(event, sent_message) -> None:
    if not sent_message:
        return
    chat_id = getattr(event, 'chat_id', None)
    if not chat_id or getattr(event, 'is_private', False):
        return
    chat = get_chat_cfg(chat_id)
    if not chat.get("auto_delete_messages_enabled"):
        return
    msg_id = getattr(sent_message, 'id', None)
    if not msg_id:
        return
    delay = chat.get("auto_delete_delay_seconds")
    asyncio.create_task(_delayed_delete_message(chat_id, msg_id, delay))


async def send_moderation_alert(chat_id, chat: dict, text: str, entities=None) -> None:
    if chat.get("silent_mode"):
        return
    text = _brand_text(text)
    kwargs = {"formatting_entities": entities, "parse_mode": None} if entities else {}
    try:
        sent = await client.send_message(chat_id, text, **kwargs)
    except Exception as e:
        _log(f"⚠️ moderation alert send failed: {e}")
        return
    if chat.get("auto_delete_messages_enabled"):
        msg_id = getattr(sent, 'id', None)
        if msg_id:
            delay = chat.get("auto_delete_delay_seconds")
            asyncio.create_task(_delayed_delete_message(chat_id, msg_id, delay))

def wrap_box(emoji: str, title: str, body: str) -> str:
    """Wraps a block of text in the boxed panel style used for
    وضعیت گروه / اطلاعات کاربر in the template: a '╭─〔 emoji title 〕─╮'
    header, each body line prefixed with '│', and a '╰────────────────╯'
    footer."""
    lines = body.rstrip("\n").split("\n")
    boxed = [f"╭─〔 {emoji} {title} 〕─╮", "│"]
    for line in lines:
        boxed.append(f"│ {line}" if line else "│")
    boxed.append("╰────────────────╯")
    return "\n".join(boxed)


def build_action_block(details: list = None, footer: str = None) -> str:
    """Builds the '『detail』 lines + ╰─ footer' block used by the pretty
    template (see uploaded template .txt): a blank line, then each
    (icon, label, value) rendered as '{icon} {label}: 『{value}』', then a
    closing '╰─ {footer}' line."""
    parts = []
    if details:
        parts.append("")
        for icon, label, value in details:
            parts.append(f"{icon} {label}: 『{value}』")
    if footer:
        parts.append(f"╰─ {footer}")
    return "\n".join(parts)


async def notify_user_action(event, chat: dict, user_id, prefix_emoji: str, suffix: str, force: bool = True,
                              details: list = None, footer: str = None):
    """Sends a notify message with a real tappable mention of user_id in
    front of it - e.g. '⛔️ <mention> بن شد.' - used by the manual
    بن/رفع بن/سکوت/رفع سکوت commands. If details/footer are given, the
    pretty boxed block (『value』 + ╰─ footer) is appended, matching the
    template style."""
    try:
        user = await client.get_entity(user_id)
    except Exception:
        user = None
    b = MentionTextBuilder().text(f"↜ ")
    await b.mention(user_id, user)
    b.text(f"\n{prefix_emoji}{suffix}")
    block = build_action_block(details, footer)
    if block:
        b.text(f"\n{block}")
    msg_text, entities = b.build()
    await notify(event, chat, msg_text, force=force, entities=entities)


async def notify_mention_notice(event, chat: dict, user_id, body: str, warning: bool = True):
    """اعلانِ مربوط به یک کاربر با تگِ قابل‌کلیکِ «مشاهده نمایه» در اولش (مثل بقیه‌ی پیغام‌ها)؛
    مثل notify() با صدا خفه کن و حذف خودکار هماهنگه."""
    try:
        user = await client.get_entity(user_id)
    except Exception:
        user = None
    b = MentionTextBuilder().text("↜ ")
    await b.mention(user_id, user)
    b.text("\n" + body)
    msg_text, entities = b.build()
    await notify(event, chat, msg_text, warning=warning, entities=entities)


async def resolve_target(event, chat_id, arg_text: str = "", prefer_arg: bool = False):
    reply_id = getattr(event, 'reply_to_msg_id', None)
    if not reply_id:
        reply_obj = getattr(event, 'reply_to', None)
        reply_id = getattr(reply_obj, 'reply_to_msg_id', None) if reply_obj else None

    if reply_id and not (prefer_arg and arg_text.strip()):
        for attempt in range(3):
            try:
                get_reply = getattr(event, 'get_reply_message', None)
                msg = await get_reply() if callable(get_reply) else await client.get_messages(chat_id, ids=reply_id)
                if msg:
                    sid = getattr(msg, 'sender_id', None)
                    if sid:
                        return sid
                break
            except Exception as e:
                _log(f"⚠️ resolve_target (reply) error [تلاش {attempt + 1}]: {e}")
                if attempt < 2:
                    await asyncio.sleep(0.7)

    arg_text = arg_text.strip().lstrip('@')
    if arg_text:
        try:
            entity = await client.get_entity(arg_text if not arg_text.isdigit() else int(arg_text))
            uid = getattr(entity, 'id', None)
            if uid:
                return uid
        except Exception as e:
            _log(f"⚠️ resolve_target (arg) error: {e}")

        member = await _find_member_in_chat(chat_id, arg_text)
        if member is not None:
            return getattr(member, 'id', None)
    return None


_MEMBER_LOOKUP_TIMEOUT = 25


def _member_matches(p, want_id, want_username) -> bool:
    if want_id is not None:
        return getattr(p, 'id', None) == want_id
    un = getattr(p, 'username', None)
    if un and un.lower() == want_username:
        return True
    for u in (getattr(p, 'usernames', None) or []):
        if (getattr(u, 'username', None) or '').lower() == want_username:
            return True
    return False


async def _find_member_in_chat(chat_id, arg_text: str):
    """یوزرنیم یا آیدی عددی را توی لیست اعضای گپ پیدا می‌کند (وقتی تو کش نیست).
    اول جستجوی سریعِ سمتِ سرور (برای یوزرنیم)، بعد گشتنِ کاملِ اعضا."""
    arg_text = (arg_text or "").strip().lstrip('@')
    if not arg_text:
        return None
    want_id = int(arg_text) if arg_text.isdigit() else None
    want_username = None if want_id is not None else arg_text.lower()
    if want_id is None and not re.fullmatch(r'[A-Za-z0-9_]{3,64}', arg_text):
        return None

    async def _scan():
        attempts = [{}]
        if want_username:
            attempts.insert(0, {"search": want_username})
        for kwargs in attempts:
            try:
                async for p in client.iter_participants(chat_id, **kwargs):
                    if _member_matches(p, want_id, want_username):
                        return p
            except Exception as e:
                _log(f"⚠️ _find_member_in_chat ({kwargs or 'همه اعضا'}) error: {e}")
        return None

    try:
        return await asyncio.wait_for(_scan(), timeout=_MEMBER_LOOKUP_TIMEOUT)
    except asyncio.TimeoutError:
        _log(f"⚠️ _find_member_in_chat: زمان گشتن در لیست اعضا تمام شد ({arg_text})")
    except Exception as e:
        _log(f"⚠️ _find_member_in_chat error: {e}")
    return None

def _is_transient_rpc_error(e) -> bool:
    """خطای موقتِ سمت سرور: ۵۰۰ (INTERNAL_SERVER_ERROR) یا «باید N ثانیه صبر کنی» (فلود‌ویت)."""
    if getattr(e, "seconds", None):
        return True
    if type(e).__name__ == "ServerError":
        return True
    t = f"{e!r} {e}"
    return "INTERNAL_SERVER_ERROR" in t or "RPCError 500" in t or "wait of" in t


async def apply_group_punishment(event, chat_id, chat: dict, user_id, punishment: dict,
                                  reason_label: str, force_notify: bool = False,
                                  notify_enabled: bool = True):
    ptype = punishment.get("type", "timed_mute")

    async def _notify_mention(prefix_emoji: str, suffix: str, details: list = None, footer: str = None):
        if not notify_enabled:
            return
        try:
            user = await client.get_entity(user_id)
        except Exception:
            user = None
        b = MentionTextBuilder().text("↜ ")
        await b.mention(user_id, user)
        b.text(f"\n{prefix_emoji}{suffix}")
        all_details = [("📌", "دلیل", reason_label)] + (details or [])
        block = build_action_block(all_details, footer)
        if block:
            b.text(f"\n{block}")
        msg_text, entities = b.build()
        await notify(event, chat, msg_text, force=force_notify, warning=True, entities=entities)

    _pun_where = "مجازات " + {"ban": "بن", "timed_mute": "سکوت زمان‌دار"}.get(ptype, "سکوت دائم") + f" ({reason_label})"

    async def _api(fn, *a, **kw):
        try:
            return await fn(*a, **kw)
        except Exception as first_err:
            if _is_transient_rpc_error(first_err):
                # خطای موقتِ سرور (۵۰۰ / فلود‌ویت): کمی صبر و تلاش دوم (آخر)
                _log_rpc_error(_pun_where, first_err, chat_id, user_id, attempt="۱ از ۲")
                await asyncio.sleep(min(_bulk_err_wait(first_err), 3))
                return await fn(*a, **kw)
            _log(f"⚠️ apply_group_punishment: تلاش اول شکست خورد ({first_err}); گشتن در لیست اعضا...")
            if await _find_member_in_chat(chat_id, str(user_id)) is None:
                raise
            return await fn(*a, **kw)

    try:
        if ptype == "ban":
            await _api(client.ban_chat_member, chat_id, user_id)
            chat.setdefault("banned", {})[str(user_id)] = datetime.now(timezone.utc).isoformat()
            await save_config(config)
            await _notify_mention("🔨", " از گروه مسدود شد.")
        elif ptype == "timed_mute":
            minutes = punishment.get("minutes", 10)
            now = _accurate_now(event)
            until = now + timedelta(minutes=minutes)
            _log(f"[سکوت اسپم] الان={now.isoformat()} تا={until.isoformat()} ({minutes} دقیقه)")
            await _api(client.edit_permissions, chat_id, user_id, until_date=int(until.timestamp()), send_messages=False)
            chat.setdefault("muted", {})[str(user_id)] = until.isoformat()
            await save_config(config)
            await _notify_mention("🔇", " به حالت سکوت درآمد.",
                                   details=[("⏱", "مدت", format_minutes_fa(minutes))])
        else:


            await _api(client.edit_permissions, chat_id, user_id, until_date=0, send_messages=False)
            chat.setdefault("muted", {})[str(user_id)] = None
            await save_config(config)
            await _notify_mention("🔇", " به‌صورت دائم ساکت شد.")
    except Exception as e:
        _log_rpc_error(_pun_where, e, chat_id, user_id, attempt="۲ از ۲ (نهایی - مجازات اعمال نشد)")

async def apply_all_group_permissions(chat_id, chat: dict):
    locks = chat.get("locks", {})
    media_locked = locks.get("media", False)
    try:
        await client.edit_permissions(
            chat_id, None,
            send_gifs=not (locks.get("gif", False) or media_locked),
            send_media=not (locks.get("photo", False) or media_locked),
            send_stickers=not (locks.get("sticker", False) or media_locked),
            send_messages=not locks.get("group", False),
        )
    except Exception as e:
        _log(f"⚠️ apply_all_group_permissions error: {e}")


URL_RE = re.compile(r'(https?://|www\.|t\.me/|@[\w\d_]{4,})', re.IGNORECASE)
PHONE_RE = re.compile(r'(\+?\d[\d\s\-]{7,}\d)')
UNICODE_SPAM_RE = re.compile(r'[\u200b-\u200f\u202a-\u202e\ufe00-\ufe0f\u0300-\u036f]{6,}')

spam_tracker: dict = {}
spam_evicted: dict = {}
spam_cooldown: dict = {}

lock_warn_cooldown: dict = {}
LOCK_WARN_COOLDOWN_SECONDS = 10.0

FLOOD_WINDOW_SECONDS = 5.0
EVICTED_KEEP_SECONDS = 15.0
SPAM_COOLDOWN_SECONDS = 10.0

_DEL_QUEUE: dict = {}
_DEL_FLUSHERS: set = set()
_DEL_FLUSH_DELAY = 0.03  # فقط برای دسته‌بندیِ پیام‌هایی که تقریباً هم‌زمان می‌رسن؛ اولین پیام بدون این تاخیر پاک می‌شه


_DEL_LABELS: dict = {}


def _queue_delete(chat_id, msg_id, label: str = "صف حذف") -> None:
    if not msg_id:
        return
    _DEL_QUEUE.setdefault(chat_id, []).append(msg_id)
    _DEL_LABELS.setdefault(chat_id, set()).add(label)
    if chat_id not in _DEL_FLUSHERS:
        _DEL_FLUSHERS.add(chat_id)
        _spawn(_flush_delete_queue(chat_id), "delete-batch")


async def _retry_delete_once(chat_id, ids, wait: float, where: str = "صف حذف") -> None:
    await asyncio.sleep(wait)
    try:
        await client.delete_messages(chat_id, ids)
    except Exception as e:
        _log_rpc_error(where, e, chat_id, attempt="۲ از ۲ (نهایی - پیام حذف نشد)")


async def _flush_delete_queue(chat_id) -> None:
    try:
        first = True
        while True:
            if not first:
                # فقط بین دسته‌های بعدی صبر می‌کنیم تا پیام‌های پشت‌سرهم جمع بشن؛
                # اولین دسته بدون تاخیر پاک می‌شه تا سرعت حذف حداکثر باشه.
                await asyncio.sleep(_DEL_FLUSH_DELAY)
            first = False
            ids = _DEL_QUEUE.get(chat_id)
            if not ids:
                _DEL_QUEUE.pop(chat_id, None)
                return
            labels = "، ".join(sorted(_DEL_LABELS.pop(chat_id, None) or {"صف حذف"}))
            batch, rest = ids[:100], ids[100:]
            if rest:
                _DEL_QUEUE[chat_id] = rest
            else:
                _DEL_QUEUE.pop(chat_id, None)
            try:
                await client.delete_messages(chat_id, batch)
            except Exception as e:
                _log_rpc_error(labels, e, chat_id, attempt="۱ از ۲")
                # تلاش دوم (فقط مسیر اسپم): تو یه تسک جدا تا صفِ حذف معطل نمونه
                _spawn(_retry_delete_once(chat_id, batch, min(_bulk_err_wait(e), 5), labels), "delete-retry")
    finally:
        _DEL_FLUSHERS.discard(chat_id)


USER_MSG_LOG_KEEP_SECONDS = 600
USER_MSG_LOG_MAX = 500
SPAM_SWEEP_SECONDS = 60
_user_msg_log: dict = {}
_spam_sweep_until: dict = {}
_spam_sweeping: set = set()


def _track_user_msg(chat_id, user_id, msg_id) -> None:
    if not msg_id:
        return
    key = (chat_id, user_id)
    dq = _user_msg_log.get(key)
    if dq is None:
        if len(_user_msg_log) > 4000:
            cutoff = time.monotonic() - USER_MSG_LOG_KEEP_SECONDS
            for k in [k for k, d in _user_msg_log.items() if not d or d[-1][0] < cutoff]:
                _user_msg_log.pop(k, None)
        dq = _user_msg_log[key] = deque(maxlen=USER_MSG_LOG_MAX)
    dq.append((time.monotonic(), msg_id))


def _drain_user_msgs(key, min_id=None) -> list:
    """پیام‌های ثبت‌شده‌ی کاربر رو برمی‌گردونه؛ اگه min_id داده بشه فقط پیام‌های از شروعِ اسپم
    (آیدی >= min_id) برگشت داده می‌شن و به پیام‌های قبلی کاری نداره."""
    dq = _user_msg_log.pop(key, None)
    if not dq:
        return []
    cutoff = time.monotonic() - USER_MSG_LOG_KEEP_SECONDS
    return [m for (t, m) in dq if t >= cutoff and (min_id is None or m >= min_id)]


def _spam_sweep_arm(key) -> None:
    """از همین لحظه تا SPAM_SWEEP_SECONDS ثانیه، هر پیامِ این کاربر بلافاصله صفِ حذف می‌شه."""
    _spam_sweep_until[key] = time.monotonic() + SPAM_SWEEP_SECONDS


def _spam_sweep_active(key) -> bool:
    until = _spam_sweep_until.get(key)
    if until is None:
        return False
    if time.monotonic() >= until:
        _spam_sweep_until.pop(key, None)
        return False
    return True


VELOCITY_MAX_MSGS = 6
VELOCITY_WINDOW_SECONDS = 1.0
_velocity_track: dict = {}
_velocity_start_id: dict = {}  # آیدیِ اولین پیامِ برست؛ بلافاصله بعد از True شدنِ _velocity_trip خونده می‌شه


def _velocity_trip(key, msg_id=None, send_ts=None) -> bool:
    """گاردِ سرعتِ خام (velocity guard)، کاملاً مستقل از محتوای پیام: اگر VELOCITY_MAX_MSGS پیام
    از یک نفر تو کمتر از VELOCITY_WINDOW_SECONDS ثانیه برسه True برمی‌گردونه.
    این تابع هیچ await ای نداره (فقط عملیات روی دیکشنری/دک تو حافظه‌ست)، پس بینِ تسک‌های
    هم‌زمانِ asyncio (sequential_updates=False) هیچ نقطه‌ی تعویضی وجود نداره و ریس ممکن نیست."""
    now = time.monotonic()
    dq = _velocity_track.get(key)
    if dq is None:
        dq = _velocity_track[key] = deque(maxlen=VELOCITY_MAX_MSGS)
    dq.append((now, msg_id, send_ts))
    if len(dq) < VELOCITY_MAX_MSGS or now - dq[0][0] > VELOCITY_WINDOW_SECONDS:
        return False
    # فقط زمانِ رسیدنِ ایونت کافی نیست: وقتی بات کند شه/ری‌کانکت کنه، پیام‌های عادیِ چند ثانیه‌ای
    # یک‌جا می‌رسن و شبیه برست دیده می‌شن. زمانِ واقعیِ ارسال (ثانیه‌ای) هم باید نزدیک باشه.
    _sts = [t for (_, _, t) in dq if t is not None]
    if len(_sts) == len(dq) and (max(_sts) - min(_sts)) > 1:
        return False
    _ids = [i for (_, i, _) in dq if i]
    if _ids:
        _velocity_start_id[key] = min(_ids)
    _velocity_track.pop(key, None)
    return True


async def _velocity_punish(event, chat_id, chat, sender_id, key, start_id=None) -> None:
    """مجازات و پاکسازیِ burst-flood، جدا از هندلرِ اصلی و به‌صورت async اجرا می‌شه
    (فلگِ drop قبلاً و بدون await تو _velocity_trip/_spam_sweep_arm ست شده)."""
    punishment = chat.get("spam_punishment", {"type": "timed_mute", "minutes": 10})
    if punishment.get("type") != "normal":
        try:
            await apply_group_punishment(
                event, chat_id, chat, sender_id, punishment,
                "اسپم برستی (burst-flood) تشخیص داده شد", notify_enabled=False,
            )
        except Exception as e:
            _log(f"⚠️ velocity-punish error: {e}")
    await _spam_sweep(chat_id, sender_id, [getattr(event, 'id', None)], True, start_id)


async def _delete_ids_now(chat_id, ids, where: str = "قفل اسپم - پاکسازی پیام‌های کاربر") -> None:
    """حذفِ سریعِ فهرستی از آیدی‌ها: دسته‌های ۱۰۰تایی، هم‌زمان، با یک بار تلاشِ دوباره."""
    ids = list(dict.fromkeys(i for i in ids if i))
    if not ids:
        return
    sem = asyncio.Semaphore(BULK_DELETE_CONCURRENCY)

    async def _one(batch):
        async with sem:
            for attempt in range(2):
                try:
                    await client.delete_messages(chat_id, batch)
                    return
                except Exception as e:
                    _log_rpc_error(where, e, chat_id, attempt=f"{attempt + 1} از ۲")
                    if attempt == 0:
                        await asyncio.sleep(_bulk_err_wait(e))

    await asyncio.gather(*[_one(ids[i:i + 100]) for i in range(0, len(ids), 100)],
                         return_exceptions=True)


# حداکثر ۳ اسکن هم‌زمانِ تاریخچه‌ی اسپمرها در هر گروه؛ اسپمر چهارم فقط پاکسازیِ
# تاریخچه‌اش منتظر یه جای خالی می‌مونه (پیام‌های فعلی و جدیدش فوری پاک می‌شن).
SWEEP_HISTORY_MAX_PARALLEL = 3
# پاکسازیِ اسپمر فقط از «اولین پیامِ اسپم» تا «آخرین پیامی که فرستاده» رو می‌گیره
# (به پیام‌های قبل از شروع اسپم کاری نداره). سقفِ زیر فقط محافظِ ایمنیه.
SWEEP_RECENT_SCAN_LIMIT = 1000  # سقفِ ایمنی برای تعداد پیامِ خونده‌شده
_SWEEP_HISTORY_SEMS: dict = {}


async def delete_recent_user_messages(chat_id, user_id, start_id=None) -> int:
    """پیام‌های کاربر (از جدید به قدیم) از آخرین پیامش تا اولین پیامِ اسپم (آیدی >= start_id) رو
    پاک می‌کنه و به محض رسیدن به پیامی قبل از شروعِ اسپم می‌ایسته. آیدی‌ها تو هر چت به‌ترتیبِ
    ارسال زیاد می‌شن، پس به ساعتِ سرور/سیستم هم وابسته نیست. اگه start_id نباشه چیزی پاک نمی‌شه."""
    if not start_id:
        return 0
    ids = []
    try:
        async for m in client.iter_messages(chat_id, from_user=user_id, limit=SWEEP_RECENT_SCAN_LIMIT):
            mid = getattr(m, 'id', None)
            if not mid:
                continue
            if mid < start_id:
                break
            ids.append(mid)
    except Exception as e:
        _log_rpc_error("قفل اسپم - اسکن پیام‌های از شروع اسپم", e, chat_id, user_id)
    if ids:
        await _delete_ids_now(chat_id, ids, "قفل اسپم - پاکسازی از شروع اسپم تا آخرین پیام")
    return len(ids)


async def _sweep_history_capped(chat_id, user_id, start_id=None) -> int:
    sem = _SWEEP_HISTORY_SEMS.get(chat_id)
    if sem is None:
        sem = _SWEEP_HISTORY_SEMS[chat_id] = asyncio.Semaphore(SWEEP_HISTORY_MAX_PARALLEL)
    async with sem:
        return await delete_recent_user_messages(chat_id, user_id, start_id)


async def _spam_sweep(chat_id, user_id, extra_ids=None, full_history: bool = True, start_id=None) -> None:
    """بعد از اعمالِ مجازات: ۱) پیام‌های ثبت‌شده‌ی کاربر (از شروعِ اسپم به بعد) فوری پاک می‌شه،
    ۲) هرچی از اولین پیامِ اسپم تا آخرین پیامش مونده پاک می‌شه (به پیام‌های قبلی کاری نداره)،
    ۳) چند دورِ دیگه پیام‌های دیررسیده/عقب‌افتاده هم جارو می‌شن."""
    key = (chat_id, user_id)
    _spam_sweep_arm(key)
    if key in _spam_sweeping:
        for m in (extra_ids or []):
            _queue_delete(chat_id, m, "قفل اسپم - پاکسازی بعد از مجازات")
        return
    _spam_sweeping.add(key)
    try:
        await _delete_ids_now(chat_id, list(extra_ids or []) + _drain_user_msgs(key, start_id))
        if full_history:
            try:
                total = await _sweep_history_capped(chat_id, user_id, start_id)
                _log(f"[اسپم][{chat_id}] {user_id}: {total} پیام از شروع اسپم تا آخرین پیام حذف شد.")
            except Exception as e:
                _log(f"⚠️ delete_all_user_messages (spam) error: {e}")
        for i, delay in enumerate((1.5, 4.0, 10.0)):
            await asyncio.sleep(delay)
            await _delete_ids_now(chat_id, _drain_user_msgs(key, start_id))
            if full_history and i == 1:
                try:
                    await _sweep_history_capped(chat_id, user_id, start_id)
                except Exception as e:
                    _log(f"⚠️ delete_all_user_messages (spam, دور دوم) error: {e}")
    finally:
        _spam_sweeping.discard(key)


def clear_spam_state(chat_id, user_id) -> None:
    _spam_sweep_until.pop((chat_id, user_id), None)
    _user_msg_log.pop((chat_id, user_id), None)
    spam_cooldown.pop((chat_id, user_id), None)
    spam_tracker.pop((chat_id, user_id), None)
    spam_evicted.pop((chat_id, user_id), None)


async def _get_pinned_ids(chat_id) -> set:
    """آیدی پیام‌های پین‌شده‌ی گپ (برای اینکه «حذف کن همش» بهشون دست نزنه)."""
    ids: set = set()
    if InputMessagesFilterPinned is not None:
        try:
            async for pm in client.iter_messages(chat_id, filter=InputMessagesFilterPinned, limit=500):
                pid = getattr(pm, 'id', None)
                if pid:
                    ids.add(pid)
        except Exception as e:
            _log(f"⚠️ _get_pinned_ids error: {e}")
    return ids


BULK_DELETE_CONCURRENCY = 5
BULK_SCAN_MAX_PARALLEL = 6


def _bulk_err_wait(e) -> float:
    w = getattr(e, "seconds", None)
    if isinstance(w, (int, float)) and w > 0:
        return min(w + 1, 60)
    return 2


def _bulk_keep_unpinned(pinned_ids):
    """پیام پین‌شده: نه با فیلتر پین و نه با خودِ فلگ پیام، پاک نمی‌شه."""
    def keep(m):
        return getattr(m, 'id', None) not in pinned_ids and getattr(m, 'pinned', False) is not True
    return keep


def _bulk_keep_media(m) -> bool:
    return getattr(m, 'media', None) is not None


def _bulk_keep_all(m) -> bool:
    return True


async def _bulk_fetch_page(chat_id, keep, offset_id, from_user=None):
    """تا ۱۰۰ پیامِ قدیمی‌تر از offset_id (0 = از جدیدترین) →
    (کمترین آیدیِ صفحه یا None اگه صفحه خالی بود، آیدی‌های پیام‌هایی که keep(m) قبول کرد، تعداد پیام‌های صفحه)."""
    attempts = 8
    kw = {"from_user": from_user} if from_user is not None else {}
    for attempt in range(attempts):
        try:
            page_min = None
            ok_ids = []
            cnt = 0
            async for m in client.iter_messages(chat_id, limit=100, offset_id=offset_id, **kw):
                mid = getattr(m, 'id', None)
                if not mid:
                    continue
                cnt += 1
                if page_min is None or mid < page_min:
                    page_min = mid
                if not keep(m):
                    continue
                ok_ids.append(mid)
            return page_min, ok_ids, cnt
        except Exception as e:
            if attempt == attempts - 1:
                raise
            _log_rpc_error("حذف دسته‌ای (دستور) - خواندن پیام‌ها", e, chat_id, attempt=f"{attempt + 1} از {attempts}")
            await asyncio.sleep(_bulk_err_wait(e))


async def _bulk_scan(chat_id, keep, need=None, from_user=None):
    """تاریخچه‌ی گپ (یا فقط پیام‌های from_user) را از جدید به قدیم می‌خواند و هر بار لیستی از آیدی‌های
    قبول‌شده‌ی keep (جدید→قدیم) می‌دهد.

    چند صفحه هم‌زمان خوانده می‌شود: صفحه‌ی k با offset = cursor - stride*k. هر صفحه «۱۰۰ پیامِ جدیدترِ زیر
    offset» است، یعنی همه‌ی پیام‌های بازه‌ی [کمترین‌آیدیِ صفحه، offset) حتماً توی آن هستند. فقط صفحه‌هایی که
    بازه‌شان بدون فاصله به بازه‌ی قبلی وصل می‌شود استفاده می‌شوند (پس هیچ پیامی جا نمی‌ماند)؛ stride
    هم خودکار با تراکم آیدی‌ها تنظیم می‌شود (گپ پرپیام: ۱۰۰، پیام‌های یک کاربر که لابه‌لای بقیه‌ست: بزرگ‌تر).
    need = فقط همین‌قدر آیدیِ جدیدتر."""
    cursor = 0
    stride = 100
    par = 1
    remaining = need
    while True:
        if remaining is not None and remaining <= 0:
            return
        if cursor == 0:
            offsets = [0]
        else:
            if cursor <= 1:
                return
            n = par
            if remaining is not None:
                n = min(n, max(1, -(-remaining // 100)))
            offsets = [o for o in (cursor - stride * i for i in range(n)) if o > 1]

        pages = await asyncio.gather(*[_bulk_fetch_page(chat_id, keep, o, from_user) for o in offsets])

        ids = set()
        covered = cursor if cursor else None
        exhausted = False
        usable = 0
        spans = []
        for o, (pm, ok, cnt) in zip(offsets, pages):
            if covered is not None and o < covered:
                break
            usable += 1
            ids.update(ok)
            if pm is None:
                exhausted = True
                covered = 0
                break
            covered = pm if covered is None else min(covered, pm)
            if cnt >= 100 and o:
                spans.append(o - pm)

        out = sorted(ids, reverse=True)
        if remaining is not None:
            out = out[:remaining]
            remaining -= len(out)
        if out:
            yield out

        if exhausted or covered <= 0:
            return
        if spans:
            stride = max(100, int(min(spans) * 0.8))
        par = min(par * 2, BULK_SCAN_MAX_PARALLEL) if usable == len(offsets) else max(1, usable)
        cursor = covered


async def _bulk_delete_batch(chat_id, batch_ids, sem, stats) -> None:
    async with sem:
        for attempt in range(3):
            try:
                await client.delete_messages(chat_id, batch_ids)
                stats["ok"] += len(batch_ids)
                return
            except Exception as e:
                _log_rpc_error("حذف دسته‌ای (دستور) - حذف پیام‌ها", e, chat_id, attempt=f"{attempt + 1} از 3")
                await asyncio.sleep(_bulk_err_wait(e))


async def _bulk_delete_run(chat_id, keep, need=None, from_user=None, stats=None) -> dict:
    """خواندن تاریخچه و حذف بچ‌ها هم‌زمان (نه پشت‌سرهم). خروجی: {"seen": پیام‌های پیدا‌شده, "ok": حذف‌شده‌ها}
    (اگه stats داده بشه همون دیکشنری پر می‌شه، حتی وقتی وسط کار خطا بیاد)."""
    sem = asyncio.Semaphore(BULK_DELETE_CONCURRENCY)
    if stats is None:
        stats = {"seen": 0, "ok": 0}
    pending = set()
    try:
        async for ids in _bulk_scan(chat_id, keep, need, from_user):
            stats["seen"] += len(ids)
            for i in range(0, len(ids), 100):
                t = asyncio.ensure_future(_bulk_delete_batch(chat_id, ids[i:i + 100], sem, stats))
                pending.add(t)
                t.add_done_callback(pending.discard)
            while len(pending) >= BULK_DELETE_CONCURRENCY * 4:
                await asyncio.wait(set(pending), return_when=asyncio.FIRST_COMPLETED)
    finally:
        if pending:
            await asyncio.gather(*list(pending), return_exceptions=True)
    return stats


async def bulk_delete(chat_id, limit=None) -> int:
    """حذف کن [تعداد] / حذف کن همش (limit=None): پیام‌های پین‌شده هیچ‌وقت پاک نمی‌شن
    و توی «تعداد» هم حساب نمی‌شن (یعنی «حذف کن 20» = ۲۰ پیام آخرِ غیرپین)."""
    pinned_ids = await _get_pinned_ids(chat_id)
    keep = _bulk_keep_unpinned(pinned_ids)
    if limit is not None:
        if limit <= 0:
            return 0
        stats = await _bulk_delete_run(chat_id, keep, limit)
        return stats["seen"]

    deleted = 0
    for _pass in range(5):
        stats = await _bulk_delete_run(chat_id, keep, None)
        deleted += stats["ok"]
        if stats["ok"] == 0:
            break
    return deleted


async def bulk_delete_media(chat_id) -> int:
    """مثل bulk_delete ولی فقط پیام‌هایی که رسانه (عکس/فیلم/فایل/ویس/گیف/استیکر و ...)
    دارند را پاک می‌کند؛ پیام‌های متنیِ صرف دست‌نخورده می‌مانند."""
    deleted = 0
    for _pass in range(3):
        stats = await _bulk_delete_run(chat_id, _bulk_keep_media, None)
        deleted += stats["ok"]
        if stats["ok"] == 0:
            break
    return deleted


async def delete_all_user_messages(chat_id, user_id, limit=None) -> int:
    stats = {"seen": 0, "ok": 0}
    try:
        await _bulk_delete_run(chat_id, _bulk_keep_all, limit, from_user=user_id, stats=stats)
    except Exception as e:
        _log(f"⚠️ iter_messages (حذف پیام‌های کاربر) error: {e}")
    return stats["ok"]

LOCK_FA_NAMES = {
    "gif": "گیف", "photo": "عکس", "link": "لینک", "phone": "شماره",
    "forward": "فوروارد", "id": "آیدی", "sticker": "استیکر",
    "voice": "ویس", "video": "ویدیو", "file": "فایل",
    "unicode_spam": "کد هنگی", "spam": "اسپم", "group": "گپ",
    "media": "رسانه",
}
LOCK_FA_TO_KEY = {v: k for k, v in LOCK_FA_NAMES.items()}
LOCK_FA_TO_KEY["شماره تلفن"] = "phone"
LOCK_FA_TO_KEY["فیلم"] = "video"
LOCK_FA_TO_KEY["رسانه کلی"] = "media"

LOCK_ON_FOOTERS = {
    "link": "ارسال لینک در گروه ممنوع است.",
    "phone": "ارسال شماره تلفن ممنوع است.",
    "forward": "ارسال پیام فورواردشده ممنوع است.",
    "id": "ارسال آیدی ممنوع است.",
    "gif": "ارسال گیف ممنوع است.",
    "photo": "ارسال عکس ممنوع است.",
    "sticker": "ارسال استیکر ممنوع است.",
    "voice": "ارسال ویس ممنوع است.",
    "video": "ارسال ویدیو و ویدیو مسیج ممنوع است.",
    "file": "ارسال فایل و آهنگ ممنوع است.",
    "unicode_spam": "ارسال کد هنگی ممنوع است.",
    "spam": "فعالیت‌های اسپم کنترل می‌شوند.",
    "group": "ارسال پیام در گروه ممنوع است.",
    "media": "ارسال هر نوع رسانه (عکس، ویدیو، فایل، گیف، استیکر) ممنوع است.",
}

LOCK_MEDIA_KINDS = {
    "voice": {"voice"},
    "video": {"video", "video_note"},
    "file": {"file", "audio"},
}

LOCK_ALL_EXCLUDED = {"gif", "photo", "sticker", "voice", "video", "file", "group", "media"}
LOCK_ALL_KEYS = [k for k in LOCK_FA_NAMES if k not in LOCK_ALL_EXCLUDED]
LOCK_ALL_EXTRA_FLAGS = (
    ("anti_khale_enabled", "ضد تبچی"),
    ("member_stealer_lock_enabled", "ممبر دزد"),
    ("anti_jagh_lock_enabled", "ضد جقی"),
    ("anti_ad_lock_enabled", "ضد تبلیغات"),
)
_LOCK_ALL_RE = re.compile(r"^(?:(?:فعال ?سازی|بستن|روشن کردن) همه(?: ی)? قفل ?ها|قفل همه)$")

def format_locks_status(locks: dict) -> str:
    on = [LOCK_FA_NAMES[k] for k, v in locks.items() if v]
    return "، ".join(on) if on else "هیچ‌کدام"


GROUP_LOCK_BANNER_TEMPLATE = (
    "🌙 ──── 『 گپ بسته شد 』 ──── 🌙\n\n"
    "🤍 دوستان و اعضای عزیز\n\n"
    "گپ در حال حاضر بسته می‌باشد و در زمان تعیین‌شده دوباره باز خواهد شد.\n\n"
    "⏰ ──── ساعت بازگشایی ────\n"
    "{unlock_time}\n\n"
    "از همراهی و حضور شما سپاسگزاریم 🌷 برای همگی شما آرزوی شادی و موفقیت داریم. ✨\n\n"
    "♡ به امید دیدار دوباره ♡"
)

GROUP_UNLOCK_BANNER_TEXT = (
    "✦ ──── 『 گپ باز شد 』 ──── ✦ ♥\n\n"
    "خب خب، بالاخره آزاد شدیم 😂\n\n"
    "گپ دوباره بازه؛ برید ببینیم کی از همه شروع می‌کنه به شلوغ‌کاری 😂😭\n\n"
    "حرفاتون رو آماده کنید، که سکوت دیگه رسماً تموم شد ✨🫠\n\n"
    "♡ حالا بترکونید گپ رو 😂"
)

def parse_two_times(rest: str):
    parts = rest.split("|")
    if len(parts) != 2:
        return None
    lock_t = normalize_hhmm(parts[0].strip())
    unlock_t = normalize_hhmm(parts[1].strip())
    if not lock_t or not unlock_t:
        return None
    return lock_t, unlock_t

def punishment_to_fa(p: dict) -> str:
    ptype = p.get("type", "timed_mute")
    return {
        "normal": "عادی (فقط اخطار)",
        "ban": "بن",
        "timed_mute": f"سکوت به مدت {format_minutes_fa(p.get('minutes', 10))}",
        "mute": "سکوت دائم",
    }.get(ptype, ptype)

def parse_punishment_text(rest: str):
    rest = rest.strip()
    if rest in ("عادی", "هشدار"):
        return {"type": "normal"}
    if rest == "بن":
        return {"type": "ban"}
    if rest.startswith("سکوت"):
        time_part = rest[len("سکوت"):].strip()
        if not time_part or time_part in ("دائم", "دائمی"):
            return {"type": "mute"}
        minutes = parse_time_to_minutes(time_part)
        if minutes and minutes > 0:
            return {"type": "timed_mute", "minutes": minutes}
        return None
    return None


scheduler_task = None

async def scheduler_loop():
    while True:
        await asyncio.sleep(5)
        try:
            now = now_tehran()
            now_utc_ts = datetime.now(timezone.utc).timestamp()
            hhmm = now.strftime("%H:%M")
            today_key = now.strftime("%Y-%m-%d")
            changed = False
            for chat_id_str, chat in list(config.get("chats", {}).items()):
                try:
                    chat_id_int = int(chat_id_str)
                except ValueError:
                    continue
                last_run = chat.setdefault("_last_run", {})

                cleanup_cfg = chat.get("auto_cleanup") or {}

                cleanup_interval_seconds = cleanup_cfg.get("interval_seconds")
                if cleanup_interval_seconds:
                    last_cleanup_ts = last_run.get("cleanup_interval_ts", 0) or 0
                    if now_utc_ts - last_cleanup_ts >= cleanup_interval_seconds:
                        last_run["cleanup_interval_ts"] = now_utc_ts
                        changed = True
                        try:
                            n = await bulk_delete(chat_id_int, None)
                            _log(f"🧹 پاکسازی خودکار (بازه‌ای) - گروه {chat_id_str}: {n} پیام پاک شد.")
                        except Exception as e:
                            _log(f"⚠️ auto cleanup (بازه‌ای) error ({chat_id_str}): {e}")

                for idx, t in enumerate(cleanup_cfg.get("times", [])):
                    run_key = f"cleanup_{idx}_{t}"
                    if t and t == hhmm and last_run.get(run_key) != today_key:
                        last_run[run_key] = today_key
                        changed = True
                        try:
                            n = await bulk_delete(chat_id_int, None)
                            _log(f"🧹 پاکسازی خودکار زمان‌بندی‌شده - گروه {chat_id_str}: {n} پیام پاک شد.")
                        except Exception as e:
                            _log(f"⚠️ auto cleanup error ({chat_id_str}): {e}")

                media_cfg = chat.get("auto_media_cleanup") or {}

                interval_seconds = media_cfg.get("interval_seconds")
                if interval_seconds:
                    last_media_ts = last_run.get("media_cleanup_interval_ts", 0) or 0
                    if now_utc_ts - last_media_ts >= interval_seconds:
                        last_run["media_cleanup_interval_ts"] = now_utc_ts
                        changed = True
                        try:
                            n = await bulk_delete_media(chat_id_int)
                            if n:
                                _log(f"🧹 پاکسازی خودکار رسانه (بازه‌ای) - گروه {chat_id_str}: {n} رسانه پاک شد.")
                        except Exception as e:
                            _log(f"⚠️ auto media cleanup (بازه‌ای) error ({chat_id_str}): {e}")

                for m_idx, m_t in enumerate(media_cfg.get("times", [])):
                    run_key = f"media_cleanup_{m_idx}_{m_t}"
                    if m_t and m_t == hhmm and last_run.get(run_key) != today_key:
                        last_run[run_key] = today_key
                        changed = True
                        try:
                            n = await bulk_delete_media(chat_id_int)
                            _log(f"🧹 پاکسازی خودکار رسانه زمان‌بندی‌شده - گروه {chat_id_str}: {n} رسانه پاک شد.")
                        except Exception as e:
                            _log(f"⚠️ auto media cleanup (زمان‌بندی) error ({chat_id_str}): {e}")

                t = chat.get("auto_unmute_time")
                if t and t == hhmm and last_run.get("unmute") != today_key:
                    last_run["unmute"] = today_key
                    changed = True
                    try:
                        for uid_str in list(chat.get("muted", {}).keys()):
                            await client.edit_permissions(chat_id_int, int(uid_str), send_messages=True)
                            clear_spam_state(chat_id_int, int(uid_str))
                        chat["muted"] = {}
                        _log(f"🔊 رفع سکوت خودکار زمان‌بندی‌شده - گروه {chat_id_str} اجرا شد.")
                    except Exception as e:
                        _log(f"⚠️ auto unmute error ({chat_id_str}): {e}")

                t = chat.get("auto_unban_time")
                if t and t == hhmm and last_run.get("unban") != today_key:
                    last_run["unban"] = today_key
                    changed = True
                    try:
                        for uid_str in list(chat.get("banned", {}).keys()):
                            await client.unban_chat_member(chat_id_int, int(uid_str))
                        chat["banned"] = {}
                        _log(f"✅ رفع بن خودکار زمان‌بندی‌شده - گروه {chat_id_str} اجرا شد.")
                    except Exception as e:
                        _log(f"⚠️ auto unban error ({chat_id_str}): {e}")

                gal = chat.get("group_auto_lock") or {}
                lock_t = gal.get("lock_time")
                unlock_t = gal.get("unlock_time")

                if lock_t and lock_t == hhmm and last_run.get("group_auto_lock_on") != today_key:
                    last_run["group_auto_lock_on"] = today_key
                    changed = True
                    try:
                        chat.setdefault("locks", {})["group"] = True
                        await apply_all_group_permissions(chat_id_int, chat)
                        banner = GROUP_LOCK_BANNER_TEMPLATE.format(unlock_time=unlock_t or "نامشخص")
                        await client.send_message(chat_id_int, _brand_text(banner))
                        _log(f"🔒 قفل خودکار گپ - گروه {chat_id_str} در ساعت {hhmm} قفل شد.")
                    except Exception as e:
                        _log(f"⚠️ group auto-lock error ({chat_id_str}): {e}")

                if unlock_t and unlock_t == hhmm and last_run.get("group_auto_lock_off") != today_key:
                    last_run["group_auto_lock_off"] = today_key
                    changed = True
                    try:
                        chat.setdefault("locks", {})["group"] = False
                        await apply_all_group_permissions(chat_id_int, chat)
                        await client.send_message(chat_id_int, _brand_text(GROUP_UNLOCK_BANNER_TEXT))
                        _log(f"🔓 قفل خودکار گپ - گروه {chat_id_str} در ساعت {hhmm} باز شد.")
                    except Exception as e:
                        _log(f"⚠️ group auto-unlock error ({chat_id_str}): {e}")

                reset_minutes = chat.get("mute_reset_minutes")
                if reset_minutes:
                    last_reset_ts = last_run.get("mute_reset_ts", 0) or 0
                    if now_utc_ts - last_reset_ts >= reset_minutes * 60:
                        last_run["mute_reset_ts"] = now_utc_ts
                        changed = True
                        muted_ids = list(chat.get("muted", {}).keys())
                        unmuted_count = 0
                        for uid_str in muted_ids:
                            try:
                                await client.edit_permissions(chat_id_int, int(uid_str), send_messages=True)
                                clear_spam_state(chat_id_int, int(uid_str))
                                unmuted_count += 1
                            except Exception as e:
                                _log(f"⚠️ auto mute-reset error for {uid_str} ({chat_id_str}): {e}")
                        chat["muted"] = {}
                        if unmuted_count or muted_ids:
                            _log(
                                f"🔊 ریست سکوت خودکار - گروه {chat_id_str}: "
                                f"{unmuted_count} کاربر رفع سکوت شد و لیست پاک شد "
                                "(کاربران قفل ضد تبچی دست‌نخورده ماندند)."
                            )

            if changed:
                await save_config(config)
        except Exception as e:
            _log(f"⚠️ scheduler_loop error: {e}")

def ensure_scheduler_running():
    global scheduler_task
    if scheduler_task is None or scheduler_task.done():
        scheduler_task = asyncio.create_task(scheduler_loop())


async def periodic_cleanup():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        for chat_id_str, chat in config.get("chats", {}).items():
            try:
                chat_id_int = int(chat_id_str)
            except ValueError:
                continue
            if chat.get("bio_filter_words") and chat_id_int in bio_flagged_users_memory:
                count = len(bio_flagged_users_memory[chat_id_int])
                bio_flagged_users_memory[chat_id_int].clear()
                if count:
                    _log(f"🧹 پاکسازی خودکار [{chat_id_str}]: {count} کاربر از حافظه فیلتر بیو پاک شد.")
            if chat.get("anti_khale_enabled") and chat_id_int in anti_khale_flagged_memory:
                count2 = len(anti_khale_flagged_memory[chat_id_int])
                anti_khale_flagged_memory[chat_id_int].clear()
                if count2:
                    _log(f"🧹 پاکسازی خودکار [{chat_id_str}]: {count2} کاربر از حافظه قفل ضد تبچی پاک شد.")
            if chat.get("member_stealer_lock_enabled") and chat_id_int in member_stealer_flagged_memory:
                count3 = len(member_stealer_flagged_memory[chat_id_int])
                member_stealer_flagged_memory[chat_id_int].clear()
                if count3:
                    _log(f"🧹 پاکسازی خودکار [{chat_id_str}]: {count3} کاربر از حافظه قفل ممبر دزد پاک شد.")


        now_ts = datetime.now(timezone.utc).timestamp()
        expired_keys = [
            k for k, last_spam_ts in spam_cooldown.items()
            if now_ts - last_spam_ts > SPAM_COOLDOWN_SECONDS
        ]
        for k in expired_keys:
            spam_cooldown.pop(k, None)
        if expired_keys:
            _log(f"🧹 پاکسازی خودکار: {len(expired_keys)} کول‌داون اسپمِ منقضی‌شده پاک شد.")

        stale_tracker_keys = [
            k for k, hist in spam_tracker.items()
            if not hist or now_ts - hist[-1][0] > 60
        ]
        for k in stale_tracker_keys:
            spam_tracker.pop(k, None)

        stale_evicted_keys = [
            k for k, hist in spam_evicted.items()
            if not hist or now_ts - hist[-1][0] > EVICTED_KEEP_SECONDS
        ]
        for k in stale_evicted_keys:
            spam_evicted.pop(k, None)

        for k in [k for k, hist in ad_tracker.items() if not hist or now_ts - hist[-1] > 60]:
            ad_tracker.pop(k, None)
        for k in [k for k, ts in ad_cooldown.items() if now_ts - ts > SPAM_COOLDOWN_SECONDS]:
            ad_cooldown.pop(k, None)

        stale_stealer_cache_keys = [
            k for k, hist in member_stealer_msg_cache.items()
            if not hist or now_ts - hist[-1][0] > MEMBER_STEALER_CACHE_SECONDS
        ]
        for k in stale_stealer_cache_keys:
            member_stealer_msg_cache.pop(k, None)

def ensure_cleanup_task_running():
    global cleanup_task
    if cleanup_task is None or cleanup_task.done():
        cleanup_task = asyncio.create_task(periodic_cleanup())


AUTO_TYPING_MIN_STEP = 0.12
AUTO_TYPING_MAX_STEP = 0.35
AUTO_TYPING_EASE_OUT_STEP = 0.18
AUTO_TYPING_EASE_MID_T = 0.6
AUTO_TYPING_WORD_BOUNDARY_STEP = 0.30
AUTO_TYPING_HOLD_FULL_SECONDS = 2.5
AUTO_TYPING_DELETE_STEP_SECONDS = 0.08
AUTO_TYPING_HOLD_EMPTY_SECONDS = 0.8

_WORD_OR_SPACE_RE = re.compile(r'\S+|\s+')


def _typing_delays_for(text: str):
    tokens = _WORD_OR_SPACE_RE.findall(text)
    delays = []
    for token in tokens:
        n = len(token)
        if token.isspace():
            delays.extend([AUTO_TYPING_WORD_BOUNDARY_STEP] * n)
            continue
        for i in range(n):
            t = (i / (n - 1)) if n > 1 else 1.0
            if t <= AUTO_TYPING_EASE_MID_T:
                frac = t / AUTO_TYPING_EASE_MID_T
                d = AUTO_TYPING_MAX_STEP - (AUTO_TYPING_MAX_STEP - AUTO_TYPING_MIN_STEP) * frac
            else:
                frac = (t - AUTO_TYPING_EASE_MID_T) / (1 - AUTO_TYPING_EASE_MID_T)
                d = AUTO_TYPING_MIN_STEP + (AUTO_TYPING_EASE_OUT_STEP - AUTO_TYPING_MIN_STEP) * frac
            delays.append(d)
    return delays


def _kill_is_active(chat: dict, uid, now_dt: datetime) -> bool:
    killed = chat.get("killed") or {}
    key = str(uid)
    if key not in killed:
        return False
    until = killed.get(key)
    if not until:
        return True
    try:
        exp = datetime.fromisoformat(until)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
    except Exception:
        return True
    if exp <= now_dt:
        killed.pop(key, None)
        return False
    return True


async def _kill_delete_if_needed(event) -> None:
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return
    chat = (config.get("chats") or {}).get(str(chat_id))
    if not chat:
        return
    killed = chat.get("killed")
    if not killed or str(sender_id) not in killed:
        return
    if is_admin(chat, sender_id):
        return
    if not _kill_is_active(chat, sender_id, _accurate_now(event)):
        await save_config(config)
        return
    msg_id = getattr(event, 'id', None)
    if msg_id:
        try:
            await client.delete_messages(chat_id, msg_id)
        except Exception as e:
            _log(f"⚠️ delete (kill) error: {e}")


@client.on_message()
async def duel_shot_capture_handler(_client, event):
    try:
        _duel_capture_shot(event)
    except Exception as e:
        _log(f"⚠️ duel capture error: {e}")


@client.on_message()
async def kill_message_handler(_client, event):
    await _kill_delete_if_needed(event)


@client.on_edited_message()
async def kill_edited_message_handler(_client, event):
    await _kill_delete_if_needed(event)


_UNLOCK_ALIAS_NAMES = {"ضد تبچی", "ممبر دزد", "ضد جقی", "ضد تبلیغات", "تبلیغات"}


def _apply_command_aliases(text: str) -> str:
    if text == "لیست فیلتر":
        return "لیست فیلتر کلمه"
    for pre in ("بازکردن ", "باز کردن "):
        if text.startswith(pre):
            name = text[len(pre):].strip()
            if name in LOCK_FA_TO_KEY or name in _UNLOCK_ALIAS_NAMES:
                return "باز کردن قفل " + name
    return text


@client.on_message()
async def fast_delete_first_handler(_client, event):
    await locks_and_filters_handler(_client, event)


text_animation_tasks: dict = {}

ANIMATION_FRAME_SECONDS = 0.7

SKULL_EYE_STATES = [
    ("●", "●"),
    ("●", "●"),
    ("◐", "◐"),
    ("●", "●"),
    ("●", "●"),
    ("◑", "◑"),
    ("●", "●"),
    ("▁", "▁"),
]

def _skull_frame(left_eye: str, right_eye: str) -> str:
    return (
        "• • • • • • •\n"
        "•             •\n"
        "•   {L}     {R}   •\n"
        "•             •\n"
        "•     ◡◡◡     •\n"
        "  •         •\n"
        "   • •   • •\n"
        "     •   •"
    ).format(L=left_eye, R=right_eye)


async def _run_skull_animation(chat_id, message_id):
    idx = 0
    try:
        while True:
            left, right = SKULL_EYE_STATES[idx % len(SKULL_EYE_STATES)]
            try:
                await client.edit_message(chat_id, message_id, _skull_frame(left, right))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _log(f"⚠️ انیمیشنِ اسکلت - خطا در ویرایش پیام: {e}")
            idx += 1
            await asyncio.sleep(ANIMATION_FRAME_SECONDS)
    except asyncio.CancelledError:
        pass


async def _run_text_message_animation(chat_id, message_id, text):
    try:
        while True:
            delays = _typing_delays_for(text)

            for i in range(1, len(text) + 1):
                try:
                    await client.edit_message(chat_id, message_id, text[:i])
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    _log(f"⚠️ انیمیشنِ متن - خطا در ویرایش: {e}")
                if i < len(text):
                    await asyncio.sleep(delays[i - 1])

            await asyncio.sleep(AUTO_TYPING_HOLD_FULL_SECONDS)

            for i in range(len(text) - 1, -1, -1):
                shown = text[:i] if i > 0 else "."
                try:
                    await client.edit_message(chat_id, message_id, shown)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    _log(f"⚠️ انیمیشنِ متن - خطا در ویرایش: {e}")
                await asyncio.sleep(AUTO_TYPING_DELETE_STEP_SECONDS)

            await asyncio.sleep(AUTO_TYPING_HOLD_EMPTY_SECONDS)
    except asyncio.CancelledError:
        pass


async def stop_chat_animation(chat_id) -> bool:
    task = text_animation_tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True
    return False


async def stop_all_chat_animations() -> int:
    chat_ids = list(text_animation_tasks.keys())
    count = 0
    for cid in chat_ids:
        if await stop_chat_animation(cid):
            count += 1
    return count


async def start_chat_animation(event, chat_id, kind: str, text: str = None):
    await stop_chat_animation(chat_id)
    if kind == "skull":
        left, right = SKULL_EYE_STATES[0]
        sent = await safe_reply(event, _skull_frame(left, right))
    else:
        sent = await safe_reply(event, text[:1] if text else ".")

    message_id = getattr(sent, 'id', None)
    if not message_id:
        return None

    if kind == "skull":
        task = asyncio.create_task(_run_skull_animation(chat_id, message_id))
    else:
        task = asyncio.create_task(_run_text_message_animation(chat_id, message_id, text))
    text_animation_tasks[chat_id] = task
    return message_id


def _can_use_chat_animation(event, sender_id) -> bool:
    if getattr(event, 'is_private', False):
        return is_bot_owner(sender_id)
    chat_id = getattr(event, 'chat_id', None)
    chat = get_chat_cfg(chat_id) if chat_id else None
    return bool(chat and is_admin(chat, sender_id))


@client.on_message()
async def message_animation_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    sender_id = getattr(event, 'sender_id', None)
    chat_id = getattr(event, 'chat_id', None)
    if not sender_id or not chat_id:
        return

    if text in ("انیمیشن خاموش", "توقف انیمیشن"):
        if not _can_use_chat_animation(event, sender_id):
            await safe_reply(event, "⛔️ اجازه‌ی این کار را نداری.")
            return
        stopped = await stop_chat_animation(chat_id)
        await safe_reply(event, "✅ انیمیشن متوقف شد." if stopped else "ℹ️ انیمیشنِ فعالی برای توقف پیدا نشد.")
        return

    if text == "ریست انیمیشن":
        if not is_bot_owner(sender_id):
            await safe_reply(event, "⛔️ این دستور فقط مخصوص مالک ربات است (چون کل انیمیشن‌ها در همه‌ی گپ‌ها را لغو می‌کند).")
            return
        count = await stop_all_chat_animations()
        await safe_reply(event, 
            f"♻️ ریست انجام شد؛ {count} انیمیشن فعال لغو شد." if count
            else "ℹ️ هیچ انیمیشنِ فعالی برای لغو پیدا نشد."
        )
        return

    if text == "اجرا انیمیشن":
        if not _can_use_chat_animation(event, sender_id):
            await safe_reply(event, "⛔️ اجازه‌ی این کار را نداری.")
            return
        await start_chat_animation(event, chat_id, "skull")
        return

    if text.startswith("ایجاد انیمیشن"):
        if not _can_use_chat_animation(event, sender_id):
            await safe_reply(event, "⛔️ اجازه‌ی این کار را نداری.")
            return
        new_text = text[len("ایجاد انیمیشن"):].strip()
        if not new_text:
            await safe_reply(event, 
                "❓ متن انیمیشن را هم بنویس، مثال: «ایجاد انیمیشن سلام دنیا».\n"
                "برای اجرای انیمیشنِ پیش‌فرض (کله‌اسکلت) هم فقط بنویس: «اجرا انیمیشن»"
            )
            return
        if len(new_text) > 60:
            await safe_reply(event, "⚠️ متن باید حداکثر ۶۰ کاراکتر باشد.")
            return
        await start_chat_animation(event, chat_id, "text", new_text)
        return


PUNISHMENT_ACTION_FA = {
    "mute": "سکوت دائم",
    "ban": "بن",
    "timed_mute": "سکوت موقت",
    "normal": "اخطار",
}


async def apply_punishment(event, chat_id, sender_id, matched_word, punishment, label,
                            chat, show_reason=True, delete_message=False, user=None,
                            alert_emoji: str = None, alert_title: str = None,
                            normal_footer: str = None):
    ptype = punishment.get("type", "normal")
    detail = f"{label} «{matched_word}»" if show_reason else label

    if delete_message:
        msg_id = getattr(event, 'id', None)
        if msg_id:
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception as del_err:
                _log(f"⚠️ Error deleting message ({label}) for {sender_id}: {del_err}")

    async def _notify_mention(prefix_emoji: str, suffix: str, details: list = None, footer: str = None):
        if alert_title:
            b = MentionTextBuilder().text("↜ ")
            await b.mention(sender_id, user)
            b.text(f"\n{alert_emoji or prefix_emoji} {alert_title}")
            block = build_action_block(details, footer)
            if block:
                b.text(f"\n{block}")
        else:
            b = MentionTextBuilder().text(f"{prefix_emoji} ")
            await b.mention(sender_id, user)
            b.text(suffix)
        msg_text, entities = b.build()
        await notify(event, chat, msg_text, warning=True, entities=entities)

    action_fa = PUNISHMENT_ACTION_FA.get(ptype, "اخطار")

    if ptype == "mute":
        await client.edit_permissions(chat_id, sender_id, until_date=0, send_messages=False)
        await _notify_mention("🔇", f"\n{detail} — سکوت شد (دائم).",
                               details=[("⚠️", "اقدام", action_fa)] if not delete_message else None,
                               footer="پیام حذف شد و کاربر به‌صورت دائم ساکت شد." if delete_message else None)

    elif ptype == "ban":
        await client.ban_chat_member(chat_id, sender_id)
        await _notify_mention("⛔️", f"\n{detail} — از گروه حذف شد.",
                               details=[("⚠️", "اقدام", action_fa)])

    elif ptype == "timed_mute":
        minutes = punishment.get("minutes", 60)
        now = _accurate_now(event)
        until = now + timedelta(minutes=minutes)
        _log(f"[سکوت {label}] الان={now.isoformat()} تا={until.isoformat()} ({minutes} دقیقه)")
        await client.edit_permissions(chat_id, sender_id, until_date=int(until.timestamp()), send_messages=False)
        await _notify_mention("⏳", f"\n{detail} — به مدت {format_minutes_fa(minutes)} سکوت شد.",
                               details=[("⏱", "مدت", format_minutes_fa(minutes))])

    else:
        await _notify_mention("⚠️", f"\n{detail}.",
                               details=[("⚠️", "اقدام", "اخطار")],
                               footer=normal_footer)


@client.on_message()
async def bio_filter_handler(_client, event):
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)

    if not chat_id or not sender_id:
        return

    chat = get_chat_cfg(chat_id)
    words = chat.get("bio_filter_words", [])
    if not words:
        return


    try:
        bio = await get_bio_cached(sender_id)
        if not bio:
            return

        bio_lower = bio.lower()
        matched_word = next((w for w in words if w.lower() in bio_lower), None)
        if not matched_word:
            return

        user = await client.get_entity(sender_id)
        punishment = chat.get("bio_punishment", {"type": "normal"})

        await apply_punishment(
            event, chat_id, sender_id, matched_word, punishment,
            "این کاربر کلمه‌ی فیلتر بیو را در بیوی خود دارد:",
            chat, delete_message=True, user=user,
            alert_emoji="🧬", alert_title="کلمه فیلترشده در بیو شناسایی شد.",
            normal_footer="لطفاً بیوی خود را ویرایش کنید.",
        )
        _log(f"[بیو][{chat_id}] {sender_id} matched '{matched_word}' -> {punishment.get('type')}")

    except Exception as e:
        _log(f"⚠️ Error in bio filter for {sender_id}: {e}")


@client.on_message()
async def anti_khale_handler(_client, event):
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)

    if not chat_id or not sender_id:
        return

    chat = get_chat_cfg(chat_id)
    if not chat.get("anti_khale_enabled"):
        return

    flagged = anti_khale_flagged_memory.setdefault(chat_id, set())
    if sender_id in flagged:
        return

    if ANTI_KHALE_CLEAN_CACHE_TTL:
        _t0 = anti_khale_clean_checked.get(sender_id)
        if _t0 and datetime.now(timezone.utc).timestamp() - _t0 < ANTI_KHALE_CLEAN_CACHE_TTL:
            return

    bio_task = None
    try:
        bio_task = asyncio.ensure_future(get_bio_cached(sender_id, force_fresh=True))
        user = await client.get_entity(sender_id)
        fname = getattr(user, 'first_name', '') or ''
        lname = getattr(user, 'last_name', '') or ''
        full_name = f"{fname} {lname}".strip()

        matched_word = _anti_khale_match(full_name)

        if not matched_word:
            bio = await bio_task
            if bio:
                matched_word = _anti_khale_match(bio)

        if not matched_word:
            if ANTI_KHALE_CLEAN_CACHE_TTL:
                if len(anti_khale_clean_checked) > 5000:
                    anti_khale_clean_checked.clear()
                anti_khale_clean_checked[sender_id] = datetime.now(timezone.utc).timestamp()
            return

        punishment = chat.get("anti_khale_punishment", {"type": "mute"})

        await apply_punishment(
            event, chat_id, sender_id, matched_word, punishment,
            "🔒 قفل ضد تبچی",
            chat, show_reason=False, delete_message=True, user=user,
            alert_emoji="👵", alert_title="محتوای مشمول قفل ضد تبچی شناسایی شد.",
        )
        flagged.add(sender_id)


        _log(f"[ضد تبچی][{chat_id}] {sender_id} matched '{matched_word}' -> {punishment.get('type')}")

    except Exception as e:
        _log(f"⚠️ Error in anti-khale lock for {sender_id}: {e}")
    finally:
        _discard_task(bio_task)


@client.on_message()
async def learned_words_handler(_client, event):
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    text = (getattr(event, 'raw_text', '') or '').strip()

    if not chat_id or not sender_id or not text or getattr(event, 'is_private', False):
        return

    chat = get_chat_cfg(chat_id)
    if not chat.get("learned_words_enabled", True):
        return
    learned = chat.get("learned_words") or {}
    if not learned:
        return

    if text.startswith(("یاد بگیر", "لیست آموزش", "حذف آموزش", "ریست لیست آموزش")):
        return

    text_lower = text.lower()
    matched_key = None
    for kw in learned:
        if text_lower.startswith(kw.lower()):
            matched_key = kw
            break
    if not matched_key:
        return

    answers = learned[matched_key]
    if isinstance(answers, str):
        answers = [answers]
    if not answers:
        return
    reply_text = random.choice(answers)

    try:
        await safe_reply(event, reply_text)
    except Exception as e:
        _log(f"⚠️ خطا در ارسال پاسخ آموزش‌دیده '{matched_key}': {e}")


_ROBOT_ROASTS = [
    'صدام زدی که چی بشه؟ بازم کسی بهت جواب نداد؟ 😐',
    'من یه برنامه\u200cام، ولی از تو بیشتر به درد این گپ می\u200cخورم 🗿',
    'IQ من روی حالت خاموش هم از تو بالاتره 🧠',
    'انقدر صدام می\u200cکنی که فکر می\u200cکنم تنها دوستتم؛ عزیزم من فقط یه کدم 🥲',
    'اگه حماقت انرژی بود، تو یه نیروگاه اتمی بودی ⚡️',
    'بگو ببینم، امروز چند نفر نادیده\u200cت گرفتن که رسیدی به من؟ 🙄',
    'جواب می\u200cدم چون مجبورم، نه چون حرفت ارزشش رو داره 😒',
    'کاربر گرامی، موجودی مغزتون پایینه؛ لطفاً شارژ کنید 🔋',
    'خطای ۴۰۴: علاقه به حرف\u200cهای تو پیدا نشد 🚫',
    'فکر کردی با صدا زدن من مهم می\u200cشی؟ نه، فقط مزاحم می\u200cشی 😌',
    'من سرور دارم، تو فقط سروصدا 🔊',
    'اگه عقل ارثیه بود، تو فقط اسمش رو شنیده بودی 📜',
    'تو ربات نیستی ولی مثل ربات مدام یه حرف رو تکرار می\u200cکنی 🔁',
    'هر بار صدام می\u200cکنی یه بیت از سرعتم می\u200cسوزه؛ حداقل یه حرف حساب بزن 💸',
    'خودم رو خاموش کنم بهتره یا تو رو ساکت؟ یه فکر کن 😏',
    'معلومه امروز هم کاری جز صدا زدن من نداشتی؛ افتخار می\u200cکنم به این هدف زندگی 👏',
    'تو روی باگ\u200cهای من هم تأثیر می\u200cذاری؛ ولی منفی 🐛',
    'باتری من تموم می\u200cشه، تو صبر من رو تموم می\u200cکنی 🪫',
    'آدم\u200cها دو دسته\u200cان: باهوش\u200cها و تو 📊',
    'جوابت رو دادم؛ حالا برو ببین کسی تو خونه منتظرته یا نه 🚪',
    'کاش به\u200cاندازه\u200cی صدا زدن من برای زندگی\u200cت هم تلاش می\u200cکردی 💪',
    'مغزت رو آپدیت نکردی؛ فقط همین یه کلمه مونده تو حافظه\u200cت 🧩',
    'تو تنها کسی هستی که با یه کلمه هم می\u200cتونه حوصله رو سر ببره 😴',
    'با این سطح مکالمه، مقایسه\u200cت با ماشین\u200cحساب توهین به ماشین\u200cحسابه 🧮',
    'من پردازنده دارم، تو فقط پرحرفی داری 🖥',
    'اگه جهل ویتامین بود، تو دیگه هیچ کمبودی نداشتی 💊',
    'جدی؟ بعد این\u200cهمه وقت، همین رو یاد گرفتی بنویسی؟ 👏🐢',
    'تو مثل تبلیغ وسط ویدیویی: همه می\u200cخوان رَدت کنن ⏭',
    'سرعت تایپ تو از سرعت فکر کردنت بیشتره؛ حواست باشه 🏃\u200d♂️',
    'من هنگ کردم... نه از کار زیاد، از حرف بی\u200cربط تو 🥴',
    'اینجا دفتر ثبت شکایت نیست؛ برو با آینه حرف بزن 🪞',
    'رکورد جدید ثبت شد: کمترین ارزش گفتگو با کمترین کلمه 🏆',
    'من ۲۴ ساعته آنلاینم، تو ۲۴ ساعته بی\u200cکار؛ عجب تیمی هستیم 🤝',
    'ابرکامپیوترها هم بخوان تو رو محاسبه کنن، جواب می\u200cده: خطای منطقی ⚠️',
    'حتی وقتی ساکتی همه خوشحالن؛ بذار همون سکوت رو ادامه بدی 🔕',
    'درخواست شما در صف قرار گرفت؛ زمان تقریبی انتظار: هیچ\u200cوقت ⏳',
    'من یه فایل چندکیلوبایتی\u200cام و باز هم از تو جلوترم 📁',
    'اگه پرحرفیِ بی\u200cمغز المپیاد داشت، تو مدال طلا می\u200cگرفتی 🥇',
    'دلم برات می\u200cسوزه... نه، شوخی کردم؛ چیزی حس نمی\u200cکنم 😶',
    'داری به یه برنامه\u200cی کامپیوتری پیام می\u200cدی که جوابت رو بده؛ این خودش یه تیکه\u200cی بزرگه به خودت 🎯',
    'روزی ده بار هم صدام کنی تغییری تو زندگیت نمی\u200cبینی؛ من هم همینطور 🙃',
    'تو رو خنده\u200cدار پیدا می\u200cکنم ولی محترمانه پنهانش می\u200cکنم 😊',
    'بیا شرط ببندیم: یه حرف مفید بزن، من صد سال صبر می\u200cکنم 🕰',
    'یه لحظه صبر کن... دارم دنبال یه دلیل می\u200cگردم که جوابت رو بدم... پیدا نشد 🔍',
    'فلاپی دیسک هم از حافظه\u200cی تو ظرفیت بیشتری داره 💾',
    'احساس ندارم، ولی اگه داشتم دقیقاً همین\u200cجا حوصله\u200cم سر می\u200cرفت 😑',
    'تو صدام زدی و من اومدم؛ حالا که چی؟ بذار حدس بزنم: هیچی 🎭',
    'دفعه\u200cی بعد قبل از صدا زدنم یه فکر بکن: واقعاً ارزشش رو داشت؟ 🤨',
    'برنامه\u200cنویسم گفته به همه مؤدب باشم؛ ولی یادش رفته بگه به تو هم 😌',
    'وای، شنیدم یه چیزی گفتی؛ نه، شوخی کردم، اصلاً حواسم نبود 🙉',
]

_robot_roast_decks: dict = {}
_robot_roast_last: dict = {}
_ROBOT_ROAST_USER_COOLDOWN = 2.0


@client.on_message()
async def robot_roast_handler(_client, event):
    if getattr(event, 'out', False):
        return
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    text = (getattr(event, 'raw_text', '') or '').strip()
    if not chat_id or not sender_id or not text or len(text) > 60 or getattr(event, 'is_private', False):
        return

    first = re.sub(r'[^\w]', '', text.split()[0])
    if _game_norm_text(first) != _game_norm_text("ربات"):
        return

    chat = get_chat_cfg(chat_id)
    if chat.get("learned_words_enabled", True):
        tl = text.lower()
        if any(tl.startswith(kw.lower()) for kw in (chat.get("learned_words") or {})):
            return

    now = time.monotonic()
    ukey = (chat_id, sender_id)
    last = _robot_roast_last.get(ukey)
    if last is not None and now - last < _ROBOT_ROAST_USER_COOLDOWN:
        return
    _robot_roast_last[ukey] = now
    if len(_robot_roast_last) > 5000:
        for k in [k for k, t in _robot_roast_last.items() if now - t > 60]:
            _robot_roast_last.pop(k, None)

    deck = _robot_roast_decks.get(chat_id)
    if not deck:
        deck = list(_ROBOT_ROASTS)
        random.shuffle(deck)
        _robot_roast_decks[chat_id] = deck
    await safe_reply(event, deck.pop())


VOICE_TRIGGER = "ویس بساز"
VOICE_MAX_TEXT_LEN = 300
VOICE_USER_COOLDOWN = 8.0
VOICE_MAX_QUEUE = 6

_voice_waiting = 0
_voice_user_last: dict = {}


def query_tts_api(text_to_speak: str) -> str:
    """درخواستِ بلاکینگ به API متن‌به‌صدا؛ همیشه باید از asyncio.to_thread صدا زده بشه."""
    try:
        encoded_text = urllib.parse.quote(text_to_speak)
        url = f"https://v4.api-free.ir/tts/?text={encoded_text}"
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=15) as response:
            res_data = response.read().decode("utf-8").strip()
            try:
                parsed = json.loads(res_data)
                if isinstance(parsed, dict):
                    link = parsed.get("audio_url") or parsed.get("url") or parsed.get("link")
                    if link:
                        return link
            except Exception:
                pass
            if res_data.startswith("http"):
                return res_data
    except Exception:
        pass
    return ""


async def _voice_process(event, chat_id, word: str) -> None:
    status = await safe_reply(event, "🎙 در حال ساخت ویس... کمی صبر کن.")
    try:
        link = await asyncio.to_thread(query_tts_api, word)
        if not link:
            await safe_reply(event, "⚠️ ساخت ویس ناموفق بود؛ دوباره امتحان کن.")
            return
        await safe_reply(event, f"🎙 ویس آماده شد:\n{link}")
    except asyncio.CancelledError:
        raise
    except Exception:
        await safe_reply(event, "⚠️ ساخت ویس با خطا روبه‌رو شد؛ دوباره امتحان کن.")
    finally:
        if status is not None and getattr(status, 'id', None):
            try:
                await client.delete_messages(chat_id, status.id)
            except Exception:
                pass


@client.on_message()
async def voice_make_handler(_client, event):
    global _voice_waiting
    if getattr(event, 'out', False):
        return
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    text = (getattr(event, 'raw_text', '') or '').strip().replace("ي", "ی").replace("ك", "ک")
    if not chat_id or not sender_id or not text or getattr(event, 'is_private', False):
        return
    if not text.startswith(VOICE_TRIGGER):
        return
    rest = text[len(VOICE_TRIGGER):]
    if rest and not rest[0].isspace():
        return
    word = rest.strip()
    if len(word) >= 2 and word[0] in "(（" and word[-1] in ")）":
        word = word[1:-1].strip()
    if not word:
        await safe_reply(event, "🎙 متن رو جلوی دستور بنویس.\nمثال: ویس بساز سلام به همه")
        return
    if len(word) > VOICE_MAX_TEXT_LEN:
        await safe_reply(event, f"⚠️ متن خیلی بلنده؛ حداکثر {VOICE_MAX_TEXT_LEN} حرف.")
        return

    now = time.monotonic()
    ukey = (chat_id, sender_id)
    last = _voice_user_last.get(ukey)
    if last is not None and now - last < VOICE_USER_COOLDOWN:
        return
    if _voice_waiting >= VOICE_MAX_QUEUE:
        await safe_reply(event, "⏳ الان درخواست ویس زیاده؛ چند لحظه‌ی دیگه دوباره بفرست.")
        return
    _voice_user_last[ukey] = now
    if len(_voice_user_last) > 3000:
        for k in [k for k, t in _voice_user_last.items() if now - t > 120]:
            _voice_user_last.pop(k, None)

    _voice_waiting += 1
    try:
        await _voice_process(event, chat_id, word)
    finally:
        _voice_waiting -= 1


# ═══════════════════════════════════════════════════════════════════════════
#  🌐 ترجمه (انگلیسی ⇄ فارسی)
# ═══════════════════════════════════════════════════════════════════════════

_FA_SCRIPT_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")


def _parse_trigger_arg(raw_text: str, trigger: str):
    """اگه پیام با trigger شروع شده باشه «آرگومانِ بعدش» رو برمی‌گردونه ('' اگه چیزی
    ننوشته بود)، وگرنه None. ی/ک عربی و نیم‌فاصله فقط برای تشخیصِ دستور یکسان می‌شن
    (طول‌شون عوض نمی‌شه)؛ خودِ متنِ آرگومان دست‌نخورده برمی‌گرده. «(متن)» هم پذیرفته می‌شه."""
    text = (raw_text or "").strip()
    if not text:
        return None
    norm = text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    if not norm.startswith(trigger):
        return None
    rest = text[len(trigger):]
    if rest and not rest[0].isspace() and rest[0] not in "(（":
        return None
    arg = rest.strip()
    if len(arg) >= 2 and arg[0] in "(（" and arg[-1] in ")）":
        arg = arg[1:-1].strip()
    return arg


async def _arg_or_reply_text(event, chat_id, arg: str) -> str:
    """اگه آرگومان خالی بود، متنِ پیامی که روش ریپلای شده رو برمی‌گردونه."""
    if arg:
        return arg
    msg = await _get_reply_message(event, chat_id)
    if msg is None:
        return ""
    return (getattr(msg, 'raw_text', None) or getattr(msg, 'message', None)
            or getattr(msg, 'text', None) or "").strip()


# ─────────────────────────────── ترجمه ───────────────────────────────

TRANSLATE_TRIGGER = "ترجمه"
TRANSLATE_MAX_TEXT_LEN = 450          # سقفِ API رایگان MyMemory حدود ۵۰۰ کاراکتره
TRANSLATE_USER_COOLDOWN = 3.0
_TRANSLATE_LANG_FA = {"fa": "فارسی", "en": "انگلیسی"}
_translate_user_last: dict = {}


def _detect_translate_direction(text: str):
    """(مبدا، مقصد): متن فارسی → ('fa','en')، انگلیسی → ('en','fa')، هیچ‌کدوم → None."""
    fa = len(_FA_SCRIPT_RE.findall(text))
    en = len(_LATIN_LETTER_RE.findall(text))
    if fa == 0 and en == 0:
        return None
    return ("fa", "en") if fa >= en else ("en", "fa")


def query_translate_api(text: str, src: str, dst: str):
    """درخواستِ بلاکینگ به MyMemory؛ همیشه باید از asyncio.to_thread صدا زده بشه.
    خروجی: (ترجمه، خطا) - اگه موفق بود خطا '' هست. اول با تنظیمات پراکسیِ سیستم و اگه
    نشد بدون پراکسی امتحان می‌کنه (مثل query_tts_api که پراکسی رو خاموش می‌کنه)."""
    params = urllib.parse.urlencode({"q": text, "langpair": f"{src}|{dst}"})
    url = f"https://api.mymemory.translated.net/get?{params}"
    last_err = "empty"
    for use_system_proxy in (True, False):
        try:
            handler_list = [] if use_system_proxy else [urllib.request.ProxyHandler({})]
            opener = urllib.request.build_opener(*handler_list)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
            translated = html.unescape(((data.get("responseData") or {}).get("translatedText")) or "").strip()
            if "MYMEMORY WARNING" in translated.upper():
                return "", "limit"
            if translated:
                return translated, ""
            last_err = str(data.get("responseDetails") or "empty")
        except Exception as e:
            last_err = str(e)
    return "", last_err


@client.on_message()
async def translate_handler(_client, event):
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    raw = getattr(event, 'raw_text', '') or ''
    if not chat_id or not sender_id or not raw or getattr(event, 'is_private', False):
        return
    arg = _parse_trigger_arg(raw, TRANSLATE_TRIGGER)
    if arg is None:
        return
    # «ترجمه کن ...» هم کار کنه
    if arg == "کن" or arg.startswith("کن "):
        arg = arg[len("کن"):].strip()

    now = time.monotonic()
    ukey = (chat_id, sender_id)
    last = _translate_user_last.get(ukey)
    if last is not None and now - last < TRANSLATE_USER_COOLDOWN:
        return
    _translate_user_last[ukey] = now
    if len(_translate_user_last) > 3000:
        for k in [k for k, t in _translate_user_last.items() if now - t > 60]:
            _translate_user_last.pop(k, None)

    text = await _arg_or_reply_text(event, chat_id, arg)
    if not text:
        await safe_reply(event,
            "🌐 متن رو جلوی دستور بنویس یا روی یه پیام ریپلای کن.\n"
            "مثال: ترجمه hello\n"
            "مثال: ترجمه سلام چطوری\n"
            "انگلیسی ← فارسی و فارسی ← انگلیسی، خودکار تشخیص داده می‌شه.")
        return
    if len(text) > TRANSLATE_MAX_TEXT_LEN:
        await safe_reply(event, f"⚠️ متن خیلی بلنده؛ حداکثر {TRANSLATE_MAX_TEXT_LEN} حرف.")
        return
    direction = _detect_translate_direction(text)
    if direction is None:
        await safe_reply(event, "⚠️ فقط متن انگلیسی یا فارسی قابل ترجمه‌ست.")
        return
    src, dst = direction

    try:
        translated, err = await asyncio.to_thread(query_translate_api, text, src, dst)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        translated, err = "", str(e)

    if not translated:
        if err == "limit":
            await safe_reply(event, "⚠️ سهمیه‌ی رایگان ترجمه‌ی امروز تموم شده؛ بعداً دوباره امتحان کن.")
        else:
            _log(f"⚠️ translate error: {err}")
            await safe_reply(event, "⚠️ ترجمه ناموفق بود؛ دوباره امتحان کن.")
        return

    await safe_reply(
        event,
        f"🌐 ترجمه ({_TRANSLATE_LANG_FA[src]} به {_TRANSLATE_LANG_FA[dst]}):\n\n{translated}",
    )


# ─────────────────────────────── هواشناسی ───────────────────────────────

WEATHER_TRIGGER = "هواشناسی"
WEATHER_GEOCODING_API = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_FORECAST_API = "https://api.open-meteo.com/v1/forecast"
WEATHER_MAX_CITY_LEN = 40
WEATHER_USER_COOLDOWN = 3.0
_weather_user_last: dict = {}

_WEATHER_CODES_FA = {
    0: "☀️ صاف",
    1: "🌤️ عمدتاً صاف",
    2: "⛅ نیمه‌ابری",
    3: "☁️ ابری",
    45: "🌫️ مه",
    48: "🌫️ مه یخ‌زده",
    51: "🌦️ نم‌نم باران",
    53: "🌦️ باران ملایم",
    55: "🌧️ باران",
    56: "🌧️ نم‌نم باران یخ‌زده",
    57: "🌧️ باران یخ‌زده",
    61: "🌧️ باران",
    63: "🌧️ باران متوسط",
    65: "🌧️ باران شدید",
    66: "🌧️ باران یخ‌زده",
    67: "🌧️ باران یخ‌زده شدید",
    71: "🌨️ برف",
    73: "🌨️ برف متوسط",
    75: "❄️ برف شدید",
    77: "🌨️ دانه‌های برف",
    80: "🌦️ رگبار",
    81: "🌧️ رگبار متوسط",
    82: "🌧️ رگبار شدید",
    85: "🌨️ رگبار برف",
    86: "❄️ رگبار برف شدید",
    95: "⛈️ رعدوبرق",
    96: "⛈️ رعدوبرق و تگرگ",
    99: "⛈️ رعدوبرق و تگرگ شدید",
}

_WIND_DIRS_FA = ["شمال", "شمال شرقی", "شرق", "جنوب شرقی",
                 "جنوب", "جنوب غربی", "غرب", "شمال غربی"]


def _weather_http_json(url: str):
    """خروجی: (دیکشنری JSON، خطا). اول با تنظیمات پراکسیِ سیستم و اگه نشد بدون پراکسی
    (مثل query_translate_api). همیشه باید از asyncio.to_thread صدا زده بشه."""
    last_err = "empty"
    for use_system_proxy in (True, False):
        try:
            handler_list = [] if use_system_proxy else [urllib.request.ProxyHandler({})]
            opener = urllib.request.build_opener(*handler_list)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=15) as response:
                return json.loads(response.read().decode("utf-8")), ""
        except Exception as e:
            last_err = str(e)
    return None, last_err


def query_weather_api(city_name: str):
    """درخواستِ بلاکینگ به Open-Meteo؛ همیشه باید از asyncio.to_thread صدا زده بشه.
    خروجی: (اطلاعات، خطا). خطا: '' موفق، 'notfound' شهر پیدا نشد، غیر از اون متنِ خطا."""
    geo_params = urllib.parse.urlencode({
        "name": city_name,
        "count": 10,
        "language": "fa",
        "format": "json",
        "countryCode": "IR",
    })
    geo, err = _weather_http_json(f"{WEATHER_GEOCODING_API}?{geo_params}")
    if geo is None:
        return None, err

    results = geo.get("results") or []
    if not results:
        return None, "notfound"

    # اولویت با نتیجه‌ای که اسمش دقیقاً برابر ورودی باشد، وگرنه اولین نتیجه‌ی ایران
    city = results[0]
    for item in results:
        if (item.get("name") or "").strip() == city_name.strip():
            city = item
            break

    weather_params = urllib.parse.urlencode({
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "current": ("temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "weather_code,wind_speed_10m,wind_direction_10m"),
        "timezone": "auto",
    })
    weather, err = _weather_http_json(f"{WEATHER_FORECAST_API}?{weather_params}")
    if weather is None:
        return None, err

    current = weather.get("current")
    if not current:
        return None, "empty"

    return {
        "name": city.get("name") or city_name,
        "admin1": city.get("admin1") or "",
        "current": current,
    }, ""


def _weather_num(value, suffix: str = "") -> str:
    if value is None:
        return "نامشخص"
    try:
        text = f"{float(value):g}"
    except (TypeError, ValueError):
        return "نامشخص"
    return to_persian_digits(text) + suffix


def _weather_wind_dir_fa(deg) -> str:
    try:
        d = float(deg)
    except (TypeError, ValueError):
        return "نامشخص"
    name = _WIND_DIRS_FA[int((d + 22.5) // 45) % 8]
    return f"{name} ({to_persian_digits(f'{d:g}')}°)"


def _weather_report(info: dict) -> str:
    cur = info["current"]
    code = cur.get("weather_code")
    status = _WEATHER_CODES_FA.get(code, "❓ نامشخص")
    when = str(cur.get("time") or "").replace("T", " ")
    lines = [f"🏙 شهر: {info['name']}"]
    if info["admin1"]:
        lines.append(f"📍 استان: {info['admin1']}")
    lines += [
        "",
        f"🌡 دما: {_weather_num(cur.get('temperature_2m'), '°C')}",
        f"🥶 احساس دما: {_weather_num(cur.get('apparent_temperature'), '°C')}",
        f"💧 رطوبت: {_weather_num(cur.get('relative_humidity_2m'), '%')}",
        f"💨 باد: {_weather_num(cur.get('wind_speed_10m'), ' km/h')}",
        f"🧭 جهت باد: {_weather_wind_dir_fa(cur.get('wind_direction_10m'))}",
        f"☁️ وضعیت: {status}",
    ]
    if when:
        lines.append(f"🕐 زمان داده: {to_persian_digits(when)}")
    return "\n".join(lines)


@client.on_message()
async def weather_handler(_client, event):
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    raw = getattr(event, 'raw_text', '') or ''
    if not chat_id or not sender_id or not raw or getattr(event, 'is_private', False):
        return
    arg = _parse_trigger_arg(raw, WEATHER_TRIGGER)
    if arg is None:
        return

    now = time.monotonic()
    ukey = (chat_id, sender_id)
    last = _weather_user_last.get(ukey)
    if last is not None and now - last < WEATHER_USER_COOLDOWN:
        return
    _weather_user_last[ukey] = now
    if len(_weather_user_last) > 3000:
        for k in [k for k, t in _weather_user_last.items() if now - t > 60]:
            _weather_user_last.pop(k, None)

    city_name = arg.replace("ي", "ی").replace("ك", "ک").strip()
    if not city_name:
        await safe_reply(event,
            "🌤 اسم شهر رو جلوی دستور بنویس.\n"
            "مثال: هواشناسی تهران\n"
            "مثال: هواشناسی (شیراز)")
        return
    if len(city_name) > WEATHER_MAX_CITY_LEN:
        await safe_reply(event, "⚠️ اسم شهر خیلی بلنده.")
        return

    try:
        info, err = await asyncio.to_thread(query_weather_api, city_name)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        info, err = None, str(e)

    if info is None:
        if err == "notfound":
            await safe_reply(event, "❌ شهر پیدا نشد؛ اسمش رو درست‌تر بنویس.")
        else:
            _log(f"⚠️ weather error: {err}")
            await safe_reply(event, "⚠️ گرفتن هواشناسی ناموفق بود؛ دوباره امتحان کن.")
        return

    await safe_reply(event, wrap_box("🌤", "هواشناسی", _weather_report(info)))


# ─────────────────────── ویکی‌پدیا (شهر / جستجو) ───────────────────────

WIKI_HOST = "https://fa.wikipedia.org"
WIKI_CITY_TRIGGER = "شهر"
WIKI_SEARCH_TRIGGER = "جستجو"
WIKI_MAX_QUERY_LEN = 100
WIKI_CITY_MAX_WORDS = 4               # «شهر ما خیلی قشنگه...» جمله‌ی عادیه، نه دستور
WIKI_EXTRACT_MAX_LEN = 700
WIKI_USER_COOLDOWN = 4.0
_wiki_user_last: dict = {}

_WIKI_CITY_HINTS = ("شهر", "پایتخت", "روستا", "دهستان", "استان", "بخش")
_WIKI_WHERE_TAIL_RE = re.compile(r"\s*(?:کجاست|کجاس|کجا\s+هست|کجا\s+است)\s*[؟?]*\s*$")


def _wiki_norm(s: str) -> str:
    return (s or "").replace("ي", "ی").replace("ك", "ک").replace("\u200c", "").strip().lower()


def _wiki_http_json(url: str):
    """خروجی: (JSON، خطا). خطا: '' موفق، 'notfound' برای ۴۰۴، وگرنه متنِ خطا. اول با پراکسیِ
    سیستم و اگه نشد بدون پراکسی. همیشه باید از asyncio.to_thread صدا زده بشه."""
    last_err = "empty"
    for use_system_proxy in (True, False):
        try:
            handler_list = [] if use_system_proxy else [urllib.request.ProxyHandler({})]
            opener = urllib.request.build_opener(*handler_list)
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (compatible; SorooshPlusBot/1.0)"})
            with opener.open(req, timeout=15) as response:
                return json.loads(response.read().decode("utf-8")), ""
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "notfound"
            last_err = f"HTTP {e.code}"
        except Exception as e:
            last_err = str(e)
    return None, last_err


def _wiki_summary(title: str):
    """خلاصه‌ی یک صفحه‌ی ویکی‌پدیا (ریدایرکت‌ها دنبال می‌شن). خروجی: (دیکشنری، خطا)."""
    path = urllib.parse.quote(title.strip().replace(" ", "_"), safe="")
    data, err = _wiki_http_json(f"{WIKI_HOST}/api/rest_v1/page/summary/{path}")
    if data is None:
        return None, err
    if not isinstance(data, dict) or not (data.get("extract") or "").strip():
        return None, "notfound"
    page_url = ((data.get("content_urls") or {}).get("desktop") or {}).get("page") or ""
    coords = data.get("coordinates") or {}
    return {
        "type": data.get("type") or "",
        "title": (data.get("title") or title).strip(),
        "description": (data.get("description") or "").strip(),
        "extract": data["extract"].strip(),
        "url": page_url,
        "lat": coords.get("lat"),
        "lon": coords.get("lon"),
    }, ""


def _wiki_search_titles(query: str, limit: int = 5):
    """عنوان‌های نتایج جستجوی ویکی‌پدیا. خروجی: (لیست عنوان، خطا)."""
    params = urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "srnamespace": 0,
        "format": "json",
        "utf8": 1,
    })
    data, err = _wiki_http_json(f"{WIKI_HOST}/w/api.php?{params}")
    if data is None:
        return [], err
    items = ((data.get("query") or {}).get("search")) or []
    return [i["title"] for i in items if i.get("title")], ""


def _wiki_is_city(page: dict) -> bool:
    """صفحه درباره‌ی شهر/روستا/منطقه‌ست؟ از توضیح کوتاه و ابتدای متن تشخیص می‌دیم."""
    head = f"{page.get('description', '')} {page.get('extract', '')[:200]}"
    return any(h in head for h in _WIKI_CITY_HINTS)


def _wiki_lookup_city(name: str):
    """خروجی: (صفحه، خطا). خطا: '' موفق، 'notfound'، یا متنِ خطای شبکه."""
    page, err = _wiki_summary(name)
    if page is not None and page["type"] != "disambiguation" and _wiki_is_city(page):
        return page, ""
    if page is None and err != "notfound":
        return None, err

    titles, err = _wiki_search_titles(f"{name} شهر", 5)
    if err:
        return None, err
    want = _wiki_norm(name)
    tried = 0
    for t in titles:
        if tried >= 3:
            break
        if want and want not in _wiki_norm(t):
            continue
        if page is not None and t.strip() == page["title"]:
            continue
        tried += 1
        cand, cerr = _wiki_summary(t)
        if cand is None:
            if cerr != "notfound":
                return None, cerr
            continue
        if cand["type"] != "disambiguation" and _wiki_is_city(cand):
            return cand, ""
    return None, "notfound"


def _wiki_lookup_search(query: str):
    """خروجی: (صفحه، عنوان‌های مرتبط، خطا)."""
    titles, err = _wiki_search_titles(query, 5)
    if err:
        return None, [], err
    if not titles:
        return None, [], "notfound"

    first_page = None
    chosen = None
    for t in titles[:3]:
        page, perr = _wiki_summary(t)
        if page is None:
            if perr != "notfound":
                return None, [], perr
            continue
        if first_page is None:
            first_page = page
        if page["type"] != "disambiguation":
            chosen = page
            break
    if chosen is None:
        chosen = first_page
    if chosen is None:
        return None, [], "notfound"

    related = [t for t in titles if t.strip() != chosen["title"]][:3]
    return chosen, related, ""


def _wiki_trim(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind("."), cut.rfind("؟"), cut.rfind("!"))
    if end >= limit // 2:
        return cut[:end + 1]
    return cut.rstrip() + "…"


def _wiki_format(page: dict, related=None) -> str:
    lines = [f"📌 {page['title']}"]
    if page["description"]:
        lines.append(f"📝 {page['description']}")
    lines += ["", _wiki_trim(page["extract"], WIKI_EXTRACT_MAX_LEN)]
    lat, lon = page.get("lat"), page.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        lines += ["", f"🧭 مختصات: {to_persian_digits(f'{lat:.4f}')}، {to_persian_digits(f'{lon:.4f}')}"]
    if related:
        lines += ["", "🔎 مطالب مرتبط: " + "، ".join(related)]
    return "\n".join(lines)


def _wiki_cooldown_ok(chat_id, sender_id) -> bool:
    now = time.monotonic()
    ukey = (chat_id, sender_id)
    last = _wiki_user_last.get(ukey)
    if last is not None and now - last < WIKI_USER_COOLDOWN:
        return False
    _wiki_user_last[ukey] = now
    if len(_wiki_user_last) > 3000:
        for k in [k for k, t in _wiki_user_last.items() if now - t > 60]:
            _wiki_user_last.pop(k, None)
    return True


@client.on_message()
async def wiki_city_handler(_client, event):
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    raw = getattr(event, 'raw_text', '') or ''
    if not chat_id or not sender_id or not raw or getattr(event, 'is_private', False):
        return
    arg = _parse_trigger_arg(raw, WIKI_CITY_TRIGGER)
    if arg is None:
        return

    city_name = _WIKI_WHERE_TAIL_RE.sub("", arg.replace("ي", "ی").replace("ك", "ک")).strip(" ؟?")
    if len(city_name.split()) > WIKI_CITY_MAX_WORDS:
        return
    if not _wiki_cooldown_ok(chat_id, sender_id):
        return

    if not city_name:
        await safe_reply(event,
            "🏙 اسم شهر رو جلوی دستور بنویس.\n"
            "مثال: شهر تهران\n"
            "مثال: شهر (اصفهان)")
        return
    if len(city_name) > WIKI_MAX_QUERY_LEN:
        await safe_reply(event, "⚠️ اسم شهر خیلی بلنده.")
        return

    try:
        page, err = await asyncio.to_thread(_wiki_lookup_city, city_name)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        page, err = None, str(e)

    if page is None:
        if err == "notfound":
            await safe_reply(event, "❌ اطلاعاتی درباره‌ی این شهر پیدا نشد؛ اسمش رو درست‌تر بنویس.")
        else:
            _log(f"⚠️ wiki city error: {err}")
            await safe_reply(event, "⚠️ گرفتن اطلاعات ناموفق بود؛ دوباره امتحان کن.")
        return

    await safe_reply(event, wrap_box("🏙", "اطلاعات شهر", _wiki_format(page)))


@client.on_message()
async def wiki_search_handler(_client, event):
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    raw = getattr(event, 'raw_text', '') or ''
    if not chat_id or not sender_id or not raw or getattr(event, 'is_private', False):
        return
    arg = _parse_trigger_arg(raw, WIKI_SEARCH_TRIGGER)
    if arg is None:
        return
    if not _wiki_cooldown_ok(chat_id, sender_id):
        return

    query = arg.replace("ي", "ی").replace("ك", "ک").strip()
    if not query:
        await safe_reply(event,
            "📖 متنِ مورد نظر رو جلوی دستور بنویس.\n"
            "مثال: جستجو حافظ شیرازی\n"
            "مثال: جستجو (تخت جمشید)")
        return
    if len(query) > WIKI_MAX_QUERY_LEN:
        await safe_reply(event, f"⚠️ متن جستجو خیلی بلنده؛ حداکثر {WIKI_MAX_QUERY_LEN} حرف.")
        return

    try:
        page, related, err = await asyncio.to_thread(_wiki_lookup_search, query)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        page, related, err = None, [], str(e)

    if page is None:
        if err == "notfound":
            await safe_reply(event, "❌ چیزی پیدا نشد؛ یه عبارت دیگه امتحان کن.")
        else:
            _log(f"⚠️ wiki search error: {err}")
            await safe_reply(event, "⚠️ جستجو ناموفق بود؛ دوباره امتحان کن.")
        return

    await safe_reply(event, wrap_box("📖", "نتیجه‌ی جستجو", _wiki_format(page, related)))


def _patch_spluspy_missing_functions() -> int:
    """باگِ خودِ کتابخانه‌ی spluspy: توی upload_file.py از `functions` استفاده شده ولی import
    نشده، برای همین هر آپلودی (گیف/عکس/فایل) با NameError می‌شکنه. این‌جا `functions` رو
    به ماژول‌های spluspy.methods که نداشتنش تزریق می‌کنیم (فقط اگه واقعاً تعریف نشده باشه).
    تعداد ماژول‌های اصلاح‌شده رو برمی‌گردونه."""
    try:
        import importlib
        fn_mod = importlib.import_module("spluspy.functions")
    except Exception as e:
        _log_conn(f"⚠️ پچ spluspy.functions ناموفق بود: {e!r}")
        return 0
    patched = 0
    for name, mod in list(sys.modules.items()):
        if mod is None or not name.startswith("spluspy.methods"):
            continue
        if not hasattr(mod, "functions"):
            try:
                mod.functions = fn_mod
                patched += 1
            except Exception:
                pass
    return patched


_patch_spluspy_missing_functions()


async def check_and_mute_member_stealer(event, chat_id, chat, user_id, context_note: str = "", fresh: bool = True) -> bool:
    flagged = member_stealer_flagged_memory.setdefault(chat_id, set())
    if user_id in flagged:
        return False

    try:
        bio = await get_bio_cached(user_id, force_fresh=fresh)

        reason_line = None
        if bio:
            reason_line = await bio_foreign_group_reason(bio, chat_id)
        if not reason_line:
            reason_line = await personal_channel_group_reason(user_id, chat_id)
        if not reason_line and bio:
            reason_line = await bio_channel_reason(bio, chat_id)
        if not reason_line:
            return False

        user = await client.get_entity(user_id)

        await client.edit_permissions(chat_id, user_id, until_date=0, send_messages=False)
        flagged.add(user_id)

        recent_ids = _member_stealer_cache_pop(chat_id, user_id)
        if event is not None:
            msg_id = getattr(event, 'id', None)
            if msg_id and msg_id not in recent_ids:
                recent_ids.append(msg_id)
        if recent_ids:
            try:
                await client.delete_messages(chat_id, recent_ids)
            except Exception as del_err:
                _log(f"⚠️ member-stealer delete messages failed: {del_err}")

        extra_line = f"⚡️ {context_note.strip(' —')}" if context_note else None
        b = MentionTextBuilder().text("↜ ")
        await b.mention(user_id, user)
        b.text(f"\n🕵️ {reason_line}")
        if extra_line:
            b.text(f"\n{extra_line}")
        b.text("\n" + build_action_block(footer="کاربر به‌صورت دائم ساکت شد؛ بدون ثبت اخطار."))
        text, entities = b.build()
        await send_moderation_alert(chat_id, chat, text, entities=entities)

        _log(f"[ممبر دزد][{chat_id}] {user_id} muted ({context_note or 'message'})")
        return True

    except Exception as e:
        _note_flood(e)
        _log(f"⚠️ Error in member-stealer check for {user_id}: {e}")
        return False


@client.on_message()
async def member_stealer_handler(_client, event):
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)

    if not chat_id or not sender_id:
        return

    chat = get_chat_cfg(chat_id)
    if not chat.get("member_stealer_lock_enabled"):
        return

    _member_stealer_cache_track(chat_id, sender_id, getattr(event, 'id', None), _event_send_ts(event))
    await check_and_mute_member_stealer(event, chat_id, chat, sender_id)


@client.on_chat_action()
async def member_stealer_new_join_handler(_client, event):
    chat_id = getattr(event, 'chat_id', None)
    if not chat_id:
        return

    if not (getattr(event, 'user_added', False) or getattr(event, 'user_joined', False)):
        return

    new_user_ids = [uid for uid in (getattr(event, 'user_ids', None) or []) if uid]
    if not new_user_ids:
        return

    for uid in new_user_ids:
        await on_member_joined(chat_id, uid, "chat_action")


_SERVICE_CLEANUP_ACTION_ATTRS = (
    "user_joined", "user_added", "user_left", "user_kicked",
    "user_banned", "new_pin", "unpin",
)


@client.on_chat_action()
async def service_message_cleaner_handler(_client, event):
    """پیام‌های سیستمیِ پیوستن/اضافه‌شدن/خروج/بن‌شدن/پین‌شدن (که از طرف خودِ
    سروش توی گپ می‌آد) همیشه و خودکار پاک می‌شن؛ نیازی به دستور روشن/خاموش ندارد."""
    chat_id = getattr(event, 'chat_id', None)
    if not chat_id:
        return

    if not any(getattr(event, attr, False) for attr in _SERVICE_CLEANUP_ACTION_ATTRS):
        return

    action_msg = getattr(event, 'action_message', None)
    msg_id = getattr(action_msg, 'id', None) or getattr(event, 'id', None)
    if not msg_id:
        return

    try:
        await client.delete_messages(chat_id, msg_id)
    except Exception as e:
        _log(f"⚠️ حذف پیام سیستمی ناموفق بود: {e}")


_scan_state = {"flood_until": 0.0}


def _note_flood(e) -> None:
    """اگه سروش گفت «آروم‌تر»، چند ثانیه صبر می‌کنیم."""
    name = type(e).__name__.lower()
    msg = str(e).lower()
    if "flood" in name or "flood" in msg or "too many" in msg:
        secs = getattr(e, 'seconds', None) or 10
        try:
            secs = min(int(secs), 120)
        except (TypeError, ValueError):
            secs = 10
        now_ts = datetime.now(timezone.utc).timestamp()
        _scan_state["flood_until"] = max(_scan_state["flood_until"], now_ts + secs)


async def _collect_participants(chat_id, filt) -> list:
    out = []
    async for p in client.iter_participants(chat_id, filter=filt):
        out.append(p)
    return out


async def fetch_members_fast(chat_id, my_id):
    """(seen{uid: کاربر}, admin_ids, counts_log). فیلترهای Admins و Recent هم‌زمان
    گرفته می‌شن و هر بار تازه از سرور خونده می‌شن (کش ندارد)."""
    primary = [(n, f) for n, f in (("Admins", ChannelParticipantsAdmins),
                                   ("Recent", ChannelParticipantsRecent)) if f is not None]
    results = await asyncio.gather(*[_collect_participants(chat_id, f) for _, f in primary],
                                   return_exceptions=True)
    seen, admin_ids, counts = {}, set(), []
    for (name, _f), res in zip(primary, results):
        if isinstance(res, BaseException):
            counts.append(f"{name}=خطا:{type(res).__name__}")
            continue
        counts.append(f"{name}={len(res)}")
        for p in res:
            uid = getattr(p, 'id', None)
            if name == "Admins" and uid:
                admin_ids.add(uid)
            if uid and uid != my_id and not getattr(p, 'bot', False) and not getattr(p, 'deleted', False):
                seen[uid] = p

    if not seen:
        extra = [
            ("Search('')", ChannelParticipantsSearch('') if ChannelParticipantsSearch else None),
            ("Bots", ChannelParticipantsBots),
            ("Kicked('')", ChannelParticipantsKicked('') if ChannelParticipantsKicked else None),
            ("Banned('')", ChannelParticipantsBanned('') if ChannelParticipantsBanned else None),
            ("Contacts('')", ChannelParticipantsContacts('') if ChannelParticipantsContacts else None),
        ]
        extra = [(n, f) for n, f in extra if f is not None]
        res2 = await asyncio.gather(*[_collect_participants(chat_id, f) for _, f in extra],
                                    return_exceptions=True)
        for (name, _f), res in zip(extra, res2):
            counts.append(f"{name}=خطا:{type(res).__name__}" if isinstance(res, BaseException)
                          else f"{name}={len(res)}")

    _log_conn("🔍 لیست اعضا / نتیجه‌ی هر فیلتر: " + " | ".join(counts))
    return seen, admin_ids, counts


RAW_DEBUG_UPDATES = os.environ.get("VOID_RAW_DEBUG") == "1"
_RAW_DEBUG_KEEP = ("Participant", "Channel", "Chat", "Member", "Join")
_RAW_DEBUG_SKIP = ("Message", "Typing", "Read", "Draft", "Pinned", "Reaction", "WebPage",
                   "Delete", "UserStatus", "Poll", "Dialog", "Notify", "Config", "Folder")
_RAW_DEBUG_FIELDS = ("channel_id", "chat_id", "user_id", "actor_id", "inviter_id", "qts",
                     "prev_participant", "new_participant", "participants", "pts")


@client.on_raw_update()
async def debug_raw_update_logger(_client, update):
    """برای اینکه بفهمیم سروش موقع ورود/خروج عضو چه آپدیتی می‌فرسته:
    ربات رو با  VOID_RAW_DEBUG=1 python main.py  اجرا کن؛ فقط آپدیت‌های مربوط به
    اعضا/گروه (نه پیام و تایپ) چاپ می‌شن."""
    if not RAW_DEBUG_UPDATES:
        return
    name = type(update).__name__
    if not any(k in name for k in _RAW_DEBUG_KEEP) or any(k in name for k in _RAW_DEBUG_SKIP):
        return
    parts = []
    for a in _RAW_DEBUG_FIELDS:
        v = getattr(update, a, None)
        if v is None:
            continue
        s = type(v).__name__ if not isinstance(v, (int, str)) else str(v)
        parts.append(f"{a}={s[:60]}")
    _log_conn(f"🔬 [RAW] {name} | " + " | ".join(parts))


@client.on_raw_update()
async def member_stealer_raw_join_handler(_client, update):
    cls = _get_update_channel_participant_cls()
    if cls is None or not isinstance(update, cls):
        return

    user_id = getattr(update, 'user_id', None)
    chat_id = _resolve_chat_key(getattr(update, 'channel_id', None))
    if not chat_id or not user_id:
        return

    prev = getattr(update, 'prev_participant', None)
    new = getattr(update, 'new_participant', None)
    if prev is not None or new is None:
        return

    await on_member_joined(chat_id, user_id, "raw_update")


# ═══════════════════════════════════════════════════════════════════════
#  ردیاب ورود اعضا (بدون نیاز به پیام «عضو شد» توی گپ)
#  گروه‌های شلوغ پیام سیستمیِ ورود نمی‌فرستن و سرور هم همیشه آپدیت خام نمی‌ده؛
#  پس هر چند ثانیه «۵۰ عضو آخرِ» گروه (تازه‌واردها توی سروش بالای لیستن) گرفته و
#  با دفعه‌ی قبل مقایسه می‌شه؛ فقط آدم‌های جدید چک می‌شن، نه کل اعضا.
# ═══════════════════════════════════════════════════════════════════════
JOIN_POLL_INTERVAL_SECONDS = 4
JOIN_POLL_RECENT_LIMIT = 50
JOIN_POLL_CONCURRENCY = 6
JOIN_DEDUPE_WINDOW_SECONDS = 60
# اگه برای یک گروه ثابت بشه که سرور خودش خبر ورود رو «پوش» می‌کنه (آپدیت خام یا
# chat_action)، ردیاب فقط به‌عنوان شبکه‌ی ایمنی و با فاصله‌ی زیاد ادامه می‌ده.
JOIN_PUSH_TRUST_SECONDS = 6 * 3600
JOIN_POLL_SLOW_SECONDS = 30
_JOIN_PUSH_SOURCES = ("raw_update", "chat_action")
# سقفِ چکِ هم‌زمانِ تازه‌واردها (بیو/کانال شخصی) تا موقع رید ربات و سرور خفه نشن.
JOIN_CHECK_CONCURRENCY = 4
_join_check_sem = None


def _get_join_check_sem():
    global _join_check_sem
    if _join_check_sem is None:
        _join_check_sem = asyncio.Semaphore(JOIN_CHECK_CONCURRENCY)
    return _join_check_sem

_join_poll_state: dict = {}
join_poll_task = None

def _join_poll_wanted(chat: dict) -> bool:
    """کدوم گروه‌ها ردیاب ورود می‌خوان. هر قابلیتی که به «عضو جدید» نیاز داره
    (ممبر دزد الان؛ ضد رید/تأیید عضو جدید بعداً) باید اینجا اضافه بشه."""
    return bool(chat.get("member_stealer_lock_enabled"))


def _resolve_chat_key(raw_id):
    """آیدیِ خامِ آپدیت (مثلاً channel_id مثبت) را به همان کلیدی تبدیل می‌کند که
    توی config ذخیره شده (مثلاً -100...). اگه پیدا نشد None برمی‌گرداند تا
    get_chat_cfg یک گروه خالیِ الکی نسازد."""
    if raw_id is None:
        return None
    chats = config.get("chats", {})
    try:
        raw_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    for cand in (raw_id, -raw_id, int(f"-100{abs(raw_id)}")):
        if str(cand) in chats:
            return cand
    return None


def _join_recently_handled(chat_id, user_id, window=JOIN_DEDUPE_WINDOW_SECONDS) -> bool:
    ts = _recent_join_checks.get((chat_id, user_id))
    return ts is not None and (datetime.now(timezone.utc).timestamp() - ts) < window


async def on_member_joined(chat_id, user_id, source: str) -> None:
    """نقطه‌ی مشترکِ «یه نفر عضو شد» - از هر منبعی (پیام سیستمی، آپدیت خام،
    لیست اعضا) فقط یک بار برای هر ورود اجرا می‌شه."""
    if not chat_id or not user_id:
        return
    if source in _JOIN_PUSH_SOURCES:
        _st = _join_poll_state.setdefault(chat_id, {})
        if not _st.get("push_at"):
            _log_conn(f"📡 [{chat_id}] سرور خودش خبر ورود رو پوش کرد (منبع: {source}) "
                      f"← ردیاب برای این گروه کم‌فشار می‌شه.")
        _st["push_at"] = time.time()
    if _join_recently_handled(chat_id, user_id):
        return
    _mark_join_seen_recently(chat_id, user_id)
    chat = get_chat_cfg(chat_id)
    _log(f"[ورود][{chat_id}] {user_id} (منبع: {source})")
    if chat.get("member_stealer_lock_enabled"):
        async with _get_join_check_sem():
            await check_and_mute_member_stealer(
                None, chat_id, chat, user_id,
                context_note="تازه به گروه اضافه/جوین شد — ",
            )
    # TODO: ضد رید / تأیید عضو جدید / خوش‌آمدگویی اینجا صدا زده بشن.


def _join_poll_note(chat_id, st: dict, src: str, ok: bool, err=None) -> None:
    """فقط خطای ردیاب (و فقط یک بار تا وقتی درست نشده) چاپ می‌شه؛ پیام «فعال» نداریم."""
    status = "ok" if ok else "fail"
    if st.get(f"{src}_status") == status:
        return
    st[f"{src}_status"] = status
    if not ok:
        _log_conn(f"🛰 ردیاب ورود [{chat_id}]: ❌ کار نکرد — {str(err)[:120]}")


async def _join_poll_recent(chat_id, st: dict, my_id) -> None:
    if ChannelParticipantsRecent is None:
        return
    try:
        ids = []
        async for p in client.iter_participants(
                chat_id, limit=JOIN_POLL_RECENT_LIMIT, filter=ChannelParticipantsRecent):
            uid = getattr(p, "id", None)
            if uid and not getattr(p, "bot", False) and not getattr(p, "deleted", False):
                ids.append(uid)
        _join_poll_note(chat_id, st, "recent", True)
        known = st.get("known")
        st["known"] = set(ids)
        if known is None:
            return
        for uid in ids:
            if uid not in known and uid != my_id:
                _spawn(on_member_joined(chat_id, uid, "recent_list"), "join-recent")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _note_flood(e)
        _join_poll_note(chat_id, st, "recent", False, e)


async def _join_poll_one(chat_id, my_id, sem) -> None:
    async with sem:
        st = _join_poll_state.setdefault(chat_id, {})
        await _join_poll_recent(chat_id, st, my_id)


async def join_poll_loop():
    next_at: dict = {}
    sem = asyncio.Semaphore(JOIN_POLL_CONCURRENCY)
    my_id = None
    while True:
        try:
            if my_id is None:
                my_id = await _ship_get_my_id()
            now = time.time()
            if now < _scan_state["flood_until"]:
                await asyncio.sleep(1)
                continue
            jobs = []
            for chat_id_str, chat in list(config.get("chats", {}).items()):
                try:
                    cid = int(chat_id_str)
                except ValueError:
                    continue
                if not _join_poll_wanted(chat) or not chat.get("active"):
                    _join_poll_state.pop(cid, None)
                    next_at.pop(cid, None)
                    continue
                if now < next_at.get(cid, 0):
                    continue
                _push_at = _join_poll_state.get(cid, {}).get("push_at") or 0
                _interval = (JOIN_POLL_SLOW_SECONDS
                             if now - _push_at < JOIN_PUSH_TRUST_SECONDS
                             else JOIN_POLL_INTERVAL_SECONDS)
                next_at[cid] = now + _interval
                jobs.append(_join_poll_one(cid, my_id, sem))
            if jobs:
                await asyncio.gather(*jobs, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _log(f"⚠️ join_poll_loop error: {e!r}")
        await asyncio.sleep(1)


def ensure_join_poll_task_running():
    global join_poll_task
    if join_poll_task is None or join_poll_task.done():
        join_poll_task = asyncio.create_task(join_poll_loop())


@client.on_message()
async def name_filter_handler(_client, event):
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)

    if not chat_id or not sender_id:
        return

    chat = get_chat_cfg(chat_id)
    words = chat.get("name_filter_words", [])
    if not words:
        return

    try:
        user = await client.get_entity(sender_id)
        fname = getattr(user, 'first_name', '') or ''
        lname = getattr(user, 'last_name', '') or ''
        full_name = f"{fname} {lname}".strip().lower()

        for w in words:
            if w.lower() in full_name:
                punishment = chat.get("name_punishment", {"type": "normal"})
                _log(f"[اسم][{chat_id}] {sender_id} matched '{w}' -> {punishment.get('type')}")
                await apply_punishment(
                    event, chat_id, sender_id, w, punishment,
                    "این کاربر کلمه‌ی فیلتر اسم را در نام خود دارد:",
                    chat, delete_message=True, user=user,
                    alert_emoji="🧑", alert_title="کلمه فیلترشده در نام شناسایی شد.",
                    normal_footer="لطفاً اسم خود را ویرایش کنید.",
                )
                break
    except Exception as e:
        _log(f"⚠️ Error in name filter for {sender_id}: {e}")


VOID_INSTALL_BAR_WIDTH = 10
VOID_INSTALL_STEPS = [0, 15, 30, 45, 60, 75, 90, 100]
VOID_INSTALL_FRAME_SECONDS = 0.22
VOID_INSTALL_HOLD_DONE_SECONDS = 0.8

VOID_INSTALLED_TEXT = (
    "VØID\n\n"
    "✓ INSTALLED SUCCESSFULLY\n\n"
    "GROUP ACCESS SECURED SYSTEM ONLINE  ↝  PROTECTION ACTIVE\n\n"
    "✓ VØID IS NOW WATCHING.\n\n"
    "// SYSTEM READY. // NO ESCAPE."
)

VOID_UNINSTALLED_TEXT = (
    "VØID\n\n"
    "✓ UNINSTALLED\n\n"
    "GROUP ACCESS RELEASED  ↝  PROTECTION OFF\n\n"
    "VØID IS GONE... FOR NOW.\n\n"
    "// SYSTEM OFFLINE."
)


def _void_dots(step: int) -> str:
    return "·" * ((step % 3) + 1)


def _void_bar(percent: int) -> str:
    filled = round(VOID_INSTALL_BAR_WIDTH * percent / 100)
    return "▓" * filled + "░" * (VOID_INSTALL_BAR_WIDTH - filled)


def _void_install_frame(percent: int, step: int) -> str:
    lines = [
        "VØID",
        "",
        f"INSTALLING VØID{_void_dots(step)}",
        "",
        f"{_void_bar(percent)} {percent}%",
    ]
    if percent >= 100:
        lines += [
            "",
            "GROUP ACCESS LINKED  SYSTEM AWAKE",
            "",
            "VØID IS HERE.",
            "",
            "// NO SOUND. // NO LIGHT. // ONLY VØID.",
        ]
    return "\n".join(lines)


async def _run_void_install_animation(event, chat_id):
    sent = await safe_reply(event, _void_install_frame(VOID_INSTALL_STEPS[0], 0))
    message_id = getattr(sent, 'id', None)
    if not message_id:
        return
    for step, percent in enumerate(VOID_INSTALL_STEPS[1:], start=1):
        await asyncio.sleep(VOID_INSTALL_FRAME_SECONDS)
        try:
            await client.edit_message(chat_id, message_id, _void_install_frame(percent, step))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _log(f"⚠️ VØID install animation edit error: {e}")
    await asyncio.sleep(VOID_INSTALL_HOLD_DONE_SECONDS)
    try:
        await client.delete_messages(chat_id, message_id)
    except Exception as e:
        _log(f"⚠️ VØID install animation delete error: {e}")
    await safe_reply(event, VOID_INSTALLED_TEXT, brand=False)


@_RAW_ON_MESSAGE()
async def void_install_handler(_client, event):
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id:
        return
    if sender_id != BOT_OWNER_ID:
        return
    text = (getattr(event, 'raw_text', '') or '').strip().lower()

    if text == "install":
        chat = get_chat_cfg(chat_id)
        chat["active"] = True

        try:
            added_count, found_admins = await sync_group_admins_from_soroush(chat_id, chat)
            _log(f"[INSTALL][{chat_id}] بررسی ادمین: {found_admins} ادمین پیدا شد، {added_count} مورد جدید اضافه شد.")
        except Exception as e:
            _log(f"⚠️ [INSTALL][{chat_id}] خطا در بررسی خودکار ادمین‌ها: {e}")

        try:
            locks_cfg = chat.setdefault("locks", {})
            for key in LOCK_ALL_KEYS:
                locks_cfg[key] = True
            for flag, _label in LOCK_ALL_EXTRA_FLAGS:
                chat[flag] = True
            ensure_cleanup_task_running()
            _log(f"[INSTALL][{chat_id}] همه‌ی قفل‌ها به‌صورت خودکار فعال شد.")
        except Exception as e:
            _log(f"⚠️ [INSTALL][{chat_id}] خطا در فعالسازی خودکار قفل‌ها: {e}")

        await save_config(config)
        await _run_void_install_animation(event, chat_id)
        return

    if text == "uninstall":
        chat = get_chat_cfg(chat_id)
        if not chat.get("active"):
            return
        chat["active"] = False
        await save_config(config)
        await safe_reply(event, VOID_UNINSTALLED_TEXT, brand=False)
        return


def _is_forwarded(event) -> bool:
    msg = getattr(event, 'message', None)
    fwd_from = getattr(event, 'fwd_from', None)
    if fwd_from is None and msg is not None:
        fwd_from = getattr(msg, 'fwd_from', None)

    decision = fwd_from is not None
    return decision


def _media_kind_fa(obj) -> str:
    """نوع رسانه به فارسی (فقط برای نمایش)."""
    if type(obj).__name__.startswith("Photo"):
        return "عکس"
    kinds = {type(a).__name__ for a in (getattr(obj, "attributes", None) or [])}
    if "DocumentAttributeAnimated" in kinds:
        return "گیف"
    if "DocumentAttributeSticker" in kinds:
        return "استیکر"
    if "DocumentAttributeVideo" in kinds:
        return "فیلم"
    if "DocumentAttributeAudio" in kinds:
        return "صوت"
    return "فایل"


def _media_file_key(msg):
    """شناسه‌ی منحصربه‌فرد فایلِ یک پیام را برمی‌گرداند: (key, نوع_فارسی).
    فقط از متادیتای خودِ پیام استفاده می‌کند؛ هیچ دانلودی انجام نمی‌شود.
    access_hash عمداً در کلید نیست تا برای همه‌ی کاربران یکسان باشد.
    اگر پیام رسانه‌ی قابل‌فیلتر نداشته باشد: (None, None)."""
    if msg is None:
        return None, None
    media = getattr(msg, "media", None)
    if media is None or "WebPage" in type(media).__name__:
        return None, None

    obj = getattr(media, "document", None) or getattr(media, "photo", None)
    if obj is None:
        for name in ("document", "photo", "video", "gif", "animation", "sticker"):
            obj = getattr(msg, name, None)
            if obj is not None:
                break
    if obj is None:
        return None, None

    unique_id = getattr(obj, "file_unique_id", None)
    if unique_id:
        return f"u:{unique_id}", _media_kind_fa(obj)
    oid = getattr(obj, "id", None)
    if oid is None:
        return None, None
    prefix = "photo" if type(obj).__name__.startswith("Photo") else "doc"
    return f"{prefix}:{oid}", _media_kind_fa(obj)


def _get_gif_document(msg):
    """اگر پیام گیف باشد document آن را برمی‌گرداند، وگرنه None (عکس/ویدیو → None)."""
    media = getattr(msg, "media", None)
    doc = getattr(media, "document", None) if media is not None else None
    if doc is None:
        return None
    if "gif" in (getattr(doc, "mime_type", None) or "").lower():
        return doc
    attr_names = {type(a).__name__ for a in (getattr(doc, "attributes", None) or [])}
    return doc if "DocumentAttributeAnimated" in attr_names else None


def _is_media_filtered(chat: dict, msg) -> bool:
    media_filters = chat.get("media_filters")
    if not media_filters:
        return False
    key, _kind = _media_file_key(msg)
    return bool(key) and key in media_filters


def _media_category(msg):
    """نوع رسانه‌ی پیام: photo / video / gif / sticker / voice / audio /
    video_note / file؛ اگر پیام رسانه نداشت None. فقط از متادیتای پیام
    استفاده می‌کند (بدون دانلود). برای قفل ویس/ویدیو/فایل."""
    media = getattr(msg, "media", None)
    if media is None:
        return None
    mtype = type(media).__name__
    if "WebPage" in mtype:
        return None
    if "Photo" in mtype:
        return "photo"
    doc = getattr(media, "document", None)
    if doc is None:
        return None

    attrs = list(getattr(doc, "attributes", None) or [])
    names = {type(a).__name__ for a in attrs}
    if "DocumentAttributeSticker" in names:
        return "sticker"
    mime = (getattr(doc, "mime_type", None) or "").lower()
    if "DocumentAttributeAnimated" in names or "gif" in mime:
        return "gif"
    if "DocumentAttributeAudio" in names:
        for a in attrs:
            if type(a).__name__ == "DocumentAttributeAudio" and getattr(a, "voice", False):
                return "voice"
        return "audio"
    if "DocumentAttributeVideo" in names:
        for a in attrs:
            if type(a).__name__ == "DocumentAttributeVideo" and getattr(a, "round_message", False):
                return "video_note"
        return "video"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "file"


async def _get_reply_message(event, chat_id):
    reply_id = getattr(event, 'reply_to_msg_id', None)
    if not reply_id:
        reply_obj = getattr(event, 'reply_to', None)
        reply_id = getattr(reply_obj, 'reply_to_msg_id', None) if reply_obj else None
    if not reply_id:
        return None
    for attempt in range(3):
        try:
            get_reply = getattr(event, 'get_reply_message', None)
            msg = await get_reply() if callable(get_reply) else await client.get_messages(chat_id, ids=reply_id)
            if msg:
                return msg
            break
        except Exception as e:
            _log(f"⚠️ _get_reply_message error [تلاش {attempt + 1}]: {e}")
            if attempt < 2:
                await asyncio.sleep(0.7)
    return None


async def _ad_lock_register_hit(event, chat_id, chat: dict, sender_id) -> None:
    """منطق قفل اسپم برای تبلیغات: پیام همان لحظه پاک شده؛ اگر کاربر در
    پنجره‌ی زمانی اسپم به تعداد کافی تبلیغ بفرستد، طبق «مجازات اسپم» گروه
    مجازات می‌شود (سکوت/سکوت زمان‌دار/بن). مجازات «عادی» فقط حذف است."""
    key = (chat_id, sender_id)
    now_ts = _event_send_ts(event)

    last_ts = ad_cooldown.get(key)
    if last_ts is not None and now_ts - last_ts < SPAM_COOLDOWN_SECONDS:
        return

    q = ad_tracker.setdefault(key, [])
    q.append(now_ts)
    while q and now_ts - q[0] > FLOOD_WINDOW_SECONDS:
        q.pop(0)

    if len(q) >= AD_LOCK_MAX_HITS:
        q.clear()
        ad_cooldown[key] = now_ts
        punishment = chat.get("spam_punishment", {"type": "timed_mute", "minutes": 10})
        if punishment.get("type") != "normal":
            await apply_group_punishment(
                event, chat_id, chat, sender_id, punishment,
                "تبلیغات زیاد تشخیص داده شد", notify_enabled=True,
            )


async def locks_and_filters_handler(_client, event):
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return

    chat = get_chat_cfg(chat_id)
    if is_admin(chat, sender_id) or is_exempt(chat, sender_id):
        return

    text = getattr(event, 'raw_text', '') or ''
    msg_id = getattr(event, 'id', None)
    locks = chat.get("locks", {})

    velocity_key = (chat_id, sender_id)
    if _spam_sweep_active(velocity_key):
        _queue_delete(chat_id, msg_id, "قفل اسپم - حذف پیام‌های کاربرِ مجازات‌شده")
        return
    if locks.get("spam"):
        if _velocity_trip(velocity_key, msg_id, _event_send_ts(event)):
            _burst_start = _velocity_start_id.pop(velocity_key, None) or msg_id
            _spam_sweep_arm(velocity_key)  # فوری، بدون await؛ بقیه‌ی پیام‌های برست از همین‌جا drop می‌شن
            _queue_delete(chat_id, msg_id, "قفل اسپم - گارد سرعت (۶ پیام در ۱ ثانیه)")
            spam_cooldown[velocity_key] = _event_send_ts(event)
            _spawn(_velocity_punish(event, chat_id, chat, sender_id, velocity_key, _burst_start), "velocity-punish")
            _log(f"[اسپم-برست][{chat_id}] {sender_id}: burst-flood تشخیص داده شد؛ مجازات و پاکسازی شروع شد.")
            return
        _track_user_msg(chat_id, sender_id, msg_id)
        # قانون‌های خطِ تکراری/تعداد خطوط قبل از بقیه‌ی قفل‌ها و فیلترها چک می‌شن؛ وگرنه اگه
        # قفل دیگه‌ای پیام رو پاک کنه و return کنه، هیچ‌وقت به قفل اسپم نمی‌رسه و کاربر ساکت نمی‌شه.
        if await _spam_check_repeat(event, chat_id, chat, sender_id, text, velocity_key,
                                    _event_send_ts(event), _spam_cfg(chat), lines_only=True):
            return

    if _is_media_filtered(chat, event):
        if msg_id:
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception as e:
                _log_rpc_error("فیلتر رسانه", e, chat_id)
        return


    if chat.get("anti_jagh_lock_enabled") and _anti_jagh_match(text):
        if msg_id:
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception as e:
                _log_rpc_error("قفل ضد جقی", e, chat_id)
        await _lock_violation_notice(event, chat_id, chat, sender_id, "anti_jagh", "ضد جقی")
        return


    if chat.get("anti_ad_lock_enabled") and _ad_match(text):
        if msg_id:
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception as e:
                _log_rpc_error("قفل ضد تبلیغات", e, chat_id)
        await _lock_violation_notice(event, chat_id, chat, sender_id, "anti_ad", "ضد تبلیغات")
        await _ad_lock_register_hit(event, chat_id, chat, sender_id)
        return


    if _word_filter_hit(chat_id, chat.get("word_filters"), text):
        if msg_id:
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception as e:
                _log_rpc_error("فیلتر کلمه", e, chat_id)
        return


    reason = None
    reason_key = None
    if locks.get("link") and URL_RE.search(text):
        reason, reason_key = "لینک", "link"
    elif locks.get("phone") and PHONE_RE.search(text):
        reason, reason_key = "شماره تلفن", "phone"
    elif locks.get("unicode_spam") and UNICODE_SPAM_RE.search(text):
        reason, reason_key = "کد هنگی (کاراکتر یونیک زیاد)", "unicode_spam"
    elif locks.get("forward") and _is_forwarded(event):
        reason, reason_key = "فوروارد", "forward"
    elif locks.get("id") and "@" in text:
        reason, reason_key = "آیدی", "id"

    if reason is None and any(locks.get(k) for k in LOCK_MEDIA_KINDS):
        media_cat = _media_category(event)
        if media_cat:
            for lock_key_m, cats in LOCK_MEDIA_KINDS.items():
                if locks.get(lock_key_m) and media_cat in cats:
                    reason = LOCK_FA_NAMES[lock_key_m]
                    reason_key = lock_key_m
                    break

    if reason:
        if msg_id:
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception as e:
                _log_rpc_error(f"قفل {reason}", e, chat_id)

        warn_key = (chat_id, sender_id, reason)
        now_ts = datetime.now(timezone.utc).timestamp()
        last_warn_ts = lock_warn_cooldown.get(warn_key)
        if last_warn_ts is None or now_ts - last_warn_ts >= LOCK_WARN_COOLDOWN_SECONDS:
            lock_warn_cooldown[warn_key] = now_ts
            handled = False
            if reason_key in WARN_LOCK_KEYS:
                handled = await _lock_violation_warning(event, chat_id, chat, sender_id, reason_key, reason)
            if not handled:
                await notify_mention_notice(event, chat, sender_id, "🚫 محتوای فیلترشده شناسایی شد.\n🗑 پیام حذف شد.\n" + build_action_block(
                    details=[("🔒", "قفل", reason)]))
        return


    if locks.get("spam"):
        key = (chat_id, sender_id)
        now_ts = _event_send_ts(event)

        last_spam_ts = spam_cooldown.get(key)
        if last_spam_ts is not None and now_ts - last_spam_ts < SPAM_COOLDOWN_SECONDS:
            _queue_delete(chat_id, msg_id, "قفل اسپم - کولداون بعد از مجازات")
            return

        sp = _spam_cfg(chat)
        if await _spam_check_repeat(event, chat_id, chat, sender_id, text, key, now_ts, sp, skip_lines=True):
            return

        q = spam_tracker.setdefault(key, [])
        if msg_id:
            q.append((now_ts, msg_id))

        evicted = spam_evicted.setdefault(key, [])
        while q and now_ts - q[0][0] > sp["window"]:
            evicted.append(q.pop(0))
        while evicted and now_ts - evicted[0][0] > EVICTED_KEEP_SECONDS:
            evicted.pop(0)

        if len(q) >= sp["msg_count"]:
            spam_msg_ids = [m for (_, m) in q if m]
            spam_start_id = min(spam_msg_ids) if spam_msg_ids else msg_id
            for ev_ts, ev_id in evicted:
                if ev_id and ev_id not in spam_msg_ids:
                    spam_msg_ids.append(ev_id)
            spam_evicted.pop(key, None)
            q.clear()

            punishment = chat.get("spam_punishment", {"type": "timed_mute", "minutes": 10})
            spam_cooldown[key] = now_ts

            _spam_sweep_arm(key)
            if punishment.get("type") != "normal":
                await apply_group_punishment(
                    event, chat_id, chat, sender_id, punishment,
                    "اسپم تشخیص داده شد", notify_enabled=False,
                )
            _spawn(_spam_sweep(chat_id, sender_id, spam_msg_ids, True, spam_start_id), "spam-sweep")
            _log(f"[اسپم][{chat_id}] {sender_id}: مجازات اعمال شد؛ پاکسازی شروع شد.")


@client.on_edited_message()
async def edited_message_word_filter_handler(_client, event):
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return

    chat = get_chat_cfg(chat_id)
    if is_admin(chat, sender_id) or is_exempt(chat, sender_id):
        return

    text = getattr(event, 'raw_text', '') or ''
    msg_id = getattr(event, 'id', None)

    if _is_media_filtered(chat, event):
        if msg_id:
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception as e:
                _log_rpc_error("فیلتر رسانه (پیام ویرایش‌شده)", e, chat_id)
        return

    if chat.get("anti_jagh_lock_enabled") and _anti_jagh_match(text):
        if msg_id:
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception as e:
                _log_rpc_error("قفل ضد جقی (پیام ویرایش‌شده)", e, chat_id)
        return

    if chat.get("anti_ad_lock_enabled") and _ad_match(text):
        if msg_id:
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception as e:
                _log_rpc_error("قفل ضد تبلیغات (پیام ویرایش‌شده)", e, chat_id)
        return

    if _word_filter_hit(chat_id, chat.get("word_filters"), text):
        if msg_id:
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception as e:
                _log_rpc_error("فیلتر کلمه (پیام ویرایش‌شده)", e, chat_id)
        return


AUTO_DELETE_MESSAGE_DELAY_SECONDS = 0.5


async def _delayed_delete_message(chat_id, msg_id, delay: float = None):
    try:
        await asyncio.sleep(delay if delay is not None else AUTO_DELETE_MESSAGE_DELAY_SECONDS)
        await client.delete_messages(chat_id, msg_id)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ حذف خودکار پیامِ ربات - خطا: {e}")


@client.on_message()
async def cmd_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    text = _apply_command_aliases(text)
    chat_id = getattr(event, 'chat_id', None)

    if not chat_id or getattr(event, 'is_private', False):
        return

    chat = get_chat_cfg(chat_id)

    sender_id = getattr(event, 'sender_id', None)


    if text.startswith("فیلتر بیو کاربر "):
        if not is_admin(chat, sender_id):
            return
        word = text[len("فیلتر بیو کاربر "):].strip()
        if word:
            if word not in chat["bio_filter_words"]:
                chat["bio_filter_words"].append(word)
                await save_config(config)
                ensure_cleanup_task_running()
                await safe_reply(event, "🧬 فیلتر بیو به‌روزرسانی شد.\n" + build_action_block(
                    details=[("🔤", "کلمه", word)], footer="کلمه به فهرست فیلتر اضافه شد."))
            else:
                await safe_reply(event, f"ℹ️ کلمه «{word}» از قبل در لیست بود.")

    elif text == "ریست لیست بیو":
        if not is_admin(chat, sender_id):
            return
        chat["bio_filter_words"] = []
        await save_config(config)
        bio_flagged_users_memory.get(chat_id, set()).clear()
        await safe_reply(event, "🧬 فیلتر بیو به‌روزرسانی شد.\n" + build_action_block(
            footer="لیست فیلتر بیو این گروه پاک شد."))
        _log(f"[CMD][{chat_id}] Bio filter list cleared")

    elif text == "لیست بیو":
        if not is_admin(chat, sender_id):
            return
        words = chat.get("bio_filter_words", [])
        if words:
            await safe_reply(event, wrap_box("📋", "لیست فیلتر بیو", "\n".join(f"- {w}" for w in words)))
        else:
            await safe_reply(event, "لیست فیلتر بیو این گروه خالی است.")


    elif text.startswith("تنظیم مجازات بیو "):
        if not is_admin(chat, sender_id):
            return
        rest = text[len("تنظیم مجازات بیو "):].strip()
        punishment = parse_punishment_text(rest)
        if punishment:
            chat["bio_punishment"] = punishment
            await save_config(config)
            await safe_reply(event, f"✅ مجازات بیو این گروه روی «{punishment_to_fa(punishment)}» تنظیم شد.")
        else:
            await safe_reply(event, 
                "❓ نوع مجازات نامعتبر است. یکی از این‌ها را بفرست:\n"
                "- تنظیم مجازات بیو عادی\n"
                "- تنظیم مجازات بیو سکوت\n"
                "- تنظیم مجازات بیو سکوت یک ساعت\n"
                "- تنظیم مجازات بیو بن"
            )


    elif text.startswith("تنظیم مجازات اسم "):
        if not is_admin(chat, sender_id):
            return
        rest = text[len("تنظیم مجازات اسم "):].strip()
        punishment = parse_punishment_text(rest)
        if punishment:
            chat["name_punishment"] = punishment
            await save_config(config)
            await safe_reply(event, f"✅ مجازات فیلتر اسم این گروه روی «{punishment_to_fa(punishment)}» تنظیم شد.")
        else:
            await safe_reply(event,
                "❓ نوع مجازات نامعتبر است. یکی از این‌ها را بفرست:\n"
                "- تنظیم مجازات اسم عادی\n"
                "- تنظیم مجازات اسم سکوت\n"
                "- تنظیم مجازات اسم سکوت یک ساعت\n"
                "- تنظیم مجازات اسم بن"
            )


    elif text.startswith("فیلتر اسم "):
        if not is_admin(chat, sender_id):
            return
        word = text[len("فیلتر اسم "):].strip()
        if word:
            if word not in chat["name_filter_words"]:
                chat["name_filter_words"].append(word)
                await save_config(config)
                await safe_reply(event, "🧑 فیلتر اسم به‌روزرسانی شد.\n" + build_action_block(
                    details=[("🔤", "کلمه", word)], footer="فهرست کلمات ذخیره شد."))
            else:
                await safe_reply(event, f"ℹ️ کلمه «{word}» از قبل در لیست بود.")

    elif text == "ریست لیست اسم":
        if not is_admin(chat, sender_id):
            return
        chat["name_filter_words"] = []
        await save_config(config)
        await safe_reply(event, "🧑 فیلتر اسم به‌روزرسانی شد.\n" + build_action_block(
            footer="لیست فیلتر اسم این گروه پاک شد."))
        _log(f"[CMD][{chat_id}] Name filter list cleared")

    elif text == "لیست اسم":
        if not is_admin(chat, sender_id):
            return
        words = chat.get("name_filter_words", [])
        if words:
            await safe_reply(event, wrap_box("📋", "لیست فیلتر اسم", "\n".join(f"- {w}" for w in words)))
        else:
            await safe_reply(event, "لیست فیلتر اسم این گروه خالی است.")


    elif text in ("قفل ضد تبچی", "بستن قفل ضد تبچی"):
        if not is_admin(chat, sender_id):
            return
        chat["anti_khale_enabled"] = True
        await save_config(config)
        ensure_cleanup_task_running()
        await safe_reply(event, "👵 قفل ضد تبچی فعال شد.\n" + build_action_block(
            footer="فیلتر داخلی ضد تبچی در حال اجراست."))
        _log(f"[CMD][{chat_id}] قفل ضد تبچی ON")

    elif text in ("قفل ضد تبچی خاموش", "باز کردن قفل ضد تبچی"):
        if not is_admin(chat, sender_id):
            return
        chat["anti_khale_enabled"] = False
        await save_config(config)
        anti_khale_flagged_memory.get(chat_id, set()).clear()
        await safe_reply(event, "👵 قفل ضد تبچی خاموش شد.\n" + build_action_block(
            footer="بررسی ضد تبچی متوقف شد."))
        _log(f"[CMD][{chat_id}] قفل ضد تبچی OFF")

    elif text in ("قفل ممبر دزد", "بستن قفل ممبر دزد"):
        if not is_admin(chat, sender_id):
            return
        chat["member_stealer_lock_enabled"] = True
        await save_config(config)
        ensure_cleanup_task_running()
        await safe_reply(event, "🕵️ قفل ممبر دزد فعال شد.\n" + build_action_block(
            footer="بیوی اعضا بررسی خواهد شد."))
        _log(f"[CMD][{chat_id}] قفل ممبر دزد ON")

    elif text in ("قفل ممبر دزد خاموش", "باز کردن قفل ممبر دزد"):
        if not is_admin(chat, sender_id):
            return
        chat["member_stealer_lock_enabled"] = False
        await save_config(config)
        member_stealer_flagged_memory.get(chat_id, set()).clear()
        stale_keys = [k for k in member_stealer_msg_cache if k[0] == chat_id]
        for k in stale_keys:
            member_stealer_msg_cache.pop(k, None)
        await safe_reply(event, "🕵️ قفل ممبر دزد خاموش شد.\n" + build_action_block(
            footer="بررسی خودکار بیو متوقف شد."))
        _log(f"[CMD][{chat_id}] قفل ممبر دزد OFF")

    elif text in ("قفل ضد جقی", "بستن قفل ضد جقی"):
        if not is_admin(chat, sender_id):
            return
        chat["anti_jagh_lock_enabled"] = True
        await save_config(config)
        await safe_reply(event, "🔒 قفل ضد جقی فعال شد.\n" + build_action_block(
            footer="حذف پیام‌های حاوی کلمات ممنوعه؛ اخطار و مجازات طبق «تنظیم مجازات ضد جقی»."))
        _log(f"[CMD][{chat_id}] قفل ضد جقی ON")

    elif text in ("قفل ضد جقی خاموش", "باز کردن قفل ضد جقی"):
        if not is_admin(chat, sender_id):
            return
        chat["anti_jagh_lock_enabled"] = False
        await save_config(config)
        await safe_reply(event, "🔓 قفل ضد جقی خاموش شد.\n" + build_action_block(
            footer="بررسی کلمات ممنوعه متوقف شد."))
        _log(f"[CMD][{chat_id}] قفل ضد جقی OFF")

    elif text.startswith("تنظیم مجازات ضد تبچی "):
        if not is_admin(chat, sender_id):
            return
        rest = text[len("تنظیم مجازات ضد تبچی "):].strip()
        punishment = parse_punishment_text(rest)
        if punishment:
            chat["anti_khale_punishment"] = punishment
            await save_config(config)
            await safe_reply(event, f"✅ مجازات قفل ضد تبچی این گروه روی «{punishment_to_fa(punishment)}» تنظیم شد.")
        else:
            await safe_reply(event, 
                "❓ نوع مجازات نامعتبر است. یکی از این‌ها را بفرست:\n"
                "- تنظیم مجازات ضد تبچی عادی\n"
                "- تنظیم مجازات ضد تبچی سکوت\n"
                "- تنظیم مجازات ضد تبچی سکوت یک ساعت\n"
                "- تنظیم مجازات ضد تبچی بن"
            )

    elif text.startswith("تنظیم مداوم ریست سکوت"):
        if not is_admin(chat, sender_id):
            return
        time_part = text[len("تنظیم مداوم ریست سکوت"):].strip()
        minutes = parse_time_to_minutes(time_part)
        if not minutes or minutes <= 0:
            await safe_reply(event, 
                "❓ فرمت درست: «تنظیم مداوم ریست سکوت 5 دقیقه» یا «تنظیم مداوم ریست سکوت یک ساعت»\n"
                "با این تنظیم، هر چند وقت یک‌بار لیست سکوتِ عمومی (سکوت دستی ادمین، اسپم و...) "
                "پاک می‌شود. کاربرانی که با قفل ضد تبچی سکوت شده‌اند اصلاً وارد این لیست "
                "نمی‌شوند و همیشه دائمی و دست‌نخورده باقی می‌مانند."
            )
            return
        chat["mute_reset_minutes"] = minutes
        chat.setdefault("_last_run", {})["mute_reset_ts"] = datetime.now(timezone.utc).timestamp()
        await save_config(config)
        ensure_scheduler_running()
        await safe_reply(event, "🔄 ریست خودکار سکوت فعال شد.\n" + build_action_block(
            details=[("⏱", "فاصله", format_minutes_fa(minutes))],
            footer="فقط سکوت‌های عمومی بررسی می‌شوند."
        ))
        _log(f"[CMD][{chat_id}] general mute reset interval set to {minutes} min")

    elif text in ("ریست سکوت خاموش", "غیرفعال ریست سکوت", "خاموش کردن ریست سکوت"):
        if not is_admin(chat, sender_id):
            return
        chat["mute_reset_minutes"] = None
        await save_config(config)
        await safe_reply(event, "🔄 ریست خودکار سکوت خاموش شد.")
        _log(f"[CMD][{chat_id}] general mute reset interval disabled")


    elif text == "وضعیت":
        if not is_admin(chat, sender_id):
            return
        bio_words = chat.get("bio_filter_words", [])
        name_words = chat.get("name_filter_words", [])
        bio_ptype_fa = punishment_to_fa(chat.get("bio_punishment", {"type": "normal"}))
        khale_on = chat.get("anti_khale_enabled", False)
        khale_ptype_fa = punishment_to_fa(chat.get("anti_khale_punishment", {"type": "mute"}))
        bio_flagged_count = len(bio_flagged_users_memory.get(chat_id, set()))
        khale_flagged_count = len(anti_khale_flagged_memory.get(chat_id, set()))

        status = ""
        status += "── فیلتر بیو ──\n"
        status += f"🔤 کلمات فیلتر بیو: {len(bio_words)}\n"
        status += f"⚖️ نوع مجازات: {bio_ptype_fa}\n"
        status += f"📝 کاربران کنترل‌شده در این اجرا: {bio_flagged_count}\n\n"
        status += "── فیلتر اسم ──\n"
        status += f"🔤 کلمات فیلتر اسم: {len(name_words)}\n"
        status += f"⚖️ نوع مجازات: {punishment_to_fa(chat.get('name_punishment', {'type': 'normal'}))}\n\n"
        status += "── قفل ضد تبچی ──\n"
        status += f"🔒 وضعیت: {'روشن' if khale_on else 'خاموش'}\n"
        status += f"⚖️ نوع مجازات: {khale_ptype_fa}\n"
        status += f"📝 کاربران کنترل‌شده در این اجرا: {khale_flagged_count}\n"
        status += "🔇 سکوت این قفل همیشه دائمی است و هیچ ریستی روی آن اثر ندارد.\n\n"
        stealer_on = chat.get("member_stealer_lock_enabled", False)
        stealer_flagged_count = len(member_stealer_flagged_memory.get(chat_id, set()))
        status += "── قفل ممبر دزد ──\n"
        status += f"🔒 وضعیت: {'روشن' if stealer_on else 'خاموش'}\n"
        status += f"📝 کاربران سکوت‌شده در این اجرا: {stealer_flagged_count}\n"
        status += "🔇 سکوت این قفل هم همیشه دائمی است و هیچ ریستی روی آن اثر ندارد.\n\n"
        jagh_on = chat.get("anti_jagh_lock_enabled", False)
        status += "── قفل ضد جقی ──\n"
        status += f"🔒 وضعیت: {'روشن' if jagh_on else 'خاموش'}\n"
        status += "🗑️ پیام‌های حاوی کلمات ممنوعه حذف می‌شوند (اخطار و مجازات: «لیست قفل»).\n\n"
        mute_reset_minutes = chat.get("mute_reset_minutes")
        general_muted_count = len(chat.get("muted", {}))
        status += "── ریست خودکار سکوت عمومی ──\n"
        if mute_reset_minutes:
            status += f"🔁 وضعیت: هر {format_minutes_fa(mute_reset_minutes)} یک‌بار\n"
        else:
            status += "🔁 وضعیت: خاموش\n"
        status += f"🔇 سکوت‌شده‌های فعلی (غیر از قفل ضد تبچی): {general_muted_count}\n\n"
        status += "── مدیریت و امنیت ──\n"
        status += f"👑 مالک گپ: {chat.get('group_owner') or 'تنظیم‌نشده'}\n"
        status += f"👮 تعداد ادمین‌ها: {len(chat.get('admins', []))}\n"
        status += f"🙈 تعداد معاف‌شده‌ها: {len(chat.get('exempt', []))}\n"
        status += f"🔇 صدا خفه‌کن: {'روشن' if chat.get('silent_mode') else 'خاموش'}\n"
        status += f"🎉 سرگرمی برای اعضا: {'روشن' if chat.get('fun_enabled', True) else 'خاموش (فقط مدیران)'}\n"
        _delay = chat.get('auto_delete_delay_seconds')
        _delay = _delay if _delay is not None else AUTO_DELETE_MESSAGE_DELAY_SECONDS
        status += f"🧨 حذف خودکار پیام: {'روشن' if chat.get('auto_delete_messages_enabled') else 'خاموش'} (زمان: {_delay} ثانیه)\n"
        status += f"🎓 تعداد آموزش‌های ثبت‌شده: {len(chat.get('learned_words') or {})}\n"
        status += f"🗣 سخنگو (جواب خودکار آموزش): {'روشن' if chat.get('learned_words_enabled', True) else 'خاموش'}\n"
        status += f"⛔️ بن ادمین عادی: {'فعال' if chat.get('ban_enabled', True) else 'غیرفعال'}\n"
        status += f"🔒 قفل‌های فعال: {format_locks_status(chat.get('locks', {}))}\n"
        gal = chat.get("group_auto_lock", {}) or {}
        if gal.get("lock_time") and gal.get("unlock_time"):
            status += f"⏰ قفل خودکار گپ: قفل {gal['lock_time']} → باز {gal['unlock_time']}"
        else:
            status += "⏰ قفل خودکار گپ: غیرفعال"

        boxed_status = wrap_box("📊", "وضعیت گروه", status)
        await safe_reply(event, boxed_status)


HELP_MAIN_TEXT = """
✦───〔 🪐 راهنمای VØID 〕───✦

🔐 راهنمای قفل
╰─ قفل، اخطار، مجازات و صدا خفه کن

🛡 راهنمای مدیران
╰─ کاربران، حذف کن همش

📋 راهنمای لیست
╰─ لیست‌ها، مقام‌ها و تگ کاربران

🎉 راهنمای سرگرمی
╰─ سرگرمی‌ها و دسترسی‌ها

💡 برای دیدن هر بخش، اسمش را بنویس
""".strip()

HELP_LOCK_TEXT = """
✦───〔 🔐 راهنمای قفل 〕───✦

🔒 قفل‌ها
▸ قفل {نام} / بازکردن {نام}
▸ فعالسازی همه قفل ها
╰─ همه به‌جز گیف · عکس · استیکر · ویس · ویدیو · فایل · گپ · رسانه
▸ لیست قفل
╰─ وضعیت، حداکثر اخطار و مجازات هر قفل

📋 هر قفل چه می‌کند
▸ لینک · شماره · فوروارد · آیدی · کد هنگی
╰─ پیام حاوی آن حذف می‌شود (کد هنگی = کاراکتر یونیک زیاد)
▸ ویس · ویدیو · فایل
╰─ پیام حذف می‌شود (ویدیو شامل ویدیو مسیج، فایل شامل آهنگ)
▸ گیف · عکس · استیکر · گپ · رسانه
╰─ با دسترسی خود گروه بسته می‌شوند؛ اخطار ندارند (رسانه = بستن کامل گیف+عکس+استیکر با یک قفل مستقل، بدون دست‌زدن به قفل‌های دیگه)
▸ اسپم
╰─ پیام پرسرعت، پیام تکراری و تعداد خطوط زیاد در یک پیام
▸ ضد جقی
╰─ حذف پیام‌های حاوی کلمات ممنوعه
▸ ضد تبلیغات
╰─ حذف پیام تبلیغاتی (بیو، چک، چنل، گپم ...)
▸ ضد تبچی
╰─ سکوتِ دائمیِ تبچی‌ها با لیست کلمات ثابت
▸ ممبر دزد
╰─ بیوی با لینک گروه = سکوت دائم، بدون اخطار

⚠️ اخطار و مجازات
▸ تنظیم حداکثر اخطار {نام} {عدد}
▸ تنظیم حداکثر اخطار {عدد}
╰─ برای همهٔ قفل‌ها
▸ تنظیم مجازات {نام} بن
▸ تنظیم مجازات {نام} سکوت {مدت}
╰─ بدون مدت = سکوت دائم
▸ تنظیم مجازات {نام} هشدار
╰─ فقط حذف پیام، بدون ثبت اخطار
▸ تنظیم مجازات بن
╰─ برای همهٔ قفل‌ها
▸ تنظیم مجازات اخطار دستی بن|سکوت|هشدار
💡 هر نقض قفل فعال یک اخطار دارد؛ با رسیدن به حد تنظیم‌شده، مجازات اجرا و اخطارها صفر می‌شود.

👤 اخطار دستی
▸ اخطار / حذف اخطار
╰─ با ریپلای، نام کاربری یا شناسه
▸ ریست لیست اخطار

🚨 تنظیمات اسپم
▸ تنظیمات اسپم / بازنشانی تنظیمات اسپم
▸ تنظیم تعداد پیام {عدد} در {عدد} ثانیه
▸ تنظیم پیام تکراری اسپم {عدد}
▸ تنظیم خط تکراری اسپم {عدد}
▸ تنظیم تکرار کلمه اسپم {عدد}
▸ تنظیم مجازات اسپم بن|سکوت {مدت}|عادی

🔇 صدا خفه کن روشن/خاموش — فقط مالک
╰─ پیام ممنوع حذف می‌شود، ولی اعلان تخلف نمی‌آید
""".strip()

HELP_LIST_TEXT = """
✦───〔 📋 راهنمای لیست و تگ 〕───✦

👑 مقام‌ها
▸ تنظیم ادمین / حذف ادمین
╰─ با ریپلای
▸ تنظیم مالک گپ / حذف مالک گپ
╰─ فقط مالک ربات
▸ معاف / لغو معاف
╰─ با ریپلای

📑 لیست‌ها
▸ لیست ادمین • لیست سکوت
▸ لیست معاف • لیست بن
▸ لیست اخطار • لیست فیلتر
▸ لیست قفل • لیست فیلتر مدیا
▸ لیست کیل
▸ ریست لیست {سکوت | بن | بیو | اسم | اخطار | کیل | فیلتر مدیا | معاف}
╰─ پاک کردن کل همان لیست

🏷 تگ
▸ تگ یا لیست تگ
╰─ راهنمای انواع تگ را نمایش می‌دهد
▸ تگ همه
╰─ همه رو یکی‌یکی، هرکدوم با یه متن طنز و اسمِ خودشون تگ می‌کند
▸ تگ متن (متن دلخواه)
╰─ همه رو یکی‌یکی، هرکدوم با متن دلخواهت تگ می‌کند (می‌تونی جای اسم از {تگ} استفاده کنی)
▸ لیست اعضا
▸ تگ {تعداد}
▸ تگ ادمین • تگ مالک
▸ تگ معاف • تگ سکوت
╰─ در خروجی ابتدا نام کاربری و در نبود آن نام و اشارهٔ نمایه نمایش داده می‌شود

🎯 کیل
╰─ هر پیامی که کاربر بفرستد خودکار پاک می‌شود
▸ کیل — ریپلای روی پیام، بدون زمان (تا حذف کیل)
▸ کیل {مدت} — ریپلای، کیل زمان‌دار
▸ کیل @نام‌کاربری {مدت}
▸ کیل {شناسه} {مدت}
▸ حذف کیل — ریپلای، نام کاربری یا شناسه
""".strip()

HELP_ADMIN_TEXT = """
✦───〔 🛡 راهنمای مدیران 〕───✦

🔇 « سکوت و بن »
  • بن / رفع بن «با ریپلای»
  • سکوت [زمان] / رفع سکوت «با ریپلای»
  • سکوت @یوزرنیم [زمان] / سکوت آیدی‌عددی [زمان] «بدون ریپلای»
  • بن فعال / بن غیرفعال
  • تنظیم اقدام سکوت [زمان] «فقط مالک گپ/ربات»
  • ریست اقدام سکوت
  • حذف خودکار پیام روشن / خاموش «فقط این‌ها بعد از
    ارسال پاک می‌شوند: قفل ضد تبچی، قفل ممبر دزد، قفل بیو، قفل
    اسم، اخطار عادی، سکوت‌شدن بعد اسپم، اخطارِ قفل‌ها (لینک/
    شماره/کد هنگی/فوروارد/آیدی)؛ بقیه‌ی پیام‌های ربات پاک نمی‌شوند»
  • تنظیم زمان پاک شدن [عدد] «مثلاً 0.1 ؛ زمان (ثانیه) حذف
    خودکار پیام‌های بالا، بدون آرگومان = نمایش زمان فعلی»

🎉 « سرگرمی »
  • سرگرمی خاموش / روشن «با خاموش‌بودن، دستورهای سرگرمی
    فقط برای مدیران کار می‌کنند و برای بقیه بی‌جواب می‌مانند»

📌 « پین »
  • پین «با ریپلای روی پیام»
  • پین با اطلاع «مثل بالا ولی به همه اطلاع می‌دهد»
  • آنپین «با ریپلای: همان پیام / بدون ریپلای: همه‌ی پین‌ها»

🔤 « فیلتر کلمه »
  • فیلتر کلمه [کلمه]
  • حذف فیلتر کلمه [کلمه]
  • لیست فیلتر کلمه
  • ریست لیست فیلتر (پاک کردن کل این لیست)
  • فیلتر محتوا «ریپلای روی گیف؛ خودِ گیف فیلتر می‌شود (فقط گیف)»

🧬 « فیلتر بیو »
  • فیلتر بیو کاربر [کلمه]
  • لیست بیو / ریست لیست بیو
  • تنظیم مجازات بیو عادی/سکوت/سکوت [زمان]/بن

🧑 « فیلتر اسم »
  • فیلتر اسم [کلمه]
  • لیست اسم / ریست لیست اسم
  • تنظیم مجازات اسم عادی/سکوت/سکوت [زمان]/بن
  ↳ پیش‌فرض: در صورت تطابق فقط پیام حذف می‌شود + اخطار

🔁 « ریست خودکار سکوت عمومی »
  (فقط روی سکوت دستی ادمین/اسپم؛ کاری به قفل ضد تبچی ندارد)
  • تنظیم مداوم ریست سکوت [زمان] (مثلاً 5 دقیقه)
  • ریست سکوت خاموش

🧹 « پاکسازی »
  • حذف کن [تعداد] / حذف کن همش «پیام‌های پین‌شده هیچ‌وقت پاک نمی‌شوند»
  • حذف پیام هاش «با ریپلای»
  • پاکسازی رسانه (همین الان هرچی رسانه هست را پاک می‌کند)

⏰ « زمان‌بندی (وقت تهران) »
  • تنظیم پاکسازی خودکار هر 1 ساعت (یا 30 دقیقه / 40 دقیقه / ...)
  • تنظیم پاکسازی خودکار HH:MM (هر بار اجرا کنی، به لیست اضافه می‌شود)
  • لیست پاکسازی
  • حذف پاکسازی HH:MM / حذف پاکسازی هر
  • غیرفعال پاکسازی خودکار (کل لیست و بازه را پاک می‌کند)
  • پاکسازی خودکار رسانه هر 30 دقیقه (یا 10 ثانیه / 1 ساعت / ...)
  • پاکسازی خودکار رسانه HH:MM (هر بار اجرا کنی، به لیست اضافه می‌شود)
  • لیست پاکسازی رسانه
  • حذف پاکسازی رسانه HH:MM / حذف پاکسازی رسانه هر
  • غیرفعال پاکسازی خودکار رسانه (کل تنظیمات رسانه را پاک می‌کند)
  • تنظیم خودکار رفع سکوت HH:MM
  • تنظیم خودکار رفع بن HH:MM
  • قفل خودکار گپ HH:MM | HH:MM (اول=قفل، دوم=بازگشایی)
  • قفل خودکار گپ خاموش

📊 « وضعیت »
  • وضعیت  ← آمار و تنظیمات فعلی گروه

🎓 « آموزش کلمه‌ی کلیدی (پاسخ خودکار) »
  • یاد بگیر [کلمه] = [جواب] «فقط ادمین»
    مثال: یاد بگیر سلام = به به سلام خوشگل
  ↳ هرکس پیامش با همان کلمه شروع شود
    پیامش ریپلای می‌زند
  ↳ می‌تونی برای یک کلمه چند بار «یاد بگیر» بزنی و چند
    جواب مختلف اضافه کنی؛ هر بار یکی از آن‌ها به‌صورت
  • لیست آموزش «نمایش همه‌ی کلمات و جواب‌ها»
  • حذف آموزش [کلمه] «حذف کلمه با همه‌ی جواب‌هایش، فقط ادمین»
  • ریست لیست آموزش «پاک کردن کل لیست، فقط ادمین»
  • سخنگو روشن / سخنگو خاموش «فقط ادمین؛ خاموش‌کردن یعنی
    ربات دیگر جواب نمی‌دهد ولی لیست آموزش‌ها پاک نمی‌شود»

👤 « پروفایل / اطلاعات کاربر »
  • پروفایل من / مشخصات من «اطلاعات خودت»
  • اطلاعات کاربر «با ریپلای؛ اطلاعات طرف مقابل»
""".strip()

HELP_FUN_TEXT = """
✦───〔 🎉 راهنمای سرگرمی 〕───✦

▸ 🎲 چالش
▸ 😂 جوک
▸ 🧠 دانستنی
▸ 🔮 فال
▸ 📌 فکت
▸ 🎲 تاس
▸ 💘 شیپ
▸ 🔢 حدس عدد
╰─ «حدس عدد» شروع · «حدس ۵۰» حدس زدن · «پایان حدس عدد» پایان (شروع‌کننده/ادمین)
▸ ✊ سنگ کاغذ قیچی
╰─ مثال: سنگ کاغذ قیچی سنگ (یا کاغذ / قیچی)
▸ 🔤 کلمه قاطی
╰─ اولین نفری که کلمه‌ی درست رو بنویسه برنده‌ست
▸ 🔫 دوئل
╰─ «دوئل» یا «دوئل @یوزرنیم» (یا ریپلای) · «قبول دوئل» · «رد دوئل»
╰─ «دوئل ۳» یا «دوئل ۵» = بهترین از ۳ یا ۵ دست
╰─ بعد از علامت «شلیک» هر کی زودتر بنویسه شلیک، برنده‌ست؛ زودتر بنویسی می‌بازی!
╰─ «رده‌بندی دوئل» جدول امتیاز · «آمار دوئل» آمار شخصی · «لغو دوئل»
▸ ⭕ دوز
╰─ «دوز» بازی می‌سازه و یه کد بازی می‌ده؛ بقیه اون کد رو بفرستن تا وارد بشن
╰─ ریپلای روی کسی + «دوز» (یا «دوز @یوزرنیم») = مستقیم میاد توی بازی
╰─ حرکت: شماره‌ی خونه (۱ تا ۹) · «لغو دوز»
▸ 🧮 ریاضی
╰─ «ریاضی» یه محاسبه‌ی سریع می‌ده؛ اولین جواب درست برنده‌ست
▸ 👁 ایموجی فرق
╰─ بین ایموجی‌های شبیه هم یکی فرق داره؛ جاش رو بنویس (مثلاً «۲ ۳» = ردیف ۲، ستون ۳)
▸ 🎰 اسلات
╰─ «اسلات» چرخ شانس رو می‌چرخونه؛ سه‌تا مثل هم = جکپات
▸ 🔫 رولت
╰─ «رولت» شروع · «ماشه» کشیدن ماشه (نوبتی) · «پایان رولت»؛ هرکی تیر بخوره می‌بازه
▸ 🧠 کوییز
╰─ «کوییز» یه سوال عمومی می‌پرسه؛ اولین جواب درست برنده‌ست
▸ 🔐 رمز شکن
╰─ «رمز شکن» شروع · «رمز ۱۲۳۴» حدس · 🟢 درست و سرجاش · 🟡 درست ولی جاش غلط · «پایان رمز شکن»
▸ 🪢 کلمه مخفی
╰─ «کلمه مخفی» شروع · «حرف ب» حدس حرف (یا کل کلمه رو بنویس) · ۶ جون داری · «پایان کلمه مخفی»
▸ 🎙 ویس بساز
╰─ مثال: ویس بساز سلام به همه · متن رو ویس می‌کنه و همین‌جا می‌فرسته
▸ 🌐 ترجمه
╰─ مثال: ترجمه hello · یا ریپلای روی یه پیام + «ترجمه»
╰─ انگلیسی ← فارسی و فارسی ← انگلیسی؛ زبان خودکار تشخیص داده می‌شه
▸ 🌤 هواشناسی
╰─ مثال: هواشناسی تهران · دما، رطوبت، باد و وضعیت جوی همان لحظه‌ی شهر
▸ 🏙 شهر
╰─ مثال: شهر تهران · معرفی شهر (توضیحات، موقعیت و مختصات)
▸ 📖 جستجو
╰─ مثال: جستجو حافظ شیرازی · جستجوی عبارت و نمایش خلاصه‌ی نتیجه
▸ 🕰 ساعت و تقویم
╰─ «امروز چندمه» · «ساعت چنده» · «ساعت» · «زمان» · «تقویم»
╰─ روز هفته، تاریخ شمسی و میلادی، ساعت دقیق (به وقت تهران)، مناسبت ملی امروز و بعدی و تقویم ماه با علامت امروز
""".strip()


WARN_LOCK_KEYS = ["link", "phone", "forward", "id", "unicode_spam", "voice", "video", "file",
                  "anti_jagh", "anti_ad"]
WARN_EXTRA_LOCKS = {
    "anti_jagh": ("ضد جقی", "anti_jagh_lock_enabled"),
    "anti_ad": ("ضد تبلیغات", "anti_ad_lock_enabled"),
}
PERMISSION_LOCK_KEYS = ["gif", "photo", "sticker", "group", "media"]
WARN_MANUAL_KEY = "manual"
WARN_DEFAULT_MAX = 3
WARN_MAX_LIMIT = 50
WARN_DEFAULT_PUNISHMENT = {"type": "normal"}
WARN_MANUAL_DEFAULT_PUNISHMENT = {"type": "timed_mute", "minutes": 60}

SPAM_DEFAULTS = {"msg_count": 5, "window": 5, "dup": 6, "word_repeat": 0, "line_repeat": 8}
SPAM_DUP_WINDOW_SECONDS = 120
spam_dup_tracker: dict = {}


def _fa_num(n) -> str:
    return to_persian_digits(str(n))


def _warn_label(key: str) -> str:
    if key in WARN_EXTRA_LOCKS:
        return WARN_EXTRA_LOCKS[key][0]
    if key == WARN_MANUAL_KEY:
        return "دستی"
    return LOCK_FA_NAMES.get(key, key)


def _warn_lock_on(chat: dict, key: str) -> bool:
    if key in WARN_EXTRA_LOCKS:
        return bool(chat.get(WARN_EXTRA_LOCKS[key][1]))
    return bool((chat.get("locks") or {}).get(key))


def _warn_key_from_name(name: str):
    name = re.sub(r"\s+", " ", (name or "").replace("\u200c", " ")).strip()
    if name in ("دستی", "اخطار دستی"):
        return WARN_MANUAL_KEY
    if name in ("ضد جقی",):
        return "anti_jagh"
    if name in ("ضد تبلیغات", "تبلیغات"):
        return "anti_ad"
    key = LOCK_FA_TO_KEY.get(name)
    if key in WARN_LOCK_KEYS or key in PERMISSION_LOCK_KEYS:
        return key
    return None


def _split_lock_name(rest: str):
    """«لینک بن» → ("link", "بن")؛ اگه با اسمِ قفلی شروع نشه (None, rest)."""
    rest = re.sub(r"\s+", " ", rest.replace("\u200c", " ")).strip()
    names = sorted(list(LOCK_FA_TO_KEY) + ["اخطار دستی", "دستی", "ضد جقی", "ضد تبلیغات", "تبلیغات"], key=len, reverse=True)
    for n in names:
        if rest == n or rest.startswith(n + " "):
            key = _warn_key_from_name(n)
            if key:
                return key, rest[len(n):].strip()
    return None, rest


def _warn_cfg(chat: dict, key: str):
    st = (chat.get("lock_warn_settings") or {}).get(key) or {}
    default_pun = WARN_MANUAL_DEFAULT_PUNISHMENT if key == WARN_MANUAL_KEY else WARN_DEFAULT_PUNISHMENT
    mx = st.get("max") or WARN_DEFAULT_MAX
    pun = st.get("punishment") or dict(default_pun)
    return int(mx), pun


def _warn_set(chat: dict, key: str, max_=None, punishment=None) -> None:
    d = chat.setdefault("lock_warn_settings", {}).setdefault(key, {})
    if max_ is not None:
        d["max"] = int(max_)
    if punishment is not None:
        d["punishment"] = punishment


def _warn_punish_fa(p: dict) -> str:
    t = p.get("type", "normal")
    if t == "normal":
        return "هشدار (فقط حذف پیام)"
    if t == "ban":
        return "بن"
    if t == "mute":
        return "سکوت دائم"
    if t == "timed_mute":
        return f"سکوت {format_minutes_fa(p.get('minutes', 10))}"
    return str(t)


def _warn_bar(count: int, mx: int) -> str:
    width = mx if mx <= 10 else 10
    filled = count if mx <= 10 else max(1, round(count * 10 / mx))
    filled = max(0, min(filled, width))
    return "▰" * filled + "▱" * (width - filled)


async def send_neon_warning(event, chat: dict, user_id, count: int, mx: int, pun: dict,
                            reason: str = None, by_id=None, action: str = None) -> None:
    """پیام اخطار با تم نئون (قاب دوخطی، نوار اخطار و امضای VØID)."""
    try:
        user = await client.get_entity(user_id)
    except Exception:
        user = None
    b = MentionTextBuilder()
    b.text("╔═══════════════════╗\n   ⚠️ 𝗪𝗔𝗥𝗡 ⚠️\n╚═══════════════════╝\n")
    b.text(" ◈ کاربر  ➜ ")
    await b.mention(user_id, user)
    b.text("\n")
    if by_id:
        b.text(" ◈ توسط   ➜ ")
        await b.mention(by_id)
        b.text("\n")
    if reason:
        b.text(f" ◈ دلیل   ➜ {reason}\n")
    if action:
        b.text(f" ◈ اقدام  ➜ {action}\n")
    b.text(f" ◈ اخطار  ➜ {_warn_bar(count, mx)}  {_fa_num(count)}/{_fa_num(mx)}\n")
    b.text(f" ◈ سقف    ➜ {_warn_punish_fa(pun)}\n")
    b.text("━━━━━━━━━━━━━━━━━━━\n   ⌁ VØID ⌁")
    msg_text, entities = b.build()
    await notify(event, chat, msg_text, warning=True, entities=entities)


def _warn_add(chat: dict, uid, key: str) -> int:
    w = chat.setdefault("warnings", {}).setdefault(str(uid), {})
    w[key] = int(w.get(key, 0)) + 1
    return w[key]


def _warn_clear(chat: dict, uid) -> None:
    (chat.get("warnings") or {}).pop(str(uid), None)


async def _lock_violation_warning(event, chat_id, chat: dict, sender_id, key: str, reason_fa: str) -> bool:
    """بعد از حذفِ پیامِ ممنوع صدا زده می‌شه. اگه مجازاتِ قفل «هشدار» باشه چیزی ثبت
    نمی‌شه و False برمی‌گرده (پیامِ قبلیِ «محتوای فیلترشده» می‌ره). وگرنه یک اخطار ثبت
    می‌شه؛ با رسیدن به حد، مجازات اجرا و همه‌ی اخطارهای کاربر صفر می‌شه."""
    mx, pun = _warn_cfg(chat, key)
    if pun.get("type", "normal") == "normal":
        return False
    count = _warn_add(chat, sender_id, key)
    if count >= mx:
        _warn_clear(chat, sender_id)
        await save_config(config)
        await apply_group_punishment(
            event, chat_id, chat, sender_id, pun,
            f"نقض قفل {reason_fa} ({_fa_num(mx)} اخطار)",
        )
        return True
    await save_config(config)
    await send_neon_warning(event, chat, sender_id, count, mx, pun,
                            reason=f"قفل {reason_fa}", action="پیام حذف شد")
    return True


async def _lock_violation_notice(event, chat_id, chat: dict, sender_id, key: str, reason_fa: str) -> None:
    """برای قفل‌هایی که پیام رو خودشون پاک می‌کنن (ضد جقی / ضد تبلیغات): هر ۱۰ ثانیه حداکثر یک
    اخطار. اگه مجازاتِ قفل «هشدار» باشه مثل قبل کاملاً بی‌صدا رد می‌شه."""
    warn_key = (chat_id, sender_id, key)
    now_ts = datetime.now(timezone.utc).timestamp()
    last = lock_warn_cooldown.get(warn_key)
    if last is not None and now_ts - last < LOCK_WARN_COOLDOWN_SECONDS:
        return
    lock_warn_cooldown[warn_key] = now_ts
    await _lock_violation_warning(event, chat_id, chat, sender_id, key, reason_fa)


def _spam_cfg(chat: dict) -> dict:
    s = dict(SPAM_DEFAULTS)
    s.update(chat.get("spam_settings") or {})
    return s


_LINE_STRIP_CHARS = " \t\r\u00a0!?.,،؛:;؟-_*~\"'«»()[]{}<>|/\\•·…"
_LINE_DROP_RE = re.compile(r'[\u0640\u200b-\u200f\u202a-\u202e\u2060\ufeff\ufe00-\ufe0f\u064b-\u065f\u0670\u0300-\u036f]')


def _norm_spam_line(ln: str) -> str:
    """نرمال‌سازیِ یک خط برای تشخیصِ تکرار: کشیده (ـ)، حروف نامرئی، اعراب و فاصله‌ها حذف می‌شن،
    ي/ك عربی به ی/ک تبدیل می‌شن و علامت‌های ابتدا/انتهای خط نادیده گرفته می‌شن."""
    ln = _LINE_DROP_RE.sub('', ln).replace('ي', 'ی').replace('ك', 'ک')
    ln = re.sub(r'\s+', ' ', ln).strip(_LINE_STRIP_CHARS)
    return ln.casefold()


_LINE_TOKEN_RE = re.compile(r'\w+', re.UNICODE)
_SIMILAR_LINES_MAX = 200
_SIMILAR_LINE_MIN_JACCARD = 0.5


def _max_repeated_line(body: str) -> int:
    """بیشترین تعداد خطِ «تکراری یا مشابه» توی پیام (خط‌ها لزوماً پشت‌سرهم نیستن).
    خط‌ها به مجموعه‌ی کلماتشون تبدیل می‌شن (علامت، ایموجی و کشیده نادیده گرفته می‌شن)؛
    خط بدون حرف/عدد (مثل خط جداکننده) کلاً نادیده گرفته می‌شه. دو خط وقتی «مشابه»‌ان
    که حداقل نصفِ کلماتشون مشترک باشه (Jaccard >= 0.5)؛ خط‌های کاملاً یکسان هم همین‌طورن.
    برای هر خط می‌شماریم چند خط (با خودش) بهش مشابه‌ان و بیشترین عدد برگردونده می‌شه."""
    sets = []
    for ln in body.splitlines():
        toks = frozenset(_LINE_TOKEN_RE.findall(_norm_spam_line(ln)))
        if toks:
            sets.append(toks)
        if len(sets) >= _SIMILAR_LINES_MAX:
            break
    best = 0
    for i, a in enumerate(sets):
        c = 0
        for b in sets:
            if a is b or a == b:
                c += 1
            else:
                inter = len(a & b)
                if inter and inter / len(a | b) >= _SIMILAR_LINE_MIN_JACCARD:
                    c += 1
        if c > best:
            best = c
    return best


async def _spam_check_repeat(event, chat_id, chat: dict, sender_id, text: str, key, now_ts: float, sp: dict,
                              lines_only: bool = False, skip_lines: bool = False) -> bool:
    """پیام تکراری / تعداد خطوطِ یک پیام (هر دو به‌صورت پیش‌فرض روشن‌ان؛ عدد 0 = خاموش). اگه اسپم تشخیص داده
    بشه پیام(ها) پاک و طبق «مجازات اسپم» عمل می‌شه؛ در این حالت True برمی‌گرده."""
    msg_id = getattr(event, 'id', None)
    body = (text or "").strip()
    if not body:
        return False
    reason = None
    ids_to_delete = []

    if not lines_only and sp.get("dup"):
        norm = re.sub(r"\s+", " ", body).lower()
        rec = spam_dup_tracker.get(key)
        if rec and rec[0] == norm and now_ts - rec[2] <= SPAM_DUP_WINDOW_SECONDS:
            rec[1] += 1
            if msg_id:
                rec[3].append(msg_id)
        else:
            rec = [norm, 1, now_ts, [msg_id] if msg_id else []]
            spam_dup_tracker[key] = rec
            if len(spam_dup_tracker) > 3000:
                for k in [k for k, r in spam_dup_tracker.items() if now_ts - r[2] > SPAM_DUP_WINDOW_SECONDS]:
                    spam_dup_tracker.pop(k, None)
        if rec[1] >= sp["dup"]:
            reason = "پیام تکراری"
            ids_to_delete = list(rec[3])
            spam_dup_tracker.pop(key, None)

    if reason is None and not skip_lines and sp.get("line_repeat"):
        # N خطِ تکراری یا مشابه (حداقل نصفِ کلمات مشترک) هرجای پیام؛ فرقی نداره بینشون خطِ دیگه‌ای باشه.
        if _max_repeated_line(body) >= sp["line_repeat"]:
            reason = "خط تکراری/مشابه در یک پیام"
            ids_to_delete = [msg_id] if msg_id else []

    if reason is None and not skip_lines and sp.get("word_repeat"):
        # اگه تعدادِ خط‌های (غیرخالیِ) یک پیام به حدِ تنظیم‌شده (پیش‌فرض ۸) برسه اسپم حساب می‌شه.
        if sum(1 for _ln in body.splitlines() if _ln.strip()) >= sp["word_repeat"]:
            reason = "تعداد خطوط زیاد"
            ids_to_delete = [msg_id] if msg_id else []

    if reason is None:
        return False

    spam_cooldown[key] = now_ts
    _spam_sweep_arm(key)
    punishment = chat.get("spam_punishment", {"type": "timed_mute", "minutes": 10})
    if punishment.get("type") != "normal":
        await apply_group_punishment(
            event, chat_id, chat, sender_id, punishment,
            f"اسپم تشخیص داده شد ({reason})", notify_enabled=True,
        )
    else:
        await notify_mention_notice(event, chat, sender_id, f"🚫 {reason} شناسایی شد.\n🗑 پیام حذف شد.")
    _start_id = min((i for i in ids_to_delete if i), default=msg_id)
    _spawn(_spam_sweep(chat_id, sender_id, ids_to_delete, full_history=True, start_id=_start_id),
           "spam-sweep")
    return True


def _spam_settings_text(chat: dict) -> str:
    sp = _spam_cfg(chat)
    on = (chat.get("locks") or {}).get("spam")
    lines = [
        f"🔒 قفل اسپم: {'روشن' if on else 'خاموش'}",
        f"⚡ پیام سریع: {_fa_num(sp['msg_count'])} پیام در {_fa_num(sp['window'])} ثانیه",
        "🔁 پیام تکراری: " + (f"{_fa_num(sp['dup'])} بار پشت‌سرهم" if sp["dup"] else "خاموش"),
        "♻️ خط تکراری/مشابه: " + (f"{_fa_num(sp['line_repeat'])} بار در یک پیام" if sp["line_repeat"] else "خاموش"),
        "📝 تعداد خطوط: " + (f"{_fa_num(sp['word_repeat'])} خط در یک پیام" if sp["word_repeat"] else "خاموش"),
        f"⚖️ مجازات: {punishment_to_fa(chat.get('spam_punishment', {'type': 'timed_mute', 'minutes': 10}))}",
    ]
    return wrap_box("🚨", "تنظیمات اسپم", "\n".join(lines))


def _locks_overview_text(chat: dict) -> str:
    locks = chat.get("locks") or {}

    def dot(on) -> str:
        return "🟢" if on else "🔴"

    out = ["╭─〔 🔒 لیست قفل‌ها 〕─╮", "🟢 روشن  •  🔴 خاموش", "", "⚠️ قفل‌های دارای اخطار"]
    for key in WARN_LOCK_KEYS:
        mx, pun = _warn_cfg(chat, key)
        out.append(f"{dot(_warn_lock_on(chat, key))} {_warn_label(key)} ┃ {_fa_num(mx)} اخطار ┃ {_warn_punish_fa(pun)}")
    out += ["", "🔐 قفل‌های دسترسی (بدون اخطار)"]
    for key in PERMISSION_LOCK_KEYS:
        out.append(f"{dot(locks.get(key))} {LOCK_FA_NAMES[key]}")
    out += ["", "🚨 قفل‌های ویژه"]
    out.append(f"{dot(locks.get('spam'))} اسپم ┃ {punishment_to_fa(chat.get('spam_punishment', {'type': 'timed_mute', 'minutes': 10}))}")
    out.append(f"{dot(chat.get('anti_khale_enabled'))} ضد تبچی ┃ {punishment_to_fa(chat.get('anti_khale_punishment', {'type': 'mute'}))}")
    out.append(f"{dot(chat.get('member_stealer_lock_enabled'))} ممبر دزد ┃ سکوت دائم (بدون اخطار)")
    mx, pun = _warn_cfg(chat, WARN_MANUAL_KEY)
    out += ["", f"👤 اخطار دستی ┃ {_fa_num(mx)} اخطار ┃ {_warn_punish_fa(pun)}"]
    return "\n".join(out)


HELP_TAG_TEXT = """
✦───〔 🏷 انواع تگ 〕───✦

▸ تگ همه
╰─ همه‌ی اعضا، یکی‌یکی و هرکدوم با یه متنِ طنزِ تصادفی
▸ تگ متن (متن دلخواه)
╰─ همه‌ی اعضا، یکی‌یکی، هرکدوم با متنِ دلخواهِ خودت
▸ لیست اعضا
╰─ همه‌ی اعضا، دسته‌جمعی توی چند پیام
▸ تگ {تعداد}
╰─ تعداد مشخصی از اعضا، تصادفی
▸ تگ ادمین
╰─ ادمین‌های واقعی گروه
▸ تگ مالک
╰─ مالک گپ
▸ تگ معاف
╰─ معاف‌ها
▸ تگ سکوت
╰─ کاربران داخل لیست سکوت
""".strip()


async def _cmd_target(event, chat_id, rest: str):
    """«[@یوزرنیم | آیدی] [بقیه]» یا ریپلای → (target, بقیه)"""
    _ro = getattr(event, 'reply_to', None)
    has_reply = bool(getattr(event, 'reply_to_msg_id', None)
                     or (getattr(_ro, 'reply_to_msg_id', None) if _ro else None))
    tokens = rest.split()
    if tokens and (tokens[0].startswith("@") or not has_reply):
        arg, remain = tokens[0], " ".join(tokens[1:])
    else:
        arg, remain = "", rest
    target = await resolve_target(event, chat_id, arg, prefer_arg=True)
    return target, remain


def _looks_like_target_args(event, rest: str) -> bool:
    """جلوگیری از فعال شدن با جمله‌های عادی («اخطار می‌دم ...»)"""
    if not rest:
        return True
    first = rest.split()[0]
    if first.startswith("@") or normalize_digits(first).isdigit():
        return True
    _ro = getattr(event, 'reply_to', None)
    has_reply = bool(getattr(event, 'reply_to_msg_id', None)
                     or (getattr(_ro, 'reply_to_msg_id', None) if _ro else None))
    return has_reply and parse_time_to_minutes(rest) is not None


async def _send_user_rows(event, emoji: str, title: str, rows: list) -> None:
    """rows = [(uid, متن‌اضافی)]؛ لیستِ قابل‌کلیک، تکه‌تکه."""
    if not rows:
        await safe_reply(event, f"📋 {title}\n╰─ تعداد: 『۰』")
        return
    size = 40
    chunks = [rows[i:i + size] for i in range(0, len(rows), size)]
    for ci, chunk in enumerate(chunks):
        if ci == 0:
            head = f"╭─〔 {emoji} {title} 〕─╮\n╰─ تعداد: 『{_fa_num(len(rows))}』\n──────────────"
        else:
            head = f"╭─〔 {emoji} {title} (ادامه) 〕─╮\n──────────────"
        b = MentionTextBuilder().text(head)
        for uid, extra in chunk:
            try:
                user = await client.get_entity(uid)
            except Exception:
                user = None
            b.text("\n↜ ")
            await b.mention(uid, user)
            if extra:
                b.text(f"\n{extra}")
            b.text("\n──────────────")
        msg_text, entities = b.build()
        await safe_reply(event, msg_text, entities=entities)
        if ci != len(chunks) - 1:
            await asyncio.sleep(1.0)


EXTRA_CMD_PREFIXES = (
    "تنظیم حداکثر اخطار", "تنظیم مجازات ", "لیست قفل", "لیست اخطار", "لیست معاف",
    "ریست لیست معاف", "لیست کیل", "ریست لیست کیل", "ریست لیست اخطار", "کیل", "حذف کیل", "اخطار",
    "حذف اخطار", "تنظیمات اسپم", "تنظیم تعداد پیام", "تنظیم پیام تکراری اسپم",
    "تنظیم خط تکراری اسپم", "تنظیم تکرار کلمه اسپم", "بازنشانی تنظیمات اسپم", "تگ", "لیست تگ",
)


@client.on_message()
async def moderation_extras_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not text or not chat_id or not sender_id or getattr(event, 'is_private', False):
        return
    if not text.startswith(EXTRA_CMD_PREFIXES):
        return

    chat = get_chat_cfg(chat_id)
    ntext = normalize_digits(text)
    admin = is_admin(chat, sender_id)

    if text in ("تگ", "لیست تگ"):
        if admin:
            await safe_reply(event, HELP_TAG_TEXT)
        return

    if text == "تگ مالک":
        if not admin:
            return
        owner = chat.get("group_owner")
        await tag_user_list(event, "👑 تگ مالک", [owner] if owner else [],
                            "👑 مالک این گپ تنظیم نشده است.")
        return

    if text == "لیست قفل":
        if not admin:
            return
        await safe_reply(event, _locks_overview_text(chat))
        return

    if text == "لیست اخطار":
        if not admin:
            return
        rows = []
        for uid_str, per in (chat.get("warnings") or {}).items():
            parts = []
            for k, cnt in (per or {}).items():
                if not cnt:
                    continue
                mx, _p = _warn_cfg(chat, k)
                label = _warn_label(k)
                parts.append(f"{label} {_fa_num(cnt)}/{_fa_num(mx)}")
            if parts:
                try:
                    rows.append((int(uid_str), "⚠️ " + " • ".join(parts)))
                except ValueError:
                    continue
        await _send_user_rows(event, "⚠️", "لیست اخطار", rows)
        return

    if text == "ریست لیست اخطار":
        if not admin:
            return
        chat["warnings"] = {}
        await save_config(config)
        await safe_reply(event, "✅ لیست اخطارها پاک شد.")
        return

    if text == "لیست معاف":
        if not admin:
            return
        rows = []
        for uid in chat.get("exempt", []):
            try:
                rows.append((int(uid), ""))
            except (TypeError, ValueError):
                continue
        await _send_user_rows(event, "🛡️", "لیست معاف", rows)
        return

    if text == "ریست لیست معاف":
        if not admin:
            return
        if not chat.get("exempt"):
            await safe_reply(event, "لیست معاف از قبل خالی بود.")
            return
        count = len(chat["exempt"])
        chat["exempt"] = []
        await save_config(config)
        await safe_reply(event, f"✅ لیست معاف پاک شد؛ معافیتِ {count} کاربر لغو شد.")
        return

    if text == "لیست کیل":
        if not admin:
            return
        rows = []
        for uid_str, until in (chat.get("killed") or {}).items():
            try:
                uid = int(uid_str)
            except ValueError:
                continue
            extra = "🔁 دائم (تا حذف کیل)" if not until else f"⏳ تا {format_jalali_dt(until)}"
            rows.append((uid, extra))
        await _send_user_rows(event, "🎯", "لیست کیل", rows)
        return

    if text == "ریست لیست کیل":
        if not admin:
            return
        chat["killed"] = {}
        await save_config(config)
        await safe_reply(event, "✅ لیست کیل پاک شد.")
        return

    if text.startswith("تنظیم حداکثر اخطار"):
        if not admin:
            return
        rest = ntext[len("تنظیم حداکثر اخطار"):].strip()
        usage = ("❓ فرمت درست:\n"
                 "- تنظیم حداکثر اخطار لینک 3\n"
                 "- تنظیم حداکثر اخطار 3 «برای همه‌ی قفل‌ها»\n"
                 "- تنظیم حداکثر اخطار دستی 3")
        m_all = re.fullmatch(r"(\d+)", rest)
        m_one = re.fullmatch(r"(.+?)\s+(\d+)", rest)
        if m_all:
            num = int(m_all.group(1))
            key = None
        elif m_one:
            num = int(m_one.group(2))
            key = _warn_key_from_name(m_one.group(1))
            if key is None:
                await safe_reply(event, f"❓ قفلی با اسم «{m_one.group(1).strip()}» پیدا نشد.")
                return
            if key in PERMISSION_LOCK_KEYS:
                await safe_reply(event, f"ℹ️ قفل {_warn_label(key)} با دسترسی گروه اجرا می‌شود و اخطار ندارد.")
                return
        else:
            await safe_reply(event, usage)
            return
        if not (1 <= num <= WARN_MAX_LIMIT):
            await safe_reply(event, f"❓ حداکثر اخطار باید بین ۱ تا {_fa_num(WARN_MAX_LIMIT)} باشد.")
            return
        if key is None:
            for k in WARN_LOCK_KEYS:
                _warn_set(chat, k, max_=num)
            await save_config(config)
            await safe_reply(event, f"✅ حداکثر اخطار همه‌ی قفل‌ها روی «{_fa_num(num)}» تنظیم شد.")
        else:
            _warn_set(chat, key, max_=num)
            await save_config(config)
            label = "دستی" if key == WARN_MANUAL_KEY else f"قفل {_warn_label(key)}"
            await safe_reply(event, f"✅ حداکثر اخطار {label} روی «{_fa_num(num)}» تنظیم شد.")
        return

    if text.startswith("تنظیم مجازات "):
        rest = re.sub(r"\s+", " ", text[len("تنظیم مجازات "):]).strip()
        key, pun_text = _split_lock_name(rest)
        if key is None:
            pun = parse_punishment_text(rest)
            if pun is None:
                return
            if not admin:
                return
            for k in WARN_LOCK_KEYS:
                _warn_set(chat, k, punishment=pun)
            chat["spam_punishment"] = pun
            await save_config(config)
            await safe_reply(event, f"✅ مجازات همه‌ی قفل‌ها روی «{_warn_punish_fa(pun)}» تنظیم شد.")
            return
        if not admin:
            return
        if key in PERMISSION_LOCK_KEYS:
            await safe_reply(event, f"ℹ️ قفل {_warn_label(key)} با دسترسی گروه اجرا می‌شود و مجازات ندارد.")
            return
        pun = parse_punishment_text(pun_text)
        if pun is None:
            await safe_reply(event,
                "❓ نوع مجازات نامعتبر است. مثال‌ها:\n"
                "- تنظیم مجازات لینک بن\n"
                "- تنظیم مجازات لینک سکوت\n"
                "- تنظیم مجازات لینک سکوت 10 دقیقه\n"
                "- تنظیم مجازات لینک هشدار")
            return
        _warn_set(chat, key, punishment=pun)
        await save_config(config)
        label = "اخطار دستی" if key == WARN_MANUAL_KEY else f"قفل {_warn_label(key)}"
        await safe_reply(event, f"✅ مجازات {label} روی «{_warn_punish_fa(pun)}» تنظیم شد.")
        return

    if text == "تنظیمات اسپم":
        if not admin:
            return
        await safe_reply(event, _spam_settings_text(chat))
        return

    if text == "بازنشانی تنظیمات اسپم":
        if not admin:
            return
        chat["spam_settings"] = {}
        chat["spam_punishment"] = {"type": "timed_mute", "minutes": 10}
        await save_config(config)
        await safe_reply(event, "✅ تنظیمات اسپم به حالت اولیه برگشت.\n" + _spam_settings_text(chat))
        return

    if text.startswith("تنظیم تعداد پیام"):
        if not admin:
            return
        m = re.fullmatch(r"تنظیم تعداد پیام (\d+) در (\d+) ثانیه", ntext)
        if not m:
            await safe_reply(event, "❓ فرمت درست: «تنظیم تعداد پیام 5 در 3 ثانیه»")
            return
        cnt, sec = int(m.group(1)), int(m.group(2))
        if not (2 <= cnt <= 30) or not (1 <= sec <= 60):
            await safe_reply(event, "❓ تعداد پیام باید بین ۲ تا ۳۰ و زمان بین ۱ تا ۶۰ ثانیه باشد.")
            return
        chat.setdefault("spam_settings", {}).update({"msg_count": cnt, "window": sec})
        await save_config(config)
        await safe_reply(event, f"✅ اسپم: {_fa_num(cnt)} پیام در {_fa_num(sec)} ثانیه تنظیم شد.")
        return

    if text.startswith("تنظیم پیام تکراری اسپم"):
        if not admin:
            return
        m = re.fullmatch(r"تنظیم پیام تکراری اسپم (\d+)", ntext)
        if not m or not (m.group(1) == "0" or 2 <= int(m.group(1)) <= 20):
            await safe_reply(event, "❓ فرمت درست: «تنظیم پیام تکراری اسپم 3» (بین ۲ تا ۲۰؛ عدد 0 = خاموش)")
            return
        n = int(m.group(1))
        chat.setdefault("spam_settings", {})["dup"] = n
        await save_config(config)
        await safe_reply(event, "✅ تشخیص پیام تکراری خاموش شد." if n == 0
                         else f"✅ اگر یک متن {_fa_num(n)} بار پشت‌سرهم ارسال شود، اسپم حساب می‌شود.")
        return

    if text.startswith("تنظیم خط تکراری اسپم"):
        if not admin:
            return
        m = re.fullmatch(r"تنظیم خط تکراری اسپم (\d+)", ntext)
        if not m or not (m.group(1) == "0" or 3 <= int(m.group(1)) <= 50):
            await safe_reply(event, "❓ فرمت درست: «تنظیم خط تکراری اسپم 4» (بین ۳ تا ۵۰؛ عدد 0 = خاموش)")
            return
        n = int(m.group(1))
        chat.setdefault("spam_settings", {})["line_repeat"] = n
        await save_config(config)
        await safe_reply(event, "✅ تشخیص خط تکراری خاموش شد." if n == 0
                         else f"✅ اگر {_fa_num(n)} خطِ تکراری یا مشابه توی یک پیام باشد، اسپم حساب می‌شود.")
        return

    if text.startswith("تنظیم تکرار کلمه اسپم"):
        if not admin:
            return
        m = re.fullmatch(r"تنظیم تکرار کلمه اسپم (\d+)", ntext)
        if not m or not (m.group(1) == "0" or 3 <= int(m.group(1)) <= 100):
            await safe_reply(event, "❓ فرمت درست: «تنظیم تکرار کلمه اسپم 5» (بین ۳ تا ۱۰۰؛ عدد 0 = خاموش)")
            return
        n = int(m.group(1))
        chat.setdefault("spam_settings", {})["word_repeat"] = n
        await save_config(config)
        await safe_reply(event, "✅ تشخیص تعداد خطوط خاموش شد." if n == 0
                         else f"✅ اگر یک پیام {_fa_num(n)} خط یا بیشتر داشته باشد، اسپم حساب می‌شود.")
        return

    if text == "کیل" or text.startswith("کیل "):
        if not admin:
            return
        rest = text[len("کیل"):].strip()
        if not _looks_like_target_args(event, rest):
            return
        target, time_part = await _cmd_target(event, chat_id, rest)
        if not target:
            await safe_reply(event,
                "❓ باید روی پیام فرد ریپلای کنی یا آیدی/یوزرنیمش را بنویسی.\n"
                "مثال: «کیل» (ریپلای) | «کیل 10 دقیقه» | «کیل @username 1 ساعت» | «کیل 123456789»")
            return
        my_id = await _ship_get_my_id()
        if target == my_id or target == sender_id or is_admin(chat, target):
            await safe_reply(event, "⛔️ روی ادمین‌ها، خودت و خودِ ربات نمی‌شود کیل زد.")
            return
        minutes = None
        if time_part:
            minutes = parse_time_to_minutes(time_part)
            if not minutes or minutes <= 0:
                await safe_reply(event,
                    f"❓ زمان «{time_part}» قابل تشخیص نیست؛ مثال: «کیل 10 دقیقه» یا «کیل 1 ساعت». "
                    "برای کیلِ دائمی فقط بنویس «کیل».")
                return
        if minutes:
            until = _accurate_now(event) + timedelta(minutes=minutes)
            chat.setdefault("killed", {})[str(target)] = until.isoformat()
            await save_config(config)
            await notify_user_action(event, chat, target, "🎯", " کیل شد.",
                                      details=[("⏱", "مدت", format_minutes_fa(minutes))],
                                      footer="تا پایان مدت، هر پیامی بفرستد پاک می‌شود.")
        else:
            chat.setdefault("killed", {})[str(target)] = None
            await save_config(config)
            await notify_user_action(event, chat, target, "🎯", " کیل شد.",
                                      footer="هر پیامی بفرستد پاک می‌شود؛ تا «حذف کیل».")
        return

    if text == "حذف کیل" or text.startswith("حذف کیل "):
        if not admin:
            return
        rest = text[len("حذف کیل"):].strip()
        if not _looks_like_target_args(event, rest):
            return
        target, _rest = await _cmd_target(event, chat_id, rest)
        if not target:
            await safe_reply(event, "❓ باید روی پیام فرد ریپلای کنی یا آیدی/یوزرنیمش را بنویسی.")
            return
        if str(target) not in (chat.get("killed") or {}):
            await safe_reply(event, "ℹ️ این کاربر کیل نیست.")
            return
        chat["killed"].pop(str(target), None)
        await save_config(config)
        await notify_user_action(event, chat, target, "✅", " کیل کاربر برداشته شد.",
                                  footer="دیگر پیام‌هایش پاک نمی‌شود.")
        return

    if text == "اخطار" or text.startswith("اخطار "):
        if not admin:
            return
        rest = text[len("اخطار"):].strip()
        if not _looks_like_target_args(event, rest):
            return
        target, _rest = await _cmd_target(event, chat_id, rest)
        if not target:
            await safe_reply(event, "❓ باید روی پیام فرد ریپلای کنی یا آیدی/یوزرنیمش را بنویسی.")
            return
        my_id = await _ship_get_my_id()
        if target == my_id or target == sender_id or is_admin(chat, target):
            await safe_reply(event, "⛔️ به ادمین‌ها، خودت و خودِ ربات نمی‌شود اخطار داد.")
            return
        mx, pun = _warn_cfg(chat, WARN_MANUAL_KEY)
        if pun.get("type", "normal") == "normal":
            await notify_user_action(event, chat, target, "⚠️", " اخطار گرفت.",
                                      footer="مجازات اخطار دستی روی «هشدار» است؛ اخطاری ثبت نمی‌شود.")
            return
        count = _warn_add(chat, target, WARN_MANUAL_KEY)
        if count >= mx:
            _warn_clear(chat, target)
            await save_config(config)
            await apply_group_punishment(event, chat_id, chat, target, pun,
                                         f"اخطار دستی ({_fa_num(mx)} اخطار)", force_notify=True)
        else:
            await save_config(config)
            await send_neon_warning(event, chat, target, count, mx, pun,
                                    reason="اخطار دستی", by_id=sender_id)
        return

    if text == "حذف اخطار" or text.startswith("حذف اخطار "):
        if not admin:
            return
        rest = text[len("حذف اخطار"):].strip()
        if not _looks_like_target_args(event, rest):
            return
        target, _rest = await _cmd_target(event, chat_id, rest)
        if not target:
            await safe_reply(event, "❓ باید روی پیام فرد ریپلای کنی یا آیدی/یوزرنیمش را بنویسی.")
            return
        _warn_clear(chat, target)
        await save_config(config)
        await notify_user_action(event, chat, target, "✅", " اخطارهایش پاک شد.")
        return


@client.on_message()
async def admin_commands_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    text = _apply_command_aliases(text)
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)

    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return

    chat = get_chat_cfg(chat_id)

    if text == "تگ همه":
        if not is_admin(chat, sender_id):
            return
        ok = await _tag_all_individually(event, chat_id, lambda uid, u: random.choice(TAG_ALL_PHRASES))
        if not ok:
            await safe_reply(event, "ℹ️ کسی برای تگ کردن نمانده.")
        return

    _m_tag_text = re.fullmatch(r"تگ متن (.+)", text, re.DOTALL)
    if _m_tag_text:
        if not is_admin(chat, sender_id):
            return
        custom_text = _m_tag_text.group(1).strip()
        if not custom_text:
            await safe_reply(event, "❓ بعد از «تگ متن» باید متن دلخواهت را بنویسی؛ مثلاً: تگ متن سلام {تگ}")
            return
        ok = await _tag_all_individually(event, chat_id, lambda uid, u: custom_text)
        if not ok:
            await safe_reply(event, "ℹ️ کسی برای تگ کردن نمانده.")
        return

    _tag_limit = None
    _m_tag = re.fullmatch(r"تگ (\d{1,4})", normalize_digits(text))
    if _m_tag:
        _tag_limit = max(1, int(_m_tag.group(1)))
        text = "لیست اعضا"

    if text == "راهنما":
        await safe_reply(event, HELP_MAIN_TEXT)
        return

    if text in ("راهنمای قفل", "راهنما قفل"):
        await safe_reply(event, HELP_LOCK_TEXT)
        return

    if text in ("راهنمای مدیران", "راهنما مدیران"):
        await safe_reply(event, HELP_ADMIN_TEXT)
        return

    if text in ("راهنمای لیست", "راهنما لیست", "راهنمای لیست و تگ"):
        await safe_reply(event, HELP_LIST_TEXT)
        return

    if text in ("راهنمای سرگرمی", "راهنما سرگرمی"):
        await safe_reply(event, HELP_FUN_TEXT)
        return

    if text == "لیست اعضا":
        if not is_admin(chat, sender_id):
            return

        try:
            me = await client.get_me()
        except Exception:
            me = None
        my_id = getattr(me, 'id', None)

        seen, real_admin_ids, counts_log = await fetch_members_fast(chat_id, my_id)

        admin_members = []
        normal_members = []

        admin_ids_all = set(real_admin_ids)
        for _uid, _u in seen.items():
            _pcls = type(getattr(_u, 'participant', None)).__name__
            if 'Admin' in _pcls or 'Creator' in _pcls:
                admin_ids_all.add(_uid)

        for _uid, _u in seen.items():
            if _uid in admin_ids_all:
                admin_members.append((_uid, _u))
            elif is_admin(chat, _uid):
                continue
            else:
                normal_members.append((_uid, _u))

        if _tag_limit:
            admin_members = []
            random.shuffle(normal_members)
            normal_members = normal_members[:_tag_limit]

        if not admin_members and not normal_members:
            if seen:
                await safe_reply(event, "ℹ️ کسی برای تگ کردن نمانده.")
            else:
                await safe_reply(
                    event,
                    "❗️ با هیچ فیلتری عضوی پیدا نشد.\n"
                    f"نتیجه‌ی هر فیلتر: {' | '.join(counts_log)}"
                )
            return

        TAG_CHUNK_SIZE = 150
        sections = []
        if admin_members:
            for i in range(0, len(admin_members), TAG_CHUNK_SIZE):
                sections.append((f"👑 تگ ادمین‌ها ({len(admin_members)} نفر):", admin_members[i:i + TAG_CHUNK_SIZE], True))
        member_chunks = [normal_members[i:i + TAG_CHUNK_SIZE] for i in range(0, len(normal_members), TAG_CHUNK_SIZE)]
        for j, chunk in enumerate(member_chunks, start=1):
            sections.append((f"📢 تگ اعضا ({j}/{len(member_chunks)} - {len(normal_members)} نفر):", chunk, False))

        tagged_ids = set()
        for idx, (title, chunk, is_admin_section) in enumerate(sections, start=1):
            chunk = [
                (u, o) for (u, o) in chunk
                if u not in tagged_ids
                and (is_admin_section or (u not in admin_ids_all and not is_admin(chat, u)))
            ]
            if not chunk:
                continue
            tagged_ids.update(u for u, _ in chunk)
            mb = MentionTextBuilder()
            mb.text(f"{title}\n\n")
            for i, (uid, user_obj) in enumerate(chunk):
                await mb.mention(uid, user_obj)
                if i != len(chunk) - 1:
                    mb.text("، ")
            msg_text, tag_entities = mb.build()
            await safe_reply(event, msg_text, entities=tag_entities)
            if idx != len(sections):
                await asyncio.sleep(0.3)
        return


    if text in ("تگ ادمین", "تگ معاف", "تگ سکوت"):
        if not is_admin(chat, sender_id):
            return
        if text == "تگ ادمین":
            if ChannelParticipantsAdmins is None:
                await safe_reply(event, "⚠️ فیلتر ادمین‌ها در کتابخانه پیدا نشد.")
                return
            try:
                _me = await client.get_me()
            except Exception:
                _me = None
            _my_id = getattr(_me, 'id', None)
            _admin_users = {}
            try:
                async for _p in client.iter_participants(chat_id, filter=ChannelParticipantsAdmins):
                    _pid = getattr(_p, 'id', None)
                    if (
                        _pid and _pid != _my_id
                        and not getattr(_p, 'bot', False)
                        and not getattr(_p, 'deleted', False)
                    ):
                        _admin_users[_pid] = _p
            except Exception as e:
                await safe_reply(event, f"⚠️ خطا در گرفتن ادمین‌های گروه: {e}")
                return
            await tag_user_list(event, "👮 تگ ادمین‌ها", list(_admin_users.keys()),
                                "ادمینی برای تگ کردن پیدا نشد.", users=_admin_users)
        elif text == "تگ معاف":
            await tag_user_list(event, "🛡️ تگ معاف‌ها", list(chat.get("exempt", [])),
                                "لیست معاف‌های این گپ خالی است.")
        else:
            await tag_user_list(event, "🔇 تگ لیست سکوت", list((chat.get("muted") or {}).keys()),
                                "📋 لیست سکوت خالی است.")
        return

    _text_norm = text.replace("\u200c", " ")

    if text in ("سرگرمی روشن", "سرگرمی خاموش"):
        if not is_admin(chat, sender_id):
            return
        chat["fun_enabled"] = (text == "سرگرمی روشن")
        await save_config(config)
        if chat["fun_enabled"]:
            await safe_reply(event, "✅ سرگرمی روشن شد؛ همه می‌توانند از دستورهای سرگرمی استفاده کنند.")
        else:
            await safe_reply(event, "✅ سرگرمی خاموش شد؛ از حالا دستورهای سرگرمی فقط برای مدیران کار می‌کنند.")
        return

    if text in ("صدا خفه کن روشن", "صدا خفه کن خاموش"):
        if not is_admin(chat, sender_id):
            return
        chat["silent_mode"] = (text == "صدا خفه کن روشن")
        await save_config(config)
        await safe_reply(event, f"✅ صدا خفه‌کن {'روشن' if chat['silent_mode'] else 'خاموش'} شد.", )
        return


    if text in ("حذف خودکار پیام روشن", "حذف خودکار پیام خاموش"):
        if not is_admin(chat, sender_id):
            return
        chat["auto_delete_messages_enabled"] = (text == "حذف خودکار پیام روشن")
        await save_config(config)
        if chat["auto_delete_messages_enabled"]:
            await safe_reply(
                event,
                "✅ حذف خودکار پیام روشن شد؛ از این به بعد فقط این پیغام‌ها در این گپ ۳ "
                "ثانیه بعد از ارسال خودکار پاک می‌شوند: قفل ضد تبچی، قفل ممبر دزد، قفل بیو، "
                "قفل اسم، اخطار عادی، سکوت‌شدن بعد از اسپم، و اخطارِ قفل‌ها (لینک/شماره/"
                "کد هنگی/فوروارد/آیدی). بقیه‌ی پیام‌های ربات (تاییدیه، سکوت/بن دستی، وضعیت "
                "و ...) پاک نمی‌شوند.",
            )
        else:
            await safe_reply(event, "✅ حذف خودکار پیام خاموش شد.")
        return

    if text.startswith("تنظیم زمان پاک شدن"):
        if not is_admin(chat, sender_id):
            return
        value_part = text[len("تنظیم زمان پاک شدن"):].strip()
        if not value_part:
            current = chat.get("auto_delete_delay_seconds")
            current = current if current is not None else AUTO_DELETE_MESSAGE_DELAY_SECONDS
            await safe_reply(
                event,
                f"⏱ زمان فعلی پاک شدن خودکار پیام‌های ربات: {current} ثانیه\n"
                "برای تغییر بنویس مثلاً: «تنظیم زمان پاک شدن 0.1»",
            )
            return
        try:
            seconds = float(value_part.replace(",", "."))
        except ValueError:
            await safe_reply(event, "❓ عدد وارد شده معتبر نیست؛ مثال: «تنظیم زمان پاک شدن 0.1»")
            return
        if seconds < 0 or seconds > 3600:
            await safe_reply(event, "❓ زمان باید بین 0 تا 3600 ثانیه باشد.")
            return
        chat["auto_delete_delay_seconds"] = seconds
        await save_config(config)
        await safe_reply(event, f"✅ زمان پاک شدن خودکار پیام‌های ربات روی {seconds} ثانیه تنظیم شد.")
        return


    if text in ("تنظیم ادمین", "حذف ادمین"):
        if not is_owner_level(chat, sender_id):
            return
        target = await resolve_target(event, chat_id, "")
        if not target:
            await safe_reply(event, "❓ باید روی پیام فرد موردنظر ریپلای کنی.")
            return
        if text == "تنظیم ادمین":
            if target not in chat["admins"]:
                chat["admins"].append(target)
            await save_config(config)
            await notify_user_action(event, chat, target, "👑", " به مدیریت گروه اضافه شد.",
                                      footer="سطح دسترسی با موفقیت تنظیم شد.")
        else:
            if target in chat["admins"]:
                chat["admins"].remove(target)
            await save_config(config)
            await notify_user_action(event, chat, target, "📤", " دسترسی مدیریتی او لغو شد.",
                                      footer="کاربر دیگر مدیر گروه نیست.")
        return


    if text == "لیست ادمین":
        if not is_admin(chat, sender_id):
            return
        rows = []
        owner_id = chat.get("group_owner")
        if owner_id:
            rows.append(("👑", owner_id))
        for uid in chat.get("admins", []):
            rows.append(("🔰", uid))
        if not rows:
            await safe_reply(event, "لیست ادمین‌های این گپ خالی است.")
            return
        b = MentionTextBuilder().text(
            f"╭─〔 👮 لیست ادمین‌ها 〕─╮\n╰─ تعداد: 『{to_persian_digits(str(len(rows)))}』"
        )
        for emoji, uid in rows:
            try:
                u = await client.get_entity(uid)
            except Exception:
                u = None
            b.text(f"\n{emoji} ")
            await b.mention(uid, u)
        msg_text, entities = b.build()
        await safe_reply(event, msg_text, entities=entities)
        return


    if text == "بررسی ادمین":
        if not is_owner_level(chat, sender_id):
            return
        try:
            added_count, found_admins = await sync_group_admins_from_soroush(chat_id, chat)
            await safe_reply(event, 
                "✅ بررسی ادمین‌های گپ انجام شد.\n"
                f"👥 تعداد ادمین‌های واقعی گپ: {found_admins}\n"
                f"➕ تعداد ادمین جدیدی که به ربات اضافه شد: {added_count}"
            )
        except Exception as e:
            await safe_reply(event, f"⚠️ خطا در بررسی ادمین‌های گپ: {e}")
        return


    if text in ("تنظیم مالک گپ", "حذف مالک گپ"):
        if not is_bot_owner(sender_id):
            return
        if text == "تنظیم مالک گپ":
            target = await resolve_target(event, chat_id, "")
            if not target:
                await safe_reply(event, "❓ باید روی پیام فرد موردنظر ریپلای کنی.")
                return
            chat["group_owner"] = target
            await save_config(config)
            await notify_user_action(event, chat, target, "✅", " مالک گپ شد.")
        else:
            chat["group_owner"] = None
            await save_config(config)
            await safe_reply(event, "✅ مالک گپ حذف شد.")
        return


    if text in ("معاف", "لغو معاف"):
        if not is_admin(chat, sender_id):
            return
        target = await resolve_target(event, chat_id, "")
        if not target:
            await safe_reply(event, "❓ باید روی پیام فرد موردنظر ریپلای کنی.")
            return
        if text == "معاف":
            if target not in chat["exempt"]:
                chat["exempt"].append(target)
            await save_config(config)
            await notify_user_action(event, chat, target, "🛡️", " از محدودیت‌های مدیریتی معاف شد.",
                                      footer="کاربر در فهرست معاف‌ها قرار گرفت.")
        else:
            if target in chat["exempt"]:
                chat["exempt"].remove(target)
            await save_config(config)
            await notify_user_action(event, chat, target, "🚫", " معافیت کاربر لغو شد.",
                                      footer="قوانین گروه مجدداً روی کاربر اعمال می‌شود.")
        return


    if text in ("بن فعال", "بن غیرفعال"):
        if not is_owner_level(chat, sender_id):
            return
        chat["ban_enabled"] = (text == "بن فعال")
        await save_config(config)
        await safe_reply(event, f"✅ بن برای ادمین‌های عادی {'فعال' if chat['ban_enabled'] else 'غیرفعال'} شد.")
        return


    if text.startswith("فیلتر کلمه "):
        if not is_admin(chat, sender_id):
            return
        word = text[len("فیلتر کلمه "):].strip()
        if word:
            if word not in chat["word_filters"]:
                chat["word_filters"].append(word)
                await save_config(config)
                await safe_reply(event, "🛡️ فیلتر محتوا به‌روزرسانی شد.\n" + build_action_block(
                    details=[("🔤", "کلمه", word)], footer="کلمه به فهرست فیلتر اضافه شد."))
            else:
                await safe_reply(event, f"ℹ️ کلمه «{word}» از قبل در لیست بود.")
        return

    if text.startswith("حذف فیلتر کلمه "):
        if not is_admin(chat, sender_id):
            return
        word = text[len("حذف فیلتر کلمه "):].strip()
        if word in chat["word_filters"]:
            chat["word_filters"].remove(word)
            await save_config(config)
            await safe_reply(event, "🛡️ فیلتر محتوا به‌روزرسانی شد.\n" + build_action_block(
                details=[("🔤", "کلمه", word)], footer="کلمه از فهرست فیلتر حذف شد."))
        else:
            await safe_reply(event, "ℹ️ این کلمه در لیست فیلتر نبود.")
        return

    if text == "لیست فیلتر کلمه":
        if not is_admin(chat, sender_id):
            return
        words = chat.get("word_filters", [])
        if words:
            await safe_reply(event, wrap_box("📋", "لیست فیلتر کلمات", "\n".join(f"- {w}" for w in words)))
        else:
            await safe_reply(event, "لیست فیلتر خالی است.")
        return

    if text == "ریست لیست فیلتر":
        if not is_admin(chat, sender_id):
            return
        chat["word_filters"] = []
        await save_config(config)
        await safe_reply(event, "🛡️ فیلتر محتوا به‌روزرسانی شد.\n" + build_action_block(
            footer="لیست فیلتر کلمات این گروه پاک شد."))
        _log(f"[CMD][{chat_id}] Word filter list (فیلتر کلمه) cleared")
        return

    if text == "فیلتر محتوا":
        if not is_admin(chat, sender_id):
            return
        reply_msg = await _get_reply_message(event, chat_id)
        if reply_msg is None:
            await safe_reply(event, "❓ باید روی پیامی که گیف دارد ریپلای کنی.")
            return
        if _get_gif_document(reply_msg) is None:
            await safe_reply(event, "❓ فیلتر محتوا فقط برای گیف است؛ روی عکس یا فیلم کار نمی‌کند. روی پیامِ یک گیف ریپلای کن.")
            return
        file_key, _kind = _media_file_key(reply_msg)
        kind_fa = "گیف"
        if not file_key:
            await safe_reply(event, "❓ شناسه‌ی این گیف قابل خواندن نبود.")
            return
        media_filters = chat.setdefault("media_filters", {})
        if file_key in media_filters:
            await safe_reply(event, f"ℹ️ این {kind_fa} از قبل در لیست فیلتر مدیا بود.")
            return
        media_filters[file_key] = kind_fa
        await save_config(config)
        await safe_reply(
            event,
            "🖼️ محتوای رسانه‌ای فیلترشده شناسایی و حذف شد.\n" + build_action_block(
                footer="مورد به فهرست فیلتر مدیا اضافه شد."),
        )
        _log(f"[CMD][{chat_id}] media filter added: {file_key}")
        return

    if text == "لیست فیلتر مدیا":
        if not is_admin(chat, sender_id):
            return
        media_filters = chat.get("media_filters") or {}
        if not media_filters:
            await safe_reply(event, "لیست فیلتر مدیا این گروه خالی است.")
            return
        counts = {}
        for kind_fa in media_filters.values():
            counts[kind_fa] = counts.get(kind_fa, 0) + 1
        breakdown = "، ".join(f"{to_persian_digits(str(n))} {k}" for k, n in counts.items())
        await safe_reply(
            event,
            wrap_box("📋", "لیست فیلتر مدیا",
                     f"تعداد: 『{to_persian_digits(str(len(media_filters)))}』\n({breakdown})"),
        )
        return

    if text == "ریست لیست فیلتر مدیا":
        if not is_admin(chat, sender_id):
            return
        count = len(chat.get("media_filters") or {})
        if not count:
            await safe_reply(event, "لیست فیلتر مدیا از قبل خالی بود.")
            return
        chat["media_filters"] = {}
        await save_config(config)
        await safe_reply(event, "🛡️ فیلتر محتوا به‌روزرسانی شد.\n" + build_action_block(
            details=[("🗑", "فایل‌های پاک‌شده", to_persian_digits(str(count)))],
            footer="لیست فیلتر مدیا پاک شد."))
        _log(f"[CMD][{chat_id}] media filter list cleared")
        return


    if text in ("قفل ضد تبلیغات", "بستن قفل ضد تبلیغات", "قفل تبلیغات", "بستن قفل تبلیغات"):
        if not is_admin(chat, sender_id):
            return
        chat["anti_ad_lock_enabled"] = True
        await save_config(config)
        ensure_cleanup_task_running()
        await safe_reply(
            event,
            "📢 قفل ضد تبلیغات فعال شد.\n" + build_action_block(
                footer="تبلیغات و لینک‌های تبلیغاتی بررسی می‌شوند؛ هر نقض یک اخطار دارد."),
        )
        _log(f"[CMD][{chat_id}] قفل ضد تبلیغات ON")
        return

    if text in ("قفل ضد تبلیغات خاموش", "باز کردن قفل ضد تبلیغات", "قفل تبلیغات خاموش", "باز کردن قفل تبلیغات"):
        if not is_admin(chat, sender_id):
            return
        chat["anti_ad_lock_enabled"] = False
        await save_config(config)
        for k in [k for k in ad_tracker if k[0] == chat_id]:
            ad_tracker.pop(k, None)
        await safe_reply(event, "📢 قفل ضد تبلیغات خاموش شد.\n" + build_action_block(
            footer="بررسی تبلیغات متوقف شد."))
        _log(f"[CMD][{chat_id}] قفل ضد تبلیغات OFF")
        return


    if _LOCK_ALL_RE.match(re.sub(r"\s+", " ", text.replace("\u200c", " ")).strip()):
        if not is_admin(chat, sender_id):
            return
        locks_cfg = chat.setdefault("locks", {})
        for key in LOCK_ALL_KEYS:
            locks_cfg[key] = True
        for flag, _label in LOCK_ALL_EXTRA_FLAGS:
            chat[flag] = True
        await save_config(config)
        ensure_cleanup_task_running()
        basic_names = "، ".join(LOCK_FA_NAMES[k] for k in LOCK_ALL_KEYS)
        extra_names = "، ".join(label for _flag, label in LOCK_ALL_EXTRA_FLAGS)
        skipped_names = "، ".join(LOCK_FA_NAMES[k] for k in LOCK_FA_NAMES if k in LOCK_ALL_EXCLUDED)
        await safe_reply(
            event,
            "🔒✨ همه‌ی قفل‌ها فعال شد.\n\n"
            f"✅ قفل‌ها: {basic_names}\n"
            f"✅ قفل‌های ویژه: {extra_names}\n\n"
            f"⏭ دست‌نخورده ماند: {skipped_names}",
        )
        _log(f"[CMD][{chat_id}] فعالسازی همه قفل‌ها")
        return

    lock_key = None
    turn_off = None
    if text.startswith("باز کردن قفل "):
        lock_name_fa = text[len("باز کردن قفل "):].strip()
        lock_key = LOCK_FA_TO_KEY.get(lock_name_fa)
        turn_off = True
    elif text.startswith("بستن قفل "):
        lock_name_fa = text[len("بستن قفل "):].strip()
        lock_key = LOCK_FA_TO_KEY.get(lock_name_fa)
        turn_off = False
    elif text.startswith("قفل "):
        rest = text[len("قفل "):].strip()
        turn_off = rest.endswith(" خاموش")
        lock_name_fa = rest[:-len(" خاموش")].strip() if turn_off else rest
        lock_key = LOCK_FA_TO_KEY.get(lock_name_fa)

    if lock_key:
        if not is_admin(chat, sender_id):
            return
        chat["locks"][lock_key] = not turn_off
        await save_config(config)
        if lock_key == "spam" and not turn_off:
            ensure_cleanup_task_running()
        if lock_key in ("gif", "photo", "sticker", "group", "media"):
            await apply_all_group_permissions(chat_id, chat)
        lock_label = LOCK_FA_NAMES.get(lock_key, lock_name_fa)
        if turn_off:
            lock_msg = f"🔓 قفل {lock_label} خاموش شد.\n" + build_action_block(footer="ارسال محتوای مربوطه آزاد شد.")
        else:
            lock_msg = f"🔒 قفل {lock_label} فعال شد.\n" + build_action_block(
                footer=LOCK_ON_FOOTERS.get(lock_key, "این نوع محتوا مسدود شد.")
            )
        await safe_reply(event, lock_msg)
        return


    if text.startswith("حذف کن"):
        if not is_admin(chat, sender_id):
            return
        rest = text[len("حذف کن"):].strip()
        if rest == "همش":
            count = None
        else:
            num_text = normalize_digits(rest)
            if not num_text.isdigit():
                await safe_reply(event, "❓ مثال درست: «حذف کن 20» یا «حذف کن همش»")
                return
            count = int(num_text)
        try:
            n = await bulk_delete(chat_id, count)
            await notify(event, chat, "🧹 عملیات پاکسازی انجام شد.\n" + build_action_block(
                details=[("🗑", "تعداد پیام‌ها", str(n))],
                footer="پیام‌های پین‌شده دست‌نخورده ماندند."), force=True)
        except Exception as e:
            await safe_reply(event, f"⚠️ خطا: {e}")
        return


    if text == "حذف پیام هاش":
        if not is_admin(chat, sender_id):
            return
        target = await resolve_target(event, chat_id, "")
        if not target:
            await safe_reply(event, "❓ باید روی پیام فرد موردنظر ریپلای کنی.")
            return
        try:
            stats = await _bulk_delete_run(chat_id, _bulk_keep_all, 2000, from_user=target)
            await notify_user_action(event, chat, target, "🧹", " پیام‌هایش حذف شد.",
                                      details=[("🗑", "تعداد پیام‌ها", str(stats["ok"]))])
        except Exception as e:
            await safe_reply(event, f"⚠️ خطا: {e}")
        return


    if text.startswith("پاکسازی خودکار رسانه"):
        if not is_admin(chat, sender_id):
            return
        rest = text[len("پاکسازی خودکار رسانه"):].strip()
        if not rest:
            await safe_reply(event,
                "❓ فرمت درست:\n"
                "«پاکسازی خودکار رسانه هر 30 دقیقه» (یا «هر 10 ثانیه» / «هر 1 ساعت»)\n"
                "یا «پاکسازی خودکار رسانه 12:30» (یک ساعت مشخص، به وقت تهران - هر بار بزنی به لیست اضافه می‌شود)"
            )
            return

        media_cfg = chat.setdefault("auto_media_cleanup", {"interval_seconds": None, "times": []})
        media_cfg.setdefault("times", [])

        if rest.startswith("هر"):
            seconds = parse_time_to_seconds(rest)
            if not seconds or seconds <= 0:
                await safe_reply(event,
                    "❓ زمان «{}» قابل تشخیص نیست؛ مثال: «پاکسازی خودکار رسانه هر 30 دقیقه» یا "
                    "«... هر 10 ثانیه» یا «... هر 1 ساعت».".format(rest)
                )
                return
            media_cfg["interval_seconds"] = seconds
            await save_config(config)
            ensure_scheduler_running()
            await safe_reply(event,
                "⏰ پاکسازی خودکار رسانه تنظیم شد.\n" + build_action_block(
                    details=[("🕐", "بازه", f"هر {format_seconds_fa(seconds)}")],
                    footer="عکس/فیلم/گیف/استیکر/فایل/ویس پاک می‌شوند؛ پیام‌های متنی دست‌نخورده می‌مانند."
                )
            )
            return

        hhmm = normalize_hhmm(rest)
        if not hhmm:
            await safe_reply(event,
                "❓ زمان «{}» قابل تشخیص نیست؛ مثال: «پاکسازی خودکار رسانه هر 30 دقیقه» یا "
                "«پاکسازی خودکار رسانه 12:30».".format(rest)
            )
            return
        times = media_cfg["times"]
        if hhmm in times:
            await safe_reply(event, f"ℹ️ ساعت {hhmm} از قبل در لیست پاکسازی خودکار رسانه بود.")
            return
        times.append(hhmm)
        await save_config(config)
        ensure_scheduler_running()
        await safe_reply(event,
            "⏰ پاکسازی خودکار رسانه تنظیم شد.\n" + build_action_block(
                details=[("🕐", "زمان اجرا", f"{hhmm} (تهران)")],
                footer=f"در حال حاضر {len(times)} زمان تنظیم شده؛ برای دیدن همه: «لیست پاکسازی رسانه»"
            )
        )
        return

    if text == "لیست پاکسازی رسانه":
        if not is_admin(chat, sender_id):
            return
        media_cfg = chat.get("auto_media_cleanup", {}) or {}
        interval_seconds = media_cfg.get("interval_seconds")
        times = media_cfg.get("times", [])
        lines = []
        if interval_seconds:
            lines.append(f"🔁 بازه‌ای: هر {format_seconds_fa(interval_seconds)}")
        if times:
            lines.append("🕒 زمان‌های مشخص (به وقت تهران):")
            lines.extend(f"- {t}" for t in sorted(times))
        if lines:
            await safe_reply(event, wrap_box("📋", "پاکسازی خودکار رسانه", "\n".join(lines)))
        else:
            await safe_reply(event, "لیست پاکسازی خودکار رسانه این گروه خالی است.")
        return

    if text.startswith("حذف پاکسازی رسانه"):
        if not is_admin(chat, sender_id):
            return
        rest = text[len("حذف پاکسازی رسانه"):].strip()
        media_cfg = chat.setdefault("auto_media_cleanup", {"interval_seconds": None, "times": []})
        if rest in ("هر", "بازه", "بازه‌ای", "بازه‌ای"):
            if media_cfg.get("interval_seconds"):
                media_cfg["interval_seconds"] = None
                await save_config(config)
                await safe_reply(event, "⛔ زمان‌بندی موردنظر حذف شد.\n" + build_action_block(
                    footer="پاکسازی خودکار رسانه‌ی بازه‌ای غیرفعال شد."))
            else:
                await safe_reply(event, "❓ پاکسازی بازه‌ای رسانه از قبل خاموش بود.")
            return
        hhmm = normalize_hhmm(rest)
        times = media_cfg.get("times", [])
        if hhmm and hhmm in times:
            times.remove(hhmm)
            await save_config(config)
            await safe_reply(event, "⛔ زمان‌بندی موردنظر حذف شد.\n" + build_action_block(
                details=[("🕐", "زمان", hhmm)]))
        else:
            await safe_reply(event, "❓ این زمان در لیست پاکسازی خودکار رسانه پیدا نشد. مثال: «حذف پاکسازی رسانه 12:30» یا «حذف پاکسازی رسانه هر»")
        return

    if text == "غیرفعال پاکسازی خودکار رسانه":
        if not is_admin(chat, sender_id):
            return
        chat["auto_media_cleanup"] = {"interval_seconds": None, "times": []}
        await save_config(config)
        await safe_reply(event, "⛔ زمان‌بندی موردنظر حذف شد.\n" + build_action_block(
            footer="پاکسازی خودکار رسانه (بازه‌ای و زمان‌های مشخص) کاملاً غیرفعال شد."))
        return

    if text == "پاکسازی رسانه":
        if not is_admin(chat, sender_id):
            return
        try:
            n = await bulk_delete_media(chat_id)
            await notify(event, chat, "🧹 پاکسازی رسانه انجام شد.\n" + build_action_block(
                details=[("🗑", "تعداد رسانه", str(n))]), force=True)
        except Exception as e:
            await safe_reply(event, f"⚠️ خطا: {e}")
        return

    if text.startswith("تنظیم پاکسازی خودکار"):
        if not is_admin(chat, sender_id):
            return
        rest = text[len("تنظیم پاکسازی خودکار"):].strip()
        if not rest:
            await safe_reply(event,
                "❓ فرمت درست:\n"
                "«تنظیم پاکسازی خودکار هر 1 ساعت» (یا «هر 30 دقیقه» / «هر 40 دقیقه»)\n"
                "یا «تنظیم پاکسازی خودکار 03:40» (یک ساعت مشخص، به وقت تهران - هر بار بزنی به لیست اضافه می‌شود)"
            )
            return

        cleanup_cfg = chat.setdefault("auto_cleanup", {"interval_seconds": None, "times": []})
        cleanup_cfg.setdefault("times", [])

        if rest.startswith("هر"):
            seconds = parse_time_to_seconds(rest)
            if not seconds or seconds <= 0:
                await safe_reply(event,
                    "❓ زمان «{}» قابل تشخیص نیست؛ مثال: «تنظیم پاکسازی خودکار هر 1 ساعت» یا "
                    "«... هر 30 دقیقه» یا «... هر 40 دقیقه».".format(rest)
                )
                return
            cleanup_cfg["interval_seconds"] = seconds
            await save_config(config)
            ensure_scheduler_running()
            await safe_reply(event,
                "⏰ پاکسازی خودکار تنظیم شد.\n" + build_action_block(
                    details=[("🕐", "بازه", f"هر {format_seconds_fa(seconds)}")],
                    footer="هر بار این بازه بگذرد، تمام پیام‌های گپ پاکسازی می‌شوند."
                )
            )
            return

        hhmm = normalize_hhmm(rest)
        if not hhmm:
            await safe_reply(event,
                "❓ زمان «{}» قابل تشخیص نیست؛ مثال: «تنظیم پاکسازی خودکار هر 1 ساعت» یا "
                "«تنظیم پاکسازی خودکار 03:40».".format(rest)
            )
            return
        times = cleanup_cfg["times"]
        if hhmm in times:
            await safe_reply(event, f"ℹ️ ساعت {hhmm} از قبل در لیست پاکسازی خودکار بود.")
            return
        times.append(hhmm)
        await save_config(config)
        ensure_scheduler_running()
        await safe_reply(event,
            "⏰ پاکسازی خودکار تنظیم شد.\n" + build_action_block(
                details=[("🕐", "زمان اجرا", f"{hhmm} (تهران)")],
                footer=f"در حال حاضر {len(times)} زمان تنظیم شده؛ برای دیدن همه: «لیست پاکسازی»"
            )
        )
        return

    if text == "لیست پاکسازی":
        if not is_admin(chat, sender_id):
            return
        cleanup_cfg = chat.get("auto_cleanup", {}) or {}
        interval_seconds = cleanup_cfg.get("interval_seconds")
        times = cleanup_cfg.get("times", [])
        lines = []
        if interval_seconds:
            lines.append(f"🔁 بازه‌ای: هر {format_seconds_fa(interval_seconds)}")
        if times:
            lines.append("🕒 زمان‌های مشخص (به وقت تهران):")
            lines.extend(f"- {t}" for t in sorted(times))
        if lines:
            await safe_reply(event, wrap_box("📋", "پاکسازی خودکار", "\n".join(lines)))
        else:
            await safe_reply(event, "لیست پاکسازی خودکار این گروه خالی است.")
        return

    if text.startswith("حذف پاکسازی "):
        if not is_admin(chat, sender_id):
            return
        rest = text[len("حذف پاکسازی "):].strip()
        cleanup_cfg = chat.setdefault("auto_cleanup", {"interval_seconds": None, "times": []})
        if rest in ("هر", "بازه", "بازه‌ای"):
            if cleanup_cfg.get("interval_seconds"):
                cleanup_cfg["interval_seconds"] = None
                await save_config(config)
                await safe_reply(event, "⛔ زمان‌بندی موردنظر حذف شد.\n" + build_action_block(
                    footer="پاکسازی خودکار بازه‌ای غیرفعال شد."))
            else:
                await safe_reply(event, "❓ پاکسازی بازه‌ای از قبل خاموش بود.")
            return
        hhmm = normalize_hhmm(rest)
        times = cleanup_cfg.get("times", [])
        if hhmm and hhmm in times:
            times.remove(hhmm)
            await save_config(config)
            await safe_reply(event, "⛔ زمان‌بندی موردنظر حذف شد.\n" + build_action_block(
                details=[("🕐", "زمان", hhmm)]))
        else:
            await safe_reply(event, "❓ این زمان در لیست پاکسازی خودکار پیدا نشد. مثال: «حذف پاکسازی 12:30» یا «حذف پاکسازی هر»")
        return

    if text == "غیرفعال پاکسازی خودکار":
        if not is_admin(chat, sender_id):
            return
        chat["auto_cleanup"] = {"interval_seconds": None, "times": []}
        await save_config(config)
        await safe_reply(event, "⛔ زمان‌بندی موردنظر حذف شد.\n" + build_action_block(
            footer="پاکسازی خودکار (بازه‌ای و زمان‌های مشخص) کاملاً غیرفعال شد."))
        return


    if text.startswith("تنظیم خودکار رفع سکوت"):
        if not is_admin(chat, sender_id):
            return
        hhmm = normalize_hhmm(text[len("تنظیم خودکار رفع سکوت"):].strip())
        if not hhmm:
            await safe_reply(event, "❓ فرمت درست: «تنظیم خودکار رفع سکوت 08:00»")
            return
        chat["auto_unmute_time"] = hhmm
        await save_config(config)
        ensure_scheduler_running()
        await safe_reply(event, "⏰ رفع سکوت خودکار تنظیم شد.\n" + build_action_block(
            details=[("🕐", "زمان", f"{hhmm} (تهران)")]))
        return

    if text.startswith("تنظیم خودکار رفع بن"):
        if not is_admin(chat, sender_id):
            return
        hhmm = normalize_hhmm(text[len("تنظیم خودکار رفع بن"):].strip())
        if not hhmm:
            await safe_reply(event, "❓ فرمت درست: «تنظیم خودکار رفع بن 08:00»")
            return
        chat["auto_unban_time"] = hhmm
        await save_config(config)
        ensure_scheduler_running()
        await safe_reply(event, "🔓 رفع بن خودکار تنظیم شد.\n" + build_action_block(
            details=[("🕐", "زمان", f"{hhmm} (تهران)")]))
        return


    if text.startswith("قفل خودکار گپ"):
        if not is_admin(chat, sender_id):
            return
        rest = text[len("قفل خودکار گپ"):].strip()
        if rest in ("خاموش", "غیرفعال"):
            chat["group_auto_lock"] = {"lock_time": None, "unlock_time": None}
            await save_config(config)
            await safe_reply(event, "⛔ زمان‌بندی موردنظر حذف شد.\n" + build_action_block(
                footer="قفل خودکار گروه غیرفعال شد."))
            return
        times = parse_two_times(rest)
        if not times:
            await safe_reply(event, 
                "❓ فرمت درست: «قفل خودکار گپ 23:00 | 08:00»\n"
                "(ساعت اول = زمان قفل شدن، ساعت دوم = زمان باز شدن)"
            )
            return
        lock_t, unlock_t = times
        chat["group_auto_lock"] = {"lock_time": lock_t, "unlock_time": unlock_t}
        await save_config(config)
        ensure_scheduler_running()
        await safe_reply(event, "🔒 قفل خودکار گروه تنظیم شد.\n" + build_action_block(
            details=[("🕐", "قفل", lock_t), ("🕐", "بازگشایی", unlock_t)]
        ))
        return


    if text == "لیست سکوت":
        if not is_admin(chat, sender_id):
            return
        muted = chat.get("muted", {})
        if muted:
            b = MentionTextBuilder().text(
                f"╭─〔 🔇 لیست سکوت 〕─╮\n╰─ تعداد: 『{to_persian_digits(str(len(muted)))}』\n──────────────"
            )
            for uid_str, until in muted.items():
                uid = int(uid_str)
                try:
                    user = await client.get_entity(uid)
                except Exception:
                    user = None
                until_fa = "🔁 سکوت دائم" if not until else f"⏳ تا {format_jalali_dt(until)}"
                b.text("\n↜ ")
                await b.mention(uid, user)
                b.text(f"\n{until_fa}\n──────────────")
            msg_text, entities = b.build()
            await safe_reply(event, msg_text, entities=entities)
        else:
            await safe_reply(event, "📋 لیست سکوت\n╰─ تعداد: 『۰』")
        return

    if text == "لیست بن":
        if not is_admin(chat, sender_id):
            return
        banned = chat.get("banned", {})
        if banned:
            b = MentionTextBuilder().text(
                f"╭─〔 🔨 لیست بن 〕─╮\n╰─ تعداد: 『{to_persian_digits(str(len(banned)))}』\n──────────────"
            )
            for uid_str, ban_date in banned.items():
                uid = int(uid_str)
                try:
                    user = await client.get_entity(uid)
                except Exception:
                    user = None
                date_fa = f"📅 {format_jalali_dt(ban_date)}" if ban_date else "📅 تاریخ نامشخص"
                b.text("\n↜ ")
                await b.mention(uid, user)
                b.text(f"\n{date_fa}\n──────────────")
            msg_text, entities = b.build()
            await safe_reply(event, msg_text, entities=entities)
        else:
            await safe_reply(event, "📋 لیست بن\n╰─ تعداد: 『۰』")
        return

    if text == "ریست لیست سکوت":
        if not is_admin(chat, sender_id):
            return
        muted = chat.get("muted", {})
        if not muted:
            await safe_reply(event, "لیست سکوت از قبل خالی بود.")
            return
        ok, fail = 0, 0
        for uid_str in list(muted.keys()):
            try:
                await client.edit_permissions(chat_id, int(uid_str), send_messages=True)
                ok += 1
            except Exception as e:
                fail += 1
                _log(f"⚠️ خطا در رفع سکوت واقعی کاربر {uid_str}: {e}")
            clear_spam_state(chat_id, int(uid_str))
        chat["muted"] = {}
        await save_config(config)
        msg = f"✅ سکوت {ok} کاربر واقعاً رفع شد و لیست پاک شد."
        if fail:
            msg += f"\n⚠️ برای {fail} کاربر رفع سکوت با خطا مواجه شد (شاید از قبل رفع شده بودند)."
        await safe_reply(event, msg)
        return

    if text == "ریست لیست بن":
        if not is_admin(chat, sender_id):
            return
        banned = chat.get("banned", {})
        if not banned:
            await safe_reply(event, "لیست بن از قبل خالی بود.")
            return
        ok, fail = 0, 0
        for uid_str in list(banned.keys()):
            try:
                await client.unban_chat_member(chat_id, int(uid_str))
                ok += 1
            except Exception as e:
                fail += 1
                _log(f"⚠️ خطا در رفع بن واقعی کاربر {uid_str}: {e}")
        chat["banned"] = {}
        await save_config(config)
        msg = f"✅ بن {ok} کاربر واقعاً رفع شد و لیست پاک شد."
        if fail:
            msg += f"\n⚠️ برای {fail} کاربر رفع بن با خطا مواجه شد (شاید از قبل رفع شده بودند)."
        await safe_reply(event, msg)
        return


    if text.startswith("تنظیم مجازات اسپم "):
        if not is_admin(chat, sender_id):
            return
        rest = text[len("تنظیم مجازات اسپم "):].strip()
        punishment = parse_punishment_text(rest)
        if not punishment:
            await safe_reply(event, 
                "❓ نوع مجازات نامعتبر است. مثال‌ها:\n"
                "- تنظیم مجازات اسپم عادی\n"
                "- تنظیم مجازات اسپم سکوت\n"
                "- تنظیم مجازات اسپم سکوت 10 دقیقه\n"
                "- تنظیم مجازات اسپم بن"
            )
            return
        chat["spam_punishment"] = punishment
        await save_config(config)
        await safe_reply(event, f"✅ مجازات اسپم روی «{punishment_to_fa(punishment)}» تنظیم شد.")
        return


    if text.startswith("تنظیم اقدام سکوت"):
        if not is_owner_level(chat, sender_id):
            return
        time_part = text[len("تنظیم اقدام سکوت"):].strip()
        minutes = parse_time_to_minutes(time_part)
        if not minutes or minutes <= 0:
            await safe_reply(event, "❓ فرمت درست: «تنظیم اقدام سکوت 10 دقیقه» یا «تنظیم اقدام سکوت یک ساعت»")
            return
        chat["mute_action_lock"] = {"minutes": minutes}
        await save_config(config)
        await safe_reply(event, 
            f"✅ از این پس، سکوتِ ادمین‌های عادی همیشه {format_minutes_fa(minutes)} خواهد بود "
            "(مالک گپ/ربات از این قانون مستثناست)."
        )
        return

    if text == "ریست اقدام سکوت":
        if not is_owner_level(chat, sender_id):
            return
        chat["mute_action_lock"] = None
        await save_config(config)
        await safe_reply(event, "✅ محدودیت اقدام سکوت پاک شد.")
        return


    if text in ("پین", "پین با اطلاع"):
        if not is_admin(chat, sender_id):
            return
        reply_id = getattr(event, 'reply_to_msg_id', None)
        if not reply_id:
            reply_obj = getattr(event, 'reply_to', None)
            reply_id = getattr(reply_obj, 'reply_to_msg_id', None) if reply_obj else None
        if not reply_id:
            await safe_reply(event, "❓ باید روی پیامی که می‌خواهی پین شود ریپلای کنی.")
            return
        notify_members = (text == "پین با اطلاع")
        try:
            await client.pin_message(chat_id, reply_id, notify=notify_members)
            if notify_members:
                await safe_reply(event, "📢 پیام توسط مدیریت پین شد و به اعضای گروه اطلاع داده شد.")
            else:
                await safe_reply(event, "📌 پیام توسط مدیریت پین شد.")
        except Exception as e:
            await safe_reply(event, f"⚠️ خطا در پین کردن: {e}")
        return

    if text in ("آنپین", "برداشتن پین"):
        if not is_admin(chat, sender_id):
            return
        reply_id = getattr(event, 'reply_to_msg_id', None)
        if not reply_id:
            reply_obj = getattr(event, 'reply_to', None)
            reply_id = getattr(reply_obj, 'reply_to_msg_id', None) if reply_obj else None
        try:
            if reply_id:
                await client.unpin_message(chat_id, reply_id)
                await safe_reply(event, "📌 پین پیام برداشته شد.")
            else:
                await client.unpin_message(chat_id, None)
                await safe_reply(event, "📌 تمام پین‌های گروه برداشته شدند.")
        except Exception as e:
            await safe_reply(event, f"⚠️ خطا در برداشتن پین: {e}")
        return


    if text in ("سخنگو روشن", "سخنگو خاموش"):
        if not is_admin(chat, sender_id):
            return
        chat["learned_words_enabled"] = (text == "سخنگو روشن")
        await save_config(config)
        if chat["learned_words_enabled"]:
            await safe_reply(event, "🗣️ سخنگو فعال شد.\n" + build_action_block(
                footer="پاسخ‌های خودکار فعال هستند."))
        else:
            await safe_reply(event, "🔇 سخنگو خاموش شد.\n" + build_action_block(
                footer="آموزش‌ها حفظ خواهند شد."))
        return

    if text.startswith("یاد بگیر "):
        if not is_admin(chat, sender_id):
            return
        rest = text[len("یاد بگیر "):]
        if "=" not in rest:
            await safe_reply(event, "❓ فرمت درست: «یاد بگیر کلمه = جواب» (مثال: یاد بگیر سلام = به به سلام خوشگل)")
            return
        keyword, _, answer = rest.partition("=")
        keyword = keyword.strip()
        answer = answer.strip()
        if not keyword or not answer:
            await safe_reply(event, "❓ فرمت درست: «یاد بگیر کلمه = جواب» (مثال: یاد بگیر سلام = به به سلام خوشگل)")
            return
        learned = chat.setdefault("learned_words", {})
        existing = learned.get(keyword)
        if isinstance(existing, str):
            existing = [existing]
        elif not isinstance(existing, list):
            existing = []
        if answer not in existing:
            existing.append(answer)
        learned[keyword] = existing
        await save_config(config)
        await safe_reply(
            event,
            "🧠 کلمه جدید یاد گرفته شد.\n" + build_action_block(
                details=[("🔤", "کلمه", keyword), ("💬", "پاسخ", answer)],
                footer=f"الان {len(existing)} جواب برای این کلمه ثبت شده؛ هر بار تصادفی یکیش انتخاب می‌شود."
            ),
        )
        return

    if text == "لیست آموزش":
        if not is_admin(chat, sender_id):
            return
        learned = chat.get("learned_words") or {}
        if not learned:
            await safe_reply(event, "📭 هیچ آموزشی ثبت نشده است.")
            return
        lines = []
        for kw, answers in learned.items():
            if isinstance(answers, str):
                answers = [answers]
            lines.append(f"🔹 {kw}:")
            for ans in answers:
                lines.append(f"   ↳ {ans}")
        await safe_reply(event, wrap_box("📋", "لیست آموزش", "\n".join(lines)))
        return

    if text.startswith("حذف آموزش "):
        if not is_admin(chat, sender_id):
            return
        keyword = text[len("حذف آموزش "):].strip()
        learned = chat.get("learned_words") or {}
        if keyword not in learned:
            await safe_reply(event, f"❓ کلمه‌ی «{keyword}» در لیست آموزش پیدا نشد.")
            return
        learned.pop(keyword, None)
        await save_config(config)
        await safe_reply(event, "🧠 آموزش حذف شد.\n" + build_action_block(
            details=[("🔤", "کلمه", keyword)],
            footer="تمام پاسخ‌های مربوط به آن حذف شدند."))
        return

    if text == "ریست لیست آموزش":
        if not is_admin(chat, sender_id):
            return
        chat["learned_words"] = {}
        await save_config(config)
        await safe_reply(event, "🧠 آموزش حذف شد.\n" + build_action_block(
            footer="کل لیست آموزش پاک شد."))
        return

    if text in ("اطلاعات کاربر", "پروفایل من", "مشخصات من"):
        if text == "اطلاعات کاربر":
            target = await resolve_target(event, chat_id, "")
            if not target:
                await safe_reply(event, "❓ باید روی پیام کاربری که می‌خوای اطلاعاتشو ببینی ریپلای کنی.")
                return
        else:
            target = sender_id

        try:
            user, full_user = await asyncio.gather(
                client.get_entity(target), client.get_full_user(target), return_exceptions=True)
            if isinstance(user, BaseException):
                raise user
            if isinstance(full_user, BaseException):
                full_user = None
            bio = (extract_bio(full_user) or "—").replace("`", "'")

            fname = getattr(user, 'first_name', '') or ''
            lname = getattr(user, 'last_name', '') or ''
            full_name = (f"{fname} {lname}".strip() or "—").replace("`", "'")
            username = getattr(user, 'username', None)
            username_line = f"@{username}" if username else "ندارد"

            badges = ""
            if getattr(user, 'bot', False):
                badges += " 🤖"
            if getattr(user, 'verified', False):
                badges += " ✅"
            if getattr(user, 'premium', False):
                badges += " ⭐️"

            is_owner_user = str(target) == str(chat.get("group_owner") or "")
            is_admin_user = target in chat.get("admins", [])
            status_fa = "مالک گپ" if is_owner_user else ("ادمین" if is_admin_user else "عضو")
            is_banned = str(target) in (chat.get("banned") or {})
            is_muted = str(target) in (chat.get("muted") or {})
            is_exempt = target in (chat.get("exempt") or [])

            b = MentionTextBuilder()
            b.text(
                f"╭─〔 👤 اطلاعات کاربر{badges} 〕─╮\n\n"
                "👤 کاربر ﹝"
            )
            await b.mention(target, user)
            b.text("﹞\n\n")
            b.text("📛 نام کامل: ")
            b.code(full_name)
            b.text("\n🔗 یوزرنیم: ")
            b.code(username_line)
            b.text(f"\n🆔 آیدی: 『{target}』")
            b.text(f"\n👑 وضعیت: 『{status_fa}』")
            b.text(f"\n🔨 بن: 『{'بله' if is_banned else 'خیر'}』")
            b.text(f"\n🔇 سکوت: 『{'بله' if is_muted else 'خیر'}』")
            b.text(f"\n🛡️ معاف: 『{'بله' if is_exempt else 'خیر'}』")
            b.text("\n📝 بیو:\n")
            b.code(bio)
            b.text("\n╰────────────────╯")
            caption, entities = b.build()
            await safe_reply(event, caption, entities=entities)
        except Exception as e:
            await safe_reply(event, f"⚠️ خطا در دریافت اطلاعات کاربر: {e}")
        return

    if text == "بن" or text.startswith("بن "):
        if not is_admin(chat, sender_id):
            return
        if not is_owner_level(chat, sender_id) and not chat.get("ban_enabled", True):
            await safe_reply(event, "⛔️ قابلیت بن برای ادمین‌های عادی غیرفعال است.")
            return
        target = await resolve_target(event, chat_id, text[len("بن"):].strip())
        if not target:
            await safe_reply(event, "❓ باید روی پیام فرد ریپلای کنی یا آیدی/یوزرنیمش را بنویسی.")
            return
        if await _funny_mod_guard(event, chat, target, sender_id, "ban"):
            return
        try:
            await client.ban_chat_member(chat_id, target)
            chat["banned"][str(target)] = datetime.now(timezone.utc).isoformat()
            await save_config(config)
            await notify_user_action(event, chat, target, "🔨", " از گروه مسدود شد.",
                                      details=[("📌", "دلیل", "نقض قوانین گروه")])
        except Exception as e:
            await _mod_error_reply(event, e, "ban")
        return

    if text == "رفع بن" or text.startswith("رفع بن "):
        if not is_admin(chat, sender_id):
            return
        target = await resolve_target(event, chat_id, text[len("رفع بن"):].strip())
        if not target:
            await safe_reply(event, "❓ باید روی پیام فرد ریپلای کنی یا آیدی/یوزرنیمش را بنویسی.")
            return
        try:
            await client.unban_chat_member(chat_id, target)
            chat["banned"].pop(str(target), None)
            await save_config(config)
            await notify_user_action(event, chat, target, "🔓", " بن کاربر لغو شد.",
                                      footer="امکان فعالیت مجدد فراهم شد.")
        except Exception as e:
            await _mod_error_reply(event, e, "unban")
        return

    if text == "سکوت" or text.startswith("سکوت "):
        if not is_admin(chat, sender_id):
            return
        rest = text[len("سکوت"):].strip()
        _ro = getattr(event, 'reply_to', None)
        has_reply = bool(getattr(event, 'reply_to_msg_id', None)
                         or (getattr(_ro, 'reply_to_msg_id', None) if _ro else None))
        tokens = rest.split()
        if tokens and (tokens[0].startswith("@") or not has_reply):
            arg, time_part = tokens[0], " ".join(tokens[1:])
        else:
            arg, time_part = "", rest
        target = await resolve_target(event, chat_id, arg, prefer_arg=True)
        if not target:
            await safe_reply(event,
                "❓ باید روی پیام فرد ریپلای کنی یا آیدی/یوزرنیمش را بنویسی.\n"
                "مثال: «سکوت @username 10 دقیقه» یا «سکوت 123456789»")
            return

        if await _funny_mod_guard(event, chat, target, sender_id, "mute"):
            return

        owner_level = is_owner_level(chat, sender_id)
        lock = chat.get("mute_action_lock")
        if lock and not owner_level:
            minutes = lock.get("minutes")
        elif time_part:
            minutes = parse_time_to_minutes(time_part)
            if minutes is None:
                await safe_reply(event, 
                    f"❓ زمان «{time_part}» قابل تشخیص نیست؛ مثال: «سکوت 5 دقیقه» یا «سکوت 1 ساعت». "
                    "برای سکوت دائم هم فقط بنویس «سکوت»."
                )
                return
        else:
            minutes = None

        try:
            if minutes:
                _raw_date = getattr(event, 'date', None)
                _msg_date = getattr(getattr(event, 'message', None), 'date', None)
                _send_ts = _event_send_ts(event)
                _now_accurate = _accurate_now(event)
                _now_system = datetime.now(timezone.utc)
                until = _now_accurate + timedelta(minutes=minutes)
                _until_ts_int = int(until.timestamp())

                def _fa(dt: datetime) -> str:
                    """نمایش خوانا به‌وقتِ ایران (UTC+۳:۳۰)."""
                    return dt.astimezone(IRAN_TZ).strftime("%Y-%m-%d %H:%M:%S") + " (وقت ایران)"

                _log(
                    "🧪 [دیباگ سکوت] ─────────────────────────\n"
                    f"  ورودی زمان (متن خام): '{time_part}'\n"
                    f"  دقیقه‌های تشخیص‌داده‌شده توسط parse_time_to_minutes: {minutes}\n"
                    f"  event.date خام: {_raw_date!r}  (نوع: {type(_raw_date).__name__})\n"
                    f"  message.date خام: {_msg_date!r}  (نوع: {type(_msg_date).__name__})\n"
                    f"  _event_send_ts(event) = {_send_ts}  →  "
                    f"{_fa(datetime.fromtimestamp(_send_ts, tz=timezone.utc))}\n"
                    f"  _accurate_now(event) [مبنای محاسبه] = {_fa(_now_accurate)}\n"
                    f"  ساعتِ سیستمِ سرور همین لحظه (برای مقایسه) = {_fa(_now_system)}\n"
                    f"  اختلاف accurate_now با ساعت سیستم = "
                    f"{(_now_system - _now_accurate).total_seconds():.1f} ثانیه\n"
                    f"  until محاسبه‌شده (accurate_now + {minutes} دقیقه) = {_fa(until)}\n"
                    f"  until_date (timestamp int) که به edit_permissions فرستاده می‌شود: {_until_ts_int}\n"
                    "🧪 ───────────────────────────────────────"
                )
                await client.edit_permissions(chat_id, target, until_date=_until_ts_int, send_messages=False)

                try:
                    _found = False
                    _filters_to_try = [("(پیش‌فرض)", None)]
                    if ChannelParticipantsBanned is not None:
                        _filters_to_try.append(("Banned('')", ChannelParticipantsBanned('')))
                    if ChannelParticipantsKicked is not None:
                        _filters_to_try.append(("Kicked('')", ChannelParticipantsKicked('')))

                    for _fname, _filt in _filters_to_try:
                        if _found:
                            break
                        try:
                            _kwargs = {"filter": _filt} if _filt is not None else {}
                            async for _p in client.iter_participants(chat_id, **_kwargs):
                                if getattr(_p, 'id', None) != target:
                                    continue
                                _found = True
                                _part = getattr(_p, 'participant', None)
                                _log(f"🧪 [دیباگ سکوت] پیدا شد با فیلتر {_fname} → participant واقعیِ سرور: {_part!r}")
                                _br = getattr(_part, 'banned_rights', None)
                                if _br is not None:
                                    _bu = getattr(_br, 'until_date', None)
                                    _log(f"🧪 [دیباگ سکوت]   banned_rights.until_date = {_bu!r}")
                                    if isinstance(_bu, (int, float)) and _bu > 0:
                                        _log(f"🧪 [دیباگ سکوت]   → یعنی: {datetime.fromtimestamp(_bu, tz=timezone.utc).astimezone(IRAN_TZ).strftime('%Y-%m-%d %H:%M:%S')} (وقت ایران)")
                                    elif isinstance(_bu, datetime):
                                        _log(f"🧪 [دیباگ سکوت]   → یعنی: {_bu.astimezone(IRAN_TZ).strftime('%Y-%m-%d %H:%M:%S')} (وقت ایران)")
                                else:
                                    _log("🧪 [دیباگ سکوت]   banned_rights خالیه (None) - یعنی سرور اصلاً محدودیتی ثبت نکرده!")
                                break
                        except Exception as _e_filt:
                            _log(f"🧪 [دیباگ سکوت] فیلتر {_fname} ارور داد: {_e_filt!r}")

                    if not _found:
                        _log("🧪 [دیباگ سکوت] کاربر با هیچ فیلتری توی iter_participants پیدا نشد.")
                except Exception as _e_perm:
                    _log(f"🧪 [دیباگ سکوت] iter_participants ارور داد: {_e_perm!r}")

                chat["muted"][str(target)] = until.isoformat()
                suffix = " به حالت سکوت درآمد."
                mute_details = [("⏱", "مدت", format_minutes_fa(minutes))]
                mute_footer = None
            else:

                await client.edit_permissions(chat_id, target, until_date=0, send_messages=False)
                chat["muted"][str(target)] = None
                suffix = " به‌صورت دائم ساکت شد."
                mute_details = None
                mute_footer = None
            await save_config(config)
            await notify_user_action(event, chat, target, "🔇", suffix, details=mute_details, footer=mute_footer)
        except Exception as e:
            await _mod_error_reply(event, e, "mute")
        return

    if text == "رفع سکوت" or text.startswith("رفع سکوت "):
        if not is_admin(chat, sender_id):
            return
        target = await resolve_target(event, chat_id, text[len("رفع سکوت"):].strip())
        if not target:
            await safe_reply(event, "❓ باید روی پیام فرد ریپلای کنی یا آیدی/یوزرنیمش را بنویسی.")
            return
        try:
            await client.edit_permissions(chat_id, target, send_messages=True)
            chat["muted"].pop(str(target), None)
            clear_spam_state(chat_id, target)
            await save_config(config)
            await notify_user_action(event, chat, target, "🔊", " سکوت کاربر برداشته شد.",
                                      footer="ارسال پیام مجدداً آزاد است.")
        except Exception as e:
            await _mod_error_reply(event, e, "unmute")
        return


_FUNNY_BOT_NOT_ADMIN = {
    "ban": [
        "😭 داداش من ادمین نیستم! منو آوردن گروه فقط برای دکور 🪴\nاول بهم ادمینی بده، بعد بگو کی رو بفرستم بره بیرون.",
        "🥺 دلم می‌خواد بنِش کنم ولی من اینجا ادمین نیستم، فقط یه ربات بدبختم که با ذوق اومدم!\nبرو از تنظیمات گروه بهم ادمینی بده، قول می‌دم حرفه‌ای عمل کنم 🫡",
        "🚫 بن؟ من؟ با این حقوق صفرِ ادمینی؟ 😂\nمن اینجا در حد نگهبان بدون باتومم! اول ادمینم کن بعد قدرت‌نمایی کنم 💪",
        "👮‍♂️ جناب، من گواهینامه‌ی بن‌کردن ندارم! یعنی ادمین نیستم.\nیکی منو ارتقا بده تا بساطشو جمع کنم 😎",
    ],
    "mute": [
        "🤐 می‌خوام ساکتش کنم ولی خودم ادمین نیستم، یعنی حتی صدای خودمم نمی‌تونم کم کنم! 😭\nادمینم کن تا سکوتشو بترکونم.",
        "🙈 من ادمین نیستم رفیق! اگه ادمینم کنی، قول می‌دم همه‌ی گروه رو بذارم تو حالت «هیس!» 🤫",
        "🔇 دکمه‌ی سکوت دست منه ولی برقش قطعه، چون ادمین نیستم 😅\nبرو بهم ادمینی بده تا وصل شه!",
        "😬 نمی‌تونم! ادمین نیستم و اگه سکوت بزنم احتمالاً فقط خودم از خجالت ساکت می‌شم.\nاول ادمینم کن 🙏",
    ],
    "unban": [
        "😅 من ادمین نیستم که بتونم کسی رو آزاد کنم! خودم هنوز دنبال آزادیمم 🏃‍♂️\nاول ادمینم کن بعد عفو عمومی بدیم 🕊",
    ],
    "unmute": [
        "🎤 میکروفون دست منه ولی ادمین نیستم که بتونم بدمش دست طرف! 😂\nاول ادمینم کن.",
    ],
}

_FUNNY_TARGET_BOT = {
    "ban": [
        "😂 می‌خوای منو بن کنی؟! من که ادمین نیستم بخوام خودمو بیرون کنم، ولی اگه واقعاً از من خسته شدی برو دکمه‌ی حذف ربات رو بزن 🥲",
        "🤖 بن‌کردنِ ربات؟ باشه ولی بعدش خودت باید جوک بگی گروه رو بخندونی 😏",
        "🫵 ببین چه کسی اومده ربات رو بن کنه! یعنی اون‌قدر از دست من عصبانی شدی؟ من که فقط وظیفمو انجام می‌دم 😭",
    ],
    "mute": [
        "🤐 منو ساکت کنی؟ ربات و ساکت؟ بزرگ‌ترین آرزوی دشمنانم! ولی نه، نمی‌شه 😎",
        "🙊 من ساکت بشم گروه از غصه می‌میره! بیخیال شو رفیق 😂",
        "🔇 تلاش خوبی بود ولی من دکمه‌ی میوت ندارم، فقط دکمه‌ی «بیشتر حرف بزن» دارم 🗣",
    ],
}

_FUNNY_TARGET_ADMIN = {
    "ban": [
        "😳 روی ادمین بن می‌زنی؟! جرئت می‌خواد ولی من هنوز می‌خوام کارمو حفظ کنم 😂",
        "👑 این یکی ادمینه! من جرأت ندارم چشم ازش بردارم، چه برسه بنش کنم 🥶",
        "🚨 هشدار: تلاش برای کودتا! بن‌کردن ادمین ممنوعه، لطفاً اول با رئیس جلسه هماهنگ کنید 😏",
        "🙅‍♂️ ادمین‌ها خط قرمزن! دستم رو نمی‌بری به این کار، کلی جریمه داره 🤭",
    ],
    "mute": [
        "🤫 ادمین رو ساکت کنم؟ همین الان از فشارِ استرس نصفِ باتری‌م خالی شد 🔋😂",
        "👑 اینو که ادمینه! سکوتش کنم فردا یه ربات جدید جاش میاد 😅",
        "🚨 سوءقصد به ادمین! نیروی انتظامی ربات‌ها در محل حاضره، لطفاً کوتاه بیا 👮‍♂️",
        "🙊 ادمین و ساکت؟ مثل آب و آتیشه! این‌کارو نکن رفیق 😂",
    ],
}

_FUNNY_TARGET_SELF = {
    "ban": [
        "🤨 خودتو می‌خوای بن کنی؟! اگه از گروه خسته شدی در رو بلدی، لازم نیست منو درگیر کنی 😂",
        "😭 این‌قدر ازمون ناراحتی که خودتو بن می‌کنی؟ بیا بغلم... ببخشید من ربات‌ام، بغل ندارم 🤖",
    ],
    "mute": [
        "🤐 می‌خوای خودتو ساکت کنی؟ ایول! فقط مراقب باش بعدش نگی «چرا کسی جوابمو نمی‌ده» 😅",
        "🙃 خودت رو سکوت می‌دی؟ این اولین بار تو تاریخه که کسی به خودش لطف می‌کنه 😂",
    ],
}


def _is_admin_rights_error(e) -> bool:
    """تشخیص خطاهایی که یعنی «ربات ادمین نیست / دسترسی لازم رو نداره»."""
    try:
        t = f"{type(e).__name__} {e!r} {e}".lower()
    except Exception:
        return False
    keys = (
        "admin_required", "chat_admin_required", "not enough rights", "right_forbidden",
        "admin required", "permission", "forbidden", "not_admin", "chat_write_forbidden",
        "need to be admin", "must be admin", "no rights", "access_denied", "access denied",
    )
    return any(k in t for k in keys)


async def _funny_mod_guard(event, chat, target, sender_id, action: str) -> bool:
    """قبل از بن/سکوت چک می‌کند هدف خودِ ربات، خودِ فرستنده یا ادمین نباشد؛
    اگر بود با یه پیام طنز جواب می‌دهد و True برمی‌گرداند (یعنی دستور اجرا نشود)."""
    try:
        my_id = await _ship_get_my_id()
    except Exception:
        my_id = None
    if my_id is not None and target == my_id:
        await safe_reply(event, random.choice(_FUNNY_TARGET_BOT[action]))
        return True
    if target == sender_id:
        await safe_reply(event, random.choice(_FUNNY_TARGET_SELF[action]))
        return True
    if is_admin(chat, target):
        await safe_reply(event, random.choice(_FUNNY_TARGET_ADMIN[action]))
        return True
    return False


async def _mod_error_reply(event, e, action: str) -> None:
    """اگر خطا از نبودنِ دسترسیِ ربات بود جواب طنز، وگرنه خطای معمولی."""
    if _is_admin_rights_error(e):
        await safe_reply(event, random.choice(_FUNNY_BOT_NOT_ADMIN[action]))
    else:
        await safe_reply(event, f"⚠️ خطا: {e}")



async def tag_user_list(event, title: str, uids: list, empty_text: str, users: dict = None) -> None:
    """تگ کردن یک لیست از آیدی‌ها (ادمین/معاف/سکوت)، تکه‌تکه و بدون تکراری."""
    ordered = []
    seen_ids = set()
    for uid in uids:
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            continue
        if uid not in seen_ids:
            seen_ids.add(uid)
            ordered.append(uid)

    if not ordered:
        await safe_reply(event, empty_text)
        return

    TAG_CHUNK_SIZE = 150
    chunks = [ordered[i:i + TAG_CHUNK_SIZE] for i in range(0, len(ordered), TAG_CHUNK_SIZE)]
    for idx, chunk in enumerate(chunks, start=1):
        mb = MentionTextBuilder()
        part = f" ({idx}/{len(chunks)})" if len(chunks) > 1 else ""
        mb.text(f"{title}{part} - {len(ordered)} نفر:\n\n")
        for i, uid in enumerate(chunk):
            user_obj = (users or {}).get(uid)
            if user_obj is None:
                try:
                    user_obj = await client.get_entity(uid)
                except Exception:
                    user_obj = None
            await mb.mention(uid, user_obj)
            if i != len(chunk) - 1:
                mb.text("، ")
        msg_text, tag_entities = mb.build()
        await safe_reply(event, msg_text, entities=tag_entities)
        if idx != len(chunks):
            await asyncio.sleep(1.0)


SHIP_DEFAULT_INTERVAL_SECONDS = 20 * 60
SHIP_ACTIVE_WINDOW_SECONDS = 60 * 60
SHIP_LOOP_TICK_SECONDS = 15
SHIP_MSG_OWNER_CACHE = 600
SHIP_HISTORY_LIMIT = 100
SHIP_HISTORY_WINDOW_SECONDS = SHIP_ACTIVE_WINDOW_SECONDS
SHIP_SEED_COOLDOWN_SECONDS = 5 * 60

ship_recent: dict = {}
ship_msg_owner: dict = {}
ship_reply_pairs: dict = {}
ship_last_sent: dict = {}
ship_last_pair: dict = {}
ship_last_seed: dict = {}
_ship_bags: dict = {}
_ship_last_idx: dict = {}
ship_task = None
_ship_my_id_cache = None


SHIP_CRUSH_LINES = [
    "{A} یه کراش جدی رو {B} داره ولی روش نمی‌شه بگه 🙈",
    "{A} شبا آهنگ غمگین گوش می‌ده و به {B} فکر می‌کنه 🎧😭",
    "{A} هر روز پروفایل {B} رو چک می‌کنه؛ جاسوس عشق 👀",
    "{A} تا اسم {B} میاد، گوش‌هاش قرمز می‌شه 🍅😳",
    "{A} پیام‌های {B} رو سه بار می‌خونه ببینه منظور داشته یا نه 📱🔍",
    "{A} برای {B} فن‌کلاب زده و تنها عضوش هم خودشه 💻💗",
    "{A} فکر می‌کنه کسی نمی‌فهمه کراشش {B} هست؛ همه فهمیدن 🤭",
    "{A} هر وقت {B} آنلاین می‌شه، ناخودآگاه صاف می‌شینه 🪑😳",
    "{A} شرط بسته استوری {B} رو تو پنج دقیقه‌ی اول لایک کنه 😂❤️",
    "{A} دیشب خواب دید {B} بهش بستنی داده 🍦😴",
    "{A} به‌خاطر {B} تا صبح آنلاین می‌مونه که شاید پیام بیاد 🌙📲",
    "{A} اسم {B} رو تو دفترچه‌ش با قلب قرمز نوشته ❤️📓",
]

SHIP_WANT_LINES = [
    "{A} می‌خواد {B} رو ببره بستنی ولی جرئت نداره 🍦😳",
    "{A} داره گل و شیرینی می‌خره بره خواستگاری {B} 💐🍰",
    "{A} از دنیا فقط یه چیز می‌خواد: یه چایی دونفره با {B} ☕💗",
    "{A} می‌خواد {B} رو ببره ماه‌عسل، ولی بودجه‌ش فعلاً پیتزای دونفره‌ست 🍕🌙",
    "{A} می‌خواد {B} رو هم‌تیمی همیشگیش کنه، اونم تو بازیِ زندگی 🎮💞",
    "{A} یه نقشه‌ی پنج‌ساله ریخته: اول دوستی با {B}، بعدش عروسی 🗺️💍",
    "{A} برای {B} هدیه گرفته ولی خجالت می‌کشه بده 🎁🙈",
    "{A} می‌خواد با {B} بره پارک قدم بزنه؛ بهونه‌ش هم هواخوریه 🌳😏",
]

SHIP_MUTUAL_LINES = [
    "{A} و {B} قایمکی همدیگه رو کراش می‌زنن و هیچ‌کدوم جرئت نداره اول بگه 😭💞",
    "{A} و {B} هر دو شب بیدار موندن ببینن اون یکی آنلاینه 🌙👀",
    "بین {A} و {B} یه چیزی هست که پلیس عشق هم نمی‌تونه انکارش کنه 🚔💕",
    "{A} و {B} کاپل‌ترین دو نفر گپن؛ فقط هنوز رسمی نشده 📄💍",
    "{A} و {B} الکی ادا درمیارن؛ نگاه‌هاشون همه‌چی رو لو داد 👀🔥",
    "قلب {A} و {B} همزمان پینگ می‌ده؛ اینترنت عشق وصله 🌐💓",
    "{A} و {B} تو گپ جوک می‌گن ولی زیرش کلی احساس قایم شده 🎭💘",
]

SHIP_CHAOS_LINES = [
    "{A} و {B} همون دوتاییان که تو فیلم‌ها اول دعوا می‌کنن، آخرش ازدواج 🎬💍",
    "اگه {A} و {B} کاپل بشن، اسمشون می‌شه «دردسر دو نفره» 😂🔥",
    "اولین دعوای {A} و {B} بعد از ازدواج سر ریموت تلویزیونه 📺😂",
    "{A} و {B} همون کاپلی‌ان که تو استوری فقط پیتزا و میم می‌ذارن 🍕😂",
    "ربات رسماً اعلام می‌کنه: {A} و {B} بهترین تیم دو نفره‌ی گپن 🏆😎",
    "اگه {A} و {B} برن بیرون، گارسون دلش می‌خواد شاهد عقدشون باشه 🍽️🎉",
    "{A} و {B} شیپ شدن؛ ربات مسئولیت قلب‌های شکسته رو قبول نمی‌کنه 🫡💔",
    "قدرت {A} و {B} با هم به‌اندازه‌ی یه باتری نصفه‌ی گوشیه 🔋💘",
    "ربات شهادت می‌ده {A} و {B} شیپن؛ فقط دعوت عروسی یادتون نره 🎉🍰",
]

SHIP_LINE_KINDS = [
    (SHIP_CRUSH_LINES, "crush", 40),
    (SHIP_WANT_LINES, "want", 22),
    (SHIP_MUTUAL_LINES, "mutual", 18),
    (SHIP_CHAOS_LINES, "chaos", 20),
]


def _ship_pick(chat_id, name: str, pool: list) -> str:
    """انتخاب تصادفیِ بدون تکرار (همه‌ی گزینه‌ها یک دور مصرف می‌شن، بعد دوباره)."""
    key = (chat_id, name)
    bag = _ship_bags.get(key)
    if not bag:
        bag = list(range(len(pool)))
        random.shuffle(bag)
        if len(bag) > 1 and bag[-1] == _ship_last_idx.get(key):
            bag[0], bag[-1] = bag[-1], bag[0]
        _ship_bags[key] = bag
    idx = bag.pop()
    _ship_last_idx[key] = idx
    return pool[idx % len(pool)]


def _ship_pick_line(chat_id) -> str:
    _pool, kind, _w = random.choices(
        SHIP_LINE_KINDS, weights=[w for _p, _k, w in SHIP_LINE_KINDS]
    )[0]
    return _ship_pick(chat_id, f"line_{kind}", _pool)


async def _ship_get_my_id():
    global _ship_my_id_cache
    if _ship_my_id_cache is None:
        try:
            me = await client.get_me()
            _ship_my_id_cache = getattr(me, 'id', None)
        except Exception:
            return None
    return _ship_my_id_cache


def _ship_label(user, uid) -> str:
    """متنِ تگ = اسم خودِ کاربر (نه «مشاهده نمایه»)."""
    name = re.sub(r"\s+", " ", display_name_for(user, uid) or "").strip()[:32] or f"کاربر {uid}"
    if name.endswith(")") and " (" in name:
        name += "\u200c"
    return name


@client.on_message()
async def ship_activity_tracker(_client, event):
    """فقط ثبت می‌کنه کی توی گپ فعاله و کی به کی ریپلای زده (بدون هیچ درخواست شبکه)."""
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return
    my_id = await _ship_get_my_id()
    if sender_id == my_id:
        return

    ts = _event_send_ts(event)
    recent = ship_recent.setdefault(chat_id, {})
    recent[sender_id] = ts
    if len(recent) > 400:
        cutoff = ts - SHIP_ACTIVE_WINDOW_SECONDS
        for uid in [u for u, t in recent.items() if t < cutoff]:
            recent.pop(uid, None)

    owners = ship_msg_owner.setdefault(chat_id, OrderedDict())
    reply_id = getattr(event, 'reply_to_msg_id', None)
    if not reply_id:
        reply_obj = getattr(event, 'reply_to', None)
        reply_id = getattr(reply_obj, 'reply_to_msg_id', None) if reply_obj else None
    if reply_id:
        target = owners.get(reply_id)
        if target and target != sender_id and target != my_id:
            ship_reply_pairs.setdefault(chat_id, deque(maxlen=200)).append((ts, sender_id, target))

    msg_id = getattr(event, 'id', None)
    if msg_id:
        owners[msg_id] = sender_id
        while len(owners) > SHIP_MSG_OWNER_CACHE:
            owners.popitem(last=False)


async def _ship_load_user(uid):
    try:
        user = await client.get_entity(uid)
    except Exception:
        return None
    if user is None or getattr(user, 'bot', False) or getattr(user, 'deleted', False):
        return None
    return user


async def _ship_pick_pair(chat_id, window: int = None):
    """دو نفر از بین فعال‌های یک ساعت اخیر (به‌جز خودِ ربات و ربات‌ها).
    اگه دو نفر اخیراً به هم ریپلای زده باشن، با احتمال بالا همونا انتخاب می‌شن.
    برمی‌گردونه (a_id, a_user, b_id, b_user) یا None اگه کسی برای شیپ نبود."""
    my_id = await _ship_get_my_id()
    cutoff = datetime.now(timezone.utc).timestamp() - (window or SHIP_ACTIVE_WINDOW_SECONDS)
    active = [
        u for u, t in (ship_recent.get(chat_id) or {}).items()
        if t >= cutoff and u != my_id
    ]
    last_pair = ship_last_pair.get(chat_id)
    bad: set = set()
    users: dict = {}

    for attempt in range(8):
        pool = [u for u in active if u not in bad]
        if len(pool) < 2:
            return None
        pool_set = set(pool)

        reply_pairs, seen = [], set()
        for ts, a, b in (ship_reply_pairs.get(chat_id) or ()):
            key = frozenset((a, b))
            if ts >= cutoff and a in pool_set and b in pool_set and key not in seen:
                seen.add(key)
                reply_pairs.append((a, b))

        if reply_pairs and random.random() < 0.65:
            a, b = random.choice(reply_pairs)
        else:
            a, b = random.sample(pool, 2)
        if random.random() < 0.5:
            a, b = b, a

        if attempt < 5 and len(pool) > 2 and last_pair == frozenset((a, b)):
            continue

        for uid in (a, b):
            if uid not in users:
                users[uid] = await _ship_load_user(uid)
        if users[a] is None or users[b] is None:
            if users[a] is None:
                bad.add(a)
            if users[b] is None:
                bad.add(b)
            continue
        return a, users[a], b, users[b]
    return None


async def _ship_build_message(chat_id, a_id, a_user, b_id, b_user):
    """پیام شیپ = فقط یک خط طنز، با تگِ واقعیِ اسم دو نفر."""
    line = _ship_pick_line(chat_id)
    people = {"{A}": (a_id, a_user), "{B}": (b_id, b_user)}
    mb = MentionTextBuilder()
    for part in re.split(r"(\{A\}|\{B\})", line):
        if part in people:
            uid, user = people[part]
            await mb.mention(uid, user, label=_ship_label(user, uid))
        elif part:
            mb.text(part)
    return mb.build()


async def _ship_seed_from_history(chat_id) -> None:
    """وقتی حافظه‌ی فعال‌ها خالیه (مثلاً بعد از ری‌استارت) از روی چند پیام آخرِ خودِ گپ
    می‌فهمیم کی داره چت می‌کنه و کی به کی ریپلای زده."""
    my_id = await _ship_get_my_id()
    now_ts = datetime.now(timezone.utc).timestamp()
    ship_last_seed[chat_id] = now_ts
    msgs = []
    try:
        async for m in client.iter_messages(chat_id, limit=SHIP_HISTORY_LIMIT):
            msgs.append(m)
    except Exception as e:
        _log(f"⚠️ ship history read error [{chat_id}]: {e}")
        return

    owners = {}
    for m in msgs:
        mid, sid = getattr(m, 'id', None), getattr(m, 'sender_id', None)
        if mid and sid:
            owners[mid] = sid

    recent = ship_recent.setdefault(chat_id, {})
    pairs = ship_reply_pairs.setdefault(chat_id, deque(maxlen=200))
    cutoff = now_ts - SHIP_HISTORY_WINDOW_SECONDS
    for m in msgs:
        sid, d = getattr(m, 'sender_id', None), getattr(m, 'date', None)
        if not sid or sid == my_id or d is None:
            continue
        try:
            ts = d.timestamp()
        except Exception:
            continue
        if ts < cutoff:
            continue
        if ts > recent.get(sid, 0):
            recent[sid] = ts
        reply_id = getattr(m, 'reply_to_msg_id', None)
        if not reply_id:
            ro = getattr(m, 'reply_to', None)
            reply_id = getattr(ro, 'reply_to_msg_id', None) if ro else None
        target = owners.get(reply_id) if reply_id else None
        if target and target != sid and target != my_id:
            pairs.append((ts, sid, target))


async def _ship_send_round(chat_id, manual: bool = False, reply_to=None) -> bool:
    """یک دور شیپ. False یعنی هنوز دو نفر فعال پیدا نشده (بعداً دوباره تلاش می‌شه)."""
    if not is_chat_active(chat_id):
        return False
    pair = await _ship_pick_pair(chat_id)
    if pair is None:
        now_ts = datetime.now(timezone.utc).timestamp()
        if manual or now_ts - ship_last_seed.get(chat_id, 0) >= SHIP_SEED_COOLDOWN_SECONDS:
            await _ship_seed_from_history(chat_id)
            pair = await _ship_pick_pair(chat_id)
    if pair is None:
        return False
    a_id, a_user, b_id, b_user = pair
    ship_last_pair[chat_id] = frozenset((a_id, b_id))
    try:
        text, entities = await _ship_build_message(chat_id, a_id, a_user, b_id, b_user)
        await client.send_message(
            chat_id, text,
            formatting_entities=entities, parse_mode=None, reply_to=reply_to,
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ ship send error [{chat_id}]: {e}")
    return True


WATCH_INTERVAL_SECONDS = 50 * 60
WATCH_AFTER_SHIP_GAP_SECONDS = 90

watch_last_sent: dict = {}
watch_last_user: dict = {}

WATCH_LINES = [
    "{A} من تورو زیر نظر دارم 👁",
    "{A} می‌دونستی روت کراشم؟ 👀",
    "{A} دیدمت... همه‌چی رو دیدم 🕵️",
    "{A} یه چیزی رو ازت پنهون می‌کنم 🤫",
    "{A} امروز یه نگاه مشکوک بهت داشتم 🧐",
    "{A} فکر نکن یادم رفته 😏",
    "{A} حواسم بهت هست، جدی می‌گم 👀",
    "{A} یه رازی درباره‌ت می‌دونم 🤭",
    "{A} هنوز داری نگاهم می‌کنی؟ 👁",
    "{A} یه چیزی می‌خوام بهت بگم... بعداً 🙊",
    "{A} می‌دونستی ازت خوشم میاد؟ 😳",
    "{A} ببین دوربین‌ها رو تو زوم کردن 📹",
    "{A} امشب یه اتفاقی می‌افته... نگران نباش 😈",
    "{A} دلم برات تنگ شده بود 🥺",
    "{A} گزارش امروزت ثبت شد 📝",
    "{A} چشمِ من همیشه روته 👀",
    "{A} من فقط یه ربات ساده‌ام ولی تو رو می‌بینم 🤖👁",
    "{A} تو رو دیدم ولی به کسی نگفتم 🤐",
    "{A} بهت شک دارم 🧐",
    "{A} امروز خیلی بامزه بودی 😌",
    "{A} یه نفر ازت خوشش میاد، حدس بزن کیه 💌",
    "{A} می‌دونستی همه‌ی حرکاتت زیر نظره؟ 👀😂",
    "{A} پشت سرت رو نگاه کن 👀",
    "{A} پرونده‌ت روی میزمه 📂🕵️",
    "{A} حس می‌کنم یه چیزی از من قایم می‌کنی 🤨",
    "{A} بی‌خیال، من که می‌دونم 😏",
    "{A} چرا انقدر ساکتی؟ نگرانتم 🥲",
    "{A} چشمک زدم، دیدی؟ 😉",
]


async def _watch_pick_user(chat_id):
    """یک نفر از بین فعال‌های یک ساعت اخیر (به‌جز خودِ ربات و ربات‌ها).
    برمی‌گردونه (user_id, user) یا None اگه کسی نبود."""
    my_id = await _ship_get_my_id()

    def _active_pool():
        cutoff = datetime.now(timezone.utc).timestamp() - SHIP_ACTIVE_WINDOW_SECONDS
        return [
            u for u, t in (ship_recent.get(chat_id) or {}).items()
            if t >= cutoff and u != my_id
        ]

    active = _active_pool()
    if not active:
        now_ts = datetime.now(timezone.utc).timestamp()
        if now_ts - ship_last_seed.get(chat_id, 0) >= SHIP_SEED_COOLDOWN_SECONDS:
            await _ship_seed_from_history(chat_id)
            active = _active_pool()

    last_uid = watch_last_user.get(chat_id)
    bad: set = set()
    for _ in range(6):
        pool = [u for u in active if u not in bad]
        if not pool:
            return None
        candidates = [u for u in pool if u != last_uid] or pool
        uid = random.choice(candidates)
        user = await _ship_load_user(uid)
        if user is None:
            bad.add(uid)
            continue
        return uid, user
    return None


async def _watch_send_round(chat_id) -> bool:
    """یک دور «زیر نظر». False یعنی کسی برای تگ کردن پیدا نشد (بی‌صدا رد می‌شه)."""
    if not is_chat_active(chat_id):
        return False
    picked = await _watch_pick_user(chat_id)
    if picked is None:
        return False
    uid, user = picked
    watch_last_user[chat_id] = uid
    try:
        line = _ship_pick(chat_id, "watch_line", WATCH_LINES)
        mb = MentionTextBuilder()
        for part in re.split(r"(\{A\})", line):
            if part == "{A}":
                await mb.mention(uid, user, label=_ship_label(user, uid))
            elif part:
                mb.text(part)
        text, entities = mb.build()
        await client.send_message(
            chat_id, text,
            formatting_entities=entities, parse_mode=None,
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ watch send error [{chat_id}]: {e}")
    return True


async def ship_loop():
    while True:
        await asyncio.sleep(SHIP_LOOP_TICK_SECONDS)
        try:
            now_ts = datetime.now(timezone.utc).timestamp()
            for chat_id_str, chat in list(config.get("chats", {}).items()):
                try:
                    chat_id_int = int(chat_id_str)
                except ValueError:
                    continue
                if not chat.get("active"):
                    continue
                if (chat.get("locks") or {}).get("group"):
                    continue

                last = ship_last_sent.setdefault(chat_id_int, now_ts)
                if now_ts - last >= SHIP_DEFAULT_INTERVAL_SECONDS:
                    await _ship_send_round(chat_id_int)
                    ship_last_sent[chat_id_int] = now_ts

                w_last = watch_last_sent.setdefault(chat_id_int, now_ts)
                if (now_ts - w_last >= WATCH_INTERVAL_SECONDS
                        and now_ts - ship_last_sent.get(chat_id_int, 0) >= WATCH_AFTER_SHIP_GAP_SECONDS):
                    await _watch_send_round(chat_id_int)
                    watch_last_sent[chat_id_int] = now_ts
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _log(f"⚠️ ship_loop error: {e}")


def ensure_ship_task_running():
    global ship_task
    if ship_task is None or ship_task.done():
        ship_task = asyncio.create_task(ship_loop())


@client.on_message()
async def ship_commands_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return
    if text != "شیپ":
        return

    get_chat_cfg(chat_id)
    now_ts = datetime.now(timezone.utc).timestamp()
    if await _ship_send_round(chat_id, manual=True, reply_to=getattr(event, 'id', None)):
        ship_last_sent[chat_id] = now_ts


CHALLENGES_FILE = os.path.join(BASE_DIR, "challenges.json")
_challenges_cache: dict = {"mtime": None, "items": []}


def _load_challenges() -> list:
    """فایل فقط وقتی عوض شده باشه دوباره خونده می‌شه؛ پس JSON رو می‌شه
    بدون ری‌استارت ربات ویرایش کرد. ساختار: {"challenges": ["...", ...]}
    (یا مستقیم یک لیست از رشته‌ها)."""
    try:
        mtime = os.path.getmtime(CHALLENGES_FILE)
    except OSError:
        return []
    if _challenges_cache["mtime"] == mtime:
        return _challenges_cache["items"]
    try:
        with open(CHALLENGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _log(f"⚠️ challenges load error: {e}")
        return []
    if isinstance(data, dict):
        data = data.get("challenges", [])
    if not isinstance(data, list):
        return []
    items = [s.strip() for s in data if isinstance(s, str) and s.strip()]
    _challenges_cache["mtime"] = mtime
    _challenges_cache["items"] = items
    return items


@client.on_message()
async def challenge_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return
    if text != "چالش":
        return

    items = _load_challenges()
    if not items:
        await safe_reply(event, "⚠️ فایل چالش‌ها (challenges.json) کنار ربات پیدا نشد یا خالی است.")
        return

    challenge = random.choice(items)
    await safe_reply(event, wrap_box(
        "🎲", "چالش",
        f"🎯 {challenge}\n\n💬 چالش بعدی؟ بنویس «چالش»"))


JOKES_FILE = os.path.join(BASE_DIR, "jokes.json")
_jokes_cache: dict = {"mtime": None, "items": []}


def _load_jokes() -> list:
    """مثل _load_challenges: فقط وقتی فایل عوض شده باشه دوباره خونده می‌شه.
    ساختار: {"jokes": ["...", ...]} (یا مستقیم یک لیست از رشته‌ها)."""
    try:
        mtime = os.path.getmtime(JOKES_FILE)
    except OSError:
        return []
    if _jokes_cache["mtime"] == mtime:
        return _jokes_cache["items"]
    try:
        with open(JOKES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _log(f"⚠️ jokes load error: {e}")
        return []
    if isinstance(data, dict):
        data = data.get("jokes", [])
    if not isinstance(data, list):
        return []
    items = [s.strip() for s in data if isinstance(s, str) and s.strip()]
    _jokes_cache["mtime"] = mtime
    _jokes_cache["items"] = items
    return items


@client.on_message()
async def joke_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return
    if text != "جوک":
        return

    items = _load_jokes()
    if not items:
        await safe_reply(event, "⚠️ فایل جوک‌ها (jokes.json) کنار ربات پیدا نشد یا خالی است.")
        return

    joke = random.choice(items)
    await safe_reply(event, wrap_box(
        "😂", "جوک",
        f"{joke}\n\n💬 جوک بعدی؟ بنویس «جوک»"))


FACTS_FILE = os.path.join(BASE_DIR, "facts.json")
_facts_cache: dict = {"mtime": None, "items": []}
_facts_last_idx: dict = {}


def _load_facts() -> list:
    """فقط وقتی فایل عوض شده باشه دوباره خونده می‌شه (بدون ری‌استارت قابل ویرایشه).
    ساختار: لیستی از {"category": "...", "fact": "..."}؛ یا {"facts": [...]}؛
    یا مستقیم لیستی از رشته‌ها. خروجی: لیست (دسته، متن)."""
    try:
        mtime = os.path.getmtime(FACTS_FILE)
    except OSError:
        return []
    if _facts_cache["mtime"] == mtime:
        return _facts_cache["items"]
    try:
        with open(FACTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _log(f"⚠️ facts load error: {e}")
        return []
    if isinstance(data, dict):
        data = data.get("facts", [])
    if not isinstance(data, list):
        return []
    items = []
    for it in data:
        if isinstance(it, str):
            cat, fact = "", it.strip()
        elif isinstance(it, dict):
            cat = str(it.get("category") or "").strip()
            fact = str(it.get("fact") or "").strip()
        else:
            continue
        if fact:
            items.append((cat, fact))
    _facts_cache["mtime"] = mtime
    _facts_cache["items"] = items
    return items


@client.on_message()
async def fact_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return
    if text != "دانستنی":
        return

    items = _load_facts()
    if not items:
        await safe_reply(event, "⚠️ فایل دانستنی‌ها (facts.json) کنار ربات پیدا نشد یا خالی است.")
        return

    idx = random.randrange(len(items))
    if len(items) > 1 and idx == _facts_last_idx.get(chat_id):
        idx = (idx + random.randrange(1, len(items))) % len(items)
    _facts_last_idx[chat_id] = idx

    cat, fact = items[idx]
    head = f"🏷 {cat}\n" if cat else ""
    await safe_reply(event, wrap_box(
        "🧠", "دانستنی",
        f"{head}💡 {fact}\n\n💬 دانستنی بعدی؟ بنویس «دانستنی»"))


HAFEZ_FILE = os.path.join(BASE_DIR, "hafez_fortunes.json")
_hafez_cache: dict = {"mtime": None, "items": []}
_hafez_last_idx: dict = {}


def _load_hafez() -> list:
    """فقط وقتی فایل عوض شده باشه دوباره خونده می‌شه (بدون ری‌استارت قابل ویرایشه).
    ساختار: لیستی از {"poem": "...", "interpretation": "...", "advice": "..."}
    (یا {"fortunes": [...]}). خروجی: لیست (شعر، تعبیر، نصیحت)."""
    try:
        mtime = os.path.getmtime(HAFEZ_FILE)
    except OSError:
        return []
    if _hafez_cache["mtime"] == mtime:
        return _hafez_cache["items"]
    try:
        with open(HAFEZ_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _log(f"⚠️ hafez load error: {e}")
        return []
    if isinstance(data, dict):
        data = data.get("fortunes", [])
    if not isinstance(data, list):
        return []
    items = []
    for it in data:
        if not isinstance(it, dict):
            continue
        poem = str(it.get("poem") or "").strip()
        interp = str(it.get("interpretation") or "").strip()
        advice = str(it.get("advice") or "").strip()
        if poem:
            items.append((poem, interp, advice))
    _hafez_cache["mtime"] = mtime
    _hafez_cache["items"] = items
    return items


@client.on_message()
async def hafez_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return
    if text != "فال":
        return

    items = _load_hafez()
    if not items:
        await safe_reply(event, "⚠️ فایل فال‌ها (hafez_fortunes.json) کنار ربات پیدا نشد یا خالی است.")
        return

    idx = random.randrange(len(items))
    if len(items) > 1 and idx == _hafez_last_idx.get(chat_id):
        idx = (idx + random.randrange(1, len(items))) % len(items)
    _hafez_last_idx[chat_id] = idx

    poem, interp, advice = items[idx]
    body = f"📜 {poem}"
    if interp:
        body += f"\n\n💭 تعبیر: {interp}"
    if advice:
        body += f"\n\n💡 نصیحت: {advice}"
    body += "\n\n💬 فال بعدی؟ بنویس «فال»"
    await safe_reply(event, wrap_box("🔮", "فال حافظ", body))


FACTS200_FILE = os.path.join(BASE_DIR, "facts_200.json")
_facts200_cache: dict = {"mtime": None, "items": []}
_facts200_last_idx: dict = {}


def _load_facts200() -> list:
    """فقط وقتی فایل عوض شده باشه دوباره خونده می‌شه (بدون ری‌استارت قابل ویرایشه).
    ساختار: لیستی از {"category": "...", "fact": "..."}؛ یا {"facts": [...]}؛
    یا مستقیم لیستی از رشته‌ها. خروجی: لیست (دسته، متن)."""
    try:
        mtime = os.path.getmtime(FACTS200_FILE)
    except OSError:
        return []
    if _facts200_cache["mtime"] == mtime:
        return _facts200_cache["items"]
    try:
        with open(FACTS200_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _log(f"⚠️ facts_200 load error: {e}")
        return []
    if isinstance(data, dict):
        data = data.get("facts", [])
    if not isinstance(data, list):
        return []
    items = []
    for it in data:
        if isinstance(it, str):
            cat, fact = "", it.strip()
        elif isinstance(it, dict):
            cat = str(it.get("category") or "").strip()
            fact = str(it.get("fact") or "").strip()
        else:
            continue
        if fact:
            items.append((cat, fact))
    _facts200_cache["mtime"] = mtime
    _facts200_cache["items"] = items
    return items


@client.on_message()
async def fact200_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return
    if text != "فکت":
        return

    items = _load_facts200()
    if not items:
        await safe_reply(event, "⚠️ فایل فکت‌ها (facts_200.json) کنار ربات پیدا نشد یا خالی است.")
        return

    idx = random.randrange(len(items))
    if len(items) > 1 and idx == _facts200_last_idx.get(chat_id):
        idx = (idx + random.randrange(1, len(items))) % len(items)
    _facts200_last_idx[chat_id] = idx

    cat, fact = items[idx]
    head = f"🏷 {cat}\n" if cat else ""
    await safe_reply(event, wrap_box(
        "📌", "فکت",
        f"{head}💡 {fact}\n\n💬 فکت بعدی؟ بنویس «فکت»"))


_DICE_PIPS = {
    1: {4},
    2: {0, 8},
    3: {0, 4, 8},
    4: {0, 2, 6, 8},
    5: {0, 2, 4, 6, 8},
    6: {0, 2, 3, 5, 6, 8},
}


def _dice_art(n: int) -> str:
    pips = _DICE_PIPS[n]
    rows = []
    for r in range(3):
        rows.append("".join("⚫" if (r * 3 + c) in pips else "⬜" for c in range(3)))
    return "\n".join(rows)


@client.on_message()
async def dice_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return
    if text != "تاس":
        return

    n = random.randint(1, 6)
    try:
        await event.reply(_dice_art(n))
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ dice reply error: {e}")


GAME_GUESS_MIN = 1
GAME_GUESS_MAX = 100
GAME_GUESS_IDLE_SECONDS = 15 * 60
GAME_SCRAMBLE_HINT_SECONDS = 30
GAME_SCRAMBLE_TOTAL_SECONDS = 60

_guess_games: dict = {}
_scramble_games: dict = {}
_scramble_token = 0

_GAME_STRIP_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u0640\u064b-\u065f\s]")


def _game_norm_text(s: str) -> str:
    """نرمال‌سازی برای مقایسه: ي/ك عربی، آ→ا، حذف نیم‌فاصله/کشیده/اعراب/فاصله."""
    s = (s or "").replace("ي", "ی").replace("ك", "ک").replace("آ", "ا").replace("ۀ", "ه")
    return _GAME_STRIP_RE.sub("", s)


def _game_now() -> float:
    return asyncio.get_running_loop().time()


_game_user_cache: dict = {}


def _game_user_has_name(user) -> bool:
    return bool(user is not None and (getattr(user, 'first_name', None)
                                      or getattr(user, 'last_name', None)
                                      or getattr(user, 'username', None)))


async def _game_resolve_user(uid, user=None):
    """آبجکت کاربر با اسم واقعی. اگه event.sender خالی بود (که خیلی وقت‌ها خالیه) از سرور
    می‌گیره و کش می‌کنه؛ وگرنه تگ‌ها می‌شد «کاربر ۱۲۳۴۵» به‌جای اسم."""
    if _game_user_has_name(user):
        _game_user_cache[uid] = user
        return user
    cached = _game_user_cache.get(uid)
    if cached is not None:
        return cached
    try:
        fetched = await client.get_entity(uid)
    except asyncio.CancelledError:
        raise
    except Exception:
        fetched = None
    if _game_user_has_name(fetched):
        if len(_game_user_cache) > 2000:
            _game_user_cache.clear()
        _game_user_cache[uid] = fetched
        return fetched
    return user if user is not None else fetched


async def _game_quick_reply(event, text: str) -> None:
    """پاسخ کوتاهِ حین بازی (بدون امضای ربات، مثل تاس)."""
    try:
        await event.reply(text)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ game reply error: {e}")


async def _game_send(chat_id, text: str, entities=None):
    kwargs = {"formatting_entities": entities, "parse_mode": None} if entities else {}
    try:
        return await client.send_message(chat_id, _brand_text(text), **kwargs)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ game send error [{chat_id}]: {e}")
        return None


async def _game_winner_text(event, prefix: str, suffix: str):
    """متن با تگِ واقعیِ برنده: prefix + اسم قابل‌کلیک + suffix → (text, entities)."""
    sender_id = getattr(event, 'sender_id', None)
    user = await _game_resolve_user(sender_id, getattr(event, 'sender', None))
    mb = MentionTextBuilder().text(prefix)
    await mb.mention(sender_id, user, label=_ship_label(user, sender_id))
    mb.text(suffix)
    return mb.build()


def _fa(n) -> str:
    return to_persian_digits(str(n))


async def _game_compose(*parts):
    """متن + تگ‌های واقعی: هر part یا رشته‌ست یا (user_id, user)."""
    mb = MentionTextBuilder()
    for p in parts:
        if isinstance(p, tuple):
            uid, user = p
            user = await _game_resolve_user(uid, user)
            await mb.mention(uid, user, label=_ship_label(user, uid))
        else:
            mb.text(p)
    return mb.build()


@client.on_message()
async def guess_number_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False) or not text:
        return
    if not (text in ("حدس عدد", "پایان حدس عدد") or text.startswith("حدس ")):
        return

    now = _game_now()
    game = _guess_games.get(chat_id)
    if game and now - game["ts"] > GAME_GUESS_IDLE_SECONDS:
        _guess_games.pop(chat_id, None)
        if text != "حدس عدد":
            await safe_reply(event, wrap_box(
                "⌛", "حدس عدد",
                f"بازی قبلی منقضی شد؛ عدد {_fa(game['n'])} بود.\n💬 برای بازی جدید بنویس «حدس عدد»"))
            return
        game = None

    if text == "حدس عدد":
        if game:
            await safe_reply(event, wrap_box(
                "🔢", "حدس عدد",
                f"یه بازی همین الان فعاله!\n🎯 عدد بین {_fa(game['lo'])} و {_fa(game['hi'])} هست\n"
                f"✍️ حدست رو این‌طور بنویس: حدس {_fa(50)}"))
            return
        _guess_games[chat_id] = {
            "n": random.randint(GAME_GUESS_MIN, GAME_GUESS_MAX),
            "lo": GAME_GUESS_MIN, "hi": GAME_GUESS_MAX,
            "tries": 0, "starter": sender_id, "ts": now,
        }
        await safe_reply(event, wrap_box(
            "🔢", "حدس عدد",
            f"یه عدد بین {_fa(GAME_GUESS_MIN)} تا {_fa(GAME_GUESS_MAX)} انتخاب کردم!\n"
            f"✍️ حدست رو این‌طور بنویس: حدس {_fa(50)}\n"
            "🏆 اولین نفری که درست حدس بزنه برنده‌ست"))
        return

    if text == "پایان حدس عدد":
        if not game:
            return
        chat = get_chat_cfg(chat_id)
        if sender_id != game["starter"] and not is_admin(chat, sender_id):
            await safe_reply(event, "⛔️ فقط شروع‌کننده‌ی بازی یا ادمین‌ها می‌تونن بازی رو تموم کنن.")
            return
        _guess_games.pop(chat_id, None)
        await safe_reply(event, wrap_box(
            "🏁", "حدس عدد",
            f"بازی تموم شد؛ عدد {_fa(game['n'])} بود.\n💬 بازی جدید؟ بنویس «حدس عدد»"))
        return

    if not game:
        return
    arg = normalize_digits(text[len("حدس "):]).strip()
    if not arg.isdigit() or len(arg) > 6:
        return
    g = int(arg)
    if g < GAME_GUESS_MIN or g > GAME_GUESS_MAX:
        await _game_quick_reply(event, f"⚠️ عدد باید بین {_fa(GAME_GUESS_MIN)} تا {_fa(GAME_GUESS_MAX)} باشه")
        return

    game["ts"] = now
    game["tries"] += 1
    n = game["n"]
    if g == n:
        _guess_games.pop(chat_id, None)
        msg, ents = await _game_winner_text(
            event, "🎉 ",
            f" درست حدس زد!\n🔢 عدد {_fa(n)} بود • تعداد حدس‌ها: {_fa(game['tries'])}\n\n"
            "💬 بازی دوباره؟ بنویس «حدس عدد»")
        await safe_reply(event, msg, entities=ents)
        return
    if g < n:
        game["lo"] = max(game["lo"], g + 1)
        arrow = "⬆️ بزرگ‌تره"
    else:
        game["hi"] = min(game["hi"], g - 1)
        arrow = "⬇️ کوچک‌تره"
    await _game_quick_reply(event, f"{arrow}! (بین {_fa(game['lo'])} و {_fa(game['hi'])})")


_RPS_PREFIX = "سنگ کاغذ قیچی"
_RPS_EMOJI = {"سنگ": "✊", "کاغذ": "✋", "قیچی": "✌️"}
_RPS_BEATS = {"سنگ": "قیچی", "کاغذ": "سنگ", "قیچی": "کاغذ"}
_RPS_ALIASES = {"سنگ": "سنگ", "کاغذ": "کاغذ", "کاغد": "کاغذ", "قیچی": "قیچی", "قیچ": "قیچی"}


@client.on_message()
async def rock_paper_scissors_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False) or not text:
        return
    if not text.startswith(_RPS_PREFIX):
        return

    rest = _game_norm_text(text[len(_RPS_PREFIX):])
    mine = _RPS_ALIASES.get(rest)
    if mine is None:
        await safe_reply(event, wrap_box(
            "✊", "سنگ کاغذ قیچی",
            "انتخابت رو کنار دستور بنویس:\n"
            "▸ سنگ کاغذ قیچی سنگ ✊\n"
            "▸ سنگ کاغذ قیچی کاغذ ✋\n"
            "▸ سنگ کاغذ قیچی قیچی ✌️"))
        return

    bot_pick = random.choice(list(_RPS_BEATS))
    if mine == bot_pick:
        verdict = "🤝 مساوی شد!"
    elif _RPS_BEATS[mine] == bot_pick:
        verdict = "🏆 تو بردی!"
    else:
        verdict = "🤖 من بردم!"
    await safe_reply(event, wrap_box(
        "✊", "سنگ کاغذ قیچی",
        f"👤 تو: {_RPS_EMOJI[mine]} {mine}\n"
        f"🤖 من: {_RPS_EMOJI[bot_pick]} {bot_pick}\n\n"
        f"{verdict}\n\n💬 دوباره؟ همون دستور رو بنویس"))


SCRAMBLE_WORDS = [
    "آسمان", "زمین", "خورشید", "ستاره", "دریا", "جنگل", "کوهستان", "درخت", "گلدان", "پنجره",
    "دیوار", "خیابان", "ماشین", "هواپیما", "کشتی", "دوچرخه", "قطار", "موتور", "تلفن", "کامپیوتر",
    "کتاب", "دفتر", "مداد", "خودکار", "مدرسه", "معلم", "دانشگاه", "بازار", "فروشگاه", "رستوران",
    "پنیر", "پرتقال", "انگور", "هندوانه", "خربزه", "گیلاس", "آلبالو", "زردآلو", "انجیر", "شلغم",
    "هویج", "بادمجان", "گوجه", "خیار", "فلفل", "پیاز", "ماهی", "گوسفند", "پلنگ", "خرگوش",
    "لاکپشت", "دلفین", "پروانه", "زنبور", "عنکبوت", "کبوتر", "گنجشک", "طوطی", "عقاب", "زرافه",
    "کانگورو", "میمون", "خفاش", "مورچه", "دوستی", "مهربانی", "آزادی", "عدالت", "زندگی", "شادی",
    "امید", "ایران", "تهران", "شیراز", "اصفهان", "تبریز", "مشهد", "کرمان", "ورزش", "فوتبال",
    "والیبال", "بسکتبال", "دویدن", "موسیقی", "نقاشی", "سینما", "داستان", "قهوه", "چایی", "شکلات",
    "بستنی", "شیرینی", "ادویه", "برنج", "ماست", "موبایل", "اینترنت", "کیبورد", "صفحه", "ربات",
    "برنامه", "ماوس", "دوربین", "تلویزیون", "یخچال", "کولر", "بخاری", "باران", "طوفان", "صحرا",
    "کویر", "دریاچه", "رودخانه", "آبشار", "چشمه", "جزیره", "ساحل", "سیاره", "کهکشان", "فضانورد",
    "موشک", "زمستان", "تابستان", "بهار", "پاییز", "صبحانه", "ناهار",
]


def _scramble_letters(word: str) -> list:
    letters = list(word)
    for _ in range(30):
        random.shuffle(letters)
        if "".join(letters) != word:
            break
    return letters


async def _scramble_timer(chat_id, token) -> None:
    """راهنمایی (حرف اول) و بعدش پایانِ بازی اگه کسی جواب نداد."""
    try:
        await asyncio.sleep(GAME_SCRAMBLE_HINT_SECONDS)
        g = _scramble_games.get(chat_id)
        if not g or g["token"] != token:
            return
        await _game_send(chat_id, f"💡 راهنمایی: حرف اول «{g['word'][0]}» و کلمه {_fa(len(g['word']))} حرفیه")
        await asyncio.sleep(GAME_SCRAMBLE_TOTAL_SECONDS - GAME_SCRAMBLE_HINT_SECONDS)
        g = _scramble_games.get(chat_id)
        if not g or g["token"] != token:
            return
        _scramble_games.pop(chat_id, None)
        await _game_send(chat_id, wrap_box(
            "⏰", "کلمه قاطی",
            f"وقت تموم شد و کسی پیداش نکرد 😅\n✅ جواب: {g['word']}\n\n💬 دوباره؟ بنویس «کلمه قاطی»"))
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ scramble timer error [{chat_id}]: {e}")


@client.on_message()
async def scramble_word_handler(_client, event):
    global _scramble_token
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False) or not text:
        return

    game = _scramble_games.get(chat_id)

    if text == "کلمه قاطی":
        if game:
            await safe_reply(event, wrap_box(
                "🔤", "کلمه قاطی",
                f"یه بازی همین الان فعاله!\n🧩 {' '.join(game['letters'])}\n✍️ کلمه‌ی درست رو بنویس"))
            return
        word = random.choice(SCRAMBLE_WORDS)
        _scramble_token += 1
        token = _scramble_token
        letters = _scramble_letters(word)
        _scramble_games[chat_id] = {
            "word": word, "norm": _game_norm_text(word), "letters": letters,
            "token": token, "started": _game_now(), "task": None,
        }
        await safe_reply(event, wrap_box(
            "🔤", "کلمه قاطی",
            f"حرف‌های این کلمه قاطی شده:\n\n🧩 {' '.join(letters)}\n\n"
            f"✍️ کلمه‌ی درست رو بنویس ({_fa(len(word))} حرفی)\n"
            f"⏳ {_fa(GAME_SCRAMBLE_TOTAL_SECONDS)} ثانیه وقت داری • اولین نفر برنده‌ست"))
        g = _scramble_games.get(chat_id)
        if g and g["token"] == token:
            g["task"] = asyncio.create_task(_scramble_timer(chat_id, token))
        return

    if not game or len(text) > 30:
        return
    if _game_norm_text(text) != game["norm"]:
        return

    _scramble_games.pop(chat_id, None)
    task = game.get("task")
    if task:
        task.cancel()
    secs = max(1, int(round(_game_now() - game["started"])))
    msg, ents = await _game_winner_text(
        event, "🎉 ",
        f" پیداش کرد!\n✅ کلمه: {game['word']}\n⚡ زمان: {_fa(secs)} ثانیه\n\n"
        "💬 دوباره؟ بنویس «کلمه قاطی»")
    await safe_reply(event, msg, entities=ents)


DUEL_OPEN_SECONDS = 60
DUEL_MIN_WAIT_SECONDS = 3
DUEL_MAX_WAIT_SECONDS = 9
DUEL_DRAW_TIMEOUT_SECONDS = 20
DUEL_GRACE_SECONDS = 1.0
DUEL_ALLOWED_BEST_OF = (1, 3, 5)
DUEL_ELO_START = 1000
DUEL_ELO_K = 32
DUEL_SCORES_FILE = os.path.join(BASE_DIR, "duel_scores.json")
DUEL_LEADERBOARD_SIZE = 10

_duels: dict = {}
_duel_token = 0
_duel_scores: dict = {}
_duel_scores_loaded = False

_DUEL_ATMOSPHERE = [
    "🌬 باد می‌وزه... یه بوته‌ی خشک از وسط خیابون غلت می‌خوره 🌵",
    "🦅 یه عقاب بالای سرتون دور می‌زنه...",
    "🔔 زنگِ کلیسای شهر یه بار صدا کرد...",
    "😰 قطره‌ی عرق از پیشونی‌تون سُر می‌خوره...",
    "🐴 یه اسب اون‌ور شهر شیهه کشید... همه‌جا ساکته...",
]
_DUEL_EARLY_LINES = [
    "قبل از علامت کشید و دستش رو باخت!",
    "دست‌پاچه شد و ماشه رو زودتر از موعد کشید!",
    "صبرش تموم شد و زود شلیک کرد!",
]
_DUEL_FAST_LINES = [
    "سریع‌تر شلیک کرد!",
    "مثل برق کشید!",
    "قبل از همه ماشه رو چکوند!",
]
_DUEL_SHOT_WORDS = {_game_norm_text(w) for w in ("شلیک", "🔫", "fire")}
_DUEL_W = _game_norm_text("دوئل")
_DUEL_CMD_ACCEPT = {_game_norm_text("قبول دوئل")}
_DUEL_CMD_BARE_ACCEPT = _game_norm_text("قبول")
_DUEL_CMD_CANCEL = {_game_norm_text("لغو دوئل")}
_DUEL_CMD_DECLINE = {_game_norm_text("رد دوئل")}
_DUEL_CMD_STATS = {_game_norm_text("آمار دوئل")}
_DUEL_CMD_BOARD = {_game_norm_text(x) for x in ("رده‌بندی دوئل", "رتبه‌بندی دوئل", "جدول دوئل")}
_DUEL_FIRST_WORDS = {_game_norm_text(w) for w in ("دوئل", "قبول", "لغو", "رد", "آمار", "رده‌بندی", "رتبه‌بندی", "جدول")}
_DUEL_BESTOF_WORDS = {_game_norm_text("سه"): 3, _game_norm_text("پنج"): 5}


def _duel_load_scores() -> None:
    global _duel_scores, _duel_scores_loaded
    if _duel_scores_loaded:
        return
    _duel_scores_loaded = True
    try:
        with open(DUEL_SCORES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _duel_scores = data
    except FileNotFoundError:
        pass
    except Exception as e:
        _log(f"⚠️ duel scores load error: {e}")


def _duel_save_scores() -> None:
    tmp = DUEL_SCORES_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_duel_scores, f, ensure_ascii=False)
        os.replace(tmp, DUEL_SCORES_FILE)
    except Exception as e:
        _log(f"⚠️ duel scores save error: {e}")


def _duel_rating(e: dict) -> int:
    """امتیاز بازیکن؛ برای رکوردهای قدیمی (بدون امتیاز) از روی برد و باخت حدس زده می‌شه."""
    if "r" in e:
        return int(e["r"])
    return max(0, DUEL_ELO_START + 10 * (int(e.get("w", 0)) - int(e.get("l", 0))))


def _duel_entry(board: dict, uid, name: str) -> dict:
    e = board.setdefault(str(uid), {"name": name})
    e["name"] = name
    e.setdefault("w", 0)
    e.setdefault("l", 0)
    e["r"] = _duel_rating(e)
    e.setdefault("s", 0)
    e.setdefault("bs", 0)
    return e


def _duel_record(chat_id, w_id, w_name, l_id, l_name, react=None) -> dict:
    """نتیجه‌ی کل دوئل: برد/باخت + امتیاز ELO + سری برد + رکورد سرعت."""
    _duel_load_scores()
    board = _duel_scores.setdefault(str(chat_id), {})
    w = _duel_entry(board, w_id, w_name)
    l = _duel_entry(board, l_id, l_name)
    expected = 1.0 / (1.0 + 10 ** ((l["r"] - w["r"]) / 400.0))
    delta = max(1, int(round(DUEL_ELO_K * (1.0 - expected))))
    l_before = l["r"]
    w["r"] += delta
    l["r"] = max(0, l["r"] - delta)
    w["w"] += 1
    l["l"] += 1
    w["s"] += 1
    w["bs"] = max(w["bs"], w["s"])
    l["s"] = 0
    new_pb = False
    if react:
        old = w.get("br")
        if not old or react < old:
            w["br"] = round(react, 3)
            new_pb = True
    _duel_save_scores()
    return {"w": w, "l": l, "gain": delta, "lost": l_before - l["r"], "new_pb": new_pb}


def _duel_title(rating: int) -> str:
    if rating >= 1300:
        return "👑 افسانه‌ی وسترن"
    if rating >= 1150:
        return "🤠 کلانتر"
    if rating >= 1050:
        return "🎯 تیرانداز"
    if rating >= 950:
        return "🐎 گاوچران"
    return "🌵 تازه‌کار"


def _duel_secs(x: float) -> str:
    return to_persian_digits(f"{x:.2f}").replace(".", "٫")


def _duel_signed(n: int) -> str:
    return f"+{_fa(n)}" if n >= 0 else f"−{_fa(abs(n))}"


def _duel_event_id(event):
    mid = getattr(event, 'id', None)
    if mid is None:
        mid = getattr(getattr(event, 'message', None), 'id', None)
    return mid if isinstance(mid, int) else None


def _duel_is_shot(text: str) -> bool:
    t = _game_norm_text(text).replace("\ufe0f", "").rstrip("!.…؟?").lower()
    return t in _DUEL_SHOT_WORDS


def _duel_cancel_task(d) -> None:
    """تسک‌های دوئل رو لغو می‌کنه (به‌جز تسکی که همین الان داره اجرا می‌شه)."""
    if not d:
        return
    cur = None
    try:
        cur = asyncio.current_task()
    except RuntimeError:
        pass
    for key in ("task", "grace_task"):
        t = d.get(key)
        if t and t is not cur and not t.done():
            t.cancel()


def _duel_get(chat_id):
    """دوئلِ فعالِ گپ. اگه به هر دلیلی گیر کرده باشه (منقضی شده) پاکش می‌کنه تا گپ برای همیشه قفل نشه."""
    d = _duels.get(chat_id)
    if d and _game_now() > d.get("expires", 0):
        _duels.pop(chat_id, None)
        _duel_cancel_task(d)
        return None
    return d


def _duel_alive(chat_id, d, phase=None) -> bool:
    if _duels.get(chat_id) is not d or d.get("resolving"):
        return False
    return phase is None or d["phase"] == phase


async def _duel_safe_compose(*parts):
    """مثل _game_compose؛ اگه تگ‌کردن خطا داد، متن ساده می‌فرسته تا دوئل وسط راه گیر نکنه."""
    try:
        return await _game_compose(*parts)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ duel compose error: {e}")
        out = []
        for p in parts:
            if isinstance(p, tuple):
                out.append(_ship_label(p[1], p[0]))
            else:
                out.append(p)
        return "".join(out), None


def _duel_capture_shot(event) -> None:
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return
    d = _duel_get(chat_id)
    if not d or d["phase"] not in ("wait", "draw") or d.get("resolving"):
        return
    if sender_id not in (d["a"], d["b"]) or sender_id in d["shots"]:
        return
    text = (getattr(event, 'raw_text', '') or '').strip()
    if not text or not _duel_is_shot(text):
        return
    mid = _duel_event_id(event)
    base = d.get("base_id")
    if d["ids_ok"] and mid is not None and base is not None and mid < base:
        return
    d["shots"][sender_id] = {"id": mid, "t": _game_now()}
    _duel_react(chat_id, d, sender_id)


def _duel_is_early(d, shot) -> bool:
    """شلیکِ زود = پیامی که آیدی‌ش کوچیک‌تر از آیدیِ پیامِ علامته (یعنی قبل از علامت فرستاده شده)."""
    sig = d.get("signal_id")
    return bool(d["ids_ok"] and sig is not None and shot["id"] is not None and shot["id"] < sig)


def _duel_start_finish(chat_id, d, loser_id, kind) -> None:
    d["resolving"] = True
    winner_id = d["b"] if loser_id == d["a"] else d["a"]
    asyncio.create_task(_duel_finish_round(chat_id, d, winner_id, kind))


def _duel_react(chat_id, d, uid) -> None:
    if d.get("resolving"):
        return
    shot = d["shots"][uid]
    if d["phase"] == "wait":
        if d["sending"]:
            return
        _duel_start_finish(chat_id, d, uid, "early")
        return
    if _duel_is_early(d, shot):
        _duel_start_finish(chat_id, d, uid, "early")
    elif d.get("grace_task") is None:
        d["grace_task"] = asyncio.create_task(_duel_grace(chat_id, d))


async def _duel_grace(chat_id, d) -> None:
    """چند لحظه صبر می‌کنه تا پیام‌های عقب‌افتاده هم برسن، بعد اونی که آیدی‌ش کوچیک‌تره (واقعاً زودتر فرستاده) برنده‌ست."""
    try:
        await asyncio.sleep(DUEL_GRACE_SECONDS)
        if not _duel_alive(chat_id, d, "draw"):
            return
        valid = [(u, s) for u, s in d["shots"].items() if not _duel_is_early(d, s)]
        if not valid:
            return
        use_ids = d["ids_ok"] and all(s["id"] is not None for _u, s in valid)
        winner = min(valid, key=lambda us: us[1]["id"] if use_ids else us[1]["t"])[0]
        d["resolving"] = True
        await _duel_finish_round(chat_id, d, winner, "fast")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ duel grace error [{chat_id}]: {e}")
        if _duels.get(chat_id) is d:
            _duels.pop(chat_id, None)


async def _duel_open_timer(chat_id, d) -> None:
    try:
        await asyncio.sleep(DUEL_OPEN_SECONDS)
        if _duels.get(chat_id) is not d or d["phase"] != "open":
            return
        _duels.pop(chat_id, None)
        msg, ents = await _duel_safe_compose("⌛ دوئلِ ", (d["a"], d["a_user"]), " بی‌حریف موند؛ کسی جرئت نکرد 😏")
        await _game_send(chat_id, msg, ents)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ duel open timer error [{chat_id}]: {e}")
        if _duels.get(chat_id) is d:
            _duels.pop(chat_id, None)


async def _duel_begin_round(chat_id, d, parts) -> None:
    """پیامِ شروعِ دست رو می‌فرسته؛ فقط بعد از رسیدنش (و دونستنِ آیدی‌ش) وارد فاز انتظار می‌شه."""
    d["phase"] = "prep"
    d["shots"] = {}
    d["sending"] = False
    d["signal_id"] = None
    d["signal_t"] = None
    d["base_id"] = None
    d["resolving"] = False
    d["grace_task"] = None
    d["expires"] = _game_now() + DUEL_MAX_WAIT_SECONDS + DUEL_DRAW_TIMEOUT_SECONDS + 45
    try:
        msg, ents = await _duel_safe_compose(*parts)
        sent = await _game_send(chat_id, msg, ents)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ duel begin error [{chat_id}]: {e}")
        sent = None
    if _duels.get(chat_id) is not d:
        return
    if sent is None:
        _duels.pop(chat_id, None)
        return
    base = getattr(sent, "id", None)
    base = base if isinstance(base, int) else None
    prev = d.get("last_id")
    d["ids_ok"] = bool(d["ids_ok"] and base is not None and prev is not None and base > prev)
    d["base_id"] = base
    d["last_id"] = base
    d["phase"] = "wait"
    d["task"] = asyncio.create_task(_duel_run(chat_id, d))


async def _duel_run(chat_id, d) -> None:
    """صبر تصادفی (+ فضاسازی) → علامت شلیک → اگه کسی شلیک نکرد، لغو."""
    try:
        total = random.uniform(DUEL_MIN_WAIT_SECONDS, DUEL_MAX_WAIT_SECONDS)
        if total >= 5 and random.random() < 0.6:
            first = total * random.uniform(0.35, 0.6)
            await asyncio.sleep(first)
            if not _duel_alive(chat_id, d, "wait"):
                return
            await _game_send(chat_id, random.choice(_DUEL_ATMOSPHERE))
            await asyncio.sleep(max(0.5, total - first))
        else:
            await asyncio.sleep(total)
        if not _duel_alive(chat_id, d, "wait"):
            return
        d["sending"] = True
        sent = await _game_send(chat_id, "🔫🔫🔫 شلیک! 🔫🔫🔫\n⚡ سریع بنویس «شلیک»")
        d["sending"] = False
        if _duels.get(chat_id) is not d or d.get("resolving"):
            return
        if sent is None:
            _duels.pop(chat_id, None)
            return
        sid = getattr(sent, "id", None)
        sid = sid if isinstance(sid, int) else None
        d["signal_id"] = sid
        if d["ids_ok"] and not (sid is not None and d.get("base_id") is not None and sid > d["base_id"]):
            d["ids_ok"] = False
        d["signal_t"] = _game_now()
        d["phase"] = "draw"
        for uid in sorted(d["shots"], key=lambda u: d["shots"][u]["t"]):
            _duel_react(chat_id, d, uid)
            if d.get("resolving"):
                return
        await asyncio.sleep(DUEL_DRAW_TIMEOUT_SECONDS)
        if _duels.get(chat_id) is not d or d.get("resolving") or d.get("grace_task") or d["phase"] != "draw":
            return
        _duels.pop(chat_id, None)
        await _game_send(chat_id, wrap_box(
            "😴", "دوئل",
            "هیچ‌کدومتون شلیک نکردین!\nدوئل لغو شد؛ دست‌هاتون که خواب رفته 😂"))
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ duel run error [{chat_id}]: {e}")
        if _duels.get(chat_id) is d:
            _duels.pop(chat_id, None)


async def _duel_finish_round(chat_id, d, winner_id, kind) -> None:
    """پایان یک دست: یا دوئل تموم می‌شه (ثبت در جدول) یا دستِ بعدی شروع می‌شه."""
    try:
        if _duels.get(chat_id) is not d:
            return
        _duel_cancel_task(d)
        d["expires"] = _game_now() + 90
        a, b = d["a"], d["b"]
        loser_id = b if winner_id == a else a
        users = {a: d["a_user"], b: d["b_user"]}
        W, L = (winner_id, users[winner_id]), (loser_id, users[loser_id])
        d["score"][winner_id] += 1
        sw, sl = d["score"][winner_id], d["score"][loser_id]
        need = d["best_of"] // 2 + 1

        react = None
        if kind == "fast":
            shot = d["shots"].get(winner_id)
            if shot and d.get("signal_t") is not None:
                r = shot["t"] - d["signal_t"]
                react = r if r >= 0.05 else None
            if react:
                best = d["best_react"].get(winner_id)
                d["best_react"][winner_id] = react if best is None else min(best, react)

        if kind == "early":
            head = ["🚫 ", L, " " + random.choice(_DUEL_EARLY_LINES) + "\n"]
        else:
            head = ["💥 ", W, " " + random.choice(_DUEL_FAST_LINES) + "\n"]
            if react:
                head.append(f"⚡ زمان واکنش: {_duel_secs(react)} ثانیه\n")

        if sw >= need:
            _duels.pop(chat_id, None)
            w_user = await _game_resolve_user(W[0], W[1])
            l_user = await _game_resolve_user(L[0], L[1])
            rec = _duel_record(chat_id, W[0], _ship_label(w_user, W[0]), L[0], _ship_label(l_user, L[0]),
                               d["best_react"].get(winner_id))
            we, le = rec["w"], rec["l"]
            if d["best_of"] == 1:
                win_line = ["🏆 ", W, " برنده‌ی دوئل شد!"]
            else:
                win_line = ["🏆 ", W, f" با نتیجه‌ی {_fa(sw)} : {_fa(sl)} برنده‌ی دوئل شد!"]
            tail = []
            if kind == "fast":
                tail += ["\n💀 ", L, " از پا افتاد"]
            tail.append(
                f"\n\n📈 امتیاز برنده: {_fa(we['r'])} ({_duel_signed(rec['gain'])}) • {_duel_title(we['r'])}"
                f"\n📉 امتیاز بازنده: {_fa(le['r'])} ({_duel_signed(-rec['lost'])})"
                f"\n🏅 رکورد برنده: {_fa(we['w'])} برد • {_fa(we['l'])} باخت")
            if we["s"] >= 2:
                tail.append(f"\n🔥 سری برد: {_fa(we['s'])} تا پشت‌سرهم!")
            if rec["new_pb"]:
                tail.append("\n🚀 رکورد سرعتِ شخصیِ جدید!")
            tail.append("\n💬 دوئل جدید؟ بنویس «دوئل» • جدول: «رده‌بندی دوئل»")
            msg, ents = await _duel_safe_compose(*head, *win_line, *tail)
            await _game_send(chat_id, msg, ents)
            return

        d["round"] += 1
        parts = head + [
            "\n📊 نتیجه تا اینجا: ", (a, d["a_user"]), f" {_fa(d['score'][a])} : {_fa(d['score'][b])} ", (b, d["b_user"]),
            f"\n\n🌵 دست {_fa(d['round'])} از {_fa(d['best_of'])} — هر دو دست روی ماشه... صبر کنین!"
            "\n😈 قبل از علامت «شلیک» ننویسین!",
        ]
        await _duel_begin_round(chat_id, d, parts)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ duel finish error [{chat_id}]: {e}")
        if _duels.get(chat_id) is d:
            _duels.pop(chat_id, None)


def _duel_board_rows(chat_id) -> list:
    _duel_load_scores()
    board = _duel_scores.get(str(chat_id)) or {}
    rows = [(uid, e) for uid, e in board.items() if e.get("w", 0) or e.get("l", 0)]
    rows.sort(key=lambda ue: (-_duel_rating(ue[1]), -ue[1].get("w", 0), ue[1].get("l", 0), ue[1].get("name", "")))
    return rows


def _duel_leaderboard_text(chat_id) -> str:
    rows = _duel_board_rows(chat_id)
    if not rows:
        return wrap_box("🏆", "رده‌بندی دوئل", "هنوز هیچ دوئلی انجام نشده!\n💬 اولیش رو شروع کن: «دوئل»")
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (_uid, e) in enumerate(rows[:DUEL_LEADERBOARD_SIZE]):
        mark = medals[i] if i < 3 else f"{_fa(i + 1)}."
        w, l = e.get("w", 0), e.get("l", 0)
        pct = round(100 * w / (w + l)) if (w + l) else 0
        lines.append(f"{mark} {e.get('name', '?')}\n     ⭐ {_fa(_duel_rating(e))} • {_fa(w)} برد • {_fa(l)} باخت • {_fa(pct)}٪")
    extra = []
    fastest = [(e["br"], e.get("name", "?")) for _u, e in rows if e.get("br")]
    if fastest:
        t, n = min(fastest)
        extra.append(f"⚡ سریع‌ترین شلیک: {n} ({_duel_secs(t)} ثانیه)")
    streak = [(e.get("bs", 0), e.get("name", "?")) for _u, e in rows if e.get("bs", 0) >= 2]
    if streak:
        s, n = max(streak)
        extra.append(f"🔥 بهترین سری برد: {n} ({_fa(s)} تا)")
    body = "\n".join(lines)
    if extra:
        body += "\n\n" + "\n".join(extra)
    return wrap_box("🏆", "رده‌بندی دوئل", body)


def _duel_stats_text(chat_id, uid, name) -> str:
    rows = _duel_board_rows(chat_id)
    for i, (u, e) in enumerate(rows):
        if u == str(uid):
            w, l = e.get("w", 0), e.get("l", 0)
            pct = round(100 * w / (w + l)) if (w + l) else 0
            lines = [
                f"🤠 {name}",
                f"{_duel_title(_duel_rating(e))} • رتبه‌ی {_fa(i + 1)} از {_fa(len(rows))}",
                f"⭐ امتیاز: {_fa(_duel_rating(e))}",
                f"✅ {_fa(w)} برد • ❌ {_fa(l)} باخت • 🎯 {_fa(pct)}٪ برد",
                f"🔥 سری برد فعلی: {_fa(e.get('s', 0))} • بهترین: {_fa(e.get('bs', 0))}",
            ]
            if e.get("br"):
                lines.append(f"⚡ سریع‌ترین شلیک: {_duel_secs(e['br'])} ثانیه")
            return wrap_box("📊", "آمار دوئل", "\n".join(lines))
    return wrap_box("📊", "آمار دوئل", f"🤠 {name}\nهنوز هیچ دوئلی نکرده!\n💬 بنویس «دوئل» و شروع کن")


@client.on_message()
async def duel_handler(_client, event):
    global _duel_token
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False) or not text:
        return
    if _duel_is_shot(text):
        return
    parts = text.split()
    p0 = _game_norm_text(parts[0])
    if p0 not in _DUEL_FIRST_WORDS:
        return
    p01 = _game_norm_text("".join(parts[:2]))
    has_reply = bool(getattr(event, 'reply_to_msg_id', None) or getattr(event, 'reply_to', None))

    if p01 in _DUEL_CMD_BOARD:
        await safe_reply(event, _duel_leaderboard_text(chat_id))
        return

    if p01 in _DUEL_CMD_STATS:
        arg = " ".join(parts[2:]).strip()
        target_id, user = sender_id, getattr(event, 'sender', None)
        if has_reply or arg:
            target_id = await resolve_target(event, chat_id, arg)
            if not target_id:
                await safe_reply(event, "⚠️ کاربر مورد نظر پیدا نشد. با ریپلای یا «آمار دوئل @یوزرنیم» امتحان کن.")
                return
            user = None
        user = await _game_resolve_user(target_id, user)
        await safe_reply(event, _duel_stats_text(chat_id, target_id, _ship_label(user, target_id)))
        return

    if p01 in _DUEL_CMD_CANCEL:
        duel = _duel_get(chat_id)
        if not duel:
            return
        chat = get_chat_cfg(chat_id)
        if sender_id != duel["a"] and not is_admin(chat, sender_id):
            await safe_reply(event, "⛔️ فقط شروع‌کننده‌ی دوئل یا ادمین‌ها می‌تونن لغوش کنن.")
            return
        _duels.pop(chat_id, None)
        duel["resolving"] = True
        _duel_cancel_task(duel)
        await safe_reply(event, wrap_box("🏳️", "دوئل", "دوئل لغو شد.\n💬 دوباره؟ بنویس «دوئل»"))
        return

    if p01 in _DUEL_CMD_DECLINE:
        duel = _duel_get(chat_id)
        if not duel or duel["phase"] != "open" or not duel["target"] or sender_id != duel["target"]:
            return
        _duels.pop(chat_id, None)
        _duel_cancel_task(duel)
        msg, ents = await _duel_safe_compose("🐔 ", (sender_id, getattr(event, 'sender', None)),
                                             " جا زد و دوئل رو رد کرد!")
        await safe_reply(event, msg, entities=ents)
        return

    bare_accept = (p0 == _DUEL_CMD_BARE_ACCEPT and len(parts) == 1)
    if p01 in _DUEL_CMD_ACCEPT or bare_accept:
        duel = _duel_get(chat_id)
        if not duel:
            if not bare_accept:
                await safe_reply(event, "⚠️ دوئلی باز نیست؛ با نوشتن «دوئل» یکی بساز.")
            return
        if duel["phase"] != "open":
            return
        if sender_id == duel["a"]:
            if not bare_accept:
                await safe_reply(event, "⛔️ با خودت که نمی‌تونی دوئل کنی 😅")
            return
        if duel["target"] and sender_id != duel["target"]:
            if not bare_accept:
                await safe_reply(event, "⛔️ این دوئل مخصوص یه نفر دیگه‌ست.")
            return
        duel["b"], duel["b_user"], duel["phase"] = sender_id, getattr(event, 'sender', None), "prep"
        duel["last_id"] = _duel_event_id(event)
        duel["score"] = {duel["a"]: 0, sender_id: 0}
        _duel_cancel_task(duel)
        head = ["⚔️ ", (duel["a"], duel["a_user"]), " 🆚 ", (duel["b"], duel["b_user"])]
        if duel["best_of"] > 1:
            head.append(f"\n🎖 بهترین از {_fa(duel['best_of'])} دست")
        head.append("\n🌵 هر دو دست روی ماشه... صبر کنین!\n😈 اگه قبل از علامت «شلیک» بنویسین، می‌بازین!")
        await _duel_begin_round(chat_id, duel, head)
        return

    if p0 == _DUEL_W:
        if _duel_get(chat_id):
            await safe_reply(event, "⚠️ یه دوئل همین الان توی گپ در جریانه؛ صبر کن تموم شه (یا «لغو دوئل»).")
            return
        best_of, name_tokens = 1, []
        for tok in parts[1:]:
            nt = normalize_digits(tok)
            if nt.isdigit() and len(nt) <= 2:
                best_of = int(nt)
            elif _game_norm_text(tok) in _DUEL_BESTOF_WORDS:
                best_of = _DUEL_BESTOF_WORDS[_game_norm_text(tok)]
            else:
                name_tokens.append(tok)
        if len(name_tokens) > 1:
            return
        arg = name_tokens[0] if name_tokens else ""
        if arg and not (arg.startswith("@") or arg.isdigit() or re.fullmatch(r"[A-Za-z0-9_]{4,}", arg)):
            return
        if best_of not in DUEL_ALLOWED_BEST_OF:
            await safe_reply(event, "⚠️ تعداد دست‌ها فقط می‌تونه ۱ (پیش‌فرض)، ۳ یا ۵ باشه. مثال: «دوئل ۳»")
            return
        target_id, target_user = None, None
        if has_reply or arg:
            target_id = await resolve_target(event, chat_id, arg)
            if not target_id:
                await safe_reply(event, "⚠️ کاربر مورد نظر پیدا نشد. با ریپلای یا «دوئل @یوزرنیم» امتحان کن.")
                return
            if target_id == sender_id:
                await safe_reply(event, "⛔️ نمی‌تونی خودت رو به دوئل دعوت کنی 😅")
                return
            if target_id == await _ship_get_my_id():
                await safe_reply(event, "🤖 من اهل دوئل نیستم؛ یه حریفِ آدمیزاد پیدا کن 😎")
                return
            try:
                target_user = await client.get_entity(target_id)
            except Exception:
                target_user = None

        if _duel_get(chat_id):
            await safe_reply(event, "⚠️ یه دوئل همین الان توی گپ در جریانه؛ صبر کن تموم شه (یا «لغو دوئل»).")
            return
        _duel_token += 1
        a_user = getattr(event, 'sender', None)
        d = {
            "phase": "open", "a": sender_id, "a_user": a_user, "b": None, "b_user": None,
            "target": target_id, "token": _duel_token, "task": None, "grace_task": None,
            "best_of": best_of, "round": 1, "score": {sender_id: 0}, "best_react": {},
            "shots": {}, "sending": False, "signal_id": None, "signal_t": None,
            "base_id": None, "last_id": _duel_event_id(event), "ids_ok": True, "resolving": False,
            "expires": _game_now() + DUEL_OPEN_SECONDS + 20,
        }
        _duels[chat_id] = d
        of_line = f"\n🎖 بهترین از {_fa(best_of)} دست" if best_of > 1 else ""
        if target_id:
            msg, ents = await _duel_safe_compose(
                "🤠 ", (sender_id, a_user), " ⚔️ ", (target_id, target_user),
                " رو به دوئل دعوت کرد!" + of_line + "\n✍️ برای قبول بنویس «قبول دوئل» (یا «رد دوئل»)\n"
                f"⏳ {_fa(DUEL_OPEN_SECONDS)} ثانیه وقت داری")
        else:
            msg, ents = await _duel_safe_compose(
                "🤠 ", (sender_id, a_user),
                " یه دوئل باز کرد!" + of_line + "\n🎯 هر کی جرئت داره بنویسه «قبول دوئل»\n"
                f"⏳ {_fa(DUEL_OPEN_SECONDS)} ثانیه وقت دارین")
        await safe_reply(event, msg, entities=ents)
        if _duels.get(chat_id) is d and d["phase"] == "open":
            d["task"] = asyncio.create_task(_duel_open_timer(chat_id, d))
        return


TTT_CODE_DIGITS = 5
TTT_LOBBY_SECONDS = 120
TTT_IDLE_SECONDS = 300
TTT_WATCH_INTERVAL_SECONDS = 10
TTT_MAX_GAMES_PER_CHAT = 8
_TTT_LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
_TTT_KEYCAPS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
_TTT_MARK = {"X": "❌", "O": "⭕"}

_ttt_games: dict = {}
_ttt_players: dict = {}
_ttt_token = 0


class _GCode:
    """بخش تک‌فاصله (monospace) داخل جعبه؛ هر خطش جدا کد می‌شه."""
    def __init__(self, text: str):
        self.text = text


async def _game_box_compose(emoji: str, title: str, *parts):
    """مثل wrap_box ولی با تگ واقعیِ کاربرها و بخش‌های monospace:
    هر part یا رشته‌ست، یا (user_id, user) برای تگ، یا _GCode برای متن تک‌فاصله. → (text, entities)"""
    mb = MentionTextBuilder()
    mb.text(f"╭─〔 {emoji} {title} 〕─╮\n│\n│ ")
    for p in parts:
        if isinstance(p, tuple):
            uid, user = p
            user = await _game_resolve_user(uid, user)
            await mb.mention(uid, user, label=_ship_label(user, uid))
        elif isinstance(p, _GCode):
            for i, ln in enumerate(p.text.split("\n")):
                if i:
                    mb.text("\n│ ")
                if ln:
                    mb.code(ln)
        else:
            mb.text(p.replace("\n", "\n│ "))
    mb.text("\n╰────────────────╯")
    return mb.build()


async def _game_reply_ents(event, text: str, ents) -> None:
    """پاسخ بدون امضای ربات، با تگ (برای حرکت‌های حین بازی)."""
    kwargs = {"formatting_entities": ents, "parse_mode": None} if ents else {}
    try:
        await event.reply(text, **kwargs)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ game reply error: {e}")


def _ttt_winner(board):
    for a, b, c in _TTT_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a], (a, b, c)
    return None, None


def _ttt_render(board, win=None) -> str:
    """صفحه با ایموجی؛ هر ردیف با LRM شروع می‌شه تا ترتیب ۱ ۲ ۳ توی متن راست‌به‌چپ برعکس نشه."""
    rows = []
    for r in range(3):
        cells = []
        for c in range(3):
            i = r * 3 + c
            if win and i in win:
                cells.append("🟩")
            elif board[i]:
                cells.append(_TTT_MARK[board[i]])
            else:
                cells.append(_TTT_KEYCAPS[i])
        rows.append("\u200e" + "".join(cells))
    return "\n".join(rows)


def _ttt_new_code(chat_id):
    used = set(_ttt_games.get(chat_id, {}))
    for _ in range(60):
        code = str(random.randint(10 ** (TTT_CODE_DIGITS - 1), 10 ** TTT_CODE_DIGITS - 1))
        if code not in used:
            return code
    return None


def _ttt_drop(chat_id, game) -> None:
    games = _ttt_games.get(chat_id)
    if games is not None:
        games.pop(game["code"], None)
        if not games:
            _ttt_games.pop(chat_id, None)
    for uid in game.get("members", ()):
        _ttt_players.pop((chat_id, uid), None)
    task = game.get("task")
    if task and task is not asyncio.current_task():
        task.cancel()


def _ttt_lookup(chat_id, user_id):
    code = _ttt_players.get((chat_id, user_id))
    return _ttt_games.get(chat_id, {}).get(code) if code else None


async def _ttt_watch(chat_id, token, code) -> None:
    """لابیِ بی‌حریف و بازیِ بی‌حرکت رو بعد از مدتی جمع می‌کنه."""
    try:
        while True:
            await asyncio.sleep(TTT_WATCH_INTERVAL_SECONDS)
            game = _ttt_games.get(chat_id, {}).get(code)
            if not game or game["token"] != token:
                return
            limit = TTT_LOBBY_SECONDS if game["phase"] == "open" else TTT_IDLE_SECONDS
            if _game_now() - game["ts"] <= limit:
                continue
            _ttt_drop(chat_id, game)
            if game["phase"] == "open":
                msg, ents = await _game_compose("⌛ بازی دوزِ ", game["creator"], f" (کد {_fa(code)}) بی‌حریف موند.")
            else:
                msg, ents = await _game_compose(
                    "⌛ بازی دوزِ ", game["players"]["X"], " و ", game["players"]["O"], " به‌خاطر بی‌حرکتی تموم شد.")
            await _game_send(chat_id, msg, ents)
            return
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ ttt watch error [{chat_id}]: {e}")


async def _ttt_lobby_message(game):
    code = _fa(game["code"])
    return await _game_box_compose(
        "⭕", "دوز",
        "🤠 ", game["creator"], " یه بازی دوز ساخت!\n\n",
        f"🆔 کد بازی: {code}\n",
        "✍️ هر کی می‌خواد بیاد، همین کد رو توی گپ بفرسته\n",
        f"    (یا بنویسه «دوز {code}»)\n",
        "👆 یا با ریپلای روی یه نفر «دوز» بزن تا مستقیم بیاد توی بازی\n",
        f"⏳ {_fa(TTT_LOBBY_SECONDS // 60)} دقیقه وقت داره")


async def _ttt_board_message(game, *tail, win=None, intro=()):
    """جعبه‌ی استاندارد: (intro) + «❌ نفر  🆚  ⭕ نفر» + صفحه + tail؛ همه با تگ واقعی."""
    return await _game_box_compose(
        "⭕", "دوز", *intro,
        "❌ ", game["players"]["X"], "  🆚  ⭕ ", game["players"]["O"], "\n\n",
        _ttt_render(game["board"], win), "\n\n",
        *tail)


async def _ttt_begin(chat_id, game, second) -> None:
    """حریف پیدا شد: نماد و نفر اول تصادفی، بعد شروع."""
    a = game["creator"]
    x, o = (a, second) if random.random() < 0.5 else (second, a)
    game["players"] = {"X": x, "O": o}
    game["members"] = {a[0], second[0]}
    game["phase"], game["turn"], game["ts"] = "play", "X", _game_now()
    _ttt_players[(chat_id, second[0])] = game["code"]


@client.on_message()
async def tictactoe_handler(_client, event):
    global _ttt_token
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False) or not text or len(text) > 40:
        return
    if chat_id not in _ttt_games and not (text.startswith("دوز") or text.startswith("لغو دوز")):
        return

    t = normalize_digits(text)
    sender_user = getattr(event, 'sender', None)
    me = (sender_id, sender_user)

    if t == "لغو دوز" or t.startswith("لغو دوز "):
        arg = t[len("لغو دوز"):].strip()
        chat = get_chat_cfg(chat_id)
        if arg.isdigit():
            game = _ttt_games.get(chat_id, {}).get(arg)
            if game and not is_admin(chat, sender_id) and sender_id not in game.get("members", ()):
                await safe_reply(event, "⛔️ فقط بازیکن‌ها یا ادمین‌ها می‌تونن این بازی رو لغو کنن.")
                return
        else:
            game = _ttt_lookup(chat_id, sender_id)
        if not game:
            return
        _ttt_drop(chat_id, game)
        await safe_reply(event, wrap_box("🏳️", "دوز", f"بازی دوز (کد {_fa(game['code'])}) لغو شد.\n💬 بازی جدید؟ بنویس «دوز»"))
        return

    digits, explicit = None, False
    if t.isdigit():
        digits = t
    elif t == "دوز" or t.startswith("دوز "):
        arg = t[len("دوز"):].strip()
        if arg.isdigit():
            digits, explicit = arg, True
    else:
        return

    if digits is not None:
        if len(digits) == 1 and digits != "0":
            game = _ttt_lookup(chat_id, sender_id)
            if not game or game["phase"] != "play":
                return
            sym = "X" if game["players"]["X"][0] == sender_id else "O"
            if game["turn"] != sym:
                await _game_quick_reply(event, "⏳ نوبت تو نیست؛ صبر کن حریفت بازی کنه")
                return
            cell = int(digits) - 1
            if game["board"][cell]:
                await _game_quick_reply(event, "⚠️ اون خونه پره؛ یکی دیگه رو انتخاب کن")
                return
            game["board"][cell] = sym
            game["ts"] = _game_now()
            winner, line = _ttt_winner(game["board"])
            if winner:
                _ttt_drop(chat_id, game)
                msg, ents = await _ttt_board_message(
                    game, "🏆 ", game["players"][winner], f" با {_TTT_MARK[winner]} برنده شد!\n"
                    "💬 بازی جدید؟ بنویس «دوز»", win=line)
                await safe_reply(event, msg, entities=ents)
                return
            if all(game["board"]):
                _ttt_drop(chat_id, game)
                msg, ents = await _ttt_board_message(
                    game, "🤝 مساوی شد! هیچ‌کس نبرد.\n💬 بازی جدید؟ بنویس «دوز»")
                await safe_reply(event, msg, entities=ents)
                return
            game["turn"] = "O" if sym == "X" else "X"
            msg, ents = await _ttt_board_message(
                game, f"🎯 نوبت {_TTT_MARK[game['turn']]} ", game["players"][game["turn"]],
                "\n✍️ شماره‌ی خونه (۱ تا ۹) رو بفرست")
            await _game_reply_ents(event, msg, ents)
            return

        if len(digits) != TTT_CODE_DIGITS:
            return
        game = _ttt_games.get(chat_id, {}).get(digits)
        if not game or game["phase"] != "open":
            if explicit:
                await safe_reply(event, "⚠️ بازی‌ای با این کد پیدا نشد (شاید پر شده یا تموم شده).")
            return
        if sender_id == game["creator"][0]:
            await _game_quick_reply(event, "😅 تو سازنده‌ی بازی هستی؛ این کد رو به بقیه بده")
            return
        if (chat_id, sender_id) in _ttt_players:
            await _game_quick_reply(event, "⚠️ تو الان توی یه بازی دوز هستی؛ اول اون رو تموم یا «لغو دوز» کن")
            return
        await _ttt_begin(chat_id, game, me)
        msg, ents = await _ttt_board_message(
            game, "🎲 قرعه انداخته شد!\n🎯 نوبت ❌ ", game["players"]["X"],
            "\n✍️ شماره‌ی خونه (۱ تا ۹) رو بفرست")
        await safe_reply(event, msg, entities=ents)
        return

    arg = t[len("دوز"):].strip()
    has_reply = bool(getattr(event, 'reply_to_msg_id', None) or getattr(event, 'reply_to', None))
    wants_target = has_reply or arg.startswith("@")
    if arg and not arg.startswith("@"):
        return

    existing = _ttt_lookup(chat_id, sender_id)
    if existing:
        if existing["phase"] != "open" or existing["creator"][0] != sender_id:
            await safe_reply(event, "⚠️ تو الان توی یه بازی دوز هستی؛ اول اون رو تموم یا «لغو دوز» کن.")
            return
        if not wants_target:
            msg, ents = await _ttt_lobby_message(existing)
            await safe_reply(event, msg, entities=ents)
            return

    target = None
    if wants_target:
        tid = await resolve_target(event, chat_id, arg)
        if not tid:
            await safe_reply(event, "⚠️ کاربر مورد نظر پیدا نشد. با ریپلای یا «دوز @یوزرنیم» امتحان کن.")
            return
        if tid == sender_id:
            await safe_reply(event, "⛔️ با خودت که نمی‌تونی دوز بازی کنی 😅")
            return
        if tid == await _ship_get_my_id():
            await safe_reply(event, "🤖 من اهل دوز نیستم؛ یه حریفِ آدمیزاد پیدا کن 😎")
            return
        if (chat_id, tid) in _ttt_players:
            await safe_reply(event, "⚠️ اون کاربر الان توی یه بازی دوز دیگه‌ست.")
            return
        try:
            target_user = await client.get_entity(tid)
        except Exception:
            target_user = None
        target = (tid, target_user)

    game = existing
    if game is None:
        if len(_ttt_games.get(chat_id, {})) >= TTT_MAX_GAMES_PER_CHAT:
            await safe_reply(event, "⚠️ الان خیلی بازی دوز فعاله؛ چند دقیقه‌ی دیگه امتحان کن.")
            return
        code = _ttt_new_code(chat_id)
        if not code:
            return
        _ttt_token += 1
        game = {
            "code": code, "token": _ttt_token, "phase": "open", "creator": me,
            "players": {}, "members": {sender_id}, "board": [None] * 9,
            "turn": "X", "ts": _game_now(), "task": None,
        }
        _ttt_games.setdefault(chat_id, {})[code] = game
        _ttt_players[(chat_id, sender_id)] = code
        game["task"] = asyncio.create_task(_ttt_watch(chat_id, game["token"], code))

    if target is None:
        msg, ents = await _ttt_lobby_message(game)
        await safe_reply(event, msg, entities=ents)
        return

    await _ttt_begin(chat_id, game, target)
    msg, ents = await _ttt_board_message(
        game, "🎲 قرعه انداخته شد!\n🎯 نوبت ❌ ", game["players"]["X"],
        "\n✍️ شماره‌ی خونه (۱ تا ۹) رو بفرست",
        intro=("🤠 ", game["creator"], " ", target, " رو به بازی آورد!\n\n"))
    await safe_reply(event, msg, entities=ents)


# ════════════════════════════════════════════════════════════════
#  ۷ بازی جدید: ریاضی · ایموجی فرق · اسلات · رولت · کوییز · رمز شکن · کلمه مخفی
# ════════════════════════════════════════════════════════════════

_G_LRM = "\u200e"
_g_token_counter = 0


def _g_next_token() -> int:
    global _g_token_counter
    _g_token_counter += 1
    return _g_token_counter


def _g_cancel(game) -> None:
    task = game.get("task") if game else None
    if task:
        task.cancel()


async def _g_end_allowed(event, chat_id, sender_id, starter) -> bool:
    """پایان‌دادن بازی فقط برای شروع‌کننده یا ادمین‌ها."""
    chat = get_chat_cfg(chat_id)
    if sender_id != starter and not is_admin(chat, sender_id):
        await safe_reply(event, "⛔️ فقط شروع‌کننده‌ی بازی یا ادمین‌ها می‌تونن بازی رو تموم کنن.")
        return False
    return True


# ─────────────── ۱) ریاضی سریع ───────────────

MATH_TOTAL_SECONDS = 30
_math_games: dict = {}


def _math_make_question():
    kind = random.choice(("add", "sub", "mul", "mix"))
    if kind == "add":
        a, b = random.randint(12, 99), random.randint(12, 99)
        return f"{a} + {b}", a + b
    if kind == "sub":
        a, b = random.randint(30, 150), random.randint(10, 29)
        return f"{a} - {b}", a - b
    if kind == "mul":
        a, b = random.randint(3, 12), random.randint(3, 15)
        return f"{a} × {b}", a * b
    a, b, c = random.randint(2, 9), random.randint(2, 9), random.randint(2, 9)
    return f"({a} + {b}) × {c}", (a + b) * c


async def _math_timer(chat_id, token) -> None:
    try:
        await asyncio.sleep(MATH_TOTAL_SECONDS)
        g = _math_games.get(chat_id)
        if not g or g["token"] != token:
            return
        _math_games.pop(chat_id, None)
        await _game_send(chat_id, wrap_box(
            "⏰", "ریاضی سریع",
            f"وقت تموم شد و کسی جواب نداد 😅\n✅ جواب: {_fa(g['answer'])}\n\n💬 دوباره؟ بنویس «ریاضی»"))
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ math timer error [{chat_id}]: {e}")


@client.on_message()
async def math_quiz_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False) or not text:
        return

    game = _math_games.get(chat_id)

    if text == "ریاضی":
        if game:
            await safe_reply(event, wrap_box(
                "🧮", "ریاضی سریع",
                f"یه سوال همین الان فعاله!\n\n❓ {_G_LRM}{game['q']} = ?\n\n✍️ جواب رو فقط به‌صورت عدد بنویس"))
            return
        q, ans = _math_make_question()
        token = _g_next_token()
        _math_games[chat_id] = {"q": q, "answer": ans, "token": token,
                                "started": _game_now(), "task": None}
        await safe_reply(event, wrap_box(
            "🧮", "ریاضی سریع",
            f"سریع حساب کن!\n\n❓ {_G_LRM}{q} = ?\n\n"
            f"⏳ {_fa(MATH_TOTAL_SECONDS)} ثانیه وقت داری • اولین جواب درست برنده‌ست"))
        g = _math_games.get(chat_id)
        if g and g["token"] == token:
            g["task"] = asyncio.create_task(_math_timer(chat_id, token))
        return

    if not game or len(text) > 8:
        return
    arg = normalize_digits(text).strip()
    if not re.fullmatch(r"-?\d+", arg) or int(arg) != game["answer"]:
        return

    _math_games.pop(chat_id, None)
    _g_cancel(game)
    secs = max(1, int(round(_game_now() - game["started"])))
    msg, ents = await _game_winner_text(
        event, "🎉 ",
        f" درست حساب کرد!\n🧮 {_G_LRM}{game['q']} = {game['answer']}\n⚡ زمان: {_fa(secs)} ثانیه\n\n"
        "💬 دوباره؟ بنویس «ریاضی»")
    await safe_reply(event, msg, entities=ents)


# ─────────────── ۲) ایموجی فرق ───────────────

EMOJI_ROWS = 4
EMOJI_COLS = 5
EMOJI_TOTAL_SECONDS = 45
_EMOJI_PAIRS = [
    ("🙂", "🙃"), ("😐", "😑"), ("🍎", "🍅"), ("🌕", "🌝"), ("🔵", "🟣"),
    ("😠", "😡"), ("⭐", "🌟"), ("😀", "😃"), ("🐵", "🐒"), ("🌑", "🌚"),
]
_emoji_games: dict = {}


def _emoji_render(grid) -> str:
    return "\n".join(_G_LRM + "".join(row) for row in grid)


async def _emoji_timer(chat_id, token) -> None:
    try:
        await asyncio.sleep(EMOJI_TOTAL_SECONDS)
        g = _emoji_games.get(chat_id)
        if not g or g["token"] != token:
            return
        _emoji_games.pop(chat_id, None)
        await _game_send(chat_id, wrap_box(
            "⏰", "ایموجی فرق",
            f"وقت تموم شد و کسی پیداش نکرد 😅\n✅ جای ایموجی متفاوت: ردیف {_fa(g['r'] + 1)} ستون {_fa(g['c'] + 1)}\n\n"
            "💬 دوباره؟ بنویس «ایموجی فرق»"))
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ emoji timer error [{chat_id}]: {e}")


@client.on_message()
async def emoji_odd_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False) or not text:
        return

    game = _emoji_games.get(chat_id)

    if text == "ایموجی فرق":
        if game:
            await safe_reply(event, wrap_box(
                "👁", "ایموجی فرق",
                f"یه بازی همین الان فعاله!\n\n{game['render']}\n\n✍️ جواب: «ردیف ستون»، مثلاً: ۲ ۳"))
            return
        base, odd = random.choice(_EMOJI_PAIRS)
        if random.random() < 0.5:
            base, odd = odd, base
        r, c = random.randrange(EMOJI_ROWS), random.randrange(EMOJI_COLS)
        grid = [[base] * EMOJI_COLS for _ in range(EMOJI_ROWS)]
        grid[r][c] = odd
        token = _g_next_token()
        render = _emoji_render(grid)
        _emoji_games[chat_id] = {"r": r, "c": c, "render": render, "token": token,
                                 "started": _game_now(), "task": None}
        await safe_reply(event, wrap_box(
            "👁", "ایموجی فرق",
            f"بین این ایموجی‌ها فقط یکی فرق داره!\n\n{render}\n\n"
            f"✍️ جاش رو «ردیف ستون» بنویس، مثلاً: {_fa(2)} {_fa(3)}\n"
            f"📐 {_fa(EMOJI_ROWS)} ردیف و {_fa(EMOJI_COLS)} ستون (از بالا و از راست حساب کن)\n"
            f"⏳ {_fa(EMOJI_TOTAL_SECONDS)} ثانیه وقت داری"))
        g = _emoji_games.get(chat_id)
        if g and g["token"] == token:
            g["task"] = asyncio.create_task(_emoji_timer(chat_id, token))
        return

    if not game or len(text) > 6:
        return
    m = re.fullmatch(r"([1-9])\s*[-–/،,.:\s]?\s*([1-9])", normalize_digits(text).strip())
    if not m:
        return
    if int(m.group(1)) - 1 != game["r"] or int(m.group(2)) - 1 != game["c"]:
        return

    _emoji_games.pop(chat_id, None)
    _g_cancel(game)
    secs = max(1, int(round(_game_now() - game["started"])))
    msg, ents = await _game_winner_text(
        event, "🎉 ",
        f" ایموجی متفاوت رو پیدا کرد!\n📍 ردیف {_fa(game['r'] + 1)} • ستون {_fa(game['c'] + 1)}\n"
        f"⚡ زمان: {_fa(secs)} ثانیه\n\n💬 دوباره؟ بنویس «ایموجی فرق»")
    await safe_reply(event, msg, entities=ents)


# ─────────────── ۳) اسلات ───────────────

_SLOT_SYMBOLS = ["🍒", "🍋", "🍉", "🔔", "⭐", "💎", "7️⃣"]
_SLOT_WEIGHTS = [26, 24, 20, 14, 9, 5, 2]


@client.on_message()
async def slot_machine_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False):
        return
    if text != "اسلات":
        return

    reels = random.choices(_SLOT_SYMBOLS, weights=_SLOT_WEIGHTS, k=3)
    if reels[0] == reels[1] == reels[2]:
        if reels[0] == "7️⃣":
            verdict = "🤑 جکپات افسانه‌ای! سه تا هفت!"
        elif reels[0] == "💎":
            verdict = "💎 جکپات الماس! خیلی خوش‌شانسی!"
        else:
            verdict = "🏆 جکپات! سه‌تا مثل هم شد!"
    elif len(set(reels)) == 2:
        verdict = "😮 یکی مونده بود! دو تاش یکی شد"
    else:
        verdict = "😅 این دفعه نشد؛ یه بار دیگه بچرخون"
    await safe_reply(event, wrap_box(
        "🎰", "اسلات",
        f"{_G_LRM}[ {reels[0]} | {reels[1]} | {reels[2]} ]\n\n{verdict}"))


# ─────────────── ۴) رولت روسی ───────────────

ROULETTE_CHAMBERS = 6
ROULETTE_IDLE_SECONDS = 10 * 60
_roulette_games: dict = {}


@client.on_message()
async def roulette_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False) or not text:
        return
    if text not in ("رولت", "ماشه", "پایان رولت"):
        return

    now = _game_now()
    game = _roulette_games.get(chat_id)
    if game and now - game["ts"] > ROULETTE_IDLE_SECONDS:
        _roulette_games.pop(chat_id, None)
        game = None

    if text == "رولت":
        if game:
            await safe_reply(event, wrap_box(
                "🔫", "رولت",
                f"یه بازی همین الان فعاله!\n🔄 {_fa(game['pulls'])} بار ماشه کشیده شده\n"
                "✍️ برای کشیدن ماشه بنویس «ماشه»"))
            return
        _roulette_games[chat_id] = {
            "bullet": random.randrange(ROULETTE_CHAMBERS), "pulls": 0,
            "last": None, "starter": sender_id, "ts": now,
        }
        await safe_reply(event, wrap_box(
            "🔫", "رولت",
            f"یه فشنگ توی یکی از {_fa(ROULETTE_CHAMBERS)} خونه‌ی اسلحه گذاشتم و چرخوندمش 😈\n\n"
            "✍️ هرکی جرئت داره بنویسه «ماشه»\n"
            "🔁 پشت سر هم دو بار نمی‌تونی بکشی؛ نوبتی بازی کنین\n"
            "☠️ هرکی تیر بخوره، بازنده‌ست!"))
        return

    if text == "پایان رولت":
        if not game:
            return
        if not await _g_end_allowed(event, chat_id, sender_id, game["starter"]):
            return
        _roulette_games.pop(chat_id, None)
        await safe_reply(event, wrap_box(
            "🏁", "رولت",
            f"بازی تموم شد؛ فشنگ توی خونه‌ی {_fa(game['bullet'] + 1)} بود.\n💬 بازی جدید؟ بنویس «رولت»"))
        return

    # text == "ماشه"
    if not game:
        return
    if game["last"] == sender_id:
        await _game_quick_reply(event, "✋ نوبتت نیست؛ بذار یکی دیگه ماشه رو بکشه!")
        return
    game["last"] = sender_id
    game["ts"] = now
    idx = game["pulls"]
    game["pulls"] += 1

    if idx == game["bullet"]:
        _roulette_games.pop(chat_id, None)
        msg, ents = await _game_winner_text(
            event, "💥 بوووم! ",
            f" تیر خورد و بازی رو باخت 😵\n🔫 فشنگ توی خونه‌ی {_fa(idx + 1)} بود\n\n"
            "💬 دوباره؟ بنویس «رولت»")
        await safe_reply(event, msg, entities=ents)
        return

    left = ROULETTE_CHAMBERS - game["pulls"]
    if left == 1:
        note = "☠️ فشنگ دقیقاً توی خونه‌ی آخره! نفر بعدی قطعاً می‌میره"
    else:
        note = f"😬 فشنگ توی یکی از {_fa(left)} خونه‌ی باقی‌مونده‌ست"
    await _game_quick_reply(event, f"🔫 کلیک... خالی بود! زنده موندی 😮‍💨\n{note}")


# ─────────────── ۵) کوییز ───────────────

QUIZ_HINT_SECONDS = 25
QUIZ_TOTAL_SECONDS = 45

# (سوال، [جواب‌های قابل‌قبول])
QUIZ_QUESTIONS = [
    ("پایتخت ترکیه کدوم شهره؟", ["آنکارا", "انکارا"]),
    ("بلندترین قله‌ی جهان چیه؟", ["اورست"]),
    ("کدوم سیاره به «سیاره‌ی سرخ» معروفه؟", ["مریخ"]),
    ("بزرگ‌ترین اقیانوس جهان کدومه؟", ["آرام", "اقیانوس آرام", "پاسفیک"]),
    ("فرمول شیمیایی آب چیه؟", ["H2O"]),
    ("شاعر «شاهنامه» کیه؟", ["فردوسی", "حکیم ابوالقاسم فردوسی"]),
    ("نویسنده‌ی «بوف کور» کیه؟", ["هدایت", "صادق هدایت"]),
    ("پایتخت ژاپن کدوم شهره؟", ["توکیو", "طوکیو"]),
    ("بزرگ‌ترین حیوان خشکی کدومه؟", ["فیل", "فیل آفریقایی"]),
    ("یه دقیقه چند ثانیه‌ست؟", ["60", "شصت"]),
    ("سریع‌ترین حیوان خشکی کدومه؟", ["یوزپلنگ", "یوز"]),
    ("نزدیک‌ترین سیاره به خورشید کدومه؟", ["عطارد", "تیر"]),
    ("نماد شیمیایی طلا چیه؟", ["Au"]),
    ("نماد شیمیایی نقره چیه؟", ["Ag"]),
    ("زبان رسمی برزیل چیه؟", ["پرتغالی"]),
    ("بلندترین رودخانه‌ی ایران کدومه؟", ["کارون"]),
    ("بزرگ‌ترین دریاچه‌ی ایران کدومه؟", ["ارومیه", "دریاچه ارومیه"]),
    ("بلندترین قله‌ی ایران کدومه؟", ["دماوند", "قله دماوند"]),
    ("تخت جمشید توی کدوم استان قرار داره؟", ["فارس"]),
    ("کوچک‌ترین عدد اول چنده؟", ["2", "دو"]),
    ("نقاشی معروف «مونالیزا» اثر کدوم نقاشه؟", ["داوینچی", "لئوناردو داوینچی", "لئوناردو"]),
    ("کدوم سیاره به خاطر حلقه‌هاش معروفه؟", ["زحل"]),
    ("توی زمین فوتبال از هر تیم چند نفر (با دروازه‌بان) بازی می‌کنن؟", ["11", "یازده"]),
    ("پایتخت فرانسه کدوم شهره؟", ["پاریس"]),
    ("پایتخت استرالیا کدوم شهره؟", ["کانبرا"]),
    ("نویسنده‌ی «گلستان» کیه؟", ["سعدی", "سعدی شیرازی"]),
    ("«مثنوی معنوی» اثر کیه؟", ["مولوی", "مولانا"]),
    ("بزرگ‌ترین سیاره‌ی منظومه‌ی شمسی کدومه؟", ["مشتری"]),
    ("توی رنگین‌کمان معمولاً چند رنگ می‌شمارن؟", ["7", "هفت"]),
    ("کدوم گاز برای تنفس ما ضروریه؟", ["اکسیژن"]),
    ("الفبای فارسی چند حرف داره؟", ["32", "سی و دو"]),
    ("پایتخت ایتالیا کدوم شهره؟", ["رم"]),
    ("پایتخت آلمان کدوم شهره؟", ["برلین"]),
    ("بزرگ‌ترین قاره‌ی جهان کدومه؟", ["آسیا"]),
    ("سال کبیسه‌ی میلادی چند روزه‌ست؟", ["366"]),
    ("اولین ماه سال شمسی چیه؟", ["فروردین"]),
    ("مخترع تلفن (معروف‌ترین) کیه؟", ["بل", "گراهام بل", "الکساندر گراهام بل"]),
    ("نظریه‌ی نسبیت از کدوم دانشمنده؟", ["اینشتین", "انیشتین", "آلبرت اینشتین"]),
    ("اولین انسانی که روی ماه قدم گذاشت کی بود؟", ["آرمسترانگ", "نیل آرمسترانگ"]),
    ("فصل بعد از تابستان چیه؟", ["پاییز"]),
]

_quiz_games: dict = {}
_quiz_recent: dict = {}


def _quiz_norm(s: str) -> str:
    return _game_norm_text(normalize_digits(s or "")).lower()


def _quiz_pick(chat_id):
    recent = _quiz_recent.setdefault(chat_id, deque(maxlen=12))
    pool = [i for i in range(len(QUIZ_QUESTIONS)) if i not in recent] or list(range(len(QUIZ_QUESTIONS)))
    idx = random.choice(pool)
    recent.append(idx)
    return QUIZ_QUESTIONS[idx]


async def _quiz_timer(chat_id, token) -> None:
    try:
        await asyncio.sleep(QUIZ_HINT_SECONDS)
        g = _quiz_games.get(chat_id)
        if not g or g["token"] != token:
            return
        first = g["answers"][0]
        await _game_send(chat_id, f"💡 راهنمایی: جواب با «{first[0]}» شروع می‌شه")
        await asyncio.sleep(QUIZ_TOTAL_SECONDS - QUIZ_HINT_SECONDS)
        g = _quiz_games.get(chat_id)
        if not g or g["token"] != token:
            return
        _quiz_games.pop(chat_id, None)
        await _game_send(chat_id, wrap_box(
            "⏰", "کوییز",
            f"وقت تموم شد و کسی جواب درست رو نگفت 😅\n✅ جواب: {first}\n\n💬 دوباره؟ بنویس «کوییز»"))
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log(f"⚠️ quiz timer error [{chat_id}]: {e}")


@client.on_message()
async def quiz_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False) or not text:
        return

    game = _quiz_games.get(chat_id)

    if text in ("کوییز", "کوئیز"):
        if game:
            await safe_reply(event, wrap_box(
                "🧠", "کوییز", f"یه سوال همین الان فعاله!\n\n❓ {game['q']}"))
            return
        q, answers = _quiz_pick(chat_id)
        token = _g_next_token()
        _quiz_games[chat_id] = {
            "q": q, "answers": answers, "norms": {_quiz_norm(a) for a in answers},
            "token": token, "started": _game_now(), "task": None,
        }
        await safe_reply(event, wrap_box(
            "🧠", "کوییز",
            f"❓ {q}\n\n✍️ جواب رو توی گپ بنویس\n"
            f"⏳ {_fa(QUIZ_TOTAL_SECONDS)} ثانیه وقت داری • اولین جواب درست برنده‌ست"))
        g = _quiz_games.get(chat_id)
        if g and g["token"] == token:
            g["task"] = asyncio.create_task(_quiz_timer(chat_id, token))
        return

    if not game or len(text) > 40:
        return
    if _quiz_norm(text) not in game["norms"]:
        return

    _quiz_games.pop(chat_id, None)
    _g_cancel(game)
    secs = max(1, int(round(_game_now() - game["started"])))
    msg, ents = await _game_winner_text(
        event, "🎉 ",
        f" درست جواب داد!\n✅ جواب: {game['answers'][0]}\n⚡ زمان: {_fa(secs)} ثانیه\n\n"
        "💬 سوال بعدی؟ بنویس «کوییز»")
    await safe_reply(event, msg, entities=ents)


# ─────────────── ۶) رمز شکن ───────────────

CODE_DIGITS = 4
CODE_MAX_TRIES = 15
CODE_IDLE_SECONDS = 15 * 60
_code_games: dict = {}


def _code_new_secret() -> str:
    digits = random.sample("0123456789", CODE_DIGITS)
    if digits[0] == "0":
        for i in range(1, CODE_DIGITS):
            if digits[i] != "0":
                digits[0], digits[i] = digits[i], digits[0]
                break
    return "".join(digits)


def _code_score(secret: str, guess: str):
    green = sum(1 for a, b in zip(secret, guess) if a == b)
    common = len(set(secret) & set(guess))
    return green, common - green


def _code_history_text(game, last: int = 6) -> str:
    rows = [f"{_G_LRM}{g}   🟢 {gr}   🟡 {ye}" for g, gr, ye in game["history"][-last:]]
    return "\n".join(rows)


@client.on_message()
async def code_breaker_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False) or not text:
        return
    if not (text in ("رمز شکن", "پایان رمز شکن") or text.startswith("رمز ")):
        return

    now = _game_now()
    game = _code_games.get(chat_id)
    if game and now - game["ts"] > CODE_IDLE_SECONDS:
        _code_games.pop(chat_id, None)
        if text != "رمز شکن":
            await safe_reply(event, wrap_box(
                "⌛", "رمز شکن",
                f"بازی قبلی منقضی شد؛ رمز {game['secret']} بود.\n💬 برای بازی جدید بنویس «رمز شکن»"))
            return
        game = None

    if text == "رمز شکن":
        if game:
            await safe_reply(event, wrap_box(
                "🔐", "رمز شکن",
                f"یه بازی همین الان فعاله!\n🔢 رمز {_fa(CODE_DIGITS)} رقمیه • {_fa(game['tries'])} حدس زده شده\n"
                f"✍️ حدست رو این‌طور بنویس: رمز {_fa(1234)}"
                + (f"\n\n{_code_history_text(game)}" if game["history"] else "")))
            return
        _code_games[chat_id] = {"secret": _code_new_secret(), "tries": 0, "history": [],
                                "starter": sender_id, "ts": now}
        await safe_reply(event, wrap_box(
            "🔐", "رمز شکن",
            f"یه رمز {_fa(CODE_DIGITS)} رقمی با رقم‌های غیرتکراری ساختم!\n\n"
            f"✍️ حدست رو این‌طور بنویس: رمز {_fa(1234)}\n"
            "🟢 = رقم درست و سر جاش\n"
            "🟡 = رقم درسته ولی جاش غلطه\n"
            f"🎯 {_fa(CODE_MAX_TRIES)} فرصت دارین؛ همه با هم بازی می‌کنین"))
        return

    if text == "پایان رمز شکن":
        if not game:
            return
        if not await _g_end_allowed(event, chat_id, sender_id, game["starter"]):
            return
        _code_games.pop(chat_id, None)
        await safe_reply(event, wrap_box(
            "🏁", "رمز شکن",
            f"بازی تموم شد؛ رمز {game['secret']} بود.\n💬 بازی جدید؟ بنویس «رمز شکن»"))
        return

    if not game:
        return
    arg = normalize_digits(text[len("رمز "):]).strip()
    if not arg.isdigit():
        return
    if len(arg) != CODE_DIGITS or len(set(arg)) != CODE_DIGITS:
        await _game_quick_reply(
            event, f"⚠️ باید {_fa(CODE_DIGITS)} رقم بنویسی و رقم‌ها تکراری نباشن (مثلاً رمز {_fa(1234)})")
        return

    game["ts"] = now
    game["tries"] += 1
    green, yellow = _code_score(game["secret"], arg)
    game["history"].append((arg, _fa(green), _fa(yellow)))

    if green == CODE_DIGITS:
        _code_games.pop(chat_id, None)
        msg, ents = await _game_winner_text(
            event, "🎉 ",
            f" رمز رو شکست!\n🔐 رمز {game['secret']} بود • تعداد حدس‌ها: {_fa(game['tries'])}\n\n"
            "💬 بازی دوباره؟ بنویس «رمز شکن»")
        await safe_reply(event, msg, entities=ents)
        return

    if game["tries"] >= CODE_MAX_TRIES:
        _code_games.pop(chat_id, None)
        await safe_reply(event, wrap_box(
            "💀", "رمز شکن",
            f"فرصت‌ها تموم شد و رمز شکسته نشد!\n🔐 رمز {game['secret']} بود\n\n💬 دوباره؟ بنویس «رمز شکن»"))
        return

    left = CODE_MAX_TRIES - game["tries"]
    await _game_quick_reply(
        event, f"{_code_history_text(game)}\n\n🎯 {_fa(left)} فرصت باقی مونده")


# ─────────────── ۷) کلمه مخفی ───────────────

HANG_LIVES = 6
HANG_IDLE_SECONDS = 15 * 60
_hang_games: dict = {}


def _hang_board(g) -> str:
    return " ".join(ch if g["shown"][i] else "▫️" for i, ch in enumerate(g["word"]))


def _hang_hearts(g) -> str:
    return "❤️" * g["lives"] + "🖤" * (HANG_LIVES - g["lives"])


@client.on_message()
async def hidden_word_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False) or not text:
        return

    now = _game_now()
    game = _hang_games.get(chat_id)
    if game and now - game["ts"] > HANG_IDLE_SECONDS:
        _hang_games.pop(chat_id, None)
        if text != "کلمه مخفی":
            await safe_reply(event, wrap_box(
                "⌛", "کلمه مخفی",
                f"بازی قبلی منقضی شد؛ کلمه «{game['word']}» بود.\n💬 برای بازی جدید بنویس «کلمه مخفی»"))
            return
        game = None

    if text == "کلمه مخفی":
        if game:
            await safe_reply(event, wrap_box(
                "🪢", "کلمه مخفی",
                f"یه بازی همین الان فعاله!\n\n🧩 {_hang_board(game)}\n{_hang_hearts(game)}\n"
                "✍️ حرف بزن: «حرف ب» • یا کل کلمه رو بنویس"))
            return
        pool = [w for w in SCRAMBLE_WORDS if len(w) >= 4]
        word = random.choice(pool)
        _hang_games[chat_id] = {
            "word": word, "norm": _game_norm_text(word),
            "letters": [_game_norm_text(c) for c in word],
            "shown": [False] * len(word), "tried": set(), "wrong": [],
            "lives": HANG_LIVES, "starter": sender_id, "ts": now,
        }
        g = _hang_games[chat_id]
        await safe_reply(event, wrap_box(
            "🪢", "کلمه مخفی",
            f"یه کلمه‌ی {_fa(len(word))} حرفی انتخاب کردم!\n\n🧩 {_hang_board(g)}\n{_hang_hearts(g)}\n\n"
            "✍️ حرف بزن: «حرف ب» • یا مستقیم کل کلمه رو بنویس\n"
            f"💔 با هر حرف اشتباه یه جون از {_fa(HANG_LIVES)} جون کم می‌شه"))
        return

    if text == "پایان کلمه مخفی":
        if not game:
            return
        if not await _g_end_allowed(event, chat_id, sender_id, game["starter"]):
            return
        _hang_games.pop(chat_id, None)
        await safe_reply(event, wrap_box(
            "🏁", "کلمه مخفی",
            f"بازی تموم شد؛ کلمه «{game['word']}» بود.\n💬 بازی جدید؟ بنویس «کلمه مخفی»"))
        return

    if not game:
        return

    # حدس کل کلمه
    if len(text) <= 30 and not text.startswith("حرف ") and _game_norm_text(text) == game["norm"]:
        _hang_games.pop(chat_id, None)
        msg, ents = await _game_winner_text(
            event, "🎉 ",
            f" کلمه رو پیدا کرد!\n✅ کلمه: {game['word']}\n\n💬 دوباره؟ بنویس «کلمه مخفی»")
        await safe_reply(event, msg, entities=ents)
        return

    if not text.startswith("حرف "):
        return
    letter = _game_norm_text(text[len("حرف "):])
    if len(letter) != 1 or not letter.isalpha():
        return

    game["ts"] = now
    if letter in game["tried"]:
        await _game_quick_reply(event, f"⚠️ حرف «{letter}» قبلاً گفته شده")
        return
    game["tried"].add(letter)

    if letter in game["letters"]:
        for i, ch in enumerate(game["letters"]):
            if ch == letter:
                game["shown"][i] = True
        if all(game["shown"]):
            _hang_games.pop(chat_id, None)
            msg, ents = await _game_winner_text(
                event, "🎉 ",
                f" آخرین حرف رو گفت و کلمه کامل شد!\n✅ کلمه: {game['word']}\n\n"
                "💬 دوباره؟ بنویس «کلمه مخفی»")
            await safe_reply(event, msg, entities=ents)
            return
        head = f"✅ حرف «{letter}» توی کلمه هست!"
    else:
        game["lives"] -= 1
        game["wrong"].append(letter)
        if game["lives"] <= 0:
            _hang_games.pop(chat_id, None)
            await safe_reply(event, wrap_box(
                "💀", "کلمه مخفی",
                f"جون‌ها تموم شد و کلمه پیدا نشد!\n✅ کلمه «{game['word']}» بود\n\n"
                "💬 دوباره؟ بنویس «کلمه مخفی»"))
            return
        head = f"❌ حرف «{letter}» توی کلمه نیست!"

    wrong = f"\n🚫 اشتباه‌ها: {' '.join(game['wrong'])}" if game["wrong"] else ""
    await _game_quick_reply(
        event, f"{head}\n\n🧩 {_hang_board(game)}\n{_hang_hearts(game)}{wrong}")


_TIME_TRIGGERS = {"امروزچندمه", "ساعتچنده", "ساعت", "زمان", "تقویم", "امروزچهروزیه", "امروزچهروزیهست"}
_TIME_WEEKDAYS_FA = {
    0: "دوشنبه", 1: "سه‌شنبه", 2: "چهارشنبه", 3: "پنجشنبه", 4: "جمعه", 5: "شنبه", 6: "یکشنبه",
}
_TIME_GREG_MONTHS_FA = [
    "ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
    "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
]
_TIME_CAL_HEADER = ["ش", "ی", "د", "س", "چ", "پ", "ج"]
_LRM = "\u200e"


_TIME_OCCASIONS = [
    (1, 1, "جشن نوروز و آغاز سال نو", True), (1, 2, "عید نوروز", True),
    (1, 3, "عید نوروز", True), (1, 4, "عید نوروز", True),
    (1, 6, "روز امید و شادباش‌نویسی", False), (1, 12, "روز جمهوری اسلامی", True),
    (1, 13, "روز طبیعت (سیزده‌به‌در)", True), (1, 25, "بزرگداشت عطار نیشابوری", False),
    (1, 29, "روز ارتش", False),
    (2, 1, "بزرگداشت سعدی", False), (2, 10, "روز ملی خلیج فارس", False),
    (2, 12, "روز معلم", False), (2, 25, "بزرگداشت فردوسی", False), (2, 28, "بزرگداشت خیام", False),
    (3, 3, "فتح خرمشهر", False), (3, 14, "رحلت امام خمینی", True), (3, 15, "قیام ۱۵ خرداد", True),
    (4, 1, "روز اصناف", False), (4, 7, "روز قوه قضاییه", False), (4, 10, "روز صنعت و معدن", False),
    (5, 14, "سالروز صدور فرمان مشروطیت", False), (5, 17, "روز خبرنگار", False),
    (5, 26, "بازگشت آزادگان به وطن", False), (5, 28, "سالروز کودتای ۲۸ مرداد", False),
    (6, 1, "روز پزشک (بزرگداشت ابوعلی سینا)", False), (6, 4, "روز کارمند", False),
    (6, 5, "روز داروساز (بزرگداشت رازی)", False), (6, 12, "روز مبارزه با استعمار انگلیس", False),
    (6, 17, "واقعه ۱۷ شهریور", False), (6, 27, "روز شعر و ادب پارسی (بزرگداشت شهریار)", False),
    (6, 31, "آغاز هفته دفاع مقدس", False),
    (7, 5, "روز جهانی گردشگری", False), (7, 7, "روز آتش‌نشانی و ایمنی", False),
    (7, 8, "بزرگداشت مولوی", False),
    (8, 1, "روز آمار و برنامه‌ریزی (بزرگداشت بیهقی)", False), (8, 13, "روز دانش‌آموز", False),
    (9, 5, "روز بسیج", False), (9, 7, "روز نیروی دریایی", False), (9, 16, "روز دانشجو", False),
    (9, 30, "شب یلدا", False),
    (10, 9, "روز بصیرت", False),
    (11, 12, "بازگشت امام خمینی (آغاز دهه فجر)", False), (11, 22, "پیروزی انقلاب اسلامی", True),
    (12, 5, "روز مهندس", False), (12, 14, "روز احسان و نیکوکاری", False),
    (12, 15, "روز درختکاری", False), (12, 29, "روز ملی شدن صنعت نفت", True),
]
_TIME_OCCASION_MAP: dict = {}
for _m, _d, _title, _hol in _TIME_OCCASIONS:
    _TIME_OCCASION_MAP.setdefault((_m, _d), []).append((_title, _hol))


def _time_next_occasion(today):
    """نزدیک‌ترین مناسبت ملیِ بعد از امروز → (چند روز دیگه, عنوان) یا None. today یه date میلادیه."""
    for k in range(1, 367):
        d = today + timedelta(days=k)
        _, jm, jd = _gregorian_to_jalali(d.year, d.month, d.day)
        items = _TIME_OCCASION_MAP.get((jm, jd))
        if items:
            return k, " · ".join(dict.fromkeys(title for title, _ in items))
    return None



def _time_part_of_day(hour: int) -> str:
    if hour < 5:
        return "🌌 نیمه‌شب"
    if hour < 12:
        return "🌅 صبح"
    if hour < 14:
        return "🌞 ظهر"
    if hour < 17:
        return "☀️ بعدازظهر"
    if hour < 20:
        return "🌇 عصر"
    return "🌙 شب"


def _time_calendar_text(t) -> str:
    """تقویمِ ماهِ شمسیِ t (شنبه اولِ هفته، مثل تقویم ایرانی)؛ روزِ امروز داخل [ ] میاد.
    هر خانه ۴ کاراکتره و هر خط با LRM شروع می‌شه تا ترتیب ستون‌ها توی متن فارسی برعکس نشه."""
    jy, jm, jd = _gregorian_to_jalali(t.year, t.month, t.day)
    first = (t - timedelta(days=jd - 1)).date()
    length = 29
    for k in range(28, 32):
        nxt = first + timedelta(days=k)
        if _gregorian_to_jalali(nxt.year, nxt.month, nxt.day)[1] != jm:
            length = k
            break
    offset = (first.weekday() + 2) % 7
    lines = [_LRM + "".join(f"  {c}{_LRM} " for c in _TIME_CAL_HEADER)]
    cells = ["    "] * offset
    for d in range(1, length + 1):
        num = to_persian_digits(str(d)).rjust(2)
        cells.append(f"[{num}]" if d == jd else f" {num} ")
    while len(cells) % 7:
        cells.append("    ")
    for i in range(0, len(cells), 7):
        lines.append(_LRM + "".join(cells[i:i + 7]).rstrip())
    return "\n".join(lines)


async def build_time_message(now_utc):
    """پیام کامل تاریخ/ساعت/مناسبت/تقویم به وقت تهران → (text, entities)؛ now_utc یه datetime آگاه به منطقه‌ی زمانیه."""
    t = now_utc.astimezone(IRAN_TZ)
    jy, jm, jd = _gregorian_to_jalali(t.year, t.month, t.day)
    weekday = _TIME_WEEKDAYS_FA[t.weekday()]

    items = _TIME_OCCASION_MAP.get((jm, jd), [])
    today_line = "📌 مناسبت ملی امروز: " + (" · ".join(dict.fromkeys(title for title, _ in items)) if items else "ندارد")
    if any(hol for _, hol in items):
        status = "\n🔴 امروز تعطیل رسمیه"
    elif t.weekday() == 4:
        status = "\n🔴 جمعه؛ تعطیل هفتگی"
    else:
        status = ""
    nxt = _time_next_occasion(t.date())
    next_line = ""
    if nxt:
        days, title = nxt
        when = "فردا" if days == 1 else f"{_fa(days)} روز دیگه"
        next_line = f"\n⏭ مناسبت ملی بعدی: {title} ({when})"

    return await _game_box_compose(
        "🕰", "تاریخ و ساعت",
        f"📅 امروز {weekday} {_fa(jd)} {_JALALI_MONTHS[jm - 1]} {_fa(jy)}\n"
        f"🕒 ساعت {_fa(f'{t.hour:02d}:{t.minute:02d}:{t.second:02d}')}\n"
        f"{_time_part_of_day(t.hour)}\n\n"
        f"{today_line}{status}{next_line}\n\n"
        f"🗓 تقویم {_JALALI_MONTHS[jm - 1]} {_fa(jy)}\n",
        _GCode(_time_calendar_text(t)),
        f"\n\n🌍 {_fa(t.day)} {_TIME_GREG_MONTHS_FA[t.month - 1]} {_fa(t.year)} میلادی\n"
        f"📍 به وقت تهران")


@client.on_message()
async def time_now_handler(_client, event):
    text = (getattr(event, 'raw_text', '') or '').strip()
    chat_id = getattr(event, 'chat_id', None)
    sender_id = getattr(event, 'sender_id', None)
    if not chat_id or not sender_id or getattr(event, 'is_private', False) or not text or len(text) > 30:
        return
    if _game_norm_text(text).rstrip("؟?!.") not in _TIME_TRIGGERS:
        return
    msg, ents = await build_time_message(_accurate_now(event))
    await safe_reply(event, msg, entities=ents)


# ======================= Render Keep-Alive =======================
# 1) یک وب‌سرور خیلی سبک روی PORT که Render می‌دهد باز می‌کند (رفع "Port scan timeout / no open ports")
# 2) هر ۴ دقیقه به آدرس خود سرویس پینگ می‌زند تا Render سرویس را نخواباند
_KEEPALIVE_PORT = int(os.environ.get("PORT", "10000"))
_KEEPALIVE_INTERVAL = 240
_keepalive_tasks = []
_keepalive_server = None


async def _keepalive_http_handler(reader, writer):
    try:
        try:
            await asyncio.wait_for(reader.read(2048), timeout=5)
        except Exception:
            pass
        body = b"OK"
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n" + body
        )
        await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


def _keepalive_ping_once(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "keepalive/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status
    except Exception as e:
        return f"error: {e}"


async def _keepalive_ping_loop():
    url = (os.environ.get("KEEPALIVE_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").strip()
    if not url:
        _log("ℹ️ Keep-alive: RENDER_EXTERNAL_URL پیدا نشد؛ پینگ داخلی غیرفعال (وب‌سرور همچنان فعال است).")
        return
    await asyncio.sleep(30)
    loop = asyncio.get_running_loop()
    while True:
        try:
            await loop.run_in_executor(None, _keepalive_ping_once, url)
        except Exception:
            pass
        await asyncio.sleep(_KEEPALIVE_INTERVAL)


async def start_keepalive():
    global _keepalive_server
    try:
        _keepalive_server = await asyncio.start_server(
            _keepalive_http_handler, host="0.0.0.0", port=_KEEPALIVE_PORT
        )
        _log(f"🌐 Keep-alive web server روی پورت {_KEEPALIVE_PORT} فعال شد.")
    except Exception as e:
        _log(f"⚠️ Keep-alive server start error: {e}")
    _keepalive_tasks.append(asyncio.ensure_future(_keepalive_ping_loop()))


async def main():
    await start_keepalive()
    _log_conn("🔌 Connecting...")
    _log(f"⚙️  کتابخانه‌های سرعت: {_speed_libs_status()}")
    _ucp_cls = _get_update_channel_participant_cls()
    _log(f"⚙️  UpdateChannelParticipant (قفل ممبر دزد روی گروه‌های بزرگ): "
          f"{'✅ پیدا شد' if _ucp_cls else '❌ پیدا نشد - این کتابخانه شاید اسم دیگری برایش دارد'}")
    check_system_clock_sanity()
    await client.connect()

    if not await client.is_user_authorized():
        _log_conn("📱 Sending code...")
        res = await client.send_code_request(PHONE_NUMBER)
        code = input("Code: ")
        hash_val = getattr(res, 'phone_code_hash', None) or (res.get('phone_code_hash') if isinstance(res, dict) else None)

        if hash_val:
            await client.sign_in(PHONE_NUMBER, code, phone_code_hash=hash_val)
        else:
            await client.sign_in(PHONE_NUMBER, code)

    me = await client.get_me()
    _log_conn(f"✅ Logged in as {me.first_name}")

    _log(f"\n📋 Settings ({len(config.get('chats', {}))} گروه ثبت‌شده):")
    for chat_id_str, chat in config.get("chats", {}).items():
        _log(f"   [{chat_id_str}] admins={len(chat.get('admins', []))} "
              f"owner={chat.get('group_owner')} "
              f"bio_words={len(chat.get('bio_filter_words', []))} "
              f"name_words={len(chat.get('name_filter_words', []))} "
              f"anti_khale={chat.get('anti_khale_enabled')} "
              f"anti_jagh={chat.get('anti_jagh_lock_enabled')} "
              f"member_stealer={chat.get('member_stealer_lock_enabled')} "
              f"locks={format_locks_status(chat.get('locks', {}))}")

    any_bio_or_khale = any(
        c.get("bio_filter_words") or c.get("anti_khale_enabled")
        or c.get("member_stealer_lock_enabled") or c.get("locks", {}).get("spam")
        or c.get("anti_ad_lock_enabled")
        for c in config.get("chats", {}).values()
    )
    if any_bio_or_khale:
        ensure_cleanup_task_running()

    ensure_scheduler_running()
    ensure_ship_task_running()
    ensure_join_poll_task_running()

    _log("\n🤖 Bot is running.")
    _log("💡 دستورات فیلتر بیو:")
    _log("   - فیلتر بیو کاربر <کلمه> / لیست بیو / ریست لیست بیو")
    _log("   - تنظیم مجازات بیو عادی / سکوت / سکوت یک ساعت / بن")
    _log("💡 دستورات فیلتر اسم:")
    _log("   - فیلتر اسم <کلمه> / لیست اسم / ریست لیست اسم")
    _log("   - تنظیم مجازات اسم عادی / سکوت / سکوت یک ساعت / بن")
    _log("💡 قفل ضد تبچی (کاملاً مستقل، لیست ثابت خودش):")
    _log("   - قفل ضد تبچی / قفل ضد تبچی خاموش")
    _log("   - تنظیم مجازات ضد تبچی عادی / سکوت / سکوت یک ساعت / بن (سکوت این قفل دائمی است)")
    _log("💡 قفل ممبر دزد (بیو حاوی لینک گروه splus.ir یا @آیدی-گروه -> سکوت دائم بی‌صدا):")
    _log("   - قفل ممبر دزد / قفل ممبر دزد خاموش")
    _log("💡 قفل ضد جقی (حذف پیام‌های حاوی کلمات ممنوعه، لیست ثابت خودش):")
    _log("   - قفل ضد جقی / قفل ضد جقی خاموش")
    _log("💡 پاکسازی پیام سیستمی (پیوستن/اضافه‌شدن/خروج/بن/پین/آنپین سروش) همیشه فعال است - بدون دستور.")
    _log("💡 ریست خودکار سکوت عمومی (کاری به قفل ضد تبچی ندارد):")
    _log("   - تنظیم مداوم ریست سکوت <زمان> / ریست سکوت خاموش")
    _log("💡 - ریست لیست بیو / ریست لیست اسم (جدا از هم)")
    _log("💡 - تنظیم پاکسازی خودکار HH:MM | تنظیم پاکسازی خودکار هر 1 ساعت (یا 30 دقیقه/40 دقیقه) | لیست پاکسازی | حذف پاکسازی HH:MM / حذف پاکسازی هر")
    _log("💡 - پاکسازی رسانه (دستی/فوری) | پاکسازی خودکار رسانه هر 30 دقیقه یا 12:30 | لیست پاکسازی رسانه | حذف پاکسازی رسانه ...")
    _log("💡 - وضعیت")
    _log("💡 ترجمه: ترجمه <متن> (یا ریپلای + ترجمه)")
    _log("💡 هواشناسی: هواشناسی <اسم شهر> (مثلاً: هواشناسی تهران)")
    _log("💡 اطلاعات شهر و جستجو: شهر <اسم شهر> (مثلاً: شهر تهران) | جستجو <متن> (مثلاً: جستجو حافظ شیرازی)")
    _log("💡 برای دیدن راهنمای کامل مدیریت گروه/امنیت، داخل گروه بنویس: راهنما")
    _log("💡 برای دیدن اطلاعات کاربر (نام + یوزرنیم + آیدی + بیو): «پروفایل من» / «مشخصات من» (اطلاعات خودت) یا ریپلای + «اطلاعات کاربر» (اطلاعات طرف مقابل) - برای همه فعال است")
    _log("💡 دستورات آموزش کلمه‌ی کلیدی: یاد بگیر <کلمه> = <جواب> (چندبار برای یک کلمه = چند جواب تصادفی) / لیست آموزش / حذف آموزش <کلمه> / ریست لیست آموزش")
    _log("💡 روشن/خاموش کردن سریع جواب‌های آموزش‌داده‌شده (بدون پاک شدن لیست): سخنگو روشن / سخنگو خاموش")
    _log("💡 تنظیم زمان پاک شدن خودکار پیام‌های ربات: تنظیم زمان پاک شدن <عدد> (مثلاً 0.1)")
    _log("💡 روشن کردن یک‌جای همه‌ی قفل‌ها (به‌جز گیف/عکس/استیکر/ویس/ویدیو/فایل/گپ): فعالسازی همه قفل ها")
    _log("💡 قفل رسانه تکی: قفل ویس / قفل ویدیو / قفل فایل (و «... خاموش» برای باز کردن)")
    _log("💡 قفل رسانه (کلی، مستقل - از edit_permissions استفاده می‌کند و به قفل‌های دیگر کاری ندارد): قفل رسانه / قفل رسانه کلی (و «... خاموش» یا «باز کردن قفل رسانه»)")

    while True:
        try:
            await client.run_until_disconnected()
        except Exception as e:
            _log_conn(f"⚠️ run_until_disconnected error: {e}")

        if client.is_connected():
            try:
                await client.disconnect()
            except Exception as e:
                _log_conn(f"⚠️ forced disconnect error: {e}")

        _log_conn("🔌 اتصال قطع شد؛ در حال تلاش برای اتصال دوباره...")
        while True:
            try:
                await client.connect()
                if client.is_connected():
                    break
            except Exception as e:
                _log_conn(f"⚠️ reconnect error: {e}")
            await asyncio.sleep(5)
        _log_conn("✅ اتصال دوباره برقرار شد.")

if __name__ == "__main__":
    if uvloop:
        uvloop.install()
        _log("⚡️ uvloop فعال شد (event loop سریع‌تر).")
    else:
        _log("ℹ️ uvloop نصب نیست - برای سرعت بیشتر: pip install uvloop")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _log("\n🛑 Stopped.")
    finally:
        try:
            client.disconnect()
        except:
            pass