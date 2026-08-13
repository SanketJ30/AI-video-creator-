"""The orchestrator (PRD §6.2). A custom resolver over Postgres, not a workflow
engine — because content-addressed artifacts already solve durable execution:

    resolve(video_id, target_stage):
        dag = build_dag(video)
        for node in topological_order(dag):
            h = compute_hash(node)
            if artifact_exists(h) or beat_locked(node):
                mark_cached(node); continue
            enqueue(node, pool=node.pool, priority=video.priority)

The one insight that makes this work: because a node's hash is computed from its
INPUTS, every hash in the DAG is known before anything runs. So the whole plan
can be hashed and enqueued in a single pass, and "invalidation" is not a graph
walk that decides what to delete — it is the emergent consequence of a changed
input producing a hash that has no artifact behind it.

Retrofitting this after Phase 5 is a rewrite, not a refactor (§5.1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable

from . import db, prompts
from .codeversion import code_version_for_stage
from .config import settings
from .dag import BeatRef, Graph, Node, StageSpec, dependencies, expand
from .hashing import closure_hash
from .stages import base as stage_base
from .store import store

# ------------------------------------------------------------------ graph lookup

def graph_for(name: str) -> Graph:
    if name == "fake":
        from .graphs.fake import GRAPH
        from .stages import fake_handlers  # noqa: F401  (registers handlers)
        return GRAPH
    if name == "production":
        from .graphs.production import GRAPH
        try:
            from .stages import production_handlers  # noqa: F401
        except ImportError:
            pass
        return GRAPH
    raise KeyError(f"unknown graph '{name}' (expected 'fake' or 'production')")


# ------------------------------------------------------------------ video context

@dataclass
class VideoContext:
    series: dict
    video: dict
    beats: list[BeatRef]
    graph: Graph

    def refresh_beats(self, conn) -> None:
        """Re-read beat rows.

        Called after every beat mutation. A stale in-memory beat list silently
        hashes the OLD brief while Postgres holds the new one, so resolve()
        enqueues a hash that the next resolve() will not ask for — the artifact
        is built and immediately orphaned. Cheap read, whole class of bug gone.
        """
        rows = db.query(conn, "select * from beats where video_id = %s order by ordinal",
                        (self.video["id"],))
        self.beats = [BeatRef(r["beat_id"], r["ordinal"], r["inputs"], r["locked"])
                      for r in rows]

    @property
    def config_surface(self) -> dict:
        s = settings()
        return {
            "locale": self.series["locale"],
            "audience_level": self.series["audience_level"],
            "brand_version": self.video["brand_version"] or self.series["brand_version"],
            "tts_voice": s.models.tts_voice,
            "tts_model": s.models.tts_model,
        }


def load_video(conn, series_slug: str, video_id: str,
               graph_name: str | None = None) -> VideoContext:
    """Load a video and its beats. `graph_name` overrides the stored graph, which
    only tests and one-off migrations should need to do."""
    series = db.one(conn, "select * from series where slug = %s", (series_slug,))
    if not series:
        raise LookupError(f"no series '{series_slug}'")
    video = db.one(conn, "select * from videos where series_id = %s and video_id = %s",
                   (series["id"], video_id))
    if not video:
        raise LookupError(f"no video '{video_id}' in series '{series_slug}'")
    rows = db.query(conn, "select * from beats where video_id = %s order by ordinal", (video["id"],))
    beats = [BeatRef(beat_id=r["beat_id"], ordinal=r["ordinal"], inputs=r["inputs"],
                     locked=r["locked"]) for r in rows]
    return VideoContext(series=series, video=video, beats=beats,
                        graph=graph_for(graph_name or video["graph"]))


# ------------------------------------------------------------------------- plan

CACHED, LOCKED, QUEUED, UNIMPLEMENTED, BLOCKED = "cached", "locked", "queued", "unimplemented", "blocked"


@dataclass
class PlannedNode:
    node: Node
    spec: StageSpec
    hash: str
    upstream: dict[str, str]
    status: str
    prompt_version: str | None = None
    model_version: str | None = None
    code_version: str | None = None
    config: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return self.node.key

    def closure(self) -> dict:
        return {
            "upstream": self.upstream,
            "prompt_version": self.prompt_version,
            "model_version": self.model_version,
            "code_version": self.code_version,
            "config": self.config,
            "extra": self.extra,
        }


@dataclass
class Plan:
    ctx: VideoContext
    nodes: list[PlannedNode] = field(default_factory=list)
    needs_second_pass: bool = False
    target: str | None = None

    def by_key(self) -> dict[str, PlannedNode]:
        return {p.key: p for p in self.nodes}

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in self.nodes:
            out[p.status] = out.get(p.status, 0) + 1
        return out

    @property
    def cache_hit_rate(self) -> float:
        considered = [p for p in self.nodes if p.status in (CACHED, LOCKED, QUEUED)]
        if not considered:
            return 1.0
        hits = sum(1 for p in considered if p.status in (CACHED, LOCKED))
        return hits / len(considered)


def _locked_hash(conn, video_pk, beat_id: str, node_key: str) -> str | None:
    row = db.one(conn, """
        select bl.hash from beat_locks bl
        join beats b on b.id = bl.beat_pk
        where b.video_id = %s and b.beat_id = %s and bl.node_key = %s
    """, (video_pk, beat_id, node_key))
    return row["hash"] if row else None


def _artifact_present(conn, hash_: str) -> bool:
    row = db.one(conn, "select hash from artifacts where hash = %s", (hash_,))
    if not row:
        return False
    # A DB row without a blob is worse than no row at all — it makes a cache hit
    # that cannot be read. Treat it as absent so the node re-runs.
    return store().exists(hash_)


def plan(conn, ctx: VideoContext, target: str | None = None,
         implemented_only: bool = True) -> Plan:
    graph = ctx.graph
    if target is None:
        target = _last_implemented(graph) if implemented_only else graph.terminal
    p = Plan(ctx=ctx, target=target)

    # Two-pass resolution: in the production graph the beat list is an OUTPUT of
    # script_plan, so on the first run we can only plan as far as that stage.
    if graph.beat_producer and not ctx.beats:
        stages_needed = graph.upto(target or graph.terminal)
        if graph.beat_producer in stages_needed:
            target = graph.beat_producer
            p.needs_second_pass = True
            p.target = target

    nodes = expand(graph, ctx.beats, target)
    hashes: dict[str, str] = {}
    statuses: dict[str, str] = {}
    surface = ctx.config_surface
    seen_prompts: list[prompts.PromptRef] = []

    for node in nodes:
        spec = graph.stage(node.stage)

        # --- locked beats are pinned and exempt from upstream invalidation (§5.4)
        if spec.is_beat and node.beat_id:
            beat = next((b for b in ctx.beats if b.beat_id == node.beat_id), None)
            if beat and beat.locked:
                lh = _locked_hash(conn, ctx.video["id"], node.beat_id, node.key)
                if lh:
                    hashes[node.key] = lh
                    statuses[node.key] = LOCKED
                    p.nodes.append(PlannedNode(node, spec, lh, {}, LOCKED))
                    continue

        deps = dependencies(graph, node, ctx.beats)
        upstream: dict[str, str] = {}
        missing_upstream = False
        for label, dep_node in deps.items():
            h = hashes.get(dep_node.key)
            if h is None:
                missing_upstream = True
                continue
            upstream[label] = h

        prompt_version = None
        if spec.prompt:
            try:
                ref = prompts.load(spec.prompt)
                prompt_version = ref.version
                seen_prompts.append(ref)
            except prompts.PromptMissing:
                prompt_version = f"{spec.prompt}@MISSING"

        model_version = settings().models.for_tier(spec.tier)
        code_version = code_version_for_stage(node.stage)
        cfg = {k: surface[k] for k in spec.config_keys if k in surface}
        extra: dict = {}
        if spec.video_input_keys:
            vin = dict(ctx.video.get("inputs") or {})
            src = {"title": ctx.video.get("title"), **vin}
            extra["video"] = {k: src.get(k) for k in spec.video_input_keys}
        if spec.reads_beat_inputs and node.beat_id:
            beat = next((b for b in ctx.beats if b.beat_id == node.beat_id), None)
            extra["beat_inputs"] = beat.inputs if beat else {}
            extra["ordinal"] = beat.ordinal if beat else None

        h = closure_hash(
            kind=node.stage, upstream=upstream, prompt_version=prompt_version,
            model_version=model_version, code_version=code_version,
            config=cfg, extra=extra,
        )
        hashes[node.key] = h

        # --- status
        upstream_blocked = any(
            statuses.get(dn.key) in (UNIMPLEMENTED, BLOCKED) for dn in deps.values()
        )
        if _artifact_present(conn, h):
            status = CACHED
        elif not spec.implemented or not stage_base.has_handler(graph.name, node.stage):
            status = UNIMPLEMENTED
        elif upstream_blocked or missing_upstream:
            status = BLOCKED
        else:
            status = QUEUED
        statuses[node.key] = status
        p.nodes.append(PlannedNode(node, spec, h, upstream, status,
                                   prompt_version, model_version, code_version,
                                   cfg, extra))

    for ref in seen_prompts:
        prompts.register(conn, ref)
    return p


def _last_implemented(graph: Graph) -> str:
    last = None
    for key in graph.order:
        spec = graph.stage(key)
        if spec.implemented and stage_base.has_handler(graph.name, key):
            last = key
        else:
            break
    return last or graph.order[0]


# ---------------------------------------------------------------------- resolve

@dataclass
class ResolutionReport:
    plan: Plan
    enqueued: list[str] = field(default_factory=list)
    edges: int = 0

    @property
    def counts(self) -> dict[str, int]:
        return self.plan.counts()


def resolve(conn, ctx: VideoContext, target: str | None = None,
            dry_run: bool = False, implemented_only: bool = True) -> ResolutionReport:
    p = plan(conn, ctx, target, implemented_only)
    report = ResolutionReport(plan=p)
    if dry_run:
        return report

    _check_cost_cap(conn, ctx)
    for pn in p.nodes:
        # Record every node's outcome, cached ones included — this is what the
        # manifest and the §14.4 hash-diff are built from.
        state = {CACHED: "cached", LOCKED: "locked", QUEUED: "queued",
                 UNIMPLEMENTED: "cancelled", BLOCKED: "queued"}[pn.status]
        not_before = None if pn.status == QUEUED else None
        db.execute(conn, """
            insert into jobs(video_id, node_key, stage, beat_id, hash, pool, state,
                             priority, not_before, context)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (video_id, node_key, hash) do update
              set state = case
                    when jobs.state in ('succeeded','running','escalated') then jobs.state
                    else excluded.state end,
                  context = excluded.context
        """, (ctx.video["id"], pn.key, pn.node.stage, pn.node.beat_id, pn.hash,
              pn.spec.pool.value, state, ctx.video["priority"], not_before,
              json.dumps(pn.closure())))
        if pn.status == QUEUED:
            report.enqueued.append(pn.key)
        for parent_hash in pn.upstream.values():
            db.execute(conn, """
                insert into artifact_edges(parent_hash, child_hash) values (%s,%s)
                on conflict do nothing""", (parent_hash, pn.hash))
            report.edges += 1

    counts = p.counts()
    db.execute(conn, """
        insert into resolutions(video_id, target, planned, cached, locked, queued,
                                unimplemented, blocked, cache_hit_rate)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (ctx.video["id"], p.target, len(p.nodes), counts.get(CACHED, 0),
          counts.get(LOCKED, 0), counts.get(QUEUED, 0), counts.get(UNIMPLEMENTED, 0),
          counts.get(BLOCKED, 0), p.cache_hit_rate))
    db.execute(conn, "update videos set current_stage = %s where id = %s",
               (p.target, ctx.video["id"]))
    return report


def _check_cost_cap(conn, ctx: VideoContext) -> None:
    """§6.7 — a runaway loop against a frontier model is a boring way to lose money."""
    row = db.one(conn, """
        select coalesce(sum(a.cost_usd), 0) as spent
        from artifacts a join videos v on v.id = a.video_id
        where v.series_id = %s""", (ctx.series["id"],))
    spent = float(row["spent"]) if row else 0.0
    cap = settings().series_cost_cap_usd
    if spent >= cap:
        raise RuntimeError(
            f"series '{ctx.series['slug']}' has spent ${spent:.2f} against a "
            f"${cap:.2f} cap. Raise SERIES_COST_CAP_USD deliberately, or stop."
        )


# ------------------------------------------------------------------- hash diff

@dataclass
class NodeDiff:
    node_key: str
    old_hash: str | None
    new_hash: str
    verdict: str  # unchanged | changed | new


def hash_diff(conn, ctx: VideoContext, target: str | None = None) -> list[NodeDiff]:
    """§14.4 — see exactly which artifacts a change would touch, before rendering
    anything. Compares the freshly computed plan against the most recent
    recorded job row per node.
    """
    p = plan(conn, ctx, target)
    prev = {r["node_key"]: r["hash"] for r in db.query(conn, """
        select node_key, hash from (
          select node_key, hash, row_number() over (
                   partition by node_key order by created_at desc) rn
          from jobs where video_id = %s) t where rn = 1
    """, (ctx.video["id"],))}
    out: list[NodeDiff] = []
    for pn in p.nodes:
        old = prev.get(pn.key)
        verdict = "new" if old is None else ("unchanged" if old == pn.hash else "changed")
        out.append(NodeDiff(pn.key, old, pn.hash, verdict))
    return out


# ------------------------------------------------------------------ beat locking

def lock_beat(conn, ctx: VideoContext, beat_id: str) -> list[str]:
    """Pin every beat-scoped node of this beat to its current hash (§5.4)."""
    p = plan(conn, ctx)
    pinned: list[str] = []
    beat = db.one(conn, "select * from beats where video_id = %s and beat_id = %s",
                  (ctx.video["id"], beat_id))
    if not beat:
        raise LookupError(f"no beat '{beat_id}'")
    for pn in p.nodes:
        if pn.node.beat_id == beat_id and pn.status in (CACHED, LOCKED):
            db.execute(conn, """
                insert into beat_locks(beat_pk, node_key, hash) values (%s,%s,%s)
                on conflict (beat_pk, node_key) do update set hash = excluded.hash
            """, (beat["id"], pn.key, pn.hash))
            pinned.append(pn.key)
    db.execute(conn, "update beats set locked = true, locked_hash = %s where id = %s",
               (pinned and p.by_key()[pinned[-1]].hash or None, beat["id"]))
    db.execute(conn, """insert into edits(video_id, beat_id, kind, accepted)
                        values (%s,%s,'lock',true)""", (ctx.video["id"], beat_id))
    ctx.refresh_beats(conn)
    return pinned


def unlock_beat(conn, ctx: VideoContext, beat_id: str) -> None:
    beat = db.one(conn, "select * from beats where video_id = %s and beat_id = %s",
                  (ctx.video["id"], beat_id))
    if not beat:
        raise LookupError(f"no beat '{beat_id}'")
    db.execute(conn, "delete from beat_locks where beat_pk = %s", (beat["id"],))
    db.execute(conn, "update beats set locked = false, locked_hash = null where id = %s",
               (beat["id"],))
    db.execute(conn, """insert into edits(video_id, beat_id, kind, accepted)
                        values (%s,%s,'unlock',true)""", (ctx.video["id"], beat_id))
    ctx.refresh_beats(conn)


# ------------------------------------------------------------------ beat editing

def edit_beat_inputs(conn, ctx: VideoContext, beat_id: str, patch: dict,
                     instruction: str | None = None, gate: str | None = "a") -> None:
    """The Gate A / Gate C edit path. Writes the beat brief, records the edit.

    Beat briefs live in `beats.inputs` precisely so that editing one beat changes
    exactly one leaf hash (§5.3). Never write briefs into a video-scoped artifact.
    """
    beat = db.one(conn, "select * from beats where video_id = %s and beat_id = %s",
                  (ctx.video["id"], beat_id))
    if not beat:
        raise LookupError(f"no beat '{beat_id}'")
    before = dict(beat["inputs"])
    after = {**before, **patch}
    db.execute(conn, "update beats set inputs = %s where id = %s",
               (json.dumps(after), beat["id"]))
    db.execute(conn, """
        insert into edits(video_id, beat_id, gate, kind, instruction_text,
                          before, after, accepted)
        values (%s,%s,%s,'edit',%s,%s,%s,true)
    """, (ctx.video["id"], beat_id, gate, instruction,
          json.dumps(before), json.dumps(after)))
    ctx.refresh_beats(conn)


def reorder_beats(conn, ctx: VideoContext, order: Iterable[str]) -> None:
    """Gate B reorder. Changes `ordinal` only — `beat_id` is stable forever, or
    every lock and every edit history breaks (§6.3, note 2)."""
    for i, beat_id in enumerate(order, start=1):
        db.execute(conn, "update beats set ordinal = %s where video_id = %s and beat_id = %s",
                   (i, ctx.video["id"], beat_id))
    db.execute(conn, """insert into edits(video_id, kind, accepted, after)
                        values (%s,'reorder',true,%s)""",
               (ctx.video["id"], json.dumps(list(order))))
    ctx.refresh_beats(conn)
