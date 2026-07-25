"""ElevenLabs voiceover (Adam) with edge-tts fallback."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import List, Tuple

import requests

from config import DEMO_MODE, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, OUTPUT_DIR
from src.scenes import SCENES, Scene

log = logging.getLogger(__name__)

# Word timings approximate: (word, start, end)
WordTiming = Tuple[str, float, float]


def _full_script(scenes: List[Scene] | None = None) -> str:
    scenes = scenes or SCENES
    parts = []
    for scene in scenes:
        parts.extend(scene.dialogue)
    # Keep the comedy punchy — dialogue only for VO track
    return " ".join(parts)


def generate_voiceover(out_path: Path | None = None) -> Path:
    """Generate voiceover.mp3 via ElevenLabs Adam, or edge-tts in demo mode.

    Builds a timeline-aligned mix: each scene's dialogue starts at that scene's
    offset so VO spans the full Short instead of finishing early.
    """
    out_path = out_path or (OUTPUT_DIR / "voiceover.mp3")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    scene_paths = generate_scene_voiceovers()
    _mix_scene_voiceovers(scene_paths, out_path)

    log.info("Voiceover written: %s", out_path)
    return out_path


def _mix_scene_voiceovers(scene_paths: List[Path], out_path: Path) -> None:
    """Place each scene VO at its scene start time → single voiceover.mp3."""
    import subprocess
    from src.scenes import SCENES

    # Build ffmpeg amix with adelay per scene
    inputs: list[str] = []
    filters: list[str] = []
    for i, (path, scene) in enumerate(zip(scene_paths, SCENES)):
        inputs.extend(["-i", str(path)])
        delay_ms = int(sum(s.duration for s in SCENES[:i]) * 1000)
        # adelay wants ms per channel
        filters.append(f"[{i}:a]adelay={delay_ms}|{delay_ms},volume=1.0[a{i}]")
    mix_inputs = "".join(f"[a{i}]" for i in range(len(scene_paths)))
    total = sum(s.duration for s in SCENES)
    filter_complex = ";".join(filters) + (
        f";{mix_inputs}amix=inputs={len(scene_paths)}:duration=longest:normalize=0,"
        f"apad=whole_dur={total:.3f}"
    )
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-t", f"{total:.3f}",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _elevenlabs_tts(text: str, out_path: Path) -> None:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.35,
            "similarity_boost": 0.85,
            "style": 0.75,
            "use_speaker_boost": True,
        },
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    out_path.write_bytes(resp.content)

    # Optional timestamps for captions
    align_url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/with-timestamps"
    )
    align = requests.post(align_url, headers={**headers, "Accept": "application/json"}, json=payload, timeout=120)
    if align.ok:
        (OUTPUT_DIR / "voiceover_alignment.json").write_text(align.text, encoding="utf-8")


async def _edge_tts(text: str, out_path: Path) -> None:
    import edge_tts

    # Excited male English voice (Adam-like energy)
    voice = "en-US-ChristopherNeural"
    communicate = edge_tts.Communicate(text, voice=voice, rate="+18%", pitch="+4Hz")
    await communicate.save(str(out_path))


def build_word_timings(
    scenes: List[Scene] | None = None,
    total_audio_duration: float | None = None,
) -> List[WordTiming]:
    """Distribute words across the timeline for caption highlighting.

    Prefers ElevenLabs alignment JSON when present; otherwise estimates
    from scene durations.
    """
    scenes = scenes or SCENES
    align_path = OUTPUT_DIR / "voiceover_alignment.json"
    if align_path.exists():
        try:
            data = json.loads(align_path.read_text(encoding="utf-8"))
            # with-timestamps returns alignment.characters or normalized_alignment
            words: List[WordTiming] = []
            norm = data.get("normalized_alignment") or data.get("alignment") or {}
            chars = norm.get("characters") or []
            starts = norm.get("character_start_times_seconds") or []
            ends = norm.get("character_end_times_seconds") or []
            if chars and starts and ends:
                buf = ""
                w_start = None
                for ch, s, e in zip(chars, starts, ends):
                    if ch.isspace():
                        if buf and w_start is not None:
                            words.append((buf, w_start, e))
                            buf = ""
                            w_start = None
                        continue
                    if w_start is None:
                        w_start = s
                    buf += ch
                if buf and w_start is not None:
                    words.append((buf, w_start, ends[-1] if ends else w_start + 0.2))
                if words:
                    return words
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not parse alignment: %s", exc)

    # Estimate from scene dialogue + durations
    words: List[WordTiming] = []
    t = 0.0
    for scene in scenes:
        dialogue = " ".join(scene.dialogue)
        tokens = [w for w in dialogue.replace("!!", "!").split() if w]
        if not tokens:
            t += scene.duration
            continue
        # Leave small head/tail padding in each scene
        usable = max(scene.duration - 0.6, 1.0)
        slot = usable / len(tokens)
        cursor = t + 0.25
        for tok in tokens:
            words.append((tok, cursor, cursor + slot * 0.92))
            cursor += slot
        t += scene.duration

    if total_audio_duration and words:
        scale = total_audio_duration / max(words[-1][2], 0.01)
        words = [(w, s * scale, e * scale) for w, s, e in words]
    return words


def generate_scene_voiceovers(out_dir: Path | None = None) -> List[Path]:
    """Per-scene VO files for timeline-aligned mix."""
    out_dir = out_dir or (OUTPUT_DIR / "vo_scenes")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    use_eleven = bool(ELEVENLABS_API_KEY) and not DEMO_MODE
    if not use_eleven:
        log.warning("Using edge-tts fallback (set ELEVENLABS_API_KEY for Adam).")
    for scene in SCENES:
        path = out_dir / f"scene_{scene.id:02d}.mp3"
        text = " ".join(scene.dialogue)
        if path.exists() and path.stat().st_size > 1000:
            paths.append(path)
            continue
        if use_eleven:
            _elevenlabs_tts(text, path)
        else:
            asyncio.run(_edge_tts(text, path))
        paths.append(path)
    return paths