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

**RESOLVED 15 Aug 2026 — option 3 (count strings), by human decision.** The
reasoning accepted: a completed `table_build` has all its cells on screen
together, which is what "simultaneous" measures, and counting slots makes the
rule dead code. Warning, never blocking.

**Still open for the PRD, and explicitly NOT to be invented here:** whether §9.3
should distinguish independent text elements from the rows of one structured
element, and if so what row-count allowance a build template gets. Until v0.2
answers that, every table and terminal scene carries a warning a human dismisses.

**Current behaviour:** option 3. Warning, never blocking.
On video v2 this fires on the 4 `table_build` scenes noted in the week-4
findings, so it compounds with the template-variety flag on the same scenes.

---

## ISSUE-7 — the `new_terms` registry is per-video, so video 2 re-teaches video 1's terms · BLOCKING

**Predicted in week 3, confirmed in week 4 on real data.** `docs/week3-findings.md`
said: *"nothing in the current design carries the term set across videos, so I
expect the first disagreement there rather than here."* v2 is the first second
video, and the prediction holds — though not in the shape expected.

Measured from stored `pedagogy_meta` on `mvcc-write-skew`:

```
v1 new_terms: xmin, xmax, snapshot, repeatable read
v2 new_terms: snapshot, write skew, serializable isolation, select for update
                ^^^^^^^^ already taught in v1
```

**The agreement rate did not catch it.** Code-computed and model-claimed
`new_terms` agree 9/9 on v1 and 9/9 on v2 — because `first_use_only` runs
against a set seeded empty at the start of each video, so the code and the
model make the *same* mistake. A 100% agreement rate on a wrong answer is worth
more attention than a disagreement would be: it means the check is measuring
consistency, not correctness.

**Why it matters beyond tidiness.** §9.2's pre-training rule fires on ">=3 new
technical terms", so a phantom "new" term inflates cognitive-load accounting.
More importantly this is the same root cause as [ISSUE-1](#issue-1): there is no
cross-video memory of what has been taught, which is Wedge A — *"video 6
correctly assumes what video 2 taught"* — and the thing the whole product is
supposed to be for.

**Fix, when Stage 2c is revisited:** seed the running term set from the union of
all previous videos' `new_terms` rather than from empty. That is a set union
over rows already in the database — deterministic, no model call, no threshold
to invent. It also supplies the second half of the recall-slot gate ISSUE-1
describes, which needs exactly this registry to check "every term presented as
already-known appears in a previous video's `new_terms`".

**Not fixed in week 4** on the same reasoning as ISSUE-1: it is a Stage 2c
defect and week 4 is Stage 2d. Logged, not chased.

**MERGED WITH ISSUE-1, 15 Aug 2026, and scheduled.** These are one piece of work,
not two: the per-course term registry is simultaneously the `new_terms` fix and
the set the recall-slot gate tests membership against. Both are blocking, both
sit on Wedge A — *"video 6 correctly assumes what video 2 taught"* — which is the
product's first wedge, so the pair goes at the **front of week 5, before any TTS
work**. Tracked as week 5 step 0.

---

## ISSUE-8 — s04 states the pivotal claim of the video backwards · BLOCKING

**Found by a human reading the script. Nothing in the pipeline can catch it, and
that is the finding.**

`mvcc-write-skew` v2, scene s04 (`present`, the 90s scene the whole video turns
on):

```
sp_b735cd9656  "Neither transaction writes the row the other one reads."
```

**False, and it is the exact inversion of the anomaly.** A writes A's row, which
B read; B writes B's row, which A read. Those two rw-antidependencies *are* write
skew — they are the thing SSI detects. The true statement is that neither
transaction writes the row the other **writes**: the absence of a write-write
collision is why Repeatable Read has nothing to catch.

The script gets that right one line later and does not notice the contradiction:

```
sp_1c3727ba32  "Repeatable Read watches for two transactions writing the same row"
```

**It also contradicts s07.** `sp_93758ba6db` says SERIALIZABLE "tracks what each
transaction reads, not just writes, and aborts one" — but if neither transaction
wrote what the other read, there would be no antidependency for SSI to find and
nothing to abort.

**The same confusion recurs in s05 and changes a recommendation:**

```
sp_fb5e4ab259  "But neither doctor's query updates the row it reads"
sp_d3de4b56b2  "each reads the whole list and writes only its own row."
```

Each transaction *does* update a row it read — its own row is in the list it
read. This is why `SELECT FOR UPDATE` gets dismissed at `sp_b66b284d03`, and the
dismissal is wrong: applied to the full read set it would in fact serialise the
two transactions and prevent the anomaly.

### Why no existing gate catches it

Every §9.6 deterministic rule is about *form* — word counts, element counts,
readability, cue anchoring. None reads the claim. The linter reports s04 clean on
every rule it has. The prose is excellent (`sp_6075dc41f2`, "It's a fact about
the relationship between rows", is the best line in the video). **The prose is
not the problem; one claim inside it is**, and that is precisely the class of
defect deterministic linting cannot reach.

### The named gap

§7.2 Tier 2 specifies **Fact Checker** — *"claims extracted, each independently
verified with sources, confidence scored. Anything below threshold gets flagged
in the UI, never silently kept."* It does not exist. `linter.MODEL_BASED_RULES`
already reserves `factual_confidence` for it, so the absence is visible in every
report, but nothing fills it.

*(Naming: v0.2 §7.2 calls this agent the Fact Checker. It has been referred to in
conversation as the "Fact Challenger" — same agent, and the spec's name is used
in code.)*

**WITHDRAWN:** I previously offered the objective extractor getting Repeatable
Read's semantics right as evidence that the Fact Checker might not be
load-bearing. That was wrong and this withdraws it. The extractor was correct
about a fact it was asked to classify; the script writer was wrong about a fact
it was asked to *explain*, in the one scene that carries the video's thesis, in
prose fluent enough that it reads as authoritative. Those are different jobs and
only the second is what §7.2's Fact Checker is for. **It is load-bearing.**

**Not fixed by hand, deliberately.** The pipeline produced this and the pipeline
must catch it. Editing the narration would remove the only real specimen we have
of the defect class the Fact Checker exists to find.

### Update, week 5 step 0 — the claim did not recur, and that changes nothing

v2 was regenerated under `script_writer.v3` for the recall gate (a different
change entirely). The new s04 does **not** contain the false claim; it says
*"Postgres never sees them touch the same row"* (true — they do not *write* the
same row) and *"the conflict lives across rows, in the rule connecting them"*
(true).

**This is not a fix and must not be recorded as one.** Nothing detected the
error; a re-roll of a stochastic stage simply landed differently. The gap is
exactly as open as it was — the next generation can reintroduce it, on this
video or any other, and no gate would notice. The original spans are preserved
above because they are the specimen.

If anything this strengthens the case for the Fact Checker: a defect that
appears and disappears across samples of the same prompt is one that manual
review will catch only when it happens to look.

---

## ISSUE-9 — speaking-rate overruns are systematic, and the video will run over · MEASURED

Four of nine scenes exceed their speaking-rate budget on v2. Warnings, none
blocking, but the direction is one-sided — which is what makes it a Stage 2c
prompt issue rather than noise.

Measured at 160 wpm from the stored narration:

| scene | slot | words | target | needs | over |
|---|---|---:|---:|---:|---:|
| s01 | hook | 39 | 15 | 14.6 | −2.5% |
| s02 | objective | 14 | 10 | 5.2 | −47.5% |
| **s03** | **recall** | **57** | **20** | **21.4** | **+6.9%** |
| s04 | present | 209 | 90 | 78.4 | −12.9% |
| **s05** | **guide** | **147** | **52** | **55.1** | **+6.0%** |
| **s06** | **elicit** | **52** | **17** | **19.5** | **+14.7%** |
| **s07** | **feedback** | **57** | **19** | **21.4** | **+12.5%** |
| s08 | assess | 25 | 10 | 9.4 | −6.2% |
| s09 | retain | 15 | 6 | 5.6 | −6.2% |

**The arithmetic that matters:**

```
targets sum                                    239 s
brief budget                                   240 s   (1 s of slack)
elastic scenes stretched to fit their words    248.4 s
                                               ------
over budget                                    +8.4 s
```

Every over-budget scene is `elastic`, so under §11.2's resolver they stretch to
fit the audio rather than truncating it. The 1 s of slack cannot absorb 8.4 s.
The only under-running scene with real room is s04 (`present`, −12.9%) and it is
**rigid**, so it will not give its time back.

**This is Stage 2c, not week 5.** The timing resolver will report the overrun
correctly; it is the script writer that is writing past its budget. Logged with
the arithmetic so the week-5 runtime can be checked against a prediction made
before TTS rather than explained after it.

**Prediction on record: the finished v2 runs long, by roughly 8 s, before any
TTS-rate variance.**

### Update, week 5 step 1 — the prediction was WRONG, and the reason matters

Measured against the pinned voice (`piper-tts@1.6.1 / en_US-lessac-medium`,
`noise_scale=0`), v2's nine scenes total **207.5 s against a 240 s budget —
32.5 s UNDER**, not 8 s over.

| scene | words | target | actual | wpm |
|---|---:|---:|---:|---:|
| s01 hook | 34 | 15 | 10.74 | 190 |
| s02 objective | 14 | 10 | 4.93 | 170 |
| s03 recall | 58 | 20 | 19.13 | 182 |
| s04 present | 246 | 90 | 79.09 | 187 |
| s05 guide | — | 52 | 48.31 | 196 |
| s06 elicit | — | 17 | 13.55 | 195 |
| s07 feedback | — | 19 | 17.24 | 209 |
| s08 assess | — | 10 | 8.75 | 206 |
| s09 retain | — | 6 | 5.76 | 208 |
| **total** | | **239** | **207.5** | **192** |

**The defect is not the script; it is the constant.** `prose.py` measures
speaking rate against **160 wpm**. The pinned voice actually delivers **192 wpm
averaged over the video**, ranging 170–209 by scene. So every
`speaking_rate` warning the linter has ever emitted was measured against a rate
this pipeline does not produce, and all four "over budget" scenes are in fact
comfortably under.

**This is a calibration defect in the gate, not a prompt defect** — the opposite
of what ISSUE-9 originally claimed, and the original claim is left above rather
than edited so the correction is visible.

**RESOLVED 15 Aug 2026 — the constant stays at 160 and the divergence is
deliberate.** §16.1's prosody gate is a pedagogical target; if it tracked the
pinned voice, swapping voices would silently move every readability verdict in
the corpus, so a script that passed would begin failing because the narrator
changed. `prose.py` now carries that reasoning at the constant.

Two things follow, and both are worth stating plainly:

1. `speaking_rate` findings run **~20% pessimistic** against this voice by
   design. A scene flagged "over budget" may fit comfortably. That is the
   accepted cost of a gate that does not move when the vendor does.
2. **The budget arithmetic that produced the original ISSUE-9 prediction was
   wrong at the source**, not just mis-transcribed here — it was a pre-week-5
   estimate made against the 160 wpm figure without a measured voice to check
   it. The eventual fix is a second per-voice measured rate used only for
   budgeting (W2), leaving §9.3's three numbers as the comprehension gate.

**Do not simply change 160 to 192.** Two reasons: 192 is one voice on one video
(n=1), and §12's prosody gate wants a *target* rate for comprehension, which is
a pedagogical number, not a measurement of whatever the current voice does. The
right shape is probably a measured per-voice rate used for BUDGETING and a
separate spec'd rate used for the comprehension gate. That is a decision for a
human — recorded in `week5-decisions-needed.md` as W2.

Note this makes ISSUE-10 worse, not better: the retain slot's 6 s now buys 5.76 s
of speech with 0.24 s to spare, so there is still no room for §9.1's
spaced-review hook.

---

## ISSUE-10 — the retain slot gets 2.5% of the video and §9.1 asks it to do two jobs · OPEN

s09 (`retain`) is budgeted **6 seconds**. §9.1 defines that slot as *"summary +
spaced-review scheduling hook"* — two jobs. Six seconds is 15 words at 160 wpm.
The scene the pipeline produced does one of them:

```
sp_8f3f52a97d  "Before you move on, say aloud how you'd spot write skew and pick its fix."
```

That is a retrieval prompt. There is no spaced-review scheduling hook, and there
is no room for one.

**Where the 6 seconds comes from.** `gagne.AUTHORED_TAIL_WEIGHTS` distributes
whatever is left after §9.1's capped slots. On v2:

```
present   90 s of 239   37.7%     (AUTHORED_PRESENT_SECONDS, rigid)
retain     6 s of 239    2.5%
```

**Flagged for review, not adjusted.** `AUTHORED_TAIL_WEIGHTS` is already marked
AUTHORED AND UNREVIEWED, and changing a weight to make one scene look better
would be tuning against a single video — the same n=1 mistake the week-2 harness
work was done to stop. The question for a human is whether §9.1's retain slot can
do both its jobs at any weighting that leaves `present` enough room, or whether
the spaced-review hook belongs outside the video entirely (§9.5 schedules
retrieval at the *course* level, which may be the real answer).

Note this interacts with ISSUE-9: retain is one of the scenes that fits, so
taking time from it to pay for the overruns is not available.

---

## ISSUE-11 — span segmentation splits on an ellipsis, so spans and TTS chunks disagree · FIXED

`Narration.from_text` treats `...` as a sentence terminator. On v2 s05 the
narration contains `SELECT ... FOR UPDATE`, which becomes **two spans**:

```
sp_…  "SELECT ..."
sp_…  "FOR UPDATE on the rows they read, take a table lock, …"
```

piper does not split there, so the scene produced **9 spans but 6 TTS chunks**
and `align.align` refused to align it — correctly. A positional guess would have
mistimed every cue in the scene.

**Three consequences, in order of seriousness:**

1. **A span that is not a sentence cannot be spoken as one.** `"SELECT ..."` on
   its own is not an utterance, and any per-span synthesis of it will sound
   wrong.
2. **Cues anchored to that span point at a fragment.** R3 anchoring assumes a
   span is a meaningful unit.
3. The caption for that span is a two-word orphan.

**Root cause is in `spans.py`, which is off-limits this week.** An ellipsis is
not a sentence boundary; neither is the `.` in `v1.2` or `Fig. 4`. The fix is a
sentence splitter that knows about them, and it belongs with whoever owns R4.

**Worked around, not fixed:** `tts.synthesize_spans` synthesises each span
separately and concatenates when the partitions disagree, so every span still
receives a measured start and end. The workaround is recorded on the audio
metadata (`per_span_fallback: true`) and reported by the CLI, so a scene using
it is visible rather than silently different from its neighbours.

**Do not "fix" this by relaxing the alignment check.** The check is what caught
it.

### FIXED, 15 Aug 2026

`spans.py` now masks every full stop that does not end a sentence before
splitting — ellipses, `i.e.`/`e.g.` and friends, decimals and version numbers —
and restores them after, so the text stays byte-identical. Tests cover
`SELECT ... FOR UPDATE`, `i.e.`, `e.g.`, `1.5 GB` and `16.2`, plus a guard that
real sentence boundaries still split.

On v2 this took the stored narration from 46 spans to 40 and the mismatched
scenes from 3 to 1.

**The remaining 1 is why per-scene synthesis was abandoned entirely.** MEASURED
on v2 s05: each of its 7 spans yields exactly 1 piper chunk when synthesised
alone, but all 7 together yield 6. piper's splitter merges differently depending
on surrounding context, so no amount of fixing OUR splitter makes the two agree.
Synthesis is now per span by construction — see **W5** in
`week5-decisions-needed.md`. The partition matches because it is never derived
twice.

---

## ISSUE-12 — the first full render produced a technically perfect SILENT video · FIXED

The first end-to-end run of `explainer render mvcc-write-skew v2` produced a
1920×1080, 30 fps, 3:39.07 MP4 with 48 kHz AAC audio, correct captions, a
correct word sidecar, and a runtime matching the resolved timeline to the
hundredth of a second.

**Every sample of its audio was digital silence.** `volumedetect` reported
`mean_volume: -91.0 dB, max_volume: -91.0 dB`.

### Why nothing caught it

Every check in the pipeline passed, and each one was right:

- durations resolved and frame-aligned — correct
- content hashes stable, cache hits clean — correct
- 46 caption cues ending at 219.06 s against a 219.07 s timeline — correct
- the render was byte-identical across two runs — correct
- `probe_duration` matched the resolver exactly — correct

The pipeline verified **structure** thoroughly and **signal** not at all.

### Root cause

Remotion's ProRes output already contains a **silent stereo PCM audio track**.
`mux_scene` passed the ProRes as input 0 and the narration PCM as input 1 with
no explicit `-map`. ffmpeg's default audio stream selection prefers the stream
with more channels, so it chose Remotion's silent **stereo** track over the
narration's **mono** one — and did so without warning, because picking a valid
audio stream is exactly what it is supposed to do.

### Fix

Explicit `-map 0:v:0 -map 1:a:0`, plus `_assert_audible()` after every mux,
which fails the build when a muxed scene peaks below −60 dB.

`"stream_map"` is now part of the mux closure. Without that, every mux made
before the fix would have been served from cache and stayed silent — the fix
would have appeared to do nothing, which is a worse failure than the original.

Measured after the fix, single scene s09: `mean_volume -18.7 dB, max_volume
-0.5 dB`.

### The lesson worth keeping

A content-addressed pipeline verifies that outputs are *reproducible*, not that
they are *right*. Determinism said the silence was perfectly reproducible
silence. **Add a signal check at every boundary where a stream can be dropped**,
not only a structural one — and note that this is the same shape as ISSUE-8,
where the prose was fluent and the claim was false. Both are cases of a check
that measures form passing something wrong in substance.

---

## ISSUE-13 — §9.2 signalling is absent from two thirds of the video, and the signal designer is not at fault · FIXED

**Question asked: did the signal designer produce cues the renderer then dropped,
or never produce them? Answer: never produced, and the renderer dropped
nothing.**

Measured on v2 as stored, before any render:

| scene | template | `supports_signalling` | cues |
|---|---|---|---:|
| s01 | cold_open | **False** | 0 |
| s02 | title_card | **False** | 0 |
| s03 | key_phrase | **False** | 0 |
| s04 | state_timeline | True | 3 |
| s05 | table_build | True | 3 |
| s06 | cold_open | **False** | 0 |
| s07 | table_build | True | 3 |
| s08 | cold_open | **False** | 0 |
| s09 | key_phrase | **False** | 0 |

Every signalling-capable scene carries the maximum §9.2 allows (3). Every scene
with zero is on a template that declares it cannot host a cue. Stored cue count
and rendered cue count agree exactly: 9 and 9.

**So this is not a cue-generation bug and not a renderer bug. It is a template
SELECTION consequence**, and the flag it depends on is mine, not the spec's —
that is ISSUE-5, where §9.2 says *"every scene contains 1–3 signalling events,
never zero"* without exceptions and `templates.py` exempts five templates.

The visual planner chose non-signalling templates for 6 of 9 scenes, so §9.2's
signalling rule is satisfied on 3 scenes and silently inapplicable on 6. The
linter reports nothing, because the exemption is encoded in the registry.

**Three ways out, and it is the same spec question as ISSUE-5:**

1. Every template must host signalling — flip the five flags, let the designer
   find a referent. §9.2 read literally.
2. Keep the exemption but make the PLANNER account for it: a video where most
   scenes cannot host a cue is a planning problem, so add a video-level finding
   on the share of non-signalling scenes.
3. Accept it and amend §9.2 to say which treatments are exempt.

**Not decided here.** Option 2 is the cheapest thing that makes the absence
visible rather than silent, and it needs a threshold v0.2 does not give.

---

## ISSUE-14 — 11 seconds of dead air at the end of the video's central scene · FIXED

s04 is the 90 s `present` scene carrying the whole explanation. Its narration is
79.09 s. The remaining **10.91 s is silence**.

**Measured placement (per-second RMS over the finished MP4, s04's 90 s window):**

```
###############################################################################...........
|<------------------ 79 s of speech ------------------>|<-- 11 s silence -->|

leading silence  : 0 s
trailing silence : 11 s
interior silence : 0 s
```

**All of it is trailing, contiguous, and at the end.** Not distributed pacing
beats — one unbroken block of nothing after the last word, before the cut to
s05.

**Why it is there.** s04 is the only `rigid` scene in the video. §15.3 says a
rigid scene keeps its authored duration and the audio is fitted into it, and
`resolver.resolve_scene` pads with silence to reach the target; `mux_scene`
appends that padding after the audio. The padding is 12.1% of the scene, inside
§15.3's ~15% budget, so no `FitProblem` was raised. **The resolver behaved
exactly as specified and the result is still bad.**

**Why the spec's budget does not catch it.** §15.3's 15% figure is about
absorbing *contraction* — a locale whose translation runs short — where the
padding is distributed by the timing model. Applying the same number to a
single trailing block treats "15% of the scene is silence somewhere" and "the
last 11 seconds are silent" as the same thing. They are not.

**Three options, none taken yet:**

1. **Distribute the padding** at span boundaries rather than appending it, so a
   rigid scene breathes between steps instead of dying at the end. Needs a rule
   for where beats go — §9.3's settling beat (≥1.5 s after each new concept) is
   the obvious candidate and is already in `DEFERRED_RULES`.
2. **Cap trailing silence** specifically, separately from the total pad budget.
   Needs a number v0.2 does not give.
3. **Make s04 elastic** and let the visual own a shorter duration. Cheapest, but
   s04 is `rigid` because the timeline animation has its own tempo, which is the
   legitimate reason for the flag.

Recommendation is 1, because it is the only one that improves the scene rather
than shortening it, and §9.3 already wants settling beats. It needs the timing
work that is currently deferred to a later week.

---

## ISSUE-15 — `concept_illustration` renders 0.43% ink: a caption alone in an empty frame · OPEN

**Found by the ink-coverage metric on its first run**, on scenes that pass the
blocking `scene_renders_nothing` gate. Both checks are correct; they measure
different things, which is why both exist.

Ink coverage across all nine v2 scenes after the blank-scene fix:

| scene | template | ink (min across scene) |
|---|---|---:|
| s01 | cold_open | 0.97% |
| s02 | title_card | 1.46% |
| s03 | key_phrase | 1.46% |
| s04 | state_timeline | 1.66% → 2.70% |
| s05 | table_build | 1.42% → 3.31% |
| **s06** | **concept_illustration** | **0.43%** ← under the floor |
| s07 | table_build | 1.22% → 2.51% |
| **s08** | **concept_illustration** | **0.43%** ← under the floor |
| s09 | key_phrase | 1.76% |

`concept_illustration` is `{subject, asset, caption}`. `subject` is a brief for
the artwork and is never typeset (week-4 D2), `asset` needs an asset pipeline
that does not exist, so the only thing drawn is `caption` — one short line in a
1920×1080 frame.

**The structural gate passes it and is right to**: a caption *is* a filled
on-screen slot, so the scene is not empty. **The ink metric fails it and is also
right**: 0.43% of the frame has anything on it. A gate that measures whether a
slot is filled cannot tell you whether the result is worth looking at.

**Same root cause as the cold_open blank (fixed): a template whose primary
content is an asset, used in a pipeline with no assets.** Three of eleven
templates are in that position — `cold_open`, `concept_illustration`,
`ui_walkthrough`.

**Not fixed, and the threshold was NOT tuned to make it pass.** 0.005 was set
before this measurement, as a blank-catcher; moving it to 0.004 to quiet two
scenes would be exactly the wrong response. Options are the same shape as
ISSUE-13's: either the planner should not choose asset-dependent templates while
there is no asset pipeline, or those templates need a text-bearing fallback the
way `cold_open` now has `headline`.

**Also worth stating plainly: the whole corpus is sparse.** The best scene in the
video reaches 3.31% ink. Nothing here is dense enough to look designed, and the
ink profile is the first number that says so.


---

## ISSUE-13 / ISSUE-14 — resolutions

### ISSUE-13, and the failure shape it names

**A capability flag disabling a pedagogical rule, with nothing surfacing the
override.** This is distinct from the form-vs-substance pattern behind ISSUE-8
and ISSUE-12, where a check measured the wrong thing. Here the check was correct
and simply never ran, because a boolean said it did not apply. Nobody decided
that two thirds of v2 would have no signalling; it fell out of a flag nobody had
to justify.

**The default is inverted.** `supports_signalling: bool` is replaced by
`signalling_exemption: str`. Empty means §9.2 applies — the default. A non-empty
string is the stated reason it cannot, `check_registry` rejects a reason shorter
than six words, and `linter.check_signalling_exemption` emits an INFO finding on
every scene an exemption suppresses a rule for, naming both the rule and the
reason.

### Which templates genuinely cannot signal: NONE

Audited all eleven. Every one of the five previously-exempt templates has at
least one addressable slot a cue could target:

| template | was exempt | addressable slots | genuinely cannot signal? |
|---|---|---|---|
| cold_open | yes | `headline`, `asset` | **no — unimplemented** |
| title_card | yes | `title`, `subtitle` | **no — unimplemented** |
| key_phrase | yes | `phrase`, `emphasis` | **no — unimplemented** |
| term_card | yes | `term`, `characteristic`, `icon` | **no — unimplemented** |
| concept_illustration | yes | `caption`, `asset` | **no — unimplemented** |

**All five were unimplemented, not incapable.** The flag was standing in for a
renderer that only consulted `isCued` on `rows`, `steps`, `tracks` and `nodes` —
so a cue on a text slot would have been produced and silently dropped. Flipping
the flag alone would have created exactly the "produced then dropped" bug that
the ISSUE-13 diagnosis ruled out. `Scene.tsx` now renders cues on scalar text
slots too.

**Measured on v2 after:** 9 cues across 3 scenes → **24 cues across 9 scenes,
zero scenes without one.**

### ISSUE-14

`AUTHORED_MAX_TRAILING_SILENCE_SHARE = 0.04`, **AUTHORED AND UNREVIEWED**, in
`resolver.py` with the reasoning beside it. Everything above that allowance is
redistributed evenly across span boundaries, and `_apply_padding` shifts span
and word timings so cues and captions move with the words — without that shift
the last cue in a 16-span scene would fire seven seconds early.

**Measured on s04:**

| | before | after |
|---|---:|---:|
| scene duration | 90.00 s | 90.00 s |
| narration | 79.09 s | 79.09 s |
| **trailing silence** | **10.91 s (12.1%)** | **3.60 s (4.0%)** |
| inter-span beats | none | 15 × 0.488 s |

The beats land on sentence boundaries because that is where the spans are. This
is a crude precursor to §9.3's settling beat (≥1.5 s held after each new
concept), not an implementation of it — that rule is still in `DEFERRED_RULES`
and would place beats by concept rather than spreading them evenly.

### A closure bug this work exposed

Rewriting the templates produced **different render bytes under an identical
closure hash**, and `LocalStore.put` raised `StoreError` — invariant 2 doing its
job. The closure carried `renderer_version()` (the Remotion *package* version)
and `template_version`, neither of which moves when `Scene.tsx` does.

Fixed at the closure, never at the blob: `render.render_source_version()` hashes
the renderer's own source into the key, and the eight templates whose rendering
semantics changed are bumped to 1.1.0. Without this, every scene rendered before
a renderer change would be served stale forever, and the only symptom would be a
video that quietly did not match its own templates.


---

## ISSUE-16 — a fix can be correct, in the closure, and still not run · FIXED

Two incidents in one session, same shape, and it is worth naming because the
second happened **after** the first was supposedly the lesson learned.

**Incident 1 (ISSUE-12).** The silent-video fix added `-map 0:v:0 -map 1:a:0`.
`stream_map` went into the closure, so it worked.

**Incident 2 (ISSUE-14).** The pad-plan fix computed the redistribution
correctly, put `pad_plan` in the closure, and the gap-insertion code **never
landed in the function** — a `str.replace()` patch whose anchor did not match,
which failed silently. The resolver reported `trailing 3.60s (4.0%)` and the
finished video still had 11.0 s of dead air. Every number in the report was
right about a plan nothing executed.

Then, after the code was applied properly, the re-render served the muxes
**from cache**: `pad_plan` was in the closure and unchanged between the two
runs, so the hash was identical and the old, wrong bytes came back.

**So the closure described what went IN and not what was DONE with it.** Fixed
with `mux_code_version()` — a hash of `mux_scene`'s own source, in the closure.
It moves when the behaviour moves, with nobody having to remember to bump a
constant. `render.render_source_version()` is the same fix one layer up.

**Measured on s04 after the fix actually ran:**

| | before | after |
|---|---:|---:|
| trailing silence | 11.00 s | **3.75 s** |
| interior beats | 0 | **6.25 s across 25 bins** |
| total silence | 11.00 s | 10.00 s |

### The rule this leaves behind

**Verify a fix against the artifact, not against the plan that describes it.**
Both incidents printed correct numbers while the video was unchanged. The only
thing that caught either was decoding the finished file and measuring it — which
is also how the column bug was found, by looking at a frame rather than reading
a report.

---

## ISSUE-17 — no vertical composition: every scene sits in the upper-left · OPEN (Phase 5)

**Observed on frames from the corrected re-render, all nine scenes.** Content
occupies the upper-left of the frame; the bottom 30–40% is dead in every scene.
The cold open's single line floats at roughly 45% height with nothing anchoring
it above or below.

There is no vertical rhythm and no safe-area-aware placement. `Scene.tsx` sets
`justifyContent: "center"` on a column flex and reserves the caption zone as
bottom padding, and that is the entire layout system — one rule, applied
identically to a four-word headline and a four-row table.

**This is an absence of design, not a bug.** Nothing is broken; nothing was
designed. A motion designer would specify a baseline grid, an optical centre
that differs from the geometric one, entry and settle positions per treatment,
and placement that reads the caption safe area as a composition boundary rather
than as padding.

**Not fixed, deliberately.** §22 puts brand and visual craft in **Phase 5**, and
inventing a layout system here would be authoring a large set of unreviewed
numbers in exactly the area where a specialist's judgement is the whole value.

**It is one of the two named gaps blocking Milestone A's success criterion** —
"an instructional designer reviews the objective graph and the rendered video
and says *I'd sign off on this*". See `docs/week6-plan.md`.

---

## ISSUE-18 — typography and colour do no work · OPEN (Phase 5)

**Observed on the same frames.** The visual system is:

- **one font family** (`Segoe UI, Helvetica, Arial, sans-serif`), plus a
  monospace stack used only by `terminal_replay`
- **one weight distinction**: 700 vs 400
- **two effective sizes** per scene, derived arithmetically from `minFontPx`
  (`×3`, `×2`, `×1`)
- **four hex literals** — `INK`, `PAPER`, `ACCENT`, `MUTED` — authored in
  `Scene.tsx` because no brand palette exists (week-4 **D6**)

So hierarchy is expressed by bold-vs-regular and nothing else. There is no
type scale, no colour semantics (an accent that means "attention" is the same
accent that means "this row is the answer"), no state vocabulary, and the
`a11y` contrast checker still reports `contrast_unresolved` because there is no
palette to check.

**Also an absence of design.** The four colours are placeholders that were
honest about being placeholders; they were never a system.

**Not fixed, deliberately** — same reasoning as ISSUE-17. §22 Phase 5 owns brand,
and `a11y.check_contrast` is already built and waiting for a palette to run
against, so the work attaches without a rewrite.

**The second of the two named gaps blocking Milestone A's success criterion.**
