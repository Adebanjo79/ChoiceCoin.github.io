#!/usr/bin/env python3
"""1-Click AI Shorts Generator — Mosquito Evacuation.

Usage:
  python generate.py              # full pipeline (demo if no API keys)
  python generate.py --prompts    # only export scene prompts
  python generate.py --demo       # force local demo rendering
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("generate")


def main() -> int:
    parser = argparse.ArgumentParser(description="1-Click AI Shorts Generator")
    parser.add_argument("--prompts", action="store_true", help="Export prompt pack only")
    parser.add_argument("--demo", action="store_true", help="Force DEMO_MODE=1")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Final MP4 path (default: output/mosquito_evacuation_short.mp4)",
    )
    args = parser.parse_args()

    if args.demo:
        os.environ["DEMO_MODE"] = "1"
        # Reload config flags after env change
        import importlib
        import config

        importlib.reload(config)

    from config import DEMO_MODE, OUTPUT_DIR
    from src.scenes import SCENES, export_prompts_markdown, total_duration
    from src.video_gen import generate_all_clips, write_prompt_pack
    from src.voiceover import generate_voiceover
    from src.editor import assemble
    from src.sfx import ensure_background_music, ensure_sfx

    print("=" * 60)
    print("  1-CLICK AI SHORTS GENERATOR")
    print("  Title: Mosquito Evacuation")
    print(f"  Scenes: {len(SCENES)} | Target: {total_duration():.1f}s | 1080x1920")
    print(f"  Mode: {'DEMO (local)' if DEMO_MODE else 'PRODUCTION (APIs)'}")
    print("=" * 60)

    prompt_path = write_prompt_pack(OUTPUT_DIR / "SCENE_PROMPTS.md")
    # Also mirror to project root for easy reading
    (ROOT / "SCENE_PROMPTS.md").write_text(export_prompts_markdown(), encoding="utf-8")
    log.info("Prompt pack → %s", prompt_path)

    if args.prompts:
        print(export_prompts_markdown())
        return 0

    ensure_sfx()
    ensure_background_music()

    log.info("[1/3] Generating voiceover…")
    vo_path = generate_voiceover(OUTPUT_DIR / "voiceover.mp3")

    log.info("[2/3] Generating scene clips (Pika/Runway or demo)…")
    clips = generate_all_clips(SCENES)

    log.info("[3/3] Editing final Short…")
    out = assemble(clips, vo_path, args.out or (OUTPUT_DIR / "mosquito_evacuation_short.mp4"))

    print()
    print("✅ DONE")
    print(f"   Video:      {out}")
    print(f"   Voiceover:  {vo_path}")
    print(f"   Prompts:    {prompt_path}")
    print(f"   Clips:      {OUTPUT_DIR / 'clips'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())