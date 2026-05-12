import re
import io
import asyncio
import traceback
from datetime import datetime
from collections import deque
import jdatetime
from rubpy import Client, filters
from rubpy.types import Update
from PIL import Image

TARGET_GROUP_GUID = "g0DHpOn042b93c4982b5b135365c7bb6"

NAME_MAP = {
    "فایتر": "Fighter",
    "اهورا": "Ahoora",
    "سبحان": "Geshtapo",
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
    "هانیه": "Hanieh"
}

SCENARIO_PATTERN = r"جک|مذاکره|بازپرس|تفنگدار|پدرخوانده|فکت|شرلوک|قاتل"
BUILDER_PATTERN = r"فایتر|اهورا|صبحان|سبحان|یکتا|ساره|مجی|گاد\s?فادر|فرید|هانتر|هانی|ماتادور|نیلوفر|هانیه"
START_REGEX = re.compile(rf"^({SCENARIO_PATTERN})\s+({BUILDER_PATTERN})(\s+فور)?$")
END_REGEX = re.compile(r"^پایان\s+(\S+)(\s+فور)?$")

active_games = {}

def normalize_builder_name(raw: str) -> str:
    key = re.sub(r"\s+", " ", raw).strip()
    return NAME_MAP.get(key, raw)

def get_shamsi_now() -> str:
    return jdatetime.datetime.now().strftime("%H:%M - %Y/%m/%d ")

def log_error(context: str, error: Exception) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] ❌ {context}")
    print(f"Type: {type(error).__name__}: {error}")
    traceback.print_exc()
    print("-" * 50)

async def compress_image(image_bytes: bytes, max_dimension: int = 960, quality: int = 65) -> tuple[bytes, int, int]:
    def _compress():
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        current_dim = max_dimension
        current_quality = quality
        target_size = 30 * 1024
        max_attempts = 15

        for attempt in range(max_attempts):
            if max(img.size) > current_dim:
                img_copy = img.copy()
                img_copy.thumbnail((current_dim, current_dim), Image.LANCZOS)
            else:
                img_copy = img

            buffer = io.BytesIO()
            img_copy.save(buffer, format="JPEG", quality=current_quality, optimize=True, exif=b"")
            data = buffer.getvalue()

            if len(data) <= target_size:
                print(f"📦 حجم عکس فشرده: {len(data)/1024:.1f} کیلوبایت | ابعاد: {img_copy.size[0]}x{img_copy.size[1]}")
                return data, img_copy.size[0], img_copy.size[1]

            if current_quality > 15:
                current_quality -= 10
                continue
            else:
                current_dim -= 150
                current_quality = 55
                if current_dim < 150:
                    break

        print(f"📦 حجم عکس فشرده: {len(data)/1024:.1f} کیلوبایت (بهینه‌ترین حالت) | ابعاد: {img_copy.size[0]}x{img_copy.size[1]}")
        return data, img_copy.size[0], img_copy.size[1]

    return await asyncio.to_thread(_compress)

bot = Client("bot")

@bot.on_message_updates(filters.object_guid("g0E19S900dd50643ab8fcbf23dad9e70"), filters.photo, filters.regex(START_REGEX))
async def handle_start(update: Update):
    print("عکس دریافت شد ")
    chat_id = update.object_guid
    user_msg_id = update.message_id

    match = START_REGEX.search(update.message.text)
    if not match:
        return
    scenario_fa = match.group(1)
    builder_fa = match.group(2)
    builder_en = normalize_builder_name(builder_fa)
    should_forward = match.group(3) is not None

    try:
        raw = await bot.download(update.message.file_inline)
    except Exception as e:
        log_error("دانلود عکس شروع", e)
        return

    try:
        compressed, w, h = await compress_image(raw)
    except Exception as e:
        log_error("فشرده‌سازی عکس شروع", e)
        return

    now = get_shamsi_now()
    caption = (
        "🌱بِه نامِ خوبی راستی و پاکی 🌱\n\n"
        f"🧑‍💻سازنده دک :  ✺ DoN 𖤍 {builder_en}✺\n\n"
        f"📜سناریو: {scenario_fa} ➪ دونیتو\n\n"
        f"⏱︎ساعت شروع : {now}\n\n"
        "🔖برای عضویت و ارتباط با لیدر گروه:\n\n"
        "@Don55555\n\n"
        "𒆜ادب احترام میاره❥︎احترام اعتبار𒆜"
    )

    try:
        sent = await bot.send_photo(
            object_guid=chat_id,
            photo=compressed,
            caption=caption,
            file_name=update.message.file_inline.file_name,
            width=w,
            height=h,
        )
    except Exception as e:
        log_error("ارسال بنر شروع", e)
        return

    game = {
        "start_msg_id": sent.message_id,
        "scenario": scenario_fa,
        "builder": builder_en,
        "should_forward": should_forward,
    }

    if chat_id not in active_games:
        active_games[chat_id] = deque()
    active_games[chat_id].append(game)

    try:
        await bot.delete_messages(object_guid=chat_id, message_ids=user_msg_id)
    except Exception as e:
        log_error("حذف پیام کاربر شروع", e)

    if should_forward:
        try:
            await bot.forward_messages(
                from_object_guid=chat_id,
                message_ids=sent.message_id,
                to_object_guid=TARGET_GROUP_GUID
            )
        except Exception as e:
            log_error("فوروارد بنر شروع", e)

@bot.on_message_updates(filters.object_guid("g0E19S900dd50643ab8fcbf23dad9e70"), filters.photo, filters.regex(END_REGEX))
async def handle_end(update: Update):
    print("عکس پایان دریافت شد")
    chat_id = update.object_guid
    user_msg_id = update.message_id
    reply_id = update.message.reply_to_message_id

    if chat_id not in active_games or not active_games[chat_id]:
        return

    if reply_id:
        game = None
        for g in active_games[chat_id]:
            if g["start_msg_id"] == reply_id:
                game = g
                break
        if game:
            active_games[chat_id].remove(game)
        else:
            return
    else:
        game = active_games[chat_id].popleft()

    match = END_REGEX.search(update.message.text)
    if not match:
        return
    winner = match.group(1)
    should_forward = match.group(2) is not None

    try:
        raw_bytes = await bot.download(update.message.file_inline)
    except Exception as e:
        log_error("دانلود عکس پایان", e)
        return

    try:
        compressed_bytes, new_w, new_h = await compress_image(raw_bytes)
    except Exception as e:
        log_error("فشرده‌سازی عکس پایان", e)
        return

    now = get_shamsi_now()
    caption = (
        "🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆🏆\n\n"
        f"🎞سناریو:    {game['scenario']}  ➪  دونیتو\n\n"
        f"🧑‍💻سازنده لابی: ✺DσN 𖤍 {game['builder']}✺\n\n"
        f"🥇برنده : {winner}  ➪ 🏆\n\n"
        f"⏱︎ساعت پایان : {now}\n\n"
        "مافیا های زندگیت رو بشناس 🔥🔥🔥\n\n"
        "🔖عضویت و ارتباط با لیدر گروه:\n\n"
        "@DoN55555\n\n"
        "𒆜ادب احترام میاره❥︎احترام اعتبار𒆜"
    )

    try:
        sent_end = await bot.send_photo(
            object_guid=chat_id,
            photo=compressed_bytes,
            caption=caption,
            file_name=update.message.file_inline.file_name,
            width=new_w,
            height=new_h,
            reply_to_message_id=game["start_msg_id"],
        )
        await bot.delete_messages(object_guid=chat_id, message_ids=user_msg_id)
        if should_forward:
            await bot.forward_messages(
                from_object_guid=chat_id,
                message_ids=sent_end.message_id,
                to_object_guid=TARGET_GROUP_GUID
            )
    except Exception as e:
        log_error("ارسال/حذف/فوروارد پایان", e)

@bot.on_message_updates(
    filters.object_guid("g0E19S900dd50643ab8fcbf23dad9e70"),
    filters.text,
    filters.regex(r"^راهنما$")
)
async def help_handler(update: Update):
    help_text = (
        "**راهنمای ربات بنرگذار دونیتو**\n\n"
        "درود بر گاد ۲ های عزیز! 🙌\n"
        "این ربات برای ساخت و ارسال خودکار بنر بازی‌ها طراحی شده. لطفاً فقط گاد ۲ ها از آن استفاده کنند تا نظم کار حفظ شود.\n\n"
        "---\n\n"
        "**📌 شرایط اولیه**\n"
        "• بنر باید یک **عکس** داشته باشد.\n"
        "• کپشن عکس شامل دو بخش اجباری و یک بخش اختیاری (فور) است.\n"
        "• قالب شروع:\n"
        "`[سناریو] [سازنده] [فور]`\n\n"
        "---\n\n"
        "**۱. سناریو**\n"
        "نام سناریوی بازی (مثلاً بازپرس، مذاکره، فکت، شرلوک، قاتل و …)\n\n"
        "**۲. سازنده دک**\n"
        "نام سازنده را از میان موارد زیر انتخاب کنید:\n\n"
        "• فایتر\n"
        "• اهورا\n"
        "• ساره\n"
        "• مجی\n"
        "• سبحان / صبحان\n"
        "• گاد فادر / گادفادر\n"
        "• یکتا\n"
        "• هانی\n"
        "• ماتادور\n"
        "• فرید\n"
        "• نیلوفر\n"
        "• هانیه\n"
        "• هانتر\n\n"
        "اگر نامی جا افتاده، به ما اطلاع دهید تا اضافه شود.\n\n"
        "**۳. فور (اختیاری)**\n"
        "با اضافه کردن کلمه «فور»، ربات بنر را علاوه بر گروه اصلی، به گروه رسمی دونیتو **فوروارد** می‌کند. بدون آن، بنر فقط در گروه خودتان ارسال می‌شود.\n\n"
        "---\n\n"
        "**مثال شروع**\n\n"
        "با فوروارد:\n"
        "`بازپرس هانتر فور`\n"
        "بدون فوروارد:\n"
        "`مذاکره سبحان`\n\n"
        "---\n\n"
        "**پایان بازی**\n"
        "برای بستن بازی، عکس پایان را با کپشن زیر بفرستید:\n"
        "`پایان [برنده] [فور]`\n\n"
        "• برنده: هر عبارتی که وارد کنید دقیقاً در بنر قرار می‌گیرد (مثلاً شهر، مافیا، زودیاک).\n"
        "• فور: مانند قبل، اختیاری است.\n\n"
        "مثال‌ها:\n"
        "`پایان شهر فور` → برنده: شهر + فوروارد\n"
        "`پایان مافیا` → برنده: مافیا، بدون فوروارد\n\n"
        "---\n\n"
        "**نکات مهم**\n"
        "• برای پایان بازی نیازی به ریپلای روی بنر شروع نیست؛ ربات خودکار اولین بازی آغازشده را می‌بندد.\n"
        "• اگر چند بازی همزمان فعال دارید، اولویت پایان با بازی‌ای است که زودتر شروع شده.\n"
        "• حتماً یک عکس همراه کپشن باشد، در غیر این‌صورت ربات اقدامی نمی‌کند.\n"
        "• پردازش عکس و فشرده‌سازی آن ممکن است چند لحظه زمان ببرد.\n\n"
        "با آرزوی بازی‌های پرهیجان و منظم برای شما ✨"
    )

    await bot.send_message(
        object_guid=update.object_guid,
        text=help_text,
        reply_to_message_id=update.message_id,
        auto_delete=20
    )

bot.run()
