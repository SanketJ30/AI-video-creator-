"""Visual planning — Sequence v0.2 §6 Stage 3, §8, §9.1.

One scene in, one `visualSpec` out: which template, and what fills its slots.
The planner does not write narration, does not time anything, and cannot invent
a template — it selects from `templates.TEMPLATES` and fills the parameters that
template declares.

## The animate-vs-static gate

§8's decision table: *"Animate vs static-with-reveal — does the referent
genuinely change over time? If no → static + progressive reveal."* The brief for
this step calls it a hard gate rather than a preference, and it is implemented
as one.

What a deterministic check can and cannot do here matters. Code cannot decide
whether a referent genuinely changes over time — that is a judgment about the
subject matter. What it CAN do is force the claim to be explicit and internally
consistent, so a human reviewing at Gate A sees the reasoning rather than the
conclusion:

    motion == "animate"  requires  referent_changes_over_time == true
                         requires  what_changes is non-empty

A scene claiming motion must name the thing that moves. A scene that names
nothing gets `static_reveal`, and the mismatch is a schema error that goes back
to the model rather than a finding a human has to chase. This turns an
unfalsifiable stylistic call into a falsifiable claim — which is the most a
deterministic gate can honestly do, and it is stated that way rather than
dressed up as motion detection.

## Provenance at decision granularity (R6, §10)

§10's principle: *"every AI decision is a named, addressable, overridable
object"* — not "regenerate the scene" but "make this static instead of
animated". So provenance is recorded per DECISION, not per scene: the template
choice, the motion choice and the slot filling each carry the rule that produced
them, and each is addressable by name. A human overriding one does not disturb
the others.

## What this module does not do

No cues — that is step 3, the signal designer, and cues anchor to narration spans
rather than to anything here. No linting beyond schema and gate validity; the
§9.2/§9.3/§9.4 rules are step 4's job and run over the finished spec.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .. import db, escalation, prompts, templates
from ..brief import CourseBrief
from ..config import settings
from ..objectives import Objective
from ..templates import Template
from . import objective_extractor as ox

AGENT = "visual_planner"
PROMPT = "visual_planner"
MAX_REPAIRS = 2
MAX_TOKENS = 64000

MOTIONS = ("animate", "static_reveal")

OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene_ref": {"type": "string"},
                    "template": {"type": "string"},
                    # A JSON-encoded object, not an object. Structured
                    # outputs reject `additionalProperties: true`, and a
                    # template's parameters are variable BY DESIGN — each
                    # template declares its own. One fixed output schema
                    # cannot express eleven different parameter sets, so the
                    # API validates the envelope and `templates.validate_params`
                    # validates the payload. The check that matters is the
                    # second one; it was never the API's job.
                    "slots_json": {"type": "string"},
                    "motion": {"type": "string", "enum": list(MOTIONS)},
                    "referent_changes_over_time": {"type": "boolean"},
                    "what_changes": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["scene_ref", "template", "slots_json", "motion",
                             "referent_changes_over_time", "what_changes",
                             "rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["scenes"],
    "additionalProperties": False,
}


@dataclass
class Decision:
    """One named, overridable choice (§10). `rule` is what produced it."""

    name: str
    value: str
    rule: str

    def to_json(self) -> dict:
        return {"value": self.value, "rule": self.rule}


@dataclass
class ScenePlan:
    scene_ref: str
    template: Template
    slots: dict
    motion: str
    referent_changes_over_time: bool
    what_changes: str
    rationale: str
    decisions: list[Decision] = field(default_factory=list)

    def visual_spec(self, provenance: dict) -> dict:
        """§5.1: visualSpec is {template, slots{}, cues[], timingSensitivity}.

        `cues` is present and empty: the signal designer (step 3) fills it, and
        a key that appears later is a key downstream code cannot rely on. The
        caption safe area comes from the TEMPLATE, never from the model.
        """
        return {
            "template": self.template.name,
            "template_version": self.template.version,
            "slots": self.slots,
            "cues": [],
            "captionSafeArea": self.template.safe_area.to_json(),
            "motion": self.motion,
            "referent_changes_over_time": self.referent_changes_over_time,
            "what_changes": self.what_changes,
            # §10 makes the storyboard the surface a human edits, and a template
            # choice with no stated reason is one a reviewer can only accept or
            # reject, never correct. The model is required to produce this and
            # `parse` keeps it; it was being dropped here until the review CLI
            # went looking for it.
            "rationale": self.rationale,
            "decisions": {d.name: d.to_json() for d in self.decisions},
            "provenance": provenance,
        }


@dataclass
class VisualPlan:
    scenes: list[ScenePlan]
    provenance: dict = field(default_factory=dict)
    attempts: list = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return round(sum(a.cost_usd for a in self.attempts), 6)


# --------------------------------------------------------------- the gate

def check_motion(scene_ref: str, motion: str, changes: bool,
                 what_changes: str) -> list[str]:
    """§8's animate-vs-static rule, as far as code can honestly take it.

    Not motion detection — a consistency check on the model's own claim. See the
    module docstring for why that is the ceiling.
    """
    problems: list[str] = []
    if motion not in MOTIONS:
        return [f"{scene_ref}: motion {motion!r} is not one of {list(MOTIONS)}"]
    if motion == "animate":
        if not changes:
            problems.append(
                f"{scene_ref}: motion is 'animate' but "
                f"referent_changes_over_time is false. §8: animate only if the "
                f"referent genuinely changes over time, otherwise static with a "
                f"progressive reveal.")
        if not what_changes.strip():
            problems.append(
                f"{scene_ref}: motion is 'animate' but what_changes is empty. "
                f"Name the thing that changes and what it changes from and to, "
                f"or use 'static_reveal'.")
    elif changes and not what_changes.strip():
        problems.append(
            f"{scene_ref}: referent_changes_over_time is true but what_changes "
            f"is empty — say what changes, or set it false.")
    return problems


def check_duration(scene_ref: str, template: Template,
                   budget_seconds: int) -> list[str]:
    """A template outside its duration band cannot land the treatment."""
    if budget_seconds <= 0 or template.fits(budget_seconds):
        return []
    return [f"{scene_ref}: template '{template.name}' holds "
            f"{template.min_sec:.0f}-{template.max_sec:.0f}s but the slot budgets "
            f"{budget_seconds}s. Choose a template whose band contains it."]


# ----------------------------------------------------------------- parse

def parse(raw: str, scenes: list[dict]) -> list[ScenePlan]:
    """Model text → validated plans. Every gate below is structural: a plan that
    fails one is unusable rather than merely worse, so it goes back to the model
    through the repair loop instead of reaching a human as a finding."""
    problems: list[str] = []
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ox.SchemaError([f"response is not valid JSON: {e}"]) from None
    if not isinstance(doc, dict):
        raise ox.SchemaError([f"top level must be an object, got {type(doc).__name__}"])
    got = doc.get("scenes")
    if not isinstance(got, list) or not got:
        raise ox.SchemaError(["'scenes' must be a non-empty array"])

    wanted = {s["ref"]: s for s in scenes}
    plans: dict[str, ScenePlan] = {}
    for i, s in enumerate(got):
        where = f"scenes[{i}]"
        if not isinstance(s, dict):
            problems.append(f"{where}: must be an object")
            continue
        ref = str(s.get("scene_ref") or "").strip()
        if ref not in wanted:
            problems.append(
                f"{where}: scene_ref {s.get('scene_ref')!r} is not one of this "
                f"video's scenes {sorted(wanted)}")
            continue
        if ref in plans:
            problems.append(f"{where}: scene '{ref}' planned more than once")
            continue
        try:
            template = templates.get(str(s.get("template") or ""))
        except templates.TemplateError as e:
            problems.append(f"{ref}: {e}")
            continue

        raw_slots = s.get("slots_json")
        if not isinstance(raw_slots, str) or not raw_slots.strip():
            problems.append(f"{ref}: 'slots_json' must be a JSON object as a string")
            continue
        try:
            slots = json.loads(raw_slots)
        except json.JSONDecodeError as e:
            problems.append(f"{ref}: slots_json is not valid JSON: {e}")
            continue
        if not isinstance(slots, dict):
            problems.append(
                f"{ref}: slots_json decodes to {type(slots).__name__}, not an object")
            continue
        if not template.design_section:
            problems.append(
                f"{ref}: template '{template.name}' has no designed layout "
                f"(ISSUE-20) and is not available. Choose one of "
                f"{sorted(t.name for t in templates.selectable())}.")
        problems += [f"{ref}: {p}" for p in templates.validate_params(template, slots)]

        motion = str(s.get("motion") or "").strip()
        changes = bool(s.get("referent_changes_over_time"))
        what = str(s.get("what_changes") or "")
        problems += check_motion(ref, motion, changes, what)
        problems += check_duration(
            ref, template,
            int((wanted[ref].get("pedagogy_meta") or {}).get(
                "duration_target_seconds") or 0))

        plans[ref] = ScenePlan(
            scene_ref=ref, template=template, slots=slots, motion=motion,
            referent_changes_over_time=changes, what_changes=what.strip(),
            rationale=str(s.get("rationale") or "").strip(),
            decisions=[
                Decision("template", template.name,
                         "§9.1 Bloom-to-treatment; §4.4 composition priority"),
                Decision("motion", motion,
                         "§8 animate only if the referent changes over time"),
                Decision("caption_safe_area",
                         f"bottom {template.safe_area.bottom}",
                         "§16.2, from the template — not model-chosen"),
            ])

    unplanned = [r for r in wanted if r not in plans]
    if unplanned:
        problems.append(
            f"these scenes were not planned: {sorted(unplanned)}. Every scene "
            f"needs a visual — §9.2's multimedia rule forbids narration over a "
            f"static title for more than 8 seconds.")

    if problems:
        raise ox.SchemaError(problems)
    return [plans[s["ref"]] for s in scenes]


# -------------------------------------------------------------- generate

def plan(conn, course_id: str | None, brief: CourseBrief, video: dict,
         scenes: list[dict], objectives: list[Objective], *, client=None,
         model: str | None = None) -> VisualPlan:
    ref = prompts.load(PROMPT)
    parts = ox._sections(ref.body)
    missing = {"system", "scenes", "repair"} - set(parts)
    if missing:
        raise RuntimeError(
            f"prompts/{PROMPT}.v{ref.file_version}.md is missing {sorted(missing)}")

    model_id = model or settings().models.for_tier("mid")
    client = client or ox._client(conn, course_id)
    by_ref = {o.ref: o for o in objectives}

    scene_input = {
        "video": {"ref": video["ref"], "title": video["title"],
                  "script_type": video["script_type"]},
        "scenes": [
            {
                "ref": s["ref"],
                "gagne_slot": s["gagne_slot"],
                "narration": s.get("text") or "",
                "seconds": (s.get("pedagogy_meta") or {}).get(
                    "duration_target_seconds"),
                "bloom_level": (s.get("pedagogy_meta") or {}).get("bloom_level"),
                "element_interactivity": (s.get("pedagogy_meta") or {}).get(
                    "element_interactivity"),
                "new_terms": (s.get("pedagogy_meta") or {}).get("new_terms", []),
                "objective": (by_ref[s["objective_ref"]].statement
                              if s.get("objective_ref") in by_ref else ""),
            }
            for s in scenes
        ],
        "templates": [
            {"name": t.name, "kind": t.kind.value, "description": t.description,
             "seconds": [t.min_sec, t.max_sec],
             "supports_signalling": t.supports_signalling,
             "params": t.param_schema()}
            # ISSUE-20: only designed templates are offered. An undesigned
            # one renders legibly but its composition was improvised.
            for t in sorted(templates.selectable(), key=lambda t: t.name)
        ],
    }
    user_turn = parts["scenes"].replace(
        "{scene_input}", json.dumps(scene_input, indent=2, sort_keys=True))
    messages: list[dict] = [{"role": "user", "content": user_turn}]
    attempts: list = []

    for n in range(1, MAX_REPAIRS + 2):
        try:
            raw, usage, content = _call(client, model_id, parts["system"], messages)
        except Exception as e:
            escalation.raise_escalated(
                conn, stage=AGENT, error_class=ox._error_class(e), course_id=course_id,
                message=f"visual planning call failed on attempt {n} for video "
                        f"'{video['ref']}': {type(e).__name__}: {e}",
                offending_input={"model": model_id, "prompt_version": ref.version,
                                 "video_ref": video["ref"]},
                next_step="check `explainer doctor`, then re-run "
                          "`explainer storyboard plan`.")
            raise

        attempts.append(ox.Attempt(
            n=n, raw=raw,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cost_usd=ox._price(model_id, usage)))

        try:
            plans = parse(raw, scenes)
        except ox.SchemaError as e:
            attempts[-1].error = str(e)
            if n > MAX_REPAIRS:
                escalation.raise_escalated(
                    conn, stage=AGENT, error_class="llm_schema", course_id=course_id,
                    message=f"visual planning produced invalid output "
                            f"{MAX_REPAIRS + 1} times for '{video['ref']}': {e}",
                    offending_input={"last_raw_response": raw[:8000],
                                     "problems": e.problems},
                    next_step="read the raw response. Fix "
                              "prompts/visual_planner.v1.md (bump to v2) or the "
                              "template registry. Do not hand-edit the output.")
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user",
                 "content": parts["repair"].replace("{errors}", e.as_prompt_text())},
            ]
            continue

        return VisualPlan(scenes=plans, attempts=attempts, provenance={
            "agent": AGENT, "prompt_version": ref.version,
            "model_version": model_id,
            "planned_at": datetime.now(UTC).isoformat(timespec="seconds"),
        })

    raise AssertionError("unreachable")


def _call(client, model: str, system: str, messages: list[dict]):
    with client.messages.stream(
        model=model, max_tokens=MAX_TOKENS,
        system=[{"type": "text", "text": system,
                 "cache_control": {"type": "ephemeral"}}],
        thinking={"type": "adaptive"},
        output_config={"effort": "high",
                       "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=messages,
    ) as stream:
        resp = stream.get_final_message()
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"model refused: {getattr(resp, 'stop_details', None)}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError(f"response hit max_tokens ({MAX_TOKENS})")
    return ("".join(b.text for b in resp.content if b.type == "text"),
            resp.usage, resp.content)


# ------------------------------------------------------------ persistence

def save(conn, video_id: str, plan: VisualPlan) -> int:
    """Write visual_spec onto each scene. Does not touch narration or duration."""
    n = 0
    for p in plan.scenes:
        n += db.execute(conn, """
            update scenes set visual_spec = %s
             where video_id = %s and ref = %s
        """, (json.dumps(p.visual_spec(plan.provenance)), video_id, p.scene_ref))
    return n


def load(conn, video_id: str) -> list[dict]:
    return db.query(conn, """
        select ref, ordinal, gagne_slot, visual_spec, narration
          from scenes where video_id = %s order by ordinal""", (video_id,))
