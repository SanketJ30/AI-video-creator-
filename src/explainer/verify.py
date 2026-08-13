"""The Phase 1 exit criteria, executable (PRD §16, Phase 1).

    - Run a fake 4-stage pipeline over 5 fake beats. Change beat 3's input.
      Confirm: exactly beat 3's downstream artifacts re-run, everything else is a
      cache hit, byte-identical.
    - Kill a worker mid-job. Confirm it requeues and completes.
    - Cache hit rate on an unchanged re-run is 100%.

Plus two checks the PRD implies but does not spell out, both of which are load-
bearing for §5.4 and S5:

    - A locked beat is exempt from upstream invalidation.
    - Two videos with identical inputs share artifacts (cross-video dedupe).

This is the regression gate for every future change to hashing, DAG resolution
or the worker. If `explainer verify` fails, the invalidation model is broken and
nothing built on top of it can be trusted.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field

from . import db, orchestrator, worker
from .orchestrator import CACHED, LOCKED, QUEUED, load_video
from .store import store

FIXTURE_SLUG = "fake-verify"
N_BEATS = 5


@dataclass
class Report:
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append((name, ok, detail))
        return ok

    @property
    def ok(self) -> bool:
        return all(c[1] for c in self.checks)


def _seed(conn, nonce: str) -> None:
    db.execute(conn, "delete from series where slug = %s", (FIXTURE_SLUG,))
    db.execute(conn, """
        insert into series(slug, title, locale, audience_level, brand_version)
        values (%s, %s, 'en', 'intermediate', '1.0.0')""",
        (FIXTURE_SLUG, f"fake verification {nonce}"))
    series = db.one(conn, "select * from series where slug = %s", (FIXTURE_SLUG,))
    for vid in ("v1", "v2"):
        row = db.one(conn, """
            insert into videos(series_id, video_id, title, brand_version, graph)
            values (%s,%s,%s,'1.0.0','fake') returning *""",
            (series["id"], vid, f"[fake] identical inputs {nonce}"))
        for i in range(1, N_BEATS + 1):
            db.execute(conn, """
                insert into beats(video_id, ordinal, beat_id, inputs, role)
                values (%s,%s,%s,%s,%s)""",
                (row["id"], i, f"b{i:02d}",
                 json.dumps({"text": f"beat {i} brief {nonce}"}), "explanation"))


def _drain(log) -> int:
    # Patient enough to outlast the dependency-gating defer window, since the
    # fake stages finish in milliseconds and the whole DAG is enqueued at once.
    return worker.run(["agent", "media", "render"], max_idle_polls=12,
                      idle_sleep=0.25, log=lambda s: None)


def _snapshot(conn, ctx) -> dict[str, tuple[str, str]]:
    """node_key -> (hash, sha256 of the stored bytes)."""
    from .hashing import content_hash
    p = orchestrator.plan(conn, ctx)
    out = {}
    for pn in p.nodes:
        if store().exists(pn.hash):
            out[pn.key] = (pn.hash, content_hash(store().get(pn.hash)))
    return out


def run_phase1_verification(log=print, keep: bool = False) -> bool:
    r = Report()
    nonce = uuid.uuid4().hex[:8]
    log(f"fixture: {FIXTURE_SLUG} (nonce {nonce}) — 2 videos × {N_BEATS} beats, fake graph\n")

    with db.tx() as conn:
        _seed(conn, nonce)

    # ---------------------------------------------------- 1. cold run completes
    log("· cold run")
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        rep = orchestrator.resolve(conn, ctx)
    total_nodes = len(rep.plan.nodes)
    expected_nodes = 1 + N_BEATS * 3 + 1          # research + (script,tts,pacing)×N + assembly
    r.add("DAG expands to the expected node count",
          total_nodes == expected_nodes, f"{total_nodes} nodes (expected {expected_nodes})")
    r.add("cold run enqueues every node",
          len(rep.enqueued) == total_nodes, f"{len(rep.enqueued)} queued")
    done = _drain(log)
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        p = orchestrator.plan(conn, ctx)
    built = sum(1 for pn in p.nodes if pn.status == CACHED)
    r.add("every node produced an artifact", built == total_nodes,
          f"{built}/{total_nodes} present after {done} jobs")

    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        snap = _snapshot(conn, ctx)

    # ------------------------------------- 2. unchanged re-run is 100% cache hit
    log("· unchanged re-run")
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        rep2 = orchestrator.resolve(conn, ctx)
    r.add("unchanged re-run is 100% cache hits",
          rep2.plan.cache_hit_rate == 1.0 and not rep2.enqueued,
          f"cache_hit_rate={rep2.plan.cache_hit_rate:.0%}, enqueued={len(rep2.enqueued)}")

    # ------------------------------------- 3. cross-video dedupe (identical inputs)
    log("· cross-video dedupe")
    with db.tx() as conn:
        ctx2 = load_video(conn, FIXTURE_SLUG, "v2", "fake")
        rep3 = orchestrator.resolve(conn, ctx2)
    r.add("identical inputs on another video reuse every artifact",
          rep3.plan.cache_hit_rate == 1.0 and not rep3.enqueued,
          f"v2 cache_hit_rate={rep3.plan.cache_hit_rate:.0%} — this is where S5's "
          f"cost curve comes from")

    # ------------------------------------- 4. edit beat 3: exact invalidation set
    log("· edit beat 3")
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        orchestrator.edit_beat_inputs(conn, ctx, "b03", {"text": "rewritten at gate C"},
                                      instruction="beat 7 was confusing", gate="c")
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        p = orchestrator.plan(conn, ctx)
    queued = {pn.key for pn in p.nodes if pn.status == QUEUED}
    expected = {"script:b03", "tts:b03", "pacing:b02", "pacing:b03", "pacing:b04", "assembly"}
    r.add("editing beat 3 invalidates exactly its downstream closure",
          queued == expected,
          f"got {sorted(queued)}" if queued != expected else
          f"{len(expected)} nodes: script/tts for b03, pacing for b02-b04 "
          f"(neighbour window), assembly (global)")
    r.add("the other 4 beats keep their hashes",
          all(pn.status == CACHED for pn in p.nodes
              if pn.node.beat_id in ("b01", "b02", "b04", "b05")
              and pn.node.stage in ("script", "tts")),
          "beats 1,2,4,5 script+tts unchanged")

    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        orchestrator.resolve(conn, ctx)
    _drain(log)

    from .hashing import content_hash
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        snap2 = _snapshot(conn, ctx)
    untouched = [k for k in snap if k in snap2 and k not in expected]
    identical = [k for k in untouched if snap[k] == snap2[k]]
    r.add("untouched artifacts are byte-identical after the edit",
          len(identical) == len(untouched) and len(untouched) >= 10,
          f"{len(identical)}/{len(untouched)} byte-identical")

    # ------------------------------------- 5. a locked beat resists invalidation
    log("· locked beat")
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        pinned = orchestrator.lock_beat(conn, ctx, "b05")
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        orchestrator.edit_beat_inputs(conn, ctx, "b05", {"text": "edited while locked"})
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        p = orchestrator.plan(conn, ctx)
    locked_nodes = {pn.key for pn in p.nodes if pn.status == LOCKED}
    still_queued = {pn.key for pn in p.nodes if pn.status == QUEUED}
    r.add("locked beat is exempt from upstream invalidation",
          not still_queued and locked_nodes,
          f"pinned {len(pinned)} nodes; queued after edit = {sorted(still_queued) or 'none'}")

    # ------------------------------------- 6. kill a worker mid-job
    log("· worker crash")
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        orchestrator.unlock_beat(conn, ctx, "b05")
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        orchestrator.edit_beat_inputs(conn, ctx, "b05", {"text": f"crash test {nonce}"})
        rep4 = orchestrator.resolve(conn, ctx)
    n_queued = len(rep4.enqueued)

    victim = subprocess.Popen(
        [sys.executable, "-c",
         "from explainer import db, worker;\n"
         "conn = db.connect();\n"
         "j = worker.claim(conn, ['agent','media','render']);\n"
         "conn.commit();\n"
         "print(j['node_key'] if j else 'none', flush=True);\n"
         "import time; time.sleep(600)"],
        stdout=subprocess.PIPE, text=True)
    claimed = (victim.stdout.readline() or "").strip()
    victim.kill()
    victim.wait(timeout=10)
    log(f"killed a worker holding {claimed}")

    with db.tx() as conn:
        # Backdate the heartbeat instead of waiting out the real 120s timeout.
        db.execute(conn, """update jobs set heartbeat_at = now() - interval '10 minutes'
                            where state = 'running'""")
    reaped = worker.reap(log=lambda s: None)
    r.add("dead worker's job is reaped back to queued", reaped >= 1, f"{reaped} reaped")
    _drain(log)
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        p = orchestrator.plan(conn, ctx)
    r.add("pipeline completes after the crash",
          all(pn.status in (CACHED, LOCKED) for pn in p.nodes),
          f"{sum(1 for pn in p.nodes if pn.status == CACHED)}/{len(p.nodes)} present "
          f"(job that died: {claimed}, {n_queued} were queued)")

    # ------------------------------------- 7. hash determinism
    log("· determinism")
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        h1 = {pn.key: pn.hash for pn in orchestrator.plan(conn, ctx).nodes}
        h2 = {pn.key: pn.hash for pn in orchestrator.plan(conn, ctx).nodes}
    r.add("hashing is deterministic across passes", h1 == h2, f"{len(h1)} nodes")

    # ------------------------------------- 8. manifest
    log("· manifest")
    from . import manifest as manifest_mod
    with db.tx() as conn:
        ctx = load_video(conn, FIXTURE_SLUG, "v1", "fake")
        m = manifest_mod.build(conn, ctx)
    r.add("manifest reports cache hit rate and cost",
          m["metrics"]["cache_hit_rate"] is not None and "artifacts" in m,
          f"cache_hit_rate={m['metrics']['cache_hit_rate']}, "
          f"cost=${m['metrics']['cost_usd']}, beats={m['beat_count']}")

    if not keep:
        with db.tx() as conn:
            db.execute(conn, "delete from series where slug = %s", (FIXTURE_SLUG,))

    # ------------------------------------------------------------------ report
    log("")
    width = max(len(n) for n, _, _ in r.checks)
    for name, ok, detail in r.checks:
        mark = "PASS" if ok else "FAIL"
        log(f"  [{mark}] {name.ljust(width)}  {detail}")
    log("")
    log("PHASE 1 EXIT CRITERIA: " + ("MET" if r.ok else "NOT MET"))
    return r.ok
