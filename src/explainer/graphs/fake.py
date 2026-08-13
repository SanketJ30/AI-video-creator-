"""The Phase 1 fake pipeline (PRD §16, Phase 1 exit criteria).

    "Run a fake 4-stage pipeline over 5 fake beats. Change beat 3's input.
     Confirm: exactly beat 3's downstream artifacts re-run, everything else is a
     cache hit, byte-identical."

Four stages, no network, no models, fully deterministic:

    research  (video)  ──►  script (beat)  ──►  tts (beat)  ──►  assembly (video)
                                                     │
                                              pacing (beat, neighbours 6-7-8)
                                                     │
                                                 assembly

`pacing` is included because neighbour invalidation is the one edge shape that
is easy to get wrong and expensive to discover late. It is a fifth *node* type
over the four-stage spine, not a fifth stage of the real pipeline.
"""
from __future__ import annotations

from ..dag import Dep, DepKind, Graph, Pool, Scope, StageSpec

STAGES = {
    "research": StageSpec(
        key="research", scope=Scope.VIDEO, pool=Pool.AGENT, tier="code",
        config_keys=("locale",), video_input_keys=("title",),
        description="fake claim list derived from the video title",
    ),
    "script": StageSpec(
        key="script", scope=Scope.BEAT, pool=Pool.AGENT, tier="code",
        deps=(Dep("research", DepKind.VIDEO),),
        config_keys=("locale", "audience_level"),
        reads_beat_inputs=True,
        description="fake narration for one beat, from the beat brief",
    ),
    "tts": StageSpec(
        key="tts", scope=Scope.BEAT, pool=Pool.MEDIA, tier="code",
        deps=(Dep("script", DepKind.SAME_BEAT),),
        config_keys=("locale", "tts_voice", "tts_model"),
        mime="audio/wav",
        description="fake WAV whose length is a function of the narration",
    ),
    "pacing": StageSpec(
        key="pacing", scope=Scope.BEAT, pool=Pool.MEDIA, tier="code",
        deps=(Dep("tts", DepKind.NEIGHBOR_BEATS, window=1),),
        description="duration match + pause insert; reads beat n-1, n, n+1 (§5.3)",
    ),
    "assembly": StageSpec(
        key="assembly", scope=Scope.VIDEO, pool=Pool.MEDIA, tier="code",
        deps=(Dep("pacing", DepKind.ALL_BEATS),),
        whole_video=True,  # §5.5 — runtime and loudness are inherently global
        description="fake rough cut over every beat",
    ),
}

GRAPH = Graph(name="fake", stages=STAGES, terminal="assembly")
