#!/usr/bin/env python3
"""Render the Davie & Stevie 'petting zoo' sketch as a short film."""

from __future__ import annotations

import math
import shutil
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
FPS = 24
SCENE = Path("/opt/cursor/artifacts/assets/davie-stevie-scene.png")
WORK = Path("/tmp/davie-stevie")
FRAMES = WORK / "frames"
AUDIO = WORK / "audio"
OUT_ARTIFACT = Path("/opt/cursor/artifacts/davie-stevie-petting-zoo.mp4")
OUT_REPO = Path("/workspace/media/davie-stevie-petting-zoo.mp4")

FONT_BOLD = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
FONT_ITAL = "/usr/share/fonts/truetype/noto/NotoSans-Italic.ttf"

# Dialogue timeline: (speaker, stage_direction, line)
# Speakers: DAVIE (buzzing), STEVIE (panicking), TITLE, CARD
LINES = [
    ("TITLE", "", "DAVIE'S FLAT"),
    ("CARD", "", "Somewhere in Glasgow. A bag of cash. A terrible idea."),
    (
        "STEVIE",
        "Gasping",
        "Davie... tell me ye didnae. Tell me that's just a bag of very heavy laundry.",
    ),
    (
        "DAVIE",
        "Grinning",
        "Better than laundry, mate! It's capital! We're businessmen now, Stevie! I found it in the alley behind the chippy. Some big bald bloke in a Merc dropped it.",
    ),
    (
        "STEVIE",
        "",
        "A big bald bloke in a Merc?! That's Big Tam's motor! We're dead. He's gonna turn us into haggis, Davie!",
    ),
    (
        "DAVIE",
        "",
        "Away an' bile yer heid! He doesn't know it's us. We just need to clean the cash. I've already bought us a business on the internet.",
    ),
    (
        "STEVIE",
        "",
        "What did ye buy?! A car wash? A cafe?",
    ),
    (
        "DAVIE",
        "Proudly",
        "A petting zoo in the Highlands.",
    ),
    ("CARD", "", "TO BE CONTINUED..."),
]


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def font(path: str, size: int):
    return ImageFont.truetype(path, size)


def wrap(text: str, width: int = 42) -> str:
    return "\n".join(textwrap.wrap(text, width=width)) if text else ""


def synthesize_line(idx: int, speaker: str, line: str) -> Path | None:
    """Create WAV for a spoken line. Returns None for non-spoken cards."""
    if speaker in {"TITLE", "CARD"} or not line.strip():
        return None

    out = AUDIO / f"line_{idx:02d}.wav"
    # Prefer edge-tts British males; fall back to Scottish flite awb.
    voice = "en-GB-RyanNeural" if speaker == "DAVIE" else "en-GB-ThomasNeural"
    # Keep rate/pitch as --opt=value so negative values are not parsed as flags.
    rate = "+12%" if speaker == "DAVIE" else "+5%"
    pitch = "+4Hz" if speaker == "DAVIE" else "+0Hz"

    # Phonetic-ish spelling helps TTS with Scots
    spoken = (
        line.replace("didnae", "did-nay")
        .replace("ye ", "yih ")
        .replace("Ye ", "Yih ")
        .replace("bile yer heid", "bile yer heed")
    )

    edge = shutil.which("edge-tts") or str(Path.home() / ".local/bin/edge-tts")
    mp3 = AUDIO / f"line_{idx:02d}.mp3"
    txt = AUDIO / f"line_{idx:02d}.txt"
    txt.write_text(spoken, encoding="utf-8")

    try:
        run(
            [
                edge,
                "--voice",
                voice,
                f"--rate={rate}",
                f"--pitch={pitch}",
                "-f",
                str(txt),
                "--write-media",
                str(mp3),
            ]
        )
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mp3),
                "-ar",
                "44100",
                "-ac",
                "1",
                str(out),
            ]
        )
        return out
    except Exception as exc:
        print(f"  edge-tts failed ({exc}); trying flite awb")
        # Scottish flite fallback via text file + CLI if available, else lavfi
        flite_bin = shutil.which("flite")
        if flite_bin:
            raw = AUDIO / f"line_{idx:02d}_raw.wav"
            run([flite_bin, "-voice", "awb", "-f", str(txt), "-o", str(raw)])
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(raw),
                    "-ar",
                    "44100",
                    "-ac",
                    "1",
                    str(out),
                ]
            )
            return out
        # Last resort: strip punctuation that breaks lavfi parsing
        safe = (
            spoken.replace("'", "")
            .replace("!", ".")
            .replace("?", ".")
            .replace(":", ",")
            .replace("\\", " ")
        )
        run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"flite=text='{safe}':voice=awb",
                "-ar",
                "44100",
                "-ac",
                "1",
                str(out),
            ]
        )
        return out


def wav_duration(path: Path) -> float:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(probe.stdout.strip())


def load_scene() -> Image.Image:
    img = Image.open(SCENE).convert("RGB")
    # Cover 1280x720
    scale = max(W / img.width, H / img.height)
    nw, nh = int(img.width * scale), int(img.height * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    return img


def ken_burns(base: Image.Image, t: float, total: float, focus: str) -> Image.Image:
    """Slow zoom/pan. focus: wide | davie | stevie | cash | punch"""
    progress = t / max(total, 0.001)
    # Extra canvas for pan room
    zoom = 1.08 + 0.10 * progress
    if focus == "davie":
        cx, cy = 0.32, 0.42
        zoom = 1.25 + 0.08 * math.sin(progress * math.pi)
    elif focus == "stevie":
        cx, cy = 0.72, 0.45
        zoom = 1.28 + 0.06 * progress
    elif focus == "cash":
        cx, cy = 0.50, 0.58
        zoom = 1.35 + 0.10 * progress
    elif focus == "punch":
        cx, cy = 0.38, 0.40
        zoom = 1.20 + 0.15 * progress
    else:
        cx, cy = 0.50 + 0.02 * math.sin(progress * math.pi), 0.48

    bw, bh = base.size
    cw, ch = int(W * zoom), int(H * zoom)
    cw = min(cw, bw)
    ch = min(ch, bh)
    left = int(cx * bw - cw / 2)
    top = int(cy * bh - ch / 2)
    left = max(0, min(left, bw - cw))
    top = max(0, min(top, bh - ch))
    crop = base.crop((left, top, left + cw, top + ch)).resize((W, H), Image.Resampling.LANCZOS)
    return crop


def draw_caption(img: Image.Image, speaker: str, direction: str, line: str) -> Image.Image:
    out = img.convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    if speaker == "TITLE":
        # Big title treatment
        d.rectangle((0, 0, W, H), fill=(8, 10, 14, 170))
        tf = font(FONT_BOLD, 64)
        sf = font(FONT_ITAL, 28)
        title = line
        tw = d.textbbox((0, 0), title, font=tf)
        d.text(((W - (tw[2] - tw[0])) / 2, H * 0.42), title, font=tf, fill=(255, 255, 255, 255))
        sub = "A very bad business plan"
        sw = d.textbbox((0, 0), sub, font=sf)
        d.text(((W - (sw[2] - sw[0])) / 2, H * 0.55), sub, font=sf, fill=(220, 200, 160, 230))
        out = Image.alpha_composite(out, overlay)
        return out.convert("RGB")

    if speaker == "CARD":
        d.rectangle((0, int(H * 0.72), W, H), fill=(0, 0, 0, 180))
        cf = font(FONT_REG, 28)
        text = line
        bw = d.textbbox((0, 0), text, font=cf)
        d.text(((W - (bw[2] - bw[0])) / 2, H * 0.82), text, font=cf, fill=(240, 240, 240, 255))
        out = Image.alpha_composite(out, overlay)
        return out.convert("RGB")

    # Dialogue caption bar
    boxed = wrap(line, 48)
    name_f = font(FONT_BOLD, 22)
    body_f = font(FONT_REG, 26)
    dir_f = font(FONT_ITAL, 18)

    lines = boxed.split("\n")
    line_h = 34
    block_h = 28 + (len(lines) * line_h) + (22 if direction else 0) + 28
    top = H - block_h - 28
    pad = 36

    # Color by speaker
    if speaker == "DAVIE":
        accent = (40, 120, 220, 255)
        name_col = (120, 190, 255, 255)
    else:
        accent = (220, 110, 40, 255)
        name_col = (255, 180, 120, 255)

    d.rounded_rectangle((pad, top, W - pad, H - 24), radius=16, fill=(10, 10, 14, 210))
    d.rectangle((pad, top, pad + 8, H - 24), fill=accent)

    y = top + 16
    label = speaker.title()
    d.text((pad + 28, y), label, font=name_f, fill=name_col)
    if direction:
        dw = d.textbbox((0, 0), label, font=name_f)
        d.text((pad + 36 + (dw[2] - dw[0]), y + 2), f"({direction})", font=dir_f, fill=(180, 180, 190, 230))
    y += 30
    for ln in lines:
        d.text((pad + 28, y), ln, font=body_f, fill=(245, 245, 248, 255))
        y += line_h

    out = Image.alpha_composite(out, overlay)
    return out.convert("RGB")


def focus_for(speaker: str, idx: int) -> str:
    if speaker == "TITLE":
        return "wide"
    if speaker == "CARD":
        return "wide" if idx == 1 else "punch"
    if speaker == "DAVIE":
        if "petting zoo" in LINES[idx][2].lower():
            return "punch"
        if "capital" in LINES[idx][2].lower() or "chippy" in LINES[idx][2].lower():
            return "cash"
        return "davie"
    if "Merc" in LINES[idx][2] or "haggis" in LINES[idx][2]:
        return "stevie"
    if "car wash" in LINES[idx][2].lower():
        return "stevie"
    return "stevie"


def build_timeline() -> list[dict]:
    AUDIO.mkdir(parents=True, exist_ok=True)
    events = []
    t = 0.0
    for i, (speaker, direction, line) in enumerate(LINES):
        wav = synthesize_line(i, speaker, line)
        if wav:
            dur = wav_duration(wav) + 0.45  # breathing room
        elif speaker == "TITLE":
            dur = 2.4
        elif "CONTINUED" in line:
            dur = 2.8
        else:
            dur = 2.2
        events.append(
            {
                "i": i,
                "speaker": speaker,
                "direction": direction,
                "line": line,
                "start": t,
                "dur": dur,
                "wav": wav,
                "focus": focus_for(speaker, i),
            }
        )
        t += dur
    return events


def mix_audio(events: list[dict], total: float) -> Path:
    # Build silence bed then overlay each line at start time
    bed = AUDIO / "bed.wav"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=mono",
            "-t",
            f"{total:.3f}",
            str(bed),
        ]
    )

    # Filter complex amix
    inputs = ["-i", str(bed)]
    filter_parts = []
    idx = 1
    for ev in events:
        if not ev["wav"]:
            continue
        inputs += ["-i", str(ev["wav"])]
        delay_ms = int(ev["start"] * 1000)
        filter_parts.append(f"[{idx}]adelay={delay_ms}|{delay_ms},volume=1.0[a{idx}]")
        idx += 1

    out = AUDIO / "mix.wav"
    if idx == 1:
        shutil.copy(bed, out)
        return out

    n = idx
    mix_inputs = "[0]" + "".join(f"[a{i}]" for i in range(1, n))
    filter_parts.append(f"{mix_inputs}amix=inputs={n}:duration=first:dropout_transition=0,volume={n * 0.9}[out]")
    fc = ";".join(filter_parts)
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "[out]", str(out)]
    run(cmd)
    return out


def render_frames(events: list[dict], base: Image.Image) -> float:
    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)

    total = events[-1]["start"] + events[-1]["dur"]
    nframes = int(total * FPS)
    frame_i = 0
    for f in range(nframes):
        t = f / FPS
        # Find active event
        ev = events[-1]
        for e in events:
            if e["start"] <= t < e["start"] + e["dur"]:
                ev = e
                break
        local_t = t - ev["start"]
        still = ken_burns(base, local_t, ev["dur"], ev["focus"])
        framed = draw_caption(still, ev["speaker"], ev["direction"], ev["line"])
        framed.save(FRAMES / f"frame_{frame_i:05d}.png")
        frame_i += 1
        if frame_i % 48 == 0:
            print(f"  frames {frame_i}/{nframes}")
    return total


def encode(total: float, mix: Path) -> None:
    OUT_REPO.parent.mkdir(parents=True, exist_ok=True)
    tmp = WORK / "out.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(FRAMES / "frame_%05d.png"),
            "-i",
            str(mix),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(tmp),
        ]
    )
    shutil.copy2(tmp, OUT_ARTIFACT)
    shutil.copy2(tmp, OUT_REPO)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    print("Synthesizing dialogue…")
    events = build_timeline()
    for ev in events:
        print(f"  [{ev['start']:5.1f}s] {ev['speaker']}: {ev['line'][:60]}…")

    print("Mixing audio…")
    total = events[-1]["start"] + events[-1]["dur"]
    mix = mix_audio(events, total)

    print("Rendering frames…")
    base = load_scene()
    total = render_frames(events, base)

    print("Encoding…")
    encode(total, mix)
    print(f"Done → {OUT_ARTIFACT}")
    print(f"Repo  → {OUT_REPO}")


if __name__ == "__main__":
    main()
