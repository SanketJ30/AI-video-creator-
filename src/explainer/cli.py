"""CLI. Phase 1 has no UI by design (PRD §16, Phase 1: "CLI only").

    explainer db init
    explainer series create sql-for-analysts --title "SQL for analysts"
    explainer video create sql-for-analysts/v1 --beats 5 --graph fake
    explainer resolve sql-for-analysts/v1 --dry-run
    explainer run --pools agent,media --drain
    explainer manifest sql-for-analysts/v1
    explainer verify                      # the Phase 1 exit criteria, executable
"""
from __future__ import annotations

import json as jsonlib
import sys
from typing import Optional

import typer

from . import db, manifest as manifest_mod, orchestrator, worker
from .config import settings
from .orchestrator import load_video

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="AI-native explainer video pipeline (PRD v4).")
db_app = typer.Typer(no_args_is_help=True, help="Schema management.")
series_app = typer.Typer(no_args_is_help=True, help="Series (§10.3 curriculum scope).")
video_app = typer.Typer(no_args_is_help=True, help="Videos.")
beat_app = typer.Typer(no_args_is_help=True, help="Beats — the atomic unit (§5.3).")
app.add_typer(db_app, name="db")
app.add_typer(series_app, name="series")
app.add_typer(video_app, name="video")
app.add_typer(beat_app, name="beat")

err = typer.style


def _split(ref: str) -> tuple[str, str]:
    if "/" not in ref:
        raise typer.BadParameter("expected SERIES_SLUG/VIDEO_ID, e.g. sql-for-analysts/v1")
    slug, vid = ref.split("/", 1)
    return slug, vid


# ----------------------------------------------------------------------- db

@db_app.command("init")
def db_init() -> None:
    """Apply migrations. Idempotent."""
    applied = db.migrate()
    typer.echo(f"db {db.dsn_summary()}: " +
               (f"applied {', '.join(applied)}" if applied else "already up to date"))


@db_app.command("reset")
def db_reset(yes: bool = typer.Option(False, "--yes", help="skip confirmation")) -> None:
    """Drop and recreate the schema. Destructive."""
    if not yes:
        typer.confirm(f"drop schema public on {db.dsn_summary()}?", abort=True)
    db.reset_schema()
    typer.echo("schema reset")


@app.command()
def doctor() -> None:
    """Check that everything this thing needs is actually reachable."""
    s = settings()
    ok = True
    typer.echo(f"env          {s.env}")
    try:
        with db.tx() as conn:
            v = db.one(conn, "select version() as v")["v"].split(",")[0]
        typer.echo(f"postgres     ok   {v}  ({db.dsn_summary()})")
    except Exception as e:
        ok = False
        typer.echo(f"postgres     FAIL {e}")
    try:
        from .store import store
        st = store()
        probe = "0" * 64
        st.exists(probe)
        typer.echo(f"store        ok   {s.artifact_backend}  {st.uri_for(probe).rsplit('/', 1)[0]}")
    except Exception as e:
        ok = False
        typer.echo(f"store        FAIL {e}")
    from .codeversion import code_version_for_stage
    typer.echo(f"code_version {code_version_for_stage('script')}")
    typer.echo(f"models       frontier={s.models.frontier} mid={s.models.mid}")
    typer.echo(f"tts          model={s.models.tts_model} voice={s.models.tts_voice}")
    from . import prompts
    typer.echo(f"prompts      {len(prompts.all_prompts())} registered")
    raise typer.Exit(0 if ok else 1)


# -------------------------------------------------------------------- series

@series_app.command("create")
def series_create(
    slug: str,
    title: str = typer.Option(..., "--title"),
    locale: str = typer.Option("en", "--locale", help="D7 — ship EN only, keep the column"),
    audience_level: str = typer.Option("intermediate", "--audience-level", help="D1"),
    brand_version: str = typer.Option("1.0.0", "--brand-version"),
    curriculum: Optional[str] = typer.Option(None, "--curriculum", help="path to curriculum.yaml"),
) -> None:
    yaml_text = open(curriculum).read() if curriculum else None
    with db.tx() as conn:
        db.execute(conn, """
            insert into series(slug, title, locale, audience_level, brand_version,
                               curriculum_yaml)
            values (%s,%s,%s,%s,%s,%s)
            on conflict (slug) do update set title = excluded.title
        """, (slug, title, locale, audience_level, brand_version, yaml_text))
    typer.echo(f"series {slug} ready")


@series_app.command("list")
def series_list() -> None:
    with db.tx() as conn:
        for r in db.query(conn, "select slug, title, locale, audience_level from series order by slug"):
            typer.echo(f"{r['slug']:28} {r['locale']} {r['audience_level']:12} {r['title']}")


# --------------------------------------------------------------------- video

@video_app.command("create")
def video_create(
    ref: str,
    title: str = typer.Option("", "--title"),
    beats: int = typer.Option(0, "--beats", help="seed N placeholder beats (fake graph)"),
    graph: str = typer.Option("production", "--graph", help="production | fake"),
    priority: int = typer.Option(0, "--priority"),
) -> None:
    slug, vid = _split(ref)
    title = title or vid
    with db.tx() as conn:
        series = db.one(conn, "select * from series where slug = %s", (slug,))
        if not series:
            typer.echo(f"no series '{slug}' — create it first", err=True)
            raise typer.Exit(1)
        row = db.one(conn, """
            insert into videos(series_id, video_id, title, brand_version, priority, graph)
            values (%s,%s,%s,%s,%s,%s)
            on conflict (series_id, video_id) do update
              set title = excluded.title, graph = excluded.graph
            returning *""", (series["id"], vid, title, series["brand_version"],
                             priority, graph))
        for i in range(1, beats + 1):
            bid = f"b{i:02d}"
            db.execute(conn, """
                insert into beats(video_id, ordinal, beat_id, inputs, role)
                values (%s,%s,%s,%s,%s)
                on conflict (video_id, beat_id) do nothing
            """, (row["id"], i, bid,
                  jsonlib.dumps({"text": f"placeholder brief for beat {i}"}),
                  "worked_example" if i % 3 == 0 else "explanation"))
    typer.echo(f"video {ref} ready ({beats} beats, graph={graph})")


# ---------------------------------------------------------------------- beat

@beat_app.command("list")
def beat_list(ref: str) -> None:
    slug, vid = _split(ref)
    with db.tx() as conn:
        ctx = load_video(conn, slug, vid)
        for b in ctx.beats:
            lock = "LOCKED" if b.locked else "      "
            typer.echo(f"{b.ordinal:>3} {b.beat_id} {lock} {jsonlib.dumps(b.inputs)[:80]}")


@beat_app.command("edit")
def beat_edit(ref: str, beat_id: str,
              text: str = typer.Option(..., "--text"),
              instruction: Optional[str] = typer.Option(None, "--instruction"),
              gate: str = typer.Option("a", "--gate")) -> None:
    """Edit a beat brief. This is the one write that must stay beat-local (§5.3)."""
    slug, vid = _split(ref)
    with db.tx() as conn:
        ctx = load_video(conn, slug, vid)
        orchestrator.edit_beat_inputs(conn, ctx, beat_id, {"text": text}, instruction, gate)
    typer.echo(f"{ref} {beat_id} edited — re-resolve to see the invalidation set")


@beat_app.command("lock")
def beat_lock(ref: str, beat_id: str) -> None:
    slug, vid = _split(ref)
    with db.tx() as conn:
        ctx = load_video(conn, slug, vid)
        pinned = orchestrator.lock_beat(conn, ctx, beat_id)
    typer.echo(f"pinned {len(pinned)} nodes: {', '.join(pinned) or '(nothing built yet)'}")


@beat_app.command("unlock")
def beat_unlock(ref: str, beat_id: str) -> None:
    slug, vid = _split(ref)
    with db.tx() as conn:
        ctx = load_video(conn, slug, vid)
        orchestrator.unlock_beat(conn, ctx, beat_id)
    typer.echo(f"{beat_id} unlocked")


@beat_app.command("reorder")
def beat_reorder(ref: str, order: str = typer.Option(..., "--order", help="b01,b03,b02,...")) -> None:
    slug, vid = _split(ref)
    with db.tx() as conn:
        ctx = load_video(conn, slug, vid)
        orchestrator.reorder_beats(conn, ctx, [x.strip() for x in order.split(",")])
    typer.echo("reordered — beat_ids unchanged, ordinals rewritten")


# ------------------------------------------------------------------- resolve

STATUS_COLOR = {"cached": typer.colors.GREEN, "locked": typer.colors.BLUE,
                "queued": typer.colors.YELLOW, "unimplemented": typer.colors.BRIGHT_BLACK,
                "blocked": typer.colors.MAGENTA}


@app.command()
def resolve(ref: str,
            target: Optional[str] = typer.Option(None, "--target", help="stop at this stage"),
            dry_run: bool = typer.Option(False, "--dry-run", help="plan only, enqueue nothing"),
            all_stages: bool = typer.Option(False, "--all", help="include unbuilt stages"),
            as_json: bool = typer.Option(False, "--json")) -> None:
    """Resolve the DAG: hash every node, serve what exists, enqueue what does not."""
    slug, vid = _split(ref)
    with db.tx() as conn:
        ctx = load_video(conn, slug, vid)
        rep = orchestrator.resolve(conn, ctx, target, dry_run, implemented_only=not all_stages)
    p = rep.plan
    if as_json:
        typer.echo(jsonlib.dumps({
            "target": p.target, "counts": p.counts(),
            "cache_hit_rate": p.cache_hit_rate,
            "nodes": [{"key": n.key, "status": n.status, "hash": n.hash} for n in p.nodes],
        }, indent=2))
        return
    for n in p.nodes:
        typer.echo(f"  {typer.style(n.status.ljust(13), fg=STATUS_COLOR.get(n.status))} "
                   f"{n.key:26} {n.hash[:12]}  {n.spec.pool.value}")
    counts = ", ".join(f"{k}={v}" for k, v in sorted(p.counts().items()))
    typer.echo(f"\ntarget={p.target}  {counts}  cache_hit_rate={p.cache_hit_rate:.0%}")
    if p.needs_second_pass:
        typer.echo("note: beat list is produced by this run — re-resolve afterwards "
                   "to expand beat-scoped stages")
    if dry_run:
        typer.echo("dry run — nothing enqueued")


@app.command()
def diff(ref: str, target: Optional[str] = typer.Option(None, "--target")) -> None:
    """§14.4 — which artifacts a change would touch, before rendering anything."""
    slug, vid = _split(ref)
    with db.tx() as conn:
        ctx = load_video(conn, slug, vid)
        rows = orchestrator.hash_diff(conn, ctx, target)
    changed = [r for r in rows if r.verdict != "unchanged"]
    for r in rows:
        mark = {"unchanged": "  ", "changed": "→ ", "new": "+ "}[r.verdict]
        typer.echo(f"{mark}{r.node_key:26} {(r.old_hash or '-')[:12]} → {r.new_hash[:12]}")
    typer.echo(f"\n{len(changed)}/{len(rows)} nodes would change")


# ------------------------------------------------------------------- workers

@app.command()
def run(pools: str = typer.Option("", "--pools", help="agent,render,media"),
        drain: bool = typer.Option(False, "--drain", help="exit when the queue empties"),
        idle_polls: int = typer.Option(4, "--idle-polls")) -> None:
    """Run a worker. One process per pool profile (§6.1)."""
    pool_list = [p.strip() for p in pools.split(",") if p.strip()] or list(settings().worker_pools)
    typer.echo(f"worker {worker.worker_id()} pools={pool_list}")
    n = worker.run(pool_list, max_idle_polls=idle_polls if drain else None)
    typer.echo(f"{n} jobs processed")


@app.command()
def reap() -> None:
    """Requeue jobs from dead workers (§6.4). Run on a cron / loop."""
    typer.echo(f"{worker.reap()} jobs reaped")


@app.command()
def jobs(ref: Optional[str] = typer.Argument(None),
         state: Optional[str] = typer.Option(None, "--state")) -> None:
    """Job table view, escalations first — the queue a human has to unblock."""
    sql = """select v.video_id, j.node_key, j.state, j.pool, j.attempts,
                    j.error_class, left(coalesce(j.error,''), 60) as err
             from jobs j join videos v on v.id = j.video_id"""
    params: list = []
    where = []
    if ref:
        slug, vid = _split(ref)
        where.append("v.video_id = %s and v.series_id = (select id from series where slug = %s)")
        params += [vid, slug]
    if state:
        where.append("j.state = %s")
        params.append(state)
    if where:
        sql += " where " + " and ".join(where)
    sql += """ order by case j.state when 'escalated' then 0 when 'failed' then 1
                                     when 'running' then 2 when 'queued' then 3 else 4 end,
                        j.created_at"""
    with db.tx() as conn:
        rows = db.query(conn, sql, params)
    for r in rows:
        typer.echo(f"{r['state']:10} {r['video_id']:6} {r['node_key']:26} "
                   f"{r['pool']:7} a={r['attempts']} {r['error_class'] or ''} {r['err'] or ''}")
    typer.echo(f"{len(rows)} jobs")


# ------------------------------------------------------------------ manifest

@app.command()
def manifest(ref: str, out: Optional[str] = typer.Option(None, "--out")) -> None:
    """Write manifest.json (Appendix A.3)."""
    slug, vid = _split(ref)
    with db.tx() as conn:
        ctx = load_video(conn, slug, vid)
        text = manifest_mod.write(conn, ctx)
    if out:
        open(out, "w").write(text)
        typer.echo(f"wrote {out}")
    else:
        typer.echo(text)


@app.command()
def graph(name: str = typer.Argument("production")) -> None:
    """Print a graph: scope, pool, tier, deps, and whether a handler exists."""
    from .stages.base import has_handler
    g = orchestrator.graph_for(name)
    for key in g.order:
        s = g.stage(key)
        built = "built" if (s.implemented and has_handler(name, key)) else "todo "
        deps = ", ".join(f"{d.stage}[{d.kind.value}]" for d in s.deps) or "-"
        typer.echo(f"{built} {key:22} {s.scope.value:5} {s.pool.value:7} {s.tier:9} ← {deps}")
        if s.description:
            typer.echo(f"       {typer.style(s.description, fg=typer.colors.BRIGHT_BLACK)}")


@app.command()
def verify(keep: bool = typer.Option(False, "--keep", help="leave the fixture in the db")) -> None:
    """Run the Phase 1 exit criteria end to end and print a pass/fail report."""
    from .verify import run_phase1_verification
    ok = run_phase1_verification(log=typer.echo, keep=keep)
    raise typer.Exit(0 if ok else 1)


def main() -> None:
    try:
        app()
    except (LookupError, KeyError) as e:
        typer.echo(f"error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
