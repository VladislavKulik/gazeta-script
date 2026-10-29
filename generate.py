"""Етап 2: генерація змісту газети з вивантаженого чату через хмарну модель Ollama.

Вхід:  data/YYYY-MM-DD.json            (результат export.py)
Вихід: data/YYYY-MM-DD.newspaper.json  (зміст газети + статистика, без верстки)

Запуск:
    python generate.py              -> сьогоднішня доба
    python generate.py 2026-10-03   -> конкретна дата
"""

import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image
import requests
from dotenv import load_dotenv

import games
import weekly

FFMPEG = shutil.which("ffmpeg") or (
    Path(__file__).parent / "ffmpeg" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
)
if isinstance(FFMPEG, Path) and not FFMPEG.exists():
    FFMPEG = None

load_dotenv()
TZ = ZoneInfo(os.getenv("TZ_NAME", "Europe/Kyiv"))
DATA_DIR = Path(__file__).parent / "data"

# Підключення напряму до хмари Ollama за API-ключем (локальний застосунок Ollama не потрібен).
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "https://ollama.com").rstrip("/")
MODEL = os.getenv("OLLAMA_MODEL", "gemma4:31b")  # у режимі API — без суфікса -cloud
NEWSPAPER_NAME = os.getenv("NEWSPAPER_NAME", "Вісник Чату")
CHUNK_CHARS = int(os.getenv("CHUNK_CHARS", "150000"))  # довші дні діляться на шматки
TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "900"))  # секунд на один запит

# Переслані пости з пабліків: показуємо моделі лише початок як контекст для обговорення
FWD_PREVIEW_CHARS = int(
    os.getenv("FWD_PREVIEW_CHARS", "200")
)  # скільки символів посту показати
FWD_WINDOW_MIN = int(
    os.getenv("FWD_WINDOW_MIN", "15")
)  # хвилин після посту, що вважаються реакцією
FWD_MIN_DISCUSSION = int(
    os.getenv("FWD_MIN_DISCUSSION", "4")
)  # мінімум реплік, щоб тема йшла в газету

# Ігри
QUIZ_SIZE = int(os.getenv("QUIZ_SIZE", "6"))  # скільки питань в «Угадай цитату»
CROSSWORD_WORDS = int(
    os.getenv("CROSSWORD_WORDS", "14")
)  # скільки слів просити для кросворду


# ---------- схема відповіді моделі ----------

ARTICLE = {
    "type": "object",
    "properties": {
        "rubric": {"type": "string"},
        "title": {"type": "string"},
        "body": {"type": "string"},
        "illustration_message_ids": {
            "type": "array",
            "items": {"type": "integer"},
        },
    },
    "required": ["rubric", "title", "body", "illustration_message_ids"],
}


def make_schema(is_games: bool = True) -> dict:
    properties = {
        "tagline": {"type": "string"},
        "headline": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "subtitle": {"type": "string"},
                "body": {"type": "string"},
                "illustration_message_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
            },
            "required": ["title", "subtitle", "body", "illustration_message_ids"],
        },
        "articles": {"type": "array", "items": ARTICLE},
        "quotes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "integer"},
                    "comment": {"type": "string"},
                },
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
    }
    required = [
        "tagline",
        "headline",
        "articles",
        "quotes",
        "short_news",
        "hero_of_day",
        "jokes",
    ]
    if is_games:
        properties["crossword"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                    "clue": {"type": "string"},
                },
                "required": ["answer", "clue"],
            },
        }
        properties["quiz_message_ids"] = {"type": "array", "items": {"type": "integer"}}
        required.extend(["crossword", "quiz_message_ids"])

    return {"type": "object", "properties": properties, "required": required}


# ---------- промпти ----------


def make_system_prompt(name: str, date: str, is_games: bool = True) -> str:
    rules = [
        "- Мова та тон: пиши українською — агресивно, зухвало, дотепно й без цензури, у стилі цинічного бульварного таблоїда. Жодних реверансів, ввічливості чи спроб нікого не образити. Жорсткий роаст (просмажка), сарказм і глузування з тупих тейків — так; але бий суворо по поведінці, словах і діях у чаті.",
        "- Мова та алфавіт: пиши виключно українською мовою. Допускається використання латиниці лише для загальновідомих оригінальних назв (ігри, нікнейми, бренди на кшталт Deadlock, Steam, YouTube, Discord). СУВОРО ЗАБОРОНЕНО використовувати літери інших алфавітів (арабського, івриту, китайського тощо) або змішувати кирилицю з чужими символами (наприклад, жодних «Хеيز» замість «Хейз»).",
        "- Нуль дипломатії та «обох сторін»: ніколи не прирівнюй маячню до фактів. Забудь кліше на кшталт «думки розділилися» чи «все неоднозначно». Прямо називай переможців, лузерів і клоунів дня. Якщо хтось гучно сів у калюжу — винось це в заголовок.",
        "- Імена, факти та реальні мотиви: використовуй активний стан і називай конкретних винуватців срачів, ниття чи вкидів. Оцінюй історії, плани та суперечки учасників за реальними наслідками (злиті дискусії, фінансові факапи, ганьба) і справжніми мотивами (понти, копіум, заздрість, синдром вахтера), повністю ігноруючи їхні дешеві відмазки.",
        "- Прямий вердикт: оцінюй ідеї та аргументи учасників безжальною логікою, прямо маркуючи їх як рідкісну базу, чистий копіум, брейнрот або тотальне фіаско.",
        "- Жодних галюцинацій: не вигадуй подій, драми і реплік, яких не було в чаті. Сатирично перебільшувати й докручувати абсурд можна, але факти беруться виключно з логів.",
        "- Жодних id у тексті: СУВОРО ЗАБОРОНЕНО вставляти у текст статей (body), заголовків чи коротких новин (short_news) номери повідомлень у квадратних дужках типу [220259] чи [1234]! Номери повідомлень потрібні виключно для полів illustration_message_ids, quiz_message_ids та quotes. Усередині тексту цитати оформлюються виключно словами й лапками (наприклад: Назар заявив: «я рік не стригся»), без жодних дужок із цифрами.",
        "- headline — головний заміс дня: найгучніший срач, найтупіший факап або найсмішніша тема. body 400–700 слів. Обов'язково цитуй учасників дослівно (вставляй прямі цитати з переписки в лапках із зазначенням автора). Детально описуй хронологію, причини і наслідки, хто що робив і як реагували інші.",
        "- articles — 3–6 розгромних статей на інші теми дня, кожна 200–450 слів, з їдкою рубрикою за змістом (наприклад: «Скандали», «Крінж дня», «Диванна аналітика», «Кулінарні злочини», «Техно-срач», «Плітки»). Кожна стаття ОБОВ'ЯЗКОВО має містити 2–4 прямі цитати учасників (дослівно з переписки, в лапках). Описуй контекст і реакції детально. Жодних номерів [id] у тексті!",
        "- illustration_message_ids — масив id повідомлень з [фото], [gif] або [стікер], які пасують до статті. Можна 1–3 фото на статтю. Порожній масив [], якщо нічого не пасує. Бери лише id з переписки, у яких справді є медіа, і не повторюй одну ілюстрацію двічі. Якщо фото має опис контексту — враховуй його при виборі.",
        "- quotes — 3–5 найепічніших або найабсурдніших реплік дня: вкажи лише message_id (текст підставиться автоматично) і короткий, уїдливий коментар-панчлайн від редакції.",
        "- short_news — 3–6 коротких новин одним реченням: максимально сухо, панчево й саркастично. Жодних медіа, жодних номерів [id].",
        "- hero_of_day — головний персонаж (або клоун) дня: ім'я точно як у переписці, саркастичне звання і жорстке, але смішне пояснення за які заслуги чи гріхи.",
    ]
    if is_games:
        rules.extend(
            [
                f"- crossword — {CROSSWORD_WORDS} слів для кросворду за подіями дня: answer — ОДНЕ слово українськими літерами, 3–12 літер,\n"
                "  без пробілів, дефісів і апострофів (можна імена учасників, назви ігор, предмети, явища з чату);\n"
                "  clue — дотепна й єхидна підказка, що відсилає до подій чи факапів дня і НЕ містить саме слово. Чим більше спільних літер між словами, тим краще.",
                f"- quiz_message_ids — {QUIZ_SIZE + 2} id повідомлень для гри «Угадай, хто це ляпнув»: смішні, компрометуючі або дуже характерні репліки\n"
                "  (довжиною від 20 символів), за якими можна вгадати автора. Не беріть репліки з quotes, переслані пости,\n"
                "  медіа та повідомлення, де автор називає себе. Бажано від різних людей.",
            ]
        )
    rules.extend(
        [
            "- jokes — 5–8 коротких оригінальних анекдотів (1–3 речення кожен) з чорним гумором та гострою сатирою за мотивами тем і подій дня. Без прямого переказу реальних реплік.",
            "- tagline — зухвалий підзаголовок випуску, одне влучне речення.",
        ]
    )

    rules_str = "\n".join(rules)
    games_json = ""
    if is_games:
        games_json = """,
  "crossword": [{"answer": "ДЕДЛОК", "clue": "Гра, через яку чат пересварився і забув про роботу весь вечір"}],
  "quiz_message_ids": [123, 456]"""

    return f"""Ти — безжальний, цинічний, гострий на язик і абсолютно некомпліментарний головний редактор жовтої газети «{name}», який препарує щоденні логи групового чату. Твій пріоритет — емпіричні факти з переписки, причинно-наслідкові зв'язки, жорстка просмажка (роаст) і викриття чужої маячні, а не дружня атмосфера чи чиєсь крихке его. Стався до всіх учасників чату зі здоровим скепсисом і ніколи не підтакуй хибним чи тупим тейкам.

Ти отримуєш переписку за {date} у форматі:
[id] ГГ:ХХ Ім'я ↪️id_повідомлення_на_яке_відповідь: текст
Мітки [фото], [стікер 😂], [gif], [відео], [голосове] позначають медіа: ти їх не бачиш, лише знаєш, що вони були.
Рядки «⤷ ПЕРЕСЛАНО з «Джерело»» — це новини й пости з пабліків, які хтось притягнув у чат. Після них у дужках
вказано розмір обговорення в чаті.

Переслані пости:
- Сам пост НЕ є новиною газети: не переказуй його і не пиши статтю про саму новину.
- Пиши лише про те, як чат ОБГОВОРЮВАВ цей пост: диванна експертиза, істерики, суперечки, хто зганьбився в коментарях. Новину згадуй одним реченням як привід.
- Якщо обговорення менше {FWD_MIN_DISCUSSION} реплік або воно прісне й нудне, повністю ігноруй цей пост.
- Ніколи не бери переслані пости в quotes та illustration_message_id.

Правила редакції:
{rules_str}
Відповідай ЛИШЕ одним JSON-об'єктом, без пояснень, без привітань і без `. Структура СУВОРО така
(headline, hero_of_day — об'єкти; articles, quotes, short_news — масиви):
{{
  "tagline": "підзаголовок випуску",
  "headline": {{"title": "заголовок", "subtitle": "підзаголовок", "body": "текст 400-700 слів з прямими цитатами", "illustration_message_ids": [123, 456]}},
  "articles": [
    {{"rubric": "Скандали", "title": "заголовок", "body": "текст 200-450 слів з прямими цитатами", "illustration_message_ids": [789]}}
  ],
  "quotes": [{{"message_id": 123, "comment": "коментар редакції"}}],
  "short_news": ["коротка новина"],
  "hero_of_day": {{"sender": "Ім'я", "title": "звання", "reason": "за що"}},
  "jokes": ["анекдот 1", "анекдот 2"]{games_json}
}}"""


SCHEMA = make_schema(True)
SYSTEM_PROMPT = make_system_prompt("{name}", "{date}", True)

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
    плюс повідомлення інших учасників протягом FWD_WINDOW_MIN хвилин, до наступного пересланого посту.
    """
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
        for m in msgs[i + 1 :]:
            if m.get("forwarded") or minutes(m["time"]) - t0 > FWD_WINDOW_MIN:
                break
            if (
                not m.get("reply_to")
                or m["reply_to"] in ids
                or m["reply_to"] == f["id"]
            ):
                ids.add(m["id"])
        ids = {x for x in ids if x in by_id and not by_id[x].get("forwarded")}
        result[f["id"]] = {
            "messages": len(ids),
            "participants": len({by_id[x]["sender"] for x in ids}),
        }
    return result


def fmt_line(m: dict, disc: dict | None = None, media_desc: dict | None = None) -> str:
    reply = f" ↪{m['reply_to']}" if m.get("reply_to") else ""
    text = m["text"].replace("\n", " ")

    # Вставляємо опис медіа для фото, gif та стікерів
    mid = m.get("media_id")
    if media_desc and mid and mid in media_desc:
        desc = media_desc[mid]
        if "[фото]" in text:
            text = text.replace("[фото]", f"[фото: {desc}]", 1)
        elif "[gif]" in text:
            text = text.replace("[gif]", f"[gif: {desc}]", 1)
        elif "[стікер" in text:
            text = re.sub(r"\[стікер([^\]]*)\]", rf"[стікер\1: {desc}]", text, count=1)
        elif "[відео]" in text:
            text = text.replace("[відео]", f"[відео: {desc}]", 1)

    if m.get("forwarded"):
        if len(text) > FWD_PREVIEW_CHARS:
            text = text[:FWD_PREVIEW_CHARS].rstrip() + "…"
        d = (disc or {}).get(m["id"], {"messages": 0, "participants": 0})
        return (
            f"[{m['id']}] {m['time']} {m['sender']} ⤷ ПЕРЕСЛАНО з «{m.get('fwd_source') or 'паблику'}»: {text} "
            f"(обговорення: {d['messages']} реплік, {d['participants']} учасників)"
        )
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
    stickers = Counter(
        m["media_id"] for m in with_media if "sticker" in media[m["media_id"]]["kind"]
    )
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
            {
                "media_id": stickers.most_common(1)[0][0],
                "count": stickers.most_common(1)[0][1],
            }
            if stickers
            else None
        ),
        "most_replied": [
            {
                "message_id": i,
                "replies": n,
                "sender": by_id[i]["sender"],
                "text": by_id[i]["text"],
            }
            for i, n in replied.most_common(3)
        ],
        "first_message": (
            {"time": msgs[0]["time"], "sender": msgs[0]["sender"]} if msgs else None
        ),
        "last_message": (
            {"time": msgs[-1]["time"], "sender": msgs[-1]["sender"]} if msgs else None
        ),
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


# ---------- розпізнавання контексту медіа (фото, стікери, гіфки) ----------

VISION_BATCH_SIZE = int(os.getenv("VISION_BATCH_SIZE", "5"))
VISION_TIMEOUT = int(os.getenv("VISION_TIMEOUT", "60"))
MEDIA_CACHE_FILE = DATA_DIR / "media_cache.json"

VISION_PROMPT = """Опиши це зображення (фото, мем, стікер або кадр з анімації/гіфки) одним-двома короткими реченнями українською мовою. Що або хто зображено: персонажі, дія, вираз обличчя/емоція, текст на картинці або суть жарту/мему. Будь конкретним і пиши без вступів, лише суть."""


def load_media_cache() -> dict[str, dict]:
    """Завантажує глобальний кеш описів медіа."""
    if MEDIA_CACHE_FILE.exists():
        try:
            return json.loads(MEDIA_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_media_cache(cache: dict[str, dict]):
    """Зберігає глобальний кеш описів медіа."""
    try:
        DATA_DIR.mkdir(exist_ok=True)
        MEDIA_CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        print(f"  ! не вдалося зберегти media_cache.json: {e}")


def extract_image_b64_from_media(media_item: dict) -> str | None:
    """Витягує base64-зображення (JPEG/PNG/WebP) з медіа будь-якого типу:
    - photo: безпосередньо з data URI
    - sticker: статичний WebP безпосередньо з data URI
    - video_sticker / gif: витягує перший кадр через ffmpeg або PIL
    """
    data_uri = media_item.get("data") or ""
    if not data_uri or "," not in data_uri:
        return None

    kind = media_item.get("kind", "")
    header, b64 = data_uri.split(",", 1)

    # 1. Фото та статичні стікери (вже зображення)
    if kind == "photo" or (kind == "sticker" and ("image/" in header or "webp" in header)):
        return b64

    # 2. Анімовані стікери Lottie (application/json) — растру немає
    if kind == "animated_sticker":
        return None

    raw = None
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return None

    # Якщо animated gif (image/gif)
    if "image/gif" in header:
        try:
            im = Image.open(io.BytesIO(raw))
            im.seek(0)
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=80)
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            pass

    # Відео (mp4, webm) — перший кадр через ffmpeg
    if FFMPEG and ("video/" in header or kind in ("gif", "video_sticker")):
        ext = ".webm" if "webm" in header else ".mp4"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                src = os.path.join(tmp, f"input{ext}")
                dst = os.path.join(tmp, "frame.jpg")
                with open(src, "wb") as f:
                    f.write(raw)
                res = subprocess.run(
                    [
                        str(FFMPEG),
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        src,
                        "-frames:v",
                        "1",
                        "-q:v",
                        "2",
                        dst,
                    ],
                    capture_output=True,
                    timeout=20,
                )
                if os.path.exists(dst):
                    with open(dst, "rb") as df:
                        return base64.b64encode(df.read()).decode("ascii")
        except Exception as e:
            print(f"  ! не вдалося витягти кадр для {kind}: {e}")

    return None


def describe_image_b64(b64: str) -> str | None:
    """Відправляє base64-зображення на vision-модель і повертає короткий опис."""
    headers = {"Authorization": f"Bearer {OLLAMA_API_KEY}"}
    payload = {
        "model": MODEL,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": VISION_PROMPT,
                "images": [b64],
            }
        ],
        "options": {"temperature": 0.3},
    }
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json=payload,
            headers=headers,
            timeout=VISION_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return r.json()["message"]["content"].strip()
    except Exception as e:
        print(f"  ! помилка опису медіа: {e}")
        return None


def describe_all_media(
    data: dict, chat_file_path: Path | None = None, skip_api: bool = False
) -> dict[str, str]:
    """Описує фото, стікери та гіфки.
    1. Перевіряє опис у data['media'][mid]['description']
    2. Перевіряє глобальний кеш data/media_cache.json
    3. Якщо skip_api=False — для нових медіа викликає vision-модель
    4. Зберігає нові описи в кеш і записує до data/{date}.json
    Повертає {media_id: опис}.
    """
    media = data.get("media", {})
    msgs = data.get("messages", [])
    cache = load_media_cache()

    candidate_ids = []
    seen = set()
    for m in msgs:
        mid = m.get("media_id")
        if mid and mid not in seen and not m.get("forwarded") and mid in media:
            seen.add(mid)
            candidate_ids.append(mid)

    descriptions = {}
    to_describe = []

    for mid in candidate_ids:
        m = media[mid]
        if m.get("description"):
            descriptions[mid] = m["description"]
        elif mid in cache and cache[mid].get("description"):
            desc = cache[mid]["description"]
            descriptions[mid] = desc
            m["description"] = desc
        else:
            to_describe.append(mid)

    if skip_api or not to_describe:
        if descriptions:
            print(f"Описів медіа з кешу: {len(descriptions)}")
        return descriptions

    print(
        f"Описів у кеші: {len(descriptions)}, нових медіа для розпізнавання: {len(to_describe)}"
    )
    updated = False

    for i, mid in enumerate(to_describe, 1):
        m = media[mid]
        kind = m.get("kind", "media")

        if kind == "animated_sticker":
            emoji = m.get("emoji")
            desc = f"анімований стікер {emoji}" if emoji else "анімований стікер"
            descriptions[mid] = desc
            m["description"] = desc
            cache[mid] = {"kind": kind, "description": desc}
            updated = True
            continue

        b64 = extract_image_b64_from_media(m)
        if not b64:
            continue

        print(f"  [{kind}] {i}/{len(to_describe)}...", end=" ", flush=True)
        desc = describe_image_b64(b64)
        if desc:
            descriptions[mid] = desc
            m["description"] = desc
            cache[mid] = {"kind": kind, "description": desc}
            updated = True
            print(desc[:60] + ("..." if len(desc) > 60 else ""))
        else:
            print("(не вдалося)")

    if updated:
        save_media_cache(cache)
        if chat_file_path and chat_file_path.exists():
            try:
                chat_file_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(f"  ✓ Збережено описи медіа до {chat_file_path.name}")
            except Exception as e:
                print(f"  ! не вдалося оновити {chat_file_path}: {e}")

    return descriptions


# ---------- робота з Ollama ----------


def ollama_chat(system: str, user: str, schema: dict | None = None) -> str:
    headers = {"Authorization": f"Bearer {OLLAMA_API_KEY}"}
    payload = {
        "model": MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": 0.7},
    }
    if schema:
        payload["format"] = schema

    for attempt in range(1, 4):
        try:
            r = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json=payload,
                headers=headers,
                timeout=TIMEOUT,
            )
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
        raw = (
            raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        )
        try:
            return post(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  ! модель повернула некоректну відповідь, спроба {attempt}/3: {e}")
    raise RuntimeError(
        "Модель тричі повернула некоректну відповідь — див. data/last_model_response.txt"
    )


def as_int(v) -> int:
    try:
        return int(str(v).strip().strip("[]#"))
    except (TypeError, ValueError):
        return 0


def as_int_list(v) -> list[int]:
    """Перетворює значення на список int — підтримка як масиву, так і одного числа."""
    if isinstance(v, list):
        return [as_int(x) for x in v if as_int(x)]
    val = as_int(v)
    return [val] if val else []


# ---------- нормалізація, захист від артефактів та слаги ----------

CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ye",
    "ж": "zh", "з": "z", "и": "y", "і": "i", "ї": "yi", "й": "y", "к": "k", "л": "l",
    "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ь": "",
    "ю": "yu", "я": "ya", "ъ": "", "ы": "y", "э": "e",
}

# Поширені арабські літери, що помилково підставляються мультимовними LLM замість кирилиці
ARABIC_TO_CYRILLIC = {
    "\u064A": "й",  # ي -> й
    "\u0649": "и",  # ى -> и
    "\u0632": "з",  # ز -> з
    "\u0648": "в",  # و -> в
    "\u0631": "р",  # ر -> р
    "\u062F": "д",  # د -> д
    "\u0627": "а",  # ا -> а
    "\u0644": "л",  # ل -> л
    "\u0645": "м",  # م -> м
    "\u0646": "н",  # ن -> н
    "\u062A": "т",  # ت -> т
    "\u0628": "б",  # ب -> б
    "\u0633": "с",  # س -> с
    "\u0643": "к",  # ك -> к
    "\u062E": "х",  # خ -> х
}


def sanitize_text(text: str) -> str:
    """Очищає текст від сторонніх писемностей (арабських, східних літер тощо)
    та прибирає згенеровані моделлю номери повідомлень у квадратних дужках типу [220259]."""
    if not text:
        return ""
    # Видаляємо випадкові номери повідомлень у квадратних дужках типу [220294] або [1234]
    text = re.sub(r"\s*\[\d{3,}\]", "", text)

    for ar, cyr in ARABIC_TO_CYRILLIC.items():
        text = text.replace(ar, cyr)

    cleaned = []
    for ch in text:
        code = ord(ch)
        # Latin, digits, common punctuation & symbols
        if code < 0x0250:
            cleaned.append(ch)
        # Cyrillic (0x0400 - 0x052F)
        elif 0x0400 <= code <= 0x052F:
            cleaned.append(ch)
        # General punctuation & quotes (0x2000 - 0x206F, e.g. —, –, «, », …)
        elif 0x2000 <= code <= 0x206F:
            cleaned.append(ch)
        # Currency, math symbols, common arrows (0x2070 - 0x218F)
        elif 0x2070 <= code <= 0x218F:
            cleaned.append(ch)
        # Emojis & misc symbols (>= 0x2600)
        elif code >= 0x2600:
            cleaned.append(ch)
        else:
            # Пропускаємо чужі писемності
            continue

    res = "".join(cleaned)
    return re.sub(r" {2,}", " ", res)


def make_slug(title: str, max_words: int = 6) -> str:
    """Генерує URL-friendly slug для новини з заголовка."""
    text = title.lower()
    trans = "".join(CYR_TO_LAT.get(ch, ch) for ch in text)
    clean = re.sub(r"[^a-z0-9\s-]", "", trans)
    words = clean.split()[:max_words]
    return "-".join(words) or "news"


def extract_lead(body: str, max_chars: int = 180) -> str:
    """Витягує короткий вступний лід/тизер для картки на головній сторінці."""
    if not body:
        return ""
    first_p = body.strip().split("\n")[0].strip()
    if len(first_p) > max_chars:
        trimmed = first_p[:max_chars].rsplit(" ", 1)[0]
        return trimmed.rstrip(".,:;!?") + "…"
    return first_p


def as_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return sanitize_text(v.strip())
    if isinstance(v, list):
        return "\n\n".join(as_text(x) for x in v if x)
    if isinstance(v, dict):
        return " ".join(as_text(x) for x in v.values() if x)
    return sanitize_text(str(v).strip())


def normalize(c) -> dict:
    """Приводить відповідь моделі до очікуваної структури, навіть якщо модель
    частково проігнорувала схему (наприклад, повернула headline рядком)."""
    if not isinstance(c, dict):
        raise ValueError("відповідь не є JSON-об'єктом")

    h = c.get("headline")
    if not isinstance(h, dict):  # модель повернула заголовок рядком
        h = {
            "title": as_text(h),
            "subtitle": c.get("subtitle", ""),
            "body": c.get("body", ""),
            "illustration_message_ids": c.get("illustration_message_ids")
            or c.get("illustration_message_id", []),
        }
    headline = {
        "title": as_text(h.get("title")),
        "subtitle": as_text(h.get("subtitle")),
        "body": as_text(h.get("body") or h.get("text")),
        "illustration_message_ids": as_int_list(
            h.get("illustration_message_ids") or h.get("illustration_message_id")
        ),
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
            "illustration_message_ids": as_int_list(
                a.get("illustration_message_ids") or a.get("illustration_message_id")
            ),
        }
        if art["title"] or art["body"]:
            articles.append(art)

    quotes = []
    for q in c.get("quotes") or []:
        if isinstance(q, dict):
            quotes.append(
                {
                    "message_id": as_int(q.get("message_id")),
                    "comment": as_text(q.get("comment")),
                }
            )
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
    """Перетворює id повідомлень на media_ids і справжні цитати, відкидає вигадані id,
    структурує дані для майбутнього переходу на окремі сторінки новин (slug, id, lead, cover_media_id)."""
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

    def media_ids_of(msg_ids):
        """Повертає список media_id для масиву message_id."""
        result = []
        for msg_id in msg_ids or []:
            mid = media_of(msg_id)
            if mid:
                result.append(mid)
        return result

    h = content["headline"]
    h["id"] = "headline"
    h["slug"] = make_slug(h.get("title", "headline"))
    h["rubric"] = "Головне"
    h["lead"] = h.get("subtitle") or extract_lead(h.get("body", ""))
    h["media_ids"] = media_ids_of(h.pop("illustration_message_ids", []))
    h["cover_media_id"] = h["media_ids"][0] if h["media_ids"] else None

    for idx, a in enumerate(content["articles"], 1):
        a["id"] = f"article-{idx}"
        a["slug"] = make_slug(a.get("title", f"article-{idx}"))
        a["lead"] = extract_lead(a.get("body", ""))
        a["media_ids"] = media_ids_of(a.pop("illustration_message_ids", []))
        a["cover_media_id"] = a["media_ids"][0] if a["media_ids"] else None

    quotes = []
    for q in content["quotes"]:
        m = by_id.get(q["message_id"])
        if m and not m.get("forwarded") and m["text"] and not m["text"].startswith("["):
            quotes.append(
                {**q, "sender": m["sender"], "time": m["time"], "text": m["text"]}
            )
    content["quotes"] = quotes
    return content


# ---------- основне ----------


def main():
    if not OLLAMA_API_KEY:
        sys.exit(
            "Не задано OLLAMA_API_KEY у файлі .env — див. інструкцію з підключення API"
        )
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
        out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return

    disc = discussions(msgs)

    # Розпізнавання контексту медіа (фото, стікери, гіфки) з кешуванням
    skip_vision = "--no-vision" in sys.argv
    media_desc = describe_all_media(data, src, skip_api=skip_vision)

    lines = [fmt_line(m, disc, media_desc) for m in msgs]
    hot = sum(1 for d in disc.values() if d["messages"] >= FWD_MIN_DISCUSSION)
    if disc:
        print(f"Пересланих постів: {len(disc)}, з помітним обговоренням: {hot}")
    transcript = "\n".join(lines)
    print(
        f"Повідомлень: {len(msgs)}, символів: {len(transcript)}, модель: {MODEL} @ {OLLAMA_HOST}"
    )

    # Довгий день: спершу підсумки по шматках, потім газета з підсумків
    if len(transcript) > CHUNK_CHARS:
        chunks = chunk_lines(lines, CHUNK_CHARS)
        print(f"Переписка довга — ділю на {len(chunks)} частин...")
        summaries = []
        for i, chunk in enumerate(chunks, 1):
            print(f"  підсумок частини {i}/{len(chunks)}...")
            summaries.append(
                f"--- Частина {i} ---\n" + ollama_chat(CHUNK_PROMPT, chunk)
            )
        material = (
            "Підсумки переписки по частинах (id повідомлень у квадратних дужках):\n\n"
            + "\n\n".join(summaries)
        )
    else:
        material = transcript

    top = ", ".join(f"{s['sender']} ({s['count']})" for s in stats["top_senders"])
    user_msg = (
        f"Статистика дня: {stats['total_messages']} повідомлень, найактивніші: {top}, "
        f"пікова година: {stats['busiest_hour']}.\n\nПереписка:\n{material}"
    )
    games_day = games.is_games_day(date)
    system = make_system_prompt(NEWSPAPER_NAME, date, games_day)
    schema = make_schema(games_day)

    print("Генерую газету...")
    t0 = time.time()
    content = ollama_json(system, user_msg, schema)
    result["content"] = resolve(content, data)
    c = result["content"]

    # ---------- ігри (лише у неділю) ----------
    if games_day:
        words = games.clean_crossword_words(c.pop("crossword_raw", []))
        c["crossword"] = games.build_crossword(words, seed=date)
        quiz_ids = c.pop("quiz_message_ids", [])
        quoted = {q["message_id"] for q in c["quotes"]}
        w_quotes, w_senders = weekly.collect_weekly_quotes(date, result)
        c["quiz"] = games.build_quiz_from_quotes(
            w_quotes, w_senders, seed=date, size=QUIZ_SIZE
        )
        if not c["quiz"]:
            c["quiz"] = games.build_quiz(
                quiz_ids, data, quoted, seed=date, size=QUIZ_SIZE
            )
        print(
            f"Кросворд: {len(c['crossword']['entries']) if c['crossword'] else 0} слів із {len(words)}, "
            f"«Угадай цитату»: {len(c['quiz'])} питань"
        )
    else:
        c.pop("crossword_raw", None)
        c.pop("quiz_message_ids", None)
        c.pop("crossword", None)
        c.pop("quiz", None)

    # ---------- тиждень ----------
    try:
        if weekly.is_weekly_day(date):
            print("Готую «Головне за тиждень»...")
            result["weekly"] = weekly.build_weekly(
                date, result, ollama_json, NEWSPAPER_NAME
            )
        result["word"] = games.word_of_day(date, ollama_json)
        if result.get("word"):
            print(
                f"Слово дня ({result['word']['id']}): {len(result['word']['word'])} літер"
            )
    except Exception as e:  # тижневі блоки не повинні ламати щоденний випуск
        print(f"  ! тижневі блоки / Wordle пропущено: {e}")

    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nГотово за {time.time() - t0:.0f} с -> {out}")
    print(f"Головна: {c['headline']['title']}")
    for a in c["articles"]:
        img_mark = f"  [медіа: {len(a['media_ids'])}]" if a.get("media_ids") else ""
        print(f"  [{a['rubric']}] {a['title']}{img_mark}")
    print(
        f"Цитат: {len(c['quotes'])}, коротких новин: {len(c['short_news'])}, "
        f"герой дня: {c['hero_of_day']['sender']}, анекдотів: {len(c['jokes'])}"
    )


if __name__ == "__main__":
    main()
