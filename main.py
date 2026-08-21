import asyncio
import heapq
import logging
import re
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from operator import itemgetter
from queue import Empty, Queue

import jdatetime
import uvloop
from rubpy import Client, filters

LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(
    logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
)

logger = logging.getLogger("DonitoBot")
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.propagate = False

# g0IPSFR0d45b7ba07ff69c3960e7fbcc
TARGET_GROUP_GUID = "g0DHpOn042b93c4982b5b135365c7bb6"
MAIN_GROUP_GUID = "g0E19S900dd50643ab8fcbf23dad9e70"
MAIN_ADMIN_GUID = "u0JNjam04cd438e3013ebd0111bc3fb3"
ADMIN_GUIDS = {MAIN_ADMIN_GUID}

IS_BOT_ACTIVE = True
WARNING_AFTER_HOURS = 5
AUTO_CLOSE_AFTER_HOURS = 6
FORWARD_RETRY_DELAY = 10
PENDING_EXPIRE_SECONDS = 300
PROCESSED_CACHE_LIMIT = 10000
FORWARD_WORKERS = 2

STORAGE_MODE = "database"
DATABASE_PATH = "donito_bot.sqlite3"
USE_DATABASE = STORAGE_MODE.strip().lower() in {
    "database",
    "db",
    "sqlite",
}

MAIN_GROUP_FILTER = filters.object_guids([MAIN_GROUP_GUID])

CONFIRM_WORDS = frozenset({
    "بله",
    "آره",
    "اوکی",
    "تایید",
    "تائید",
    "باشه",
    "✅",
    "✓",
})

REJECT_WORDS = frozenset({
    "نه",
    "خیر",
    "رد",
    "لغو",
    "❌",
    "✗",
})

STATS_WORDS = frozenset({
    "آمار",
    "stats",
    "امار",
    "احصائیه",
    "وضعیت",
})

TOTAL_STATS_WORDS = frozenset({
    "کل",
    "کلی",
    "all",
    "total",
})

HELP_WORDS = frozenset({
    "راهنما",
    "help",
    "کمک",
    "راهنمایی",
    "راهنمايي",
})

DUNYTO_VARIATIONS = frozenset({
    "دنیتو",
    "دونیتو",
    "دُنیتو",
})

NAME_MAP = {
    "فایتر": "Fighter",
    "اهورا": "Ahoora",
    "سبحان": "Geshtapo",
    "یحیی": "Yahya",
    "صبحان": "Geshtapo",
    "یکتا": "Yekta",
    "ساره": "Sareh",
    "مجی": "Moji",
    "گاد فادر": "GodFather",
    "گادفادر": "GodFather",
    "فرید": "Farid",
    "هانتر": "Hunter",
    "هانی": "Hani",
    "ماتادور": "Matador",
    "نیلوفر": "Niloofar",
    "هانیه": "Hanieh",
    "رضا": "Reza",
    "آتنا": "Atena",
    "اتنا": "Atena",
}

FINGLISH_TABLE = str.maketrans(
    {
        "ا": "a",
        "آ": "a",
        "ب": "b",
        "پ": "p",
        "ت": "t",
        "ث": "s",
        "ج": "j",
        "چ": "ch",
        "ح": "h",
        "خ": "kh",
        "د": "d",
        "ذ": "z",
        "ر": "r",
        "ز": "z",
        "ژ": "zh",
        "س": "s",
        "ش": "sh",
        "ص": "s",
        "ض": "z",
        "ط": "t",
        "ظ": "z",
        "ع": "a",
        "غ": "gh",
        "ف": "f",
        "ق": "gh",
        "ک": "k",
        "ك": "k",
        "گ": "g",
        "ل": "l",
        "م": "m",
        "ن": "n",
        "و": "oo",
        "ه": "h",
        "ی": "i",
        "ي": "i",
        "ئ": "e",
        "؟": "?",
        "،": ",",
        "؛": ";",
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "َ": "a",
        "ُ": "o",
        "ِ": "e",
        "\u200c": None,
    }
)

NORMALIZE_TABLE = str.maketrans(
    {
        8204: " ",
        1610: "ی",
        1603: "ک",
    }
)

DIGIT_TABLE = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

NAME_BY_LEN = {}
for name, mapped in NAME_MAP.items():
    NAME_BY_LEN.setdefault(len(name), []).append((name, mapped))

START_REGEX = re.compile(
    r"^(?!پایان[\s,،])([^,،]+)[,،]\s*([^,،]+?)"
    r"(?:\s*[,،]\s*(فور))?\s*$"
)

END_REGEX = re.compile(
    r"^پایان[\s,،]+(.+?)(?:\s*[,،]?\s*(فور))?\s*$"
)

LIST_GAMES_REGEX = re.compile(
    r"^(?:(?:لیست|نمایش)\s+)?بازی(?:\s+ها)?$"
)

DELETE_GAME_REGEX = re.compile(
    r"^(?:حذف|پاک)(?:\s+کردن)?\s+بازی\s+(\d+)$"
)

DELETE_ALL_REGEX = re.compile(
    r"^(?:حذف|پاک)(?:\s+کردن)?"
    r"(?:\s+(?:تمام|همه|کل|کلیه|تمامی))?"
    r"\s+بازی(?:\s+ها)?$"
)

AUTO_STATS_SET_REGEX = re.compile(
    r"^(?:آمار|احصائیه)\s+(?:خودکار|اتوماتیک)\s+"
    r"(?:در\s+)?ساعت\s+(\d{1,2}:\d{2})$"
)

AUTO_STATS_DISABLE_REGEX = re.compile(
    r"^(?:لغو|حذف|غیرفعال|قطع)\s+"
    r"(?:(?:آمار\s+(?:خودکار|اتوماتیک))|"
    r"(?:(?:خودکار|اتوماتیک)\s+آمار))$"
)

CLOSE_GROUP_REGEX = re.compile(
    r"^(?:بستن|بسته|قفل)(?:\s+کردن)?"
    r"(?:\s+(?:گروه|چت|گپ))?$"
)

OPEN_GROUP_REGEX = re.compile(
    r"^(?:باز\s+کردن|وا\s+کردن|آزاد\s*کردن)"
    r"(?:\s+(?:گروه|چت|گپ))?$"
)

ADD_ADMIN_REGEX = re.compile(
    r"^(?:ادمین\s+کن|افزودن\s+ادمین|ادمین\s+کردن|"
    r"ادمین\s+اضافه\s+کن)(?:\s+(\S+))?$"
)

REMOVE_ADMIN_REGEX = re.compile(
    r"^(?:عزل\s+ادمین|حذف\s+ادمین|برداشتن\s+ادمین|"
    r"عزل\s+کردن)(?:\s+(\S+))?$"
)

DELETE_MESSAGES_REGEX = re.compile(
    r"^(?:حذف|پاک)(?:\s+کردن)?\s+پیام\s+(\d+)$"
)

BAN_REGEX = re.compile(
    r"^(?:بن(?:\s+کن)?|اخراج(?:\s+کن)?|حذف(?:\s+کن)?)"
    r"(?:\s+(\S+))?$"
)

UNBAN_REGEX = re.compile(
    r"^(?:آنبن(?:\s+کن)?|لغو\s+بن|لغو\s+اخراج|برگردان|"
    r"لغو\s+کردن|لغو)(?:\s+(\S+))?$"
)

BLOCK_REGEX = re.compile(
    r"^(?:بلاک|مسدود)(?:\s+کردن)?(?:\s+(\S+))?$"
)

SPECIAL_REGEX = re.compile(
    r"^(?:ویژه|مخصوص|خاص)(?:\s+(\S+))?$"
)

OBJECT_ID_REGEX = re.compile(r"^[ugc]\w+$")

HELP_TEXT = (
    "📖 راهنمای کامل ربات بنرگذار دُنیتو\n\n"
    "🎮 شروع بازی (کاربران ویژه)\n"
    "• یک عکس با کپشن زیر بفرستید:\n"
    "  [سناریو] ، [سازنده] ، فور\n"
    "• «فور» اختیاری است (فوروارد به گروه رسمی).\n"
    "• اگر «دنیتو» در سناریو باشد، "
    "خودکار به کپشن اضافه می‌شود.\n"
    "• مثال: مذاکره دنیتو ، هانتر ، فور\n\n"
    "✅ تأیید / ❌ رد بنر\n"
    "• بعد از ارسال عکس، پیش‌نمایشی دریافت می‌کنید.\n"
    "• با ریپلای روی پیش‌نمایش یکی از کلمات زیر را بفرستید:\n"
    "  تأیید: بله / آره / اوکی / تایید\n"
    "  رد: نه / خیر / رد / لغو\n"
    "• فقط سازندۀ اصلی می‌تواند تأیید/رد کند.\n\n"
    "🏁 پایان بازی\n"
    "• یک عکس با کپشن زیر بفرستید:\n"
    "  پایان [برنده] ، فور\n"
    "• «فور» اختیاری است.\n"
    "• در صورت وجود چند بازی، قدیمی‌ترین بسته می‌شود.\n"
    "• می‌توانید روی بنر شروع ریپلای بزنید.\n"
    "• پس از ارسال، پیش‌نمایش دریافت می‌کنید و "
    "با بله/نه تأیید یا رد کنید.\n\n"
    "📊 آمار و اطلاعات\n"
    "• آمار روزانه گروه: آمار / stats\n"
    "• آمار کلی گروه: آمار کل / آمار کلی\n"
    "• آمار اختصاصی: ریپلای روی کاربر + آمار\n"
    "• راهنما: راهنما / help\n"
    "• لیست بازی‌های فعال: لیست بازی‌ها / نمایش بازی‌ها\n"
    "• حذف یک بازی: حذف بازی 01 / پاک بازی 01\n"
    "• حذف تمام بازی‌ها: حذف تمام بازی‌ها / پاک کل بازی‌ها\n\n"
    "👑 دستورات مدیریت گروه (ادمین‌ها)\n"
    "• قفل گروه: قفل / قفل گروه / بستن\n"
    "• باز کردن گروه: بازکردن / باز کردن گروه / وا کردن\n\n"
    "🔨 مدیریت کاربران (ادمین‌ها)\n"
    "• ویژه کردن: ویژه / ویژه u0xxx\n"
    "• بلاک کردن: بلاک / بلاک u0xxx / مسدود\n"
    "• بن کردن: بن / اخراج / حذف کن\n"
    "• آنبن + ارسال لینک: آنبن / برگردان / لغو بن\n\n"
    "⚙️ مدیریت ادمین‌ها (فقط ادمین اصلی)\n"
    "• افزودن ادمین: ادمین کن / افزودن ادمین u0xxx\n"
    "• حذف ادمین: عزل ادمین / حذف ادمین\n\n"
    "🧹 پاکسازی پیام‌ها (ادمین‌ها)\n"
    "• حذف پیام 20\n"
    "  حداکثر ۱۰۰۰ پیام آخر حذف می‌شود.\n\n"
    "⏰ آمار خودکار (ادمین‌ها)\n"
    "• تنظیم: آمار خودکار ساعت 00:00\n"
    "• لغو: لغو آمار خودکار / حذف آمار خودکار\n\n"
    "🛑 توقف و راه‌اندازی ربات (فقط ادمین اصلی)\n"
    "• توقف: !stop\n"
    "• راه‌اندازی: !start\n"
)

active_games = {}
pending_banners = {}
pending_by_preview = {}
pending_ends = {}
pending_end_by_preview = {}
start_message_index = {}
processing_previews = set()
processed_message_ids = {}
BACKGROUND_TASKS = set()

game_stats = {
    "total_games": 0,
    "daily_games": 0,
    "builder_stats": defaultdict(int),
    "scenario_stats": defaultdict(int),
    "daily_builder_stats": defaultdict(int),
    "daily_scenario_stats": defaultdict(int),
    "user_stats": {},
    "daily_user_stats": {},
    "last_reset": "",
}

BLOCKED_USERS = set()
SPECIAL_USERS = set()

AUTO_STATS_ENABLED = False
AUTO_STATS_TIME = None
AUTO_STATS_HANDLE = None
LAST_AUTO_STATS_DATE = ""

FORWARD_QUEUE = None
ACTIVE_EVENT = None
WORKERS = []

DB_CONNECTION = None
_DB_QUEUE = None
_DB_THREAD = None

bot = Client("bot")


def log_error(context, error):
    logger.error(
        "%s | %s: %s",
        context,
        type(error).__name__,
        error,
    )


def normalize_text(text):
    return text.translate(NORMALIZE_TABLE).strip().lower()


def first_word(text):
    if not text:
        return ""
    return text.split(maxsplit=1)[0].strip(".,!?؟،؛:()")


def consume_message_id(message_id):
    cache = processed_message_ids
    if message_id in cache:
        return False
    if len(cache) >= PROCESSED_CACHE_LIMIT:
        cache.pop(next(iter(cache)))
    cache[message_id] = None
    return True


def _task_done(task):
    BACKGROUND_TASKS.discard(task)
    if not task.cancelled():
        error = task.exception()
        if error is not None:
            logger.error("Background task error: %s", error)


def spawn(coro):
    task = asyncio.create_task(coro)
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(_task_done)
    return task


def _silent_done(task):
    if not task.cancelled():
        task.exception()


async def delete_messages_safe(object_guid, message_ids):
    ids = [mid for mid in message_ids if mid is not None]
    if not ids:
        return
    try:
        await bot.delete_messages(
            object_guid=object_guid,
            message_ids=ids,
        )
    except Exception as error:
        logger.warning("delete_messages failed: %s", error)


async def send_message_safe(
    object_guid,
    text,
    reply_to_message_id=None,
    auto_delete=None,
):
    kwargs = {
        "object_guid": object_guid,
        "text": text,
    }
    if reply_to_message_id is not None:
        kwargs["reply_to_message_id"] = reply_to_message_id
    if auto_delete is not None:
        kwargs["auto_delete"] = auto_delete
    try:
        await bot.send_message(**kwargs)
    except Exception as error:
        logger.warning("send_message failed: %s", error)


async def respond_and_cleanup(update, text, auto_delete=15):
    await send_message_safe(
        update.object_guid,
        text,
        update.message_id,
        auto_delete,
    )
    await delete_messages_safe(
        update.object_guid,
        [update.message_id],
    )


def get_shamsi_now():
    return jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")


def get_shamsi_date():
    return jdatetime.datetime.now().strftime("%Y/%m/%d")


def persian_to_finglish(text):
    return text.translate(FINGLISH_TABLE).title().replace(" ", "")


def one_edit_match(a, b):
    len_a = len(a)
    len_b = len(b)
    if len_a == len_b:
        diff = 0
        for index in range(len_a):
            if a[index] != b[index]:
                diff += 1
                if diff > 1:
                    return False
        return True
    if len_a + 1 == len_b:
        a, b = b, a
        len_a, len_b = len_b, len_a
    elif len_b + 1 != len_a:
        return False
    index_a = index_b = diff = 0
    while index_a < len_a and index_b < len_b:
        if a[index_a] != b[index_b]:
            diff += 1
            if diff > 1:
                return False
            index_a += 1
        else:
            index_a += 1
            index_b += 1
    return True


def normalize_builder_name(raw):
    key = " ".join(raw.translate(NORMALIZE_TABLE).split())
    mapped = NAME_MAP.get(key)
    if mapped is not None:
        return mapped, None
    length = len(key)
    for candidates in (
        NAME_BY_LEN.get(length),
        NAME_BY_LEN.get(length - 1),
        NAME_BY_LEN.get(length + 1),
    ):
        if not candidates:
            continue
        for name, mapped_name in candidates:
            if one_edit_match(key, name):
                return mapped_name, name
    return persian_to_finglish(key), None


def extract_message_id(result):
    if result is None:
        return None
    if isinstance(result, int):
        return result
    if isinstance(result, str):
        return int(result) if result.isdigit() else None
    if isinstance(result, (list, tuple)):
        return extract_message_id(result[0]) if result else None
    value = getattr(result, "message_id", None)
    if value is None:
        value = getattr(result, "message_ids", None)
    if value is None and isinstance(result, dict):
        value = result.get("message_id") or result.get("message_ids")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("message_id") or value.get("id")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def extract_message_ids(result):
    if result is None:
        return []
    messages = getattr(result, "messages", None)
    if messages is None:
        if isinstance(result, dict):
            messages = result.get("messages")
        elif isinstance(result, list):
            messages = result
    if not messages:
        return []
    ids = []
    for message in messages:
        if isinstance(message, int):
            ids.append(message)
            continue
        if isinstance(message, dict):
            message_id = message.get("message_id")
        else:
            message_id = getattr(message, "message_id", None)
        if message_id:
            ids.append(message_id)
    return ids


def find_available_game_id(games):
    for index in range(1, 100):
        game_id = f"{index:02d}"
        if game_id not in games:
            return game_id
    return "XX"


def is_user_allowed(update):
    author = update.author_guid
    if author in ADMIN_GUIDS:
        return True
    if not IS_BOT_ACTIVE or author in BLOCKED_USERS:
        return False
    return not SPECIAL_USERS or author in SPECIAL_USERS


def _format_scenario_lines(items):
    return "\n".join(
        f"{index}. {name}: {count} بازی"
        for index, (name, count) in enumerate(items, 1)
    ) or "📭 داده‌ای موجود نیست"


def _ensure_user_stats(container, user_guid):
    user = container.get(user_guid)
    if user is None:
        user = {
            "games": 0,
            "scenarios": defaultdict(int),
        }
        container[user_guid] = user
    return user


def _reset_daily_memory():
    game_stats["daily_games"] = 0
    game_stats["daily_builder_stats"].clear()
    game_stats["daily_scenario_stats"].clear()
    game_stats["daily_user_stats"].clear()


def _increment_memory(user_guid, builder, scenario):
    stats = game_stats
    stats["total_games"] += 1
    stats["daily_games"] += 1
    stats["builder_stats"][builder] += 1
    stats["scenario_stats"][scenario] += 1
    stats["daily_builder_stats"][builder] += 1
    stats["daily_scenario_stats"][scenario] += 1

    user = _ensure_user_stats(stats["user_stats"], user_guid)
    user["games"] += 1
    user["scenarios"][scenario] += 1

    daily_user = _ensure_user_stats(
        stats["daily_user_stats"],
        user_guid,
    )
    daily_user["games"] += 1
    daily_user["scenarios"][scenario] += 1


def _db_create_tables():
    DB_CONNECTION.executescript(
        """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS builder_stats (
    name TEXT PRIMARY KEY,
    count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS scenario_stats (
    name TEXT PRIMARY KEY,
    count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_builder_stats (
    name TEXT PRIMARY KEY,
    count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_scenario_stats (
    name TEXT PRIMARY KEY,
    count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS user_total (
    user_guid TEXT PRIMARY KEY,
    games INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS user_scenario (
    user_guid TEXT NOT NULL,
    scenario TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (user_guid, scenario)
);
CREATE TABLE IF NOT EXISTS daily_user_total (
    user_guid TEXT PRIMARY KEY,
    games INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_user_scenario (
    user_guid TEXT NOT NULL,
    scenario TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (user_guid, scenario)
);
CREATE TABLE IF NOT EXISTS access_control (
    guid TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK(type IN ('admin', 'blocked', 'special'))
);
"""
    )


def _db_load():
    cur = DB_CONNECTION.cursor()
    cur.execute("SELECT key, value FROM meta")
    meta = dict(cur.fetchall())
    stats = game_stats
    stats["total_games"] = int(meta.get("total_games", 0))
    stats["daily_games"] = int(meta.get("daily_games", 0))
    stats["last_reset"] = meta.get("last_reset", "")

    for name, count in cur.execute(
        "SELECT name, count FROM builder_stats"
    ):
        stats["builder_stats"][name] = count

    for name, count in cur.execute(
        "SELECT name, count FROM scenario_stats"
    ):
        stats["scenario_stats"][name] = count

    for name, count in cur.execute(
        "SELECT name, count FROM daily_builder_stats"
    ):
        stats["daily_builder_stats"][name] = count

    for name, count in cur.execute(
        "SELECT name, count FROM daily_scenario_stats"
    ):
        stats["daily_scenario_stats"][name] = count

    for user_guid, games in cur.execute(
        "SELECT user_guid, games FROM user_total"
    ):
        user = stats["user_stats"].get(user_guid)
        if user is None:
            user = {
                "games": 0,
                "scenarios": defaultdict(int),
            }
            stats["user_stats"][user_guid] = user
        if not user["games"]:
            user["games"] = games

    for user_guid, scenario, count in cur.execute(
        "SELECT user_guid, scenario, count FROM user_scenario"
    ):
        user = stats["user_stats"].get(user_guid)
        if user is None:
            user = {
                "games": 0,
                "scenarios": defaultdict(int),
            }
            stats["user_stats"][user_guid] = user
        if not user["scenarios"][scenario]:
            user["scenarios"][scenario] = count

    for user_guid, games in cur.execute(
        "SELECT user_guid, games FROM daily_user_total"
    ):
        user = stats["daily_user_stats"].get(user_guid)
        if user is None:
            user = {
                "games": 0,
                "scenarios": defaultdict(int),
            }
            stats["daily_user_stats"][user_guid] = user
        if not user["games"]:
            user["games"] = games

    for user_guid, scenario, count in cur.execute(
        "SELECT user_guid, scenario, count "
        "FROM daily_user_scenario"
    ):
        user = stats["daily_user_stats"].get(user_guid)
        if user is None:
            user = {
                "games": 0,
                "scenarios": defaultdict(int),
            }
            stats["daily_user_stats"][user_guid] = user
        if not user["scenarios"][scenario]:
            user["scenarios"][scenario] = count

    for guid, acc_type in cur.execute(
        "SELECT guid, type FROM access_control"
    ):
        if acc_type == "admin":
            ADMIN_GUIDS.add(guid)
        elif acc_type == "blocked":
            BLOCKED_USERS.add(guid)
        elif acc_type == "special":
            SPECIAL_USERS.add(guid)


def _db_apply(cur, item):
    if item[0] == 0:
        _, user_guid, builder, scenario, today = item
        cur.execute(
            "INSERT INTO meta(key, value) "
            "VALUES('total_games', 1) "
            "ON CONFLICT(key) DO UPDATE SET value = value + 1"
        )
        cur.execute(
            "INSERT INTO meta(key, value) "
            "VALUES('daily_games', 1) "
            "ON CONFLICT(key) DO UPDATE SET value = value + 1"
        )
        cur.execute(
            "INSERT INTO builder_stats(name, count) "
            "VALUES(?, 1) "
            "ON CONFLICT(name) DO UPDATE SET count = count + 1",
            (builder,),
        )
        cur.execute(
            "INSERT INTO scenario_stats(name, count) "
            "VALUES(?, 1) "
            "ON CONFLICT(name) DO UPDATE SET count = count + 1",
            (scenario,),
        )
        cur.execute(
            "INSERT INTO daily_builder_stats(name, count) "
            "VALUES(?, 1) "
            "ON CONFLICT(name) DO UPDATE SET count = count + 1",
            (builder,),
        )
        cur.execute(
            "INSERT INTO daily_scenario_stats(name, count) "
            "VALUES(?, 1) "
            "ON CONFLICT(name) DO UPDATE SET count = count + 1",
            (scenario,),
        )
        cur.execute(
            "INSERT INTO user_total(user_guid, games) "
            "VALUES(?, 1) "
            "ON CONFLICT(user_guid) "
            "DO UPDATE SET games = games + 1",
            (user_guid,),
        )
        cur.execute(
            "INSERT INTO user_scenario(user_guid, scenario, count) "
            "VALUES(?, ?, 1) "
            "ON CONFLICT(user_guid, scenario) "
            "DO UPDATE SET count = count + 1",
            (user_guid, scenario),
        )
        cur.execute(
            "INSERT INTO daily_user_total(user_guid, games) "
            "VALUES(?, 1) "
            "ON CONFLICT(user_guid) "
            "DO UPDATE SET games = games + 1",
            (user_guid,),
        )
        cur.execute(
            "INSERT INTO daily_user_scenario("
            "user_guid, scenario, count) "
            "VALUES(?, ?, 1) "
            "ON CONFLICT(user_guid, scenario) "
            "DO UPDATE SET count = count + 1",
            (user_guid, scenario),
        )
    elif item[0] == 1:
        _, guid, acc_type, action = item
        if action == "add":
            cur.execute(
                "INSERT OR REPLACE INTO access_control(guid, type) "
                "VALUES(?, ?)",
                (guid, acc_type),
            )
        else:
            cur.execute(
                "DELETE FROM access_control WHERE guid=? AND type=?",
                (guid, acc_type),
            )
    elif item[0] == 2:
        _, today = item
        cur.execute("DELETE FROM daily_builder_stats")
        cur.execute("DELETE FROM daily_scenario_stats")
        cur.execute("DELETE FROM daily_user_total")
        cur.execute("DELETE FROM daily_user_scenario")
        cur.execute(
            "UPDATE meta SET value='0' WHERE key='daily_games'"
        )
        cur.execute(
            "INSERT OR REPLACE INTO meta(key, value) "
            "VALUES('last_reset', ?)",
            (today,),
        )


def _db_writer():
    q = _DB_QUEUE
    conn = DB_CONNECTION
    while True:
        item = q.get()
        if item is None:
            break
        try:
            cur = conn.cursor()
            _db_apply(cur, item)
            while True:
                try:
                    item = q.get_nowait()
                except Empty:
                    break
                if item is None:
                    conn.commit()
                    return
                _db_apply(cur, item)
            conn.commit()
        except Exception as error:
            try:
                conn.rollback()
            except Exception:
                pass
            log_error("db_writer", error)


def _db_enqueue(item):
    if USE_DATABASE and _DB_QUEUE is not None:
        _DB_QUEUE.put_nowait(item)


def _db_update_access(guid, acc_type, action):
    _db_enqueue((1, guid, acc_type, action))


def _init_storage():
    global DB_CONNECTION, USE_DATABASE, _DB_QUEUE, _DB_THREAD
    if not USE_DATABASE:
        return
    try:
        DB_CONNECTION = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False,
        )
        DB_CONNECTION.execute("PRAGMA journal_mode=WAL")
        DB_CONNECTION.execute("PRAGMA synchronous=NORMAL")
        DB_CONNECTION.execute("PRAGMA temp_store=MEMORY")
        DB_CONNECTION.execute("PRAGMA cache_size=-4000")
        DB_CONNECTION.execute("PRAGMA busy_timeout=5000")
        _db_create_tables()
        _db_load()
        _DB_QUEUE = Queue()
        _DB_THREAD = threading.Thread(
            target=_db_writer,
            daemon=True,
        )
        _DB_THREAD.start()
    except Exception as error:
        DB_CONNECTION = None
        USE_DATABASE = False
        log_error("storage_init", error)


def _ensure_daily_reset():
    today = get_shamsi_date()
    if game_stats["last_reset"] != today:
        _reset_daily_memory()
        game_stats["last_reset"] = today
        if USE_DATABASE:
            _db_enqueue((2, today))


def update_stats(builder, scenario, user_guid):
    _ensure_daily_reset()
    user_guid = (user_guid or "").strip()
    _increment_memory(user_guid, builder, scenario)
    if USE_DATABASE:
        today = get_shamsi_date()
        _db_enqueue(
            (0, user_guid, builder, scenario, today)
        )


def generate_daily_stats_text():
    _ensure_daily_reset()
    stats_date = game_stats["last_reset"] or get_shamsi_date()
    daily_games = game_stats["daily_games"]
    top_builders = heapq.nlargest(
        3,
        game_stats["daily_builder_stats"].items(),
        key=itemgetter(1),
    )
    top_scenarios = heapq.nlargest(
        3,
        game_stats["daily_scenario_stats"].items(),
        key=itemgetter(1),
    )
    builder_lines = _format_scenario_lines(top_builders)
    scenario_lines = _format_scenario_lines(top_scenarios)
    return (
        "📊 آمار روزانه ربات دُنیتو\n\n"
        f"📅 تاریخ آمار: {stats_date}\n"
        f"📈 بازی‌های ثبت‌شده: {daily_games}\n\n"
        f"🥇 ۳ سازنده برتر روزانه:\n{builder_lines}\n\n"
        f"🎭 ۳ سناریوی محبوب روزانه:\n{scenario_lines}"
    )


def generate_total_stats_text():
    _ensure_daily_reset()
    today = get_shamsi_date()
    total_games = game_stats["total_games"]
    top_builders = heapq.nlargest(
        3,
        game_stats["builder_stats"].items(),
        key=itemgetter(1),
    )
    top_scenarios = heapq.nlargest(
        3,
        game_stats["scenario_stats"].items(),
        key=itemgetter(1),
    )
    builder_lines = _format_scenario_lines(top_builders)
    scenario_lines = _format_scenario_lines(top_scenarios)
    return (
        "📊 آمار کلی ربات دُنیتو\n\n"
        f"📅 تاریخ: {today}\n"
        f"🎮 کل بازی‌های برگزار شده: {total_games}\n\n"
        f"🥇 ۳ سازنده برتر (کل):\n{builder_lines}\n\n"
        f"🎭 ۳ سناریوی محبوب (کل):\n{scenario_lines}"
    )


def generate_user_stats_text(user_guid):
    _ensure_daily_reset()
    user_guid = (user_guid or "").strip()
    stats_date = game_stats["last_reset"] or get_shamsi_date()
    user = game_stats["user_stats"].get(user_guid)
    daily_user = game_stats["daily_user_stats"].get(user_guid)
    total_games = user["games"] if user else 0
    daily_games = daily_user["games"] if daily_user else 0
    total_top = heapq.nlargest(
        3,
        user["scenarios"].items() if user else [],
        key=itemgetter(1),
    )
    daily_top = heapq.nlargest(
        3,
        daily_user["scenarios"].items() if daily_user else [],
        key=itemgetter(1),
    )
    total_lines = _format_scenario_lines(total_top)
    daily_lines = _format_scenario_lines(daily_top)
    return (
        "👤 آمار اختصاصی کاربر\n\n"
        f"🆔 شناسه: `{user_guid}`\n"
        f"📅 تاریخ آمار روزانه: {stats_date}\n\n"
        f"🎮 کل بازی‌ها: {total_games}\n"
        f"📈 بازی‌های روز: {daily_games}\n\n"
        f"🏆 سناریوهای برتر (کل):\n{total_lines}\n\n"
        f"📅 سناریوهای برتر (روز):\n{daily_lines}"
    )


def set_bot_active(value):
    global IS_BOT_ACTIVE
    IS_BOT_ACTIVE = value
    if ACTIVE_EVENT is not None:
        if value:
            ACTIVE_EVENT.set()
        else:
            ACTIVE_EVENT.clear()


async def forward_worker():
    queue = FORWARD_QUEUE
    event = ACTIVE_EVENT
    target = TARGET_GROUP_GUID
    forward_messages = bot.forward_messages
    while True:
        task = await queue.get()
        try:
            if not IS_BOT_ACTIVE:
                await event.wait()
            try:
                result = await asyncio.wait_for(
                    forward_messages(
                        from_object_guid=task["from_guid"],
                        message_ids=[task["message_id"]],
                        to_object_guid=target,
                    ),
                    timeout=30,
                )
                forwarded = extract_message_id(result)
                chat_id = task.get("chat_id")
                game_id = task.get("game_id")
                if chat_id and game_id and forwarded is not None:
                    games = active_games.get(chat_id)
                    if games:
                        game = games.get(game_id)
                        if game is not None:
                            game["forwarded_msg_id"] = forwarded
            except Exception as error:
                log_error("forward_queue", error)
                retries = task.get("retries", 0) + 1
                if retries < 3:
                    task["retries"] = retries
                    asyncio.get_running_loop().call_later(
                        FORWARD_RETRY_DELAY,
                        queue.put_nowait,
                        task,
                    )
        finally:
            queue.task_done()


def get_forward_queue():
    global FORWARD_QUEUE, ACTIVE_EVENT
    if FORWARD_QUEUE is None:
        FORWARD_QUEUE = asyncio.Queue()
        ACTIVE_EVENT = asyncio.Event()
        if IS_BOT_ACTIVE:
            ACTIVE_EVENT.set()
        for _ in range(FORWARD_WORKERS):
            WORKERS.append(asyncio.create_task(forward_worker()))
    return FORWARD_QUEUE


def cancel_game_timers(game):
    for key in ("warn_handle", "close_handle"):
        handle = game.pop(key, None)
        if handle is not None:
            handle.cancel()


async def send_game_timeout_warning(chat_id, game, hours):
    text = (
        "⚠️ هشدار زمان بازی\n\n"
        f"بازی شماره `{game['id']}`\n"
        f"سناریو: {game['scenario_caption']}\n"
        f"مدت زمان: {hours:.1f} ساعت\n\n"
        "لطفاً نسبت به پایان بازی اقدام کنید."
    )
    await send_message_safe(
        chat_id,
        text,
        game.get("start_msg_id"),
        60,
    )


async def close_expired_game(chat_id, game):
    games = active_games.get(chat_id)
    if not games:
        return
    removed = games.pop(game["id"], None)
    if removed is None:
        return
    cancel_game_timers(removed)
    if not games:
        active_games.pop(chat_id, None)
    start_message_index.pop(removed.get("start_msg_id"), None)
    await delete_messages_safe(
        chat_id,
        [removed.get("start_msg_id")],
    )
    forwarded = removed.get("forwarded_msg_id")
    if forwarded is not None:
        await delete_messages_safe(
            TARGET_GROUP_GUID,
            [forwarded],
        )


def _game_warning(chat_id, game_id):
    games = active_games.get(chat_id)
    if not games:
        return
    game = games.get(game_id)
    if game is None or game.get("timeout_warned"):
        return
    game["timeout_warned"] = True
    spawn(
        send_game_timeout_warning(
            chat_id,
            game,
            WARNING_AFTER_HOURS,
        )
    )


def _game_close(chat_id, game_id):
    games = active_games.get(chat_id)
    if not games:
        return
    game = games.get(game_id)
    if game is None or game.get("closing"):
        return
    game["closing"] = True
    spawn(close_expired_game(chat_id, game))


def schedule_auto_stats():
    global AUTO_STATS_HANDLE
    if not AUTO_STATS_ENABLED or not AUTO_STATS_TIME:
        return
    now = datetime.now()
    try:
        hour, minute = map(int, AUTO_STATS_TIME.split(":"))
        target = now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
    except ValueError:
        return
    if target <= now:
        target += timedelta(days=1)
    delay = (target - now).total_seconds()
    AUTO_STATS_HANDLE = asyncio.get_running_loop().call_later(
        delay,
        auto_stats_fire,
    )


def auto_stats_fire():
    global LAST_AUTO_STATS_DATE, AUTO_STATS_HANDLE
    if not AUTO_STATS_ENABLED:
        return
    now = datetime.now()
    if now.strftime("%H:%M") != AUTO_STATS_TIME:
        schedule_auto_stats()
        return
    today = jdatetime.datetime.now().strftime("%Y/%m/%d")
    if today != LAST_AUTO_STATS_DATE and IS_BOT_ACTIVE:
        LAST_AUTO_STATS_DATE = today
        spawn(
            send_message_safe(
                MAIN_GROUP_GUID,
                generate_daily_stats_text(),
            )
        )
    schedule_auto_stats()


def expire_pending(user_guid, preview_msg_id):
    if preview_msg_id in processing_previews:
        return
    banner = pending_banners.get(user_guid)
    if banner is None:
        return
    if banner.get("preview_msg_id") != preview_msg_id:
        return
    pending_banners.pop(user_guid, None)
    pending_by_preview.pop(preview_msg_id, None)
    task = banner.get("download_task")
    if task is not None and not task.done():
        task.cancel()
    spawn(delete_messages_safe(banner["chat_id"], [preview_msg_id]))


def expire_pending_end(user_guid, preview_msg_id):
    if preview_msg_id in processing_previews:
        return
    end_data = pending_ends.get(user_guid)
    if end_data is None:
        return
    if end_data.get("preview_msg_id") != preview_msg_id:
        return
    pending_ends.pop(user_guid, None)
    pending_end_by_preview.pop(preview_msg_id, None)
    task = end_data.get("download_task")
    if task is not None and not task.done():
        task.cancel()
    spawn(delete_messages_safe(end_data["chat_id"], [preview_msg_id]))


async def resolve_target_guid(identifier):
    identifier = identifier.strip()
    if OBJECT_ID_REGEX.match(identifier):
        return identifier
    if identifier.startswith("@"):
        identifier = identifier[1:]
    if identifier.startswith("https://rubika.ir/join"):
        try:
            if "/joinc" in identifier:
                result = await bot.channel_preview_by_join_link(
                    identifier
                )
                return result.channel.channel_guid
            result = await bot.group_preview_by_join_link(identifier)
            return result.group.group_guid
        except Exception as error:
            raise ValueError("لینک نامعتبر است.") from error
    try:
        result = await bot.get_object_by_username(identifier)
        if hasattr(result, "user"):
            return result.user.user_guid
        if hasattr(result, "group"):
            return result.group.group_guid
        if hasattr(result, "channel"):
            return result.channel.channel_guid
    except Exception as error:
        raise ValueError("یوزرنیم یا شناسه معتبر نیست.") from error
    raise ValueError("نوع شیء شناسایی نشد.")


async def get_reply_author_guid(update):
    message = update.message
    reply_id = getattr(message, "reply_to_message_id", None)
    if not reply_id:
        return None
    reply_msg = getattr(message, "reply_to_message", None)
    if reply_msg is None:
        reply_msg = getattr(message, "reply_to", None)
    if reply_msg is not None:
        author = getattr(reply_msg, "author_object_guid", None)
        if author is None:
            author = getattr(reply_msg, "author_guid", None)
        if author:
            return author
    try:
        result = await bot.get_messages_by_id(
            update.object_guid,
            [reply_id],
        )
        messages = getattr(result, "messages", None)
        if messages is None:
            messages = result if isinstance(result, list) else [result]
        if messages:
            message_obj = messages[0]
            author = getattr(message_obj, "author_object_guid", None)
            if author is None:
                author = getattr(message_obj, "author_guid", None)
            if author:
                return author
    except Exception as error:
        logger.warning("get_reply_author_guid failed: %s", error)
    return None


async def resolve_target_or_respond(update, identifier):
    target_guid = None
    if getattr(update.message, "reply_to_message_id", None):
        target_guid = await get_reply_author_guid(update)
    if target_guid is None and identifier:
        try:
            target_guid = await resolve_target_guid(identifier)
        except ValueError as error:
            await respond_and_cleanup(update, f"⚠️ {error}", 10)
            return None
    if target_guid is None:
        text = (
            "❌ کاربری مشخص نشد. "
            "ریپلای کنید یا شناسه/یوزرنیم را بنویسید."
        )
        await respond_and_cleanup(update, text, 10)
        return None
    return target_guid


async def admin_stop(update):
    set_bot_active(False)
    await respond_and_cleanup(update, "🛑 ربات متوقف شد.", 30)


async def admin_start(update):
    set_bot_active(True)
    await respond_and_cleanup(update, "✅ ربات راه‌اندازی شد.", 10)


async def set_auto_stats(update, match):
    global AUTO_STATS_ENABLED, AUTO_STATS_TIME
    global LAST_AUTO_STATS_DATE, AUTO_STATS_HANDLE
    AUTO_STATS_ENABLED = True
    AUTO_STATS_TIME = match.group(1).translate(DIGIT_TABLE)
    LAST_AUTO_STATS_DATE = ""
    if AUTO_STATS_HANDLE is not None:
        AUTO_STATS_HANDLE.cancel()
    schedule_auto_stats()
    text = f"⏰ آمار خودکار برای ساعت {AUTO_STATS_TIME} فعال شد."
    await respond_and_cleanup(update, text, 15)


async def disable_auto_stats(update):
    global AUTO_STATS_ENABLED, AUTO_STATS_HANDLE
    AUTO_STATS_ENABLED = False
    if AUTO_STATS_HANDLE is not None:
        AUTO_STATS_HANDLE.cancel()
        AUTO_STATS_HANDLE = None
    await respond_and_cleanup(update, "🛑 آمار خودکار غیرفعال شد.", 15)


async def block_user(update, match):
    target_guid = await resolve_target_or_respond(
        update,
        match.group(1),
    )
    if target_guid is None:
        return
    if target_guid in ADMIN_GUIDS:
        await respond_and_cleanup(
            update,
            "⛔ نمی‌توانید ادمین را بلاک کنید.",
            10,
        )
        return
    was_special = target_guid in SPECIAL_USERS
    SPECIAL_USERS.discard(target_guid)
    if target_guid in BLOCKED_USERS:
        text = (
            f"⚠️ کاربر `{target_guid}` قبلاً بلاک شده است."
        )
        await respond_and_cleanup(update, text, 10)
        return
    BLOCKED_USERS.add(target_guid)
    note = " و از لیست ویژه حذف شد" if was_special else ""
    text = f"🚫 کاربر `{target_guid}` بلاک شد{note}."
    await respond_and_cleanup(update, text, 15)
    _db_update_access(target_guid, "blocked", "add")
    if was_special:
        _db_update_access(target_guid, "special", "remove")


async def special_user(update, match):
    target_guid = await resolve_target_or_respond(
        update,
        match.group(1),
    )
    if target_guid is None:
        return
    was_blocked = target_guid in BLOCKED_USERS
    BLOCKED_USERS.discard(target_guid)
    if target_guid in SPECIAL_USERS:
        text = (
            f"⭐ کاربر `{target_guid}` قبلاً ویژه شده است."
        )
        await respond_and_cleanup(update, text, 10)
        return
    SPECIAL_USERS.add(target_guid)
    note = " و از بلاک خارج شد" if was_blocked else ""
    text = f"⭐ کاربر `{target_guid}` ویژه شد{note}."
    await respond_and_cleanup(update, text, 15)
    _db_update_access(target_guid, "special", "add")
    if was_blocked:
        _db_update_access(target_guid, "blocked", "remove")


async def close_group(update):
    try:
        await bot.set_group_default_access(
            update.object_guid,
            ["ViewMembers", "ViewAdmins", "AddMember"],
        )
        text = (
            "🔒 گروه بسته شد. "
            "فقط ادمین‌ها می‌توانند پیام بفرستند."
        )
        await respond_and_cleanup(update, text, 15)
    except Exception as error:
        log_error("close_group", error)
        await respond_and_cleanup(update, "❌ خطا در بستن گروه.", 10)


async def open_group(update):
    try:
        await bot.set_group_default_access(
            update.object_guid,
            [
                "ViewMembers",
                "ViewAdmins",
                "SendMessages",
                "AddMember",
            ],
        )
        text = "🔓 گروه باز شد. همه می‌توانند پیام بفرستند."
        await respond_and_cleanup(update, text, 15)
    except Exception as error:
        log_error("open_group", error)
        await respond_and_cleanup(
            update,
            "❌ خطا در باز کردن گروه.",
            10,
        )


async def add_admin(update, match):
    target_guid = await resolve_target_or_respond(
        update,
        match.group(1),
    )
    if target_guid is None:
        return
    if target_guid in ADMIN_GUIDS:
        text = f"⚠️ کاربر `{target_guid}` قبلاً ادمین است."
        await respond_and_cleanup(update, text, 10)
        return
    ADMIN_GUIDS.add(target_guid)
    text = (
        f"👑 کاربر `{target_guid}` به لیست ادمین‌ها اضافه شد."
    )
    await respond_and_cleanup(update, text, 15)
    _db_update_access(target_guid, "admin", "add")


async def remove_admin(update, match):
    target_guid = await resolve_target_or_respond(
        update,
        match.group(1),
    )
    if target_guid is None:
        return
    if target_guid == MAIN_ADMIN_GUID:
        await respond_and_cleanup(
            update,
            "⛔ نمی‌توانید ادمین اصلی را عزل کنید.",
            10,
        )
        return
    if target_guid not in ADMIN_GUIDS:
        text = f"⚠️ کاربر `{target_guid}` ادمین نیست."
        await respond_and_cleanup(update, text, 10)
        return
    ADMIN_GUIDS.remove(target_guid)
    text = f"❌ کاربر `{target_guid}` از لیست ادمین‌ها حذف شد."
    await respond_and_cleanup(update, text, 15)
    _db_update_access(target_guid, "admin", "remove")


async def delete_messages_command(update, match):
    count = int(match.group(1).translate(DIGIT_TABLE))
    if count < 1:
        return
    if count > 1000:
        text = "⚠️ حداکثر ۱۰۰۰ پیام را می‌توانید حذف کنید."
        await respond_and_cleanup(update, text, 10)
        return
    try:
        result = await bot.get_messages(
            update.object_guid,
            max_id="0",
            limit=str(count),
            sort="FromMax",
        )
        ids = extract_message_ids(result)[:count]
        if not ids:
            await respond_and_cleanup(
                update,
                "📭 پیامی برای حذف یافت نشد.",
                10,
            )
            return
        await bot.delete_messages(
            object_guid=update.object_guid,
            message_ids=ids,
        )
        text = f"🧹 {len(ids)} پیام با موفقیت حذف شد."
        await respond_and_cleanup(update, text, 10)
    except Exception as error:
        log_error("delete_messages_command", error)
        await respond_and_cleanup(update, "❌ خطا در حذف پیام‌ها.", 10)


async def ban_user(update, match):
    target_guid = await resolve_target_or_respond(
        update,
        match.group(1),
    )
    if target_guid is None:
        return
    if target_guid in ADMIN_GUIDS:
        await respond_and_cleanup(
            update,
            "⛔ نمی‌توانید ادمین را بن کنید.",
            10,
        )
        return
    try:
        await bot.ban_group_member(
            group_guid=update.object_guid,
            member_guid=target_guid,
            action="Set",
        )
        text = f"🚫 کاربر `{target_guid}` بن شد."
        await respond_and_cleanup(update, text, 15)
    except Exception as error:
        log_error("ban_user", error)
        await respond_and_cleanup(update, "❌ خطا در بن کردن کاربر.", 10)


async def unban_user(update, match):
    target_guid = await resolve_target_or_respond(
        update,
        match.group(1),
    )
    if target_guid is None:
        return
    try:
        await bot.ban_group_member(
            group_guid=update.object_guid,
            member_guid=target_guid,
            action="Unset",
        )
        try:
            link_info = await bot.get_group_link(update.object_guid)
            invite_link = getattr(link_info, "join_link", None)
            if invite_link:
                text = (
                    "✅ شما از گروه آنبن شدید.\n"
                    f"🔗 لینک گروه:\n{invite_link}"
                )
                await send_message_safe(target_guid, text)
        except Exception as error:
            log_error("unban_get_link", error)
        text = f"🔓 کاربر `{target_guid}` از بن خارج شد."
        await respond_and_cleanup(update, text, 15)
    except Exception as error:
        log_error("unban_user", error)
        await respond_and_cleanup(
            update,
            "❌ خطا در خارج کردن کاربر از بن.",
            10,
        )


def detach_game(chat_id, game):
    games = active_games.get(chat_id)
    if games is not None:
        games.pop(game["id"], None)
        if not games:
            active_games.pop(chat_id, None)
    cancel_game_timers(game)
    start_message_index.pop(game.get("start_msg_id"), None)


async def remove_game_by_id(chat_id, game_id, delete_banners=True):
    games = active_games.get(chat_id)
    if not games:
        return None
    game = games.pop(game_id, None)
    if game is None:
        return None
    cancel_game_timers(game)
    start_message_index.pop(game.get("start_msg_id"), None)
    if not games:
        active_games.pop(chat_id, None)
    if delete_banners:
        await delete_messages_safe(chat_id, [game.get("start_msg_id")])
        forwarded = game.get("forwarded_msg_id")
        if forwarded is not None:
            await delete_messages_safe(
                TARGET_GROUP_GUID,
                [forwarded],
            )
    return game


async def show_stats(update):
    await respond_and_cleanup(
        update,
        generate_daily_stats_text(),
        60,
    )


async def show_total_stats(update):
    await respond_and_cleanup(
        update,
        generate_total_stats_text(),
        60,
    )


async def show_user_stats(update, target_guid):
    await respond_and_cleanup(
        update,
        generate_user_stats_text(target_guid),
        60,
    )


async def help_handler(update):
    await respond_and_cleanup(update, HELP_TEXT, 20)


async def list_games(update):
    chat_id = update.object_guid
    games = active_games.get(chat_id)
    if not games:
        await respond_and_cleanup(
            update,
            "📭 لیست بازی‌ها خالی است.",
            20,
        )
        return
    now_mono = asyncio.get_running_loop().time()
    lines = ["📋 لیست بازی‌های فعال:"]
    for game in games.values():
        start_mono = game.get("start_mono", now_mono)
        hours = (now_mono - start_mono) / 3600
        warning = "⚠️" if hours >= WARNING_AFTER_HOURS else ""
        lines.append(
            f"🆔 شناسه بازی: `{game['id']}` {warning}\n"
            f"🎭 سناریو: {game['scenario_caption']}\n"
            f"🛠️ سازنده: {game['builder']}\n"
            f"⏰ زمان استارت: {game['start_time']}\n"
            f"⏳ مدت: {hours:.1f} ساعت\n"
            "➖➖➖➖➖➖➖➖"
        )
    await respond_and_cleanup(update, "\n".join(lines), 20)


async def delete_specific_game(update, match):
    chat_id = update.object_guid
    game_id = f"{int(match.group(1).translate(DIGIT_TABLE)):02d}"
    game = await remove_game_by_id(chat_id, game_id)
    if game is None:
        text = f"🔍 بازی با شناسه `{game_id}` یافت نشد."
        await respond_and_cleanup(update, text, 20)
        return
    text = f"✅ بازی `{game_id}` با موفقیت حذف شد."
    await respond_and_cleanup(update, text, 20)


async def delete_all_games(update):
    chat_id = update.object_guid
    games = active_games.pop(chat_id, None)
    if not games:
        await respond_and_cleanup(
            update,
            "📭 هیچ بازی فعالی نیست.",
            20,
        )
        return
    start_ids = []
    forward_ids = []
    for game in games.values():
        cancel_game_timers(game)
        start_message_index.pop(game.get("start_msg_id"), None)
        start_id = game.get("start_msg_id")
        if start_id is not None:
            start_ids.append(start_id)
        forwarded = game.get("forwarded_msg_id")
        if forwarded is not None:
            forward_ids.append(forwarded)
    await delete_messages_safe(chat_id, start_ids)
    await delete_messages_safe(TARGET_GROUP_GUID, forward_ids)
    await respond_and_cleanup(update, "🧹 تمامی بازی‌ها حذف شدند.", 20)


async def process_start(update, match):
    chat_id = update.object_guid
    user_guid = update.author_guid or ""
    download_task = None
    try:
        scenario_part = match.group(1).strip()
        builder_fa = match.group(2).strip()
        should_forward = match.group(3) is not None

        scenario_words = scenario_part.split()
        has_donyto = False
        filtered_words = []
        for word in scenario_words:
            if word in DUNYTO_VARIATIONS:
                has_donyto = True
            else:
                filtered_words.append(word)

        if has_donyto:
            scenario_fa = " ".join(filtered_words)
            if scenario_fa:
                scenario_caption = f"{scenario_fa} ➪ دُنیتو"
            else:
                scenario_caption = "دُنیتو"
        else:
            scenario_caption = scenario_part

        builder_en, corrected_name = normalize_builder_name(builder_fa)
        message = update.message
        file_inline = getattr(message, "file_inline", None)
        if file_inline is None:
            return

        download_task = asyncio.create_task(bot.download(file_inline))
        download_task.add_done_callback(_silent_done)

        now = get_shamsi_now()
        caption = (
            "🌱بِه نامِ خوبی راستی و پاکی 🌱\n\n"
            f"🧑‍💻سازنده دک: ✺ DoN 𖤍 {builder_en}✺\n\n"
            f"📜سناریو: {scenario_caption}\n\n"
            f"⏱︎ساعت شروع : {now}\n\n"
            "🔖برای عضویت و ارتباط با لیدر گروه:\n\n"
            "@Don55555\n\n"
            "𒆜ادب احترام میاره❥︎احترام اعتبار𒆜"
        )

        correction_note = ""
        if corrected_name:
            correction_note = (
                f"\n\n⚠️ نام '{builder_fa}' "
                f"به '{corrected_name}' اصلاح شد."
            )

        file_meta = {}
        file_name = getattr(file_inline, "file_name", None)
        width = getattr(file_inline, "width", None)
        height = getattr(file_inline, "height", None)
        if file_name is not None:
            file_meta["file_name"] = file_name
        if width is not None:
            file_meta["width"] = width
        if height is not None:
            file_meta["height"] = height

        old_banner = pending_banners.get(user_guid)
        if old_banner is not None:
            handle = old_banner.pop("expire_handle", None)
            if handle is not None:
                handle.cancel()
            old_task = old_banner.get("download_task")
            if old_task is not None and not old_task.done():
                old_task.cancel()
            old_preview = old_banner.get("preview_msg_id")
            if old_preview is not None:
                pending_by_preview.pop(old_preview, None)
                spawn(
                    delete_messages_safe(
                        old_banner["chat_id"],
                        [old_preview],
                    )
                )

        banner_data = {
            "chat_id": chat_id,
            "file_inline": file_inline,
            "download_task": download_task,
            "photo_raw": None,
            "caption": caption,
            "file_meta": file_meta,
            "should_forward": should_forward,
            "scenario_caption": scenario_caption,
            "builder_en": builder_en,
            "now": now,
            "creator_guid": user_guid,
            "builder_fa": builder_fa,
            "user_msg_id": update.message_id,
        }
        pending_banners[user_guid] = banner_data

        preview_text = (
            f"⚠️ پیش‌نمایش بنر{correction_note}\n\n"
            f"{caption}\n\n"
            "آیا اطلاعات صحیح است؟\n"
            "✅ برای تایید کلمه بله را ریپلای کنید.\n"
            "❌ برای رد کردن کلمه نه را ریپلای کنید."
        )

        preview_msg = await bot.send_message(
            object_guid=chat_id,
            text=preview_text,
            reply_to_message_id=update.message_id,
        )
        preview_msg_id = getattr(preview_msg, "message_id", None)
        if preview_msg_id is None:
            preview_msg_id = extract_message_id(preview_msg)
        if preview_msg_id is None:
            pending_banners.pop(user_guid, None)
            if not download_task.done():
                download_task.cancel()
            return

        banner_data["preview_msg_id"] = preview_msg_id
        pending_by_preview[preview_msg_id] = user_guid
        banner_data["expire_handle"] = (
            asyncio.get_running_loop().call_later(
                PENDING_EXPIRE_SECONDS,
                expire_pending,
                user_guid,
                preview_msg_id,
            )
        )
    except Exception as error:
        if download_task is not None and not download_task.done():
            download_task.cancel()
        pending_banners.pop(user_guid, None)
        log_error("process_start", error)


async def confirm_banner(update, banner, preview_msg_id):
    raw = banner.get("photo_raw")
    if raw is None:
        task = banner.get("download_task")
        if task is not None:
            raw = await task
            banner["photo_raw"] = raw
        else:
            raw = await bot.download(banner["file_inline"])

    sent = await bot.send_photo(
        object_guid=banner["chat_id"],
        photo=raw,
        caption=banner["caption"],
        **banner["file_meta"],
    )
    sent_msg_id = getattr(sent, "message_id", None)
    if sent_msg_id is None:
        sent_msg_id = extract_message_id(sent)

    chat_id = banner["chat_id"]
    games = active_games.setdefault(chat_id, {})
    game_id = find_available_game_id(games)
    loop = asyncio.get_running_loop()

    game = {
        "id": game_id,
        "start_msg_id": sent_msg_id,
        "scenario_caption": banner["scenario_caption"],
        "builder": banner["builder_en"],
        "creator_guid": banner.get("creator_guid", ""),
        "should_forward": banner["should_forward"],
        "start_time": banner["now"],
        "start_mono": loop.time(),
        "forwarded_msg_id": None,
        "timeout_warned": False,
        "closing": False,
    }
    games[game_id] = game

    if sent_msg_id is not None:
        start_message_index[sent_msg_id] = (chat_id, game_id)

    game["warn_handle"] = loop.call_later(
        WARNING_AFTER_HOURS * 3600,
        _game_warning,
        chat_id,
        game_id,
    )
    game["close_handle"] = loop.call_later(
        AUTO_CLOSE_AFTER_HOURS * 3600,
        _game_close,
        chat_id,
        game_id,
    )

    update_stats(
        banner["builder_en"],
        banner["scenario_caption"],
        banner.get("creator_guid"),
    )

    if banner["should_forward"] and sent_msg_id is not None:
        get_forward_queue().put_nowait(
            {
                "from_guid": chat_id,
                "message_id": sent_msg_id,
                "chat_id": chat_id,
                "game_id": game_id,
            }
        )

    await delete_messages_safe(
        chat_id,
        [
            preview_msg_id,
            banner.get("user_msg_id"),
            update.message_id,
        ],
    )


async def reject_banner(update, banner, preview_msg_id):
    text = "♻️ بنر رد شد. لطفاً نسخه صحیح را مجدداً ارسال کنید."
    await send_message_safe(
        banner["chat_id"],
        text,
        update.message_id,
        15,
    )
    await delete_messages_safe(
        banner["chat_id"],
        [
            preview_msg_id,
            banner.get("user_msg_id"),
            update.message_id,
        ],
    )


async def confirm_end(update, end_data, preview_msg_id):
    raw = end_data.get("photo_raw")
    if raw is None:
        task = end_data.get("download_task")
        if task is not None:
            raw = await task
            end_data["photo_raw"] = raw
        else:
            raw = await bot.download(end_data["file_inline"])

    chat_id = end_data["chat_id"]
    game_id = end_data["game_id"]
    games = active_games.get(chat_id)
    if not games:
        await respond_and_cleanup(update, "📭 بازی یافت نشد.", 15)
        return
    game = games.get(game_id)
    if game is None:
        await respond_and_cleanup(update, "📭 بازی یافت نشد.", 15)
        return

    sent_end = await bot.send_photo(
        object_guid=chat_id,
        photo=raw,
        caption=end_data["caption"],
        reply_to_message_id=game.get("start_msg_id"),
        **end_data["file_meta"],
    )
    sent_end_id = getattr(sent_end, "message_id", None)
    if sent_end_id is None:
        sent_end_id = extract_message_id(sent_end)

    detach_game(chat_id, game)

    if end_data["should_forward"] and sent_end_id is not None:
        get_forward_queue().put_nowait(
            {
                "from_guid": chat_id,
                "message_id": sent_end_id,
            }
        )

    await delete_messages_safe(
        chat_id,
        [
            preview_msg_id,
            end_data.get("user_msg_id"),
            update.message_id,
        ],
    )


async def reject_end(update, end_data, preview_msg_id):
    text = (
        "♻️ بنر پایان رد شد. "
        "لطفاً نسخه صحیح را مجدداً ارسال کنید."
    )
    await send_message_safe(
        end_data["chat_id"],
        text,
        update.message_id,
        15,
    )
    await delete_messages_safe(
        end_data["chat_id"],
        [
            preview_msg_id,
            end_data.get("user_msg_id"),
            update.message_id,
        ],
    )


async def process_confirmation(update, reply_id, word):
    if reply_id in pending_by_preview:
        target_user_guid = pending_by_preview[reply_id]
        author = update.author_guid or ""
        if author != target_user_guid:
            text = (
                "❌ فقط ارسال‌کننده اصلی بنر "
                "می‌تواند آن را تأیید یا رد کند."
            )
            await respond_and_cleanup(update, text, 10)
            return
        if reply_id in processing_previews:
            return
        processing_previews.add(reply_id)
        banner = None
        try:
            banner = pending_banners.get(target_user_guid)
            if banner is None or banner.get("preview_msg_id") != reply_id:
                pending_by_preview.pop(reply_id, None)
                return
            handle = banner.get("expire_handle")
            if handle is not None:
                handle.cancel()
            if word in CONFIRM_WORDS:
                await confirm_banner(update, banner, reply_id)
            else:
                task = banner.get("download_task")
                if task is not None and not task.done():
                    task.cancel()
                await reject_banner(update, banner, reply_id)
            pending_banners.pop(target_user_guid, None)
            pending_by_preview.pop(reply_id, None)
        except Exception as error:
            pending_banners.pop(target_user_guid, None)
            pending_by_preview.pop(reply_id, None)
            if banner is not None:
                task = banner.get("download_task")
                if task is not None and not task.done():
                    task.cancel()
            log_error("process_confirmation", error)
            await respond_and_cleanup(
                update,
                "❌ خطا در پردازش بنر.",
                10,
            )
        finally:
            processing_previews.discard(reply_id)
    elif reply_id in pending_end_by_preview:
        await process_end_confirmation(update, reply_id, word)


async def process_end_confirmation(update, reply_id, word):
    target_user_guid = pending_end_by_preview.get(reply_id)
    if target_user_guid is None:
        return
    author = update.author_guid or ""
    if author != target_user_guid:
        text = (
            "❌ فقط ارسال‌کننده اصلی بنر پایان "
            "می‌تواند آن را تأیید یا رد کند."
        )
        await respond_and_cleanup(update, text, 10)
        return
    if reply_id in processing_previews:
        return
    processing_previews.add(reply_id)
    end_data = None
    try:
        end_data = pending_ends.get(target_user_guid)
        if end_data is None or end_data.get("preview_msg_id") != reply_id:
            pending_end_by_preview.pop(reply_id, None)
            return
        handle = end_data.get("expire_handle")
        if handle is not None:
            handle.cancel()
        if word in CONFIRM_WORDS:
            await confirm_end(update, end_data, reply_id)
        else:
            task = end_data.get("download_task")
            if task is not None and not task.done():
                task.cancel()
            await reject_end(update, end_data, reply_id)
        pending_ends.pop(target_user_guid, None)
        pending_end_by_preview.pop(reply_id, None)
    except Exception as error:
        pending_ends.pop(target_user_guid, None)
        pending_end_by_preview.pop(reply_id, None)
        if end_data is not None:
            task = end_data.get("download_task")
            if task is not None and not task.done():
                task.cancel()
        log_error("process_end_confirmation", error)
        await respond_and_cleanup(
            update,
            "❌ خطا در پردازش بنر پایان.",
            10,
        )
    finally:
        processing_previews.discard(reply_id)


async def process_end(update, match):
    chat_id = update.object_guid
    user_guid = update.author_guid or ""
    reply_id = getattr(update.message, "reply_to_message_id", None)
    download_task = None
    try:
        winner = match.group(1).strip()
        should_forward = match.group(2) is not None

        games = active_games.get(chat_id)
        if not games:
            await respond_and_cleanup(
                update,
                "📭 بازی فعالی ثبت نشده است.",
                15,
            )
            return

        game = None
        if reply_id:
            indexed = start_message_index.get(reply_id)
            if indexed is not None and indexed[0] == chat_id:
                game = games.get(indexed[1])
            if game is None:
                game = next(
                    (
                        item
                        for item in games.values()
                        if item.get("start_msg_id") == reply_id
                    ),
                    None,
                )
        if game is None and reply_id is None:
            game = next(iter(games.values()), None)

        if game is None:
            await respond_and_cleanup(
                update,
                "🔍 بازی مرتبط با این ریپلای یافت نشد.",
                15,
            )
            return

        file_inline = getattr(update.message, "file_inline", None)
        if file_inline is None:
            return

        download_task = asyncio.create_task(bot.download(file_inline))
        download_task.add_done_callback(_silent_done)

        now = get_shamsi_now()
        caption = (
            "🏆🏆🏆🏆🏆🏆🏆🏆\n\n"
            f"🎞سناریو: {game['scenario_caption']}\n\n"
            f"🧑‍💻سازنده لابی: ✺DσN 𖤍 {game['builder']}✺\n\n"
            f"🥇برنده : {winner} ➪ 🏆\n\n"
            f"⏱︎ساعت پایان : {now}\n\n"
            "مافیا های زندگیت رو بشناس 🔥🔥🔥\n\n"
            "🔖عضویت و ارتباط با لیدر گروه:\n\n@DoN55555\n\n"
            "𒆜ادب احترام میاره❥︎احترام اعتبار𒆜"
        )

        file_meta = {}
        file_name = getattr(file_inline, "file_name", None)
        width = getattr(file_inline, "width", None)
        height = getattr(file_inline, "height", None)
        if file_name is not None:
            file_meta["file_name"] = file_name
        if width is not None:
            file_meta["width"] = width
        if height is not None:
            file_meta["height"] = height

        old_end = pending_ends.get(user_guid)
        if old_end is not None:
            handle = old_end.pop("expire_handle", None)
            if handle is not None:
                handle.cancel()
            old_task = old_end.get("download_task")
            if old_task is not None and not old_task.done():
                old_task.cancel()
            old_preview = old_end.get("preview_msg_id")
            if old_preview is not None:
                pending_end_by_preview.pop(old_preview, None)
                spawn(
                    delete_messages_safe(
                        old_end["chat_id"],
                        [old_preview],
                    )
                )

        end_data = {
            "chat_id": chat_id,
            "game_id": game["id"],
            "file_inline": file_inline,
            "download_task": download_task,
            "photo_raw": None,
            "caption": caption,
            "file_meta": file_meta,
            "should_forward": should_forward,
            "winner": winner,
            "now": now,
            "creator_guid": user_guid,
            "user_msg_id": update.message_id,
        }
        pending_ends[user_guid] = end_data

        preview_text = (
            "⚠️ پیش‌نمایش بنر پایان\n\n"
            f"{caption}\n\n"
            "آیا اطلاعات صحیح است؟\n"
            "✅ برای تایید کلمه بله را ریپلای کنید.\n"
            "❌ برای رد کردن کلمه نه را ریپلای کنید."
        )

        preview_msg = await bot.send_message(
            object_guid=chat_id,
            text=preview_text,
            reply_to_message_id=update.message_id,
        )
        preview_msg_id = getattr(preview_msg, "message_id", None)
        if preview_msg_id is None:
            preview_msg_id = extract_message_id(preview_msg)
        if preview_msg_id is None:
            pending_ends.pop(user_guid, None)
            if not download_task.done():
                download_task.cancel()
            return

        end_data["preview_msg_id"] = preview_msg_id
        pending_end_by_preview[preview_msg_id] = user_guid
        end_data["expire_handle"] = (
            asyncio.get_running_loop().call_later(
                PENDING_EXPIRE_SECONDS,
                expire_pending_end,
                user_guid,
                preview_msg_id,
            )
        )
    except Exception as error:
        if download_task is not None and not download_task.done():
            download_task.cancel()
        pending_ends.pop(user_guid, None)
        log_error("process_end", error)


@bot.on_message_updates(MAIN_GROUP_FILTER, filters.photo)
async def handle_photo(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if not consume_message_id(update.message_id):
        return
    if not is_user_allowed(update):
        return
    text = getattr(update.message, "text", None) or ""
    text = text.translate(NORMALIZE_TABLE).strip()
    if not text:
        return
    match = START_REGEX.match(text)
    if match:
        await process_start(update, match)
        return
    match = END_REGEX.match(text)
    if match:
        await process_end(update, match)


@bot.on_message_updates(MAIN_GROUP_FILTER, filters.text)
async def handle_text(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    message = update.message
    if getattr(message, "file_inline", None) is not None:
        return
    if not consume_message_id(update.message_id):
        return
    text = getattr(message, "text", None) or ""
    text = text.strip()
    if not text:
        return
    normalized = normalize_text(text)
    if not normalized:
        return
    word = first_word(normalized)
    if not word:
        return

    reply_id = getattr(message, "reply_to_message_id", None)
    if reply_id and (word in CONFIRM_WORDS or word in REJECT_WORDS):
        if is_user_allowed(update):
            await process_confirmation(update, reply_id, word)
        return

    author = update.author_guid
    if author == MAIN_ADMIN_GUID:
        if normalized == "!stop":
            await admin_stop(update)
            return
        if normalized == "!start":
            await admin_start(update)
            return

    if author in ADMIN_GUIDS:
        match = AUTO_STATS_SET_REGEX.match(normalized)
        if match:
            await set_auto_stats(update, match)
            return
        if AUTO_STATS_DISABLE_REGEX.match(normalized):
            await disable_auto_stats(update)
            return
        if CLOSE_GROUP_REGEX.match(normalized):
            await close_group(update)
            return
        if OPEN_GROUP_REGEX.match(normalized):
            await open_group(update)
            return
        match = DELETE_MESSAGES_REGEX.match(normalized)
        if match:
            await delete_messages_command(update, match)
            return

    if author == MAIN_ADMIN_GUID:
        match = ADD_ADMIN_REGEX.match(normalized)
        if match:
            await add_admin(update, match)
            return
        match = REMOVE_ADMIN_REGEX.match(normalized)
        if match:
            await remove_admin(update, match)
            return

    if not is_user_allowed(update):
        return

    if word in STATS_WORDS:
        if reply_id:
            target_guid = None
            indexed = start_message_index.get(reply_id)
            if indexed is not None:
                games = active_games.get(indexed[0])
                if games:
                    game = games.get(indexed[1])
                    if game is not None:
                        target_guid = game.get("creator_guid")
            if not target_guid:
                target_guid = await get_reply_author_guid(update)
            if target_guid:
                await show_user_stats(update, target_guid)
                return
        parts = normalized.split(maxsplit=1)
        second = ""
        if len(parts) > 1:
            second = first_word(parts[1])
        if second in TOTAL_STATS_WORDS:
            await show_total_stats(update)
        else:
            await show_stats(update)
        return

    if word in HELP_WORDS:
        await help_handler(update)
        return

    if LIST_GAMES_REGEX.match(normalized):
        await list_games(update)
        return

    if DELETE_ALL_REGEX.match(normalized):
        await delete_all_games(update)
        return

    match = DELETE_GAME_REGEX.match(normalized)
    if match:
        await delete_specific_game(update, match)
        return

    if author in ADMIN_GUIDS:
        match = BLOCK_REGEX.match(normalized)
        if match:
            await block_user(update, match)
            return
        match = SPECIAL_REGEX.match(normalized)
        if match:
            await special_user(update, match)
            return
        match = BAN_REGEX.match(normalized)
        if match:
            await ban_user(update, match)
            return
        match = UNBAN_REGEX.match(normalized)
        if match:
            await unban_user(update, match)
            return


if __name__ == "__main__":
    uvloop.install()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    _init_storage()

    logger.info("ربات دُنیتو راه‌اندازی شد")
    logger.info(
        "وضعیت اولیه: %s",
        "فعال" if IS_BOT_ACTIVE else "متوقف",
    )
    logger.info("شناسه ادمین اصلی: %s", MAIN_ADMIN_GUID)
    logger.info(
        "حالت ذخیره‌سازی: %s",
        "database" if USE_DATABASE else "memory",
    )

    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("ربات توسط کاربر متوقف شد.")
    except Exception:
        logger.exception("خطای مرگبار")
    finally:
        try:
            if hasattr(bot, "disconnect"):
                loop.run_until_complete(bot.disconnect())
            elif hasattr(bot, "close"):
                loop.run_until_complete(bot.close())
        except Exception:
            pass
        if _DB_QUEUE is not None:
            _DB_QUEUE.put(None)
        if _DB_THREAD is not None:
            _DB_THREAD.join(timeout=2)
