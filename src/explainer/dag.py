"""The DAG: stage specs, beat expansion, dependency resolution (PRD §5.3, §6.2).

Granularity is the BEAT, never the video. A beat-scoped stage becomes N nodes.
node_key is "script:b03" for beat nodes and "assembly" for video nodes.

Four dependency kinds cover every edge in the PRD's 13-stage pipeline:

  VIDEO           beat or video node  -> one video-scoped node   (script <- research)
  SAME_BEAT       beat node           -> same beat's node        (tts:b03 <- script:b03)
  ALL_BEATS       video node          -> every beat's node       (assembly <- render:*)
  NEIGHBOR_BEATS  beat node           -> beat n-1, n, n+1        (pacing(6,7,8), §5.3)

Everything else in the pipeline is a composition of those four.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Scope(str, Enum):
    VIDEO = "video"
    BEAT = "beat"


class Pool(str, Enum):
    AGENT = "agent"    # I/O-bound LLM + vision calls, cheap to scale
    RENDER = "render"  # CPU/GPU-bound Remotion + Chromium, the latency wall
    MEDIA = "media"    # short bursty FFmpeg / TTS / loudness work


class DepKind(str, Enum):
    VIDEO = "video"
    SAME_BEAT = "same_beat"
    ALL_BEATS = "all_beats"
    NEIGHBOR_BEATS = "neighbor_beats"


@dataclass(frozen=True)
class Dep:
    stage: str
    kind: DepKind
    window: int = 1          # NEIGHBOR_BEATS only
    optional: bool = False   # missing upstream is tolerated (e.g. skipped beat)


@dataclass(frozen=True)
class StageSpec:
    key: str
    scope: Scope
    pool: Pool
    tier: str = "code"                    # frontier|mid|vision|code|tts (§9.6)
    deps: tuple[Dep, ...] = ()
    prompt: str | None = None             # prompts/<name>.md, versioned in git
    config_keys: tuple[str, ...] = ()     # which config values legitimately
                                          # affect this stage's output
    reads_beat_inputs: bool = False       # beat brief enters the closure here
    video_input_keys: tuple[str, ...] = ()  # video-level fields this stage reads
                                          # (title, inputs.topic, …). Declaring
                                          # them is what puts them in the hash.
    whole_video: bool = False             # §5.5 global-scope exception
    implemented: bool = True
    mime: str = "application/json"
    description: str = ""

    @property
    def is_beat(self) -> bool:
        return self.scope is Scope.BEAT


@dataclass(frozen=True)
class Node:
    stage: str
    beat_id: str | None
    ordinal: int | None = None

    @property
    def key(self) -> str:
        return f"{self.stage}:{self.beat_id}" if self.beat_id else self.stage


@dataclass
class Graph:
    name: str
    stages: dict[str, StageSpec]
    # In the production pipeline the beat list is itself an OUTPUT (of the script
    # stage). resolve() therefore runs in two passes: everything up to and
    # including this stage, then re-resolve once beat rows exist. See CLAUDE.md.
    beat_producer: str | None = None
    terminal: str | None = None
    _order: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._order = topological_stages(self.stages)
        if self.terminal is None and self._order:
            self.terminal = self._order[-1]

    def stage(self, key: str) -> StageSpec:
        try:
            return self.stages[key]
        except KeyError:
            raise KeyError(f"unknown stage '{key}' in graph '{self.name}'") from None

    @property
    def order(self) -> list[str]:
        return list(self._order)

    def upto(self, target: str) -> list[str]:
        """Stage keys needed to reach `target`, in topological order."""
        self.stage(target)
        needed: set[str] = set()

        def walk(k: str) -> None:
            if k in needed:
                return
            needed.add(k)
            for d in self.stage(k).deps:
                walk(d.stage)

        walk(target)
        return [k for k in self._order if k in needed]


def topological_stages(stages: dict[str, StageSpec]) -> list[str]:
    """Kahn, with a deterministic tie-break on declaration order."""
    decl = {k: i for i, k in enumerate(stages)}
    indeg = {k: 0 for k in stages}
    children: dict[str, list[str]] = {k: [] for k in stages}
    for k, spec in stages.items():
        for d in spec.deps:
            if d.stage == k:
                raise ValueError(f"stage '{k}' depends on itself")
            if d.stage not in stages:
                raise ValueError(f"stage '{k}' depends on unknown stage '{d.stage}'")
            children[d.stage].append(k)
            indeg[k] += 1
    ready = sorted([k for k, v in indeg.items() if v == 0], key=lambda k: decl[k])
    out: list[str] = []
    while ready:
        k = ready.pop(0)
        out.append(k)
        for c in children[k]:
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
                ready.sort(key=lambda k: decl[k])
    if len(out) != len(stages):
        cyc = sorted(set(stages) - set(out))
        raise ValueError(f"cycle in graph involving: {cyc}")
    return out


@dataclass(frozen=True)
class BeatRef:
    beat_id: str
    ordinal: int
    inputs: dict
    locked: bool = False


def expand(graph: Graph, beats: list[BeatRef], target: str | None = None) -> list[Node]:
    """All nodes needed to reach `target`, in a valid execution order."""
    stage_keys = graph.upto(target) if target else graph.order
    ordered_beats = sorted(beats, key=lambda b: b.ordinal)
    nodes: list[Node] = []
    for sk in stage_keys:
        spec = graph.stage(sk)
        if spec.is_beat:
            nodes.extend(Node(sk, b.beat_id, b.ordinal) for b in ordered_beats)
        else:
            nodes.append(Node(sk, None))
    return nodes


def dependencies(graph: Graph, node: Node, beats: list[BeatRef]) -> dict[str, Node]:
    """Resolve one node's dependencies to labelled upstream nodes.

    Labels are stable and enter the hash closure, so 'prev'/'next' matter: a beat
    whose neighbours change order gets a different hash, which is correct — its
    pacing and transitions genuinely differ.
    """
    spec = graph.stage(node.stage)
    by_ord = {b.ordinal: b for b in beats}
    ordered = sorted(beats, key=lambda b: b.ordinal)
    out: dict[str, Node] = {}

    for d in spec.deps:
        upstream = graph.stage(d.stage)
        if d.kind is DepKind.VIDEO:
            if upstream.is_beat:
                raise ValueError(f"{node.key}: VIDEO dep on beat-scoped stage '{d.stage}'")
            out[d.stage] = Node(d.stage, None)

        elif d.kind is DepKind.SAME_BEAT:
            if not spec.is_beat or not upstream.is_beat:
                raise ValueError(f"{node.key}: SAME_BEAT dep requires both stages beat-scoped")
            out[d.stage] = Node(d.stage, node.beat_id, node.ordinal)

        elif d.kind is DepKind.ALL_BEATS:
            if spec.is_beat:
                raise ValueError(f"{node.key}: ALL_BEATS dep is only valid on a video-scoped stage")
            for b in ordered:
                out[f"{d.stage}:{b.beat_id}"] = Node(d.stage, b.beat_id, b.ordinal)

        elif d.kind is DepKind.NEIGHBOR_BEATS:
            if not spec.is_beat or not upstream.is_beat:
                raise ValueError(f"{node.key}: NEIGHBOR_BEATS requires both stages beat-scoped")
            assert node.ordinal is not None
            for off in range(-d.window, d.window + 1):
                nb = by_ord.get(node.ordinal + off)
                if nb is None:
                    continue  # ends of the video have fewer neighbours
                label = {0: "self"}.get(off, f"{'prev' if off < 0 else 'next'}{abs(off)}")
                out[f"{d.stage}:{label}"] = Node(d.stage, nb.beat_id, nb.ordinal)

    return out
