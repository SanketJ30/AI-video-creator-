# Known issues

Named, numbered, and cited to the spec section they break. This file exists so a
defect that undermines a product claim cannot sit in a paragraph of a findings
doc that someone skims.

Status values: **BLOCKING** (a product claim is decoration until it is fixed),
**MEASURED** (real, understood, deliberately not being chased), **STANDING** (an
operational rule that applies from now on).

---

## ISSUE-1 — the recall slot does not link to the previous video · BLOCKING

**Breaks:** Sequence v0.2 §9.1 slot 3 — *"recall ≤20s, link to a prior objective
BY ID (course memory)"*. Undermines **Wedge A**, the course-continuity claim
(§1.3), which is the product's first differentiator.

**Why it is blocking rather than a quality issue.** The claim being sold is that
video 6 correctly assumes what video 2 taught. If the recall slot instead asserts
prior teaching that never happened, the continuity is not merely weak — it is
false, and a learner meets a video that tells them they already know something
they have never been shown. A wrong recall is worse than no recall.

**Status of the plumbing: correct.** `cli._course_position` passes the previous
video's ref, title, and every objective it taught with that objective's
learner-facing statement. Verified on video v2, which received:

    previous.objectives = [
      {ref: o4, statement: "You'll see how Postgres keeps several versions of a
                            row and picks the one you get."},
      {ref: o5, statement: "You'll work out exactly what each transaction reads,
                            and when it took its snapshot."}]

`prompts/script_writer.v2.md` has a *"The recall slot and course memory"* section
instructing the slot to activate one of those by name.

**Status of the behaviour: wrong.** v2's recall slot (scene s03) instead recalled
this video's own subject matter:

> You already know how Postgres's Repeatable Read isolation behaves: it blocks a
> non-repeatable read, blocks a phantom, and blocks two transactions from losing
> an update when they write the same row — each one stopped with a
> could-not-serialize error.

Neither `o4` nor `o5` is referenced. Wiring correct, prompt correct, behaviour
wrong.

**The measured registry evidence is worse than it first looked.** The terms that
sentence presents as already-known appear in *no* video's `new_terms` registry:

    v1 registry:  s04 [xmin, xmax, snapshot]   s05 [repeatable read]
    v2 registry:  s04 [snapshot, write skew]   s05 [serializable isolation,
                                                     select for update]

`non-repeatable read` and `phantom` are in neither. They are not v2's own new
terms being falsely back-dated — they are introduced in the recall slot as
already-known and never registered as introduced at all. Under the gate below
they fail on both clauses.

**The fix, when Stage 2c is next opened.** A deterministic gate, no threshold to
invent — set membership, not similarity:

1. On a video with a previous video, the recall slot's scene must reference at
   least one `objective_ref` taught by that previous video.
2. Every term the recall slot presents as already-known must appear in a
   previous video's `new_terms` registry.

Clause 2 requires the **per-course term registry** already flagged as a known gap
at the end of week 3: `new_terms` is currently computed per video, so `snapshot`
is registered as new in *both* v1 and v2 — visible in the table above. A
per-course registry is a schema change, and clause 2 cannot be enforced without
it.

**Not fixed in week 4.** Week 4 is Stage 3, storyboard and linter. This is Stage
2c.

---

## ISSUE-2 — one of the three anomalies is absent from the built narration · MEASURED

**Relates to:** §9.2 coherence; the gold's `extraction_note` 2, the
ANSI-vs-PostgreSQL trap.

The objective graph names all three anomalies in 3 of 3 harness samples at
`max_videos: 2`. The built video's narration names two:

    non-repeatable read   PRESENT
    phantom               PRESENT
    dirty read            ABSENT
    write skew            PRESENT
    serializable          PRESENT

**Deliberately not chased.** Under a 300-second budget, dropping one of three
anomalies is a defensible editorial cut, and §9.2's coherence principle —
*reject anything not serving the objective* — arguably favours it: dirty read is
the one anomaly Read Committed also prevents, so it discriminates least. Recorded
here so it is not rediscovered as a surprise during week 6 review, and so the gap
between graph coverage (3/3) and screen coverage (2/3) is a known quantity rather
than a defect someone finds.

---

## ISSUE-3 — script_writer MAX_TOKENS has been raised three times · STANDING

16000 → 32000 → 64000. Each overrun surfaced as a correct escalation with the
model, prompt version and video ref attached, never as a silent truncation, so
the invariant-7 path is doing its job. But the ceiling has now moved three times
for the same reason: adaptive thinking counts against `max_tokens`, and the
prompt has grown a section at each Stage 2c revision.

**Standing rule: a fourth overrun is not a ceiling problem.** 64000 is half of
Sonnet 5's output limit and a nine-slot script is a few thousand tokens of
narration. If it overruns again, the thing to examine is `output_config.effort`
— currently `high` on every agent — not `MAX_TOKENS`. Raising the ceiling a
fourth time would be treating the symptom.
