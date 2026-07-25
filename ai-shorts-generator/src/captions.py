"""Word-by-word highlighted captions: Montserrat ExtraBold, yellow + black stroke."""

from __future__ import annotations

from typing import List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import ImageClip, CompositeVideoClip

from config import FONT_PATH, HEIGHT, WIDTH

WordTiming = Tuple[str, float, float]


def _font(size: int = 64) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT_PATH), size=size)
    except OSError:
        return ImageFont.load_default()


def _render_caption_image(words: List[str], highlight_idx: int, max_width: int = 980) -> np.ndarray:
    font = _font(62)
    # Wrap into ~4 words per line for Shorts readability
    lines: List[List[tuple[str, int]]] = []
    current: List[tuple[str, int]] = []
    global_i = 0
    for w in words:
        current.append((w, global_i))
        global_i += 1
        if len(current) >= 4:
            lines.append(current)
            current = []
    if current:
        lines.append(current)

    # Measure
    line_heights = []
    line_widths = []
    tmp = Image.new("RGBA", (max_width, 400), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    for line in lines:
        text = " ".join(w for w, _ in line)
        bbox = d.textbbox((0, 0), text, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1] + 14)
    img_h = sum(line_heights) + 20
    img_w = min(max_width, max(line_widths + [100]) + 40)
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    y = 8
    for line, lh in zip(lines, line_heights):
        # compute x start for centered line
        text = " ".join(w for w, _ in line)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        x = (img_w - tw) // 2
        for word, idx in line:
            color = (255, 230, 0, 255) if idx == highlight_idx else (255, 255, 255, 255)
            # black stroke
            for ox in (-3, -2, -1, 0, 1, 2, 3):
                for oy in (-3, -2, -1, 0, 1, 2, 3):
                    if ox == 0 and oy == 0:
                        continue
                    draw.text((x + ox, y + oy), word, font=font, fill=(0, 0, 0, 255))
            draw.text((x, y), word, font=font, fill=color)
            wb = draw.textbbox((0, 0), word + " ", font=font)
            x += wb[2] - wb[0]
        y += lh

    return np.array(img)


def build_caption_clips(
    timings: List[WordTiming],
    video_duration: float,
) -> List:
    """Return a list of ImageClips with word-by-word highlight."""
    if not timings:
        return []

    # Group into rolling windows of ~8 words for display context
    clips = []
    n = len(timings)
    window = 8
    for i, (word, start, end) in enumerate(timings):
        if start >= video_duration:
            break
        end = min(end, video_duration)
        dur = max(0.05, end - start)
        win_start = max(0, i - (window // 2))
        win_end = min(n, win_start + window)
        win_start = max(0, win_end - window)
        words = [timings[j][0] for j in range(win_start, win_end)]
        highlight = i - win_start
        frame = _render_caption_image(words, highlight)
        clip = (
            ImageClip(frame, duration=dur, transparent=True)
            .with_start(start)
            .with_position(("center", int(HEIGHT * 0.72)))
        )
        clips.append(clip)
    return clips


def compose_with_captions(base_clip, timings: List[WordTiming]):
    caps = build_caption_clips(timings, base_clip.duration)
    if not caps:
        return base_clip
    return CompositeVideoClip([base_clip, *caps], size=(WIDTH, HEIGHT))