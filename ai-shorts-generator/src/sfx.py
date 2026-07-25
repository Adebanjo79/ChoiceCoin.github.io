"""Generate comedy SFX + background music bed with ffmpeg."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Dict

from config import MUSIC_DIR, SFX_DIR

log = logging.getLogger(__name__)


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ensure_sfx() -> Dict[str, Path]:
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "siren": SFX_DIR / "siren.wav",
        "fart": SFX_DIR / "fart.wav",
        "buzzing": SFX_DIR / "buzzing.wav",
        "whoosh": SFX_DIR / "whoosh.wav",
    }
    if not paths["siren"].exists():
        # Alternating siren tones
        _run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "sine=frequency=780:duration=1.2",
            "-f", "lavfi",
            "-i", "sine=frequency=980:duration=1.2",
            "-filter_complex",
            "[0][1]concat=n=2:v=0:a=1,volume=0.55",
            str(paths["siren"]),
        ])
    if not paths["fart"].exists():
        # Low rumble burst
        _run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anoisesrc=color=brown:amplitude=0.6:duration=0.55",
            "-af", "lowpass=f=180,vibrato=f=8:d=0.6,volume=1.4",
            str(paths["fart"]),
        ])
    if not paths["buzzing"].exists():
        _run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "sine=frequency=240:duration=2.5",
            "-af", "tremolo=f=55:d=0.8,volume=0.35",
            str(paths["buzzing"]),
        ])
    if not paths["whoosh"].exists():
        _run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anoisesrc=color=white:amplitude=0.4:duration=0.7",
            "-af", "highpass=f=800,afade=t=in:st=0:d=0.05,afade=t=out:st=0.35:d=0.35,volume=0.8",
            str(paths["whoosh"]),
        ])
    return paths


def ensure_background_music() -> Path:
    """Ensure a comedy bed exists under music/ (or /music)."""
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    candidates = (
        list(MUSIC_DIR.glob("*.mp3"))
        + list(MUSIC_DIR.glob("*.wav"))
        + list(MUSIC_DIR.glob("*.m4a"))
    )
    preferred = MUSIC_DIR / "background.mp3"
    if preferred.exists():
        return preferred
    if candidates:
        return candidates[0]

    # Generate a light comedic loop: two alternating chords via sine mix
    log.info("Generating placeholder comedy BGM at %s", preferred)
    _run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=261.63:duration=40",
        "-f", "lavfi",
        "-i", "sine=frequency=329.63:duration=40",
        "-f", "lavfi",
        "-i", "sine=frequency=392.00:duration=40",
        "-filter_complex",
        "[0]volume=0.12[a];[1]volume=0.10,atrim=0:40,adelay=500|500[b];"
        "[2]volume=0.08,atrim=0:40,adelay=1000|1000[c];"
        "[a][b][c]amix=inputs=3:duration=longest,"
        "tremolo=f=2:d=0.25,afade=t=in:st=0:d=1,afade=t=out:st=38:d=2",
        str(preferred),
    ])
    return preferred