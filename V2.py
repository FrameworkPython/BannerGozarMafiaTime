import asyncio
import logging
import re
from collections import deque

import jdatetime
from rubpy import Client, filters

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(
    logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
)
logger = logging.getLogger("DonitoBot")
logger.setLevel(logging.DEBUG)
logger.addHandler(console_handler)
logger.propagate = False

TARGET_GROUP_GUID = "g0DHpOn042b93c4982b5b135365c7bb6"
MAIN_GROUP_GUID = "g0E19S900dd50643ab8fcbf23dad9e70"
MAIN_ADMIN_GUID = "u0JNjam04cd438e3013ebd0111bc3fb3"
ADMIN_GUIDS = {MAIN_ADMIN_GUID}
IS_BOT_ACTIVE = True
WARNING_AFTER_HOURS = 5
AUTO_CLOSE_AFTER_HOURS = 6
FORWARD_QUEUE_DELAY = 10

MAIN_GROUP_FILTER = filters.object_guids([MAIN_GROUP_GUID])

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

DUNYTO_VARIATIONS = {"دنیتو", "دونیتو", "دُنیتو"}

PERSIAN_TO_FINGLISH_MAP = {
    "ا": "a", "آ": "a", "ب": "b", "پ": "p", "ت": "t", "ث": "s",
    "ج": "j", "چ": "ch", "ح": "h", "خ": "kh", "د": "d", "ذ": "z",
    "ر": "r", "ز": "z", "ژ": "zh", "س": "s", "ش": "sh", "ص": "s",
    "ض": "z", "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f",
    "ق": "gh", "ک": "k", "گ": "g", "ل": "l", "م": "m", "ن": "n",
    "و": "oo", "ه": "h", "ی": "i", "ي": "i", "ئ": "e", " ": " ",
    "؟": "?", "،": ",", "؛": ";", "۰": "0", "۱": "1", "۲": "2",
    "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8",
    "۹": "9", "َ": "a", "ُ": "o", "ِ": "e",
}

TRANS_TABLE = str.maketrans(PERSIAN_TO_FINGLISH_MAP)

START_REGEX = re.compile(
    r"^(?!پایان[\s,،])([^,،]+)[,،]\s*([^,،]+)(?:[,،]\s*(فور))?$"
)
END_REGEX = re.compile(r"^پایان[\s,،]+(.+?)(?:\s*[,،]?\s*(فور))?$")
CONFIRM_REGEX = re.compile(r"^(بله|آره|اوکی|تایید)$", re.IGNORECASE)
REJECT_REGEX = re.compile(r"^(نه|خیر|رد|لغو)$", re.IGNORECASE)
STOP_REGEX = re.compile(r"^!stop$", re.IGNORECASE)
BOT_START_REGEX = re.compile(r"^!start$", re.IGNORECASE)
STATS_REGEX = re.compile(r"^(آمار|stats|امار)$", re.IGNORECASE)
HELP_REGEX = re.compile(r"^راهنما$")
LIST_GAMES_REGEX = re.compile("^لیست\\s+بازی(?:[\\s\u200c]*ها)?$")
DELETE_GAME_REGEX = re.compile(r"^حذف\s+بازی\s+(\d+)$")
DELETE_ALL_REGEX = re.compile(
    "^حذف(?:[\\s\u200c]+تمام)?[\\s\u200c]+بازی[\\s\u200c]*ها$"
)
AUTO_STATS_SET_REGEX = re.compile(
    r"^آمار\s+خودکار\s+ساعت\s+(\d{1,2}:\d{2})$"
)
AUTO_STATS_DISABLE_REGEX = re.compile(
    r"^(لغو|حذف)\s+آمار\s+خودکار$"
)
BLOCK_REGEX = re.compile(r"^بلاک(?:\s+(\S+))?$")
SPECIAL_REGEX = re.compile(r"^ویژه(?:\s+(\S+))?$")
CLOSE_GROUP_REGEX = re.compile(
    r"^(بستن|بستن گروه|بستن چت|قفل|قفل گروه|قفل چت)$"
)
OPEN_GROUP_REGEX = re.compile(
    r"^(باز کردن|باز کردن گروه|باز کردن چت|بازکردن|بازکردن گروه|بازکردن چت)$"
)
ADD_ADMIN_REGEX = re.compile(r"^(ادمین کن|ادمین‌کن|افزودن ادمین)(?:\s+(\S+))?$")
REMOVE_ADMIN_REGEX = re.compile(r"^(عزل ادمین|حذف ادمین|برداشتن ادمین)(?:\s+(\S+))?$")
DELETE_MESSAGES_REGEX = re.compile(r"^حذف\s+پیام(?:\s+)?(\d+)$")
BAN_REGEX = re.compile(r"^(بن|بن کن|اخراج|حذف کن|اخراج کن)(?:\s+(\S+))?$")
UNBAN_REGEX = re.compile(r"^(آنبن|آنبن کن|لغو بن|لغو اخراج|برگردان)(?:\s+(\S+))?$")

HELP_TEXT = (
    "📖 راهنمای کامل ربات بنرگذار دُنیتو\n\n"

    "🎮 شروع بازی (کاربران ویژه)\n"
    "• یک عکس با کپشن زیر بفرستید:\n"
    "[سناریو] ، [سازنده] ، فور\n"
    "• «فور» اختیاری است (فوروارد به گروه رسمی).\n"
    "• اگر «دنیتو» در سناریو باشد، خودکار به کپشن اضافه می‌شود.\n"
    "• مثال: مذاکره دنیتو ، هانتر ، فور\n\n"

    "✅ تأیید / ❌ رد بنر\n"
    "• بعد از ارسال عکس، پیش‌نمایشی دریافت می‌کنید.\n"
    "• با ریپلای روی پیش‌نمایش یکی از کلمات زیر را بفرستید:\n"
    "تأیید: بله / آره / اوکی / تایید\n"
    "رد: نه / خیر / رد / لغو\n"
    "• فقط سازندۀ اصلی می‌تواند تأیید/رد کند.\n\n"

    "🏁 پایان بازی\n"
    "• یک عکس با کپشن زیر بفرستید:\n"
    "پایان [برنده] ، فور\n"
    "• «فور» اختیاری است.\n"
    "• در صورت وجود چند بازی، قدیمی‌ترین بسته می‌شود.\n"
    "• می‌توانید روی بنر شروع ریپلای بزنید.\n\n"

    "📊 آمار و اطلاعات\n"
    "• آمار: آمار / stats\n"
    "• راهنما: راهنما\n"
    "• لیست بازی‌های فعال: لیست بازی‌ها\n"
    "• حذف یک بازی: حذف بازی 01\n"
    "• حذف تمام بازی‌ها: حذف تمام بازی‌ها\n\n"

    "👑 دستورات مدیریت گروه (ادمین‌ها)\n"
    "• قفل گروه (فقط ادمین‌ها پیام بدهند):\n"
    "قفل / قفل گروه / بستن / بستن گروه\n"
    "• باز کردن گروه: بازکردن / باز کردن گروه\n\n"

    "🔨 مدیریت کاربران (ادمین‌ها)\n"
    "• ویژه کردن (با ریپلای یا آیدی): ویژه / ویژه u0xxx\n"
    "• بلاک کردن: بلاک / بلاک u0xxx\n"
    "• بن کردن: بن / اخراج / حذف کن\n"
    "• آنبن + ارسال لینک: آنبن / برگردان / لغو بن\n\n"

    "⚙️ مدیریت ادمین‌ها (فقط ادمین اصلی)\n"
    "• افزودن ادمین: ادمین کن / افزودن ادمین u0xxx\n"
    "• حذف ادمین: عزل ادمین / حذف ادمین\n\n"

    "🧹 پاکسازی پیام‌ها (ادمین‌ها)\n"
    "• حذف پیام 20\n"
    "حداکثر ۱۰۰۰ پیام آخر (جدیدترین‌ها) حذف می‌شود.\n\n"

    "⏰ آمار خودکار (ادمین‌ها)\n"
    "• تنظیم: آمار خودکار ساعت 00:00\n"
    "• لغو: لغو آمار خودکار / حذف آمار خودکار\n\n"

    "🛑 توقف و راه‌اندازی ربات (فقط ادمین اصلی)\n"
    "• توقف: !stop\n"
    "• راه‌اندازی: !start\n"
)


active_games = {}
pending_banners = {}
forward_queue = deque()
game_stats = {
    "total_games": 0,
    "builder_stats": {},
    "scenario_stats": {},
    "daily_games": 0,
    "last_reset": "",
}
forward_worker = None
timeout_worker = None
auto_stats_worker = None

BLOCKED_USERS = set()
SPECIAL_USERS = set()
AUTO_STATS_ENABLED = False
AUTO_STATS_TIME = None
LAST_AUTO_STATS_DATE = ""


def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def persian_to_finglish(text):
    return text.translate(TRANS_TABLE).title().replace(" ", "")


def normalize_builder_name(raw):
    key = " ".join(raw.split())
    if key in NAME_MAP:
        return NAME_MAP[key], None
    best_match = None
    min_distance = 1
    for name, mapped in NAME_MAP.items():
        distance = levenshtein_distance(key, name)
        if distance <= min_distance:
            min_distance = distance
            best_match = (mapped, name)
    if best_match:
        return best_match
    return persian_to_finglish(key), None


def get_shamsi_now():
    return jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")


def get_shamsi_date():
    return jdatetime.datetime.now().strftime("%Y/%m/%d")


def log_error(context, error):
    logger.exception(
        f"{context} | خطا: {type(error).__name__} | پیام: {error}"
    )


def extract_message_id(result):
    if result is None:
        return None
    if isinstance(result, int):
        return result
    if isinstance(result, str):
        return int(result) if result.isdigit() else None
    if isinstance(result, dict):
        value = result.get("message_ids") or result.get("message_id")
    elif isinstance(result, (list, tuple)):
        value = result[0] if result else None
    else:
        value = getattr(result, "message_ids", None)
        if value is None:
            value = getattr(result, "message_id", None)
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("message_id") or value.get("id")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value) if value.isdigit() else None
    return value


def find_available_game_id(chat_id):
    games = active_games[chat_id]["games"]
    used = {game["id"] for game in games}
    for i in range(1, 100):
        candidate = f"{i:02d}"
        if candidate not in used:
            return candidate
    return "XX"


def parse_time_to_hours(time_str):
    try:
        date_part, time_part = time_str.split(" - ")
        year, month, day = map(int, date_part.split("/"))
        hour, minute = map(int, time_part.split(":"))
        start_dt = jdatetime.datetime(year, month, day, hour, minute)
        delta = jdatetime.datetime.now() - start_dt
        return delta.total_seconds() / 3600
    except Exception:
        return 0


def is_user_allowed(update):
    if update.author_guid in ADMIN_GUIDS:
        return True
    if not IS_BOT_ACTIVE:
        return False
    if update.author_guid in BLOCKED_USERS:
        return False
    if SPECIAL_USERS:
        return update.author_guid in SPECIAL_USERS
    return True


def update_stats(builder, scenario):
    today = get_shamsi_date()
    if game_stats["last_reset"] != today:
        game_stats["daily_games"] = 0
        game_stats["last_reset"] = today
    game_stats["total_games"] += 1
    game_stats["daily_games"] += 1
    builder_stats = game_stats["builder_stats"]
    scenario_stats = game_stats["scenario_stats"]
    builder_stats[builder] = builder_stats.get(builder, 0) + 1
    scenario_stats[scenario] = scenario_stats.get(scenario, 0) + 1


def generate_stats_text():
    today = get_shamsi_date()
    if game_stats["last_reset"] != today:
        game_stats["daily_games"] = 0
        game_stats["last_reset"] = today
    top_builders = sorted(
        game_stats["builder_stats"].items(),
        key=lambda item: item[1],
        reverse=True,
    )[:3]
    top_scenarios = sorted(
        game_stats["scenario_stats"].items(),
        key=lambda item: item[1],
        reverse=True,
    )[:3]
    builder_lines = "\n".join(
        f"{i}. {name}: {count} بازی"
        for i, (name, count) in enumerate(top_builders, 1)
    ) or "📭 داده‌ای موجود نیست"
    scenario_lines = "\n".join(
        f"{i}. {name}: {count} بازی"
        for i, (name, count) in enumerate(top_scenarios, 1)
    ) or "📭 داده‌ای موجود نیست"
    total_games = game_stats["total_games"]
    daily_games = game_stats["daily_games"]
    return (
        "📊 آمار ربات دُنیتو\n\n"
        f"📅 تاریخ: {today}\n"
        f"🎮 کل بازی‌های برگزار شده: {total_games}\n"
        f"📈 بازی‌های امروز: {daily_games}\n\n"
        f"🥇 ۳ سازنده برتر:\n{builder_lines}\n\n"
        f"🎭 ۳ سناریوی محبوب:\n{scenario_lines}"
    )


async def forward_queue_processor():
    logger.info("کارگر صف فوروارد فعال شد.")
    while True:
        if forward_queue and IS_BOT_ACTIVE:
            task = forward_queue.popleft()
            try:
                result = await asyncio.wait_for(
                    bot.forward_messages(
                        from_object_guid=task["from_guid"],
                        message_ids=[task["message_id"]],
                        to_object_guid=TARGET_GROUP_GUID,
                    ),
                    timeout=30,
                )
                forwarded_msg_id = extract_message_id(result)
                chat_id = task.get("chat_id")
                game_id = task.get("game_id")
                if chat_id and game_id and forwarded_msg_id is not None:
                    games = active_games.get(chat_id, {}).get("games")
                    if games:
                        for game in games:
                            if game["id"] == game_id:
                                game["forwarded_msg_id"] = forwarded_msg_id
                                break
                logger.info(
                    f"فوروارد از صف انجام شد: {task['message_id']}"
                )
            except Exception as e:
                log_error("فوروارد از صف", e)
                task["retries"] = task.get("retries", 0) + 1
                if task["retries"] < 3:
                    forward_queue.append(task)
            await asyncio.sleep(FORWARD_QUEUE_DELAY)
        else:
            await asyncio.sleep(1)


async def game_timeout_checker():
    logger.info("کارگر بررسی زمان بازی‌ها فعال شد.")
    while True:
        await asyncio.sleep(60)
        if not IS_BOT_ACTIVE:
            continue
        try:
            for chat_id, data in active_games.items():
                games = data.get("games", deque())
                for game in list(games):
                    hours = parse_time_to_hours(game.get("start_time", ""))
                    if hours >= AUTO_CLOSE_AFTER_HOURS:
                        try:
                            await bot.delete_messages(
                                object_guid=chat_id,
                                message_ids=[game["start_msg_id"]],
                            )
                        except Exception as e:
                            log_error("حذف بنر اصلی", e)
                        if game.get("forwarded_msg_id") is not None:
                            try:
                                await bot.delete_messages(
                                    object_guid=TARGET_GROUP_GUID,
                                    message_ids=[game["forwarded_msg_id"]],
                                )
                            except Exception as e:
                                log_error("حذف بنر فوروارد", e)
                        games.remove(game)
                        logger.info(
                            f"بازی {game['id']} به صورت خودکار بسته شد "
                            f"({hours:.1f} ساعت)"
                        )
                    elif hours >= WARNING_AFTER_HOURS:
                        if not game.get("timeout_warned", False):
                            try:
                                await bot.send_message(
                                    object_guid=chat_id,
                                    text=(
                                        "⚠️ هشدار زمان بازی\n\n"
                                        f"بازی شماره `{game['id']}`\n"
                                        f"سناریو: {game['scenario_caption']}\n"
                                        f"مدت زمان: {hours:.1f} ساعت\n\n"
                                        "لطفاً نسبت به پایان بازی اقدام کنید."
                                    ),
                                    reply_to_message_id=game["start_msg_id"],
                                    auto_delete=60,
                                )
                                game["timeout_warned"] = True
                                logger.warning(
                                    "هشدار زمان برای بازی "
                                    f"{game['id']} ارسال شد"
                                )
                            except Exception as e:
                                log_error("ارسال هشدار زمان", e)
        except Exception as e:
            log_error("بررسی زمان بازی‌ها", e)


async def auto_stats_scheduler():
    global LAST_AUTO_STATS_DATE
    logger.info("زمان‌بند آمار خودکار فعال شد.")
    while True:
        await asyncio.sleep(60)
        if not AUTO_STATS_ENABLED or not AUTO_STATS_TIME:
            continue
        now_str = get_shamsi_now()
        date_part, time_part = now_str.split(" - ")
        if time_part[:5] == AUTO_STATS_TIME:
            today = date_part
            if today != LAST_AUTO_STATS_DATE:
                try:
                    stats_text = generate_stats_text()
                    await bot.send_message(
                        object_guid=MAIN_GROUP_GUID,
                        text=stats_text,
                    )
                    LAST_AUTO_STATS_DATE = today
                    logger.info("آمار خودکار ارسال شد.")
                except Exception as e:
                    log_error("ارسال آمار خودکار", e)


async def expire_pending_task(user_guid, preview_msg_id):
    await asyncio.sleep(300)
    banner = pending_banners.get(user_guid)
    if banner and banner.get("preview_msg_id") == preview_msg_id:
        del pending_banners[user_guid]
        try:
            await bot.delete_messages(
                object_guid=banner["chat_id"],
                message_ids=[preview_msg_id],
            )
        except Exception as e:
            log_error("حذف پیش‌نمایش منقضی", e)
        logger.warning(f"بنر در انتظار کاربر {user_guid} منقضی شد.")


def ensure_background_tasks():
    global forward_worker, timeout_worker, auto_stats_worker
    if forward_worker is None or forward_worker.done():
        forward_worker = asyncio.create_task(forward_queue_processor())
    if timeout_worker is None or timeout_worker.done():
        timeout_worker = asyncio.create_task(game_timeout_checker())
    if auto_stats_worker is None or auto_stats_worker.done():
        auto_stats_worker = asyncio.create_task(auto_stats_scheduler())


async def resolve_target_guid(identifier):
    if re.match(r"^[ugc]\w+$", identifier):
        return identifier
    if identifier.startswith("https://rubika.ir/join"):
        try:
            if "/joinc" in identifier:
                result = await bot.channel_preview_by_join_link(identifier)
                return result.channel.channel_guid
            result = await bot.group_preview_by_join_link(identifier)
            return result.group.group_guid
        except Exception as e:
            raise ValueError("لینک نامعتبر است.") from e
    try:
        result = await bot.get_object_by_username(identifier)
        if hasattr(result, "user"):
            return result.user.user_guid
        if hasattr(result, "group"):
            return result.group.group_guid
        if hasattr(result, "channel"):
            return result.channel.channel_guid
    except Exception as e:
        raise ValueError("یوزرنیم یا شناسه معتبر نیست.") from e
    raise ValueError("نوع شیء شناسایی نشد.")


async def get_reply_author_guid(update):
    reply_id = getattr(update.message, "reply_to_message_id", None)
    if not reply_id:
        return None
    reply_msg = getattr(update.message, "reply_to_message", None)
    if not reply_msg:
        reply_msg = getattr(update.message, "reply_to", None)
    if reply_msg:
        author = (
            getattr(reply_msg, "author_object_guid", None)
            or getattr(reply_msg, "author_guid", None)
        )
        if author:
            return author
    try:
        result = await bot.get_messages_by_id(update.object_guid, [reply_id])
        messages = getattr(result, "messages", None)
        if messages is None:
            messages = result if isinstance(result, list) else [result]
        if messages:
            msg = messages[0]
            author = (
                getattr(msg, "author_object_guid", None)
                or getattr(msg, "author_guid", None)
            )
            if author:
                return author
    except Exception as e:
        logger.debug(f"get_messages failed: {e}")
    return None


bot = Client("bot")


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(STOP_REGEX),
)
async def admin_stop(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if update.author_guid != MAIN_ADMIN_GUID:
        return
    global IS_BOT_ACTIVE
    IS_BOT_ACTIVE = False
    await bot.send_message(
        object_guid=update.object_guid,
        text=(
            "🛑 ربات توسط ادمین متوقف شد.\n"
            "هیچ پیامی جز دستورات ادمین پردازش نمی‌شود.\n"
            "برای راه‌اندازی مجدد از دستور `!start` استفاده کنید."
        ),
        reply_to_message_id=update.message_id,
        auto_delete=30,
    )
    await bot.delete_messages(
        object_guid=update.object_guid,
        message_ids=[update.message_id],
    )
    logger.warning("ربات توسط ادمین متوقف شد.")


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(BOT_START_REGEX),
)
async def admin_start(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if update.author_guid != MAIN_ADMIN_GUID:
        return
    global IS_BOT_ACTIVE
    IS_BOT_ACTIVE = True
    ensure_background_tasks()
    await bot.send_message(
        object_guid=update.object_guid,
        text=(
            "✅ ربات توسط ادمین راه‌اندازی شد.\n"
            "پردازش پیام‌ها از سر گرفته شد."
        ),
        reply_to_message_id=update.message_id,
        auto_delete=10,
    )
    await bot.delete_messages(
        object_guid=update.object_guid,
        message_ids=[update.message_id],
    )
    logger.info("ربات توسط ادمین راه‌اندازی شد.")


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(AUTO_STATS_SET_REGEX),
)
async def set_auto_stats(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if update.author_guid not in ADMIN_GUIDS:
        return
    match = AUTO_STATS_SET_REGEX.match(update.message.text.strip())
    time_str = match.group(1)
    global AUTO_STATS_ENABLED, AUTO_STATS_TIME, LAST_AUTO_STATS_DATE
    AUTO_STATS_ENABLED = True
    AUTO_STATS_TIME = time_str
    LAST_AUTO_STATS_DATE = ""
    ensure_background_tasks()
    await bot.send_message(
        object_guid=update.object_guid,
        text=f"⏰ آمار خودکار برای ساعت {time_str} فعال شد.",
        reply_to_message_id=update.message_id,
        auto_delete=15,
    )
    await bot.delete_messages(
        object_guid=update.object_guid,
        message_ids=[update.message_id],
    )
    logger.info(f"آمار خودکار برای ساعت {time_str} تنظیم شد.")


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(AUTO_STATS_DISABLE_REGEX),
)
async def disable_auto_stats(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if update.author_guid not in ADMIN_GUIDS:
        return
    global AUTO_STATS_ENABLED
    AUTO_STATS_ENABLED = False
    await bot.send_message(
        object_guid=update.object_guid,
        text="🛑 آمار خودکار غیرفعال شد.",
        reply_to_message_id=update.message_id,
        auto_delete=15,
    )
    await bot.delete_messages(
        object_guid=update.object_guid,
        message_ids=[update.message_id],
    )
    logger.info("آمار خودکار غیرفعال شد.")


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(BLOCK_REGEX),
)
async def block_user(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if update.author_guid not in ADMIN_GUIDS:
        return
    match = BLOCK_REGEX.match(update.message.text.strip())
    identifier = match.group(1)
    target_guid = None
    if update.message.reply_to_message_id:
        target_guid = await get_reply_author_guid(update)
    if target_guid is None and identifier:
        try:
            target_guid = await resolve_target_guid(identifier)
        except ValueError as e:
            await bot.send_message(
                object_guid=update.object_guid,
                text=f"⚠️ {e}",
                reply_to_message_id=update.message_id,
                auto_delete=10,
            )
            return
    if target_guid is None:
        await bot.send_message(
            object_guid=update.object_guid,
            text="❌ کاربری مشخص نشد. ریپلای کنید یا شناسه/یوزرنیم را بنویسید.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        return
    if target_guid in ADMIN_GUIDS:
        await bot.send_message(
            object_guid=update.object_guid,
            text="⛔ نمی‌توانید ادمین را بلاک کنید.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        return
    was_special = target_guid in SPECIAL_USERS
    SPECIAL_USERS.discard(target_guid)
    if target_guid in BLOCKED_USERS:
        await bot.send_message(
            object_guid=update.object_guid,
            text=f"⚠️ کاربر `{target_guid}` قبلاً بلاک شده است.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        await bot.delete_messages(
            object_guid=update.object_guid,
            message_ids=[update.message_id],
        )
        return
    BLOCKED_USERS.add(target_guid)
    note = " و از لیست ویژه حذف شد" if was_special else ""
    await bot.send_message(
        object_guid=update.object_guid,
        text=f"🚫 کاربر `{target_guid}` بلاک شد{note}.",
        reply_to_message_id=update.message_id,
        auto_delete=15,
    )
    await bot.delete_messages(
        object_guid=update.object_guid,
        message_ids=[update.message_id],
    )
    logger.warning(f"کاربر {target_guid} بلاک شد.")


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(SPECIAL_REGEX),
)
async def special_user(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if update.author_guid not in ADMIN_GUIDS:
        return
    match = SPECIAL_REGEX.match(update.message.text.strip())
    identifier = match.group(1)
    target_guid = None
    if update.message.reply_to_message_id:
        target_guid = await get_reply_author_guid(update)
    if target_guid is None and identifier:
        try:
            target_guid = await resolve_target_guid(identifier)
        except ValueError as e:
            await bot.send_message(
                object_guid=update.object_guid,
                text=f"⚠️ {e}",
                reply_to_message_id=update.message_id,
                auto_delete=10,
            )
            return
    if target_guid is None:
        await bot.send_message(
            object_guid=update.object_guid,
            text="❌ کاربری مشخص نشد. ریپلای کنید یا شناسه/یوزرنیم را بنویسید.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        return
    was_blocked = target_guid in BLOCKED_USERS
    BLOCKED_USERS.discard(target_guid)
    if target_guid in SPECIAL_USERS:
        await bot.send_message(
            object_guid=update.object_guid,
            text=f"⭐ کاربر `{target_guid}` قبلاً ویژه شده است.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        await bot.delete_messages(
            object_guid=update.object_guid,
            message_ids=[update.message_id],
        )
        return
    SPECIAL_USERS.add(target_guid)
    note = " و از بلاک خارج شد" if was_blocked else ""
    await bot.send_message(
        object_guid=update.object_guid,
        text=f"⭐ کاربر `{target_guid}` ویژه شد{note}.",
        reply_to_message_id=update.message_id,
        auto_delete=15,
    )
    await bot.delete_messages(
        object_guid=update.object_guid,
        message_ids=[update.message_id],
    )
    logger.info(f"کاربر {target_guid} ویژه شد.")


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(CLOSE_GROUP_REGEX),
)
async def close_group(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if update.author_guid not in ADMIN_GUIDS:
        return
    try:
        await bot.set_group_default_access(
            update.object_guid,
            ["ViewMembers", "ViewAdmins", "AddMember"]
        )
        await bot.send_message(
            object_guid=update.object_guid,
            text="🔒 گروه بسته شد. فقط ادمین‌ها می‌توانند پیام بفرستند.",
            reply_to_message_id=update.message_id,
            auto_delete=15,
        )
    except Exception as e:
        log_error("close_group", e)


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(OPEN_GROUP_REGEX),
)
async def open_group(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if update.author_guid not in ADMIN_GUIDS:
        return
    try:
        await bot.set_group_default_access(
            update.object_guid,
            ["ViewMembers", "ViewAdmins", "SendMessages", "AddMember"]
        )
        await bot.send_message(
            object_guid=update.object_guid,
            text="🔓 گروه باز شد. همه می‌توانند پیام بفرستند.",
            reply_to_message_id=update.message_id,
            auto_delete=15,
        )
    except Exception as e:
        log_error("open_group", e)


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(ADD_ADMIN_REGEX),
)
async def add_admin(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if update.author_guid != MAIN_ADMIN_GUID:
        return
    match = ADD_ADMIN_REGEX.match(update.message.text.strip())
    identifier = match.group(2)
    target_guid = None

    if update.message.reply_to_message_id:
        target_guid = await get_reply_author_guid(update)

    if target_guid is None and identifier:
        try:
            target_guid = await resolve_target_guid(identifier)
        except ValueError as e:
            await bot.send_message(
                object_guid=update.object_guid,
                text=f"⚠️ {e}",
                reply_to_message_id=update.message_id,
                auto_delete=10,
            )
            return

    if target_guid is None:
        await bot.send_message(
            object_guid=update.object_guid,
            text="❌ کاربری مشخص نشد. ریپلای کنید یا شناسه/یوزرنیم را بنویسید.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        return

    if target_guid in ADMIN_GUIDS:
        await bot.send_message(
            object_guid=update.object_guid,
            text=f"⚠️ کاربر `{target_guid}` قبلاً ادمین است.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        return

    ADMIN_GUIDS.add(target_guid)
    await bot.send_message(
        object_guid=update.object_guid,
        text=f"👑 کاربر `{target_guid}` به لیست ادمین‌ها اضافه شد.",
        reply_to_message_id=update.message_id,
        auto_delete=15,
    )
    await bot.delete_messages(
        object_guid=update.object_guid,
        message_ids=[update.message_id],
    )
    logger.info(f"ادمین جدید اضافه شد: {target_guid}")


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(REMOVE_ADMIN_REGEX),
)
async def remove_admin(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if update.author_guid != MAIN_ADMIN_GUID:
        return
    match = REMOVE_ADMIN_REGEX.match(update.message.text.strip())
    identifier = match.group(2)
    target_guid = None

    if update.message.reply_to_message_id:
        target_guid = await get_reply_author_guid(update)

    if target_guid is None and identifier:
        try:
            target_guid = await resolve_target_guid(identifier)
        except ValueError as e:
            await bot.send_message(
                object_guid=update.object_guid,
                text=f"⚠️ {e}",
                reply_to_message_id=update.message_id,
                auto_delete=10,
            )
            return

    if target_guid is None:
        await bot.send_message(
            object_guid=update.object_guid,
            text="❌ کاربری مشخص نشد. ریپلای کنید یا شناسه/یوزرنیم را بنویسید.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        return

    if target_guid == MAIN_ADMIN_GUID:
        await bot.send_message(
            object_guid=update.object_guid,
            text="⛔ نمی‌توانید ادمین اصلی را عزل کنید.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        return

    if target_guid not in ADMIN_GUIDS:
        await bot.send_message(
            object_guid=update.object_guid,
            text=f"⚠️ کاربر `{target_guid}` ادمین نیست.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        return

    ADMIN_GUIDS.remove(target_guid)
    await bot.send_message(
        object_guid=update.object_guid,
        text=f"❌ کاربر `{target_guid}` از لیست ادمین‌ها حذف شد.",
        reply_to_message_id=update.message_id,
        auto_delete=15,
    )
    await bot.delete_messages(
        object_guid=update.object_guid,
        message_ids=[update.message_id],
    )
    logger.info(f"ادمین حذف شد: {target_guid}")


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.photo,
    filters.regex(START_REGEX),
)
async def handle_start(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if not is_user_allowed(update):
        return
    ensure_background_tasks()
    chat_id = update.object_guid
    user_guid = update.author_guid
    user_msg_id = update.message_id
    logger.info(f"شروع بازی | {user_guid} | {update.message.text[:50]}")
    try:
        match = START_REGEX.search(update.message.text)
        if not match:
            return
        scenario_part = match.group(1).strip()
        builder_fa = match.group(2).strip()
        should_forward = match.group(3) is not None
        scenario_words = scenario_part.split()
        has_dunyto = any(word in DUNYTO_VARIATIONS for word in scenario_words)
        if has_dunyto:
            scenario_fa = " ".join(
                word for word in scenario_words
                if word not in DUNYTO_VARIATIONS
            ).strip()
            scenario_caption = (
                f"{scenario_fa} ➪ دُنیتو" if scenario_fa else "دُنیتو"
            )
        else:
            scenario_caption = scenario_part
        builder_en, corrected_name = normalize_builder_name(builder_fa)
        raw = await bot.download(update.message.file_inline)
        now = get_shamsi_now()
        caption = (
            "🌱بِه نامِ خوبی راستی و پاکی 🌱\n\n"
            f"🧑‍💻سازنده دک: ✺ DoN 𖤍 {builder_en}✺\n\n"
            f"📜سناریو: {scenario_caption}\n\n"
            f"⏱︎ساعت شروع : {now}\n\n"
            "🔖برای عضویت و ارتباط با لیدر گروه:\n\n@Don55555\n\n"
            "𒆜ادب احترام میاره❥︎احترام اعتبار𒆜"
        )
        correction_note = ""
        if corrected_name:
            correction_note = (
                f"\n\n⚠️ نام '{builder_fa}' به '{corrected_name}' اصلاح شد."
            )
        banner_data = {
            "chat_id": chat_id,
            "photo_raw": raw,
            "caption": caption,
            "file_meta": {
                "file_name": update.message.file_inline.file_name,
                "width": update.message.file_inline.width,
                "height": update.message.file_inline.height,
            },
            "should_forward": should_forward,
            "scenario_caption": scenario_caption,
            "builder_en": builder_en,
            "now": now,
            "creator_guid": user_guid,
            "builder_fa": builder_fa,
            "user_msg_id": user_msg_id,
        }
        pending_banners[user_guid] = banner_data
        preview_text = (
            f"⚠️ پیش‌نمایش بنر{correction_note}\n\n{caption}\n\n"
            "آیا اطلاعات صحیح است؟\n"
            "✅ برای تایید کلمه بله را ریپلای کنید.\n"
            "❌ برای رد کردن کلمه نه را ریپلای کنید."
        )
        preview_msg = await bot.send_message(
            object_guid=chat_id,
            text=preview_text,
            reply_to_message_id=user_msg_id,
        )
        banner_data["preview_msg_id"] = preview_msg.message_id
        asyncio.create_task(
            expire_pending_task(user_guid, preview_msg.message_id)
        )
        logger.info(f"پیش‌نمایش بنر برای کاربر {user_guid} ارسال شد.")
    except Exception as e:
        log_error("handle_start (preview)", e)


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
)
async def handle_confirmation(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if not is_user_allowed(update):
        return
    ensure_background_tasks()
    text = update.message.text.strip()
    if not (CONFIRM_REGEX.match(text) or REJECT_REGEX.match(text)):
        return
    reply_id = update.message.reply_to_message_id
    if not reply_id:
        return
    target_banner = None
    target_user_guid = None
    for uid, data in pending_banners.items():
        if data.get("preview_msg_id") == reply_id:
            target_banner = data
            target_user_guid = uid
            break
    if not target_banner:
        return
    if update.author_guid != target_user_guid:
        await bot.send_message(
            object_guid=update.object_guid,
            text=(
                "❌ خطا: فقط ارسال‌کننده اصلی بنر می‌تواند آن را "
                "تایید یا رد کند."
            ),
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        return
    try:
        if CONFIRM_REGEX.match(text):
            sent = await bot.send_photo(
                object_guid=target_banner["chat_id"],
                photo=target_banner["photo_raw"],
                caption=target_banner["caption"],
                **target_banner["file_meta"],
            )
            chat_id = target_banner["chat_id"]
            if chat_id not in active_games:
                active_games[chat_id] = {"games": deque()}
            game_id = find_available_game_id(chat_id)
            game = {
                "id": game_id,
                "start_msg_id": sent.message_id,
                "scenario_caption": target_banner["scenario_caption"],
                "builder": target_banner["builder_en"],
                "should_forward": target_banner["should_forward"],
                "start_time": target_banner["now"],
                "forwarded_msg_id": None,
                "timeout_warned": False,
            }
            if target_banner["should_forward"]:
                forward_queue.append(
                    {
                        "from_guid": chat_id,
                        "message_id": sent.message_id,
                        "chat_id": chat_id,
                        "game_id": game_id,
                    }
                )
                ensure_background_tasks()
                logger.info(f"فوروارد به صف اضافه شد: {sent.message_id}")
            active_games[chat_id]["games"].append(game)
            update_stats(
                target_banner["builder_en"],
                target_banner["scenario_caption"],
            )
            await bot.delete_messages(
                object_guid=update.object_guid,
                message_ids=[reply_id],
            )
            await bot.delete_messages(
                object_guid=update.object_guid,
                message_ids=[target_banner["user_msg_id"]],
            )
            await bot.delete_messages(
                object_guid=update.object_guid,
                message_ids=[update.message_id],
            )
            del pending_banners[target_user_guid]
            logger.info(
                f"بنر {game_id} توسط کاربر {update.author_guid} تایید شد."
            )
        elif REJECT_REGEX.match(text):
            await bot.delete_messages(
                object_guid=update.object_guid,
                message_ids=[reply_id],
            )
            await bot.delete_messages(
                object_guid=update.object_guid,
                message_ids=[target_banner["user_msg_id"]],
            )
            await bot.send_message(
                object_guid=update.object_guid,
                text="♻️ بنر رد شد. لطفاً نسخه صحیح را مجدداً ارسال کنید.",
                reply_to_message_id=update.message_id,
                auto_delete=15,
            )
            await bot.delete_messages(
                object_guid=update.object_guid,
                message_ids=[update.message_id],
            )
            del pending_banners[target_user_guid]
            logger.info(f"بنر کاربر {update.author_guid} رد شد.")
    except Exception as e:
        log_error("handle_confirmation", e)


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.photo,
    filters.regex(END_REGEX),
)
async def handle_end(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if not is_user_allowed(update):
        return
    ensure_background_tasks()
    chat_id = update.object_guid
    user_msg_id = update.message_id
    reply_id = update.message.reply_to_message_id
    logger.info(
        f"پایان بازی | reply_id={reply_id} | {update.message.text[:50]}"
    )
    try:
        match = END_REGEX.search(update.message.text)
        if not match:
            return
        winner = match.group(1).strip()
        should_forward = match.group(2) is not None
        if chat_id not in active_games or not active_games[chat_id]["games"]:
            await bot.send_message(
                object_guid=chat_id,
                text="📭 بازی فعالی ثبت نشده است.",
                reply_to_message_id=user_msg_id,
                auto_delete=15,
            )
            await bot.delete_messages(
                object_guid=chat_id,
                message_ids=[user_msg_id],
            )
            return
        games = active_games[chat_id]["games"]
        if reply_id:
            game = next(
                (g for g in games if g["start_msg_id"] == reply_id), None
            )
        else:
            game = next(iter(games), None)
        if game is None:
            await bot.send_message(
                object_guid=chat_id,
                text="🔍 بازی مرتبط با این ریپلای یافت نشد.",
                reply_to_message_id=user_msg_id,
                auto_delete=15,
            )
            await bot.delete_messages(
                object_guid=chat_id,
                message_ids=[user_msg_id],
            )
            return
        raw_bytes = await bot.download(update.message.file_inline)
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
        sent_end = await bot.send_photo(
            object_guid=chat_id,
            photo=raw_bytes,
            caption=caption,
            file_name=update.message.file_inline.file_name,
            width=update.message.file_inline.width,
            height=update.message.file_inline.height,
            reply_to_message_id=game["start_msg_id"],
        )
        games.remove(game)
        logger.info(f"بنر پایان ارسال شد {sent_end.message_id}")
        await bot.delete_messages(
            object_guid=chat_id,
            message_ids=[user_msg_id],
        )
        if should_forward:
            forward_queue.append(
                {
                    "from_guid": chat_id,
                    "message_id": sent_end.message_id,
                }
            )
            ensure_background_tasks()
            logger.info(
                f"فوروارد پایان به صف اضافه شد: {sent_end.message_id}"
            )
    except Exception as e:
        log_error("handle_end", e)


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(STATS_REGEX),
)
async def show_stats(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if not is_user_allowed(update):
        return
    logger.info("درخواست آمار")
    try:
        stats_text = generate_stats_text()
        await bot.send_message(
            object_guid=update.object_guid,
            text=stats_text,
            reply_to_message_id=update.message_id,
            auto_delete=60,
        )
        await bot.delete_messages(
            object_guid=update.object_guid,
            message_ids=[update.message_id],
        )
    except Exception as e:
        log_error("show_stats", e)


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(HELP_REGEX),
)
async def help_handler(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if not is_user_allowed(update):
        return
    logger.info("درخواست راهنما")
    await bot.send_message(
        object_guid=update.object_guid,
        text=HELP_TEXT,
        reply_to_message_id=update.message_id,
        auto_delete=20,
    )
    await bot.delete_messages(
        object_guid=update.object_guid,
        message_ids=[update.message_id],
    )


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(LIST_GAMES_REGEX),
)
async def list_games(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if not is_user_allowed(update):
        return
    chat_id = update.object_guid
    user_msg_id = update.message_id
    logger.info("لیست بازی‌ها")
    try:
        if chat_id not in active_games or not active_games[chat_id]["games"]:
            reply = "📭 لیست بازی‌ها خالی است."
        else:
            lines = ["📋 لیست بازی‌های فعال:\n"]
            for game in active_games[chat_id]["games"]:
                hours = parse_time_to_hours(game.get("start_time", ""))
                warn_icon = " ⚠️" if hours >= WARNING_AFTER_HOURS else ""
                lines.append(
                    f"🆔 شناسه بازی: `{game['id']}`{warn_icon}\n"
                    f"🎭 سناریو: {game['scenario_caption']}\n"
                    f"🛠️ سازنده: {game['builder']}\n"
                    f"⏰ زمان استارت: {game['start_time']}\n"
                    f"⏳ مدت: {hours:.1f} ساعت\n"
                    "➖➖➖➖➖➖➖➖"
                )
            reply = "\n".join(lines)
        await bot.send_message(
            object_guid=chat_id,
            text=reply,
            reply_to_message_id=user_msg_id,
            auto_delete=20,
        )
        await bot.delete_messages(
            object_guid=chat_id,
            message_ids=[user_msg_id],
        )
    except Exception as e:
        log_error("list_games", e)


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(DELETE_MESSAGES_REGEX),
)
async def delete_messages_handler(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if update.author_guid not in ADMIN_GUIDS:
        return

    match = DELETE_MESSAGES_REGEX.match(update.message.text.strip())
    if not match:
        return

    count = int(match.group(1))
    if count < 1:
        return
    if count > 1000:
        await bot.send_message(
            object_guid=update.object_guid,
            text="⚠️ حداکثر ۱۰۰۰ پیام را می‌توانید حذف کنید.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        return

    try:
        # ارسال پارامترها به صورت رشته (مطابق API اصلی)
        result = await bot.get_messages(
            update.object_guid,
            max_id="0",
            limit=str(count),
            sort="FromMax",
        )

        if result is None:
            raise Exception("result is None")

        # استخراج messages (ممکن است dict یا object باشد)
        messages = None
        if hasattr(result, 'messages'):
            messages = result.messages
        elif isinstance(result, dict):
            messages = result.get('messages', [])

        if not messages:
            await bot.send_message(
                object_guid=update.object_guid,
                text="📭 پیامی برای حذف یافت نشد.",
                reply_to_message_id=update.message_id,
                auto_delete=10,
            )
            return

        # جمع‌آوری شناسه‌ها و محدود کردن به count (در صورت برگشت اضافی)
        ids = []
        for msg in messages:
            mid = msg['message_id'] if isinstance(msg, dict) else getattr(msg, 'message_id', None)
            if mid:
                ids.append(mid)
        ids = ids[:count]   # فقط count تا اول را نگه می‌داریم

        if not ids:
            await bot.send_message(
                object_guid=update.object_guid,
                text="📭 پیامی برای حذف یافت نشد.",
                reply_to_message_id=update.message_id,
                auto_delete=10,
            )
            return

        await bot.delete_messages(update.object_guid, ids)
        await bot.send_message(
            object_guid=update.object_guid,
            text=f"🧹 {len(ids)} پیام با موفقیت حذف شد.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        await asyncio.sleep(3)
        await bot.delete_messages(update.object_guid, [update.message_id])

    except Exception as e:
        log_error("delete_messages", e)
        await bot.send_message(
            object_guid=update.object_guid,
            text="❌ خطا در حذف پیام‌ها.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        

@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(BAN_REGEX),
)
async def ban_user(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if update.author_guid not in ADMIN_GUIDS:
        return

    match = BAN_REGEX.match(update.message.text.strip())
    if not match:
        return

    identifier = match.group(2)
    target_guid = None

    if update.message.reply_to_message_id:
        target_guid = await get_reply_author_guid(update)

    if target_guid is None and identifier:
        try:
            target_guid = await resolve_target_guid(identifier)
        except ValueError as e:
            await bot.send_message(
                object_guid=update.object_guid,
                text=f"⚠️ {e}",
                reply_to_message_id=update.message_id,
                auto_delete=10,
            )
            return

    if target_guid is None:
        await bot.send_message(
            object_guid=update.object_guid,
            text="❌ کاربری مشخص نشد. ریپلای کنید یا شناسه/یوزرنیم را بنویسید.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        return

    if target_guid in ADMIN_GUIDS:
        await bot.send_message(
            object_guid=update.object_guid,
            text="⛔ نمی‌توانید ادمین را بن کنید.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        return

    try:
        await bot.ban_group_member(
            group_guid=update.object_guid,
            member_guid=target_guid,
            action='Set',
        )
        await bot.send_message(
            object_guid=update.object_guid,
            text=f"🚫 کاربر `{target_guid}` بن شد.",
            reply_to_message_id=update.message_id,
            auto_delete=15,
        )
        await bot.delete_messages(
            object_guid=update.object_guid,
            message_ids=[update.message_id],
        )
        logger.warning(f"کاربر {target_guid} بن شد.")
    except Exception as e:
        log_error("ban_user", e)
        await bot.send_message(
            object_guid=update.object_guid,
            text="❌ خطا در بن کردن کاربر.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )


@bot.on_message_updates(
    MAIN_GROUP_FILTER,
    filters.text,
    filters.regex(UNBAN_REGEX),
)
async def unban_user(update):
    if update.object_guid != MAIN_GROUP_GUID:
        return
    if update.author_guid not in ADMIN_GUIDS:
        return

    match = UNBAN_REGEX.match(update.message.text.strip())
    if not match:
        return

    identifier = match.group(2)
    target_guid = None

    if update.message.reply_to_message_id:
        target_guid = await get_reply_author_guid(update)

    if target_guid is None and identifier:
        try:
            target_guid = await resolve_target_guid(identifier)
        except ValueError as e:
            await bot.send_message(
                object_guid=update.object_guid,
                text=f"⚠️ {e}",
                reply_to_message_id=update.message_id,
                auto_delete=10,
            )
            return

    if target_guid is None:
        await bot.send_message(
            object_guid=update.object_guid,
            text="❌ کاربری مشخص نشد. ریپلای کنید یا شناسه/یوزرنیم را بنویسید.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        return

    try:
        await bot.ban_group_member(
            group_guid=update.object_guid,
            member_guid=target_guid,
            action='Unset',
        )

        # دریافت لینک گروه
        try:
            link_info = await bot.get_group_link(update.object_guid)
            invite_link = link_info.join_link
            if invite_link:
                try:
                    await bot.send_message(
                        object_guid=target_guid,
                        text=(
                            "✅ شما از گروه آنبن شدید.\n"
                            f"🔗 لینک گروه:\n{invite_link}"
                        ),
                    )
                except Exception:
                    pass
        except Exception as e:
            log_error("unban_get_link", e)

        await bot.send_message(
            object_guid=update.object_guid,
            text=f"🔓 کاربر `{target_guid}` از بن خارج شد.",
            reply_to_message_id=update.message_id,
            auto_delete=15,
        )
        await bot.delete_messages(
            object_guid=update.object_guid,
            message_ids=[update.message_id],
        )
        logger.info(f"کاربر {target_guid} آنبن شد.")
    except Exception as e:
        log_error("unban_user", e)
        await bot.send_message(
            object_guid=update.object_guid,
            text="❌ خطا در خارج کردن کاربر از بن.",
            reply_to_message_id=update.message_id,
            auto_delete=10,
        )
        

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.create_task(forward_queue_processor())
    loop.create_task(game_timeout_checker())
    loop.create_task(auto_stats_scheduler())

    logger.info("ربات دُنیتو راه‌اندازی شد")
    logger.info(
        f"وضعیت اولیه: {'فعال' if IS_BOT_ACTIVE else 'متوقف'}"
    )
    logger.info(f"شناسه ادمین اصلی: {MAIN_ADMIN_GUID}")
    logger.info(
        "سیستم‌های هوشمند فعال شدند: صف فوروارد، "
        "بررسی زمان بازی‌ها، آمارگیری"
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
