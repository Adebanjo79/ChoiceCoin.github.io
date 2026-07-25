"""Scene breakdown + hyper-realistic Pika 1.5 / Runway Gen-3 prompts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from config import STYLE_SUFFIX


@dataclass
class Scene:
    id: int
    slug: str
    location: str
    duration: float
    dialogue: List[str]
    voiceover_text: str
    caption_lines: List[str]
    prompts: List[str] = field(default_factory=list)
    sfx_cues: List[str] = field(default_factory=list)


SCENES: List[Scene] = [
    Scene(
        id=1,
        slug="toilet_code_red",
        location="INT. TOILET - DAY",
        duration=9.0,
        dialogue=[
            "CODE RED! ABANDON SHIP!!",
        ],
        voiceover_text=(
            "Scene one. Inside a toilet. A green toxic smell cloud fills the room. "
            "Mosquito one panics: CODE RED! ABANDON SHIP!!"
        ),
        caption_lines=["CODE RED!", "ABANDON SHIP!!"],
        sfx_cues=["fart", "siren", "buzzing"],
        prompts=[
            (
                "Hyper-realistic Pixar-style 3D animation, 9:16 vertical. "
                "Interior dirty bathroom toilet bowl POV. Thick swirling green toxic fog "
                "pours up from the toilet like a biohazard cloud. A photorealistic mosquito "
                "with expressive panicked eyes and a tiny comedy gas mask flails its wings, "
                "alarm lights flashing red on its compound eyes. Dramatic volumetric lighting, "
                "particles of green mist, cinematic depth of field, comedic panic timing. "
                f"{STYLE_SUFFIX}"
            ),
            (
                "Close-up cinematic 3D shot, 9:16. Photorealistic mosquito wearing a tiny "
                "gas mask screams and rockets upward through green toxic bathroom fog, "
                "toilet porcelain and tile reflections below, red emergency vibe, motion blur "
                "on wings, Pixar emotional facial acting, 8k, dramatic rim light. "
                f"{STYLE_SUFFIX}"
            ),
        ],
    ),
    Scene(
        id=2,
        slug="window_escape",
        location="WINDOW LEDGE",
        duration=9.0,
        dialogue=[
            "I'm escaping too! That smell violated the Geneva Convention!",
        ],
        voiceover_text=(
            "Scene two. Window ledge. Mosquito two crashes in: "
            "I'm escaping too! That smell violated the Geneva Convention!"
        ),
        caption_lines=[
            "I'm escaping too!",
            "That smell violated the Geneva Convention!",
        ],
        sfx_cues=["whoosh", "buzzing", "fart"],
        prompts=[
            (
                "Cinematic 3D animation, 9:16 vertical. Bathroom window ledge escape route. "
                "Bright daylight outside, green toxic fog leaking from the dark bathroom behind. "
                "A second photorealistic mosquito with a tiny comedy gas mask crash-lands onto "
                "the window sill in a comedic tumble, wings buzzing wildly, Pixar-style "
                "expressive face mid-yell. Photoreal insect detail, dramatic lighting, 8k. "
                f"{STYLE_SUFFIX}"
            ),
            (
                "Dynamic tracking shot, 9:16. Mosquito with tiny gas mask bursts through a "
                "half-open bathroom window onto the ledge, green poison mist trailing behind, "
                "city daylight outside, comedic timing, photorealistic Pixar 3D, motion streaks, "
                "heroic escape energy. "
                f"{STYLE_SUFFIX}"
            ),
        ],
    ),
    Scene(
        id=3,
        slug="free_buffet",
        location="OUTSIDE WINDOW",
        duration=9.5,
        dialogue=[
            "Yo why are y'all leaving? Free buffet!",
            "DON'T GO IN THERE!! That man is pooing again.",
        ],
        voiceover_text=(
            "Scene three. Outside the window. Mosquito three flies in: "
            "Yo why are y'all leaving? Free buffet! "
            "Mosquito one and two scream: DON'T GO IN THERE!! That man is pooing again."
        ),
        caption_lines=[
            "Yo why are y'all leaving?",
            "Free buffet!",
            "DON'T GO IN THERE!!",
            "That man is pooing again.",
        ],
        sfx_cues=["buzzing", "whoosh", "siren"],
        prompts=[
            (
                "Outside bathroom window, 9:16 vertical cinematic 3D. Three photorealistic "
                "mosquitoes with tiny comedy gas masks. Mosquito 3 approaches cheerfully from "
                "fresh air toward the green-fog bathroom window, naive grin. Mosquito 1 and 2 "
                "on the ledge wave frantically, blocking him, Pixar expressive panic faces, "
                "dramatic lighting, photoreal textures, comedic timing. "
                f"{STYLE_SUFFIX}"
            ),
            (
                "Reaction shot montage energy in one continuous 9:16 shot. Excited mosquito "
                "with gas mask flies toward toxic green bathroom window saying free buffet vibe, "
                "while two masked mosquitoes scream and point away from the window, green fog "
                "billowing out, hyper-realistic Pixar style, 8k, slapstick comedy framing. "
                f"{STYLE_SUFFIX}"
            ),
        ],
    ),
    Scene(
        id=4,
        slug="dumpster_finale",
        location="FINAL / OUTSIDE",
        duration=10.0,
        dialogue=[
            "I grew up in a dumpster. I LIKE where poo smells... but THIS wants to suffocate me!",
        ],
        voiceover_text=(
            "Final scene. Mosquito one: I grew up in a dumpster. I LIKE where poo smells... "
            "but THIS wants to suffocate me! All mosquitoes fly away. "
            "Text on screen: POV: You ate beans yesterday."
        ),
        caption_lines=[
            "I grew up in a dumpster.",
            "I LIKE where poo smells...",
            "but THIS wants to suffocate me!",
            "POV: You ate beans yesterday",
        ],
        sfx_cues=["buzzing", "whoosh", "fart"],
        prompts=[
            (
                "Final cinematic wide 9:16 vertical. Outside under a window, green toxic fog "
                "still oozing from the bathroom. Mosquito 1 with tiny gas mask delivers an "
                "emotional monologue face, nostalgic dumpster childhood flash subtle in "
                "background bokeh, then all three photorealistic mosquitoes with gas masks "
                "rocket away into the sky. Pixar emotional comedy, dramatic sunset rim light, 8k. "
                f"{STYLE_SUFFIX}"
            ),
            (
                "End-card energy shot, 9:16. Three gas-masked photorealistic mosquitoes flee "
                "the toxic green bathroom window into open sky, trailing comic speed lines, "
                "bold readable space in lower third for text 'POV: You ate beans yesterday', "
                "cinematic Pixar 3D, photorealistic, dramatic lighting, comedic timing. "
                f"{STYLE_SUFFIX}"
            ),
        ],
    ),
]


def total_duration(scenes: List[Scene] | None = None) -> float:
    scenes = scenes or SCENES
    return sum(s.duration for s in scenes)


def export_prompts_markdown() -> str:
    lines = ["# Mosquito Evacuation — Scene Prompts\n"]
    for scene in SCENES:
        lines.append(f"## Scene {scene.id}: {scene.location}")
        lines.append(f"- **Slug:** `{scene.slug}`")
        lines.append(f"- **Duration:** {scene.duration}s")
        lines.append(f"- **Dialogue:** {' | '.join(scene.dialogue)}")
        lines.append("")
        for i, prompt in enumerate(scene.prompts, 1):
            lines.append(f"### Prompt {i} (Pika 1.5 / Runway Gen-3)")
            lines.append("```")
            lines.append(prompt)
            lines.append("```")
            lines.append("")
    lines.append(f"**Total runtime target:** {total_duration():.1f}s (35–40s)\n")
    return "\n".join(lines)