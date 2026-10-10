"""«Головне за тиждень» і Wordle зі словом дня.

Використовує вже згенеровані випуски (data/*.newspaper.json) і сирі вивантаження (data/*.json),
тому окремо нічого запускати не треба — generate.py викликає це сам.
"""

import json
import os
import re
from collections import Counter
from datetime import date as Date, timedelta
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
WORDS_DIR = DATA_DIR / "words"

# У які дні тижня додавати «Головне за тиждень»: 1=пн ... 7=нд, через кому, або "all"
WEEKLY_DAYS = os.getenv("WEEKLY_DAYS", "6").strip().lower()
WORDLE_LEN = int(os.getenv("WORDLE_LEN", "5"))
WORDLE_STRICT = (
    os.getenv("WORDLE_STRICT", "0").strip() == "1"
)  # 1 = приймати лише слова з чату (без загального словника)
UK_WORDS_FILE = (
    WORDS_DIR / "uk_words.txt"
)  # словник справжніх слів: усі форми, по одному слову в рядку

UA_LOWER = "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя"
TOKEN_RE = re.compile(r"[а-яіїєґёыэъ'ʼ’]+", re.I)
DAY_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]

# Службові слова, які не годяться у «слово тижня»
STOP = set(
    """
тобто треба також можна зараз тільки взагалі просто якщо коли поки потім після через перед
навіть щось хтось ніхто нічого чомусь завжди тепер досить більше менше дуже трохи багато
який яка яке які якого якої якій своїх свого своєї мене тебе нього неї нами вами ними
цього цієї цьому цими цієї того тому таке такий така такі тоді звідти звідки куди туди
нехай мабуть ніби наче майже також зовсім звісно дякую добре гарно погано знаєш думаю
знову вдома чесно хочеш можеш давай буде були була було могли хіба
""".split()
)


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
    return {
        "title": str(c["title"]).strip(),
        "intro": str(c.get("intro", "")).strip(),
        "stories": stories[:5],
        "hero_of_week": {
            k: str(hero.get(k, "")).strip() for k in ("sender", "title", "reason")
        },
    }


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


# ====================== WORDLE: СЛОВО ДНЯ ======================

WORD_SCHEMA = {
    "type": "object",
    "properties": {"word": {"type": "string"}, "why": {"type": "string"}},
    "required": ["word", "why"],
}

WORD_PROMPT = """Обери слово дня для гри Wordle з переліку найчастіших слів дружнього чату за сьогодні.
Правила вибору:
- Слово має бути саме з переліку, українською, звичайне повнозначне слово (краще іменник), характерне саме для цього дня.
- Не обирай нецензурні слова, імена, службові слова.
- why — 1–2 речення, чому це слово дня, з контекстом із чату (показується після гри; саме слово не приховуй).
Відповідай ЛИШЕ JSON: {"word": "...", "why": "..."}"""


def _tokens(msgs: list[dict]) -> Counter:
    cnt = Counter()
    for m in msgs:
        for t in TOKEN_RE.findall(m.get("text", "").lower()):
            t = t.replace("ʼ", "'").replace("’", "'")
            if (
                len(t) == WORDLE_LEN
                and len(set(t)) >= 3
                and all(ch in UA_LOWER for ch in t)
                and t not in STOP
            ):  # ≥3 різних літер: відсіює «ахаха»
                cnt[t] += 1
    return cnt


@lru_cache(maxsize=1)
def _all_words() -> tuple[str, ...]:
    try:
        return tuple(UK_WORDS_FILE.read_text(encoding="utf-8").split())
    except OSError:
        return ()


def load_wordlist(length: int) -> list[str]:
    """Справжні українські слова потрібної довжини зі словника data/words/uk_words.txt
    (усі словоформи, без власних назв). Порожній список, якщо файлу немає."""
    return sorted({x for x in _all_words() if len(x) == length})


def _used_words() -> set[str]:
    """Слова, що вже були «словом дня» (щоб не повторювалися)."""
    used = set()
    for f in WORDS_DIR.glob("????-??-??.json"):
        w = (_load(f) or {}).get("word")
        if w:
            used.add(w)
    return used


def cached_word(day: str) -> dict | None:
    """Слово цього дня з кешу, без звернень до моделі."""
    cache = WORDS_DIR / f"{day}.json"
    return _load(cache) if cache.exists() else None


def word_of_day(day: str, ask_json, save: bool = True) -> dict | None:
    """Одне слово на день, обране з переписки цього дня (якщо повідомлень мало — з попередніх двох).
    Зберігається в data/words/РРРР-ММ-ДД.json, тож повторний запуск дає ту саму гру.
    Слова, що вже були, не повторюються."""
    d = Date.fromisoformat(day)
    cache = WORDS_DIR / f"{day}.json"
    if cache.exists():
        return _load(cache)

    real = set(
        load_wordlist(WORDLE_LEN)
    )  # справжні слова: відсіюємо сленг, «ахаха» й набори літер
    used = _used_words()

    def count(days: int) -> Counter:
        cnt = _tokens([m for x in _days(d, days) for m in _messages(x)])
        if real:
            cnt = Counter({w: n for w, n in cnt.items() if w in real})
        return cnt

    counts, candidates = Counter(), []
    for span in (1, 3, 7):  # спершу лише цей день, потім ширше
        counts = count(span)
        fresh = {w: n for w, n in counts.items() if w not in used}
        candidates = [
            w for w, n in sorted(fresh.items(), key=lambda x: (-x[1], x[0])) if n >= 2
        ][:40]
        if len(candidates) < 5:
            candidates = [
                w for w, n in sorted(fresh.items(), key=lambda x: (-x[1], x[0]))
            ][:40]
        if len(candidates) >= 5:
            break
    if (
        not candidates and counts
    ):  # всі слова вже були — беремо найчастіше, хай і повтор
        candidates = [w for w, _ in counts.most_common(40)]
    if not candidates:
        print(f"  Wordle: немає {WORDLE_LEN}-літерних українських слів, пропускаю")
        return None

    listing = ", ".join(f"{w} ({counts[w]})" for w in candidates)

    def post(c):
        w = str((c or {}).get("word", "")).strip().lower()
        if w not in candidates:
            raise ValueError(f"слово «{w}» не з переліку")
        return {"word": w, "why": str(c.get("why", "")).strip()}

    try:
        if ask_json is None:  # без моделі: беремо найчастіше слово
            raise RuntimeError("модель не передано")
        pick = ask_json(
            WORD_PROMPT,
            "Перелік (слово і кількість згадок):\n" + listing,
            WORD_SCHEMA,
            post,
        )
    except Exception as e:
        print(f"  Wordle: модель не впоралась ({e}), беру найчастіше слово")
        pick = {"word": candidates[0], "why": ""}

    result = {
        "id": day,
        "week": day,  # застаріла назва поля, лишена для сумісності зі старим кодом
        "len": WORDLE_LEN,
        "word": pick["word"],
        "hint": "",  # підказок більше немає, поле лишене для сумісності
        "why": pick["why"],
        "count": counts[pick["word"]],
        "dictionary": sorted(
            counts
        ),  # слова з чату (приймаються як правильні, навіть якщо їх немає у словнику)
    }
    if save:
        WORDS_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


word_of_week = word_of_day  # стара назва: generate.py міг імпортувати її
