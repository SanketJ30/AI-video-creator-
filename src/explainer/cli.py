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

import typer

from . import brief as brief_mod
from . import coursegraph, db, gagne, goldgraph, prose, orchestrator, worker
from . import manifest as manifest_mod
from .agents import objective_extractor
from .config import settings
from .orchestrator import load_video

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="AI-native explainer video pipeline (PRD v4).")
db_app = typer.Typer(no_args_is_help=True, help="Schema management.")
series_app = typer.Typer(no_args_is_help=True, help="Series (§10.3 curriculum scope).")
video_app = typer.Typer(no_args_is_help=True, help="Videos.")
beat_app = typer.Typer(no_args_is_help=True, help="Beats — the atomic unit (§5.3).")
course_app = typer.Typer(no_args_is_help=True,
                         help="Courses and the Course Brief (§6 Stage 1).")
objectives_app = typer.Typer(no_args_is_help=True,
                             help="The objective graph (§5.3) — the course spine.")
curriculum_app = typer.Typer(no_args_is_help=True,
                             help="Curriculum planning (§6 Stage 2b).")
script_app = typer.Typer(no_args_is_help=True,
                         help="Script generation into Gagné slots (§6 Stage 2c).")
app.add_typer(db_app, name="db")
app.add_typer(series_app, name="series")
app.add_typer(video_app, name="video")
app.add_typer(beat_app, name="beat")
app.add_typer(course_app, name="course")
app.add_typer(objectives_app, name="objectives")
app.add_typer(curriculum_app, name="curriculum")
app.add_typer(script_app, name="script")

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
    curriculum: str | None = typer.Option(None, "--curriculum", help="path to curriculum.yaml"),
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


# -------------------------------------------------------------------- course

@course_app.command("create")
def course_create(
    slug: str,
    title: str = typer.Option("", "--title", help="defaults to the slug"),
    description: str = typer.Option("", "--description", "-d",
                                    help="what the course is about — the extractor reads this"),
    source: list[str] = typer.Option([], "--source",
                                     help="source material ref (repeatable): url, doc id or asset sha"),
    level: str = typer.Option(brief_mod.DEFAULT_AUDIENCE_LEVEL, "--level"),
    prior: list[str] = typer.Option([], "--prior",
                                    help="prior knowledge, repeatable — drives `assumed` objectives"),
    native_ratio: float = typer.Option(0.0, "--native-language-ratio"),
    seconds: int = typer.Option(brief_mod.DEFAULT_TARGET_SECONDS, "--seconds",
                                help="target seconds per video"),
    locale: str = typer.Option(brief_mod.DEFAULT_LOCALE, "--locale",
                               help="comma-separated; the first is primary"),
    tone: str = typer.Option(brief_mod.DEFAULT_TONE, "--tone"),
    brand: str | None = typer.Option(None, "--brand-kit"),
    reference: str | None = typer.Option(None, "--reference-video"),
) -> None:
    """Create a course and version 1 of its Course Brief.

    Every field has a defensible default (see brief.py) — a slug alone produces
    a complete, usable brief. Nothing here blocks generation.
    """
    b = brief_mod.CourseBrief(
        title=title or slug,
        description=description,
        source_material=tuple(source),
        audience=brief_mod.Audience(level=level, prior_knowledge=tuple(prior),
                                    native_language_ratio=native_ratio),
        target_seconds_per_video=seconds,
        locales=tuple(x.strip() for x in locale.split(",") if x.strip()),
        brand_kit_ref=brand, tone=tone, reference_video_ref=reference,
    )
    with db.tx() as conn:
        course_id = brief_mod.ensure_course(conn, slug, b)
        saved = brief_mod.save(conn, course_id, b,
                               provenance={"source": "cli", "command": "course create"})
    typer.echo(f"course {slug} ready — brief v{saved.version}")


@course_app.command("list")
def course_list() -> None:
    with db.tx() as conn:
        rows = brief_mod.list_courses(conn)
    for r in rows:
        typer.echo(f"{r['slug']:28} brief=v{r['brief_version'] or 0} "
                   f"objectives={r['objectives']:<3} {r['locale']}  {r['title']}")
    typer.echo(f"{len(rows)} courses")


@course_app.command("brief")
def course_brief(slug: str,
                 version: int | None = typer.Option(None, "--version"),
                 history: bool = typer.Option(False, "--history")) -> None:
    """Show a Course Brief, or its version history."""
    with db.tx() as conn:
        course_id = brief_mod.course_id_for(conn, slug)
        if history:
            for r in brief_mod.history(conn, course_id):
                typer.echo(f"v{r['version']:<3} {r['created_at']:%Y-%m-%d %H:%M}  "
                           f"{jsonlib.dumps(r['provenance'])}")
            return
        b = brief_mod.load(conn, course_id, version)
    typer.echo(f"# {slug} brief v{b.version}")
    typer.echo(b.render_for_prompt())


@course_app.command("edit")
def course_edit(
    slug: str,
    description: str | None = typer.Option(None, "--description", "-d"),
    tone: str | None = typer.Option(None, "--tone"),
    seconds: int | None = typer.Option(None, "--seconds"),
    level: str | None = typer.Option(None, "--level"),
    prior: list[str] | None = typer.Option(None, "--prior",
                                              help="replaces prior knowledge entirely"),
    note: str | None = typer.Option(None, "--note", help="why you changed it"),
    regenerate: bool = typer.Option(False, "--regenerate",
                                    help="re-extract the objective graph from the edited brief"),
) -> None:
    """Edit the brief as a NEW version, optionally regenerating from it.

    §6 Stage 1: the brief is versioned and editable, so this never overwrites a
    brief a human approved — it writes the next version.
    """
    changes: dict = {}
    if description is not None:
        changes["description"] = description
    if tone is not None:
        changes["tone"] = tone
    if seconds is not None:
        changes["target_seconds_per_video"] = seconds
    audience: dict = {}
    if level is not None:
        audience["level"] = level
    if prior:
        audience["prior_knowledge"] = list(prior)
    if audience:
        changes["audience"] = audience
    if not changes:
        typer.echo("nothing to change", err=True)
        raise typer.Exit(1)

    with db.tx() as conn:
        course_id = brief_mod.course_id_for(conn, slug)
        if regenerate:
            outcome = _run_extraction(conn, course_id, slug, changes=changes, note=note)
            _report_extraction(conn, course_id, slug, outcome)
        else:
            saved = brief_mod.revise(conn, course_id, changes, note=note)
            typer.echo(f"{slug} brief v{saved.version} written "
                       f"({', '.join(sorted(changes))} changed) — "
                       f"`explainer objectives extract {slug}` to rebuild the graph")


# ---------------------------------------------------------------- objectives

def _run_extraction(conn, course_id: str, slug: str,
                    changes: dict | None = None, note: str | None = None):
    from .escalation import Escalated
    try:
        if changes:
            return brief_mod.regenerate_from_edited_brief(conn, course_id, changes,
                                                          note=note)
        b = brief_mod.load(conn, course_id)
        return objective_extractor.extract(conn, course_id, b)
    except Escalated as e:
        # Invariant 7: an escalation is a state, not a stack trace. It is
        # already recorded; print it in the form a human can act on.
        typer.echo(typer.style(e.render(), fg=typer.colors.MAGENTA), err=True)
        raise typer.Exit(2) from None


def _report_extraction(conn, course_id: str, slug: str, outcome) -> None:
    graph = coursegraph.save(conn, course_id, outcome.objectives, outcome.items,
                             provenance=outcome.provenance,
                             rationales=outcome.rationales,
                             learner_facing=outcome.learner_facing)
    typer.echo(coursegraph.render(graph))
    typer.echo("")
    typer.echo(f"{len(outcome.objectives)} objectives, {len(outcome.items)} assessment "
               f"items, {len(outcome.attempts)} model call(s), "
               f"${outcome.cost_usd:.4f}")
    typer.echo(f"teaching order: {' -> '.join(graph.teaching_order)}")
    if outcome.out_of_scope:
        # Printed, not buried: the boundary the model drew is the difference
        # between a scoped course and a silently truncated one, and it is the
        # thing a human most needs to disagree with at review.
        typer.echo("")
        typer.echo(typer.style("declared out of scope:", fg=typer.colors.CYAN))
        typer.echo(f"  {outcome.out_of_scope}")
    typer.echo("")
    colour = typer.colors.GREEN if outcome.report.ok else typer.colors.RED
    typer.echo(typer.style(outcome.report.render(), fg=colour))
    if not outcome.report.ok:
        typer.echo("")
        typer.echo("blocking findings are NOT auto-fixed — edit the brief and "
                   f"`explainer course edit {slug} --regenerate`, or fix the graph "
                   "by hand.")


@objectives_app.command("extract")
def objectives_extract(
    slug: str,
    show_raw: bool = typer.Option(False, "--raw",
                                  help="print the model's raw response before parsing"),
    raw_out: str | None = typer.Option(None, "--raw-out",
                                          help="write every attempt's raw response here"),
    model: str | None = typer.Option(None, "--model",
                                        help="override the pinned model FOR THIS RUN only "
                                             "(§6.6: the pin lives in .env, not here)"),
) -> None:
    """Extract the objective graph from the course's latest brief.

    The first real model call. Output is validated by objectives.py — code, not
    a model — and blocking findings are reported, never silently repaired.
    """
    with db.tx() as conn:
        course_id = brief_mod.course_id_for(conn, slug)
        if model:
            from .escalation import Escalated
            b = brief_mod.load(conn, course_id)
            try:
                outcome = objective_extractor.extract(conn, course_id, b, model=model)
            except Escalated as e:
                typer.echo(typer.style(e.render(), fg=typer.colors.MAGENTA), err=True)
                raise typer.Exit(2) from None
        else:
            outcome = _run_extraction(conn, course_id, slug)

        if show_raw:
            for a in outcome.attempts:
                typer.echo(typer.style(
                    f"--- raw response, attempt {a.n} "
                    f"({a.input_tokens} in / {a.output_tokens} out) ---",
                    fg=typer.colors.BRIGHT_BLACK))
                typer.echo(a.raw)
                if a.error:
                    typer.echo(typer.style(f"    rejected: {a.error}",
                                           fg=typer.colors.YELLOW))
            typer.echo("")
        if raw_out:
            with open(raw_out, "w", encoding="utf-8") as fh:
                jsonlib.dump([{"attempt": a.n, "raw": a.raw, "error": a.error,
                               "input_tokens": a.input_tokens,
                               "output_tokens": a.output_tokens} for a in outcome.attempts],
                             fh, indent=2)
            typer.echo(f"raw responses written to {raw_out}")

        _report_extraction(conn, course_id, slug, outcome)
    raise typer.Exit(0 if outcome.report.ok else 1)


@objectives_app.command("show")
def objectives_show(slug: str,
                    as_json: bool = typer.Option(False, "--json")) -> None:
    """Render the stored objective graph and its ValidationReport."""
    with db.tx() as conn:
        course_id = brief_mod.course_id_for(conn, slug)
        graph = coursegraph.load(conn, course_id)
    if not graph.objectives:
        typer.echo(f"no objective graph for '{slug}' — run "
                   f"`explainer objectives extract {slug}`", err=True)
        raise typer.Exit(1)
    report = graph.validate()
    if as_json:
        typer.echo(jsonlib.dumps({
            "teaching_order": graph.teaching_order,
            "objectives": [{"ref": o.ref, "verb": o.verb, "object": o.object,
                            "bloom_level": o.bloom_level.value,
                            "knowledge_type": o.knowledge_type.value,
                            "assumed": o.assumed,
                            "prerequisites": o.prerequisites} for o in graph.objectives],
            "findings": [{"rule": f.rule, "severity": f.severity,
                          "subject": f.subject, "message": f.message, "fix": f.fix}
                         for f in report.findings],
            "ok": report.ok,
        }, indent=2))
        raise typer.Exit(0 if report.ok else 1)

    typer.echo(coursegraph.render(graph))
    typer.echo("")
    typer.echo(f"teaching order: {' -> '.join(graph.teaching_order)}")
    typer.echo("")
    typer.echo(typer.style(report.render(),
                           fg=typer.colors.GREEN if report.ok else typer.colors.RED))
    raise typer.Exit(0 if report.ok else 1)


@objectives_app.command("diff")
def objectives_diff(
    slug: str,
    against: str = typer.Option(..., "--against",
                                help="path to a hand-authored gold graph yaml"),
    alignment: str | None = typer.Option(
        None, "--alignment",
        help="hand-authored alignment yaml; used when it has an entry recorded "
             "for this run, otherwise the scorer runs and says it is approximate"),
    run: str | None = typer.Option(
        None, "--run", help="force a specific run id from the alignment file"),
) -> None:
    """Compare the stored graph against a hand-authored gold graph.

    Reports missing objectives, extra objectives, wrong Bloom levels and wrong
    edges. Every diff states how it aligned the two graphs: HAND when a human
    recorded the mapping for this exact run, APPROXIMATE when the content scorer
    guessed. The scorer cannot match a gold objective the extractor split across
    several, so on a granularity mismatch its answer is close to meaningless —
    which is why the label is never omitted.
    """
    gold = goldgraph.load_gold(against)
    with db.tx() as conn:
        course_id = brief_mod.course_id_for(conn, slug)
        graph = coursegraph.load(conn, course_id)
        # Read inside the transaction: the diff runs after the block closes.
        brief_version = brief_mod.load(conn, course_id).version
    if not graph.objectives:
        typer.echo(f"no objective graph for '{slug}' — run "
                   f"`explainer objectives extract {slug}` first", err=True)
        raise typer.Exit(1)

    # The prompt version the stored graph was produced by, so the alignment file
    # can only match the run it was actually written for.
    prompt_version = next((p.get("prompt_version", "")
                           for p in graph.provenance.values() if p.get("prompt_version")), "")
    align_file = goldgraph.load_alignment(alignment) if alignment else None
    try:
        d = goldgraph.diff(graph.objectives, gold, alignment=align_file,
                           prompt_version=prompt_version, run=run,
                           brief_version=brief_version)
    except ValueError as e:
        typer.echo(typer.style(str(e), fg=typer.colors.RED), err=True)
        raise typer.Exit(2) from None

    if align_file and d.approximate:
        typer.echo(typer.style(
            f"note: {align_file.path.name} has no entry recorded for this run "
            f"({prompt_version or 'unknown prompt version'}, "
            f"{len(graph.objectives)} objectives) — falling back to the scorer.",
            fg=typer.colors.YELLOW))
    typer.echo(f"gold: {gold.path}  ({gold.topic})")
    typer.echo(d.render())
    if gold.notes:
        typer.echo("")
        typer.echo("the gold file's own notes on what to watch for:")
        for n in gold.notes:
            typer.echo(f"  - {n.strip()}")
    clean = not (d.missing or d.extra or d.bloom or d.missing_edges or d.extra_edges)
    raise typer.Exit(0 if clean else 1)


@objectives_app.command("escalations")
def objectives_escalations(slug: str | None = typer.Argument(None)) -> None:
    """Open escalations — the queue a human has to unblock (invariant 7)."""
    from . import escalation
    with db.tx() as conn:
        course_id = brief_mod.course_id_for(conn, slug) if slug else None
        rows = escalation.open_escalations(conn, course_id)
    for r in rows:
        typer.echo(f"{r['created_at']:%Y-%m-%d %H:%M}  {r['stage']:22} "
                   f"[{r['error_class']}] {r['error'][:90]}")
        typer.echo(f"    next step: {r['next_step']}")
    typer.echo(f"{len(rows)} open")


# ---------------------------------------------------------------- curriculum

@curriculum_app.command("plan")
def curriculum_plan(slug: str,
                    show_raw: bool = typer.Option(False, "--raw")) -> None:
    """Group taught objectives into videos (§6 Stage 2b).

    The order is not a choice: it comes from the objective DAG's topological
    sort, and a plan that contradicts it is a hard error, not a finding.
    """
    from .agents import curriculum_planner as cp
    from .escalation import Escalated
    with db.tx() as conn:
        course_id = brief_mod.course_id_for(conn, slug)
        b = brief_mod.load(conn, course_id)
        graph = coursegraph.load(conn, course_id)
        if not graph.objectives:
            typer.echo(f"no objective graph for '{slug}' — run "
                       f"`explainer objectives extract {slug}` first", err=True)
            raise typer.Exit(1)
        try:
            result = cp.plan(conn, course_id, b, graph.objectives,
                             graph.teaching_order)
        except Escalated as e:
            typer.echo(typer.style(e.render(), fg=typer.colors.MAGENTA), err=True)
            raise typer.Exit(2) from None
        except cp.PlanError as e:
            typer.echo(typer.style(f"PLAN REJECTED: {e}", fg=typer.colors.RED), err=True)
            typer.echo("This is a structural failure, not a quality one — the plan "
                       "cannot be used and was not saved.", err=True)
            raise typer.Exit(2) from None

        if show_raw:
            for a in result.attempts:
                typer.echo(typer.style(f"--- raw, attempt {a.n} ---",
                                       fg=typer.colors.BRIGHT_BLACK))
                typer.echo(a.raw)
        cp.save(conn, course_id, result, cp.objective_ids_for(conn, course_id))

    for v in result.videos:
        typer.echo(f"{v.ordinal}. {v.ref:<4} [{v.script_type}] {v.title}")
        typer.echo(f"       objectives: {', '.join(v.objective_refs)}  "
                   f"budget: {v.target_seconds}s")
        if v.rationale:
            typer.echo(typer.style(f"       {v.rationale}",
                                   fg=typer.colors.BRIGHT_BLACK))
    typer.echo("")
    typer.echo(f"{len(result.videos)} video(s), {len(result.attempts)} model call(s), "
               f"${result.cost_usd:.4f}")
    if result.notes:
        typer.echo("")
        typer.echo(typer.style(f"planner notes: {result.notes}", fg=typer.colors.CYAN))


@curriculum_app.command("show")
def curriculum_show(slug: str) -> None:
    """The stored plan."""
    from .agents import curriculum_planner as cp
    with db.tx() as conn:
        course_id = brief_mod.course_id_for(conn, slug)
        rows = cp.load(conn, course_id)
    if not rows:
        typer.echo(f"no curriculum plan for '{slug}' — run "
                   f"`explainer curriculum plan {slug}`", err=True)
        raise typer.Exit(1)
    for r in rows:
        typer.echo(f"{r['ordinal']}. {r['ref']:<4} [{r['script_type']}] {r['title']}")
        typer.echo(f"       objectives: {', '.join(r['objective_refs'])}  "
                   f"budget: {r['target_seconds']}s")
    typer.echo(f"\n{len(rows)} video(s)")


# -------------------------------------------------------------------- script

def _script_context(conn, slug: str, video_ref: str):
    from .agents import script_writer as sw
    course_id = brief_mod.course_id_for(conn, slug)
    return course_id, sw.video_row(conn, course_id, video_ref)


@script_app.command("generate")
def script_generate(slug: str, video_ref: str,
                    show_raw: bool = typer.Option(False, "--raw"),
                    raw_out: str | None = typer.Option(None, "--raw-out")) -> None:
    """Fill one video's Gagné slot form (§6 Stage 2c)."""
    from .agents import script_writer as sw
    from .escalation import Escalated
    with db.tx() as conn:
        course_id, video = _script_context(conn, slug, video_ref)
        b = brief_mod.load(conn, course_id)
        graph = coursegraph.load(conn, course_id)
        plan_rows = _course_position(conn, course_id, video)
        try:
            draft = sw.generate(conn, course_id, b, video, graph.objectives,
                                learner_facing=graph.learner_facing,
                                position=plan_rows)
        except Escalated as e:
            typer.echo(typer.style(e.render(), fg=typer.colors.MAGENTA), err=True)
            raise typer.Exit(2) from None
        except gagne.BudgetError as e:
            typer.echo(typer.style(f"BUDGET: {e}", fg=typer.colors.RED), err=True)
            raise typer.Exit(2) from None

        if show_raw:
            for a in draft.attempts:
                typer.echo(typer.style(
                    f"--- raw, attempt {a.n} ({a.input_tokens} in / "
                    f"{a.output_tokens} out) ---", fg=typer.colors.BRIGHT_BLACK))
                typer.echo(a.raw)
        if raw_out:
            with open(raw_out, "w", encoding="utf-8") as fh:
                jsonlib.dump([{"attempt": a.n, "raw": a.raw, "error": a.error,
                               "input_tokens": a.input_tokens,
                               "cache_creation_tokens": a.cache_creation_tokens,
                               "cache_read_tokens": a.cache_read_tokens,
                               "output_tokens": a.output_tokens} for a in draft.attempts],
                             fh, indent=2)
            typer.echo(f"raw responses written to {raw_out}")

        sw.save(conn, str(video["id"]), draft,
                {o.ref: i for o, i in _objective_id_map(conn, course_id)})
        scenes = sw.load(conn, str(video["id"]))
        report = prose.check_script(
            scenes, technical=True,
            is_final_video=plan_rows["ordinal"] == plan_rows["total"])
        prose.save_findings(conn, str(video["id"]), report,
                            _scene_id_map(conn, str(video["id"])))

    typer.echo(f"{len(draft.scenes)} scenes, {len(draft.attempts)} model call(s), "
               f"${draft.cost_usd:.4f}")
    typer.echo("")
    typer.echo(typer.style(report.render(),
                           fg=typer.colors.GREEN if report.ok else typer.colors.RED))
    raise typer.Exit(0 if report.ok else 1)


def _objective_id_map(conn, course_id: str):
    from .agents import curriculum_planner as cp
    ids = cp.objective_ids_for(conn, course_id)
    graph = coursegraph.load(conn, course_id)
    return [(o, ids[o.ref]) for o in graph.objectives if o.ref in ids]


def _course_position(conn, course_id: str, video: dict) -> dict:
    """Where this video sits in the course, for the retain slot.

    Without this the final video has no way to know a forward reference is a
    lie — which is exactly what week 3 shipped.
    """
    from .agents import curriculum_planner as cp
    rows = cp.load(conn, course_id)
    total = len(rows)
    ordinal = video["ordinal"]
    nxt = next((r for r in rows if r["ordinal"] == ordinal + 1), None)
    brief_row = db.one(conn, """select brief from course_briefs
                                where course_id = %s order by version desc limit 1""",
                       (course_id,))
    return {
        "ordinal": ordinal, "total": total,
        "next": ({"title": nxt["title"], "objective_refs": nxt["objective_refs"]}
                 if nxt else None),
        "out_of_scope": (brief_row or {}).get("brief", {}).get("out_of_scope", ""),
    }


def _scene_id_map(conn, video_id: str) -> dict:
    return {r["ref"]: str(r["id"]) for r in db.query(
        conn, "select id, ref from scenes where video_id = %s", (video_id,))}


@script_app.command("show")
def script_show(slug: str, video_ref: str,
                spans: bool = typer.Option(True, "--spans/--no-spans",
                                           help="render span ids (Gate A needs them)")) -> None:
    """Slots, narration, span ids and findings for one video.

    Span ids are shown by default because a human reviewing at Gate A needs to
    see what a cue could anchor to (R3/R4) — a wall of prose hides the thing the
    storyboard will point at.
    """
    from .agents import script_writer as sw
    with db.tx() as conn:
        course_id, video = _script_context(conn, slug, video_ref)
        scenes = sw.load(conn, str(video["id"]))
        findings = db.query(conn, """
            select rule, severity, message, s.ref as scene_ref
              from linter_findings lf left join scenes s on s.id = lf.scene_id
             where lf.video_id = %s order by lf.severity, s.ref""",
                            (str(video["id"]),))
    if not scenes:
        typer.echo(f"no script for '{video_ref}' — run "
                   f"`explainer script generate {slug} {video_ref}`", err=True)
        raise typer.Exit(1)

    typer.echo(f"{video['ref']}  [{video['script_type']}]  {video['title']}")
    typer.echo(f"budget {video['target_seconds']}s  objectives "
               f"{', '.join(video['objective_refs'])}")
    typer.echo("")
    by_scene: dict = {}
    for f in findings:
        by_scene.setdefault(f["scene_ref"], []).append(f)

    for s in scenes:
        meta = s["pedagogy_meta"] or {}
        dur = "null" if s["duration_value"] is None else str(s["duration_value"])
        typer.echo(typer.style(
            f"{s['ordinal']:>2}. {s['ref']}  {s['gagne_slot']:<10} "
            f"target {meta.get('duration_target_seconds')}s  duration={dur}  "
            f"{s['timing_sensitivity']}  obj={s['objective_ref']}  "
            f"load={meta.get('element_interactivity')}",
            fg=typer.colors.CYAN))
        if meta.get("new_terms"):
            typer.echo(f"      new terms: {', '.join(meta['new_terms'])}")
        for sp in (s["narration"] or []):
            if spans:
                typer.echo(f"      {typer.style(sp['id'], fg=typer.colors.BRIGHT_BLACK)}"
                           f"  {sp['text']}")
            else:
                typer.echo(f"      {sp['text']}")
        for f in by_scene.get(s["ref"], []):
            colour = typer.colors.RED if f["severity"] == "blocking" else typer.colors.YELLOW
            typer.echo(typer.style(f"      [{f['severity'].upper()}] {f['rule']}: "
                                   f"{f['message']}", fg=colour))
        typer.echo("")

    total_spans = sum(len(s["narration"] or []) for s in scenes)
    typer.echo(f"{len(scenes)} scenes, {total_spans} spans, {len(findings)} findings")


@script_app.command("gates")
def script_gates(slug: str, video_ref: str,
                 save: bool = typer.Option(False, "--save",
                                           help="rewrite linter_findings")) -> None:
    """Just the prose gate report (§9.6 deterministic gates)."""
    from .agents import script_writer as sw
    with db.tx() as conn:
        course_id, video = _script_context(conn, slug, video_ref)
        scenes = sw.load(conn, str(video["id"]))
        if not scenes:
            typer.echo(f"no script for '{video_ref}'", err=True)
            raise typer.Exit(1)
        pos = _course_position(conn, course_id, video)
        report = prose.check_script(scenes, technical=True,
                                    is_final_video=pos["ordinal"] == pos["total"])
        if save:
            n = prose.save_findings(conn, str(video["id"]), report,
                                    _scene_id_map(conn, str(video["id"])))
            typer.echo(f"{n} findings written to linter_findings")
    typer.echo(typer.style(report.render(),
                           fg=typer.colors.GREEN if report.ok else typer.colors.RED))
    raise typer.Exit(0 if report.ok else 1)


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
              instruction: str | None = typer.Option(None, "--instruction"),
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
            target: str | None = typer.Option(None, "--target", help="stop at this stage"),
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
def diff(ref: str, target: str | None = typer.Option(None, "--target")) -> None:
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
def jobs(ref: str | None = typer.Argument(None),
         state: str | None = typer.Option(None, "--state")) -> None:
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
def manifest(ref: str, out: str | None = typer.Option(None, "--out")) -> None:
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
