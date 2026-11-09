"""Тижневий випуск: «Підсумок тижня», «Обране за тиждень», цифри, цитати та кросворд для ігор.

Використовує вже згенеровані випуски (data/*.newspaper.json) і сирі вивантаження (data/*.json),
тому окремо нічого запускати не треба — generate.py викликає це сам.

«Обране за тиждень» (weekly["picks"]): модель обирає найсмішніші й найцікавіші новини з випусків тижня. Вона лише
називає номери зі списку кандидатів — тексти й медіа беруться з оригінальних випусків без переписування. Поточний
випуск у кандидатах не бере участі: його новини вже стоять у «Головному».
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

    try:
        picks = build_picks(day, today_paper, ask_json, name)
    except Exception as e:  # «Обране» не повинно ламати підсумок тижня
        print(f"  «Обране за тиждень» пропущено: {e}")
        picks = []

    total = sum(p["count"] for p in per_day)
    busiest = max(per_day, key=lambda p: p["count"])
    return {
        "range": rng,
        "content": content,
        "headlines": get_weekly_headlines(day, today_paper),
        "picks": picks,
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
        lead_text = str(h.get("lead") or h.get("subtitle") or "").strip()
        if not lead_text and h.get("body"):
            lead_text = str(h.get("body", "")).strip().split("\n")[0].strip()[:180]
        headlines.append(
            {
                "date": iso,
                "date_short": f"{d.day:02d}.{d.month:02d}",
                "label": DAY_SHORT[d.weekday()],
                "weekday": WEEKDAYS[d.weekday()],
                "title": str(h.get("title", "")).strip(),
                "subtitle": str(h.get("subtitle", "")).strip(),
                "lead": lead_text,
                "body": str(h.get("body", "")).strip(),
                "media_id": (
                    (h.get("media_ids") or [h.get("cover_media_id") or h.get("media_id")])[0]
                    if (h.get("media_ids") or h.get("cover_media_id") or h.get("media_id"))
                    else None
                ),
            }
        )
    return headlines


# ====================== ОБРАНЕ ЗА ТИЖДЕНЬ ======================

PICKS_MAX = int(os.getenv("WEEKLY_PICKS", "6"))  # скільки новин брати
PICKS_PER_DAY = int(os.getenv("WEEKLY_PICKS_PER_DAY", "2"))  # максимум з одного дня

PICKS_SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {"type": "integer"}}},
    "required": ["picks"],
}

PICKS_PROMPT = """Ти — редактор жартівливої газети «{name}» дружнього чату.
Нижче — нумерований список новин із випусків за тиждень {range}. Обери для рубрики «Обране за тиждень» {count} новин,
які варто (пере)прочитати: найсмішніші, найнезвичайніші або найцікавіші.
Правила:
- Обирай лише номери зі списку. Нічого не вигадуй і не переписуй.
- Не більше {per_day} новин з одного дня; за рівних варіантів чергуй дні.
- Нудну побутову дрібницю пропускай; вище став те, що смішне чи добре розповідає історію.
- Порядок — від найкращої до слабшої.
Відповідай ЛИШЕ JSON:
{"picks": [3, 7, 12]}"""


def _lead_of(x: dict) -> str:
    lead = str(x.get("lead") or x.get("subtitle") or "").strip()
    if not lead and x.get("body"):
        lead = str(x["body"]).strip().split("\n")[0].strip()[:180]
    return lead


def _media_ids_of(x: dict) -> list:
    ids = list(x.get("media_ids") or [])
    if not ids and (x.get("cover_media_id") or x.get("media_id")):
        ids = [x.get("cover_media_id") or x.get("media_id")]
    return [i for i in ids if i]


def _pick_from(d: Date, kind: str, x: dict, rubric: str) -> dict | None:
    title = str(x.get("title", "")).strip()
    if not title:
        return None
    return {
        "date": d.isoformat(),
        "date_short": f"{d.day:02d}.{d.month:02d}",
        "label": DAY_SHORT[d.weekday()],
        "weekday": WEEKDAYS[d.weekday()],
        "kind": kind,  # headline | article
        "rubric": rubric,
        "slug": str(x.get("slug", "")).strip(),
        "title": title,
        "subtitle": str(x.get("subtitle", "")).strip(),
        "lead": _lead_of(x),
        "body": str(x.get("body", "")).strip(),
        "media_ids": _media_ids_of(x),
    }


def collect_pick_candidates(day: str, today_paper: dict | None = None) -> list[dict]:
    """Новина дня й статті з випусків тижня, КРІМ поточного: його новини вже є в «Головному», тож у «Обране»
    вони не потрапляють (так одна історія не з'являється у випуску двічі). Збіг за назвою теж відсікається."""
    end = Date.fromisoformat(day)
    c0 = (today_paper or {}).get("content") or {}
    today_titles = {str((c0.get("headline") or {}).get("title", "")).strip().lower()}
    today_titles |= {str(a.get("title", "")).strip().lower() for a in c0.get("articles") or []}
    today_titles.discard("")

    out = []
    for d in _days(end):
        if d.isoformat() == day:
            continue
        c = (_load(DATA_DIR / f"{d.isoformat()}.newspaper.json") or {}).get("content")
        if not c:
            continue
        cand = []
        if c.get("headline"):
            cand.append(_pick_from(d, "headline", c["headline"], "Новина дня"))
        for a in c.get("articles") or []:
            cand.append(_pick_from(d, "article", a, str(a.get("rubric", "")).strip() or "Новини"))
        out += [p for p in cand if p and p["title"].lower() not in today_titles]
    return out


def get_weekly_picks_fallback(day: str, today_paper: dict | None = None) -> list[dict]:
    """Без моделі: головні новини днів тижня (крім поточного). Для випусків, згенерованих до появи «Обраного»."""
    heads = [p for p in collect_pick_candidates(day, today_paper) if p["kind"] == "headline"]
    return heads[:PICKS_MAX]


def _picks_validate(c, cands: list[dict], limit: int) -> list[dict]:
    if not isinstance(c, dict) or not isinstance(c.get("picks"), list):
        raise ValueError("немає списку picks")
    seen, per_day, res = set(), Counter(), []
    for it in c["picks"]:
        if isinstance(it, int):
            it = {"n": it}
        if not isinstance(it, dict):
            continue
        try:
            n = int(it.get("n"))
        except (TypeError, ValueError):
            continue
        if n in seen or not (1 <= n <= len(cands)):
            continue  # вигаданий або повторений номер
        p = cands[n - 1]
        if per_day[p["date"]] >= PICKS_PER_DAY:
            continue
        seen.add(n)
        per_day[p["date"]] += 1
        res.append(dict(p))
        if len(res) >= limit:
            break
    if not res:
        raise ValueError("жодного коректного номера")
    return res


def build_picks(day: str, today_paper: dict, ask_json, name: str) -> list[dict]:
    """ask_json(system, user, schema, post) — та сама функція запиту до моделі, що й для «Підсумку тижня»."""
    cands = collect_pick_candidates(day, today_paper)
    if not cands:
        return []
    limit = min(PICKS_MAX, len(cands))
    if len(cands) <= 3:  # обирати нема з чого
        return cands
    days = _days(Date.fromisoformat(day))
    rng = f"{days[0]:%d.%m} – {days[-1]:%d.%m.%Y}"
    system = (
        PICKS_PROMPT.replace("{name}", name).replace("{range}", rng)
        .replace("{count}", str(limit)).replace("{per_day}", str(PICKS_PER_DAY))
    )
    lines = [
        f"[{i}] {p['date']} ({p['label']}) · {p['rubric']}: {p['title']} — {p['lead'][:220]}"
        for i, p in enumerate(cands, 1)
    ]
    try:
        return ask_json(system, "\n".join(lines), PICKS_SCHEMA, lambda c: _picks_validate(c, cands, limit))
    except Exception as e:
        print(f"  «Обране за тиждень»: модель не впоралась ({e}), беру головні новини днів")
        return get_weekly_picks_fallback(day, today_paper)


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
                        "message_id": q.get("message_id", 0),
                    }
                )
    top_senders = [s for s, _ in senders.most_common(20)]
    return quotes, top_senders


# ====================== ТИЖНЕВИЙ КРОСВОРД ======================


def collect_weekly_crossword_material(
    day: str, today_paper: dict | None = None
) -> str:
    """Збирає підсумок подій, тем, статей, героїв і цитат за останні 7 днів для тижневого кросворду."""
    end = Date.fromisoformat(day)
    days = _days(end)
    sections = []
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

        c = (paper or {}).get("content")
        if not c:
            continue

        day_lines = [
            f"=== {iso} ({DAY_SHORT[d.weekday()]}, {WEEKDAYS[d.weekday()]}) ==="
        ]

        # Головна новина
        h = c.get("headline") or {}
        if h.get("title"):
            lead = str(h.get("lead") or h.get("subtitle") or "").strip()
            day_lines.append(
                f"Головна новина: {h['title']}" + (f" — {lead}" if lead else "")
            )

        # Статті
        for a in c.get("articles") or []:
            t = str(a.get("title", "")).strip()
            if t:
                rubric = str(a.get("rubric", "")).strip() or "Тема"
                lead = str(a.get("lead") or a.get("subtitle") or "").strip()
                day_lines.append(
                    f"Стаття [{rubric}]: {t}" + (f" — {lead}" if lead else "")
                )

        # Короткі новини
        news = [str(n).strip() for n in c.get("short_news") or [] if str(n).strip()]
        if news:
            day_lines.append("Коротко: " + "; ".join(news[:4]))

        # Герой дня
        hero = c.get("hero_of_day")
        if isinstance(hero, dict) and hero.get("sender"):
            day_lines.append(
                f"Герой дня: {hero['sender']} ({hero.get('title', '')}) — {hero.get('reason', '')}"
            )

        # Цитати
        quotes = c.get("quotes") or []
        for q in quotes[:3]:
            if isinstance(q, dict) and q.get("text") and q.get("sender"):
                day_lines.append(f"Цитата ({q['sender']}): «{q['text'][:120]}»")

        sections.append("\n".join(day_lines))

    top_senders = ", ".join(s for s, _ in senders.most_common(8) if s)
    header = f"Найактивніші учасники тижня: {top_senders}\n\n" if top_senders else ""
    return header + "\n\n".join(sections)


def build_weekly_crossword(
    day: str,
    today_paper: dict,
    ask_json,
    name: str,
    count: int = 14,
) -> dict | None:
    """Будує тижневий кросворд: збирає зведення за 7 днів, просить слова у моделі та розкладає сітку."""
    import games

    material = collect_weekly_crossword_material(day, today_paper)
    if not material.strip():
        return None

    days = _days(Date.fromisoformat(day))
    rng = f"{days[0]:%d.%m} – {days[-1]:%d.%m.%Y}"

    words = games.generate_crossword_words(
        material, ask_json, name=name, count=count, rng=rng
    )
    if not words:
        return None

    return games.build_crossword(words, seed=day)
