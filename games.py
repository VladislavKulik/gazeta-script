"""Ігри газети: кросворд, «Угадай цитату» та Wordle (слово дня).

Модель лише пропонує матеріал (слова з підказками, id смішних повідомлень, вибір слова дня),
а все, що має бути точним — розкладка кросворду, варіанти відповідей, перевірка словника Wordle — рахується тут.
"""

import base64
import json
import os
import random
import re
from collections import Counter
from datetime import date as Date, timedelta
from functools import lru_cache
from pathlib import Path

# У які дні виходять кросворд і «Вгадай, хто це сказав»: 1=пн ... 7=нд, через кому, або "all"
GAMES_DAYS = os.getenv("GAMES_DAYS", "7").strip().lower()

UA_LETTERS = "АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ"
WORD_RE = re.compile(f"^[{UA_LETTERS}]+$")


def is_games_day(day: str) -> bool:
    """Кросворд і вікторина — лише у вказані дні (за замовчуванням неділя).
    Wordle («слово дня») не залежить від цього: воно у кожному випуску."""
    if GAMES_DAYS == "all":
        return True
    wd = Date.fromisoformat(day).isoweekday()
    return str(wd) in {x.strip() for x in GAMES_DAYS.split(",")}


def obf(obj) -> str:
    """Легке приховування відповідей у коді сторінки, щоб не підглянути випадково."""
    return base64.b64encode(json.dumps(obj, ensure_ascii=False).encode("utf-8")).decode(
        "ascii"
    )


# ====================== КРОСВОРД ======================


def clean_crossword_words(raw: list, min_len=3, max_len=12) -> list[dict]:
    """Залишає лише слова з українських літер без пробілів/апострофів, без дублікатів."""
    out, seen = [], set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        ans = str(item.get("answer", "")).strip().upper().replace("Ё", "Е")
        clue = str(item.get("clue", "")).strip()
        if (
            not clue
            or not WORD_RE.match(ans)
            or not (min_len <= len(ans) <= max_len)
            or ans in seen
        ):
            continue
        # підказка не повинна містити саму відповідь
        if ans.lower() in clue.lower():
            continue
        seen.add(ans)
        out.append({"answer": ans, "clue": clue})
    return out


def _fits(grid, dirs, word, r, c, d):
    """Чи можна поставити слово: літери збігаються, сусіди порожні, немає злиття зі словами поруч."""
    dr, dc = (0, 1) if d == "a" else (1, 0)
    pr, pc = (1, 0) if d == "a" else (0, 1)  # перпендикулярний напрям
    # клітинки перед початком і після кінця мають бути порожні
    if (r - dr, c - dc) in grid or (r + dr * len(word), c + dc * len(word)) in grid:
        return -1
    crossings = 0
    for k, ch in enumerate(word):
        cell = (r + dr * k, c + dc * k)
        if cell in grid:
            if grid[cell] != ch or d in dirs[cell]:
                return -1
            crossings += 1
        else:
            if (cell[0] + pr, cell[1] + pc) in grid or (
                cell[0] - pr,
                cell[1] - pc,
            ) in grid:
                return -1
    return crossings


def _attempt(words, rnd):
    grid, dirs, placed = {}, {}, []

    def put(w, r, c, d):
        dr, dc = (0, 1) if d == "a" else (1, 0)
        for k, ch in enumerate(w["answer"]):
            cell = (r + dr * k, c + dc * k)
            grid[cell] = ch
            dirs.setdefault(cell, set()).add(d)
        placed.append({**w, "r": r, "c": c, "d": d})

    first = words[0]
    put(first, 0, 0, "a")
    for w in words[1:]:
        ans, options = w["answer"], []
        for p in placed:
            nd = "d" if p["d"] == "a" else "a"
            for i, ch in enumerate(ans):
                for j, ch2 in enumerate(p["answer"]):
                    if ch != ch2:
                        continue
                    pr = p["r"] + (j if p["d"] == "d" else 0)
                    pc = p["c"] + (j if p["d"] == "a" else 0)
                    r, c = (pr, pc - i) if nd == "a" else (pr - i, pc)
                    score = _fits(grid, dirs, ans, r, c, nd)
                    if score > 0:
                        options.append((score + rnd.random() * 0.5, r, c, nd))
        if options:
            options.sort(reverse=True)
            _, r, c, d = options[0]
            put(w, r, c, d)
    return placed, grid


def build_crossword(
    words: list[dict], seed: str, max_side=17, tries=300
) -> dict | None:
    """Шукає найкращу розкладку: більше слів, компактніша сітка."""
    if len(words) < 4:
        return None
    rnd = random.Random(seed)
    best, best_score = None, None
    for t in range(tries):
        order = sorted(words, key=lambda w: len(w["answer"]), reverse=True)
        if t:
            head, tail = order[:3], order[3:]
            rnd.shuffle(head)
            rnd.shuffle(tail)
            order = head + tail
        placed, grid = _attempt(order, rnd)
        rows = [r for r, _ in grid]
        cols = [c for _, c in grid]
        h, w = max(rows) - min(rows) + 1, max(cols) - min(cols) + 1
        if max(h, w) > max_side:
            continue
        score = (len(placed), -(h * w), -abs(h - w))
        if best_score is None or score > best_score:
            best_score, best = score, (placed, min(rows), min(cols), h, w)
    if not best or len(best[0]) < 4:
        return None

    placed, r0, c0, h, w = best
    for p in placed:
        p["r"] -= r0
        p["c"] -= c0
    # нумерація клітинок у порядку читання
    starts = sorted({(p["r"], p["c"]) for p in placed})
    num = {cell: i + 1 for i, cell in enumerate(starts)}
    entries = [
        {
            "n": num[(p["r"], p["c"])],
            "r": p["r"],
            "c": p["c"],
            "d": p["d"],
            "ans": p["answer"],
            "clue": p["clue"],
        }
        for p in placed
    ]
    entries.sort(key=lambda e: (e["d"], e["n"]))
    return {"w": w, "h": h, "entries": entries}


# ====================== УГАДАЙ ЦИТАТУ ======================

LINK_RE = re.compile(r"https?://|t\.me/|www\.", re.I)


def _good_quote(m: dict, min_len=20, max_len=280) -> bool:
    t = (m.get("text") or "").strip()
    return (
        not m.get("forwarded")
        and not t.startswith("[")
        and not LINK_RE.search(t)
        and min_len <= len(t) <= max_len
    )


def build_quiz(
    ids: list[int], data: dict, exclude: set, seed: str, size=6, options=4
) -> list[dict]:
    """Питання «хто це сказав»: цитата + 4 варіанти автора (правильний + найактивніші інші)."""
    msgs = [m for m in data["messages"] if not m.get("forwarded")]
    by_id = {m["id"]: m for m in msgs}
    rnd = random.Random(seed + "quiz")

    senders = [
        s for s, _ in sorted({m["sender"]: 0 for m in msgs}.items())
    ]  # стабільний порядок
    counts = {}
    for m in msgs:
        counts[m["sender"]] = counts.get(m["sender"], 0) + 1
    active = sorted(senders, key=lambda s: -counts[s])
    if len(active) < 2:
        return []

    chosen, used_ids = [], set(exclude)
    for i in ids or []:
        m = by_id.get(i)
        if (
            m
            and m["id"] not in used_ids
            and _good_quote(m)
            and m["sender"].split()[0].lower() not in m["text"].lower()
        ):
            chosen.append(m)
            used_ids.add(m["id"])
        if len(chosen) >= size:
            break

    # якщо модель дала замало — добираємо випадкові «змістовні» повідомлення
    if len(chosen) < size:
        pool = [m for m in msgs if m["id"] not in used_ids and _good_quote(m, 40, 200)]
        rnd.shuffle(pool)
        for m in pool:
            if sum(1 for x in chosen if x["sender"] == m["sender"]) >= 2:
                continue  # не більше двох цитат від однієї людини
            chosen.append(m)
            if len(chosen) >= size:
                break

    quiz = []
    for m in chosen:
        others = [s for s in active if s != m["sender"]][: max(options * 2, 6)]
        rnd.shuffle(others)
        opts = others[: options - 1] + [m["sender"]]
        rnd.shuffle(opts)
        quiz.append(
            {
                "text": m["text"],
                "time": m["time"],
                "options": opts,
                "answer": opts.index(m["sender"]),
            }
        )
    return quiz


def build_quiz_from_quotes(
    quotes: list[dict],
    senders_pool: list[str] | set[str] | None,
    seed: str,
    size: int = 6,
    options: int = 4,
) -> list[dict]:
    """Будує вікторину «хто це сказав» із блоків «Цитати дня» за тиждень.

    quotes: список цитат {text, sender, time, date/date_short, ...}
    senders_pool: список/множина учасників чату для варіантів відповідей
    """
    if not quotes:
        return []

    rnd = random.Random(seed + "quiz")
    active_senders = [s for s in (senders_pool or []) if s]
    if len(set(active_senders)) < options:
        for q in quotes:
            s = q.get("sender")
            if s and s not in active_senders:
                active_senders.append(s)

    unique_active = list(dict.fromkeys(active_senders))
    if len(unique_active) < 2:
        return []

    valid = []
    seen_texts = set()
    for q in quotes:
        text = (q.get("text") or "").strip()
        sender = (q.get("sender") or "").strip()
        if not text or not sender:
            continue
        if text in seen_texts:
            continue
        first_name = sender.split()[0].lower()
        if len(first_name) >= 3 and first_name in text.lower():
            continue
        if len(text) < 15 or len(text) > 350:
            continue
        if LINK_RE.search(text):
            continue
        seen_texts.add(text)
        valid.append(q)

    if not valid:
        return []

    rnd.shuffle(valid)

    chosen = []
    sender_counts = Counter()
    for q in valid:
        s = q["sender"]
        if sender_counts[s] >= 2:
            continue
        chosen.append(q)
        sender_counts[s] += 1
        if len(chosen) >= size:
            break

    if len(chosen) < size:
        for q in valid:
            if q not in chosen:
                chosen.append(q)
                if len(chosen) >= size:
                    break

    quiz = []
    for q in chosen:
        sender = q["sender"]
        others = [s for s in unique_active if s != sender]
        rnd.shuffle(others)
        opts = others[: options - 1] + [sender]
        rnd.shuffle(opts)
        quiz.append(
            {
                "text": q["text"],
                "time": q.get("time", ""),
                "date": q.get("date_short") or q.get("date", ""),
                "options": opts,
                "answer": opts.index(sender),
            }
        )
    return quiz


# ====================== WORDLE: СЛОВО ДНЯ ======================

DATA_DIR = Path(__file__).parent / "data"
WORDS_DIR = DATA_DIR / "words"
UK_WORDS_FILE = WORDS_DIR / "uk_words.txt"

WORDLE_LEN = int(os.getenv("WORDLE_LEN", "5"))
WORDLE_STRICT = (
    os.getenv("WORDLE_STRICT", "0").strip() == "1"
)  # 1 = приймати лише слова з чату (без загального словника)

UA_LOWER = UA_LETTERS.lower()
TOKEN_RE = re.compile(r"[а-яіїєґёыэъ'ʼ’]+", re.I)

# Службові слова, які не годяться у «слово дня»
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


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _days(end: Date, n=7) -> list[Date]:
    return [end - timedelta(days=i) for i in range(n - 1, -1, -1)]


def _messages(d: Date) -> list[dict]:
    raw = _load_json(DATA_DIR / f"{d.isoformat()}.json")
    if not raw:
        return []
    return [m for m in raw.get("messages", []) if not m.get("forwarded")]


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
        w = (_load_json(f) or {}).get("word")
        if w:
            used.add(w)
    return used


def cached_word(day: str) -> dict | None:
    """Слово цього дня з кешу, без звернень до моделі."""
    cache = WORDS_DIR / f"{day}.json"
    return _load_json(cache) if cache.exists() else None


def word_of_day(day: str, ask_json, save: bool = True) -> dict | None:
    """Одне слово на день, обране з переписки цього дня (якщо повідомлень мало — з попередніх двох).
    Зберігається в data/words/РРРР-ММ-ДД.json, тож повторний запуск дає ту саму гру.
    Слова, що вже були, не повторюються."""
    d = Date.fromisoformat(day)
    cache = WORDS_DIR / f"{day}.json"
    if cache.exists():
        return _load_json(cache)

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
