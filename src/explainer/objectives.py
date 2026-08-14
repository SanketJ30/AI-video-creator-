"""Objective schema and validation (PRD v0.2 §5.3).

All three checks here are CODE, not agents (§7.1 rule 4: "deterministic checks
beat agentic checks"). They are the cheapest part of the pedagogy engine and the
part a buyer can be shown.

    - Reject non-observable verbs: understand, know, learn, appreciate...
    - Constructive alignment: every objective needs >=1 assessment item at the
      SAME Bloom level. "The most common real-world ID failure is Apply-level
      objectives assessed by Remember-level MCQs. The engine refuses to ship this."
    - prerequisiteObjectiveIds form a DAG -> topological sort DERIVES course
      order. Cycle detection is a hard error.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Bloom(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"

    @property
    def rank(self) -> int:
        return list(Bloom).index(self)


class KnowledgeType(str, Enum):
    FACTUAL = "factual"
    CONCEPTUAL = "conceptual"
    PROCEDURAL = "procedural"
    METACOGNITIVE = "metacognitive"


# Verbs that describe an internal state nobody can observe. An objective built on
# one of these cannot be assessed, which means it cannot be verified, which means
# the whole constructive-alignment chain is decorative.
BANNED_VERBS: dict[str, str] = {
    "understand": "explain, predict, or compare",
    "know": "state, list, or identify",
    "learn": "apply or demonstrate",
    "appreciate": "justify or evaluate",
    "be familiar with": "identify or describe",
    "be aware of": "identify",
    "grasp": "explain or predict",
    "comprehend": "explain or summarise",
    "realise": "explain",
    "internalise": "apply",
    "become comfortable with": "use or apply",
    "gain insight into": "analyse or explain",
    "study": "analyse",
    "think about": "evaluate or justify",
}

# Observable verbs by Bloom level. Not exhaustive — extend deliberately, and keep
# each verb at exactly one level so the alignment check stays unambiguous.
VERB_WHITELIST: dict[Bloom, set[str]] = {
    Bloom.REMEMBER: {"define", "list", "state", "name", "recall", "identify",
                     "recognise", "recognize", "label"},
    Bloom.UNDERSTAND: {"explain", "describe", "summarise", "summarize",
                       "paraphrase", "classify", "illustrate", "interpret"},
    Bloom.APPLY: {"apply", "use", "compute", "execute", "implement", "solve",
                  "demonstrate", "predict", "write", "configure"},
    Bloom.ANALYZE: {"analyse", "analyze", "compare", "contrast", "differentiate",
                    "diagnose", "trace", "decompose", "distinguish"},
    Bloom.EVALUATE: {"evaluate", "justify", "critique", "assess", "defend",
                     "recommend", "select", "prioritise", "prioritize"},
    Bloom.CREATE: {"design", "compose", "construct", "formulate", "build",
                   "generate", "plan"},
}

_VERB_LEVEL: dict[str, Bloom] = {
    v: lvl for lvl, verbs in VERB_WHITELIST.items() for v in verbs
}


@dataclass
class Objective:
    ref: str
    verb: str
    object: str
    bloom_level: Bloom
    knowledge_type: KnowledgeType
    condition: str | None = None
    criterion: str | None = None
    prerequisites: list[str] = field(default_factory=list)
    # Declared prerequisite the course does NOT teach. Lets a single-video
    # Milestone A stand on honest foundations rather than pretending.
    assumed: bool = False

    @property
    def statement(self) -> str:
        parts = [self.verb, self.object]
        if self.condition:
            parts.insert(0, self.condition + ",")
        if self.criterion:
            parts.append(f"({self.criterion})")
        return " ".join(parts)


@dataclass
class AssessmentItem:
    ref: str
    objective_ref: str
    bloom_level: Bloom
    kind: str
    stem: str


@dataclass
class Finding:
    rule: str
    severity: str          # blocking | warning | info
    subject: str
    message: str
    fix: str | None = None

    @property
    def blocking(self) -> bool:
        return self.severity == "blocking"


# ------------------------------------------------------------------ validators

def check_verbs(objectives: list[Objective]) -> list[Finding]:
    out: list[Finding] = []
    for o in objectives:
        verb = o.verb.strip().lower()
        if verb in BANNED_VERBS:
            out.append(Finding(
                "observable_verb", "blocking", o.ref,
                f"'{verb}' describes an internal state and cannot be observed, "
                f"so no assessment item can verify it.",
                f"use {BANNED_VERBS[verb]}"))
            continue
        level = _VERB_LEVEL.get(verb)
        if level is None:
            out.append(Finding(
                "verb_whitelist", "warning", o.ref,
                f"'{verb}' is not in the verb whitelist, so its Bloom level "
                "cannot be checked automatically.",
                "add it to VERB_WHITELIST at the correct level, or pick a listed verb"))
        elif level is not o.bloom_level:
            out.append(Finding(
                "verb_bloom_mismatch", "blocking", o.ref,
                f"'{verb}' is a {level.value}-level verb but the objective is "
                f"declared {o.bloom_level.value}.",
                f"change the level to {level.value}, or pick a "
                f"{o.bloom_level.value}-level verb"))
    return out


def check_dag(objectives: list[Objective]) -> tuple[list[Finding], list[str]]:
    """Returns findings plus the derived teaching order (§5.3: the prerequisite
    DAG *is* the course-sequencing algorithm)."""
    out: list[Finding] = []
    by_ref = {o.ref: o for o in objectives}

    for o in objectives:
        for p in o.prerequisites:
            if p not in by_ref:
                out.append(Finding(
                    "unknown_prerequisite", "blocking", o.ref,
                    f"prerequisite '{p}' is not an objective in this course.",
                    "declare it as an assumed objective, or remove the edge"))

    indeg = {r: 0 for r in by_ref}
    children: dict[str, list[str]] = {r: [] for r in by_ref}
    for o in objectives:
        for p in o.prerequisites:
            if p in by_ref:
                children[p].append(o.ref)
                indeg[o.ref] += 1

    ready = sorted(r for r, d in indeg.items() if d == 0)
    order: list[str] = []
    while ready:
        r = ready.pop(0)
        order.append(r)
        for c in children[r]:
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
        ready.sort()

    if len(order) != len(by_ref):
        stuck = sorted(set(by_ref) - set(order))
        out.append(Finding(
            "prerequisite_cycle", "blocking", ", ".join(stuck),
            f"prerequisite cycle among {stuck}; no teaching order exists.",
            "break the cycle — one of these concepts must be teachable first"))

    # A concept can be assumed or taught, but assuming something you also teach
    # later means the video is using it before it is introduced.
    for o in objectives:
        if o.assumed and o.prerequisites:
            out.append(Finding(
                "assumed_with_prerequisites", "warning", o.ref,
                "an assumed objective should not declare prerequisites inside "
                "this course; it is supposed to arrive already known."))

    return out, order


def check_alignment(objectives: list[Objective],
                    items: list[AssessmentItem]) -> list[Finding]:
    """Constructive alignment. The check the PRD says the engine must refuse to
    ship without."""
    out: list[Finding] = []
    by_obj: dict[str, list[AssessmentItem]] = {}
    for it in items:
        by_obj.setdefault(it.objective_ref, []).append(it)

    for o in objectives:
        if o.assumed:
            continue        # assumed prerequisites are not taught, so not assessed
        mine = by_obj.get(o.ref, [])
        if not mine:
            out.append(Finding(
                "no_assessment", "blocking", o.ref,
                f"objective '{o.ref}' has no assessment item.",
                f"add at least one {o.bloom_level.value}-level item"))
            continue
        if not any(i.bloom_level is o.bloom_level for i in mine):
            levels = sorted({i.bloom_level.value for i in mine})
            out.append(Finding(
                "bloom_misalignment", "blocking", o.ref,
                f"objective '{o.ref}' is {o.bloom_level.value}-level but its "
                f"only assessment items are {levels}. Testing recall does not "
                f"verify the ability to {o.verb}.",
                f"add a {o.bloom_level.value}-level item"))

    orphans = sorted(set(by_obj) - {o.ref for o in objectives})
    for ref in orphans:
        out.append(Finding("orphan_assessment", "warning", ref,
                           f"assessment items reference unknown objective '{ref}'."))
    return out


@dataclass
class ValidationReport:
    findings: list[Finding]
    teaching_order: list[str]

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]

    @property
    def ok(self) -> bool:
        return not self.blocking

    def render(self) -> str:
        if not self.findings:
            return "objective graph: all checks pass"
        lines = []
        for f in sorted(self.findings, key=lambda f: (f.severity != "blocking", f.rule)):
            mark = "BLOCK" if f.blocking else f.severity.upper()[:4]
            lines.append(f"[{mark}] {f.rule} · {f.subject}: {f.message}"
                         + (f"\n        fix: {f.fix}" if f.fix else ""))
        return "\n".join(lines)


def validate(objectives: list[Objective],
             items: list[AssessmentItem] | None = None) -> ValidationReport:
    """Run every deterministic objective check. Called before a script is
    written — §6 Stage 2a: "a wrong objective graph poisons everything
    downstream, and it is cheap to fix here and expensive to fix later." """
    findings = check_verbs(objectives)
    dag_findings, order = check_dag(objectives)
    findings += dag_findings
    if items is not None:
        findings += check_alignment(objectives, items)
    return ValidationReport(findings, order)
