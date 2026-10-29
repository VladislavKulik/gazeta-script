"""«Головне за тиждень».

Використовує вже згенеровані випуски (data/*.newspaper.json) і сирі вивантаження (data/*.json),
тому окремо нічого запускати не треба — generate.py викликає це сам.
"""

import json
import os
from collections import Counter
from datetime import date as Date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# У які дні тижня додавати «Головне за тиждень»: 1=пн ... 7=нд, через кому, або "all"
WEEKLY_DAYS = os.getenv("WEEKLY_DAYS", "7").strip().lower()
DAY_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]
WEEKDAYS = ["понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя"]


def is_weekly_day(day: str) -> bool:
    if WEEKLY_DAYS == "all":
        return True
    wd = Date.fromisoformat(day).isoweekday()
    return str(wd) in {x.strip() for x in WEEKLY_DAYS.split(",")}


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _days(end: Date, n=7) -> list[Date]:
    return [end - timedelta(days=i) for i in range(n - 1, -1, -1)]


def _messages(d: Date) -> list[dict]:
    raw = _load(DATA_DIR / f"{d.isoformat()}.json")
    if not raw:
        return []
    return [m for m in raw.get("messages", []) if not m.get("forwarded")]


# ====================== ГОЛОВНЕ ЗА ТИЖДЕНЬ ======================

WEEKLY_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "intro": {"type": "string"},
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "title": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["date", "title", "text"],
            },
        },
        "hero_of_week": {
            "type": "object",
            "properties": {
                "sender": {"type": "string"},
                "title": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["sender", "title", "reason"],
        },
    },
    "required": ["title", "intro", "stories", "hero_of_week"],
}

WEEKLY_PROMPT = """Ти — головний редактор жартівливої газети «{name}» дружнього чату.
Тобі дають короткі підсумки щоденних випусків за тиждень {range}. Склади рубрику «Головне за тиждень».
Правила:
- Пиши українською, з гумором, без образ. Нічого не вигадуй — лише те, що є у випусках.
- title — заголовок тижня, одне речення.
- intro — 2–3 речення про те, яким був тиждень у чаті.
- stories — 3–5 найважливіших або найсмішніших історій тижня; date у форматі РРРР-ММ-ДД з наданих днів; text — 2–4 речення.
- hero_of_week — герой тижня: ім'я точно як у випусках, жартівливе звання і за що.
Відповідай ЛИШЕ JSON:
{"title": "...", "intro": "...", "stories": [{"date": "2026-10-01", "title": "...", "text": "..."}],
 "hero_of_week": {"sender": "...", "title": "...", "reason": "..."}}"""


def _weekly_validate(c, valid_dates: set) -> dict:
    if not isinstance(c, dict) or not str(c.get("title", "")).strip():
        raise ValueError("немає заголовка тижня")
    stories = []
    for s in c.get("stories") or []:
        if isinstance(s, dict) and str(s.get("title", "")).strip():
            d = str(s.get("date", "")).strip()
            stories.append(
                {
                    "date": d if d in valid_dates else "",
                    "title": str(s["title"]).strip(),
                    "text": str(s.get("text", "")).strip(),
                }
            )
    hero = c.get("hero_of_week") if isinstance(c.get("hero_of_week"), dict) else {}
    res = {
        "title": str(c["title"]).strip(),
        "intro": str(c.get("intro", "")).strip(),
        "stories": stories[:5],
        "hero_of_week": {
            k: str(hero.get(k, "")).strip() for k in ("sender", "title", "reason")
        },
    }
    if isinstance(c.get("meme"), dict):
        res["meme"] = c["meme"]
    if isinstance(c.get("dialogue"), dict):
        res["dialogue"] = c["dialogue"]
    return res


def build_weekly(day: str, today_paper: dict, ask_json, name: str) -> dict | None:
    """ask_json(system, user, schema, post) — функція запиту до моделі з generate.py."""
    end = Date.fromisoformat(day)
    days = _days(end)
    digest, per_day, senders = [], [], Counter()

    for d in days:
        iso = d.isoformat()
        paper = today_paper if iso == day else _load(DATA_DIR / f"{iso}.newspaper.json")
        msgs = _messages(d)
        total = (
            len(msgs)
            if msgs
            else ((paper or {}).get("stats") or {}).get("total_messages", 0)
        )
        per_day.append(
            {"date": iso, "label": DAY_SHORT[d.weekday()], "day": d.day, "count": total}
        )
        senders.update(m["sender"] for m in msgs)
        c = (paper or {}).get("content")
        if c:
            arts = "; ".join(a["title"] for a in c.get("articles", []))
            news = "; ".join(c.get("short_news", [])[:4])
            hero = c.get("hero_of_day", {})
            digest.append(
                f"[{iso}, {DAY_SHORT[d.weekday()]}] Головна: {c['headline']['title']} — {c['headline'].get('subtitle', '')}\n"
                f"  Статті: {arts}\n  Коротко: {news}\n"
                f"  Герой дня: {hero.get('sender', '')} ({hero.get('title', '')})\n"
                f"  Повідомлень: {total}"
            )

    if len(digest) < 2:
        print("  «Головне за тиждень»: замало випусків за тиждень, пропускаю")
        return None

    rng = f"{days[0]:%d.%m} – {days[-1]:%d.%m.%Y}"
    system = WEEKLY_PROMPT.replace("{name}", name).replace("{range}", rng)
    valid = {d.isoformat() for d in days}
    content = ask_json(
        system, "\n\n".join(digest), WEEKLY_SCHEMA, lambda c: _weekly_validate(c, valid)
    )

    total = sum(p["count"] for p in per_day)
    busiest = max(per_day, key=lambda p: p["count"])
    return {
        "range": rng,
        "content": content,
        "headlines": get_weekly_headlines(day, today_paper),
        "stats": {
            "total_messages": total,
            "per_day": per_day,
            "per_day_max": max(1, busiest["count"]),
            "busiest_day": busiest,
            "top_senders": [
                {"sender": s, "count": n} for s, n in senders.most_common(5)
            ],
        },
    }


def get_weekly_headlines(day: str, today_paper: dict | None = None) -> list[dict]:
    """Збирає головні новини («Новина дня») за кожен день тижня."""
    end = Date.fromisoformat(day)
    days = _days(end)
    headlines = []
    for d in days:
        iso = d.isoformat()
        paper = (
            today_paper
            if (today_paper and iso == day)
            else _load(DATA_DIR / f"{iso}.newspaper.json")
        )
        if not paper:
            continue
        c = paper.get("content")
        if not c or not c.get("headline"):
            continue
        h = c["headline"]
        headlines.append(
            {
                "date": iso,
                "date_short": f"{d.day:02d}.{d.month:02d}",
                "label": DAY_SHORT[d.weekday()],
                "weekday": WEEKDAYS[d.weekday()],
                "title": str(h.get("title", "")).strip(),
                "subtitle": str(h.get("subtitle", "")).strip(),
                "body": str(h.get("body", "")).strip(),
                "media_id": (
                    (h.get("media_ids") or [h.get("cover_media_id") or h.get("media_id")])[0]
                    if (h.get("media_ids") or h.get("cover_media_id") or h.get("media_id"))
                    else None
                ),
            }
        )
    return headlines


def collect_weekly_quotes(
    day: str, today_paper: dict | None = None
) -> tuple[list[dict], list[str]]:
    """Збирає цитати дня та найактивніших авторів за останні 7 днів для гри «Угадай цитату»."""
    end = Date.fromisoformat(day)
    days = _days(end)
    quotes = []
    senders = Counter()
    for d in days:
        iso = d.isoformat()
        paper = (
            today_paper
            if (today_paper and iso == day)
            else _load(DATA_DIR / f"{iso}.newspaper.json")
        )
        msgs = _messages(d)
        senders.update(m["sender"] for m in msgs)
        if paper and paper.get("content"):
            c_quotes = paper["content"].get("quotes", [])
            for q in c_quotes:
                s = q.get("sender")
                if s:
                    senders[s] += 1
                quotes.append(
                    {
                        "date": iso,
                        "date_short": f"{d.day:02d}.{d.month:02d}",
                        "sender": q.get("sender", ""),
                        "text": q.get("text", ""),
                        "time": q.get("time", ""),
                        "comment": q.get("comment", ""),
                        "message_id": q.get("message_id", 0),
                    }
                )
    top_senders = [s for s, _ in senders.most_common(20)]
    return quotes, top_senders
