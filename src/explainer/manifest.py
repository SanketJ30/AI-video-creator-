"""manifest.json (PRD Appendix A.3).

    "manifest.json is not bookkeeping — it is what makes S5 and §14.4 measurable."

Everything here is derived from Postgres, never hand-maintained: artifact hashes
and whether each was a cache hit, model and prompt versions, per-stage cost and
timing, human-minutes from gate_sessions, edit rate per gate from `edits`.
"""
from __future__ import annotations

import json
from typing import Any

from . import db
from .orchestrator import VideoContext, plan


def build(conn, ctx: VideoContext, target: str | None = None) -> dict[str, Any]:
    p = plan(conn, ctx, target)
    keys = [pn.key for pn in p.nodes]
    hashes = {pn.key: pn.hash for pn in p.nodes}

    art_rows = {r["hash"]: r for r in db.query(
        conn, "select * from artifacts where hash = any(%s)", (list(hashes.values()),))}
    job_rows = {(r["node_key"], r["hash"]): r for r in db.query(
        conn, "select * from jobs where video_id = %s", (ctx.video["id"],))}

    artifacts: dict[str, Any] = {}
    total_cost = 0.0
    total_exec_ms = 0
    cached_count = 0
    for k in keys:
        h = hashes[k]
        a = art_rows.get(h)
        j = job_rows.get((k, h))
        # A node whose artifact exists but whose job for this hash never ran (or
        # ran for a different video) was served from the store: a cache hit.
        was_cached = bool(a) and (j is None or j["state"] in ("cached", "locked")
                                 or j["exec_ms"] is None)
        if a:
            cached_count += 1 if was_cached else 0
            total_cost += float(a["cost_usd"] or 0)
        if j and j["exec_ms"]:
            total_exec_ms += j["exec_ms"]
        artifacts[k] = {
            "hash": h,
            "present": bool(a),
            "cached": was_cached,
            "state": (j or {}).get("state", "unplanned"),
            "bytes": (a or {}).get("bytes"),
            "cost_usd": float((a or {}).get("cost_usd") or 0),
            "duration_ms": (a or {}).get("duration_ms"),
            "model_version": (a or {}).get("model_version"),
            "prompt_version": (a or {}).get("prompt_version"),
            "code_version": (a or {}).get("code_version"),
        }

    # §6.5 — cache hit rate must come from the resolution record, not be inferred
    # after the fact: once the artifacts exist, "served" and "built" look alike.
    last = db.one(conn, """select * from resolutions where video_id = %s
                            order by created_at desc limit 1""", (ctx.video["id"],))
    cache_hit_rate = float(last["cache_hit_rate"]) if last and last["cache_hit_rate"] is not None else None

    gate = db.one(conn, """
        select coalesce(sum(active_seconds), 0) as secs
        from gate_sessions where video_id = %s""", (ctx.video["id"],))
    human_minutes = round((gate["secs"] or 0) / 60.0, 2) if gate else 0.0

    edit_rate = {}
    for row in db.query(conn, """
        select gate, count(*) filter (where kind = 'edit') as edits, count(*) as total
        from edits where video_id = %s and gate is not null group by gate""",
        (ctx.video["id"],)):
        edit_rate[f"gate_{row['gate']}"] = (
            round(row["edits"] / row["total"], 4) if row["total"] else 0.0)

    fails = db.one(conn, """
        select count(*) filter (where error_class = 'render_compile') as compile_fails,
               count(*) filter (where stage = 'render') as renders
        from jobs where video_id = %s""", (ctx.video["id"],))

    model_versions = {pn.node.stage: pn.model_version for pn in p.nodes}
    prompt_versions = {pn.node.stage: pn.prompt_version for pn in p.nodes if pn.prompt_version}

    return {
        "video_id": ctx.video["video_id"],
        "series": ctx.series["slug"],
        "graph": ctx.graph.name,
        "brand_version": ctx.video["brand_version"] or ctx.series["brand_version"],
        "locale": ctx.series["locale"],
        "audience_level": ctx.series["audience_level"],
        "beat_count": len(ctx.beats),
        "model_versions": model_versions,
        "prompt_versions": prompt_versions,
        "artifacts": artifacts,
        "metrics": {
            "fact_error_count": None,          # filled by the fact challenger (§9)
            "edit_rate": edit_rate or None,
            "human_minutes": human_minutes,
            "beats_regenerated": sum(
                1 for k in keys if job_rows.get((k, hashes[k]), {}).get("exec_ms")),
            "compile_failure_rate": (
                round((fails["compile_fails"] or 0) / fails["renders"], 4)
                if fails and fails["renders"] else 0.0),
            "template_gaps": None,
            "cache_hit_rate": cache_hit_rate,
            "artifacts_served_from_store": cached_count,
            "cost_usd": round(total_cost, 6),
            "wall_clock_min": round(total_exec_ms / 60000.0, 3),
            "retention_15s": None,             # §12.4, post-publish
            "comprehension_rate": None,        # §12.4, post-publish — S4
        },
        "rubric_scores": None,                 # §14.2, written by the reviewer
    }


def write(conn, ctx: VideoContext, target: str | None = None) -> str:
    """Build the manifest and store it as an artifact of the video."""
    doc = build(conn, ctx, target)
    return json.dumps(doc, indent=2, sort_keys=True)
