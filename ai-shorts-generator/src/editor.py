"""MoviePy + FFmpeg edit: stitch, VO, captions, SFX, music → 1080x1920."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    VideoFileClip,
    concatenate_videoclips,
    vfx,
)

from config import FPS, HEIGHT, MUSIC_DB, OUTPUT_DIR, WIDTH
from src.captions import compose_with_captions
from src.scenes import SCENES, Scene
from src.sfx import ensure_background_music, ensure_sfx
from src.voiceover import build_word_timings

log = logging.getLogger(__name__)


def _fit_vertical(clip: VideoFileClip, duration: float) -> VideoFileClip:
    """Force 9:16 1080x1920 and exact scene duration."""
    clip = clip.without_audio() if clip.audio is not None else clip
    # Resize covering the frame then crop center
    w, h = clip.size
    target_aspect = WIDTH / HEIGHT
    aspect = w / h
    if aspect > target_aspect:
        # too wide
        new_h = HEIGHT
        new_w = int(w * (HEIGHT / h))
    else:
        new_w = WIDTH
        new_h = int(h * (WIDTH / w))
    clip = clip.resized(new_size=(new_w, new_h))
    clip = clip.cropped(
        x_center=clip.w / 2,
        y_center=clip.h / 2,
        width=WIDTH,
        height=HEIGHT,
    )
    if clip.duration < duration:
        clip = clip.with_effects([vfx.Loop(duration=duration)])
    clip = clip.subclipped(0, duration)
    return clip.with_fps(FPS)


def stitch_scenes(clip_paths: List[Path], scenes: List[Scene] | None = None) -> VideoFileClip:
    scenes = scenes or SCENES
    parts = []
    for path, scene in zip(clip_paths, scenes):
        raw = VideoFileClip(str(path))
        parts.append(_fit_vertical(raw, scene.duration))
    return concatenate_videoclips(parts, method="compose")


def _db_to_factor(db: float) -> float:
    return 10 ** (db / 20.0)


def build_sfx_track(total_duration: float, scenes: List[Scene] | None = None) -> CompositeAudioClip:
    scenes = scenes or SCENES
    sfx = ensure_sfx()
    clips = []
    t = 0.0
    for scene in scenes:
        # Cue map relative to scene start
        schedule = {
            "fart": 0.15,
            "siren": 0.4,
            "buzzing": 0.8,
            "whoosh": 1.6,
        }
        for name in scene.sfx_cues:
            path = sfx.get(name)
            if not path or not path.exists():
                continue
            ac = AudioFileClip(str(path)).with_start(t + schedule.get(name, 0.2))
            # Keep SFX shorter than remaining scene
            if ac.duration > scene.duration - 0.1:
                ac = ac.subclipped(0, scene.duration - 0.1)
            vol = 0.45 if name != "buzzing" else 0.25
            ac = ac.with_volume_scaled(vol)
            clips.append(ac)
        t += scene.duration
    return CompositeAudioClip(clips).with_duration(total_duration)


def assemble(
    clip_paths: List[Path],
    voiceover_path: Path,
    out_path: Path | None = None,
) -> Path:
    """Full edit pipeline → final Shorts MP4 at 1080x1920."""
    out_path = out_path or (OUTPUT_DIR / "mosquito_evacuation_short.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    video = stitch_scenes(clip_paths)
    timings = build_word_timings(total_audio_duration=None)
    video = compose_with_captions(video, timings)

    vo = AudioFileClip(str(voiceover_path))
    # Stretch/pad VO to video length if needed
    if vo.duration < video.duration:
        # leave natural end silence by composing with delayed silence via start only
        vo_fitted = vo
    else:
        vo_fitted = vo.subclipped(0, video.duration)

    music_path = ensure_background_music()
    music = AudioFileClip(str(music_path))
    if music.duration < video.duration:
        loops = int(video.duration // music.duration) + 1
        from moviepy import concatenate_audioclips

        music = concatenate_audioclips([music] * loops)
    music = music.subclipped(0, video.duration).with_volume_scaled(_db_to_factor(MUSIC_DB))

    sfx_track = build_sfx_track(video.duration)

    final_audio = CompositeAudioClip([
        music,
        sfx_track,
        vo_fitted.with_volume_scaled(1.15),
    ]).with_duration(video.duration)

    final = video.with_audio(final_audio)

    tmp_path = out_path.with_suffix(".tmp.mp4")
    final.write_videofile(
        str(tmp_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        logger="bar",
    )

    # Final FFmpeg normalize to exact 1080x1920 yuv420p for Shorts
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(tmp_path),
            "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                   f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}",
            "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(out_path),
        ],
        check=True,
    )
    tmp_path.unlink(missing_ok=True)

    # Cleanup
    final.close()
    video.close()
    vo.close()
    music.close()

    log.info("Exported Short: %s (%.1fs)", out_path, _probe_duration(out_path))
    return out_path


def _probe_duration(path: Path) -> float:
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            text=True,
        ).strip()
        return float(out)
    except Exception:  # noqa: BLE001
        return -1.0