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

# A hand alignment's third verdict, alongside covered and missing. A gold
# objective the run was never meant to teach is neither.
EXCLUDED_BY_SCOPE = "excluded_by_scope"


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

    # How the alignment was arrived at. "hand" means a human wrote it down for
    # THIS run; "approximate" means the content scorer guessed. The label is
    # printed on every diff because the two carry completely different
    # authority, and a reader who cannot tell them apart will trust the guess.
    method: str = "approximate"
    method_detail: str = "content scorer, Jaccard over token sets"
    # gold ref -> extracted refs that together cover it (hand alignment only).
    coverage: dict[str, list[str]] = field(default_factory=dict)
    coverage_notes: dict[str, str] = field(default_factory=dict)
    # Gold objectives a human has ruled deliberately out of this run's scope
    # — in_milestone_a false, over the video budget, declared in
    # out_of_scope. NOT missing: scoring them as missing punishes the exact
    # behaviour the prompt specifies, which would train the next prompt
    # version toward over-emitting.
    excluded: list[str] = field(default_factory=list)

    @property
    def approximate(self) -> bool:
        return self.method != "hand"

    @property
    def max_bloom_distance(self) -> int:
        return max((m.distance for m in self.bloom), default=0)

    def chain_intact(self, chain: list[str]) -> bool:
        """Is `chain` present as *direct* prerequisite edges in the extraction?

        Direct, not transitive: the gold notes are explicit that a flattened
        chain is a failure, and transitivity would let A->C plus B->C pass as
        A->B->C.
        """
        present = self.coverage if self.method == "hand" else self.mapping
        missing = set(self.missing_edges)
        return all((chain[i], chain[i + 1]) not in missing
                   and present.get(chain[i]) and present.get(chain[i + 1])
                   for i in range(len(chain) - 1))

    def render(self) -> str:
        if self.method == "hand":
            out = [f"alignment: HAND ({self.method_detail})",
                   "  gold <- extracted refs that together cover it:"]
            for gref in sorted(self.coverage):
                if not self.coverage[gref]:
                    continue          # shown once, below, as MISSING
                out.append(f"    {gref:<5} <- {', '.join(self.coverage[gref])}")
            for ref in self.missing:
                out.append(f"    {ref:<5} <- (nothing)   MISSING")
            for ref in self.excluded:
                out.append(f"    {ref:<5} <- (nothing)   excluded by scope, "
                           f"not counted")
            if self.extra:
                out.append(f"    unmapped extracted: {', '.join(self.extra)}")
        else:
            out = [f"alignment: APPROXIMATE ({self.method_detail})",
                   "  treat these pairings as a guess, not a verdict — supply",
                   "  --alignment with a hand-authored file to remove the guess.",
                   "  gold <- extracted, content score:"]
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
        if self.coverage_notes:
            out.append("coverage notes (from the hand alignment):")
            for gref in sorted(self.coverage_notes):
                note = " ".join(self.coverage_notes[gref].split())
                out.append(f"    {gref}: {note}")
        clean = not (self.missing or self.extra or self.bloom or self.missing_edges
                     or self.extra_edges)
        out.append("verdict: matches the gold graph" if clean
                   else f"verdict: {len(self.missing)} missing, {len(self.extra)} extra, "
                        f"{len(self.bloom)} bloom, "
                        f"{len(self.missing_edges)} missing edges")
        if self.approximate:
            out.append("         (approximate — no hand alignment for this run)")
        return "\n".join(out)


# ------------------------------------------------- hand-authored alignments

@dataclass
class AlignmentRun:
    """One recorded run's hand alignment. Immutable once written."""

    run: str
    prompt_version: str = ""
    # Two runs of the SAME prompt against DIFFERENT briefs are different
    # runs, and the v3/brief-v2 experiment proved they can produce the same
    # objective count. Without this the matcher sees two candidates, finds
    # no unique hit, and silently falls back to the scorer.
    brief_version: int | None = None
    extracted_count: int | None = None
    note: str = ""
    verdict: str = ""
    coverage: dict[str, list[str]] = field(default_factory=dict)
    coverage_notes: dict[str, str] = field(default_factory=dict)
    # gold ref -> the human's verdict. `excluded_by_scope` is load-bearing:
    # see GraphDiff.excluded.
    coverage_verdicts: dict[str, str] = field(default_factory=dict)
    unmapped_extracted: list[str] = field(default_factory=list)


@dataclass
class AlignmentFile:
    path: Path
    gold_file: str = ""
    runs: list[AlignmentRun] = field(default_factory=list)

    def by_run(self, run: str) -> AlignmentRun | None:
        return next((r for r in self.runs if r.run == run), None)

    def match(self, prompt_version: str, count: int,
              brief_version: int | None = None) -> AlignmentRun | None:
        """Find the entry recorded for THIS extraction.

        Matching on prompt version and objective count, not on "the newest
        entry", is the guard against the stale-alignment failure: reusing a v1
        alignment to score a v2 extraction is the same class of error as a stale
        cache hit, and it would silently flatter whichever run it was written
        for. A near-miss is not a match — it falls back to the scorer and says
        so.
        """
        stem = (prompt_version or "").split("+")[0]      # drop the body sha
        hits = [r for r in self.runs
                if (not r.prompt_version or r.prompt_version.split("+")[0] == stem)
                and (r.extracted_count is None or r.extracted_count == count)
                and (r.brief_version is None or brief_version is None
                     or r.brief_version == brief_version)]
        # Prefer the entry that names THIS brief version. An older entry
        # recorded before brief_version existed carries None and would
        # otherwise act as a wildcard, silently scoring a run it was not
        # written for — the exact failure this matcher exists to prevent.
        exact = [r for r in hits if r.brief_version == brief_version]
        if len(exact) == 1:
            return exact[0]
        return hits[0] if len(hits) == 1 else None


def load_alignment(path: str | Path) -> AlignmentFile:
    p = Path(path)
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    runs = []
    for raw in doc.get("runs") or []:
        cov, notes, verdicts = {}, {}, {}
        for gref, entry in (raw.get("coverage") or {}).items():
            if isinstance(entry, dict):
                cov[str(gref)] = [str(x) for x in (entry.get("extracted") or [])]
                if entry.get("comment"):
                    notes[str(gref)] = str(entry["comment"])
                if entry.get("verdict"):
                    verdicts[str(gref)] = str(entry["verdict"])
            else:                                   # bare list shorthand
                cov[str(gref)] = [str(x) for x in (entry or [])]
        runs.append(AlignmentRun(
            run=str(raw.get("run") or "?"),
            prompt_version=str(raw.get("prompt_version") or ""),
            brief_version=(int(raw["brief_version"])
                           if raw.get("brief_version") is not None else None),
            extracted_count=(int(raw["extracted_count"])
                             if raw.get("extracted_count") is not None else None),
            note=str(raw.get("note") or ""),
            verdict=str(raw.get("verdict") or ""),
            coverage=cov, coverage_notes=notes, coverage_verdicts=verdicts,
            unmapped_extracted=[str(x) for x in (raw.get("unmapped_extracted") or [])],
        ))
    return AlignmentFile(path=p, gold_file=str(doc.get("gold_file") or ""), runs=runs)


def diff_with_alignment(extracted: list[Objective], gold: GoldGraph,
                        run: AlignmentRun, source: str) -> GraphDiff:
    """Diff using a human's coverage mapping instead of the scorer.

    Coverage is one-to-many by design: the v1 finding was that the extractor
    splits one gold objective across several, which a 1:1 matcher can only
    report as "missing". Here a gold objective is covered when the extracted set
    collectively teaches it, and the checks below are group-shaped to match.
    """
    ext = {o.ref: o for o in extracted}
    gld = gold.by_ref()
    d = GraphDiff(method="hand", method_detail=source,
                  coverage={g: list(v) for g, v in run.coverage.items()},
                  coverage_notes=dict(run.coverage_notes))

    # Refs a human named that no longer exist are a stale alignment, not a
    # finding about the model — say so loudly rather than scoring around it.
    unknown = sorted({r for refs in run.coverage.values() for r in refs} - set(ext))
    if unknown:
        raise ValueError(
            f"alignment {source} names extracted refs that are not in this graph: "
            f"{unknown}. It was written for a different run — re-record it, or "
            f"drop --alignment to fall back to the approximate scorer.")

    # The same staleness, from the other side: an entry written before the
    # gold was amended can name a gold objective that no longer exists. Its
    # coverage judgment for that ref is meaningless and the rest is suspect.
    stale_gold = sorted(set(run.coverage) - set(gld))
    if stale_gold:
        raise ValueError(
            f"alignment {source} covers gold refs that {gold.path.name} no "
            f"longer has: {stale_gold}. The gold was amended after this entry "
            f"was written — record a new run rather than reusing it.")

    covered = {g: [ext[r] for r in refs] for g, refs in run.coverage.items() if refs}
    d.excluded = sorted(ref for ref, v in run.coverage_verdicts.items()
                        if v == EXCLUDED_BY_SCOPE)
    d.missing = sorted(g.ref for g in gold.objectives
                       if not covered.get(g.ref) and g.ref not in d.excluded)
    mapped = {r for refs in run.coverage.values() for r in refs}
    d.extra = sorted(set(ext) - mapped)

    for gref in sorted(covered):
        if gref not in gld:
            continue
        g, group = gld[gref], covered[gref]
        # A group satisfies the gold Bloom level if ANY member reaches it —
        # the others are the sub-steps the gold folded into its criterion.
        if not any(e.bloom_level is g.bloom_level for e in group):
            closest = min(group, key=lambda e: abs(e.bloom_level.rank - g.bloom_level.rank))
            d.bloom.append(BloomMismatch(gref, closest.ref, g.bloom_level,
                                         closest.bloom_level))
        if not any(e.knowledge_type is g.knowledge_type for e in group):
            d.knowledge.append((gref, g.knowledge_type.value,
                                "/".join(sorted({e.knowledge_type.value for e in group}))))
        if g.assumed and not any(e.assumed for e in group):
            d.assumed_mismatch.append(f"{gref} (gold=assumed, no member assumed)")

    # An edge between two gold objectives survives if any member of the earlier
    # group is a direct prerequisite of any member of the later one. Direct, not
    # transitive — a flattened chain must still fail (gold note 1).
    for a, b in sorted(gold.edges()):
        # An edge into or out of an excluded objective is not a missing edge.
        if a in d.excluded or b in d.excluded:
            continue
        if not covered.get(a) or not covered.get(b):
            continue
        a_refs = {e.ref for e in covered[a]}
        if any(p in a_refs for e in covered[b] for p in e.prerequisites):
            continue
        d.missing_edges.append((a, b))
    return d


def diff(extracted: list[Objective], gold: GoldGraph,
         alignment: AlignmentFile | None = None,
         prompt_version: str = "", run: str | None = None,
         brief_version: int | None = None) -> GraphDiff:
    """Diff an extraction against the gold graph.

    Uses a hand alignment when the file has an entry recorded for this run;
    otherwise falls back to the content scorer and labels the result
    approximate. It never silently picks an entry that was written for a
    different run.
    """
    if alignment is not None:
        entry = (alignment.by_run(run) if run
                 else alignment.match(prompt_version, len(extracted),
                                      brief_version))
        if entry is not None:
            return diff_with_alignment(
                extracted, gold, entry, f"{alignment.path.name}, run {entry.run}")

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
