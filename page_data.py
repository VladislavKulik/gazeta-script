"""Дані для шаблону газети, які раніше рахувалися всередині Jinja і JS.

1. build_news()          — списки новин дня й тижня: slug (унікальні, без зарезервованих), обкладинки, «близнюк» тижневої
                           новини, що збігається з новиною дня, класи плиток «Головного» і прапорець «обкладинка вже у файлі».
2. build_day_stats()     — усе для вікна «Цифри дня → Детально»: числа, відсотки, підписи, рядки спостережень.
3. build_week_stats()    — те саме для «Цифри тижня → Детально».

Шаблон лише розкладає готове по розмітці; жодних обчислень, множини чи форматування чисел у Jinja/JS немає.
Тести: tests/test_page_data.py (python -m unittest discover tests).
"""

from __future__ import annotations

from datetime import date as Date

# slug — це id шаблону сторінки (tpl-<slug>) і адреса переходу (#<slug>), тож ці назви зайняті самим газетним каркасом
RESERVED_SLUGS = frozenset({"main", "wordle", "tetris", "quiz", "crossword"})

WEEKDAYS_FULL = ["понеділок", "вівторок", "середа", "четвер", "п’ятниця", "субота", "неділя"]
MONTHS_GEN = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]


# ───────────────────────────── дрібні утиліти ─────────────────────────────


def plural(n: int, one: str, few: str, many: str) -> str:
    """Українська множина: 1 стікер, 2 стікери, 5 стікерів."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _round(x: float) -> int:
    """Округлення «як у JS» (.5 — вгору), а не банківське."""
    return int(x + 0.5)


def pct(v: float, total: float) -> str:
    """Відсоток з одним знаком і комою: 12,3. total=0 -> '0'."""
    if not total:
        return "0"
    return f"{_round(v / total * 1000) / 10:.1f}".replace(".", ",")


def msgs(n: int) -> str:
    return f"{n} {plural(n, 'повідомлення', 'повідомлення', 'повідомлень')}"


def pad(n: int) -> str:
    return f"{n:02d}"


def initials(name: str) -> str:
    return "".join(w[0] for w in (name or "").split()[:2]).upper()


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _media_list(media: dict, raw) -> list[dict]:
    """raw (id, список id або порожнє) -> [{'id', 'm'}] лише з наявних у media."""
    if raw is None or raw == "":
        ids = []
    elif isinstance(raw, (list, tuple)):
        ids = list(raw)
    else:
        ids = [raw]
    return [{"id": i, "m": media[i]} for i in ids if i and media.get(i)]


def _cover(lst: list[dict]) -> tuple[dict | None, str | None]:
    """Перше не-стікерне медіа = обкладинка плитки."""
    for e in lst:
        if "sticker" not in (e["m"].get("kind") or ""):
            return e["m"], e["id"]
    return None, None


class _Slugs:
    """Унікальні slug: порожній -> 'news'; зарезервований або вже зайнятий -> «-2», «-3»…"""

    def __init__(self):
        self.used: set[str] = set()

    def take(self, raw) -> str:
        base = _s(raw) or "news"
        s = base
        i = 2
        while s in self.used or s in RESERVED_SLUGS:
            s = f"{base}-{i}"
            i += 1
        self.used.add(s)
        return s


# ───────────────────────────── 1. новини ─────────────────────────────


def tile_classes(n: int) -> list[str]:
    """Класи плиток «Головного» для n новин: перша — велика (6×2), решта підлаштовується під кількість,
    щоб сітка 12 колонок не мала дірок. Раніше це були ~25 рядків умов у макросі news_grid."""
    out: list[str] = []
    m = n - 1
    for idx in range(n):
        if idx == 0:
            out.append("main-lead" + (" ms-solo" if m == 0 else ""))
            continue
        k = idx - 1
        sp = ""
        if m == 1:
            sp = " ms-6 ms-tall"
        elif m == 2:
            sp = " ms-6"
        elif m == 3:
            sp = " ms-6" if k == 0 else ""
        elif k >= 4:
            rest = m - 4
            full = (rest // 4) * 4
            j = k - 4
            if j >= full:
                r = rest - full
                sp = " ms-12" if r == 1 else (" ms-6" if r == 2 else " ms-4")
        out.append("main-small" + sp)
    return out


def _item(slug, cat, title, lead, body, media_lst, twin=None, day_chip=None) -> dict:
    cover, cover_id = _cover(media_lst)
    return {
        "slug": slug, "cat": cat, "title": title, "lead": lead, "body": body,
        "media": media_lst, "cover": cover, "cover_id": cover_id, "twin": twin, "day_chip": day_chip,
    }


def build_news(content, weekly, weekly_picks, media: dict, format_headline_date=None) -> dict:
    """Повертає {'news': [...], 'recap': [...], 'picks': [...], 'week': [...], 'cover_ids': [...]}.

    news — новина дня + статті («Головне»); recap — «Підсумок тижня» (0 або 1 елемент, лише коли є weekly.content);
    picks — «Обране за тиждень»: новини з випусків тижня, яких немає в «Головному» (їх обирає weekly.build_picks);
    week — recap + picks разом (для сторінок статей і «Читайте також»).
    Кожен елемент: slug, cat, title, lead, body, media [{id, m}], cover, cover_id, twin (завжди None, лишився для
    сумісності з шаблоном і скриптом), day_chip (повна назва дня тижня для «Обраного», інакше None), tile_cls, cover_seen.
    Рубрика, заголовок і текст «Обраного» лишаються такими, як в оригінальному випуску.
    cover_ids — обкладинки, що лежать у файлі повними даними (решта місць бере їх за посиланням).
    cover_seen — обкладинка цієї плитки вже вставлена вище за документом (плитка бере її за посиланням data-ref).
    """
    media = media or {}
    news: list[dict] = []
    recap: list[dict] = []
    picks: list[dict] = []
    if not content:
        return {"news": news, "recap": recap, "picks": picks, "week": [], "cover_ids": []}

    sl = _Slugs()
    h = content.get("headline") or {}
    news.append(_item(
        sl.take(h.get("slug") or "news-day"), "Новина дня", h.get("title"),
        h.get("lead") or h.get("subtitle"), h.get("body"),
        _media_list(media, h.get("media_ids") or h.get("cover_media_id") or h.get("media_id")),
    ))
    for i, a in enumerate(content.get("articles") or [], 1):
        news.append(_item(
            sl.take(a.get("slug") or f"news-{i}"), a.get("rubric"), a.get("title"),
            a.get("lead") or a.get("subtitle"), a.get("body"),
            _media_list(media, a.get("media_ids") or a.get("cover_media_id") or a.get("media_id")),
        ))

    wc = (weekly or {}).get("content") if weekly else None
    if wc:
        recap.append(_item(
            sl.take(wc.get("slug") or "week"), "Підсумок тижня", wc.get("title"),
            wc.get("lead") or wc.get("subtitle") or wc.get("intro"), wc.get("intro"),
            _media_list(media, wc.get("media_id")),
        ))

    news_titles = {_s(x["title"]) for x in news}
    for i, pk in enumerate(weekly_picks or [], 1):
        title = _s(pk.get("title"))
        if not title or title in news_titles:  # страховка: та сама історія вже є в «Головному»
            continue
        picks.append(_item(
            sl.take(pk.get("slug") or f"pick-{i}"), pk.get("rubric") or "Новини", pk.get("title"),
            pk.get("lead") or pk.get("subtitle"), pk.get("body"),
            _media_list(media, pk.get("media_ids") or pk.get("cover_media_id") or pk.get("media_id")),
            day_chip=_s(pk.get("weekday")).capitalize() or None,  # «Четвер» — над заголовком плитки
        ))

    for items in (news, recap, picks):
        for it, cls in zip(items, tile_classes(len(items))):
            it["tile_cls"] = cls

    week = recap + picks
    cover_ids = [it["cover_id"] for it in news + week if it["cover_id"]]
    seen: set[str] = set()
    for it in news + week:  # порядок = порядок плиток у документі: «Головне» → «Підсумок тижня» → «Обране за тиждень»
        cid = it["cover_id"]
        it["cover_seen"] = bool(cid) and cid in seen
        if cid:
            seen.add(cid)
    return {"news": news, "recap": recap, "picks": picks, "week": week, "cover_ids": cover_ids}


# ───────────────────────────── 2–3. статистика ─────────────────────────────


def _media_view(m: dict | None) -> dict | None:
    """{'photo', 'sticker', 'gif'} -> з підсумком; None, якщо даних немає."""
    if not isinstance(m, dict):
        return None
    photo = int(m.get("photo", 0) or 0)
    sticker = sum(int(v or 0) for k, v in m.items() if "sticker" in k)
    gif = int(m.get("gif", 0) or 0) + int(m.get("gif_preview", 0) or 0)
    return {"photo": photo, "sticker": sticker, "gif": gif, "total": photo + sticker + gif}


def _people_rows(people: list, total: int) -> list[dict]:
    pmax = (people[0][1] if people else 0) or 1
    return [
        {"rank": pad(i + 1), "ava": initials(n), "name": n, "count": c,
         "w": f"{c / pmax * 100:.1f}", "share": pct(c, total)}
        for i, (n, c) in enumerate(people)
    ]


def _media_section(m: dict, title: str) -> dict:
    mt = m["total"]
    return {
        "title": title, "count": f"{mt} {plural(mt, 'файл', 'файли', 'файлів')}",
        "photo": m["photo"], "sticker": m["sticker"], "gif": m["gif"],
        "legend": [
            {"cls": "m-photo", "n": m["photo"], "label": "фото", "share": pct(m["photo"], mt)},
            {"cls": "m-sticker", "n": m["sticker"], "label": "стікерів", "share": pct(m["sticker"], mt)},
            {"cls": "m-gif", "n": m["gif"], "label": "GIF", "share": pct(m["gif"], mt)},
        ],
    }


def _people_pairs(stats: dict, explicit) -> list[list]:
    """[[ім'я, кількість], …]: явний список бекенда, інакше all_senders, інакше top_senders."""
    if explicit:
        return [list(p) for p in explicit]
    src = stats.get("all_senders") or stats.get("top_senders") or []
    return [[s["sender"], s["count"]] for s in src]


def _bar(i, v, scale, is_peak, aria, label, rt, rs, pk) -> dict:
    return {"i": i, "h": f"{v / scale * 100:.1f}", "is_peak": is_peak, "aria": aria, "label": label,
            "rt": rt, "rs": rs, "pk": pk}


def build_day_stats(stats: dict, people=None, media=None, date_short: str = "") -> dict | None:
    """Дані вікна «Цифри дня → Детально». None, якщо учасників немає (кнопки не буде)."""
    stats = stats or {}
    ppl = _people_pairs(stats, people)
    hours = list(stats.get("messages_by_hour") or [])
    if not ppl or len(hours) != 24:
        return None
    total = int(stats.get("total_messages") or 0)
    mx = max(hours)
    scale = mx or 1
    peak = hours.index(mx)
    m = _media_view(media if media is not None else stats.get("media_counts"))

    best_s, best_v = 0, -1
    for s in range(0, 21):
        v = sum(hours[s:s + 4])
        if v > best_v:
            best_v, best_s = v, s
    zero = sum(1 for v in hours if v == 0)
    top3 = sum(p[1] for p in ppl[:3])

    kpis = [
        {"val": total, "text": "повідомлень за день"},
        {"val": len(ppl), "text": plural(len(ppl), "учасник", "учасники", "учасників")},
    ]
    if m:
        kpis.append({"val": m["total"], "text": f"медіа: {m['photo']} фото · {m['sticker']} стікерів · {m['gif']} GIF"})
    kpis.append({"val": f"{pad(peak)}:00", "hi": True, "text": f"пік · {msgs(mx)} ({pct(mx, total)}%)"})

    ins = [(ppl[0][0], f" — лідер дня: {msgs(ppl[0][1])}, або {pct(ppl[0][1], total)}% від загальної кількості")]
    fm, lm = stats.get("first_message"), stats.get("last_message")
    if fm and lm:
        bh = stats.get("busiest_hour")
        ins.append(("Активність чату:", f" з {fm.get('time')} до {lm.get('time')}" + (f", пік о {bh}" if bh else "")))
    ins += [
        (f"{pad(best_s)}:00–{pad(best_s + 3)}:59", f" — найактивніший відрізок: {msgs(best_v)}, або {pct(best_v, total)}% доби"),
        (f"{zero} з 24", " годин пройшли без жодного повідомлення"),
        ("Топ-3", f" учасники написали {pct(top3, total)}% усіх повідомлень"),
    ]

    bars = [
        _bar(i, v, scale, i == peak, f"{pad(i)}:00 — {msgs(v)}", pad(i),
             f"{pad(i)}:00–{pad(i)}:59", f"{msgs(v)} · {pct(v, total)}% доби", "пік дня" if i == peak else "")
        for i, v in enumerate(hours)
    ]
    return {
        "title": f"Цифри дня · {date_short}", "kpis": kpis, "peak": peak,
        "chart": {"title": "Активність по годинах", "hint": "наведіть або оберіть годину",
                  "aria": "Повідомлення по годинах", "gl_top": mx, "gl_mid": (mx + 1) // 2, "bars": bars},
        "insights_hint": "аналітика доби", "insights": ins,
        "people_head": f"{len(ppl)} {plural(len(ppl), 'учасник', 'учасники', 'учасників')}",
        "people": _people_rows(ppl, total),
        "media": _media_section(m, "Медіа за день") if m else None,
    }


def _full_date(s) -> str:
    """'2026-11-01' -> 'неділя, 1 листопада'; усе інше (наприклад '01.11') лишається як є."""
    try:
        d = Date.fromisoformat(str(s))
    except (TypeError, ValueError):
        return _s(s)
    return f"{WEEKDAYS_FULL[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}"


def build_week_stats(weekly: dict | None, people=None, media=None, period: str = "") -> dict | None:
    """Дані вікна «Цифри тижня → Детально». None, якщо тижневої статистики або учасників немає."""
    ws = ((weekly or {}).get("stats")) if weekly and weekly.get("content") else None
    if not ws:
        return None
    ppl = _people_pairs(ws, people)
    if not ppl:
        return None
    days = [[p.get("label"), p.get("date"), int(p.get("count") or 0)] for p in (ws.get("per_day") or [])]
    vals = [d[2] for d in days]
    total = int(ws.get("total_messages") or 0) or sum(vals) or 1
    mx = max(vals) if vals else 0
    scale = mx or 1
    peak = vals.index(mx) if vals and mx > 0 else -1
    low = vals.index(min(vals)) if vals else -1
    m = _media_view(media if media is not None else ws.get("media_counts"))
    has_media = bool(m and m["total"])
    avg_day = ws.get("avg_per_day") or (_round(total / len(days)) if days else 0)
    top3 = sum(p[1] for p in ppl[:3])
    peak_str = _full_date(days[peak][1]) if peak >= 0 else ""
    low_str = _full_date(days[low][1]) if low >= 0 else ""

    kpis = [
        {"val": total, "text": "повідомлень за тиждень"},
        {"val": len(ppl), "text": plural(len(ppl), "учасник", "учасники", "учасників")},
    ]
    if has_media:
        kpis.append({"val": m["total"], "text": f"медіа: {m['photo']} фото · {m['sticker']} стікерів · {m['gif']} GIF"})
    else:
        kpis.append({"val": f"~{avg_day}", "text": "у середньому на добу"})
    if days and peak_str:
        kpis.append({"val": mx, "hi": True, "text": f"пік тижня: {peak_str} · {pct(mx, total)}%"})

    mph = ws.get("msgs_per_hour")
    mph = _s(mph).replace(".", ",") if mph else f"{total / 168:.1f}".replace(".", ",")
    ins = [(ppl[0][0], f" — лідер тижня: {msgs(ppl[0][1])}, або {pct(ppl[0][1], total)}% від загальної кількості")]
    if avg_day:
        ins.append(("Темп спілкування:", f" у середньому ~{avg_day} {plural(avg_day, 'повідомлення', 'повідомлення', 'повідомлень')} на добу, близько {mph} щогодини"))
    if peak_str:
        ins.append((peak_str, f" — найактивніший день: {msgs(mx)}, або {pct(mx, total)}% тижня"))
    if low != peak and low_str:
        ins.append((low_str, f" — найтихіший день: {msgs(vals[low])}"))
    ins.append(("Топ-3", f" учасники написали {pct(top3, total)}% усіх повідомлень"))

    chart = None
    if days:
        chart = {
            "title": "Активність по днях", "hint": "наведіть або оберіть день", "aria": "Повідомлення по днях",
            "gl_top": mx, "gl_mid": (mx + 1) // 2,
            "bars": [
                _bar(i, d[2], scale, i == peak, f"{_s(d[1])} — {msgs(d[2])}", _s(d[0]),
                     f"{_s(d[0])}, {_s(d[1])}", f"{msgs(d[2])} · {pct(d[2], total)}% тижня", "пік тижня" if i == peak else "")
                for i, d in enumerate(days)
            ],
        }
    return {
        "title": "Цифри тижня" + (f" · {period}" if period else ""), "kpis": kpis, "peak": peak, "chart": chart,
        "insights_hint": "аналітика за 7 днів", "insights": ins,
        "people_head": f"{len(ppl)} {plural(len(ppl), 'учасник', 'учасники', 'учасників')}",
        "people": _people_rows(ppl, total),
        "media": _media_section(m, "Медіа за тиждень") if has_media else None,
    }
