"""Ігри газети: кросворд і «Угадай цитату».

Модель лише пропонує матеріал (слова з підказками, id смішних повідомлень),
а все, що має бути точним — розкладка кросворду, варіанти відповідей — рахується тут.
"""

import base64
import json
import os
import random
import re
from datetime import date as Date

# У які дні виходять кросворд і «Вгадай, хто це сказав»: 1=пн ... 7=нд, через кому, або "all"
GAMES_DAYS = os.getenv("GAMES_DAYS", "7").strip().lower()

UA_LETTERS = "АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ"
WORD_RE = re.compile(f"^[{UA_LETTERS}]+$")


def is_games_day(day: str) -> bool:
    """Кросворд і вікторина — лише у вказані дні (за замовчуванням неділя).
    «Слово тижня» не залежить від цього: воно у кожному випуску."""
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
