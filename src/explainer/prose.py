"""Deterministic prose gates (Sequence v0.2 §9.2 Personalisation, §9.3, §9.6).

    §9.6: "Deterministic (code, fast, free) — text density, word counts, element
     counts, contrast ratios, cue count per scene, video duration, term-registry
     violations, readability, passive-voice ratio, objective-assessment Bloom
     alignment, DAG acyclicity, glyph coverage, caption safe area."

Code only. No model calls, ever. These run before anything expensive and they
are the part of the pedagogy claim a buyer can be shown working, so an opinion
dressed as a measurement would be worse than no gate at all.

Three gates:

  * **Readability** — Flesch-Kincaid grade. §9.2 Personalisation: "Flesch-Kincaid
    <= 9 general / <= 11 technical." Warning.
  * **Passive voice** — §9.2: "Passive voice <= 20%." Warning. See the heuristic's
    documented limits in `passive_sentences`.
  * **Speaking rate** — §9.3: "135-160 wpm technical; up to 185 wpm narrative."
    A slot whose words cannot be spoken in its budget is a finding. Blocking past
    20% over, because the narration physically does not fit and no downstream
    stage can absorb it.

NOT here: redundancy against on-screen text. That is §9.4 and it needs the
storyboard, which does not exist until week 4. A redundancy gate written now
would have nothing to compare the narration against.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import db

# §9.2 Personalisation
FK_GRADE_GENERAL = 9.0
FK_GRADE_TECHNICAL = 11.0
PASSIVE_RATIO_MAX = 0.20

# §9.3 Speaking rate. The low end is what a dense slot can be delivered at
# without losing the listener; the high end is the fastest a narrative slot can
# run before it stops sounding like teaching.
WPM_DENSE_MIN, WPM_DENSE_MAX = 135, 160
WPM_NARRATIVE_MAX = 185

# [AUTHORED] Overrun beyond this fraction of the slot budget is blocking rather
# than a warning. §9.3 gives the rates but no tolerance; 20% is the point past
# which trimming stops being an edit and becomes a rewrite.
OVERRUN_BLOCKING_RATIO = 0.20

# Slots whose job is narrative rather than dense explanation, so §9.3's faster
# ceiling applies. Everything else is measured against WPM_DENSE_MAX.
NARRATIVE_SLOTS = frozenset({"hook", "retain"})


@dataclass
class Finding:
    rule: str
    severity: str                 # blocking | warning | info
    subject: str                  # scene ref
    message: str
    measured: dict = field(default_factory=dict)
    threshold: dict = field(default_factory=dict)
    fix: str | None = None

    @property
    def blocking(self) -> bool:
        return self.severity == "blocking"


# ------------------------------------------------------------- text tools

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_VOWEL_GROUP = re.compile(r"[aeiouy]+")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def count_syllables(word: str) -> int:
    """Vowel-group heuristic with the usual silent-e correction.

    This is the standard approximation Flesch-Kincaid is computed with in
    practice. It is wrong on some words — "queue" counts 2, "business" counts 3 —
    but it is wrong the same way every time, which is what a threshold needs.
    """
    w = word.lower().strip("'’-")
    if not w:
        return 0
    groups = _VOWEL_GROUP.findall(w)
    n = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and n > 1:
        n -= 1
    return max(1, n)


def flesch_kincaid_grade(text: str) -> float:
    """FK grade level: 0.39*(words/sentences) + 11.8*(syllables/words) - 15.59.

    Implemented rather than imported: it is three numbers and a formula, and a
    dependency for it would be a dependency to audit.
    """
    sents = sentences(text)
    ws = words(text)
    if not sents or not ws:
        return 0.0
    syllables = sum(count_syllables(w) for w in ws)
    return round(0.39 * (len(ws) / len(sents)) + 11.8 * (syllables / len(ws)) - 15.59, 2)


# ---------------------------------------------------------- passive voice

_BE = r"(?:am|is|are|was|were|be|been|being|get|gets|got|gotten)"
# A past participle: regular -ed, or one of the irregulars that actually turn up
# in technical narration.
_IRREGULAR = (
    "given|taken|written|seen|shown|known|done|made|held|kept|left|read|set|put|"
    "sent|built|found|lost|drawn|thrown|chosen|broken|driven|risen|frozen|"
    "forgotten|hidden|bitten|beaten|blocked|aborted"
)
_PASSIVE = re.compile(
    rf"\b{_BE}\b(?:\s+\w+ly)?\s+(?:\w+ed|{_IRREGULAR})\b", re.IGNORECASE)


def passive_sentences(text: str) -> list[str]:
    """Sentences that look passive.

    **What it catches:** a form of "to be" (or "get") followed by a past
    participle, optionally with an adverb between — "is aborted", "was silently
    rolled back", "gets committed". This is the shape that carries almost all
    real passive voice in technical prose.

    **What it misses:**
      * passives with the participle far from the auxiliary ("was, after the
        second commit, aborted");
      * bare participial clauses with no auxiliary ("the row, updated by T2, …");
      * irregular participles outside the list above.

    **What it wrongly flags:**
      * adjectival predicates that are not passive at all — "the value is
        committed" reads as passive here, and "is interested", "is located",
        "is related" all match;
      * "get" used as a plain verb before an -ed adjective.

    So the ratio is an over-estimate more often than an under-estimate. That is
    the right direction for a warning-severity gate — it errs toward asking a
    human to look — but it is why this is a warning and never blocking, and why
    the docstring says so instead of the module claiming to detect passive voice.
    """
    return [s for s in sentences(text) if _PASSIVE.search(s)]


def passive_ratio(text: str) -> float:
    sents = sentences(text)
    if not sents:
        return 0.0
    return round(len(passive_sentences(text)) / len(sents), 4)


# ---------------------------------------------------------- speaking rate

def speakable_seconds(word_count: int, wpm: int) -> float:
    return round(word_count / wpm * 60, 1) if wpm else 0.0


def max_words_for(seconds: int, wpm: int) -> int:
    return int(seconds / 60 * wpm)


# ----------------------------------------------------------------- gates

def check_readability(scene_ref: str, text: str, technical: bool) -> list[Finding]:
    limit = FK_GRADE_TECHNICAL if technical else FK_GRADE_GENERAL
    grade = flesch_kincaid_grade(text)
    if grade <= limit:
        return []
    return [Finding(
        rule="readability_fk", severity="warning", subject=scene_ref,
        message=f"Flesch-Kincaid grade {grade} exceeds the "
                f"{'technical' if technical else 'general'} limit of {limit}.",
        measured={"fk_grade": grade,
                  "words": len(words(text)), "sentences": len(sentences(text))},
        threshold={"fk_grade_max": limit, "technical": technical},
        fix="split the longest sentence; one clause carrying one idea")]


def check_passive(scene_ref: str, text: str) -> list[Finding]:
    ratio = passive_ratio(text)
    if ratio <= PASSIVE_RATIO_MAX:
        return []
    flagged = passive_sentences(text)
    return [Finding(
        rule="passive_voice", severity="warning", subject=scene_ref,
        message=f"{ratio:.0%} of sentences look passive, over the "
                f"{PASSIVE_RATIO_MAX:.0%} limit. Flagged: "
                + " | ".join(f'"{s}"' for s in flagged[:3]),
        measured={"passive_ratio": ratio, "passive_sentences": len(flagged),
                  "sentences": len(sentences(text))},
        threshold={"passive_ratio_max": PASSIVE_RATIO_MAX},
        fix="name the actor: 'PostgreSQL aborts the transaction', not "
            "'the transaction is aborted'")]


def check_speaking_rate(scene_ref: str, text: str, budget_seconds: int,
                        slot: str) -> list[Finding]:
    """§9.3. A slot whose words cannot be spoken in its budget is a finding.

    Measured against the FASTEST acceptable rate for the slot: if the narration
    does not fit even when rushed, it does not fit at all.
    """
    if budget_seconds <= 0:
        return []
    ceiling = WPM_NARRATIVE_MAX if slot in NARRATIVE_SLOTS else WPM_DENSE_MAX
    n = len(words(text))
    allowed = max_words_for(budget_seconds, ceiling)
    if n <= allowed:
        return []

    overrun = (n - allowed) / allowed if allowed else 1.0
    blocking = overrun > OVERRUN_BLOCKING_RATIO
    needed = speakable_seconds(n, ceiling)
    return [Finding(
        rule="speaking_rate", severity="blocking" if blocking else "warning",
        subject=scene_ref,
        message=f"{n} words need {needed}s at {ceiling} wpm but the "
                f"{slot} slot budgets {budget_seconds}s "
                f"({overrun:.0%} over; {allowed} words fit).",
        measured={"words": n, "seconds_needed_at_max_wpm": needed,
                  "overrun_ratio": round(overrun, 4), "wpm_ceiling": ceiling},
        threshold={"budget_seconds": budget_seconds, "max_words": allowed,
                   "wpm_ceiling": ceiling,
                   "blocking_over_ratio": OVERRUN_BLOCKING_RATIO},
        fix=f"cut to {allowed} words, or move the surplus into an adjacent slot")]


@dataclass
class ProseReport:
    findings: list[Finding]

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]

    @property
    def ok(self) -> bool:
        return not self.blocking

    def render(self) -> str:
        if not self.findings:
            return "prose gates: all pass"
        lines = []
        for f in sorted(self.findings, key=lambda f: (not f.blocking, f.subject, f.rule)):
            mark = "BLOCK" if f.blocking else f.severity.upper()[:4]
            lines.append(f"[{mark}] {f.rule} · {f.subject}: {f.message}")
            if f.fix:
                lines.append(f"        fix: {f.fix}")
        return "\n".join(lines)


def check_scene(scene_ref: str, text: str, budget_seconds: int, slot: str,
                technical: bool = False) -> list[Finding]:
    return (check_readability(scene_ref, text, technical)
            + check_passive(scene_ref, text)
            + check_speaking_rate(scene_ref, text, budget_seconds, slot))


def check_script(scenes: list[dict], technical: bool = False) -> ProseReport:
    """Run every gate over a video's scenes.

    `scenes` are rows as `script_writer.load` returns them: `ref`, `text`,
    `gagne_slot`, and `pedagogy_meta.duration_target_seconds`.
    """
    findings: list[Finding] = []
    for s in scenes:
        meta = s.get("pedagogy_meta") or {}
        findings += check_scene(
            scene_ref=s["ref"], text=s.get("text") or "",
            budget_seconds=int(meta.get("duration_target_seconds") or 0),
            slot=s.get("gagne_slot") or "", technical=technical)
    return ProseReport(findings)


# ------------------------------------------------------------ persistence

def save_findings(conn, video_id: str, report: ProseReport,
                  scene_ids: dict[str, str] | None = None) -> int:
    """Write to linter_findings. §9.6: the report is a customer-visible artifact,
    so it is stored rather than only returned."""
    scene_ids = scene_ids or {}
    db.execute(conn, """delete from linter_findings
                         where video_id = %s and rule in
                               ('readability_fk','passive_voice','speaking_rate')""",
               (video_id,))
    for f in report.findings:
        db.execute(conn, """
            insert into linter_findings(video_id, scene_id, rule, severity,
                                        message, measured, threshold, fix)
            values (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (video_id, scene_ids.get(f.subject), f.rule, f.severity, f.message,
              json.dumps(f.measured), json.dumps(f.threshold),
              json.dumps({"suggestion": f.fix}) if f.fix else None))
    return len(report.findings)
