"""Pika 1.5 / Runway Gen-3 clip generation + local demo renderer."""

from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import (
    DEMO_MODE,
    FPS,
    HEIGHT,
    OUTPUT_DIR,
    PIKA_API_BASE,
    PIKA_API_KEY,
    RUNWAY_API_BASE,
    RUNWAY_API_KEY,
    WIDTH,
)
from src.scenes import SCENES, Scene

log = logging.getLogger(__name__)


def generate_all_clips(scenes: List[Scene] | None = None) -> List[Path]:
    scenes = scenes or SCENES
    clip_dir = OUTPUT_DIR / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    for scene in scenes:
        out = clip_dir / f"scene_{scene.id:02d}_{scene.slug}.mp4"
        if out.exists() and out.stat().st_size > 10_000:
            log.info("Reusing existing clip: %s", out)
            paths.append(out)
            continue

        prompt = scene.prompts[0]
        if not DEMO_MODE and PIKA_API_KEY:
            try:
                _pika_generate(prompt, scene.duration, out)
                paths.append(out)
                continue
            except Exception as exc:  # noqa: BLE001
                log.error("Pika failed for scene %s: %s", scene.id, exc)

        if not DEMO_MODE and RUNWAY_API_KEY:
            try:
                _runway_generate(prompt, scene.duration, out)
                paths.append(out)
                continue
            except Exception as exc:  # noqa: BLE001
                log.error("Runway failed for scene %s: %s", scene.id, exc)

        log.warning("Rendering DEMO clip for scene %s (no/failed video API).", scene.id)
        _render_demo_clip(scene, out)
        paths.append(out)

    return paths


def _pika_generate(prompt: str, duration: float, out_path: Path) -> None:
    """Pika 1.5 text-to-video. Endpoint shapes vary by account — this hits the common v1 generate flow."""
    headers = {
        "Authorization": f"Bearer {PIKA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "promptText": prompt,
        "model": "1.5",
        "aspectRatio": "9:16",
        "duration": int(max(3, min(10, round(duration)))),
        "fps": FPS,
        "options": {"frameRate": FPS, "motion": 2, "guidanceScale": 12},
    }
    create = requests.post(
        f"{PIKA_API_BASE}/generate", headers=headers, json=payload, timeout=60
    )
    if create.status_code == 404:
        create = requests.post(
            f"{PIKA_API_BASE}/videos/generate", headers=headers, json=payload, timeout=60
        )
    create.raise_for_status()
    data = create.json()
    job_id = data.get("id") or data.get("job_id") or data.get("data", {}).get("id")
    if not job_id:
        raise RuntimeError(f"Unexpected Pika response: {data}")

    video_url = _poll_job(
        status_url=f"{PIKA_API_BASE}/videos/{job_id}",
        headers=headers,
        url_keys=("video_url", "url", "result_url", "download_url"),
    )
    _download(video_url, out_path)


def _runway_generate(prompt: str, duration: float, out_path: Path) -> None:
    """Runway Gen-3 text-to-video via official-style REST."""
    headers = {
        "Authorization": f"Bearer {RUNWAY_API_KEY}",
        "Content-Type": "application/json",
        "X-Runway-Version": "2024-11-06",
    }
    dur = int(max(5, min(10, round(duration))))
    payload = {
        "model": "gen3a_turbo",
        "promptText": prompt,
        "ratio": "720:1280",
        "duration": dur,
    }
    create = requests.post(
        f"{RUNWAY_API_BASE}/text_to_video", headers=headers, json=payload, timeout=60
    )
    create.raise_for_status()
    data = create.json()
    task_id = data.get("id") or data.get("task_id")
    if not task_id:
        raise RuntimeError(f"Unexpected Runway response: {data}")

    video_url = _poll_job(
        status_url=f"{RUNWAY_API_BASE}/tasks/{task_id}",
        headers=headers,
        url_keys=("output", "video_url", "url"),
        done_statuses=("SUCCEEDED", "completed", "COMPLETE"),
    )
    if isinstance(video_url, list):
        video_url = video_url[0]
    _download(str(video_url), out_path)


def _poll_job(
    status_url: str,
    headers: dict,
    url_keys: tuple,
    done_statuses: tuple = ("completed", "SUCCEEDED", "success", "COMPLETE"),
    timeout_s: int = 600,
) -> str:
    start = time.time()
    while time.time() - start < timeout_s:
        resp = requests.get(status_url, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        status = (
            data.get("status")
            or data.get("state")
            or data.get("data", {}).get("status")
            or ""
        ).upper()
        if status in {s.upper() for s in done_statuses}:
            for key in url_keys:
                if key in data and data[key]:
                    return data[key]
                nested = data.get("data") or data.get("result") or {}
                if key in nested and nested[key]:
                    return nested[key]
            # Runway often returns output list under output
            if data.get("output"):
                return data["output"]
            raise RuntimeError(f"Done but no URL in: {data}")
        if status in {"FAILED", "ERROR", "CANCELLED"}:
            raise RuntimeError(f"Job failed: {data}")
        time.sleep(5)
    raise TimeoutError(f"Timed out polling {status_url}")


def _download(url: str, out_path: Path) -> None:
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                if chunk:
                    f.write(chunk)


# ---------------------------------------------------------------------------
# DEMO local renderer — stylized cinematic stand-ins when APIs unavailable
# ---------------------------------------------------------------------------

def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    from config import FONT_PATH

    try:
        return ImageFont.truetype(str(FONT_PATH), size=size)
    except OSError:
        return ImageFont.load_default()


def _mosquito(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float, panic: bool) -> None:
    """Draw a simple expressive mosquito with tiny gas mask."""
    s = scale
    body = (40, 40, 45)
    # body
    draw.ellipse([cx - 18 * s, cy - 8 * s, cx + 18 * s, cy + 10 * s], fill=body)
    # head
    draw.ellipse([cx + 12 * s, cy - 10 * s, cx + 28 * s, cy + 6 * s], fill=(30, 30, 35))
    # gas mask
    draw.ellipse([cx + 16 * s, cy - 4 * s, cx + 34 * s, cy + 10 * s], fill=(60, 90, 70))
    draw.ellipse([cx + 28 * s, cy + 2 * s, cx + 40 * s, cy + 14 * s], outline=(30, 50, 30), width=2)
    # eyes
    eye_y = cy - 6 * s
    draw.ellipse([cx + 18 * s, eye_y - 4 * s, cx + 24 * s, eye_y + 4 * s], fill=(255, 255, 255))
    pupil = (220, 30, 30) if panic else (20, 20, 20)
    draw.ellipse([cx + 20 * s, eye_y - 2 * s, cx + 23 * s, eye_y + 2 * s], fill=pupil)
    # wings
    draw.ellipse([cx - 10 * s, cy - 28 * s, cx + 16 * s, cy - 4 * s], fill=(180, 210, 240))
    draw.ellipse([cx - 6 * s, cy - 24 * s, cx + 20 * s, cy], fill=(160, 200, 230))
    # legs hint
    for dx in (-10, 0, 10):
        draw.line([(cx + dx * s, cy + 8 * s), (cx + dx * s - 6 * s, cy + 22 * s)], fill=(20, 20, 20), width=2)


def _scene_palette(scene_id: int) -> tuple:
    if scene_id == 1:
        return (18, 40, 22), (40, 120, 50)  # toxic bathroom
    if scene_id == 2:
        return (70, 110, 150), (40, 70, 50)  # window ledge
    if scene_id == 3:
        return (110, 160, 210), (50, 100, 60)  # outside window
    return (40, 50, 70), (180, 100, 40)  # finale dusk


# Render demo at half-res then upscale — still 1080x1920 output, much faster.
_DEMO_W = WIDTH // 2
_DEMO_H = HEIGHT // 2
_DEMO_FPS = 24


def _render_frame(scene: Scene, t: float, duration: float, w: int = _DEMO_W, h: int = _DEMO_H) -> np.ndarray:
    base, accent = _scene_palette(scene.id)
    ys = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    pulse = 0.08 * math.sin(t * 3)
    r = np.clip(base[0] * (1 - ys) + accent[0] * ys + pulse * 40, 0, 255)
    g = np.clip(base[1] * (1 - ys) + accent[1] * ys + pulse * 40, 0, 255)
    b = np.clip(base[2] * (1 - ys) + accent[2] * ys, 0, 255)
    arr = np.concatenate(
        [np.repeat(r, w, axis=1)[..., None],
         np.repeat(g, w, axis=1)[..., None],
         np.repeat(b, w, axis=1)[..., None]],
        axis=2,
    ).astype(np.uint8)

    img = Image.fromarray(arr, mode="RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    # green toxic fog blobs (lighter blur for speed)
    fog = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fog)
    for i in range(8):
        cx = int(w * (0.2 + 0.6 * ((math.sin(t * 1.3 + i) + 1) / 2)))
        cy = int(h * (0.45 + 0.2 * math.sin(t * 0.9 + i * 0.7)))
        rad = int(70 + 40 * math.sin(t + i))
        alpha = 55 + (i % 5) * 8
        fd.ellipse([cx - rad, cy - rad // 2, cx + rad, cy + rad // 2], fill=(40, 220, 60, alpha))
    fog = fog.filter(ImageFilter.GaussianBlur(radius=14))
    img = Image.alpha_composite(img.convert("RGBA"), fog).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    if scene.id in (2, 3, 4):
        wx0, wy0, wx1, wy1 = int(w * 0.15), int(h * 0.18), int(w * 0.85), int(h * 0.55)
        draw.rectangle([wx0, wy0, wx1, wy1], outline=(220, 220, 230), width=6)
        draw.line([(w // 2, wy0), (w // 2, wy1)], fill=(200, 200, 210), width=4)
        draw.line([(wx0, (wy0 + wy1) // 2), (wx1, (wy0 + wy1) // 2)], fill=(200, 200, 210), width=4)

    if scene.id == 1:
        draw.ellipse([w * 0.25, h * 0.55, w * 0.75, h * 0.85], fill=(210, 215, 220))
        draw.ellipse([w * 0.32, h * 0.60, w * 0.68, h * 0.80], fill=(40, 90, 55))

    progress = t / max(duration, 0.01)
    scale = 1.7  # half-res scale factor for mosquito drawings
    if scene.id == 1:
        x = int(w * 0.5 + 20 * math.sin(t * 8))
        y = int(h * (0.45 - 0.15 * progress) + 10 * math.sin(t * 10))
        _mosquito(draw, x, y, 3.2 * scale / 2, panic=True)
    elif scene.id == 2:
        x = int(w * (0.2 + 0.5 * min(1, progress * 1.4)) + 6 * math.sin(t * 12))
        y = int(h * 0.38 + 16 * math.sin(t * 9))
        _mosquito(draw, x, y, 3.0 * scale / 2, panic=True)
    elif scene.id == 3:
        _mosquito(draw, int(w * 0.35), int(h * 0.40 + 6 * math.sin(t * 7)), 2.6 * scale / 2, True)
        _mosquito(draw, int(w * 0.55), int(h * 0.42 + 6 * math.cos(t * 7)), 2.6 * scale / 2, True)
        x = int(w * (0.85 - 0.35 * min(1, progress * 1.2)))
        y = int(h * 0.30 + 10 * math.sin(t * 6))
        _mosquito(draw, x, y, 2.8 * scale / 2, panic=False)
    else:
        for i, px in enumerate((0.3, 0.5, 0.7)):
            x = int(w * (px + 0.25 * progress) + 8 * math.sin(t * 8 + i))
            y = int(h * (0.45 - 0.25 * progress) + 6 * math.cos(t * 7 + i))
            _mosquito(draw, x, y, 2.7 * scale / 2, panic=True)

    font_sm = _font(28)
    draw.text((24, 32), scene.location, font=font_sm, fill=(240, 240, 240))

    if scene.id == 4 and progress > 0.55:
        font_big = _font(32)
        text = "POV: You ate beans yesterday"
        bbox = draw.textbbox((0, 0), text, font=font_big)
        tw = bbox[2] - bbox[0]
        tx = (w - tw) // 2
        ty = int(h * 0.78)
        for ox, oy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            draw.text((tx + ox, ty + oy), text, font=font_big, fill=(0, 0, 0))
        draw.text((tx, ty), text, font=font_big, fill=(255, 230, 40))

    return np.array(img)


def _render_demo_clip(scene: Scene, out_path: Path) -> None:
    import subprocess
    from moviepy import VideoClip

    duration = scene.duration
    tmp = out_path.with_suffix(".half.mp4")

    def make_frame(t: float):
        return _render_frame(scene, t, duration)

    clip = VideoClip(make_frame, duration=duration).with_fps(_DEMO_FPS)
    clip.write_videofile(
        str(tmp),
        fps=_DEMO_FPS,
        codec="libx264",
        audio=False,
        preset="ultrafast",
        threads=2,
        logger=None,
    )
    clip.close()

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(tmp),
            "-vf", f"scale={WIDTH}:{HEIGHT}:flags=lanczos",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
            str(out_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    tmp.unlink(missing_ok=True)


def write_prompt_pack(path: Optional[Path] = None) -> Path:
    from src.scenes import export_prompts_markdown

    path = path or (OUTPUT_DIR / "SCENE_PROMPTS.md")
    path.write_text(export_prompts_markdown(), encoding="utf-8")
    return path