"""Етап 2: генерація змісту газети з вивантаженого чату через хмарну модель Ollama.

Вхід:  data/YYYY-MM-DD.json            (результат export.py)
Вихід: data/YYYY-MM-DD.newspaper.json  (зміст газети + статистика, без верстки)

Запуск:
    python generate.py              -> сьогоднішня доба
    python generate.py 2026-10-03   -> конкретна дата
"""
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

import games
import weekly

load_dotenv()
TZ = ZoneInfo(os.getenv("TZ_NAME", "Europe/Kyiv"))
DATA_DIR = Path(__file__).parent / "data"

# Підключення напряму до хмари Ollama за API-ключем (локальний застосунок Ollama не потрібен).
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "https://ollama.com").rstrip("/")
MODEL = os.getenv("OLLAMA_MODEL", "gemma4:31b")  # у режимі API — без суфікса -cloud
NEWSPAPER_NAME = os.getenv("NEWSPAPER_NAME", "Вісник Чату")
CHUNK_CHARS = int(os.getenv("CHUNK_CHARS", "150000"))  # довші дні діляться на шматки
TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "900"))      # секунд на один запит

# Переслані пости з пабліків: показуємо моделі лише початок як контекст для обговорення
FWD_PREVIEW_CHARS = int(os.getenv("FWD_PREVIEW_CHARS", "200"))  # скільки символів посту показати
FWD_WINDOW_MIN = int(os.getenv("FWD_WINDOW_MIN", "15"))         # хвилин після посту, що вважаються реакцією
FWD_MIN_DISCUSSION = int(os.getenv("FWD_MIN_DISCUSSION", "4"))  # мінімум реплік, щоб тема йшла в газету

# Ігри
QUIZ_SIZE = int(os.getenv("QUIZ_SIZE", "6"))            # скільки питань в «Угадай цитату»
CROSSWORD_WORDS = int(os.getenv("CROSSWORD_WORDS", "14"))  # скільки слів просити для кросворду


# ---------- схема відповіді моделі ----------

ARTICLE = {
    "type": "object",
    "properties": {
        "rubric": {"type": "string"},
        "title": {"type": "string"},
        "body": {"type": "string"},
        "illustration_message_id": {"type": "integer"},
    },
    "required": ["rubric", "title", "body", "illustration_message_id"],
}

SCHEMA = {
    "type": "object",
    "properties": {
        "tagline": {"type": "string"},
        "headline": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "subtitle": {"type": "string"},
                "body": {"type": "string"},
                "illustration_message_id": {"type": "integer"},
            },
            "required": ["title", "subtitle", "body", "illustration_message_id"],
        },
        "articles": {"type": "array", "items": ARTICLE},
        "quotes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"message_id": {"type": "integer"}, "comment": {"type": "string"}},
                "required": ["message_id", "comment"],
            },
        },
        "short_news": {"type": "array", "items": {"type": "string"}},
        "hero_of_day": {
            "type": "object",
            "properties": {
                "sender": {"type": "string"},
                "title": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["sender", "title", "reason"],
        },
        "jokes": {"type": "array", "items": {"type": "string"}},
        "crossword": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"answer": {"type": "string"}, "clue": {"type": "string"}},
                "required": ["answer", "clue"],
            },
        },
        "quiz_message_ids": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["tagline", "headline", "articles", "quotes", "short_news", "hero_of_day", "jokes",
                 "crossword", "quiz_message_ids"],
}


# ---------- промпти ----------

SYSTEM_PROMPT = """Ти — головний редактор щоденної жартівливої газети «{name}» для дружнього групового чату.
Ти отримуєш переписку за {date} у форматі:
[id] ГГ:ХХ Ім'я ↪id_повідомлення_на_яке_відповідь: текст
Мітки [фото], [стікер 😂], [gif], [відео], [голосове] позначають медіа: ти їх не бачиш, лише знаєш, що вони були.
Рядки «⤷ ПЕРЕСЛАНО з «Джерело»» — це новини й пости з пабліків, які хтось переслав у чат. Після них у дужках
вказано розмір обговорення в чаті.

Переслані пости:
- Сам пост НЕ є новиною газети: не переказуй його і не пиши статтю про саму новину.
- Пиши лише про те, як чат ОБГОВОРЮВАВ цей пост: реакції, суперечки, жарти, хто що сказав. Новину згадуй одним реченням як привід.
- Якщо обговорення менше {fwd_min} реплік або воно нецікаве, повністю ігноруй цей пост.
- Ніколи не бери переслані пости в quotes та illustration_message_id.

Правила:
- Пиши українською, живо, з гумором, у стилі газети чи таблоїда. Дружні підколки — так; образи, насмішки над зовнішністю, здоров'ям чи особистими бідами — ні.
- Не вигадуй подій і реплік, яких не було в чаті. Художньо перебільшувати можна, але факти беруться тільки з переписки.
- headline — головна новина дня: найобговорюваніша або найсмішніша тема. body 150–300 слів.
- articles — 3–6 статей на інші теми дня, кожна 80–200 слів, з рубрикою за змістом (наприклад: «Скандали», «Культура», «Спорт», «Кулінарія», «Техно», «Плітки»).
- illustration_message_id — id повідомлення з [фото], [gif] або [стікер], яке пасує до статті; 0, якщо нічого не пасує. Бери лише id з переписки, у яких справді є медіа, і не повторюй одну ілюстрацію двічі.
- quotes — 3–5 найяскравіших реплік дня: вкажи лише message_id (текст підставиться автоматично) і короткий редакторський коментар.
- short_news — 3–6 коротких новин, кожна одним реченням.
- hero_of_day — учасник дня: ім'я точно як у переписці, жартівливе звання і пояснення за що.
- crossword — {cw} слів для кросворду за подіями дня: answer — ОДНЕ слово українськими літерами, 3–12 літер,
  без пробілів, дефісів і апострофів (можна імена учасників, назви ігор, предмети, явища з чату);
  clue — дотепна підказка, що відсилає до подій дня і НЕ містить саме слово. Чим більше спільних літер між словами, тим краще.
- quiz_message_ids — {quiz} id повідомлень для гри «Угадай, хто це сказав»: смішні або дуже характерні репліки
  (довжиною від 20 символів), за якими можна вгадати автора. Не беріть репліки з quotes, переслані пости,
  медіа та повідомлення, де автор називає себе. Бажано від різних людей.
- jokes — 5–8 коротких оригінальних анекдотів (1–3 речення кожен) за мотивами тем і подій дня. Без образ учасників, грубих слів і переказу реальних реплік.
- tagline — підзаголовок випуску, одне речення.
Відповідай ЛИШЕ одним JSON-об'єктом, без пояснень і без ```. Структура СУВОРО така
(headline, hero_of_day — об'єкти; articles, quotes, short_news — масиви):
{
  "tagline": "підзаголовок випуску",
  "headline": {"title": "заголовок", "subtitle": "підзаголовок", "body": "текст", "illustration_message_id": 0},
  "articles": [
    {"rubric": "Скандали", "title": "заголовок", "body": "текст", "illustration_message_id": 0}
  ],
  "quotes": [{"message_id": 123, "comment": "коментар редакції"}],
  "short_news": ["коротка новина"],
  "hero_of_day": {"sender": "Ім'я", "title": "звання", "reason": "за що"},
  "jokes": ["анекдот 1", "анекдот 2"],
  "crossword": [{"answer": "ДЕДЛОК", "clue": "Гра, через яку чат сварився весь вечір"}],
  "quiz_message_ids": [123, 456]
}"""

CHUNK_PROMPT = """Це фрагмент переписки дружнього чату. Стисло (до 400 слів) опиши українською:
теми розмов, ключові події, суперечки, смішні моменти і хто що казав.
ОБОВ'ЯЗКОВО зберігай у квадратних дужках id ключових повідомлень, найяскравіших реплік
і повідомлень з медіа ([фото], [gif], [стікер]), щоб редактор міг на них послатися, наприклад: «Олег [1234] заявив...».
Переслані пости з пабліків (⤷ ПЕРЕСЛАНО) не переказуй — лише одним реченням згадай тему і детально опиши, як чат на неї відреагував.
Пости без помітного обговорення пропускай."""


# ---------- допоміжне ----------

def minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def discussions(msgs: list[dict]) -> dict[int, dict]:
    """Для кожного пересланого посту рахує реакцію чату: відповіді на нього (усім ланцюжком)
    плюс повідомлення інших учасників протягом FWD_WINDOW_MIN хвилин, до наступного пересланого посту."""
    children: dict[int, list[int]] = {}
    for m in msgs:
        if m.get("reply_to"):
            children.setdefault(m["reply_to"], []).append(m["id"])
    by_id = {m["id"]: m for m in msgs}
    result = {}
    for i, f in enumerate(msgs):
        if not f.get("forwarded"):
            continue
        ids, stack = set(), list(children.get(f["id"], []))
        while stack:  # уся гілка відповідей
            x = stack.pop()
            if x not in ids:
                ids.add(x)
                stack.extend(children.get(x, []))
        t0 = minutes(f["time"])
        for m in msgs[i + 1:]:
            if m.get("forwarded") or minutes(m["time"]) - t0 > FWD_WINDOW_MIN:
                break
            if not m.get("reply_to") or m["reply_to"] in ids or m["reply_to"] == f["id"]:
                ids.add(m["id"])
        ids = {x for x in ids if x in by_id and not by_id[x].get("forwarded")}
        result[f["id"]] = {"messages": len(ids), "participants": len({by_id[x]["sender"] for x in ids})}
    return result


def fmt_line(m: dict, disc: dict | None = None) -> str:
    reply = f" ↪{m['reply_to']}" if m.get("reply_to") else ""
    text = m["text"].replace("\n", " ")
    if m.get("forwarded"):
        if len(text) > FWD_PREVIEW_CHARS:
            text = text[:FWD_PREVIEW_CHARS].rstrip() + "…"
        d = (disc or {}).get(m["id"], {"messages": 0, "participants": 0})
        return (f"[{m['id']}] {m['time']} {m['sender']} ⤷ ПЕРЕСЛАНО з «{m.get('fwd_source') or 'паблику'}»: {text} "
                f"(обговорення: {d['messages']} реплік, {d['participants']} учасників)")
    return f"[{m['id']}] {m['time']} {m['sender']}{reply}: {text}"


def compute_stats(data: dict) -> dict:
    """Статистику рахуємо в Python — моделі в підрахунках помиляються."""
    all_msgs, media = data["messages"], data["media"]
    msgs = [m for m in all_msgs if not m.get("forwarded")]  # переслане не рахуємо
    by_id = {m["id"]: m for m in msgs}
    by_sender = Counter(m["sender"] for m in msgs)
    by_hour = Counter(int(m["time"][:2]) for m in msgs)
    with_media = [m for m in msgs if m.get("media_id") in media]
    kinds = Counter(media[m["media_id"]]["kind"] for m in with_media)
    stickers = Counter(m["media_id"] for m in with_media if "sticker" in media[m["media_id"]]["kind"])
    replied = Counter(m["reply_to"] for m in msgs if m.get("reply_to") in by_id)

    return {
        "total_messages": len(msgs),
        "forwarded": len(all_msgs) - len(msgs),
        "participants": len(by_sender),
        "top_senders": [{"sender": s, "count": c} for s, c in by_sender.most_common(5)],
        "messages_by_hour": [by_hour.get(h, 0) for h in range(24)],
        "busiest_hour": f"{by_hour.most_common(1)[0][0]:02d}:00" if by_hour else None,
        "media_counts": dict(kinds),
        "top_sticker": (
            {"media_id": stickers.most_common(1)[0][0], "count": stickers.most_common(1)[0][1]}
            if stickers else None
        ),
        "most_replied": [
            {"message_id": i, "replies": n, "sender": by_id[i]["sender"], "text": by_id[i]["text"]}
            for i, n in replied.most_common(3)
        ],
        "first_message": {"time": msgs[0]["time"], "sender": msgs[0]["sender"]} if msgs else None,
        "last_message": {"time": msgs[-1]["time"], "sender": msgs[-1]["sender"]} if msgs else None,
    }


def chunk_lines(lines: list[str], limit: int) -> list[str]:
    chunks, cur, size = [], [], 0
    for line in lines:
        if cur and size + len(line) > limit:
            chunks.append("\n".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks


# ---------- робота з Ollama ----------

def ollama_chat(system: str, user: str, schema: dict | None = None) -> str:
    headers = {"Authorization": f"Bearer {OLLAMA_API_KEY}"}
    payload = {
        "model": MODEL,
        "stream": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": 0.7},
    }
    if schema:
        payload["format"] = schema

    for attempt in range(1, 4):
        try:
            r = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, headers=headers, timeout=TIMEOUT)
            if r.status_code == 401:
                sys.exit("Помилка 401: невірний OLLAMA_API_KEY. Перевір ключ у .env")
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
            return r.json()["message"]["content"]
        except (requests.RequestException, RuntimeError, KeyError) as e:
            print(f"  ! запит до моделі, спроба {attempt}/3: {e}")
            if attempt == 3:
                raise
            time.sleep(15 * attempt)


def ollama_json(system: str, user: str, schema: dict, post=None) -> dict:
    """post — функція перевірки/нормалізації відповіді; за замовчуванням — для газети."""
    post = post or normalize
    for attempt in range(1, 4):
        raw = ollama_chat(system, user, schema).strip()
        # Сира відповідь зберігається завжди — зручно для діагностики
        DATA_DIR.mkdir(exist_ok=True)
        (DATA_DIR / "last_model_response.txt").write_text(raw, encoding="utf-8")
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return post(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  ! модель повернула некоректну відповідь, спроба {attempt}/3: {e}")
    raise RuntimeError("Модель тричі повернула некоректну відповідь — див. data/last_model_response.txt")


def as_int(v) -> int:
    try:
        return int(str(v).strip().strip("[]#"))
    except (TypeError, ValueError):
        return 0


def as_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        return "\n\n".join(as_text(x) for x in v if x)
    if isinstance(v, dict):
        return " ".join(as_text(x) for x in v.values() if x)
    return str(v)


def normalize(c) -> dict:
    """Приводить відповідь моделі до очікуваної структури, навіть якщо модель
    частково проігнорувала схему (наприклад, повернула headline рядком)."""
    if not isinstance(c, dict):
        raise ValueError("відповідь не є JSON-об'єктом")

    h = c.get("headline")
    if not isinstance(h, dict):  # модель повернула заголовок рядком
        h = {"title": as_text(h), "subtitle": c.get("subtitle", ""), "body": c.get("body", ""),
             "illustration_message_id": c.get("illustration_message_id", 0)}
    headline = {
        "title": as_text(h.get("title")),
        "subtitle": as_text(h.get("subtitle")),
        "body": as_text(h.get("body") or h.get("text")),
        "illustration_message_id": as_int(h.get("illustration_message_id")),
    }
    if not headline["title"]:
        raise ValueError("немає заголовка головної новини")

    articles = []
    for a in c.get("articles") or []:
        if isinstance(a, str):
            a = {"title": a}
        if not isinstance(a, dict):
            continue
        art = {
            "rubric": as_text(a.get("rubric")) or "Новини",
            "title": as_text(a.get("title")),
            "body": as_text(a.get("body") or a.get("text")),
            "illustration_message_id": as_int(a.get("illustration_message_id")),
        }
        if art["title"] or art["body"]:
            articles.append(art)

    quotes = []
    for q in c.get("quotes") or []:
        if isinstance(q, dict):
            quotes.append({"message_id": as_int(q.get("message_id")), "comment": as_text(q.get("comment"))})
        else:
            quotes.append({"message_id": as_int(q), "comment": ""})

    news = c.get("short_news") or []
    if isinstance(news, str):
        news = [news]
    short_news = [as_text(n) for n in news if as_text(n)]

    hero = c.get("hero_of_day")
    if not isinstance(hero, dict):
        hero = {"sender": "", "title": as_text(hero), "reason": ""}
    hero_of_day = {k: as_text(hero.get(k)) for k in ("sender", "title", "reason")}

    jokes = c.get("jokes") or []
    if isinstance(jokes, str):
        jokes = [j for j in jokes.split("\n") if j.strip()]
    jokes = [as_text(j) for j in jokes if as_text(j)]

    crossword = [x for x in (c.get("crossword") or []) if isinstance(x, dict)]
    quiz_ids = [as_int(x) for x in (c.get("quiz_message_ids") or []) if as_int(x)]

    return {
        "tagline": as_text(c.get("tagline")),
        "headline": headline,
        "articles": articles,
        "quotes": quotes,
        "short_news": short_news,
        "hero_of_day": hero_of_day,
        "jokes": jokes,
        "crossword_raw": crossword,
        "quiz_message_ids": quiz_ids,
    }


# ---------- перевірка відповіді ----------

def resolve(content: dict, data: dict) -> dict:
    """Перетворює id повідомлень на media_id і справжні цитати, відкидає вигадані id."""
    by_id = {m["id"]: m for m in data["messages"]}
    media = data["media"]
    used = set()

    def media_of(msg_id):
        m = by_id.get(msg_id)
        mid = m.get("media_id") if m and not m.get("forwarded") else None
        if mid in media and mid not in used:
            used.add(mid)
            return mid
        return None

    h = content["headline"]
    h["media_id"] = media_of(h.pop("illustration_message_id", 0))
    for a in content["articles"]:
        a["media_id"] = media_of(a.pop("illustration_message_id", 0))

    quotes = []
    for q in content["quotes"]:
        m = by_id.get(q["message_id"])
        if m and not m.get("forwarded") and m["text"] and not m["text"].startswith("["):
            quotes.append({**q, "sender": m["sender"], "time": m["time"], "text": m["text"]})
    content["quotes"] = quotes
    return content


# ---------- основне ----------

def main():
    if not OLLAMA_API_KEY:
        sys.exit("Не задано OLLAMA_API_KEY у файлі .env — див. інструкцію з підключення API")
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now(TZ).strftime("%Y-%m-%d")
    src = DATA_DIR / f"{date}.json"
    if not src.exists():
        sys.exit(f"Немає файлу {src} — спершу запусти export.py {date}")

    data = json.loads(src.read_text(encoding="utf-8"))
    msgs = data["messages"]
    stats = compute_stats(data)
    out = DATA_DIR / f"{date}.newspaper.json"

    result = {
        "date": date,
        "newspaper_name": NEWSPAPER_NAME,
        "model": MODEL,
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "stats": stats,
        "content": None,
    }

    if not msgs:
        print("За цю добу в чаті не було повідомлень — газета буде порожньою.")
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    disc = discussions(msgs)
    lines = [fmt_line(m, disc) for m in msgs]
    hot = sum(1 for d in disc.values() if d["messages"] >= FWD_MIN_DISCUSSION)
    if disc:
        print(f"Пересланих постів: {len(disc)}, з помітним обговоренням: {hot}")
    transcript = "\n".join(lines)
    print(f"Повідомлень: {len(msgs)}, символів: {len(transcript)}, модель: {MODEL} @ {OLLAMA_HOST}")

    # Довгий день: спершу підсумки по шматках, потім газета з підсумків
    if len(transcript) > CHUNK_CHARS:
        chunks = chunk_lines(lines, CHUNK_CHARS)
        print(f"Переписка довга — ділю на {len(chunks)} частин...")
        summaries = []
        for i, chunk in enumerate(chunks, 1):
            print(f"  підсумок частини {i}/{len(chunks)}...")
            summaries.append(f"--- Частина {i} ---\n" + ollama_chat(CHUNK_PROMPT, chunk))
        material = "Підсумки переписки по частинах (id повідомлень у квадратних дужках):\n\n" + "\n\n".join(summaries)
    else:
        material = transcript

    top = ", ".join(f"{s['sender']} ({s['count']})" for s in stats["top_senders"])
    user_msg = (
        f"Статистика дня: {stats['total_messages']} повідомлень, найактивніші: {top}, "
        f"пікова година: {stats['busiest_hour']}.\n\nПереписка:\n{material}"
    )
    system = (SYSTEM_PROMPT.replace("{name}", NEWSPAPER_NAME).replace("{date}", date)
              .replace("{fwd_min}", str(FWD_MIN_DISCUSSION))
              .replace("{cw}", str(CROSSWORD_WORDS)).replace("{quiz}", str(QUIZ_SIZE + 2)))

    print("Генерую газету...")
    t0 = time.time()
    content = ollama_json(system, user_msg, SCHEMA)
    result["content"] = resolve(content, data)
    c = result["content"]

    # ---------- ігри ----------
    words = games.clean_crossword_words(c.pop("crossword_raw", []))
    c["crossword"] = games.build_crossword(words, seed=date)
    quoted = {q["message_id"] for q in c["quotes"]}
    c["quiz"] = games.build_quiz(c.pop("quiz_message_ids", []), data, quoted, seed=date, size=QUIZ_SIZE)
    print(f"Кросворд: {len(c['crossword']['entries']) if c['crossword'] else 0} слів із {len(words)}, "
          f"«Угадай цитату»: {len(c['quiz'])} питань")

    # ---------- тиждень ----------
    try:
        if weekly.is_weekly_day(date):
            print("Готую «Головне за тиждень»...")
            result["weekly"] = weekly.build_weekly(date, result, ollama_json, NEWSPAPER_NAME)
        result["word"] = weekly.word_of_week(date, ollama_json)
        if result.get("word"):
            print(f"Слово тижня ({result['word']['week']}): {len(result['word']['word'])} літер")
    except Exception as e:  # тижневі блоки не повинні ламати щоденний випуск
        print(f"  ! тижневі блоки пропущено: {e}")

    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nГотово за {time.time() - t0:.0f} с -> {out}")
    print(f"Головна: {c['headline']['title']}")
    for a in c["articles"]:
        print(f"  [{a['rubric']}] {a['title']}{'  🖼' if a['media_id'] else ''}")
    print(f"Цитат: {len(c['quotes'])}, коротких новин: {len(c['short_news'])}, "
          f"герой дня: {c['hero_of_day']['sender']}, анекдотів: {len(c['jokes'])}")


if __name__ == "__main__":
    main()
