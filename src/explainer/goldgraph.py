"""Hand-authored gold graphs, and diffing an extraction against one.

A gold file is a human's answer to "what should this course teach?", written
before the machine got a vote. `tests/gold/*.yaml` holds them. They are the only
way to tell an extractor that got lucky from one that is right, and they are
checked into git so a prompt or model change is measured, not guessed at (§14.4).

## Why matching is fuzzy, and why that is not a fudge

Refs are arbitrary labels. The extractor has no way to know the gold file calls
snapshot isolation `o1`, and aligning by position would make "missed the first
objective" look like "got all four wrong". So alignment is by content: token
overlap over verb + object + condition, greedy, highest score first, ties broken
alphabetically. It is deterministic — the same two graphs always produce the same
diff — and the alignment itself is printed, so a human can see and reject a
pairing the score got wrong. Nothing here calls a model; a model-scored diff
would be a rubber stamp on its own homework.

## What the diff reports

  * missing objectives — in the gold, no counterpart in the extraction
  * extra objectives   — in the extraction, no counterpart in the gold
  * wrong Bloom levels — matched pair, different level, with the rank distance
  * wrong edges        — the prerequisite chain, mapped through the alignment

Edges are the finding that matters most. A gold file's note usually says it
outright: an extractor that flattens `o1 -> o2 -> o3` into three independents has
produced a plausible-looking list and destroyed the sequencing this whole system
exists for.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .objectives import AssessmentItem, Bloom, KnowledgeType, Objective

# Words that carry no discriminating signal between two objective statements.
_STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by",
    "at", "from", "as", "is", "are", "was", "be", "been", "it", "its", "that",
    "this", "these", "those", "which", "how", "why", "what", "whether", "each",
    "given", "when", "will", "can", "does", "do", "has", "have", "not", "no",
    "one", "two", "any", "some", "into", "over", "under", "their", "there",
}
MATCH_THRESHOLD = 0.22      # tuned to accept paraphrase, reject a different topic


@dataclass
class GoldGraph:
    path: Path
    topic: str = ""
    engine: str | None = None
    audience: dict = field(default_factory=dict)
    objectives: list[Objective] = field(default_factory=list)
    items: list[AssessmentItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Per-ref annotations the deterministic core has no opinion about — e.g.
    # `in_milestone_a: false` for an objective a later video owns. Kept out of
    # `Objective` on purpose: scheduling is not part of an objective's identity.
    scope: dict[str, bool] = field(default_factory=dict)

    def by_ref(self) -> dict[str, Objective]:
        return {o.ref: o for o in self.objectives}

    def edges(self) -> set[tuple[str, str]]:
        return {(p, o.ref) for o in self.objectives for p in o.prerequisites}


def load_gold(path: str | Path) -> GoldGraph:
    p = Path(path)
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    objectives, scope = [], {}
    for raw in doc.get("objectives") or []:
        ref = str(raw["ref"])
        objectives.append(Objective(
            ref=ref,
            verb=str(raw["verb"]).strip().lower(),
            object=str(raw["object"]).strip(),
            bloom_level=Bloom(str(raw["bloom_level"]).strip().lower()),
            knowledge_type=KnowledgeType(str(raw["knowledge_type"]).strip().lower()),
            condition=(raw.get("condition") or None),
            criterion=(raw.get("criterion") or None),
            prerequisites=[str(x) for x in (raw.get("prerequisites") or [])],
            assumed=bool(raw.get("assumed", False)),
        ))
        scope[ref] = bool(raw.get("in_milestone_a", True))
    items = [
        AssessmentItem(ref=str(raw["ref"]), objective_ref=str(raw["objective_ref"]),
                       bloom_level=Bloom(str(raw["bloom_level"]).strip().lower()),
                       kind=str(raw["kind"]), stem=str(raw["stem"]))
        for raw in (doc.get("assessment_items") or [])
    ]
    return GoldGraph(
        path=p, topic=str(doc.get("topic") or ""), engine=doc.get("engine"),
        audience=doc.get("audience") or {}, objectives=objectives, items=items,
        notes=[str(n) for n in (doc.get("extraction_notes") or [])], scope=scope,
    )


# ------------------------------------------------------------------ matching

def _tokens(o: Objective) -> set[str]:
    text = " ".join(filter(None, [o.verb, o.object, o.condition or ""]))
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOP and len(w) > 1}


def similarity(a: Objective, b: Objective) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb) / len(ta | tb)
    # A shared verb is weak evidence on its own ("explain" is everywhere), so it
    # nudges rather than decides.
    return round(overlap + (0.05 if a.verb == b.verb else 0.0), 6)


def align(extracted: list[Objective],
          gold: list[Objective]) -> tuple[dict[str, str], list[tuple[str, str, float]]]:
    """Greedy content alignment. Returns (gold_ref -> extracted_ref, scored pairs)."""
    pairs = sorted(
        ((similarity(e, g), g.ref, e.ref) for g in gold for e in extracted),
        key=lambda t: (-t[0], t[1], t[2]),
    )
    mapping: dict[str, str] = {}
    used: set[str] = set()
    scored: list[tuple[str, str, float]] = []
    for score, gref, eref in pairs:
        if score < MATCH_THRESHOLD or gref in mapping or eref in used:
            continue
        mapping[gref] = eref
        used.add(eref)
        scored.append((gref, eref, score))
    return mapping, scored


# ---------------------------------------------------------------------- diff

@dataclass
class BloomMismatch:
    gold_ref: str
    extracted_ref: str
    expected: Bloom
    got: Bloom

    @property
    def distance(self) -> int:
        return abs(self.expected.rank - self.got.rank)


@dataclass
class GraphDiff:
    mapping: dict[str, str] = field(default_factory=dict)
    scores: list[tuple[str, str, float]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)        # gold refs not found
    extra: list[str] = field(default_factory=list)          # extracted refs unmatched
    bloom: list[BloomMismatch] = field(default_factory=list)
    knowledge: list[tuple[str, str, str]] = field(default_factory=list)
    missing_edges: list[tuple[str, str]] = field(default_factory=list)  # gold refs
    extra_edges: list[tuple[str, str]] = field(default_factory=list)    # gold refs
    assumed_mismatch: list[str] = field(default_factory=list)

    @property
    def max_bloom_distance(self) -> int:
        return max((m.distance for m in self.bloom), default=0)

    def chain_intact(self, chain: list[str]) -> bool:
        """Is `chain` present as *direct* prerequisite edges in the extraction?

        Direct, not transitive: the gold notes are explicit that a flattened
        chain is a failure, and transitivity would let A->C plus B->C pass as
        A->B->C.
        """
        return all((chain[i], chain[i + 1]) not in set(self.missing_edges)
                   and chain[i] in self.mapping and chain[i + 1] in self.mapping
                   for i in range(len(chain) - 1))

    def render(self) -> str:
        out = ["alignment (gold <- extracted, content score):"]
        for gref, eref, score in sorted(self.scores):
            out.append(f"    {gref:<5} <- {eref:<5} {score:.2f}")
        for ref in self.missing:
            out.append(f"    {ref:<5} <- (nothing)   MISSING")
        for ref in self.extra:
            out.append(f"    {'-':<5} <- {ref:<5} EXTRA")
        if self.bloom:
            out.append("bloom levels:")
            for m in self.bloom:
                out.append(f"    {m.gold_ref} ({m.extracted_ref}): expected "
                           f"{m.expected.value}, got {m.got.value} "
                           f"(off by {m.distance})")
        if self.knowledge:
            out.append("knowledge types:")
            for ref, exp, got in self.knowledge:
                out.append(f"    {ref}: expected {exp}, got {got}")
        if self.assumed_mismatch:
            out.append("assumed flag differs: " + ", ".join(self.assumed_mismatch))
        if self.missing_edges:
            out.append("missing prerequisite edges (gold refs):")
            for a, b in self.missing_edges:
                out.append(f"    {a} -> {b}")
        if self.extra_edges:
            out.append("extra prerequisite edges (gold refs):")
            for a, b in self.extra_edges:
                out.append(f"    {a} -> {b}")
        clean = not (self.missing or self.extra or self.bloom or self.missing_edges
                     or self.extra_edges)
        out.append("verdict: matches the gold graph" if clean
                   else f"verdict: {len(self.missing)} missing, {len(self.extra)} extra, "
                        f"{len(self.bloom)} bloom, "
                        f"{len(self.missing_edges)} missing edges")
        return "\n".join(out)


def diff(extracted: list[Objective], gold: GoldGraph) -> GraphDiff:
    mapping, scores = align(extracted, gold.objectives)
    ext = {o.ref: o for o in extracted}
    gld = gold.by_ref()
    rev = {v: k for k, v in mapping.items()}

    d = GraphDiff(
        mapping=mapping, scores=scores,
        missing=[o.ref for o in gold.objectives if o.ref not in mapping],
        extra=[o.ref for o in extracted if o.ref not in rev],
    )
    for gref, eref in sorted(mapping.items()):
        g, e = gld[gref], ext[eref]
        if g.bloom_level is not e.bloom_level:
            d.bloom.append(BloomMismatch(gref, eref, g.bloom_level, e.bloom_level))
        if g.knowledge_type is not e.knowledge_type:
            d.knowledge.append((gref, g.knowledge_type.value, e.knowledge_type.value))
        if g.assumed != e.assumed:
            d.assumed_mismatch.append(f"{gref} (gold={g.assumed}, got={e.assumed})")

    # Compare edges in GOLD ref space: translate the extraction's edges back
    # through the alignment so a human reads one vocabulary, not two.
    ext_edges: set[tuple[str, str]] = set()
    for o in extracted:
        if o.ref not in rev:
            continue
        for p in o.prerequisites:
            if p in rev:
                ext_edges.add((rev[p], rev[o.ref]))
    gold_edges = {(a, b) for a, b in gold.edges()
                  if a in mapping and b in mapping}
    d.missing_edges = sorted(gold_edges - ext_edges)
    d.extra_edges = sorted(ext_edges - gold_edges)
    return d
