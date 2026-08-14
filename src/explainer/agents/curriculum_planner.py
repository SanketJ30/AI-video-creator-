"""Curriculum planning — Sequence v0.2 §6 Stage 2b.

    "2b. Curriculum planning → modules and videos, mapped to objectives,
     sequenced by the DAG, with per-video duration budgets."

The planner groups taught objectives into videos and titles them. It does NOT
choose the order: §8's first row says video boundaries are driven by the
objective DAG, split at objective boundaries. `check_dag`'s topological sort
already produced that order, and this module enforces it in code afterwards
rather than trusting the model to have respected it.

Two deterministic checks run on the model's output and are HARD ERRORS, not
findings (§7.1 rule 4 — deterministic checks beat agentic checks):

  * no video carries more than two objectives (§5.3, the hard rule);
  * no video depends on an objective taught by a later video.

Both are structural: a plan that breaks either is not a worse plan, it is an
unusable one, and every scene generated from it would inherit the break. They
raise rather than returning findings because there is nothing a human could
usefully approve here.

Script type comes from §8's row "Script type per video | Bloom level + knowledge
type (procedural → Procedure/Demo; conceptual → Explainer/Compare)". That table
covers two knowledge types. `script_type_for` raises on the other two rather
than guessing a mapping the spec does not state.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .. import db, escalation, prompts
from ..brief import CourseBrief
from ..config import settings
from ..objectives import Bloom, KnowledgeType, Objective
from . import objective_extractor as ox

AGENT = "curriculum_planner"
PROMPT = "curriculum_planner"
MAX_REPAIRS = 2
MAX_TOKENS = 8000

# §9.2 Segmenting: "Video length hard cap 6:00, target 3-5."
HARD_CAP_SECONDS = 360
MAX_OBJECTIVES_PER_VIDEO = 2          # §5.3, hard rule

OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "videos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string"},
                    "title": {"type": "string"},
                    "objective_refs": {"type": "array", "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                },
                "required": ["ref", "title", "objective_refs", "rationale"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["videos", "notes"],
    "additionalProperties": False,
}


class PlanError(RuntimeError):
    """A structurally unusable plan. Not a finding — nothing to approve."""


@dataclass
class PlannedVideo:
    ref: str
    title: str
    objective_refs: list[str]
    rationale: str = ""
    script_type: str = ""
    target_seconds: int = 0
    ordinal: int = 0


@dataclass
class CurriculumPlan:
    videos: list[PlannedVideo]
    notes: str = ""
    provenance: dict = field(default_factory=dict)
    attempts: list = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return round(sum(a.cost_usd for a in self.attempts), 6)


# ------------------------------------------------------------- script type

def script_type_for(objectives: list[Objective]) -> str:
    """§8: "Script type per video | Bloom level + knowledge type
    (procedural → Procedure/Demo; conceptual → Explainer/Compare)".

    The spec states two knowledge types. `factual` and `metacognitive` are not
    covered, and this course does not exercise them, so they raise. Guessing a
    mapping for a branch no data covers would put an unreviewed decision into
    the schema where it looks like spec.

    The conceptual row is itself ambiguous ("Explainer/Compare"). §9.1's
    Bloom→treatment table breaks the tie: Analyze is "compare/contrast, error
    hunt", so an analyze-level conceptual video is a compare-contrast and
    everything else conceptual is an explainer.
    """
    if not objectives:
        raise PlanError("cannot choose a script type for a video with no objectives")
    # The most demanding objective drives the video's shape — a video that
    # teaches an apply-level skill is not an explainer just because it also
    # restates a definition.
    lead = max(objectives, key=lambda o: o.bloom_level.rank)
    ktype = lead.knowledge_type

    if ktype is KnowledgeType.PROCEDURAL:
        return "procedure_demo"
    if ktype is KnowledgeType.CONCEPTUAL:
        return "compare_contrast" if lead.bloom_level is Bloom.ANALYZE else "explainer"
    raise NotImplementedError(
        f"§8's script-type table covers procedural and conceptual knowledge "
        f"types only; objective '{lead.ref}' is {ktype.value}. Add the row to "
        f"Sequence v0.2 §8 and then to script_type_for — do not guess it here."
    )


# ------------------------------------------------------- deterministic gates

def check_plan(videos: list[PlannedVideo], objectives: list[Objective],
               teaching_order: list[str]) -> None:
    """Hard structural checks. Raises `PlanError` on the first real problem.

    Deliberately not a ValidationReport: every failure here makes the plan
    unusable rather than merely worse, so there is no severity to model and
    nothing for a human to weigh.
    """
    by_ref = {o.ref: o for o in objectives}
    taught = {o.ref for o in objectives if not o.assumed}
    assumed = {o.ref for o in objectives if o.assumed}

    for v in videos:
        if len(v.objective_refs) > MAX_OBJECTIVES_PER_VIDEO:
            raise PlanError(
                f"video '{v.ref}' carries {len(v.objective_refs)} objectives "
                f"({', '.join(v.objective_refs)}); §5.3 allows at most "
                f"{MAX_OBJECTIVES_PER_VIDEO}.")
        if not v.objective_refs:
            raise PlanError(f"video '{v.ref}' carries no objectives")
        for ref in v.objective_refs:
            if ref not in by_ref:
                raise PlanError(
                    f"video '{v.ref}' references objective '{ref}', which is not "
                    f"in the graph")
            if ref in assumed:
                raise PlanError(
                    f"video '{v.ref}' carries assumed objective '{ref}'; assumed "
                    f"objectives are the foundation, not content to teach")

    placed = [ref for v in videos for ref in v.objective_refs]
    if len(placed) != len(set(placed)):
        dupes = sorted({r for r in placed if placed.count(r) > 1})
        raise PlanError(f"objective(s) {dupes} appear in more than one video")

    missing = taught - set(placed)
    if missing:
        raise PlanError(
            f"taught objective(s) {sorted(missing)} were not placed in any video")

    # Prerequisite ordering. An objective may depend on something assumed, or on
    # something taught in this video or an earlier one — never on a later video.
    video_of = {ref: i for i, v in enumerate(videos) for ref in v.objective_refs}
    for v_index, v in enumerate(videos):
        for ref in v.objective_refs:
            for prereq in by_ref[ref].prerequisites:
                if prereq in assumed:
                    continue
                where = video_of.get(prereq)
                if where is None:
                    raise PlanError(
                        f"objective '{ref}' in video '{v.ref}' depends on '{prereq}', "
                        f"which no video teaches")
                if where > v_index:
                    raise PlanError(
                        f"video '{v.ref}' teaches '{ref}', which depends on "
                        f"'{prereq}' taught later in '{videos[where].ref}'. The "
                        f"objective DAG derives the order; the plan must follow it.")

    # The DAG's own order is the authority (§8). Placing objectives in an order
    # that contradicts it is the same error as the check above, seen globally.
    rank = {ref: i for i, ref in enumerate(teaching_order)}
    seen: list[int] = [rank[r] for r in placed if r in rank]
    if seen != sorted(seen):
        raise PlanError(
            f"video order {[v.ref for v in videos]} contradicts the teaching order "
            f"derived from the prerequisite DAG ({' -> '.join(teaching_order)})")


# ------------------------------------------------------------------- parse

def parse(raw: str, objectives: list[Objective], brief: CourseBrief
          ) -> tuple[list[PlannedVideo], str]:
    problems: list[str] = []
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ox.SchemaError([f"response is not valid JSON: {e}"]) from None
    if not isinstance(doc, dict):
        raise ox.SchemaError([f"top level must be an object, got {type(doc).__name__}"])

    raw_videos = doc.get("videos")
    if not isinstance(raw_videos, list) or not raw_videos:
        raise ox.SchemaError(["'videos' must be a non-empty array"])

    videos: list[PlannedVideo] = []
    seen: set[str] = set()
    for i, v in enumerate(raw_videos):
        where = f"videos[{i}]"
        if not isinstance(v, dict):
            problems.append(f"{where}: must be an object")
            continue
        ref = str(v.get("ref") or "").strip()
        title = str(v.get("title") or "").strip()
        refs = v.get("objective_refs")
        if not ref:
            problems.append(f"{where}: 'ref' is required")
            continue
        if ref in seen:
            problems.append(f"{where}: duplicate ref '{ref}'")
            continue
        seen.add(ref)
        if not title:
            problems.append(f"{where}: 'title' is required")
        if not isinstance(refs, list) or not refs or not all(isinstance(r, str) for r in refs):
            problems.append(f"{where}: 'objective_refs' must be a non-empty array of refs")
            continue
        videos.append(PlannedVideo(
            ref=ref, title=title, objective_refs=[r.strip() for r in refs],
            rationale=str(v.get("rationale") or "").strip(),
            ordinal=len(videos) + 1))

    if problems:
        raise ox.SchemaError(problems)

    by_ref = {o.ref: o for o in objectives}
    for v in videos:
        known = [by_ref[r] for r in v.objective_refs if r in by_ref]
        if known:
            v.script_type = script_type_for(known)
        v.target_seconds = min(brief.target_seconds_per_video, HARD_CAP_SECONDS)
    return videos, str(doc.get("notes") or "").strip()


# ------------------------------------------------------------------- plan

def plan(conn, course_id: str | None, brief: CourseBrief,
         objectives: list[Objective], teaching_order: list[str], *,
         client=None, model: str | None = None) -> CurriculumPlan:
    """Group taught objectives into videos. Structural checks are hard errors."""
    ref = prompts.load(PROMPT)
    parts = ox._sections(ref.body)
    missing = {"system", "plan", "repair"} - set(parts)
    if missing:
        raise RuntimeError(
            f"prompts/{PROMPT}.v{ref.file_version}.md is missing section(s) "
            f"{sorted(missing)}")

    model_id = model or settings().models.for_tier("mid")
    client = client or ox._client(conn, course_id)

    taught = [o for o in objectives if not o.assumed]
    plan_input = {
        "brief": brief.to_closure(),
        "teaching_order": teaching_order,
        "objectives": [
            {"ref": o.ref, "statement": o.statement, "bloom_level": o.bloom_level.value,
             "knowledge_type": o.knowledge_type.value, "assumed": o.assumed,
             "prerequisites": o.prerequisites}
            for o in objectives
        ],
        "taught_objective_count": len(taught),
    }
    user_turn = parts["plan"].replace(
        "{plan_input}", json.dumps(plan_input, indent=2, sort_keys=True))
    messages: list[dict] = [{"role": "user", "content": user_turn}]
    attempts: list = []

    for n in range(1, MAX_REPAIRS + 2):
        try:
            raw, usage, content = _call(client, model_id, parts["system"], messages)
        except Exception as e:
            escalation.raise_escalated(
                conn, stage=AGENT, error_class=ox._error_class(e), course_id=course_id,
                message=f"curriculum planning call failed on attempt {n}: "
                        f"{type(e).__name__}: {e}",
                offending_input={"model": model_id, "prompt_version": ref.version},
                next_step="check `explainer doctor`, then re-run "
                          "`explainer curriculum plan`.")
            raise

        attempts.append(ox.Attempt(
            n=n, raw=raw,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cost_usd=ox._price(model_id, usage)))

        try:
            videos, notes = parse(raw, objectives, brief)
        except ox.SchemaError as e:
            attempts[-1].error = str(e)
            if n > MAX_REPAIRS:
                escalation.raise_escalated(
                    conn, stage=AGENT, error_class="llm_schema", course_id=course_id,
                    message=f"curriculum planning produced invalid output "
                            f"{MAX_REPAIRS + 1} times. Last errors: {e}",
                    offending_input={"last_raw_response": raw[:8000],
                                     "problems": e.problems},
                    next_step="read the raw response. Fix "
                              "prompts/curriculum_planner.v1.md (bump to v2) or "
                              "OUTPUT_SCHEMA. Do not hand-edit the output.")
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user",
                 "content": parts["repair"].replace("{errors}", e.as_prompt_text())},
            ]
            continue

        # Structural gates. These raise — see the module docstring.
        check_plan(videos, objectives, teaching_order)
        return CurriculumPlan(
            videos=videos, notes=notes, attempts=attempts,
            provenance={
                "agent": AGENT, "prompt_version": ref.version,
                "model_version": model_id, "brief_version": brief.version,
                "attempt": n,
                "planned_at": datetime.now(UTC).isoformat(timespec="seconds"),
            })

    raise AssertionError("unreachable")


def _call(client, model: str, system: str, messages: list[dict]):
    resp = client.messages.create(
        model=model, max_tokens=MAX_TOKENS,
        system=[{"type": "text", "text": system,
                 "cache_control": {"type": "ephemeral"}}],
        thinking={"type": "adaptive"},
        output_config={"effort": "high",
                       "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=messages,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"model refused: {getattr(resp, 'stop_details', None)}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError(f"response hit max_tokens ({MAX_TOKENS})")
    return ("".join(b.text for b in resp.content if b.type == "text"),
            resp.usage, resp.content)


# ------------------------------------------------------------- persistence

def save(conn, course_id: str, plan: CurriculumPlan,
         objective_ids: dict[str, str]) -> None:
    """Write videos_v2 + video_objectives. Replaces the course's plan wholesale.

    Deliberately does NOT write duration_value/duration_rate: those are derived
    from TTS (R5) and authoring them here would make a guess look like a
    measurement. `target_seconds` is the budget, and it lives in its own column.
    """
    db.execute(conn, "delete from videos_v2 where course_id = %s", (course_id,))
    for v in plan.videos:
        row = db.one(conn, """
            insert into videos_v2(course_id, ordinal, ref, title, script_type,
                                  target_seconds, provenance)
            values (%s,%s,%s,%s,%s,%s,%s) returning id
        """, (course_id, v.ordinal, v.ref, v.title, v.script_type, v.target_seconds,
              json.dumps({**plan.provenance, "rationale": v.rationale})))
        for ref in v.objective_refs:
            if ref in objective_ids:
                db.execute(conn, """
                    insert into video_objectives(video_id, objective_id)
                    values (%s,%s) on conflict do nothing
                """, (str(row["id"]), objective_ids[ref]))


def load(conn, course_id: str) -> list[dict]:
    rows = db.query(conn, """
        select v.id, v.ordinal, v.ref, v.title, v.script_type, v.target_seconds,
               v.provenance
          from videos_v2 v where v.course_id = %s order by v.ordinal""", (course_id,))
    for r in rows:
        r["objective_refs"] = [x["ref"] for x in db.query(conn, """
            select o.ref from video_objectives vo
              join objectives o on o.id = vo.objective_id
             where vo.video_id = %s order by o.ref""", (str(r["id"]),))]
    return rows


def objective_ids_for(conn, course_id: str) -> dict[str, str]:
    return {r["ref"]: str(r["id"]) for r in db.query(
        conn, "select id, ref from objectives where course_id = %s", (course_id,))}
