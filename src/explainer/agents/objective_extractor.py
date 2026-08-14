"""Objective extraction — the first real model call (PRD v0.2 §6 Stage 2a).

Course Brief in, objective graph out. What this file is careful about:

**The deterministic checks stay deterministic.** This agent produces `Objective`
and `AssessmentItem` values and hands them, unchanged, to `objectives.validate`.
It does not pre-filter, repair or argue with the result. Bloom alignment, banned
verbs and the prerequisite DAG are code (§7.1 rule 4: "deterministic checks beat
agentic checks") — the moment one of them becomes a model call, the linter
becomes an opinion and the thing a buyer can be shown stops being a proof.

**Two kinds of failure, handled differently.**

  * *Structural* failure — the model emitted something that is not a valid
    objective graph at all (unknown Bloom level, duplicate refs, an assessment
    item pointing at nothing). This is retried: re-prompt with the exact errors,
    at most `MAX_REPAIRS` times, then escalate (§7.1 rule 1).
  * *Pedagogical* findings — the graph is well-formed but `validate` objects to
    it (an apply-level objective assessed by a recall MCQ, a flattened chain, an
    unobservable verb). These are RETURNED to the caller, never auto-fixed. A
    human decides. Silently repairing a finding would hide exactly the signal
    this stage exists to produce.

**Provenance on every objective (R6).** Which agent, which prompt version, which
model version, when. The timestamp is provenance metadata and is deliberately
kept out of anything that could reach a hash closure (invariant 1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .. import escalation, prompts, prose
from ..brief import CourseBrief
from ..config import settings
from ..objectives import AssessmentItem, Bloom, KnowledgeType, Objective, ValidationReport, validate

AGENT = "objective_extractor"
PROMPT = "objective_extractor"
MAX_REPAIRS = 2          # §7.1 rule 1 — three attempts total, then escalate
MAX_TOKENS = 16000
ASSESSMENT_KINDS = ("mcq", "short", "predict", "task")

# Published list prices, USD per million tokens, for the pinned models we
# actually call. Absent means "unpriced" and cost is reported as 0.0 rather
# than guessed — a wrong cost number is worse than a missing one (§15).
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

# The typed output contract. This is a schema, not a prompt — it is enforced by
# the API and re-checked below, and it lives in code because `code_version`
# already covers it. All prose lives in prompts/objective_extractor.v1.md.
OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "objectives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string"},
                    "verb": {"type": "string"},
                    "object": {"type": "string"},
                    "condition": {"type": "string"},
                    "criterion": {"type": "string"},
                    "bloom_level": {"type": "string",
                                    "enum": [b.value for b in Bloom]},
                    "knowledge_type": {"type": "string",
                                       "enum": [k.value for k in KnowledgeType]},
                    "assumed": {"type": "boolean"},
                    "prerequisites": {"type": "array", "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                    # v3: the speakable short form the §9.1 objective slot
                    # says verbatim. Stored data, not a generation-time
                    # abridgement — see migration 0004.
                    "learner_facing_statement": {"type": "string"},
                },
                "required": ["ref", "verb", "object", "condition", "criterion",
                             "bloom_level", "knowledge_type", "assumed",
                             "prerequisites", "rationale",
                             "learner_facing_statement"],
                "additionalProperties": False,
            },
        },
        "assessment_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string"},
                    "objective_ref": {"type": "string"},
                    "bloom_level": {"type": "string",
                                    "enum": [b.value for b in Bloom]},
                    "kind": {"type": "string", "enum": list(ASSESSMENT_KINDS)},
                    "stem": {"type": "string"},
                },
                "required": ["ref", "objective_ref", "bloom_level", "kind", "stem"],
                "additionalProperties": False,
            },
        },
        # Prompt v2 asks the model to declare what the video budget forced it to
        # leave out rather than silently expanding the graph. The field has to
        # exist here or `additionalProperties: false` forbids the very thing the
        # prompt instructs — the schema and the prompt are one contract, and a
        # prompt that asks for a key the schema rejects is a bug in this file.
        "out_of_scope": {"type": "string"},
    },
    "required": ["objectives", "assessment_items", "out_of_scope"],
    "additionalProperties": False,
}


class SchemaError(ValueError):
    """Structural problems with a model response. Retryable — the message is
    fed back to the model verbatim as the repair prompt's `{errors}`."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))

    def as_prompt_text(self) -> str:
        return "\n".join(f"- {p}" for p in self.problems)


@dataclass
class Attempt:
    """One model call, kept whole. `raw` is what came back before any parsing —
    the thing you look at first when the output is wrong."""

    n: int
    raw: str
    # `input_tokens` is the UNCACHED remainder only. The cached portion of the
    # prompt is reported separately and is billed at different rates, so all
    # three have to be recorded or the cost is wrong — see `_price`. The first
    # three runs of this agent recorded only two of them and under-reported
    # their cost by roughly 9%; that is why these fields exist.
    input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None

    @property
    def total_input_tokens(self) -> int:
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens


@dataclass
class ExtractionOutcome:
    objectives: list[Objective]
    items: list[AssessmentItem]
    report: ValidationReport
    provenance: dict
    attempts: list[Attempt] = field(default_factory=list)
    rationales: dict[str, str] = field(default_factory=dict)
    # What the model says the video budget forced it to leave out (prompt v2).
    # Empty on a v1 run. This is a first-class output, not a footnote: an
    # honest boundary is the difference between a scoped course and a
    # silently truncated one.
    out_of_scope: str = ""
    # ref -> the speakable short form (v3+). Empty for a v1/v2 run.
    learner_facing: dict[str, str] = field(default_factory=dict)

    @property
    def raw(self) -> str:
        return self.attempts[-1].raw if self.attempts else ""

    @property
    def cost_usd(self) -> float:
        return round(sum(a.cost_usd for a in self.attempts), 6)

    @property
    def ok(self) -> bool:
        return self.report.ok


# ------------------------------------------------------------------ prompts

def _sections(body: str) -> dict[str, str]:
    """Split the prompt file on `<!-- @section NAME -->` markers.

    The repair prompt is prompt text and therefore has to live in the file too
    (invariant 6). One file keeps the whole conversation under one
    prompt_version, so a repair-wording change invalidates downstream artifacts
    exactly as a system-prompt change does.
    """
    out: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("<!-- @section ") and stripped.endswith("-->"):
            if current:
                out[current] = "\n".join(buf).strip()
            current = stripped[len("<!-- @section "):-3].strip()
            buf = []
        else:
            buf.append(line)
    if current:
        out[current] = "\n".join(buf).strip()
    return out


# ----------------------------------------------------------------- parsing

def _require(obj, key, kind, where: str, problems: list[str]):
    val = obj.get(key)
    if not isinstance(val, kind):
        problems.append(f"{where}: '{key}' must be {kind.__name__}, got "
                        f"{type(val).__name__}")
        return None
    return val


def parse(raw: str) -> tuple[list[Objective], list[AssessmentItem], dict[str, str], str, dict[str, str]]:
    """Model text → typed values. Raises `SchemaError` listing every problem.

    Every problem is collected rather than raised on the first one, so a repair
    round trip fixes everything at once instead of peeling errors one per call.
    """
    problems: list[str] = []
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SchemaError([f"response is not valid JSON: {e}"]) from None
    if not isinstance(doc, dict):
        raise SchemaError([f"top level must be an object, got {type(doc).__name__}"])

    raw_objs = doc.get("objectives")
    if not isinstance(raw_objs, list) or not raw_objs:
        raise SchemaError(["'objectives' must be a non-empty array"])
    raw_items = doc.get("assessment_items")
    if not isinstance(raw_items, list):
        problems.append("'assessment_items' must be an array (use [] if none)")
        raw_items = []

    objectives: list[Objective] = []
    rationales: dict[str, str] = {}
    learner_facing: dict[str, str] = {}
    seen: set[str] = set()
    for i, o in enumerate(raw_objs):
        where = f"objectives[{i}]"
        if not isinstance(o, dict):
            problems.append(f"{where}: must be an object")
            continue
        ref = _require(o, "ref", str, where, problems)
        verb = _require(o, "verb", str, where, problems)
        obj_text = _require(o, "object", str, where, problems)
        if ref is None or verb is None or obj_text is None:
            continue
        if ref in seen:
            problems.append(f"{where}: duplicate ref '{ref}' — refs must be unique")
            continue
        seen.add(ref)
        try:
            bloom = Bloom(str(o.get("bloom_level", "")).strip().lower())
        except ValueError:
            problems.append(f"{where}: bloom_level {o.get('bloom_level')!r} is not "
                            f"one of {[b.value for b in Bloom]}")
            continue
        try:
            ktype = KnowledgeType(str(o.get("knowledge_type", "")).strip().lower())
        except ValueError:
            problems.append(f"{where}: knowledge_type {o.get('knowledge_type')!r} is "
                            f"not one of {[k.value for k in KnowledgeType]}")
            continue
        prereqs = o.get("prerequisites") or []
        if not isinstance(prereqs, list) or not all(isinstance(p, str) for p in prereqs):
            problems.append(f"{where}: prerequisites must be an array of refs")
            prereqs = []
        objectives.append(Objective(
            ref=ref.strip(), verb=verb.strip().lower(), object=obj_text.strip(),
            bloom_level=bloom, knowledge_type=ktype,
            condition=(o.get("condition") or "").strip() or None,
            criterion=(o.get("criterion") or "").strip() or None,
            prerequisites=[p.strip() for p in prereqs],
            assumed=bool(o.get("assumed", False)),
        ))
        rationales[ref.strip()] = (o.get("rationale") or "").strip()
        short = (o.get("learner_facing_statement") or "").strip()
        learner_facing[ref.strip()] = short
        # Validated HERE, at extraction, so the repair loop fixes it. A
        # short form that cannot be spoken in its 10s slot is an extraction
        # error, not something the script writer inherits.
        problems.extend(prose.check_learner_facing_statement(ref.strip(), short))

    items: list[AssessmentItem] = []
    item_refs: set[str] = set()
    for i, it in enumerate(raw_items):
        where = f"assessment_items[{i}]"
        if not isinstance(it, dict):
            problems.append(f"{where}: must be an object")
            continue
        ref = _require(it, "ref", str, where, problems)
        obj_ref = _require(it, "objective_ref", str, where, problems)
        stem = _require(it, "stem", str, where, problems)
        if ref is None or obj_ref is None or stem is None:
            continue
        if ref in item_refs:
            problems.append(f"{where}: duplicate ref '{ref}'")
            continue
        item_refs.add(ref)
        try:
            bloom = Bloom(str(it.get("bloom_level", "")).strip().lower())
        except ValueError:
            problems.append(f"{where}: bloom_level {it.get('bloom_level')!r} is not "
                            f"one of {[b.value for b in Bloom]}")
            continue
        kind = str(it.get("kind", "")).strip().lower()
        if kind not in ASSESSMENT_KINDS:
            problems.append(f"{where}: kind {it.get('kind')!r} is not one of "
                            f"{list(ASSESSMENT_KINDS)}")
            continue
        items.append(AssessmentItem(ref=ref.strip(), objective_ref=obj_ref.strip(),
                                    bloom_level=bloom, kind=kind, stem=stem.strip()))

    # Dangling objective_refs are structural, not pedagogical: the graph does not
    # hang together at all, so it is worth a repair round trip. `validate` also
    # reports them as `orphan_assessment`, but only as a warning.
    known = {o.ref for o in objectives}
    for it in items:
        if it.objective_ref not in known:
            problems.append(
                f"assessment item '{it.ref}' targets objective "
                f"'{it.objective_ref}', which is not in the objectives list")

    if problems:
        raise SchemaError(problems)
    # Optional on the way in: a v1 response has no `out_of_scope` and is still a
    # perfectly valid graph. Absent means "nothing declared", not "nothing left
    # out" — the distinction matters when reading an old recorded run.
    out_of_scope = str(doc.get("out_of_scope") or "").strip()
    return objectives, items, rationales, out_of_scope, learner_facing


# ------------------------------------------------------------- model access

def _client(conn=None, course_id: str | None = None):
    """Build the SDK client, or escalate.

    A missing credential is a configuration failure, not a model failure, and it
    is the single most likely reason a first run does not work. It gets the same
    treatment as any other failure path (invariant 7): a recorded state with the
    fix in it, not a stack trace.
    """
    try:
        import anthropic
    except ImportError:  # pragma: no cover - environment problem, not logic
        raise RuntimeError(
            "the `anthropic` package is not installed. `pip install -e \".[dev]\"` "
            "or `pip install anthropic`.") from None
    try:
        return anthropic.Anthropic()
    except Exception as e:
        escalation.raise_escalated(
            conn, stage=AGENT, error_class="internal", course_id=course_id,
            message=f"cannot build an Anthropic client: {type(e).__name__}: {e}",
            next_step="set ANTHROPIC_API_KEY in .env (see .env.example), or run "
                      "`ant auth login`. `explainer doctor` shows what is "
                      "currently configured.")


# Prompt-caching multipliers on the INPUT rate. A cache write costs more than a
# plain input token; a cache read costs a fraction of one. Counting only the
# uncached remainder — as this function originally did — silently under-reports
# every cached run, and gets worse the better caching works, which is the wrong
# way round for a budget that §15 treats as a first-class constraint.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10


def _price(model: str, usage) -> float:
    """Cost of one call, summing all four token classes at their own rates."""
    rates = PRICES_PER_MTOK.get(model)
    if not rates:
        return 0.0
    in_rate, out_rate = rates
    uncached = getattr(usage, "input_tokens", 0) or 0
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    return (
        uncached * in_rate
        + written * in_rate * CACHE_WRITE_MULTIPLIER
        + read * in_rate * CACHE_READ_MULTIPLIER
        + out * out_rate
    ) / 1_000_000


def _call(client, model: str, system: str, messages: list[dict]):
    resp = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=[{"type": "text", "text": system,
                 # The system prompt is byte-identical across every course, so
                 # it is worth caching; the brief goes in the user turn, after
                 # the breakpoint, where it invalidates nothing.
                 "cache_control": {"type": "ephemeral"}}],
        thinking={"type": "adaptive"},
        output_config={"effort": "high",
                       "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=messages,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"model refused: {getattr(resp, 'stop_details', None)}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError(
            f"response hit max_tokens ({MAX_TOKENS}); the graph is truncated. "
            "Raise MAX_TOKENS or narrow the brief.")
    text = "".join(b.text for b in resp.content if b.type == "text")
    # `resp.content` (not just the text) is what goes back on a repair turn:
    # thinking blocks must be echoed unchanged when continuing on the same model.
    return text, resp.usage, resp.content


# ------------------------------------------------------------------- extract

def extract(conn, course_id: str | None, brief: CourseBrief, *,
            client=None, model: str | None = None) -> ExtractionOutcome:
    """Run the extractor against a brief and validate the result.

    `conn` may be None (dry run, unit test) — then an escalation is raised but
    not recorded, and says so. `client` is injectable so a test can drive the
    parse/repair loop without a network call.
    """
    ref = prompts.load(PROMPT)
    parts = _sections(ref.body)
    missing = {"system", "brief", "repair"} - set(parts)
    if missing:
        raise RuntimeError(
            f"prompts/{PROMPT}.v{ref.file_version}.md is missing section(s) "
            f"{sorted(missing)}; expected `<!-- @section NAME -->` markers")

    model_id = model or settings().models.for_tier("frontier")
    client = client or _client(conn, course_id)
    user_turn = parts["brief"].replace("{brief}", brief.render_for_prompt())

    messages: list[dict] = [{"role": "user", "content": user_turn}]
    attempts: list[Attempt] = []

    for n in range(1, MAX_REPAIRS + 2):
        try:
            raw, usage, content = _call(client, model_id, parts["system"], messages)
        except Exception as e:
            attempts.append(Attempt(n=n, raw="", error=f"{type(e).__name__}: {e}"))
            escalation.raise_escalated(
                conn, stage=AGENT, error_class=_error_class(e), course_id=course_id,
                message=f"objective extraction call failed on attempt {n}/"
                        f"{MAX_REPAIRS + 1}: {type(e).__name__}: {e}",
                offending_input={"model": model_id, "prompt_version": ref.version,
                                 "brief_version": brief.version,
                                 "brief": brief.to_closure()},
                next_step="check `explainer doctor` for model/credential config, "
                          "then re-run `explainer objectives extract`. If the model "
                          "id is wrong, fix MODEL_FRONTIER in .env — it is pinned "
                          "on purpose and must name a model that exists.")
            raise  # unreachable; raise_escalated always raises

        attempt = Attempt(
            n=n, raw=raw,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cost_usd=_price(model_id, usage))
        attempts.append(attempt)

        try:
            objectives, items, rationales, out_of_scope, learner_facing = parse(raw)
        except SchemaError as e:
            attempt.error = str(e)
            if n > MAX_REPAIRS:
                escalation.raise_escalated(
                    conn, stage=AGENT, error_class="llm_schema", course_id=course_id,
                    message=f"objective extraction produced invalid output "
                            f"{MAX_REPAIRS + 1} times. Last errors: {e}",
                    offending_input={"model": model_id, "prompt_version": ref.version,
                                     "brief_version": brief.version,
                                     "last_raw_response": raw[:8000],
                                     "problems": e.problems},
                    next_step="read the raw response above. If the model is wrong, "
                              "the fix is prompts/objective_extractor.v1.md (bump to "
                              "v2 — prompts are code). If the SCHEMA is wrong, fix "
                              "OUTPUT_SCHEMA and re-run. Do not hand-edit the output.")
            # Re-prompt with the errors. The model's own attempt stays in the
            # conversation so it repairs rather than starts over.
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user",
                 "content": parts["repair"].replace("{errors}", e.as_prompt_text())},
            ]
            continue

        # Deterministic checks. Their findings are REPORTED, never repaired.
        report = validate(objectives, items=items)
        return ExtractionOutcome(
            objectives=objectives, items=items, report=report,
            provenance=provenance(ref.version, model_id, brief.version, n),
            attempts=attempts, rationales=rationales,
            out_of_scope=out_of_scope, learner_facing=learner_facing)

    raise AssertionError("unreachable: loop always returns or escalates")


def provenance(prompt_version: str, model_version: str, brief_version: int,
               attempt: int) -> dict:
    """R6. Written onto every objective and assessment item row.

    `extracted_at` is metadata about the run, not an input to it — it must never
    reach a hash closure (invariant 1).
    """
    return {
        "agent": AGENT,
        "prompt_version": prompt_version,
        "model_version": model_version,
        "brief_version": brief_version,
        "attempt": attempt,
        "extracted_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _error_class(e: Exception) -> str:
    """Map an SDK exception onto the §6.4 retry classes."""
    name = type(e).__name__
    if name in {"RateLimitError", "APIConnectionError", "APITimeoutError",
                "InternalServerError"}:
        return "llm_transient"
    if name in {"BadRequestError", "NotFoundError"}:
        return "internal"      # a wrong pinned model or a malformed schema
    return "llm_transient" if "Status" in name else "internal"
