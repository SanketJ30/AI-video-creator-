"""Persisting and loading the objective graph (PRD v0.2 §5.3).

Three tables, one shape: `objectives` holds the nodes, `objective_edges` holds
the prerequisite DAG, `assessment_items` holds the constructive-alignment
evidence. Two rules govern all of it:

**The teaching order is derived, never stored.** `check_dag`'s topological sort
IS the sequencing algorithm; caching its result would let the stored order drift
away from the edges that produced it, and then a human is looking at an order
the system does not actually believe. `load` recomputes it every time. It is a
sort over a handful of nodes — the cost is nothing and the guarantee is total.

**`ref` is stable; the uuid is an implementation detail.** Everything a human
sees, everything a gold file names, and every edge is keyed on `ref` (o1, o2).
The uuid exists so Postgres can enforce the foreign keys. Same reasoning as
invariant 4: key nothing on something that can move.

`save` replaces the whole graph for a course inside one transaction. Objective
extraction is not incremental — it produces a graph, and half a graph is worse
than none.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import db
from .objectives import (
    AssessmentItem,
    Bloom,
    KnowledgeType,
    Objective,
    ValidationReport,
    check_dag,
    validate,
)


@dataclass
class CourseGraph:
    objectives: list[Objective]
    items: list[AssessmentItem] = field(default_factory=list)
    teaching_order: list[str] = field(default_factory=list)
    provenance: dict[str, dict] = field(default_factory=dict)
    rationales: dict[str, str] = field(default_factory=dict)
    # ref -> speakable short form (migration 0004). The §9.1 objective slot
    # speaks this verbatim and it is reused as that scene's title.
    learner_facing: dict[str, str] = field(default_factory=dict)

    def validate(self) -> ValidationReport:
        return validate(self.objectives, items=self.items)

    def by_ref(self) -> dict[str, Objective]:
        return {o.ref: o for o in self.objectives}

    def edges(self) -> set[tuple[str, str]]:
        """(prerequisite, objective) pairs — the DAG, as a set."""
        return {(p, o.ref) for o in self.objectives for p in o.prerequisites}


def teaching_order(objectives: list[Objective]) -> list[str]:
    """Derived course order. Empty findings are the caller's problem — a cycle
    yields a partial order and a blocking finding from `validate`."""
    return check_dag(objectives)[1]


# ------------------------------------------------------------------- save

def save(conn, course_id: str, objectives: list[Objective],
         items: list[AssessmentItem] | None = None,
         provenance: dict | None = None,
         rationales: dict[str, str] | None = None,
         learner_facing: dict[str, str] | None = None) -> CourseGraph:
    """Replace the course's objective graph. All-or-nothing.

    Deletes first: an extraction that drops an objective must actually drop it,
    or the next run silently teaches something nobody asked for. `objective_edges`
    and `assessment_items` cascade from `objectives`.
    """
    items = items or []
    rationales = rationales or {}
    learner_facing = learner_facing or {}
    db.execute(conn, "delete from objectives where course_id = %s", (course_id,))

    ids: dict[str, str] = {}
    for o in objectives:
        prov = dict(provenance or {})
        if rationales.get(o.ref):
            prov["rationale"] = rationales[o.ref]
        row = db.one(conn, """
            insert into objectives(course_id, ref, verb, object, condition, criterion,
                                   bloom_level, knowledge_type, assumed,
                                   learner_facing_statement, provenance)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id
        """, (course_id, o.ref, o.verb, o.object, o.condition, o.criterion,
              o.bloom_level.value, o.knowledge_type.value, o.assumed,
              learner_facing.get(o.ref) or None, json.dumps(prov)))
        ids[o.ref] = str(row["id"])

    for o in objectives:
        for p in o.prerequisites:
            if p not in ids:
                # `validate` already reports this as blocking (unknown_prerequisite).
                # Writing a dangling edge is not possible — the FK forbids it — so
                # the edge is dropped and the finding is what tells the human.
                continue
            db.execute(conn, """
                insert into objective_edges(course_id, prerequisite_id, objective_id)
                values (%s,%s,%s) on conflict do nothing
            """, (course_id, ids[p], ids[o.ref]))

    for it in items:
        if it.objective_ref not in ids:
            continue          # reported by validate as orphan_assessment
        db.execute(conn, """
            insert into assessment_items(course_id, objective_id, bloom_level,
                                         kind, stem, provenance)
            values (%s,%s,%s,%s,%s,%s)
        """, (course_id, ids[it.objective_ref], it.bloom_level.value, it.kind,
              it.stem, json.dumps(provenance or {})))

    return load(conn, course_id)


# ------------------------------------------------------------------- load

def load(conn, course_id: str) -> CourseGraph:
    rows = db.query(conn, """
        select id, ref, verb, object, condition, criterion, bloom_level,
               knowledge_type, assumed, learner_facing_statement, provenance
          from objectives where course_id = %s order by ref""", (course_id,))
    by_id = {str(r["id"]): r["ref"] for r in rows}

    prereqs: dict[str, list[str]] = {r["ref"]: [] for r in rows}
    for e in db.query(conn, """
            select prerequisite_id, objective_id from objective_edges
             where course_id = %s""", (course_id,)):
        src = by_id.get(str(e["prerequisite_id"]))
        dst = by_id.get(str(e["objective_id"]))
        if src and dst:
            prereqs[dst].append(src)

    objectives = [
        Objective(ref=r["ref"], verb=r["verb"], object=r["object"],
                  bloom_level=Bloom(r["bloom_level"]),
                  knowledge_type=KnowledgeType(r["knowledge_type"]),
                  condition=r["condition"], criterion=r["criterion"],
                  prerequisites=sorted(prereqs[r["ref"]]), assumed=r["assumed"])
        for r in rows
    ]

    items = [
        AssessmentItem(ref=f"a{i + 1}", objective_ref=by_id[str(r['objective_id'])],
                       bloom_level=Bloom(r["bloom_level"]), kind=r["kind"],
                       stem=r["stem"])
        for i, r in enumerate(db.query(conn, """
            select objective_id, bloom_level, kind, stem from assessment_items
             where course_id = %s order by created_at, id""", (course_id,)))
        if str(r["objective_id"]) in by_id
    ]

    prov = {r["ref"]: (r["provenance"] or {}) for r in rows}
    return CourseGraph(
        objectives=objectives, items=items,
        teaching_order=teaching_order(objectives),
        provenance=prov,
        rationales={ref: p.get("rationale", "") for ref, p in prov.items()
                    if p.get("rationale")},
        learner_facing={r["ref"]: r["learner_facing_statement"] for r in rows
                        if r["learner_facing_statement"]},
    )


def render(graph: CourseGraph) -> str:
    """Human-readable graph, in teaching order — the order the DAG derived, not
    the order the model happened to emit."""
    by_ref = graph.by_ref()
    lines = []
    for i, ref in enumerate(graph.teaching_order, 1):
        o = by_ref[ref]
        tag = "ASSUMED" if o.assumed else f"{o.bloom_level.value}/{o.knowledge_type.value}"
        deps = f"  <- {', '.join(o.prerequisites)}" if o.prerequisites else ""
        lines.append(f"{i:>2}. {o.ref:<4} [{tag}] {o.statement}{deps}")
        for it in graph.items:
            if it.objective_ref == ref:
                lines.append(f"        assess [{it.bloom_level.value}/{it.kind}] "
                             f"{it.stem}")
    stranded = sorted({o.ref for o in graph.objectives} - set(graph.teaching_order))
    for ref in stranded:
        lines.append(f"    {ref:<4} [UNORDERED — in a prerequisite cycle]")
    return "\n".join(lines)
