"""Оптимізація медіа для газети: WebP для фото, перекодування відео, дедуплікація,
постери для гіфок.

Працює з dict media з data-URI, повертає оптимізований dict і звіт.
"""

import base64
import fractions
import hashlib
import io

try:
    import av

    HAS_AV = True
except ImportError:
    HAS_AV = False


def _decode_data_uri(data_uri: str) -> tuple[str, bytes]:
    """Повертає (mime, raw_bytes) з data-URI."""
    header, b64 = data_uri.split(",", 1)
    mime = header.split(":")[1].split(";")[0]
    return mime, base64.b64decode(b64)


def _encode_data_uri(mime: str, raw: bytes) -> str:
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


# ── Фото → WebP ──────────────────────────────────────────────────────────────


def _optimize_image(
    raw: bytes, mime: str, max_width: int = 1000, quality: int = 78
) -> tuple[str, bytes, int, int]:
    """JPEG/PNG → WebP з обмеженням ширини. Повертає (new_mime, new_bytes, w, h).
    Якщо WebP більший за оригінал — повертає оригінал без змін."""
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(raw))

    # Застосовуємо поворот з EXIF до того, як метадані зникнуть у WebP
    img = ImageOps.exif_transpose(img)

    # Обмеження ширини
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

    # Режими: прозорість зберігаємо (RGBA), решту переводимо в RGB
    if img.mode == "P":
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    elif img.mode == "LA":
        img = img.convert("RGBA")
    elif img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    w, h = img.width, img.height

    buf = io.BytesIO()
    img.save(
        buf, format="WEBP", quality=quality, method=4
    )  # EXIF не передаємо — він видалений

    webp_bytes = buf.getvalue()
    if len(webp_bytes) < len(raw):
        return "image/webp", webp_bytes, w, h
    return mime, raw, w, h  # оригінал менший


# ── Відео: перекодування через PyAV ───────────────────────────────────────────


def _get_video_fps(raw: bytes) -> float:
    """Отримує FPS відео через PyAV."""
    if not HAS_AV:
        return 24.0
    try:
        container = av.open(io.BytesIO(raw))
        stream = container.streams.video[0]
        fps = float(stream.average_rate or stream.guessed_rate or 24)
        container.close()
        return fps
    except Exception:
        return 24.0


def _optimize_video(raw: bytes) -> bytes:
    """Перекодовує mp4: без аудіо, scale ≤ 640, fps ≤ 24, crf 30.
    Якщо результат більший за оригінал (або PyAV недоступний) — повертає оригінал."""
    if not HAS_AV:
        return raw

    try:
        in_container = av.open(io.BytesIO(raw))
        if not in_container.streams.video:
            in_container.close()
            return raw
        in_stream = in_container.streams.video[0]

        src_fps = float(in_stream.average_rate or in_stream.guessed_rate or 24)
        target_fps = min(24, max(1, int(round(src_fps))))

        # Визначаємо парні розміри (scale ≤ 640)
        src_w = in_stream.codec_context.width
        src_h = in_stream.codec_context.height
        if src_w > 640:
            scale = 640 / src_w
            dst_w = 640
            dst_h = int(src_h * scale)
        else:
            dst_w = src_w
            dst_h = src_h
        dst_w -= dst_w % 2
        dst_h -= dst_h % 2

        out_buf = io.BytesIO()
        out_container = av.open(out_buf, mode="w", format="mp4")
        out_stream = out_container.add_stream("libx264", rate=target_fps)
        out_stream.width = dst_w
        out_stream.height = dst_h
        out_stream.pix_fmt = "yuv420p"
        out_stream.options = {
            "crf": "30",
            "preset": "slow",
            "movflags": "+faststart",
        }

        out_pts = 0
        next_time = 0.0
        frame_interval = 1.0 / target_fps
        out_tb = fractions.Fraction(1, target_fps)

        for frame in in_container.decode(video=0):
            t = (
                float(frame.time)
                if frame.time is not None
                else (out_pts * frame_interval)
            )
            if t < next_time - 0.0001:
                continue
            next_time += frame_interval

            f = frame.reformat(width=dst_w, height=dst_h, format="yuv420p")
            f.pts = out_pts
            f.time_base = out_tb
            out_pts += 1

            for packet in out_stream.encode(f):
                out_container.mux(packet)

        for packet in out_stream.encode():
            out_container.mux(packet)

        out_container.close()
        in_container.close()

        out_bytes = out_buf.getvalue()
        if len(out_bytes) < len(raw):
            return out_bytes
        return raw

    except Exception:
        return raw


# ── Постери для гіфок ─────────────────────────────────────────────────────────


def make_posters(media: dict, ids, width: int = 360, quality: int = 60) -> dict:
    """Постер (перший кадр у WebP, ширина ≤ width) для кожної гіфки-відео з ids.

    Повертає {media_id: data-URI}. Якщо PyAV недоступний або кадр не вдалося
    витягти — для цієї гіфки постера не буде (шаблон покаже перший кадр сам).
    """
    if not HAS_AV:
        print("  PyAV не знайдено — постери для гіфок пропущено")
        return {}
    from PIL import Image

    posters = {}
    for mid in ids:
        m = media.get(mid) or {}
        data = m.get("data") or ""
        if m.get("kind") != "gif" or not data.startswith("data:video"):
            continue
        try:
            _, raw = _decode_data_uri(data)
            container = av.open(io.BytesIO(raw))
            for frame in container.decode(video=0):
                img = frame.to_image()  # PIL Image
                # Масштабування
                if img.width > width:
                    ratio = width / img.width
                    img = img.resize((width, int(img.height * ratio)), Image.LANCZOS)
                buf = io.BytesIO()
                img.convert("RGB").save(buf, "WEBP", quality=quality, method=6)
                posters[mid] = _encode_data_uri("image/webp", buf.getvalue())
                break  # тільки перший кадр
            container.close()
        except Exception as e:  # noqa: BLE001 — постер не критичний
            print(f"  постер для {mid} не створено: {e}")
    return posters


# ── Дедуплікація ──────────────────────────────────────────────────────────────


def _content_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


# ── Головна функція ──────────────────────────────────────────────────────────


def optimize_media(media: dict, used_ids: set[str]) -> dict:
    """Оптимізує медіа, які реально використовуються у випуску.

    Повертає dict з полями:
      media  — оптимізований словник медіа
      report — dict з статистикою (до/після по типах)
    """
    report = {
        "before": {},
        "after": {},
        "dedup_saved": 0,
        "video_reencoded": 0,
        "images_converted": 0,
        "skipped_larger": 0,
    }

    # Порахуємо розміри до оптимізації
    total_before = 0
    for mid in used_ids:
        if mid not in media:
            continue
        m = media[mid]
        _, raw = _decode_data_uri(m["data"])
        report["before"][mid] = len(raw)
        total_before += len(raw)

    # 1. Дедуплікація: знаходимо дублікати по хешу контенту
    hash_to_first: dict[str, str] = {}  # hash → first media_id
    dedup_map: dict[str, str] = {}  # duplicate_id → canonical_id

    for mid in used_ids:
        if mid not in media:
            continue
        _, raw = _decode_data_uri(media[mid]["data"])
        h = _content_hash(raw)
        if h in hash_to_first:
            dedup_map[mid] = hash_to_first[h]
            report["dedup_saved"] += len(raw)
        else:
            hash_to_first[h] = mid

    # 2. Оптимізація (тільки канонічних, не дублікатів)
    optimized = {}
    for mid in used_ids:
        if mid not in media:
            continue

        # Якщо це дублікат — пропускаємо, пізніше підставимо
        if mid in dedup_map:
            continue

        m = media[mid].copy()
        mime, raw = _decode_data_uri(m["data"])
        kind = m["kind"]

        if kind in ("photo", "gif_preview"):
            # Фото → WebP
            if mime in ("image/jpeg", "image/png"):
                new_mime, new_raw, w, h = _optimize_image(raw, mime)
                m["w"], m["h"] = w, h
                if new_mime != mime:
                    report["images_converted"] += 1
                    m["data"] = _encode_data_uri(new_mime, new_raw)
                elif len(new_raw) < len(raw):
                    m["data"] = _encode_data_uri(mime, new_raw)
                # Якщо оригінал менший — data вже лишається як є

        elif kind == "gif":
            # GIF (mp4 base64) → перекодування
            new_raw = _optimize_video(raw)
            if len(new_raw) < len(raw):
                report["video_reencoded"] += 1
                m["data"] = _encode_data_uri(mime, new_raw)
            else:
                report["skipped_larger"] += 1

        # sticker, video_sticker, animated_sticker — не чіпаємо

        optimized[mid] = m

    # 3. Підставляємо дублікати
    for dup_id, canon_id in dedup_map.items():
        if canon_id in optimized:
            optimized[dup_id] = optimized[canon_id]
        elif canon_id in media:
            optimized[dup_id] = media[canon_id]

    # 4. Додаємо невикористані медіа як є (стікери тощо, що не в used_ids)
    for mid, m in media.items():
        if mid not in optimized:
            optimized[mid] = m

    # Порахуємо розміри після оптимізації
    total_after = 0
    for mid in used_ids:
        if mid not in optimized:
            continue
        _, raw = _decode_data_uri(optimized[mid]["data"])
        report["after"][mid] = len(raw)
        total_after += len(raw)

    report["total_before"] = total_before
    report["total_after"] = total_after

    return {"media": optimized, "report": report}


def ensure_media_dimensions(media: dict, ids: set[str] | list[str]) -> None:
    """Визначає ширину та висоту (w, h) для фото/відео/стікерів, якщо вони ще не задані."""
    from PIL import Image, ImageOps

    for mid in ids:
        if mid not in media:
            continue
        m = media[mid]
        if m.get("w") and m.get("h"):
            continue
        data = m.get("data", "")
        if not data or not data.startswith("data:"):
            continue
        kind = m.get("kind", "")
        try:
            mime, raw = _decode_data_uri(data)
            if "image" in mime or kind in ("photo", "sticker", "gif_preview"):
                img = Image.open(io.BytesIO(raw))
                img = ImageOps.exif_transpose(img)
                m["w"], m["h"] = img.width, img.height
            elif kind in ("gif", "video_sticker") and HAS_AV:
                container = av.open(io.BytesIO(raw))
                stream = container.streams.video[0]
                m["w"] = stream.codec_context.width
                m["h"] = stream.codec_context.height
                container.close()
        except Exception:
            pass
