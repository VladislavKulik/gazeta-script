"""Етап 3: верстка газети в один самодостатній HTML-файл.

Вхід:  data/YYYY-MM-DD.json            (export.py — повідомлення і медіа)
       data/YYYY-MM-DD.newspaper.json  (generate.py — тексти газети і статистика)
       template.html                   (шаблон верстки — дизайн міняється тут)
Вихід: output/Газета {name} Випуск №{issue} DD-MM-YYYY.html

Запуск:
    python render.py              -> сьогоднішня доба
    python render.py 2026-10-03   -> конкретна дата
"""

import json
import os
import re
import sys
import io, base64
from PIL import Image
from datetime import date as Date, datetime
from pathlib import Path

from optimize_media import optimize_media
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

load_dotenv()
BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
OUT_DIR = BASE / "output"
TZ = ZoneInfo(os.getenv("TZ_NAME", "Europe/Kyiv"))
NEWSPAPER_START = os.getenv(
    "NEWSPAPER_START", ""
).strip()  # дата першого випуску -> номер випуску
GALLERY_MAX = int(os.getenv("GALLERY_MAX", "12"))  # скільки фото/гіфок у «Фото дня»

MONTHS = [
    "січня",
    "лютого",
    "березня",
    "квітня",
    "травня",
    "червня",
    "липня",
    "серпня",
    "вересня",
    "жовтня",
    "листопада",
    "грудня",
]
WEEKDAYS = ["понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя"]


def ua_date(d: Date) -> str:
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]} {d.year}"


def paragraphs(text: str) -> Markup:
    parts = [p.strip() for p in re.split(r"\n+", text or "") if p.strip()]
    return Markup("".join(f"<p>{escape(p)}</p>" for p in parts))


def plural(n: int, one: str, few: str, many: str) -> str:
    """Українська множина: 1 стікер, 2 стікери, 5 стікерів."""
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def strip_tag(text: str) -> str:
    return re.sub(r"^\[[^\]]+\]\s*", "", text or "").strip()


def pick_gallery(data: dict, used: set) -> list[dict]:
    """Фото і гіфки, що не потрапили в статті, рівномірно по всьому дню."""
    media = data["media"]
    candidates, seen = [], set(used)
    for m in data["messages"]:
        mid = m.get("media_id")
        if (
            mid in media
            and mid not in seen
            and not m.get("forwarded")
            and media[mid]["kind"] in ("photo", "gif", "gif_preview")
        ):
            seen.add(mid)
            candidates.append(
                {
                    "media_id": mid,
                    "sender": m["sender"],
                    "time": m["time"],
                    "caption": strip_tag(m["text"]),
                }
            )
    if len(candidates) <= GALLERY_MAX:
        return candidates
    step = len(candidates) / GALLERY_MAX
    return [candidates[int(i * step)] for i in range(GALLERY_MAX)]


def media_summary(counts: dict) -> str:
    parts = []
    photo = counts.get("photo", 0)
    stickers = sum(v for k, v in counts.items() if "sticker" in k)
    gifs = counts.get("gif", 0) + counts.get("gif_preview", 0)
    if photo:
        parts.append(f"{photo} {plural(photo, 'фото', 'фото', 'фото')}")
    if stickers:
        parts.append(f"{stickers} {plural(stickers, 'стікер', 'стікери', 'стікерів')}")
    if gifs:
        parts.append(f"{gifs} {plural(gifs, 'гіфка', 'гіфки', 'гіфок')}")
    return ", ".join(parts)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    day = args[0] if args else datetime.now(TZ).strftime("%Y-%m-%d")
    chat_file = DATA_DIR / f"{day}.json"
    paper_file = DATA_DIR / f"{day}.newspaper.json"
    for f, step in ((chat_file, "export.py"), (paper_file, "generate.py")):
        if not f.exists():
            sys.exit(f"Немає файлу {f} — спершу запусти {step} {day}")

    data = json.loads(chat_file.read_text(encoding="utf-8"))
    paper = json.loads(paper_file.read_text(encoding="utf-8"))
    content, stats = paper.get("content"), paper["stats"]
    d = Date.fromisoformat(day)

    issue = None
    if NEWSPAPER_START:
        issue = (d - Date.fromisoformat(NEWSPAPER_START)).days + 1

    used = set()
    if content:
        used |= {content["headline"].get("media_id")} | {
            a.get("media_id") for a in content["articles"]
        }
    if stats.get("top_sticker"):
        used.add(stats["top_sticker"]["media_id"])
    used.discard(None)
    gallery = pick_gallery(data, used) if content else []

    gallery_range = (
        f"{gallery[0]['time']} – {gallery[-1]['time']}" if len(gallery) > 1 else ""
    )

    all_ids = used | {g["media_id"] for g in gallery}
    has_lottie = any(
        data["media"].get(i, {}).get("kind") == "animated_sticker" for i in all_ids
    )

    # ── Оптимізація медіа ─────────────────────────────────────────────────
    skip_optimize = "--no-optimize" in sys.argv
    if skip_optimize:
        opt_media = data["media"]
        opt_report = None
    else:
        print("Оптимізація медіа…")
        result = optimize_media(data["media"], all_ids)
        opt_media = result["media"]
        opt_report = result["report"]

    env = Environment(
        loader=FileSystemLoader(BASE), autoescape=select_autoescape(["html"])
    )
    env.filters["paragraphs"] = paragraphs
    env.globals["plural"] = plural
    html = env.get_template("template.html").render(
        name=paper.get("newspaper_name", "Вісник Чату"),
        date_text=ua_date(d),
        date_short=d.strftime("%d.%m.%Y"),
        issue=issue,
        c=content,
        stats=stats,
        media=opt_media,
        gallery=gallery,
        gallery_range=gallery_range,
        media_summary=media_summary(stats.get("media_counts", {})),
        hour_max=max(stats.get("messages_by_hour") or [0]) or 1,
        sender_max=(
            stats["top_senders"][0]["count"] if stats.get("top_senders") else 1
        ),
        has_lottie=has_lottie,
        model=paper.get("model", ""),
        generated_at=paper.get("generated_at", ""),
    )

    OUT_DIR.mkdir(exist_ok=True)
    name_part = paper.get("newspaper_name", "Вісник Чату")
    date_part = d.strftime("%d-%m-%Y")
    if issue is not None:
        out_name = f"Газета {name_part} Випуск №{issue} {date_part}.html"
    else:
        out_name = f"Газета {name_part} {date_part}.html"
    out = OUT_DIR / out_name
    out.write_text(html, encoding="utf-8")
    file_mb = out.stat().st_size / 1024 / 1024
    print(f"Готово -> {out} ({file_mb:.1f} МБ)")

    if opt_report:
        b = opt_report["total_before"] / 1024
        a = opt_report["total_after"] / 1024
        pct = (1 - a / b) * 100 if b > 0 else 0
        print(f"Медіа до:  {b:.0f} КБ")
        print(f"Медіа після: {a:.0f} КБ  (-{pct:.1f}%)")
        print(f"  Фото -> WebP: {opt_report['images_converted']}")
        print(f"  Відео перекодовано: {opt_report['video_reencoded']}")
        print(f"  Відео пропущено (більші): {opt_report['skipped_larger']}")
        print(f"  Дедуплікація зекономила: {opt_report['dedup_saved'] // 1024} КБ")

    if sys.platform == "win32" and "--no-open" not in sys.argv:
        os.startfile(out)


if __name__ == "__main__":
    main()
