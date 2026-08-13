"""The worker (PRD §6.2, §6.4).

Claim with `SELECT ... FOR UPDATE SKIP LOCKED`, heartbeat while running, apply
the failure policy from §6.4, and escalate rather than die quietly:

    "escalated is a first-class state, not a failure. A pipeline that dies
     silently at 2 a.m. and shows a red dot in a log is a pipeline nobody trusts."

Three pools exist because their resource profiles differ completely (§6.1). Run
`--pools agent,media` on a cheap box and `--pools render` wherever Chromium
lives; one shared pool means a single long render starves twelve cheap LLM calls.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import traceback
import uuid
from dataclasses import dataclass

from . import db
from .config import settings
from .dag import BeatRef, Node
from .hashing import closure_hash, content_hash
from .orchestrator import graph_for
from .stages.base import (LoadedInput, StageContext, StageFailure,
                          StageNotImplemented, StageResult, get_handler)
from .store import store

# ------------------------------------------------------------- §6.4 retry policy

@dataclass(frozen=True)
class Policy:
    max_attempts: int
    backoff: str  # 'none' | 'exp'


POLICY: dict[str, Policy] = {
    "llm_transient":  Policy(5, "exp"),    # 429 / 5xx, 2s → 60s
    "llm_schema":     Policy(3, "none"),   # re-prompt with the validation error
    "render_compile": Policy(3, "none"),   # feed traceback + scene spec back
    "render_timeout": Policy(1, "none"),   # likely an infinite animation
    "tts":            Policy(3, "exp"),
    "ffmpeg":         Policy(2, "none"),
    "internal":       Policy(1, "none"),
    "unknown":        Policy(1, "none"),
}


def backoff_seconds(policy: Policy, attempts: int) -> int:
    if policy.backoff == "none":
        return 0
    return min(60, 2 ** max(0, attempts - 1) * 2)


def classify(exc: BaseException) -> str:
    if isinstance(exc, StageFailure):
        return exc.error_class if exc.error_class in POLICY else "unknown"
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "render_timeout"
    if "validation" in name or isinstance(exc, (ValueError, KeyError)):
        return "llm_schema"
    return "unknown"


# ------------------------------------------------------------------- heartbeat

class Heartbeat:
    """Separate connection: the job's transaction must not hold the heartbeat."""

    def __init__(self, job_id: str, interval_s: int):
        self.job_id, self.interval = job_id, interval_s
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                with db.tx() as conn:
                    db.execute(conn, "update jobs set heartbeat_at = now() where id = %s",
                               (self.job_id,))
            except Exception:
                pass  # a missed beat costs one reap, a crashed thread costs the job

    def __enter__(self) -> "Heartbeat":
        self._t.start()
        return self

    def __exit__(self, *a) -> None:
        self._stop.set()


# ----------------------------------------------------------------------- claim

def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


CLAIM_SQL = """
update jobs set state = 'running',
                worker_id = %(wid)s,
                attempts = attempts + 1,
                started_at = coalesce(started_at, now()),
                heartbeat_at = now(),
                queue_wait_ms = coalesce(queue_wait_ms,
                    (extract(epoch from (now() - created_at)) * 1000)::int)
where id = (
    select id from jobs
    where state = 'queued'
      and pool = any(%(pools)s)
      and (not_before is null or not_before <= now())
      -- Only claim jobs whose whole upstream closure is already in the store.
      -- Without this, a worker burns claims on jobs it must immediately defer,
      -- and a drain loop can spin forever making no progress.
      and not exists (
          select 1 from artifact_edges e
          left join artifacts a on a.hash = e.parent_hash
          where e.child_hash = jobs.hash and a.hash is null)
    order by priority desc, created_at
    for update skip locked
    limit 1)
returning *
"""


def claim(conn, pools: list[str]) -> dict | None:
    rows = db.query(conn, CLAIM_SQL, {"wid": worker_id(), "pools": pools})
    return rows[0] if rows else None


def parents_ready(conn, job: dict) -> list[str]:
    """Which upstream artifacts are still missing. Dependency gating lives here
    rather than in the orchestrator, so the whole DAG can be enqueued at once."""
    ups: dict[str, str] = (job["context"] or {}).get("upstream", {})
    if not ups:
        return []
    have = {r["hash"] for r in db.query(
        conn, "select hash from artifacts where hash = any(%s)", (list(set(ups.values())),))}
    return sorted({h for h in ups.values() if h not in have})


# --------------------------------------------------------------------- execute

def build_context(conn, job: dict) -> StageContext:
    video = db.one(conn, "select * from videos where id = %s", (job["video_id"],))
    series = db.one(conn, "select * from series where id = %s", (video["series_id"],))
    graph = graph_for(video["graph"])
    spec = graph.stage(job["stage"])

    beat = None
    if job["beat_id"]:
        row = db.one(conn, "select * from beats where video_id = %s and beat_id = %s",
                     (job["video_id"], job["beat_id"]))
        if row:
            beat = BeatRef(row["beat_id"], row["ordinal"], row["inputs"], row["locked"])

    closure = job["context"] or {}
    inputs: dict[str, LoadedInput] = {}
    for label, h in (closure.get("upstream") or {}).items():
        art = db.one(conn, "select * from artifacts where hash = %s", (h,))
        if not art:
            raise StageFailure(f"upstream artifact {h} vanished from the store", "internal")
        inputs[label] = LoadedInput(label, h, art["mime"] or "", store().get(h))

    prompt_body = None
    if spec.prompt:
        from . import prompts
        try:
            prompt_body = prompts.load(spec.prompt).body
        except prompts.PromptMissing:
            prompt_body = None

    # Integrity check: re-derive the hash from the stored closure. A mismatch
    # means something drifted between enqueue and execute — refuse to poison the
    # cache with an artifact filed under the wrong hash.
    recomputed = closure_hash(
        kind=job["stage"], upstream=closure.get("upstream") or {},
        prompt_version=closure.get("prompt_version"),
        model_version=closure.get("model_version"),
        code_version=closure.get("code_version"),
        config=closure.get("config") or {}, extra=closure.get("extra") or {},
    )
    if recomputed != job["hash"]:
        raise StageFailure(
            f"closure drift on {job['node_key']}: job hash {job['hash'][:12]} but "
            f"recomputed {recomputed[:12]}. Re-resolve the video.", "internal")

    return StageContext(
        node=Node(job["stage"], job["beat_id"], beat.ordinal if beat else None),
        spec=spec, hash=job["hash"], series=series, video=video, beat=beat,
        inputs=inputs, prompt_body=prompt_body,
        prompt_version=closure.get("prompt_version"),
        model_version=closure.get("model_version"),
        config=closure.get("config") or {},
    )


def persist_success(conn, job: dict, result: StageResult, exec_ms: int) -> None:
    uri = store().put(job["hash"], result.data, result.mime)
    closure = job["context"] or {}
    db.execute(conn, """
        insert into artifacts(hash, kind, video_id, beat_id, storage_uri,
                              content_sha256, bytes, mime, cost_usd, duration_ms,
                              model_version, prompt_version, code_version, meta)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (hash) do nothing
    """, (job["hash"], job["stage"], job["video_id"], job["beat_id"], uri,
          content_hash(result.data), len(result.data), result.mime,
          result.cost_usd, result.duration_ms,
          result.model_version or closure.get("model_version"),
          closure.get("prompt_version"), closure.get("code_version"),
          json.dumps(result.meta)))
    db.execute(conn, """
        update jobs set state = 'succeeded', finished_at = now(), exec_ms = %s,
                        error = null, error_class = null
        where id = %s""", (exec_ms, job["id"]))


def handle_failure(conn, job: dict, exc: BaseException) -> str:
    cls = classify(exc)
    policy = POLICY[cls]
    detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    tb = traceback.format_exc(limit=8)
    if job["attempts"] >= policy.max_attempts:
        db.execute(conn, """
            update jobs set state = 'escalated', finished_at = now(),
                            error = %s, error_class = %s where id = %s
        """, (f"{detail}\n\n{tb}", cls, job["id"]))
        if cls == "render_compile":
            db.execute(conn, """
                update templates set compile_failures = compile_failures + 1
                where name = %s""", ((job["context"] or {}).get("config", {}).get("template", ""),))
        return "escalated"
    delay = backoff_seconds(policy, job["attempts"])
    db.execute(conn, """
        update jobs set state = 'queued', worker_id = null,
                        not_before = now() + make_interval(secs => %s),
                        error = %s, error_class = %s where id = %s
    """, (delay, detail, cls, job["id"]))
    return f"retry in {delay}s ({job['attempts']}/{policy.max_attempts}, {cls})"


# -------------------------------------------------------------------- run loop

def run_once(pools: list[str] | None = None) -> str | None:
    """Claim and execute at most one job. Returns a log line, or None if idle."""
    pools = pools or list(settings().worker_pools)
    with db.tx() as conn:
        job = claim(conn, pools)
    if job is None:
        return None

    with db.tx() as conn:
        missing = parents_ready(conn, job)
        if missing:
            db.execute(conn, """
                update jobs set state = 'queued', worker_id = null,
                                attempts = attempts - 1,
                                not_before = now() + interval '1 second'
                where id = %s""", (job["id"],))
            return f"defer  {job['node_key']} (waiting on {len(missing)} upstream)"

    t0 = time.monotonic()
    try:
        with Heartbeat(job["id"], settings().heartbeat_interval_s):
            with db.tx() as conn:
                ctx = build_context(conn, job)
            handler = get_handler(ctx.video["graph"], job["stage"])
            result = handler(ctx)
        exec_ms = int((time.monotonic() - t0) * 1000)
        with db.tx() as conn:
            persist_success(conn, job, result, exec_ms)
        return f"ok     {job['node_key']}  {exec_ms}ms  {len(result.data)}B  {job['hash'][:10]}"
    except StageNotImplemented as e:
        with db.tx() as conn:
            db.execute(conn, """update jobs set state = 'cancelled', error = %s,
                                error_class = 'unimplemented', finished_at = now()
                                where id = %s""", (str(e), job["id"]))
        return f"skip   {job['node_key']} (no handler yet)"
    except BaseException as e:  # noqa: BLE001 — every failure must be recorded
        with db.tx() as conn:
            outcome = handle_failure(conn, job, e)
        return f"FAIL   {job['node_key']}  {classify(e)}  → {outcome}"


def run(pools: list[str] | None = None, idle_sleep: float = 0.5,
        max_idle_polls: int | None = None, log=print) -> int:
    """Loop until drained (max_idle_polls) or forever (None). Returns jobs done.

    A deferral counts as no progress. Treating it as progress is how a drain loop
    livelocks: deferred jobs keep resetting the idle counter forever.
    """
    done, idle = 0, 0
    while True:
        line = run_once(pools)
        progressed = line is not None and not line.startswith("defer")
        if not progressed:
            idle += 1
            if max_idle_polls is not None and idle >= max_idle_polls:
                return done
            time.sleep(idle_sleep)
        else:
            idle = 0
            done += 1
        if line is not None:
            log(line)


# ---------------------------------------------------------------------- reaper

def reap(timeout_s: int | None = None, log=print) -> int:
    """Requeue jobs whose worker stopped heartbeating (§6.4, last row).

    Retries are unlimited and the attempt count is PRESERVED — a dead machine is
    not the job's fault, so it must not consume the job's retry budget.
    """
    timeout_s = timeout_s or settings().heartbeat_timeout_s
    with db.tx() as conn:
        rows = db.query(conn, """
            update jobs set state = 'queued', worker_id = null,
                            attempts = greatest(attempts - 1, 0),
                            not_before = null
            where state = 'running'
              and heartbeat_at < now() - make_interval(secs => %s)
            returning node_key, attempts
        """, (timeout_s,))
    for r in rows:
        log(f"reaped {r['node_key']} → queued")
    return len(rows)
