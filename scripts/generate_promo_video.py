#!/usr/bin/env python3
"""Generate a short Choice Coin promotional video."""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
FPS = 30
FRAMES_DIR = Path("/tmp/choice-frames")
OUT_REPO = Path("/workspace/media/choice-coin-promo.mp4")
OUT_ARTIFACT = Path("/opt/cursor/artifacts/choice-coin-promo.mp4")
LOGO_PATH = Path("/workspace/Logo_200x200.png")

FONT_BOLD = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
FONT_SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"

# Brand palette aligned with the Choice Coin site
NAVY = (12, 18, 48)
INDIGO = (92, 84, 219)
INDIGO_LIGHT = (106, 130, 231)
WHITE = (255, 255, 255)
SOFT = (210, 218, 240)
ACCENT = (99, 102, 241)

_Y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
_X = np.linspace(0, 1, W, dtype=np.float32)[None, :]
_BASE = np.empty((H, W, 3), dtype=np.uint8)
_BASE[..., 0] = (12 + _Y[:, 0] * 10).astype(np.uint8)[:, None]
_BASE[..., 1] = (18 + _Y[:, 0] * 10).astype(np.uint8)[:, None]
_BASE[..., 2] = (48 + _Y[:, 0] * 24).astype(np.uint8)[:, None]


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 3 * t * t - 2 * t * t * t


def mix(c1, c2, t: float):
    t = max(0.0, min(1.0, t))
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def text_size(draw: ImageDraw.ImageDraw, text: str, fnt) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: float,
    fnt,
    fill,
    opacity: float = 1.0,
    img: Image.Image | None = None,
):
    opacity = max(0.0, min(1.0, opacity))
    if opacity <= 0:
        return
    tw, th = text_size(draw, text, fnt)
    x = (W - tw) / 2
    if opacity >= 0.999:
        draw.text((x, y), text, font=fnt, fill=fill)
        return
    # Soft fade via temporary overlay
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    color = (*fill[:3], int(255 * opacity))
    od.text((x, y), text, font=fnt, fill=color)
    if img is not None:
        img.alpha_composite(overlay)


def paint_background(img: Image.Image, t: float, phase: float = 0.0):
    """Deep navy with drifting indigo orbs and subtle grid."""
    base = Image.fromarray(_BASE, mode="RGB").convert("RGBA")
    img.paste(base)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # Soft orbs
    orbs = [
        (0.22, 0.35, 280, (92, 84, 219, 70)),
        (0.78, 0.55, 340, (106, 130, 231, 55)),
        (0.55, 0.18, 220, (72, 100, 210, 45)),
    ]
    for ox, oy, r, color in orbs:
        cx = int(W * (ox + 0.03 * math.sin(t * 0.7 + phase + ox * 4)))
        cy = int(H * (oy + 0.04 * math.cos(t * 0.55 + phase + oy * 3)))
        blob = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(blob)
        bd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        overlay = Image.alpha_composite(overlay, blob)

    # Fine diagonal sheen
    sheen = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheen)
    for i in range(-H, W, 28):
        alpha = 10 + int(6 * math.sin((i + t * 40) * 0.02))
        sd.line([(i, 0), (i + H, H)], fill=(255, 255, 255, alpha), width=1)
    overlay = Image.alpha_composite(overlay, sheen)

    img.alpha_composite(overlay)


def load_logo(size: int = 160) -> Image.Image:
    logo = Image.open(LOGO_PATH).convert("RGBA")
    logo = logo.resize((size, size), Image.Resampling.LANCZOS)
    return logo


def scene_intro(frame: int, total: int, logo: Image.Image) -> Image.Image:
    t = frame / FPS
    progress = frame / max(total - 1, 1)
    img = Image.new("RGBA", (W, H), (*NAVY, 255))
    paint_background(img, t, 0.2)
    draw = ImageDraw.Draw(img)

    appear = ease_out(progress / 0.35) if progress < 0.35 else 1.0
    lift = int(lerp(40, 0, appear))

    # Logo
    lw, lh = logo.size
    lx = (W - lw) // 2
    ly = 160 + lift
    if appear > 0:
        faded = logo.copy()
        alpha = faded.split()[-1].point(lambda a: int(a * appear))
        faded.putalpha(alpha)
        img.paste(faded, (lx, ly), faded)

    title_f = font(FONT_BOLD, 72)
    sub_f = font(FONT_REG, 28)
    draw_centered(draw, "Choice Coin", 360 + lift, title_f, WHITE, appear, img)
    draw_centered(
        draw,
        "Democratic Token for a New Age",
        450 + lift,
        sub_f,
        SOFT,
        max(0.0, (appear - 0.35) / 0.65),
        img,
    )
    return img.convert("RGB")


def scene_mission(frame: int, total: int) -> Image.Image:
    t = frame / FPS
    progress = frame / max(total - 1, 1)
    img = Image.new("RGBA", (W, H), (*NAVY, 255))
    paint_background(img, t, 1.1)
    draw = ImageDraw.Draw(img)

    fade_in = ease_out(min(1.0, progress / 0.25))
    fade_out = 1.0 if progress < 0.8 else ease_out((1.0 - progress) / 0.2)
    opacity = fade_in * fade_out
    y_off = int(lerp(28, 0, fade_in))

    eyebrow = font(FONT_REG, 22)
    title = font(FONT_SERIF, 54)
    body = font(FONT_REG, 26)

    draw_centered(draw, "FORTIOR VOTING PROTOCOL", 180 + y_off, eyebrow, mix(SOFT, INDIGO_LIGHT, 0.4), opacity, img)
    draw_centered(draw, "Decentralized voting,", 250 + y_off, title, WHITE, opacity, img)
    draw_centered(draw, "built for communities.", 320 + y_off, title, WHITE, opacity, img)
    draw_centered(
        draw,
        "Powered by Algorand — designed for transparent governance.",
        430 + y_off,
        body,
        SOFT,
        opacity * 0.95,
        img,
    )
    return img.convert("RGB")


def scene_features(frame: int, total: int) -> Image.Image:
    t = frame / FPS
    progress = frame / max(total - 1, 1)
    img = Image.new("RGBA", (W, H), (*NAVY, 255))
    paint_background(img, t, 2.0)
    draw = ImageDraw.Draw(img)

    fade_in = ease_out(min(1.0, progress / 0.2))
    fade_out = 1.0 if progress < 0.85 else ease_out((1.0 - progress) / 0.15)
    opacity = fade_in * fade_out

    headline = font(FONT_BOLD, 40)
    card_title = font(FONT_BOLD, 28)
    card_body = font(FONT_REG, 20)

    draw_centered(draw, "Promoting Democracy & Decentralization", 90, headline, WHITE, opacity, img)

    cards = [
        ("Decentralized Voting", "Governance tech for the\nnext generation."),
        ("Participatory Validation", "Holders vote on network\nallocations in real time."),
        ("Open Integration", "Bring Fortior into your\nown community."),
    ]

    card_w, card_h = 320, 220
    gap = 40
    total_w = 3 * card_w + 2 * gap
    start_x = (W - total_w) // 2
    base_y = 200

    for i, (title, body) in enumerate(cards):
        # Staggered entrance
        local = ease_out(max(0.0, min(1.0, (progress - i * 0.08) / 0.35)))
        a = opacity * local
        if a <= 0:
            continue
        x = start_x + i * (card_w + gap)
        y = base_y + int(lerp(36, 0, local))

        panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(panel)
        # Rounded rectangle background
        pd.rounded_rectangle(
            (x, y, x + card_w, y + card_h),
            radius=24,
            fill=(255, 255, 255, int(18 * a)),
            outline=(*INDIGO_LIGHT, int(120 * a)),
            width=2,
        )
        # Accent bar
        pd.rounded_rectangle(
            (x + 28, y + 36, x + 68, y + 44),
            radius=4,
            fill=(*ACCENT, int(255 * a)),
        )
        pd.text((x + 28, y + 64), title, font=card_title, fill=(*WHITE, int(255 * a)))
        pd.multiline_text((x + 28, y + 112), body, font=card_body, fill=(*SOFT, int(230 * a)), spacing=6)
        img.alpha_composite(panel)

    return img.convert("RGB")


def scene_cta(frame: int, total: int, logo: Image.Image) -> Image.Image:
    t = frame / FPS
    progress = frame / max(total - 1, 1)
    img = Image.new("RGBA", (W, H), (*NAVY, 255))
    paint_background(img, t, 3.2)
    draw = ImageDraw.Draw(img)

    fade_in = ease_out(min(1.0, progress / 0.3))
    pulse = 0.92 + 0.08 * math.sin(t * 3.2)
    opacity = fade_in

    small = logo.resize((96, 96), Image.Resampling.LANCZOS)
    faded = small.copy()
    alpha = faded.split()[-1].point(lambda a: int(a * opacity))
    faded.putalpha(alpha)
    img.paste(faded, ((W - 96) // 2, 140), faded)

    title = font(FONT_BOLD, 56)
    body = font(FONT_REG, 26)
    cta_f = font(FONT_BOLD, 24)

    draw_centered(draw, "Make your Choice.", 280, title, WHITE, opacity, img)
    draw_centered(
        draw,
        "Explore the white paper and join the network.",
        360,
        body,
        SOFT,
        opacity,
        img,
    )

    # CTA pill
    label = "choice-coin.github.io"
    tw, th = text_size(draw, label, cta_f)
    pad_x, pad_y = 36, 18
    bw, bh = tw + pad_x * 2, th + pad_y * 2
    bx = (W - bw) // 2
    by = 440
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    scale = pulse
    # Slight pulse via alpha
    pd.rounded_rectangle(
        (bx, by, bx + bw, by + bh),
        radius=bh // 2,
        fill=(*INDIGO, int(230 * opacity * scale)),
    )
    pd.text((bx + pad_x, by + pad_y - 2), label, font=cta_f, fill=(*WHITE, int(255 * opacity)))
    img.alpha_composite(panel)

    return img.convert("RGB")


def write_scene(frames: list[Image.Image], start_idx: int) -> int:
    idx = start_idx
    for frame in frames:
        frame.save(FRAMES_DIR / f"frame_{idx:05d}.png")
        idx += 1
    return idx


def render_scene(renderer, duration_s: float, *args) -> list[Image.Image]:
    total = int(duration_s * FPS)
    return [renderer(i, total, *args) if args else renderer(i, total) for i in range(total)]


def encode_video():
    OUT_REPO.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(FPS),
        "-i",
        str(FRAMES_DIR / "frame_%05d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "20",
        "-movflags",
        "+faststart",
        str(OUT_REPO),
    ]
    subprocess.run(cmd, check=True)
    shutil.copy2(OUT_REPO, OUT_ARTIFACT)


def main():
    if FRAMES_DIR.exists():
        shutil.rmtree(FRAMES_DIR)
    FRAMES_DIR.mkdir(parents=True)

    logo = load_logo(168)

    print("Rendering intro…")
    intro = render_scene(scene_intro, 3.5, logo)
    print("Rendering mission…")
    mission = render_scene(scene_mission, 4.0)
    print("Rendering features…")
    features = render_scene(scene_features, 5.0)
    print("Rendering CTA…")
    cta = render_scene(scene_cta, 4.0, logo)

    idx = 0
    for batch in (intro, mission, features, cta):
        idx = write_scene(batch, idx)

    print(f"Encoded {idx} frames → mp4")
    encode_video()
    print(f"Wrote {OUT_REPO}")
    print(f"Artifact {OUT_ARTIFACT}")


if __name__ == "__main__":
    main()
