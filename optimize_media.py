"""Оптимізація медіа для газети: WebP для фото, перекодування відео, дедуплікація,
постери для гіфок.

Працює з dict media з data-URI, повертає оптимізований dict і звіт.
"""

import base64
import hashlib
import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _find_bin(name: str) -> str | None:
    """Спершу шукає ffmpeg/<name>(.exe) поруч зі скриптом, потім у PATH."""
    local = (
        Path(__file__).parent / "ffmpeg" / (name + (".exe" if os.name == "nt" else ""))
    )
    if local.exists():
        return str(local)
    return shutil.which(name)


FFMPEG = _find_bin("ffmpeg")
FFPROBE = _find_bin("ffprobe")


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
) -> tuple[str, bytes]:
    """JPEG/PNG → WebP з обмеженням ширини. Повертає (new_mime, new_bytes).
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

    buf = io.BytesIO()
    img.save(
        buf, format="WEBP", quality=quality, method=4
    )  # EXIF не передаємо — він видалений

    webp_bytes = buf.getvalue()
    if len(webp_bytes) < len(raw):
        return "image/webp", webp_bytes
    return mime, raw  # оригінал менший


# ── Відео: перекодування ffmpeg ───────────────────────────────────────────────


def _get_video_fps(path: str) -> float:
    """Отримує FPS відео через ffprobe."""
    if not FFPROBE:
        return 24.0
    try:
        r = subprocess.run(
            [
                FFPROBE,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=r_frame_rate",
                "-of",
                "csv=p=0",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        parts = r.stdout.strip().split("/")
        if len(parts) == 2 and int(parts[1]) > 0:
            return int(parts[0]) / int(parts[1])
        return float(parts[0]) if parts[0] else 24.0
    except Exception:
        return 24.0


def _optimize_video(raw: bytes) -> bytes:
    """Перекодовує mp4: -an, scale ≤ 640, fps ≤ 24, crf 30, slow.
    Якщо результат більший за оригінал (або ffmpeg недоступний) — повертає оригінал."""
    if not FFMPEG:
        return raw
    with tempfile.TemporaryDirectory() as tmp:
        inp = os.path.join(tmp, "in.mp4")
        out = os.path.join(tmp, "out.mp4")
        with open(inp, "wb") as f:
            f.write(raw)

        fps = _get_video_fps(inp)
        target_fps = min(24, fps)

        cmd = [
            FFMPEG,
            "-y",
            "-i",
            inp,
            "-an",
            "-vf",
            f"scale='min(640,iw)':-2,fps={target_fps}",
            "-c:v",
            "libx264",
            "-crf",
            "30",
            "-preset",
            "slow",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            out,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return raw

        with open(out, "rb") as f:
            out_bytes = f.read()
        if len(out_bytes) < len(raw):
            return out_bytes
        return raw


# ── Постери для гіфок ─────────────────────────────────────────────────────────


def make_posters(media: dict, ids, width: int = 360, quality: int = 60) -> dict:
    """Постер (перший кадр у WebP, ширина ≤ width) для кожної гіфки-відео з ids.

    Повертає {media_id: data-URI}. Якщо ffmpeg недоступний або кадр не вдалося
    витягти — для цієї гіфки постера не буде (шаблон покаже перший кадр сам).
    """
    if not FFMPEG:
        print("  ffmpeg не знайдено — постери для гіфок пропущено")
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
            with tempfile.TemporaryDirectory() as tmp:
                src = os.path.join(tmp, "in.mp4")
                png = os.path.join(tmp, "poster.png")
                with open(src, "wb") as f:
                    f.write(raw)
                subprocess.run(
                    [
                        FFMPEG,
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        src,
                        "-frames:v",
                        "1",
                        "-vf",
                        f"scale='min({width},iw)':-2",
                        png,
                    ],
                    capture_output=True,
                    timeout=30,
                    check=True,
                )
                buf = io.BytesIO()
                with Image.open(png) as im:
                    im.convert("RGB").save(buf, "WEBP", quality=quality, method=6)
            posters[mid] = _encode_data_uri("image/webp", buf.getvalue())
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
                new_mime, new_raw = _optimize_image(raw, mime)
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
