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
