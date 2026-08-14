"""Signal design — Sequence v0.2 §8, §9.2 Signalling. CHALLENGES R3.

Cues anchored to narration spans. What gets highlighted, and on which words.

## Everything here rests on R3

    R3  cues anchor to span ids, never timestamps  → localisation, editing

A cue that carried a timestamp would be correct exactly once: until the
narration is re-recorded at a different pace, or re-timed, or translated into a
language whose word order puts the referent three seconds later. Anchoring to a
span id means the cue survives all three, because the span is the thing that gets
translated and re-timed *with* it. `spans.Anchor` has no timestamp field at all —
the invariant is enforced by the type, not by a check.

The resolved firing time is computed at timing-resolution (week 5) from
`Narration.resolve_cue`, using word timings that TTS produces. Nothing here
knows when anything happens.

## The blocking checks

Both from the brief for this step, and both set membership rather than judgement:

  * every cue's `span_id` must exist in THAT scene's narration;
  * every cue's `target` must exist in the chosen template's parameter schema.

A cue pointing at a span that was deleted, or a slot the template does not have,
is not a lower-quality cue — it is one that cannot fire. It refers to nothing.
So both are blocking, and both go back through the repair loop rather than
reaching a human as findings.

## The spec numbers, none of them invented

§9.2 Signalling states all of them:

    1-3 events per scene, never zero, never more than 3 concurrent
    permitted: colour highlight, arrow/pointer, scale-pulse (<=120%, <=400ms),
               dimming of non-focal regions to ~40% opacity
    onset time-locked to the narration word within +/-150 ms - early beats late

`SCALE_PULSE_MAX`, `SCALE_PULSE_MAX_MS`, `DIM_OPACITY` and `MAX_OFFSET_MS` are
transcribed from that paragraph. The one thing NOT taken from it is the
zero-cue exemption for templates that declare `supports_signalling = False` —
see ISSUE-5, which records that the flag is an authored judgement of mine that
conflicts with §9.2's "never zero", and that resolving it is a spec decision.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .. import db, escalation, prompts, templates
from ..config import settings
from ..rtime import RationalTime
from ..spans import Anchor, AnchorPoint, Cue, Narration
from ..templates import Template
from . import objective_extractor as ox

AGENT = "signal_designer"
PROMPT = "signal_designer"
MAX_REPAIRS = 2
MAX_TOKENS = 64000

# §9.2 Signalling — every number below is quoted from that paragraph.
MIN_CUES_PER_SCENE = 1
MAX_CUES_PER_SCENE = 3
CUE_KINDS = ("highlight", "pointer", "scale_pulse", "dim")
MAX_OFFSET_MS = 150          # "within +/-150 ms"
SCALE_PULSE_MAX = 1.20       # "scale-pulse (<=120%"
SCALE_PULSE_MAX_MS = 400     # "<=400 ms)"
DIM_OPACITY = 0.40           # "dimming of non-focal regions to ~40% opacity"

# Offsets are expressed in milliseconds by the model and stored as RationalTime
# at this rate — 1000 ticks/second makes a millisecond exactly representable, so
# no rounding enters at the boundary (R2).
OFFSET_RATE = 1000

OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene_ref": {"type": "string"},
                    "cues": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": list(CUE_KINDS)},
                                "target": {"type": "string"},
                                "span_id": {"type": "string"},
                                "point": {"type": "string",
                                          "enum": ["start", "end"]},
                                "offset_ms": {"type": "integer"},
                                "rationale": {"type": "string"},
                            },
                            "required": ["kind", "target", "span_id", "point",
                                         "offset_ms", "rationale"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["scene_ref", "cues"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["scenes"],
    "additionalProperties": False,
}

# A target is a parameter name, optionally with an item selector: `nodes.n1`,
# `steps[2]`, `series.throughput`.
_TARGET = re.compile(r"^(?P<slot>[a-z_][a-z0-9_]*)(?:\.(?P<key>[^.\[\]]+)|\[(?P<idx>\d+)\])?$")


@dataclass
class SceneSignals:
    scene_ref: str
    cues: list[Cue] = field(default_factory=list)
    rationales: list[str] = field(default_factory=list)

    def to_json(self) -> list[dict]:
        return [c.to_json() for c in self.cues]


@dataclass
class SignalPlan:
    scenes: list[SceneSignals]
    provenance: dict = field(default_factory=dict)
    attempts: list = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return round(sum(a.cost_usd for a in self.attempts), 6)

    @property
    def cue_count(self) -> int:
        return sum(len(s.cues) for s in self.scenes)


# ---------------------------------------------------------- the two gates

def check_span(scene_ref: str, span_id: str, narration: Narration) -> list[str]:
    """R3's other half: a cue must point at a span that exists HERE."""
    if any(s.id == span_id for s in narration.spans):
        return []
    return [f"{scene_ref}: cue anchors to span '{span_id}', which is not in this "
            f"scene's narration. Its spans are "
            f"{[s.id for s in narration.spans]}."]


def check_target(scene_ref: str, target: str, template: Template,
                 slots: dict) -> list[str]:
    """A cue must affect something the template actually has."""
    m = _TARGET.match(target.strip())
    if not m:
        return [f"{scene_ref}: target '{target}' is not a slot name, "
                f"'slot.key' or 'slot[index]'"]
    slot = m.group("slot")
    if slot not in template.param_names():
        return [f"{scene_ref}: target '{target}' names slot '{slot}', which "
                f"template '{template.name}' does not have. It has "
                f"{template.param_names()}."]
    if slot not in slots:
        return [f"{scene_ref}: target '{target}' names slot '{slot}', which this "
                f"scene did not fill — there is nothing on screen to affect."]
    idx = m.group("idx")
    if idx is not None:
        value = slots[slot]
        if not isinstance(value, list) or int(idx) >= len(value):
            return [f"{scene_ref}: target '{target}' indexes item {idx} of "
                    f"'{slot}', which has "
                    f"{len(value) if isinstance(value, list) else 0} items."]
    return []


def check_offset(scene_ref: str, offset_ms: int) -> list[str]:
    """§9.2: onset time-locked within +/-150 ms."""
    if abs(offset_ms) <= MAX_OFFSET_MS:
        return []
    return [f"{scene_ref}: offset {offset_ms}ms exceeds §9.2's +/-{MAX_OFFSET_MS}ms "
            f"tolerance. The signal has to land on the word, not near it."]


def check_count(scene_ref: str, n: int, template: Template) -> list[str]:
    """§9.2: 1-3 per scene. The exemption is ISSUE-5, not the spec."""
    if not template.supports_signalling:
        if n:
            return [f"{scene_ref}: template '{template.name}' does not host "
                    f"signalling, so it cannot carry {n} cue(s)."]
        return []
    if n < MIN_CUES_PER_SCENE:
        return [f"{scene_ref}: no signalling events. §9.2 requires "
                f"{MIN_CUES_PER_SCENE}-{MAX_CUES_PER_SCENE} per scene — never zero."]
    if n > MAX_CUES_PER_SCENE:
        return [f"{scene_ref}: {n} signalling events, over §9.2's maximum of "
                f"{MAX_CUES_PER_SCENE} concurrent."]
    return []


# ----------------------------------------------------------------- parse

def parse(raw: str, scenes: list[dict]) -> list[SceneSignals]:
    """`scenes` need `ref`, `narration` (a Narration) and `visual_spec`."""
    problems: list[str] = []
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ox.SchemaError([f"response is not valid JSON: {e}"]) from None
    if not isinstance(doc, dict):
        raise ox.SchemaError([f"top level must be an object, got {type(doc).__name__}"])
    got = doc.get("scenes")
    if not isinstance(got, list):
        raise ox.SchemaError(["'scenes' must be an array"])

    wanted = {s["ref"]: s for s in scenes}
    out: dict[str, SceneSignals] = {}
    for i, s in enumerate(got):
        where = f"scenes[{i}]"
        if not isinstance(s, dict):
            problems.append(f"{where}: must be an object")
            continue
        ref = str(s.get("scene_ref") or "").strip()
        if ref not in wanted:
            problems.append(f"{where}: scene_ref {s.get('scene_ref')!r} is not one "
                            f"of {sorted(wanted)}")
            continue
        if ref in out:
            problems.append(f"{where}: scene '{ref}' appears more than once")
            continue

        scene = wanted[ref]
        narration: Narration = scene["narration"]
        spec = scene.get("visual_spec") or {}
        try:
            template = templates.get(spec.get("template", ""))
        except templates.TemplateError as e:
            problems.append(f"{ref}: {e}")
            continue
        slots = spec.get("slots") or {}

        raw_cues = s.get("cues")
        if not isinstance(raw_cues, list):
            problems.append(f"{ref}: 'cues' must be an array")
            continue

        cues: list[Cue] = []
        rationales: list[str] = []
        for j, c in enumerate(raw_cues):
            cw = f"{ref}.cues[{j}]"
            if not isinstance(c, dict):
                problems.append(f"{cw}: must be an object")
                continue
            kind = str(c.get("kind") or "").strip()
            if kind not in CUE_KINDS:
                problems.append(f"{cw}: kind {c.get('kind')!r} is not one of "
                                f"{list(CUE_KINDS)} (§9.2's permitted signals)")
                continue
            target = str(c.get("target") or "").strip()
            span_id = str(c.get("span_id") or "").strip()
            try:
                offset_ms = int(c.get("offset_ms", 0))
            except (TypeError, ValueError):
                problems.append(f"{cw}: offset_ms must be an integer")
                continue

            span_problems = check_span(cw, span_id, narration)
            target_problems = check_target(cw, target, template, slots)
            problems += span_problems + target_problems
            problems += check_offset(cw, offset_ms)
            if span_problems or target_problems:
                continue

            cues.append(Cue(
                kind=kind, target=target,
                anchor=Anchor(span_id=span_id,
                              point=AnchorPoint(str(c.get("point") or "start")),
                              offset=RationalTime(offset_ms, OFFSET_RATE)),
                params=_params_for(kind)))
            rationales.append(str(c.get("rationale") or "").strip())

        problems += check_count(ref, len(cues), template)
        out[ref] = SceneSignals(scene_ref=ref, cues=cues, rationales=rationales)

    missing = [r for r in wanted if r not in out]
    if missing:
        problems.append(f"no signal plan for scene(s) {sorted(missing)}")

    if problems:
        raise ox.SchemaError(problems)
    return [out[s["ref"]] for s in scenes]


def _params_for(kind: str) -> dict:
    """The §9.2 bounds each signal type carries. Not model-chosen: the spec
    states them, so they are attached here rather than asked for."""
    if kind == "scale_pulse":
        return {"max_scale": SCALE_PULSE_MAX, "max_ms": SCALE_PULSE_MAX_MS}
    if kind == "dim":
        return {"non_focal_opacity": DIM_OPACITY}
    return {}


# -------------------------------------------------------------- generate

def design(conn, course_id: str | None, video: dict, scenes: list[dict], *,
           client=None, model: str | None = None) -> SignalPlan:
    ref = prompts.load(PROMPT)
    parts = ox._sections(ref.body)
    missing = {"system", "scenes", "repair"} - set(parts)
    if missing:
        raise RuntimeError(
            f"prompts/{PROMPT}.v{ref.file_version}.md is missing {sorted(missing)}")

    model_id = model or settings().models.for_tier("mid")
    client = client or ox._client(conn, course_id)

    scene_input = {"scenes": [
        {
            "ref": s["ref"],
            "gagne_slot": s.get("gagne_slot"),
            "template": (s.get("visual_spec") or {}).get("template"),
            "supports_signalling": templates.get(
                (s.get("visual_spec") or {}).get("template", "labelled_diagram")
            ).supports_signalling,
            "slots": (s.get("visual_spec") or {}).get("slots", {}),
            "spans": [{"id": sp.id, "text": sp.text}
                      for sp in s["narration"].spans],
        }
        for s in scenes
    ]}
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
                message=f"signal design call failed on attempt {n} for "
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
                    message=f"signal design produced invalid output "
                            f"{MAX_REPAIRS + 1} times for '{video['ref']}': {e}",
                    offending_input={"last_raw_response": raw[:8000],
                                     "problems": e.problems},
                    next_step="read the raw response. A cue pointing at a missing "
                              "span or slot means the visual plan and the script "
                              "disagree — check those before editing the prompt.")
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user",
                 "content": parts["repair"].replace("{errors}", e.as_prompt_text())},
            ]
            continue

        return SignalPlan(scenes=plans, attempts=attempts, provenance={
            "agent": AGENT, "prompt_version": ref.version,
            "model_version": model_id,
            "designed_at": datetime.now(UTC).isoformat(timespec="seconds"),
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

def save(conn, video_id: str, plan: SignalPlan) -> int:
    """Merge cues into each scene's existing visual_spec.

    A read-modify-write rather than an overwrite: the visual planner owns
    `template` and `slots`, the signal designer owns `cues`, and §10 wants those
    separately overridable. Replacing the whole spec here would silently
    discard a human's earlier slot edit.
    """
    n = 0
    for s in plan.scenes:
        row = db.one(conn, """select visual_spec from scenes
                              where video_id = %s and ref = %s""",
                     (video_id, s.scene_ref))
        if not row:
            continue
        spec = dict(row["visual_spec"] or {})
        spec["cues"] = s.to_json()
        spec.setdefault("decisions", {})["cues"] = {
            "value": f"{len(s.cues)} cue(s)",
            "rule": "§9.2 signalling 1-3 per scene, anchored to spans (R3)"}
        spec["cue_rationales"] = s.rationales
        n += db.execute(conn, """update scenes set visual_spec = %s
                                 where video_id = %s and ref = %s""",
                        (json.dumps(spec), video_id, s.scene_ref))
    return n
