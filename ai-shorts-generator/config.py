"""Runtime configuration for the 1-Click AI Shorts Generator."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# Paths — prefer project music/, fall back to /music as specified
PROJECT_MUSIC = ROOT / "music"
SYSTEM_MUSIC = Path("/music")
MUSIC_DIR = Path(os.getenv("MUSIC_DIR", "")) if os.getenv("MUSIC_DIR") else (
    PROJECT_MUSIC if PROJECT_MUSIC.exists() else SYSTEM_MUSIC
)
if not MUSIC_DIR.exists():
    MUSIC_DIR = PROJECT_MUSIC
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)

ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
SFX_DIR = ASSETS / "sfx"
IMAGES = ASSETS / "images"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", ROOT / "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FONT_PATH = FONTS / "Montserrat-ExtraBold.ttf"

# Video
WIDTH = int(os.getenv("TARGET_WIDTH", "1080"))
HEIGHT = int(os.getenv("TARGET_HEIGHT", "1920"))
FPS = int(os.getenv("FPS", "30"))
SCENE_DURATION = 9.0  # 8–10s per scene → ~36s total
MUSIC_DB = -18.0

# APIs
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB").strip()
PIKA_API_KEY = os.getenv("PIKA_API_KEY", "").strip()
PIKA_API_BASE = os.getenv("PIKA_API_BASE", "https://api.pika.art/v1").rstrip("/")
RUNWAY_API_KEY = os.getenv("RUNWAY_API_KEY", "").strip()
RUNWAY_API_BASE = os.getenv("RUNWAY_API_BASE", "https://api.dev.runwayml.com/v1").rstrip("/")

_FORCE_DEMO = os.getenv("DEMO_MODE", "0").strip() in {"1", "true", "True", "yes"}
DEMO_MODE = _FORCE_DEMO or not (ELEVENLABS_API_KEY and (PIKA_API_KEY or RUNWAY_API_KEY))

STYLE_SUFFIX = (
    "cinematic 3D animation, photorealistic, Pixar style, 8k, dramatic lighting, "
    "9:16 vertical, comedic timing, hyper-detailed insect textures, expressive cartoon eyes, "
    "tiny comedy gas masks on mosquitoes"
)