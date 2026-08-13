"""The real pipeline (PRD §5). Declared in full, implemented incrementally.

Every stage here is already wired with the right scope, pool, tier, dependency
shape and config surface. Phases 2–8 are therefore "write a handler", never
"rewire the graph". `implemented=False` means there is no handler yet; the CLI
stops cleanly at the frontier of what is built and tells you what is next.

Two structural decisions worth understanding before you touch this file:

1. `script_plan` is video-scoped and produces the BEAT LIST; `script_beat` is
   beat-scoped and produces one beat's narration. This split is what makes
   §5.3's "editing beat 7 changes exactly one leaf hash" true. Beat briefs live
   in `beats.inputs` rows, NOT inside the plan artifact — if they lived in the
   plan, editing beat 7 would rehash the plan and invalidate all 12 beats.
   Gate A edits therefore write to `beats.inputs`.

2. `hook` is its own video-scoped node rather than part of `script_plan`, so
   choosing hook variant 2 over variant 1 does not invalidate twelve beats.

Brand only appears in `config_keys` for the four stages whose output actually
depends on it. That is what makes a `brand@1.2.0 → 1.3.0` sweep cheap (§5.4).
"""
from __future__ import annotations

from ..dag import Dep, DepKind, Graph, Pool, Scope, StageSpec

_ = False  # implemented flag, for readability below

STAGES = {
    # ---------------------------------------------------------------- [1] research
    "research": StageSpec(
        key="research", scope=Scope.VIDEO, pool=Pool.AGENT, tier="frontier",
        prompt="research", config_keys=("locale",),
        video_input_keys=("title", "topic", "angle"), implemented=_,
        description="claims + per-claim source, closed corpus (D10) → verified_facts.json",
    ),
    "fact_challenger": StageSpec(
        key="fact_challenger", scope=Scope.VIDEO, pool=Pool.AGENT, tier="frontier",
        deps=(Dep("research", DepKind.VIDEO),),
        prompt="fact_challenger", config_keys=("locale",), implemented=_,
        description="prompted to REFUTE each claim — asymmetric framing (§9.6)",
    ),

    # ------------------------------------------------- [2] instructional design
    "instructional_design": StageSpec(
        key="instructional_design", scope=Scope.VIDEO, pool=Pool.AGENT, tier="frontier",
        deps=(Dep("research", DepKind.VIDEO), Dep("fact_challenger", DepKind.VIDEO)),
        prompt="instructional_design",
        config_keys=("locale", "audience_level"),
        video_input_keys=("title", "topic", "target_minutes"), implemented=_,
        description="CTML-grounded lesson plan + objectives + CFU items (§11)",
    ),
    "pedagogy_critic": StageSpec(
        key="pedagogy_critic", scope=Scope.VIDEO, pool=Pool.AGENT, tier="mid",
        deps=(Dep("instructional_design", DepKind.VIDEO),),
        prompt="pedagogy_critic",
        config_keys=("locale", "audience_level"), implemented=_,
        description="load spikes, prerequisite gaps, framework misuse (parallel critic)",
    ),

    # ------------------------------------------------------------------ [3] script
    "script_plan": StageSpec(
        key="script_plan", scope=Scope.VIDEO, pool=Pool.AGENT, tier="mid",
        deps=(Dep("instructional_design", DepKind.VIDEO), Dep("pedagogy_critic", DepKind.VIDEO)),
        prompt="script_plan", config_keys=("locale", "audience_level"), implemented=_,
        description="beat list, ordering, roles, load budget. WRITES beats rows.",
    ),
    "hook": StageSpec(
        key="hook", scope=Scope.VIDEO, pool=Pool.AGENT, tier="mid",
        deps=(Dep("script_plan", DepKind.VIDEO),),
        prompt="hook", config_keys=("locale", "audience_level"), implemented=_,
        description="3 hook candidates + rubric scores; human picks at Gate A",
    ),
    "script_beat": StageSpec(
        key="script_beat", scope=Scope.BEAT, pool=Pool.AGENT, tier="mid",
        deps=(Dep("script_plan", DepKind.VIDEO),),
        prompt="script_beat", config_keys=("locale", "audience_level"),
        reads_beat_inputs=True, implemented=_,
        description="one beat's narration; lexicon applied; signaling flags",
    ),

    # -------------------------------------------------------------- [4] storyboard
    "storyboard": StageSpec(
        key="storyboard", scope=Scope.BEAT, pool=Pool.AGENT, tier="mid",
        deps=(Dep("script_beat", DepKind.SAME_BEAT),),
        prompt="storyboard",
        config_keys=("locale", "brand_version"), implemented=_,
        description="typed template selection, transition grammar, signaling map",
    ),
    "visual_critic": StageSpec(
        key="visual_critic", scope=Scope.BEAT, pool=Pool.AGENT, tier="vision",
        deps=(Dep("storyboard", DepKind.SAME_BEAT),),
        prompt="visual_critic",
        config_keys=("brand_version",), implemented=_,
        description="brand compliance, legibility, variety, signaling correctness",
    ),

    # --------------------------------------------------------------------- [5] tts
    "tts": StageSpec(
        key="tts", scope=Scope.BEAT, pool=Pool.MEDIA, tier="tts",
        deps=(Dep("script_beat", DepKind.SAME_BEAT),),
        config_keys=("locale", "tts_voice", "tts_model"), mime="audio/wav",
        implemented=_,
        description="pinned voice+model, lexicon.json applied, cached (§12.1)",
    ),

    # ------------------------------------------------------------------ [6] render
    "render": StageSpec(
        key="render", scope=Scope.BEAT, pool=Pool.RENDER, tier="vision",
        deps=(Dep("storyboard", DepKind.SAME_BEAT), Dep("visual_critic", DepKind.SAME_BEAT)),
        config_keys=("brand_version",), mime="video/mp4", implemented=_,
        description="Remotion, compile-repair ×3, keyframe visual verification (§13.2)",
    ),

    # ------------------------------------------------------------------ [7] pacing
    "pacing": StageSpec(
        key="pacing", scope=Scope.BEAT, pool=Pool.MEDIA, tier="code",
        deps=(Dep("tts", DepKind.NEIGHBOR_BEATS, window=1), Dep("render", DepKind.SAME_BEAT)),
        implemented=_,
        description="duration match + pause insertion. CODE, no model (§9.6)",
    ),

    # ------------------------------------------------------------- [8] sound design
    "sound_design": StageSpec(
        key="sound_design", scope=Scope.VIDEO, pool=Pool.MEDIA, tier="mid",
        deps=(Dep("pacing", DepKind.ALL_BEATS),),
        config_keys=("brand_version",), whole_video=True, implemented=_,
        description="licensed palette, ducking, SFX budget, −14 LUFS / −1 dBTP",
    ),

    # ---------------------------------------------------------------- [9] assembly
    "assembly": StageSpec(
        key="assembly", scope=Scope.VIDEO, pool=Pool.MEDIA, tier="code",
        deps=(Dep("sound_design", DepKind.VIDEO), Dep("render", DepKind.ALL_BEATS)),
        mime="video/mp4", whole_video=True, implemented=_,
        description="FFmpeg → rough_cut.mp4. Partial delivery allowed (§6.4)",
    ),

    # ------------------------------------------------------- [10] emergent reviewer
    "emergent_reviewer": StageSpec(
        key="emergent_reviewer", scope=Scope.VIDEO, pool=Pool.AGENT, tier="frontier",
        deps=(Dep("assembly", DepKind.VIDEO),),
        prompt="emergent_reviewer", whole_video=True, implemented=_,
        description="ONLY what needs a finished video: A/V sync, match, loudness (§13.4)",
    ),

    # ------------------------------------------------------------- [11] finishing
    "finishing": StageSpec(
        key="finishing", scope=Scope.VIDEO, pool=Pool.MEDIA, tier="vision",
        deps=(Dep("assembly", DepKind.VIDEO),
              Dep("emergent_reviewer", DepKind.VIDEO),
              Dep("hook", DepKind.VIDEO)),
        config_keys=("locale", "brand_version"), whole_video=True, implemented=_,
        description="3 thumbnails, styled captions, 16:9 + 9:16, transcript, sources",
    ),
}

# Stage [0] curriculum planner is series-scoped and human-owned — it is not a
# node in the per-video DAG. Stage [12] feedback runs post-publish and writes
# known_issues[] back into the next revision's Gate A.
GRAPH = Graph(name="production", stages=STAGES,
              beat_producer="script_plan", terminal="finishing")
