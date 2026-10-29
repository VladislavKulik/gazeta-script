"""Етап 3: верстка газети в один самодостатній HTML-файл.

Вхід:  data/YYYY-MM-DD.json            (export.py — повідомлення і медіа)
       data/YYYY-MM-DD.newspaper.json  (generate.py — тексти газети і статистика)
       template.html                   (шаблон верстки — дизайн міняється тут)
Вихід: output/Газета {name} Випуск №{issue} DD-MM-YYYY.html

Запуск:
    python render.py              -> сьогоднішня доба
    python render.py 2026-10-03   -> конкретна дата
"""

import base64
import json
import os
import re
import sys
from datetime import date as Date, datetime, timedelta
from pathlib import Path

from optimize_media import optimize_media, make_posters, ensure_media_dimensions
from games import (
    WORDLE_STRICT,
    build_quiz_from_quotes,
    cached_word,
    is_games_day,
    load_wordlist,
    obf,
    word_of_day,
)
from weekly import (
    _load,
    collect_weekly_quotes,
    get_weekly_headlines,
    is_weekly_day,
)
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


FONTS_DIR = BASE / "fonts"
# (файл, family, діапазон символів, діапазон ваг[, стиль]) — лише кирилиця й латиниця
FONT_FACES = [
    (
        "onest-cyr.woff2",
        "Onest",
        "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116",
        "100 900",
    ),
    (
        "onest-lat.woff2",
        "Onest",
        "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2190-2193",
        "100 900",
    ),
    (
        "unbounded-cyr.woff2",
        "Unbounded",
        "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116",
        "200 900",
    ),
    (
        "unbounded-lat.woff2",
        "Unbounded",
        "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2190-2193",
        "200 900",
    ),
]


def _font_dirs() -> list[Path]:
    """Де шукати папку fonts/: поруч зі скриптом, на рівень вище (корінь проєкту), у поточній папці."""
    dirs = []
    for d in (BASE / "fonts", BASE.parent / "fonts", Path.cwd() / "fonts"):
        if d.is_dir() and d not in dirs:
            dirs.append(d)
    return dirs


def fonts_css() -> str:
    """Готовий блок <style> з @font-face, де woff2 вбудовані як base64: шрифт є до першого кадру,
    верстка не стрибає, інтернет не потрібен. Порожній рядок, якщо шрифтів немає —
    тоді шаблон підключить їх з Google Fonts."""
    dirs = _font_dirs()
    out, missing = [], []
    for face in FONT_FACES:
        fname, family, rng, weights = face[:4]
        style = face[4] if len(face) > 4 else "normal"
        f = next((d / fname for d in dirs if (d / fname).exists()), None)
        if not f:
            missing.append(fname)
            continue
        b64 = base64.b64encode(f.read_bytes()).decode("ascii")
        out.append(
            f"@font-face{{font-family:'{family}';font-style:{style};font-weight:{weights};font-display:block;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');unicode-range:{rng}}}"
        )
    if missing:
        where = ", ".join(str(d) for d in (dirs or [BASE / "fonts"]))
        print(
            f"  УВАГА: шрифти не вбудовано, немає {', '.join(missing)} (шукав у: {where}) — буде Google Fonts"
        )
        return ""
    return "<style>" + "\n".join(out) + "</style>"


def ua_date(d: Date) -> str:
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]} {d.year}"


def format_period(range_str: str) -> str:
    """Форматує рядок діапазону тижня (наприклад '05.10 – 11.10.2026') у вигляд '5–11 жовтня'."""
    m = re.search(
        r"(\d{1,2})\.(\d{1,2})\s*[–-]\s*(\d{1,2})\.(\d{1,2})\.?(\d{4})?",
        range_str or "",
    )
    if m:
        d1, m1 = int(m.group(1)), int(m.group(2))
        d2, m2 = int(m.group(3)), int(m.group(4))
        if 1 <= m1 <= 12 and 1 <= m2 <= 12:
            if m1 == m2:
                return f"{d1}–{d2} {MONTHS[m2 - 1]}"
            return f"{d1} {MONTHS[m1 - 1]} – {d2} {MONTHS[m2 - 1]}"
    return range_str or ""


def format_headline_date(h: dict) -> str:
    """Форматує дату для 'День за днем': 'Понеділок, 5 жовтня'."""
    d_str = h.get("date")
    if d_str:
        try:
            d = Date.fromisoformat(d_str)
            wday = h.get("weekday") or WEEKDAYS[d.weekday()]
            return f"{wday.capitalize()}, {d.day} {MONTHS[d.month - 1]}"
        except Exception:
            pass
    return h.get("label", "")


def get_weekly_dialogue(day: str, paper: dict) -> dict | None:
    """Повертає 'Діалог тижня': з paper.weekly.dialogue або paper.weekly.content.dialogue, або видобуває найяскравіший діалог тижня."""
    weekly = paper.get("weekly") or {}
    wc = weekly.get("content") or {}
    dlg = weekly.get("dialogue") or wc.get("dialogue")
    if dlg and isinstance(dlg, dict):
        return dlg

    try:
        end = Date.fromisoformat(day)
        days = [end - timedelta(days=i) for i in range(6, -1, -1)]
        for d in days:
            raw = _load(DATA_DIR / f"{d.isoformat()}.json")
            if not raw:
                continue
            msgs = [
                m
                for m in raw.get("messages", [])
                if m.get("text")
                and not m.get("forwarded")
                and not m["text"].startswith("[")
                and 5 <= len(m["text"]) <= 120
            ]
            for i in range(len(msgs) - 3):
                chunk = msgs[i : i + 4]
                senders = [m.get("sender") for m in chunk]
                distinct = list(dict.fromkeys(senders))
                if (
                    len(distinct) == 2
                    and senders[0] != senders[1]
                    and senders[0] == senders[2]
                ):
                    t0, tk = chunk[0].get("time", ""), chunk[-1].get("time", "")
                    if t0 and tk and t0[:2] == tk[:2]:
                        return {
                            "title": "Суперечка тижня",
                            "topic": f"Діалог між {distinct[0]} та {distinct[1]}",
                            "day_label": f"{WEEKDAYS[d.weekday()].capitalize()}, {d.day} {MONTHS[d.month - 1]}",
                            "messages": [
                                {
                                    "sender": m["sender"],
                                    "time": m.get("time", ""),
                                    "text": m["text"],
                                }
                                for m in chunk
                            ],
                            "moral": "Класичний чатовий діалог тижня.",
                        }
    except Exception:
        pass
    return None


def get_weekly_meme(day: str, paper: dict) -> dict | None:
    """Повертає 'Мем тижня': з paper.weekly.meme або paper.weekly.content.meme, або дефолтний зі слова дня."""
    weekly = paper.get("weekly") or {}
    wc = weekly.get("content") or {}
    meme = weekly.get("meme") or wc.get("meme")
    if meme and isinstance(meme, dict):
        return meme

    word_info = paper.get("word")
    if word_info and word_info.get("why"):
        return {
            "word": str(word_info.get("word", "")).upper(),
            "pos": "іменник · тренд тижня",
            "count_chip": f"У чаті — {word_info.get('count', 1)} разів",
            "author": "Комʼюніті",
            "definition": word_info.get("why", ""),
            "example": "",
            "context": "Найчастіше вживане ключове слово тижневого циклу.",
        }
    return None


def get_daily_dialogue(day: str, paper: dict) -> dict | None:
    """Повертає 'Діалог дня': з paper.dialogue або paper.content.dialogue, або видобуває найяскравіший діалог дня."""
    content = paper.get("content") or {}
    dlg = paper.get("dialogue") or content.get("dialogue")
    if dlg and isinstance(dlg, dict):
        msgs = dlg.get("messages") or []
        first_s = msgs[0].get("sender") if msgs else ""
        return {
            "title": dlg.get("title") or "Суперечка дня",
            "topic": dlg.get("topic") or "",
            "time_range": dlg.get("time_range") or "",
            "moral": dlg.get("moral") or "",
            "messages": [
                {
                    "sender": m.get("sender", ""),
                    "time": m.get("time", ""),
                    "text": m.get("text", ""),
                    "is_alt": m.get("is_alt", (m.get("sender") != first_s)),
                }
                for m in msgs
            ],
        }

    try:
        raw = _load(DATA_DIR / f"{day}.json") or paper
        msgs = [
            m
            for m in raw.get("messages", [])
            if m.get("text")
            and not m.get("forwarded")
            and not m["text"].startswith("[")
            and 4 <= len(m["text"]) <= 140
        ]
        for i in range(len(msgs) - 2):
            for k in (4, 3):
                if i + k > len(msgs):
                    continue
                chunk = msgs[i : i + k]
                senders = [m.get("sender") for m in chunk]
                distinct = list(dict.fromkeys(senders))
                if (
                    len(distinct) == 2
                    and senders[0] != senders[1]
                    and senders[0] == senders[2]
                ):
                    t0 = chunk[0].get("time", "")
                    tk = chunk[-1].get("time", "")
                    if t0 and tk and t0[:2] == tk[:2]:
                        first_s = chunk[0].get("sender")
                        return {
                            "title": "Суперечка дня",
                            "topic": f"{distinct[0]} та {distinct[1]}",
                            "time_range": f"{t0} – {tk}",
                            "messages": [
                                {
                                    "sender": m["sender"],
                                    "time": m.get("time", ""),
                                    "text": m["text"],
                                    "is_alt": (m["sender"] != first_s),
                                }
                                for m in chunk
                            ],
                            "moral": "Живий діалог із чату.",
                        }
    except Exception:
        pass
    return None


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


def safe_filename(text: str) -> str:
    """Прибирає символи, недопустимі в іменах файлів (Windows/macOS/Linux)."""
    return re.sub(r'[\\/:*?"<>|]+', "", text or "").strip() or "Газета"


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
        if issue < 1:  # дата раніше за NEWSPAPER_START — номера немає
            issue = None

    used = set()
    if content:
        # Підтримка як нового формату (media_ids / cover_media_id), так і старого архівного (media_id)
        h_ids = content["headline"].get("media_ids") or []
        if not h_ids and content["headline"].get("cover_media_id"):
            h_ids = [content["headline"]["cover_media_id"]]
        elif not h_ids and content["headline"].get("media_id"):
            h_ids = [content["headline"]["media_id"]]
        used |= set(h_ids)
        for a in content["articles"]:
            a_ids = a.get("media_ids") or []
            if not a_ids and a.get("cover_media_id"):
                a_ids = [a["cover_media_id"]]
            elif not a_ids and a.get("media_id"):
                a_ids = [a["media_id"]]
            used |= set(a_ids)
    if stats.get("top_sticker"):
        used.add(stats["top_sticker"]["media_id"])
    used.discard(None)

    # Тижневі новини дня (для спецвипуску)
    weekly_headlines = []
    if is_weekly_day(day) or paper.get("weekly"):
        weekly_headlines = (paper.get("weekly") or {}).get(
            "headlines"
        ) or get_weekly_headlines(day, paper)
        for wh in weekly_headlines:
            mid = wh.get("media_id")
            if mid and mid not in data.get("media", {}):
                raw_day = _load(DATA_DIR / f"{wh['date']}.json")
                if raw_day and mid in raw_day.get("media", {}):
                    data["media"][mid] = raw_day["media"][mid]
            if mid and mid in data.get("media", {}):
                used.add(mid)

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

    # ── Постери для гіфок у галереї ───────────────────────────────────────
    posters = make_posters(opt_media, [g["media_id"] for g in gallery])
    if posters:
        opt_media = dict(opt_media)
        for mid, uri in posters.items():
            opt_media[mid] = {**opt_media[mid], "poster": uri}
        print(f"Постерів для гіфок: {len(posters)}")

    ensure_media_dimensions(opt_media, all_ids)

    # ── Ігри та тижневі блоки ─────────────────────────────────────────────
    weekly = paper.get("weekly")
    if weekly and weekly.get("stats"):
        ws = weekly["stats"]
        tot = ws.get("total_messages", 0)
        days_list = ws.get("per_day") or []
        days_cnt = len(days_list) or 7
        top_senders = ws.get("top_senders") or []
        top_cnt = top_senders[0]["count"] if top_senders else 0
        top_share = round((top_cnt / tot * 100)) if tot else 0
        avg_day = round(tot / days_cnt) if days_cnt else 0
        busiest = ws.get("busiest_day") or {}
        b_date_str = busiest.get("date")
        b_name = ""
        if b_date_str:
            try:
                b_name = WEEKDAYS[Date.fromisoformat(b_date_str).weekday()]
            except Exception:
                b_name = busiest.get("label", "")

        ws["avg_per_day"] = avg_day
        ws["top_share"] = top_share
        ws["msgs_per_hour"] = round(tot / 168, 1)
        ws["busiest_day_name"] = b_name
    w_quotes = []
    if is_weekly_day(day) or paper.get("weekly"):
        w_quotes, w_senders = collect_weekly_quotes(day, paper)

    games_day = is_games_day(
        day
    )  # кросворд і вікторина — лише у «ігровий» день (неділя)
    cw = (content or {}).get("crossword") if games_day else None
    quiz = ((content or {}).get("quiz") or []) if games_day else []
    if games_day and len(quiz) < 3:
        if not w_quotes:
            w_quotes, w_senders = collect_weekly_quotes(day, paper)
        quiz = build_quiz_from_quotes(w_quotes, w_senders, seed=day)

    weekly_quotes = []
    if w_quotes:
        candidates = [q for q in w_quotes if 6 <= len(q.get("text", "")) <= 95]
        seen_senders = set()
        hero_sender = (
            ((weekly or {}).get("content") or {}).get("hero_of_week", {}).get("sender")
        )

        # Спочатку цитата Героя тижня, якщо є
        hero_q = next((q for q in candidates if q.get("sender") == hero_sender), None)
        if hero_q:
            weekly_quotes.append(hero_q)
            seen_senders.add(hero_sender)

        # Потім по одній від інших різних авторів
        for q in candidates:
            if len(weekly_quotes) >= 5:
                break
            s = q.get("sender")
            if s not in seen_senders:
                weekly_quotes.append(q)
                seen_senders.add(s)

        # Добираємо до 5, якщо авторів менше
        for q in candidates:
            if len(weekly_quotes) >= 5:
                break
            if q not in weekly_quotes:
                weekly_quotes.append(q)

    weekly_dialogue = None
    weekly_meme = None
    if is_weekly_day(day) or paper.get("weekly"):
        weekly_meme = get_weekly_meme(day, paper)
        if not weekly_meme:
            weekly_dialogue = get_weekly_dialogue(day, paper)

    daily_dialogue = get_daily_dialogue(day, paper)

    # Wordle — у кожному випуску, нове слово щодня. Беремо зі спарсеного випуску, інакше з кешу дня,
    # інакше (без моделі, без запису в кеш) найчастіше слово дня.
    word = paper.get("word") or cached_word(day)
    if not word and content:
        try:
            word = word_of_day(day, None, save=False)
        except Exception as e:  # noqa: BLE001 — гра не критична
            print(f"  Wordle пропущено: {e}")
    word_meta = word_data = word_dict = None
    if word:
        word_meta = {
            "id": word.get("id") or word.get("week") or day,
            "len": word["len"],
        }
        word_data = obf({k: word.get(k) for k in ("word", "why", "count")})
        # Що приймається як слово: справжній словник (усі форми) + саме слово тижня.
        # WORDLE_STRICT=1 — лише слова з чату. Без словника гра приймала б будь-які літери.
        real_words = [] if WORDLE_STRICT else load_wordlist(word["len"])
        if real_words:
            pool = set(real_words)
        elif WORDLE_STRICT:
            pool = set(word.get("dictionary") or [])
        else:
            pool = set()
        pool.add(word["word"])
        if len(pool) > 1:
            word_dict = " ".join(sorted(pool))
        else:
            print(
                "  УВАГА: немає словника data/words/uk_words.txt — Wordle прийматиме будь-які літери"
            )

    hm_mids = content["headline"].get("media_ids") if content else None
    hm_mid = (
        (hm_mids[0] if hm_mids else None)
        or content["headline"].get("cover_media_id")
        or content["headline"].get("media_id")
        if content
        else None
    )
    hm_media = opt_media.get(hm_mid) if hm_mid else None
    hm_is_h = False
    hm_aspect = ""
    if hm_media and hm_media.get("w") and hm_media.get("h"):
        r = hm_media["w"] / hm_media["h"]
        if r >= 1.1:
            hm_is_h = True
            hm_aspect = f"{min(max(r, 4 / 3), 16 / 9):.3f}"

    env = Environment(
        loader=FileSystemLoader(BASE), autoescape=select_autoescape(["html"])
    )
    env.filters["paragraphs"] = paragraphs
    env.globals["plural"] = plural
    env.globals["format_period"] = format_period
    env.globals["format_headline_date"] = format_headline_date
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
        day=day,
        weekly=weekly,
        weekly_headlines=weekly_headlines,
        weekly_quotes=weekly_quotes,
        weekly_dialogue=weekly_dialogue,
        weekly_meme=weekly_meme,
        daily_dialogue=daily_dialogue,
        cw_data=obf(cw) if cw else None,
        quiz_data=obf(quiz) if len(quiz) >= 3 else None,
        word_data=word_data,
        word_meta=word_meta,
        word_dict=word_dict,
        fonts_css=Markup(fonts_css()),
        hm_is_h=hm_is_h,
        hm_aspect=hm_aspect,
        is_sunday=(d.weekday() == 6),
    )

    OUT_DIR.mkdir(exist_ok=True)
    name_part = safe_filename(paper.get("newspaper_name", "Вісник Чату"))
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
