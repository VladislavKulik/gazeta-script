"""Крок 6: вивантаження повідомлень групи за добу в data/YYYY-MM-DD.json.

Медіа (фото, стікери, гіфки) зберігаються в base64 (data URI) в окремому розділі "media",
а повідомлення посилаються на них через "media_id". Однаковий стікер, надісланий
20 разів, зберігається лише один раз.

Типи медіа (поле "kind"):
  photo            — JPEG, зменшене фото                 -> <img>
  sticker          — статичний стікер, WEBP з прозорістю -> <img>
  video_sticker    — відео-стікер, WEBM з прозорістю     -> <video autoplay loop muted>
  animated_sticker — анімований стікер, Lottie JSON      -> бібліотека lottie-web
  gif              — "гіфка" Telegram, насправді MP4     -> <video autoplay loop muted>
  gif_preview      — завелика гіфка: лише статичний кадр -> <img>

Переслані повідомлення (новини з пабліків тощо) позначаються "forwarded": true і
"fwd_source": назва джерела. Їхні медіа не завантажуються — у газету вони не йдуть,
а слугують лише контекстом для обговорення.

Запуск:
    python export.py              -> сьогоднішня доба
    python export.py 2026-10-03   -> конкретна дата
"""
import asyncio
import base64
import gzip
import io
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from PIL import Image
from telethon import TelegramClient

load_dotenv()
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
CHAT_ID = int(os.environ["TG_CHAT_ID"])
TZ = ZoneInfo(os.getenv("TZ_NAME", "Europe/Kyiv"))
DATA_DIR = Path(__file__).parent / "data"

PHOTO_MAX_SIDE = int(os.getenv("PHOTO_MAX_SIDE", "800"))      # px по довшій стороні
PHOTO_QUALITY = int(os.getenv("PHOTO_QUALITY", "75"))         # якість JPEG 1–95
STICKER_MAX_SIDE = int(os.getenv("STICKER_MAX_SIDE", "256"))  # px для статичних стікерів
MAX_GIF_KB = int(os.getenv("MAX_GIF_KB", "3000"))             # гіфки більші за це -> лише кадр


# ---------- допоміжне ----------

def day_bounds(date_str: str | None):
    """Початок і кінець доби в місцевому часі."""
    if date_str:
        start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=TZ)
    else:
        start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def sender_name(m) -> str:
    s = m.sender
    if s is None:
        return "Невідомий"
    first = getattr(s, "first_name", None) or getattr(s, "title", None) or "Невідомий"
    last = getattr(s, "last_name", None)
    return f"{first} {last}" if last else first


def media_tag(m) -> str:
    """Текстова мітка для моделі. Порядок важливий: стікер/гіф/голосове/відео — теж документи."""
    if m.photo:
        return "[фото]"
    if m.sticker:
        emoji = getattr(m.file, "emoji", None)
        return f"[стікер {emoji}]" if emoji else "[стікер]"
    if m.gif:
        return "[gif]"
    if m.voice:
        return "[голосове]"
    if m.video:
        return "[відео]"
    if m.poll:
        return "[опитування]"
    if m.document:
        return "[файл]"
    return ""


def to_data_uri(raw: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


def image_to_data_uri(raw: bytes, max_side: int, fmt: str) -> str:
    """Зменшує картинку. JPEG — без прозорості, WEBP — з прозорістю (для стікерів)."""
    img = Image.open(io.BytesIO(raw))
    img = img.convert("RGB" if fmt == "JPEG" else "RGBA")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.save(buf, format="JPEG", quality=PHOTO_QUALITY, optimize=True)
        return to_data_uri(buf.getvalue(), "image/jpeg")
    img.save(buf, format="WEBP", quality=80)
    return to_data_uri(buf.getvalue(), "image/webp")


def media_key(m) -> str | None:
    """Унікальний ключ медіа — щоб не завантажувати однаковий стікер/гіфку кілька разів."""
    if m.photo:
        return f"photo_{m.photo.id}"
    if (m.sticker or m.gif) and m.document:
        return f"doc_{m.document.id}"
    return None


async def forward_source(m, cache: dict) -> str | None:
    """Назва паблику/людини, звідки переслано повідомлення."""
    f = m.forward
    if not f:
        return None
    key = getattr(f, "chat_id", None) or getattr(f, "sender_id", None) or f.from_name
    if key in cache:
        return cache[key]
    name = None
    try:
        ent = f.chat or f.sender or await f.get_chat() or await f.get_sender()
        name = getattr(ent, "title", None) or getattr(ent, "first_name", None)
    except Exception:
        pass  # приватний канал або прихований профіль
    name = name or f.from_name or "невідоме джерело"
    cache[key] = name
    return name


# ---------- завантаження медіа ----------

async def download_entry(m) -> dict | None:
    try:
        if m.photo:
            raw = await m.download_media(file=bytes)
            return {"kind": "photo", "data": image_to_data_uri(raw, PHOTO_MAX_SIDE, "JPEG")}

        mime = (m.file.mime_type or "") if m.file else ""

        if m.sticker:
            emoji = getattr(m.file, "emoji", None)
            raw = await m.download_media(file=bytes)
            if mime == "application/x-tgsticker":  # анімований (.tgs = gzip з Lottie JSON)
                return {"kind": "animated_sticker", "emoji": emoji,
                        "data": to_data_uri(gzip.decompress(raw), "application/json")}
            if mime == "video/webm":               # відео-стікер
                return {"kind": "video_sticker", "emoji": emoji,
                        "data": to_data_uri(raw, "video/webm")}
            return {"kind": "sticker", "emoji": emoji,  # статичний .webp
                    "data": image_to_data_uri(raw, STICKER_MAX_SIDE, "WEBP")}

        if m.gif:
            size = (m.file.size or 0) if m.file else 0
            if size > MAX_GIF_KB * 1024:
                thumb = await m.download_media(file=bytes, thumb=-1)
                if not thumb:
                    return None
                return {"kind": "gif_preview",
                        "data": image_to_data_uri(thumb, PHOTO_MAX_SIDE, "JPEG")}
            raw = await m.download_media(file=bytes)
            return {"kind": "gif", "data": to_data_uri(raw, mime or "video/mp4")}

    except Exception as e:  # одне бите медіа не повинно зупиняти весь експорт
        print(f"  ! не вдалося обробити медіа в повідомленні {m.id}: {e}")
    return None


# ---------- основне ----------

async def main():
    start, end = day_bounds(sys.argv[1] if len(sys.argv) > 1 else None)
    messages = []
    media: dict[str, dict | None] = {}  # None = вже пробували, не вдалося
    usage = Counter()                   # скільки разів використано кожен тип
    fwd_cache: dict = {}
    forwarded_total = 0

    client = TelegramClient("newspaper", API_ID, API_HASH)
    await client.start()
    try:
        async for m in client.iter_messages(CHAT_ID, offset_date=start, reverse=True):
            if m.date >= end:
                break
            if m.action:  # службові: "X приєднався", "закріплено" тощо
                continue
            text = " ".join(filter(None, [media_tag(m), m.message or ""])).strip()
            if not text:
                continue

            fwd_src = await forward_source(m, fwd_cache) if m.fwd_from else None
            if m.fwd_from:
                forwarded_total += 1

            key = None if m.fwd_from else media_key(m)  # медіа пересланих постів не потрібні
            if key and key not in media:
                media[key] = await download_entry(m)
            if key and media.get(key) is None:
                key = None
            if key:
                usage[media[key]["kind"]] += 1

            messages.append({
                "id": m.id,
                "time": m.date.astimezone(TZ).strftime("%H:%M"),
                "sender_id": m.sender_id,
                "sender": sender_name(m),
                "reply_to": m.reply_to_msg_id,
                "text": text,
                "media_id": key,
                "forwarded": bool(m.fwd_from),
                "fwd_source": fwd_src,
            })
    finally:
        await client.disconnect()

    media = {k: v for k, v in media.items() if v is not None}
    result = {
        "date": f"{start:%Y-%m-%d}",
        "chat_id": CHAT_ID,
        "messages": messages,
        "media": media,
    }

    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / f"{start:%Y-%m-%d}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    size_mb = out.stat().st_size / 1024 / 1024
    print(f"Збережено {len(messages)} повідомлень (з них переслано: {forwarded_total}) -> {out} ({size_mb:.1f} МБ)")
    if usage:
        unique = Counter(v["kind"] for v in media.values())
        print("Медіа (надіслано / унікальних):")
        for kind in sorted(usage):
            print(f"  {kind:<17} {usage[kind]:>4} / {unique[kind]}")
    for msg in messages[:5]:
        reply = f" (↪{msg['reply_to']})" if msg["reply_to"] else ""
        mark = (" 🖼" if msg["media_id"] else "") + (f" ⤷ з «{msg['fwd_source']}»" if msg["forwarded"] else "")
        print(f"[{msg['id']}] {msg['time']} {msg['sender']}{reply}{mark}: {msg['text'][:80]}")


if __name__ == "__main__":
    asyncio.run(main())
