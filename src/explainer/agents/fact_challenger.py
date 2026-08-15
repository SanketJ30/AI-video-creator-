"""The Fact Challenger — §7.2 Tier 2, ISSUE-8.

§7.2 specifies a *Fact Checker*: "claims extracted, each independently verified
with sources, confidence scored. Anything below threshold gets flagged in the
UI, never silently kept." This implements it **adversarially**: the model is
asked to REFUTE each claim, not to verify it.

## Why adversarial rather than verifying

ISSUE-8 is the specimen. v2 s04 said *"Neither transaction writes the row the
other one reads"* — the exact inversion of write skew, in the scene carrying the
video's thesis, in prose fluent enough to read as authoritative. Every
deterministic gate passed it, because every §9.6 rule measures FORM. A model
asked "is this correct?" agrees with fluent prose; a model asked "show me this
is wrong" has to engage with the mechanism.

This is the same reasoning §14.4's harness applies to itself: a check that can
only confirm is not a check.

## Findings attach to spans (R3/R4)

A verdict on a scene tells a reviewer to re-read ninety seconds of narration. A
verdict on `sp_b735cd9656` tells them which sentence. Spans are already the unit
cues anchor to and captions are cut at, so they are the unit a challenge belongs
to as well.

## The threshold

§7.2 says "anything below threshold gets flagged" and gives no number.
`AUTHORED_MIN_CONFIDENCE` is marked and is the number to argue with. Note what
it gates: it does NOT decide whether a claim is false, it decides whether the
CHALLENGER's own verdict is confident enough to raise. A low-confidence
`refuted` is still shown — it is demoted to a warning, not discarded, because
the expensive failure here is silence.

## What this does not do

No sources are fetched. §7.2 says "independently verified with sources" and this
version verifies against the model's own knowledge, which is weaker. It is
recorded here rather than implied: a `survives` verdict from this agent means
"an adversarial reading did not break it", not "a source confirms it".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .. import db, prompts
from ..config import settings
from . import objective_extractor as ox

AGENT = "fact_challenger"
PROMPT = "fact_challenger"
MAX_REPAIRS = 2
MAX_TOKENS = 32000

VERDICTS = ("refuted", "unsupported", "survives")

# ===========================================================================
# AUTHORED AND UNREVIEWED — §7.2 says "anything below threshold gets flagged"
# and names no threshold.
#
# This gates the CHALLENGER's confidence in its own verdict, not the truth of
# the claim. Below it a `refuted` becomes a warning rather than blocking; it is
# never discarded, because ISSUE-8's whole lesson is that silence is the
# expensive failure.
# ===========================================================================
AUTHORED_MIN_CONFIDENCE = 0.70

OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "span_id": {"type": "string"},
                    "claim": {"type": "string"},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                    "confidence": {"type": "number"},
                    # The attack made, whether or not it succeeded. A `survives`
                    # with no attack described is not a result.
                    "attack": {"type": "string"},
                    "correction": {"type": "string"},
                    "contradicts": {"type": "string"},
                },
                "required": ["span_id", "claim", "verdict", "confidence",
                             "attack", "correction", "contradicts"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["findings"],
    "additionalProperties": False,
}


@dataclass
class Challenge:
    span_id: str
    claim: str
    verdict: str
    confidence: float
    attack: str = ""
    correction: str = ""
    contradicts: str = ""
    scene_ref: str = ""

    @property
    def blocking(self) -> bool:
        """A confident refutation stops the video. §7.2: never silently kept."""
        return (self.verdict == "refuted"
                and self.confidence >= AUTHORED_MIN_CONFIDENCE)

    @property
    def severity(self) -> str:
        if self.verdict == "refuted":
            return "blocking" if self.blocking else "warning"
        return "warning" if self.verdict == "unsupported" else "info"

    def to_json(self) -> dict:
        return {"span_id": self.span_id, "claim": self.claim,
                "verdict": self.verdict, "confidence": self.confidence,
                "attack": self.attack, "correction": self.correction,
                "contradicts": self.contradicts, "scene_ref": self.scene_ref,
                "severity": self.severity}


@dataclass
class ChallengeReport:
    scenes: dict = field(default_factory=dict)      # scene_ref -> [Challenge]
    attempts: list = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    @property
    def all(self) -> list[Challenge]:
        return [c for cs in self.scenes.values() for c in cs]

    @property
    def refuted(self) -> list[Challenge]:
        return [c for c in self.all if c.verdict == "refuted"]

    @property
    def blocking(self) -> list[Challenge]:
        return [c for c in self.all if c.blocking]

    @property
    def ok(self) -> bool:
        return not self.blocking

    @property
    def cost_usd(self) -> float:
        return round(sum(a.cost_usd for a in self.attempts), 6)

    def render(self) -> str:
        lines: list[str] = []
        for sev in ("blocking", "warning", "info"):
            group = [c for c in self.all if c.severity == sev]
            if not group:
                continue
            lines.append(f"{sev.upper()} ({len(group)})")
            for c in sorted(group, key=lambda x: (x.scene_ref, x.span_id)):
                lines.append(f"  [{c.scene_ref} {c.span_id}] {c.verdict} "
                             f"(confidence {c.confidence:.2f})")
                lines.append(f"      claim:  {c.claim}")
                lines.append(f"      attack: {c.attack}")
                if c.correction:
                    lines.append(f"      should say: {c.correction}")
                if c.contradicts:
                    lines.append(f"      contradicts: {c.contradicts}")
        if not self.all:
            lines.append("no claims extracted")
        return "\n".join(lines)


def parse(raw: str, spans: list[dict]) -> list[Challenge]:
    """Model text -> challenges, validated against the spans it was given."""
    problems: list[str] = []
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ox.SchemaError([f"response is not valid JSON: {e}"]) from None

    known = {s["id"] for s in spans}
    out: list[Challenge] = []
    for i, f in enumerate(doc.get("findings") or []):
        where = f"findings[{i}]"
        span_id = str(f.get("span_id") or "").strip()
        if span_id not in known:
            # R3's rule applied to findings: a verdict on a span that does not
            # exist points a reviewer at nothing.
            problems.append(
                f"{where}: span_id {span_id!r} is not in this scene. Spans: "
                f"{sorted(known)}")
            continue
        verdict = str(f.get("verdict") or "").strip().lower()
        if verdict not in VERDICTS:
            problems.append(f"{where}: verdict {verdict!r} is not one of "
                            f"{list(VERDICTS)}")
            continue
        try:
            confidence = float(f.get("confidence"))
        except (TypeError, ValueError):
            problems.append(f"{where}: confidence must be a number 0-1")
            continue
        if not 0.0 <= confidence <= 1.0:
            problems.append(f"{where}: confidence {confidence} is outside 0-1")
            continue
        attack = str(f.get("attack") or "").strip()
        if not attack:
            problems.append(
                f"{where}: every verdict needs the attack that produced it. A "
                f"'survives' with no attack described is not a result.")
            continue
        if verdict == "refuted" and not str(f.get("correction") or "").strip():
            problems.append(
                f"{where}: a refutation must say what a correct version would "
                f"say, or a human cannot act on it.")
            continue
        out.append(Challenge(
            span_id=span_id, claim=str(f.get("claim") or "").strip(),
            verdict=verdict, confidence=confidence, attack=attack,
            correction=str(f.get("correction") or "").strip(),
            contradicts=str(f.get("contradicts") or "").strip()))

    if problems:
        raise ox.SchemaError(problems)
    return out


def challenge_scene(conn, course_id: str | None, scene_ref: str,
                    spans: list[dict], context: dict, *, client=None,
                    model: str | None = None) -> tuple[list[Challenge], list]:
    """Challenge one scene's narration. Returns (challenges, attempts)."""
    ref = prompts.load(PROMPT)
    parts = ox._sections(ref.body)
    missing = {"system", "scenes", "repair"} - set(parts)
    if missing:
        raise RuntimeError(
            f"prompts/{PROMPT}.v{ref.file_version}.md is missing {sorted(missing)}")

    # The FRONTIER tier, deliberately. This is the one agent whose job is to be
    # right about the world rather than to follow a form, and it is the last
    # line before a human.
    model_id = model or settings().models.for_tier("frontier")
    client = client or ox._client(conn, course_id)

    user = (parts["scenes"]
            .replace("{context}", json.dumps(context, indent=2, ensure_ascii=False))
            .replace("{spans}", json.dumps(spans, indent=2, ensure_ascii=False)))
    messages = [{"role": "user", "content": user}]
    attempts: list = []

    for n in range(MAX_REPAIRS + 2):
        raw, usage, content = _call(client, model_id, parts["system"], messages)
        attempts.append(ox.Attempt(
            n=n + 1, raw=raw,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cost_usd=ox._price(model_id, usage)))
        try:
            found = parse(raw, spans)
        except ox.SchemaError as e:
            attempts[-1].error = str(e)
            if n > MAX_REPAIRS:
                raise
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user",
                 "content": parts["repair"].replace("{errors}", e.as_prompt_text())},
            ]
            continue
        for c in found:
            c.scene_ref = scene_ref
        return found, attempts

    raise AssertionError("unreachable")


def challenge(conn, course_id: str | None, scenes: list[dict], context: dict,
              *, client=None, model: str | None = None) -> ChallengeReport:
    """Challenge every scene. One call per scene: a claim is judged against its
    own scene's narration, and a whole video in one prompt buries the span ids."""
    ref = prompts.load(PROMPT)
    report = ChallengeReport(provenance={
        "agent": AGENT,
        "prompt_version": ref.version,
        "model_version": model or settings().models.for_tier("frontier"),
        "at": datetime.now(UTC).isoformat(),
        "min_confidence": AUTHORED_MIN_CONFIDENCE,
        "verifies_against": "model knowledge, not sources (see module docstring)",
    })
    for scene in scenes:
        found, attempts = challenge_scene(
            conn, course_id, scene["ref"], scene["spans"], context,
            client=client, model=model)
        report.scenes[scene["ref"]] = found
        report.attempts += attempts
    return report


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


def save(conn, video_id: str, report: ChallengeReport,
         scene_ids: dict[str, str] | None = None) -> int:
    """§4.3: the report is customer-visible, so it is stored."""
    scene_ids = scene_ids or {}
    n = 0
    for c in report.all:
        db.execute(conn, """
            insert into linter_findings(video_id, scene_id, rule, severity,
                                        message, measured, threshold, fix)
            values (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (video_id, scene_ids.get(c.scene_ref), f"fact_{c.verdict}",
              c.severity,
              f"[{c.span_id}] {c.claim} — {c.attack}",
              json.dumps({"confidence": c.confidence, "span_id": c.span_id,
                          "contradicts": c.contradicts}),
              json.dumps({"min_confidence": AUTHORED_MIN_CONFIDENCE}),
              # `fix` is jsonb, so the correction travels as a JSON string
              # rather than bare text.
              json.dumps(c.correction) if c.correction else None))
        n += 1
    return n
