# 1-Click AI Shorts Generator — *Mosquito Evacuation*

Turn the comedy script **Mosquito Evacuation** into a hyper-realistic **9:16** Shorts video (1080×1920, ~35–40s).

## What it does

1. **Scene breakdown** — 4 scenes, each with **2 Pika 1.5 / Runway Gen-3 prompts** (gas-mask mosquitoes, green toxic fog, window escape).
2. **Voiceover** — ElevenLabs **Adam** (excited/comedic) → `output/voiceover.mp3` (falls back to `edge-tts` without a key).
3. **Video clips** — Pika or Runway API, **8–10s per scene**.
4. **Edit (MoviePy + FFmpeg)** — stitch → VO → word-by-word captions (Montserrat ExtraBold, yellow + black stroke) → SFX (siren/fart/buzz/whoosh) → BGM at **-18 dB** → export **1080p vertical**.

## Quick start

```bash
cd ai-shorts-generator
python3 -m pip install -r requirements.txt
cp .env.example .env   # add keys for production
python generate.py     # 1-click
```

Force offline demo (no API keys):

```bash
python generate.py --demo
```

Export prompts only:

```bash
python generate.py --prompts
```

## API keys (`.env`)

| Variable | Purpose |
|----------|---------|
| `ELEVENLABS_API_KEY` | Adam voiceover |
| `ELEVENLABS_VOICE_ID` | Default `pNInz6obpgDQGcFmaJgB` (Adam) |
| `PIKA_API_KEY` | Pika 1.5 clips (preferred) |
| `RUNWAY_API_KEY` | Runway Gen-3 fallback |

Without keys, the pipeline still runs end-to-end in **DEMO** mode (local cinematic stand-in clips + neural TTS).

## Music

Place a bed track in `music/` (or `/music`). If none exists, a placeholder comedy loop is generated. Mixed at **-18 dB**.

## Outputs

```
output/
  SCENE_PROMPTS.md
  voiceover.mp3
  clips/scene_01_*.mp4 …
  mosquito_evacuation_short.mp4
```

## Script

**Title:** Mosquito Evacuation  
**Text:** `POV: You ate beans yesterday`