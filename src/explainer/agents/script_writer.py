"""Script generation — Sequence v0.2 §6 Stage 2c.

    "2c. Script generation — per video, using the Gagné 9-slot template (§9.1)
     with typed slots. Each slot has a duration budget and a treatment rule.
     This converts open-ended generation into constrained slot-filling, which
     LLMs do dramatically more reliably."

One slot in, one scene out. The model is given the form (`gagne.plan_slots`) and
fills it; it does not decide what the slots are, how long they get, or what
order they come in.

## Four things this module does in CODE, not in the prompt

**Segmentation into spans.** Narration goes through `Narration.from_text()` and
is persisted as span JSON (CHALLENGES R4). Spans are the join key every later
stage anchors to — cues, translations, captions, the timing resolver — and
asking the model to emit them would make the join key a matter of opinion.

**`new_terms`.** The model is asked for the terms it thinks it introduced, but
the value written to `pedagogy_meta` is computed here against a running set
across the video's scenes in slot order. A model asked "is this term new?" has
to remember every earlier scene correctly; a set does not. §9.2's pre-training
rule counts on this being right.

**Duration.** Nothing here writes `scenes.duration_value` or `duration_rate`.
Those are derived from TTS (R5), which is week 5. The slot's budget goes into
`pedagogy_meta.duration_target_seconds`, which is a budget and is named like one.

**Provenance.** R6, on every scene: agent, prompt version, model version, when.

## What it does not do

No visual planning, no templates, no cues, no linter beyond what `prose.py`
runs separately. That is week 4 and Stage 3.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .. import db, escalation, gagne, prompts
from ..brief import CourseBrief
from ..config import settings
from ..gagne import Slot
from ..objectives import Objective
from ..spans import Narration
from . import objective_extractor as ox

AGENT = "script_writer"
PROMPT = "script_writer"
MAX_REPAIRS = 2
# Adaptive thinking counts against this. 16000 overran on the first v2-prompt
# run and 32000 overran again once the prompt grew a recall section, both
# times as a correct escalation rather than a silent truncation. Raised to
# 64000 — half of Sonnet 5's 128k output ceiling — so the next prompt section
# does not trip it again. The request streams, so the SDK's non-streaming
# guard does not apply. If this needs raising a third time, the thing to
# examine is the effort setting, not the ceiling.
MAX_TOKENS = 64000

TIMING_SENSITIVITIES = ("rigid", "elastic")
INTERACTIVITIES = ("low", "medium", "high")

OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slot": {"type": "string", "enum": [s.value for s in Slot]},
                    "narration": {"type": "string"},
                    "timing_sensitivity": {"type": "string",
                                           "enum": list(TIMING_SENSITIVITIES)},
                    "element_interactivity": {"type": "string",
                                              "enum": list(INTERACTIVITIES)},
                    "new_terms": {"type": "array", "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                },
                "required": ["slot", "narration", "timing_sensitivity",
                             "element_interactivity", "new_terms", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["scenes"],
    "additionalProperties": False,
}


@dataclass
class DraftScene:
    """One slot's worth of script, before it reaches the database."""

    ref: str
    ordinal: int
    slot: Slot
    objective_ref: str
    narration: Narration
    timing_sensitivity: str
    element_interactivity: str
    new_terms: list[str]
    duration_target_seconds: int
    bloom_level: str
    rationale: str = ""
    model_new_terms: list[str] = field(default_factory=list)
    # §9.1: the objective slot's line is also the scene title. Set only on
    # that scene; None elsewhere.
    scene_title: str | None = None

    @property
    def text(self) -> str:
        return self.narration.text

    def pedagogy_meta(self) -> dict:
        return {
            "bloom_level": self.bloom_level,
            "new_terms": self.new_terms,
            "element_interactivity": self.element_interactivity,
            # A BUDGET, not a duration. The duration columns stay null until TTS
            # measures the real thing (R5).
            "duration_target_seconds": self.duration_target_seconds,
            # Kept for the review loop: where the model's own guess disagreed
            # with the computed set is a signal about the prompt, not the scene.
            "model_claimed_new_terms": self.model_new_terms,
            **({"scene_title": self.scene_title} if self.scene_title else {}),
        }


@dataclass
class ScriptDraft:
    scenes: list[DraftScene]
    provenance: dict = field(default_factory=dict)
    attempts: list = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return round(sum(a.cost_usd for a in self.attempts), 6)


# ------------------------------------------------------------- new terms

_TERM_SPLIT = re.compile(r"[^a-z0-9+#._-]+")


def normalise_term(term: str) -> str:
    """Lowercase, trimmed, edge-punctuation-stripped.

    Deliberately crude: the point is that 'Repeatable Read', 'repeatable read'
    and 'Repeatable Read.' are one term, not that we understand morphology.
    `.`, `_`, `-`, `+` and `#` survive INSIDE a word so `node.js` and
    `first-updater-wins` stay intact, then get stripped at the edges —
    otherwise a trailing full stop makes a term look new the second time it
    appears.

    Known limitation: a term whose meaning lives in TRAILING punctuation is
    flattened. "C++" normalises to "c" and would collide with "C", and "C#"
    likewise. Harmless for this course; fix it with a term allow-list before
    generating a course about those languages, and do not fix it by keeping
    trailing punctuation, which reintroduces the full-stop bug above.
    """
    words = [w.strip("._-+#") for w in _TERM_SPLIT.split(term.strip().lower())]
    return " ".join(w for w in words if w)


def first_use_only(claimed: list[str], already_seen: set[str]) -> list[str]:
    """Filter a slot's claimed terms down to genuine first uses, in code.

    `already_seen` is mutated — the caller walks scenes in slot order and the
    set carries forward. This is the §9.2 pre-training rule's foundation: a term
    that reappears is not new, however confidently the model says it is.
    """
    out: list[str] = []
    for raw in claimed:
        term = normalise_term(raw)
        if not term or term in already_seen:
            continue
        already_seen.add(term)
        out.append(term)
    return out


# ----------------------------------------------------------------- parse

def parse(raw: str, form: list[gagne.SlotSpec]) -> list[dict]:
    """Model text → one dict per slot, validated against the form.

    Every slot in the form must be filled and no slot may appear twice: the form
    is the contract, and a script missing its elicit slot is not a shorter
    script, it is one that breaks §9.2's non-optional generative activity.
    """
    problems: list[str] = []
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ox.SchemaError([f"response is not valid JSON: {e}"]) from None
    if not isinstance(doc, dict):
        raise ox.SchemaError([f"top level must be an object, got {type(doc).__name__}"])
    scenes = doc.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ox.SchemaError(["'scenes' must be a non-empty array"])

    wanted = [s.slot.value for s in form]
    seen: dict[str, dict] = {}
    for i, s in enumerate(scenes):
        where = f"scenes[{i}]"
        if not isinstance(s, dict):
            problems.append(f"{where}: must be an object")
            continue
        slot = str(s.get("slot") or "").strip().lower()
        if slot not in wanted:
            problems.append(
                f"{where}: slot '{s.get('slot')}' is not in this video's form; "
                f"expected one of {wanted}")
            continue
        if slot in seen:
            problems.append(f"{where}: slot '{slot}' appears more than once")
            continue
        narration = str(s.get("narration") or "").strip()
        if not narration:
            problems.append(f"{where}: slot '{slot}' has empty narration")
            continue
        ts = str(s.get("timing_sensitivity") or "").strip().lower()
        if ts not in TIMING_SENSITIVITIES:
            problems.append(f"{where}: timing_sensitivity {s.get('timing_sensitivity')!r} "
                            f"is not one of {list(TIMING_SENSITIVITIES)}")
            continue
        ei = str(s.get("element_interactivity") or "").strip().lower()
        if ei not in INTERACTIVITIES:
            problems.append(f"{where}: element_interactivity "
                            f"{s.get('element_interactivity')!r} is not one of "
                            f"{list(INTERACTIVITIES)}")
            continue
        terms = s.get("new_terms")
        if not isinstance(terms, list) or not all(isinstance(t, str) for t in terms):
            problems.append(f"{where}: new_terms must be an array of strings")
            continue
        seen[slot] = {"slot": slot, "narration": narration, "timing_sensitivity": ts,
                      "element_interactivity": ei, "new_terms": terms,
                      "rationale": str(s.get("rationale") or "").strip()}

    unfilled = [w for w in wanted if w not in seen]
    if unfilled:
        problems.append(
            f"the form has {len(wanted)} slots and these were not filled: "
            f"{unfilled}. Every slot must be filled.")

    if problems:
        raise ox.SchemaError(problems)
    return [seen[w] for w in wanted]          # form order, not response order


# -------------------------------------------------------------- generate

def generate(conn, course_id: str | None, brief: CourseBrief, video: dict,
             objectives: list[Objective], *, client=None,
             model: str | None = None,
             learner_facing: dict[str, str] | None = None,
             position: dict | None = None) -> ScriptDraft:
    """Fill one video's slot form. `video` is a row from curriculum_planner.load.

    `position` carries the video's place in the course — ordinal, total, and
    the next video's objectives if there is one. Without it the retain slot
    has no way to know whether a forward reference is true, and week 3 shipped
    a final video promising a sequel that does not exist.
    """
    ref = prompts.load(PROMPT)
    parts = ox._sections(ref.body)
    missing = {"system", "video", "repair"} - set(parts)
    if missing:
        raise RuntimeError(
            f"prompts/{PROMPT}.v{ref.file_version}.md is missing section(s) "
            f"{sorted(missing)}")

    form = gagne.plan_slots(video["script_type"], video["target_seconds"])
    by_ref = {o.ref: o for o in objectives}
    carried = [by_ref[r] for r in video["objective_refs"] if r in by_ref]
    if not carried:
        raise RuntimeError(
            f"video '{video['ref']}' carries no objectives that exist in the "
            f"graph; the curriculum plan and the objective graph disagree")

    model_id = model or settings().models.for_tier("mid")
    client = client or ox._client(conn, course_id)

    learner_facing = learner_facing or {}
    position = position or {}
    is_final = bool(position) and position.get("ordinal") == position.get("total")
    video_input = {
        "title": video["title"],
        "script_type": video["script_type"],
        "target_seconds": video["target_seconds"],
        "audience": brief.audience.to_json(),
        "tone": brief.tone,
        "objectives": [
            {"ref": o.ref, "statement": o.statement,
             "bloom_level": o.bloom_level.value,
             "knowledge_type": o.knowledge_type.value,
             "criterion": o.criterion or ""}
            for o in carried
        ],
        "assumed_knowledge": [
            o.statement for o in objectives if o.assumed],
        # §9.1: the objective slot states this VERBATIM and it is reused as
        # that scene's title. Stored data (migration 0004), not something to
        # re-abridge here.
        "learner_facing_statements": {
            o.ref: learner_facing.get(o.ref, "") for o in carried},
        "course_position": {
            "video_number": position.get("ordinal"),
            "total_videos": position.get("total"),
            "is_final_video": is_final,
            "next_video": position.get("next"),
            "out_of_scope": position.get("out_of_scope", ""),
        },
        "slots": [
            {"slot": s.slot.value,
             "seconds": s.seconds,
             "treatment": s.treatment,
             "objective_ref": _objective_for_slot(s.slot, carried).ref,
             "spec_capped": s.spec_capped}
            for s in form
        ],
    }
    user_turn = parts["video"].replace(
        "{video_input}", json.dumps(video_input, indent=2, sort_keys=True))
    messages: list[dict] = [{"role": "user", "content": user_turn}]
    attempts: list = []

    for n in range(1, MAX_REPAIRS + 2):
        try:
            raw, usage, content = _call(client, model_id, parts["system"], messages)
        except Exception as e:
            escalation.raise_escalated(
                conn, stage=AGENT, error_class=ox._error_class(e), course_id=course_id,
                message=f"script generation call failed on attempt {n} for video "
                        f"'{video['ref']}': {type(e).__name__}: {e}",
                offending_input={"model": model_id, "prompt_version": ref.version,
                                 "video_ref": video["ref"]},
                next_step="check `explainer doctor`, then re-run "
                          "`explainer script generate`.")
            raise

        attempts.append(ox.Attempt(
            n=n, raw=raw,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cost_usd=ox._price(model_id, usage)))

        try:
            filled = parse(raw, form)
        except ox.SchemaError as e:
            attempts[-1].error = str(e)
            if n > MAX_REPAIRS:
                escalation.raise_escalated(
                    conn, stage=AGENT, error_class="llm_schema", course_id=course_id,
                    message=f"script generation produced invalid output "
                            f"{MAX_REPAIRS + 1} times for video '{video['ref']}'. "
                            f"Last errors: {e}",
                    offending_input={"last_raw_response": raw[:8000],
                                     "problems": e.problems,
                                     "video_ref": video["ref"]},
                    next_step="read the raw response. Fix "
                              "prompts/script_writer.v1.md (bump to v2) or "
                              "OUTPUT_SCHEMA. Do not hand-edit the output.")
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user",
                 "content": parts["repair"].replace("{errors}", e.as_prompt_text())},
            ]
            continue

        return _assemble(filled, form, carried, ref.version, model_id, attempts,
                         learner_facing)

    raise AssertionError("unreachable")


def _objective_for_slot(slot: Slot, carried: list[Objective]) -> Objective:
    """Every scene gets exactly one objective (§5.3).

    With two objectives on a video, the split is structural rather than a
    judgment call: the setup slots and the first teaching pass serve the first
    objective, and everything from `guide` onward serves the second — which is
    the objective that depends on the first, since the planner ordered them.
    """
    if len(carried) == 1:
        return carried[0]
    early = {Slot.HOOK, Slot.OBJECTIVE, Slot.RECALL, Slot.PRESENT}
    return carried[0] if slot in early else carried[1]


def _assemble(filled: list[dict], form: list[gagne.SlotSpec],
              carried: list[Objective], prompt_version: str, model_id: str,
              attempts: list, learner_facing: dict[str, str] | None = None
              ) -> ScriptDraft:
    by_slot = {s.slot.value: s for s in form}
    learner_facing = learner_facing or {}
    seen_terms: set[str] = set()
    scenes: list[DraftScene] = []

    for i, f in enumerate(filled, start=1):
        slot = Slot(f["slot"])
        objective = _objective_for_slot(slot, carried)
        scenes.append(DraftScene(
            ref=f"s{i:02d}",
            ordinal=i,
            slot=slot,
            objective_ref=objective.ref,
            # R4: segmented at authoring time, never stored as flat prose.
            narration=Narration.from_text(f["narration"]),
            timing_sensitivity=f["timing_sensitivity"],
            element_interactivity=f["element_interactivity"],
            # Computed in code against a running set, in slot order.
            new_terms=first_use_only(f["new_terms"], seen_terms),
            model_new_terms=[normalise_term(t) for t in f["new_terms"]],
            duration_target_seconds=by_slot[f["slot"]].seconds,
            bloom_level=objective.bloom_level.value,
            rationale=f["rationale"],
            scene_title=(learner_facing.get(objective.ref)
                         if slot is Slot.OBJECTIVE else None),
        ))

    return ScriptDraft(scenes=scenes, attempts=attempts, provenance={
        "agent": AGENT, "prompt_version": prompt_version,
        "model_version": model_id,
        "written_at": datetime.now(UTC).isoformat(timespec="seconds"),
    })


def _call(client, model: str, system: str, messages: list[dict]):
    """Streamed, because MAX_TOKENS is above the SDK's non-streaming guard.

    Nine slots of narration plus an adaptive-thinking pass can run past the
    ten-minute idle window a plain request allows, and the SDK refuses rather
    than letting the connection drop mid-generation. `get_final_message()` gives
    the same accumulated Message a non-streaming call would have returned, so
    nothing downstream changes.
    """
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

def save(conn, video_id: str, draft: ScriptDraft,
         objective_ids: dict[str, str]) -> None:
    """Write scenes. Replaces the video's scenes wholesale.

    Never writes duration_value/duration_rate — R5, those come from TTS. The
    columns stay null and the budget lives in pedagogy_meta.
    """
    db.execute(conn, "delete from scenes where video_id = %s", (video_id,))
    for s in draft.scenes:
        db.execute(conn, """
            insert into scenes(video_id, ref, ordinal, objective_id, gagne_slot,
                               narration, timing_sensitivity, pedagogy_meta,
                               provenance)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (video_id, s.ref, s.ordinal, objective_ids.get(s.objective_ref),
              s.slot.value, json.dumps(s.narration.to_json()),
              s.timing_sensitivity, json.dumps(s.pedagogy_meta()),
              json.dumps({**draft.provenance, "rationale": s.rationale})))


def load(conn, video_id: str) -> list[dict]:
    rows = db.query(conn, """
        select s.ref, s.ordinal, s.gagne_slot, s.narration, s.timing_sensitivity,
               s.pedagogy_meta, s.provenance, s.duration_value, s.duration_rate,
               o.ref as objective_ref
          from scenes s left join objectives o on o.id = s.objective_id
         where s.video_id = %s order by s.ordinal""", (video_id,))
    for r in rows:
        r["text"] = " ".join(sp["text"] for sp in (r["narration"] or []))
    return rows


def video_row(conn, course_id: str, video_ref: str) -> dict:
    row = db.one(conn, """
        select id, ref, title, script_type, target_seconds, ordinal
          from videos_v2 where course_id = %s and ref = %s""",
                 (course_id, video_ref))
    if not row:
        raise LookupError(
            f"no video '{video_ref}' in this course — run "
            f"`explainer curriculum plan` first")
    row["objective_refs"] = [r["ref"] for r in db.query(conn, """
        select o.ref from video_objectives vo
          join objectives o on o.id = vo.objective_id
         where vo.video_id = %s order by o.ref""", (str(row["id"]),))]
    return row
