"""The per-course term registry — the course-memory primitive (§12, Wedge A).

Fixes ISSUE-7 and supplies the set ISSUE-1's recall gate tests membership
against. These are one piece of work, not two.

## What was wrong

`script_writer._assemble` seeded its running term set empty at the start of
every video, so `first_use_only` could only ever see within-video repeats. v2
declared `snapshot` a new term that v1 had already taught. The model claimed the
same thing, so the code-vs-model agreement rate read 9/9 — **100% agreement on a
wrong answer**, which is what happens when both sides share the same blind spot.

## What this is

A set union over terms already introduced in EARLIER videos of the same course,
read from `scenes.pedagogy_meta`. Deterministic. No model call. No threshold.
Nothing to tune.

The ordering is by the curriculum plan's ordinal, not by `created_at`: videos
are generated in whatever order a human asks for, and "what has the learner
already been taught" is a question about teaching order (§10.3), never about
when a row was written.

## Why the registry rather than a bigger prompt

The model is not asked to remember what video 1 taught. It is asked for the
terms it thinks it introduced, and code decides which of those are genuinely
first uses — the same division of labour §9.6 draws between deterministic and
agentic work. A prompt that carried the full prior-term list would grow without
bound across a 40-video course and would still be advisory.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import db


@dataclass(frozen=True)
class Registry:
    """What a course has already taught, as of one video."""

    # term -> ref of the earliest video that introduced it
    terms: dict[str, str] = field(default_factory=dict)
    # objective refs taught by the immediately preceding video
    previous_video_objectives: tuple[str, ...] = ()
    previous_video_ref: str | None = None
    # ordinal this registry was built for
    up_to_ordinal: int = 0

    def knows(self, term: str) -> bool:
        return term in self.terms

    def taught_by(self, term: str) -> str | None:
        return self.terms.get(term)

    @property
    def seen(self) -> set[str]:
        """A mutable copy for `first_use_only` to carry forward."""
        return set(self.terms)


def build(conn, course_id: str, up_to_ordinal: int) -> Registry:
    """Every term introduced by a video with a LOWER ordinal in this course.

    `up_to_ordinal` is exclusive: building for video 2 returns video 1's terms.
    Building for video 1 returns an empty registry, which is correct rather than
    a special case.
    """
    rows = db.query(conn, """
        select v.ref as video_ref, v.ordinal, s.ordinal as scene_ordinal,
               s.pedagogy_meta
          from videos_v2 v join scenes s on s.video_id = v.id
         where v.course_id = %s and v.ordinal < %s
         order by v.ordinal, s.ordinal
    """, (course_id, up_to_ordinal))

    terms: dict[str, str] = {}
    for r in rows:
        for term in ((r["pedagogy_meta"] or {}).get("new_terms") or []):
            # First writer wins: the earliest video that taught it owns it.
            terms.setdefault(term, r["video_ref"])

    prev = db.one(conn, """
        select id, ref from videos_v2
         where course_id = %s and ordinal = %s
    """, (course_id, up_to_ordinal - 1))
    prev_objectives: tuple[str, ...] = ()
    if prev:
        prev_objectives = tuple(r["ref"] for r in db.query(conn, """
            select o.ref from video_objectives vo
              join objectives o on o.id = vo.objective_id
             where vo.video_id = %s order by o.ref""", (str(prev["id"]),)))

    return Registry(
        terms=terms,
        previous_video_objectives=prev_objectives,
        previous_video_ref=(prev or {}).get("ref"),
        up_to_ordinal=up_to_ordinal)


# ------------------------------------------------------------- the gate
#
# ISSUE-1: §9.1 slot 3 (recall) is the course-memory mechanism behind Wedge A —
# "video 6 correctly assumes what video 2 taught". Week 3 shipped a recall slot
# that recalled THIS video's own content, and nothing caught it.
#
# Two checks, both set membership. Neither needs a threshold, a similarity
# measure or a model. That is the whole point: §9.6 puts this class of rule on
# the deterministic side, and a fuzzy version would be arguable exactly when it
# mattered.

def check_recall_slot(scene_ref: str, objective_ref: str | None,
                      claimed_known_terms: list[str],
                      registry: Registry) -> list[str]:
    """Problems with one recall scene. Empty means it passes.

    1. It must name at least one objective ref from the PREVIOUS video.
    2. Every term it presents as already-known must appear in the registry.

    Video 1 has no previous video, so its recall slot is exempt from (1) and
    every claimed-known term fails (2) unless the registry is non-empty — which
    is correct: video 1 cannot assume anything.
    """
    problems: list[str] = []

    if registry.previous_video_ref is None:
        if objective_ref or claimed_known_terms:
            problems.append(
                f"{scene_ref}: this is the first video in the course, so the "
                f"recall slot has nothing to recall — it must not present "
                f"anything as already known")
        return problems

    if objective_ref not in registry.previous_video_objectives:
        problems.append(
            f"{scene_ref}: recall names objective {objective_ref!r}, which is "
            f"not taught by the previous video "
            f"({registry.previous_video_ref}). §9.1 slot 3 links to a prior "
            f"objective BY ID — that link is the course-memory mechanism. "
            f"Available: {list(registry.previous_video_objectives)}")

    for raw in claimed_known_terms:
        term = raw.strip().lower()
        if not registry.knows(term):
            problems.append(
                f"{scene_ref}: recall presents {term!r} as already known, but "
                f"no earlier video in this course introduced it. Known so far: "
                f"{sorted(registry.terms)}")
    return problems
