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

---

## ISSUE-4 — v0.2 has no transition grammar or variety budget · SPEC GAP

**Missing from:** Sequence v0.2. **Present in:** PRD_v4 §13.5, which v0.2
supersedes.

PRD_v4 §13.5 stated both halves concretely:

> - Every scene node declares its transition to the next: `hard_cut` |
>   `cross_dissolve` | `match_cut{shared_element}` | `wipe_reveal`.
> - **Variety budget:** the same template may not fire more than **2 times
>   consecutively**; the agent must substitute or justify, and a justification
>   surfaces as a Gate B flag.
> - `match_cut` requires both scenes to share a registered element.

Neither appears anywhere in v0.2. Grep confirms: no `transition grammar`, no
`variety budget`, no consecutive-template rule. The `transitions` table exists in
migration 0002 with a `kind` column defaulting to `cut`, so the data model kept
what the spec dropped.

**Why it matters now.** Video v2's first visual plan put `table_build` on 4 of 9
scenes, including three consecutive (s05, s06, s07). Under PRD_v4's rule that
would have flagged. Under v0.2 nothing flags, because there is no rule. Every
individual choice was defensible; the sequence is monotonous.

**Not reconstructed here, deliberately.** Restoring §13.5's numbers into code
would make a superseded PRD's decisions into current behaviour by the back door,
and the "2 consecutive" figure is exactly the sort of thing that should be
re-decided rather than inherited. **This needs to come back into Sequence v0.2 as
spec.**

**What week 4 does in the meantime:** the linter reports the distribution of
templates across a video and flags any template exceeding a share threshold. That
threshold is AUTHORED AND UNREVIEWED and sits in the same marked table as the
duration bands. It is a warning with a visible number to argue with — not a rule,
and explicitly not §13.5.

---

## ISSUE-5 — §9.2 requires signalling in every scene; five templates cannot host it · OPEN

**Tension between:** §9.2 Signalling — *"Every scene contains 1–3 signalling
events. Never zero, never more than 3 concurrent"* — and `templates.py`, where
`key_phrase`, `term_card`, `concept_illustration`, `title_card` and `cold_open`
declare `supports_signalling = False`.

**The flag is mine, not the spec's.** §9.2 states the 1–3 rule and the permitted
signal types; nothing in v0.2 says a template may decline to host one. I set
those five to False on the judgement that a single typeset phrase has nothing to
point *at*, which is defensible but is an authored decision creating a conflict
with a stated rule.

Two ways out, and it is a spec question rather than a code one:

1. **Every template must host signalling** — flip all five to True and let the
   signal designer find something to highlight, satisfying §9.2 literally.
2. **§9.2's rule applies only to templates that can host a cue** — the current
   behaviour, which means "never zero" is not literally true.

**Current behaviour, pending that decision:** scenes on a signalling-capable
template must carry 1–3 cues, enforced as blocking. Scenes on the other five
carry zero and are not flagged. On video v2 that means 4 of 9 scenes are exempt
from a rule §9.2 states without exceptions.

---

## ISSUE-6 — §9.3's ≤3 text elements is unsatisfiable by two registered templates · OPEN

**Tension between:** §9.3 — *"≤3 simultaneous text elements"* — and
`templates.py`, where `table_build` and `terminal_replay` exist specifically to
put a sequence of short text rows on screen.

Measured across the registry with a minimal realistic fill of each template:

| template | text elements | fires §9.3 |
|---|---|---|
| cold_open | 1 | no |
| key_phrase | 1 | no |
| title_card | 2 | no |
| term_card | 2 | no |
| labelled_diagram | 2 | no |
| concept_illustration | 2 | no |
| series_build | 3 | no |
| **table_build** | **4** | **yes** |
| **terminal_replay** | **5** | **yes** |

Only those two, and they fire *by construction*: a 2×2 table is the smallest
useful table and it is already 4 elements. Any real use of either template
warns.

**Why it is not counted differently.** A build's rows arrive one at a time but
they do not leave — at the end of a `table_build` every cell is on screen
together, which is what "simultaneous" measures. Counting filled *slots* instead
(a table = one element) was implemented, measured, and reverted: it drops the
maximum across all 11 templates to 2, so the rule can never fire on anything and
is worthless.

**So the count is right and the conflict is real.** It is a spec question:

1. **§9.3's cap applies to independent text elements, not to the rows of one
   structured element** — needs v0.2 to say so, and needs a number for rows.
2. **The cap stands and the two templates are wrong** — they should cap their
   own row counts, which makes `terminal_replay` nearly useless.
3. **The cap stands and the warning is correct** — current behaviour: every
   table and terminal scene carries a §9.3 warning a human dismisses.

**Current behaviour, pending that decision:** option 3. Warning, never blocking.
On video v2 this fires on the 4 `table_build` scenes noted in the week-4
findings, so it compounds with the template-variety flag on the same scenes.
