# Week 3 findings — curriculum planning and script generation

What the script writer actually produced against the MVCC objectives, which
gates fired, and what surprised me. Two runs are recorded: the original week 3
run, and the re-run after the two defects below were fixed.

Models: `claude-opus-5` for extraction (the `frontier` pin), `claude-sonnet-5`
for curriculum planning and script writing (the `mid` pin). 14 Aug 2026.

---

## Run 2 — after the defect fixes (objective_extractor v3, script_writer v2)

`explainer curriculum plan mvcc-write-skew` → one video, one model call, $0.0160.

```
1. v1   [explainer] Why concurrent reads can miss each other's writes
       objectives: o1, o2  budget: 240s
```

`explainer script generate mvcc-write-skew v1` → 9 scenes, one model call,
$0.2841.

| scene | slot | target | words | wpm needed | spans | new terms |
|---|---|---:|---:|---:|---:|---|
| s01 | hook | 15s | 46 | 184 | 5 | — |
| s02 | objective | 10s | **11** | **66** | 1 | — |
| s03 | recall | 20s | 52 | 156 | 4 | repeatable read, snapshot |
| s04 | present | 90s | 210 | 140 | 18 | xmin, xmax |
| s05 | guide | 36s | 83 | 138 | 9 | — |
| s06 | elicit | 17s | 40 | 141 | 3 | serialization error |
| s07 | feedback | 23s | 52 | 136 | 5 | write skew |
| s08 | assess | 18s | 39 | 130 | 3 | — |
| s09 | retain | 12s | 34 | 170 | 1 | — |

567 words over 241s — 141 wpm, inside §9.3's 135–160 band. Every
`duration_value` null.

**Two findings, both readability warnings, both on different scenes than before:**

- s03, FK 11.82 against the technical limit of 11.0
- s09, FK 13.98

**Defect 1 is fixed and measurable.** The objective scene went from 30 words at
180 wpm with three findings to **11 words at 66 wpm with none**. The stored short
form and the spoken narration are byte-identical:

```
stored : You'll work out exactly what each transaction can see, and why.
spoken : You'll work out exactly what each transaction can see, and why.
VERBATIM MATCH: True
scene_title  : You'll work out exactly what each transaction can see, and why.
```

**Defect 2 is fixed.** The retain slot now reads:

> Pause and put it in your own words: what makes a snapshot fix what a
> transaction sees, and why can two rule-respecting transactions still break a
> rule that spans rows they never both touched?

No forward reference, and it is learner-generated, which §9.5 asks for.

**The extraction-time validator earned its keep on its first run.** Extraction
took two model calls, not one. Attempt 1 was rejected by code:

> objective 'o3': learner_facing_statement contains a colon or semicolon, so it
> is carrying a condition or criterion. Those exist for alignment checking and
> are not spoken. Keep one clause.

The repair loop fixed it. That failure would previously have surfaced three
stages later as a gate warning on a scene, where the only available fix is to
rewrite narration around a bad stored string.

All five short forms, as stored:

```
o3: [12w] You already know what a transaction promises about atomicity, isolation and durability.
o4: [11w] You can already read and write simple SELECT and UPDATE statements.
o5: [10w] You already know a transaction gets its own numeric id.
o1: [11w] You'll work out exactly what each transaction can see, and why.
o2: [14w] You'll spot the case where both transactions commit happily and still break your rule.
```

**Two infrastructure failures surfaced during the re-run, both correctly
escalated rather than silently swallowed.** The v2 script prompt plus an
adaptive-thinking pass overran `MAX_TOKENS = 16000`; raising it to 32000 then hit
the SDK's non-streaming guard (`Streaming is required for operations that may
take longer than 10 minutes`). The script writer now streams and takes the final
message. Both appeared as `escalated` rows with the offending input and a next
step, which is invariant 7 doing exactly its job — the first one named the
model, the prompt version and the video ref, which was enough to diagnose it
without re-running anything.

### `new_terms` agreement rate

The code-computed `new_terms` is kept regardless of agreement — deterministic
beats agentic — but the rate is worth tracking, because a consistently perfect
one across topics would tell us something and one run tells us nothing.

| run | prompt | scenes | agreement |
|---|---|---:|---:|
| week 3 run 1 | script_writer v1 | 9 | 9/9 (100%) |
| week 3 run 2 | script_writer v2 | 9 | 9/9 (100%) |

Two runs, same topic, same video shape, 18 scenes total, zero disagreements. That
is not yet evidence: both runs are a single 9-scene video on a subject with few
competing terms, which is the easiest case for a model to track. The number to
watch is the first multi-video course, where a term introduced in video 1 has to
stay un-introduced in video 3 — nothing in the current design carries the term
set across videos, so I expect the first disagreement there rather than here.

---

## Run 1 — the original week 3 run (objective_extractor v2, script_writer v1)

Kept because the before/after is the point.

`explainer curriculum plan` → one video, $0.0155:

```
1. v1   [explainer] Why concurrent transactions can break your invariants
       objectives: o1, o2  budget: 240s
```

That is step 1's acceptance criterion met on real data: `max_videos=1`, two
taught objectives, exactly one video carrying both. The planner's rationale:

> o2 is the direct payoff of the snapshot/xmin-xmax mechanics taught in o1 —
> predicting write skew requires exactly the read-prediction skill just built,
> so splitting them would force re-explaining the same snapshot timeline twice.

`explainer script generate` → 9 scenes, $0.1859. 578 words over 241s = 144 wpm.

Four findings, all warnings, three of them on one scene:

**s02, speaking rate.** The worst measurement in the run:

> By the end of this scene, you'll predict what each statement in two concurrent
> Repeatable Read transactions reads, naming the row's xmin and xmax and when
> its snapshot was taken.

30 words in a 10-second slot — 180 wpm, and §9.1 caps that slot absolutely, so
there was nowhere for the surplus to go. `26 words fit`. 15% over, under the 20%
blocking threshold, so it warned.

**s02, readability.** FK 13.02 against 11.0. Same sentence, three subordinate
clauses.

**s02, passive voice.** 100% — but with one sentence in the scene, any single
passive reads as 100%. It flagged "was taken", a real passive in a subordinate
clause where the active alternative is worse prose.

**s03, readability.** FK 12.09. A 44-word sentence with a colon and two "Recall
that" openers.

---

## What surprised me

**The objective slot was the hardest slot in the template, and I did not expect
that.** §9.1 gives it ≤10s and says the objective is "stated verbatim; reused as
the scene title". But v2-extracted objectives carry conditions and criteria
because §5.3's alignment check needs them, and the full statement runs to 40
words. Three of run 1's four findings were on that one scene. The extractor was
rewarded for precise criterion-bearing statements; the objective slot punished
exactly that. Neither prompt knew about the other's constraint. The fix was to
stop treating "verbatim" as "read the schema record aloud" and store a second,
speakable form — v3 emits it, migration 0004 holds it, and it is validated at
extraction rather than at script time.

**The model chose `rigid` timing for precisely the two scenes where it matters,**
and I expected it to default everything to elastic. In run 1, s04 (walking a
transaction timeline) and s05 (the on-call schedule) were rigid and the other
seven elastic. That is the right answer from a one-line instruction.

**Span segmentation split one sentence somewhere I would not have.** Run 1, s05:

```
sp_9d69309186  PostgreSQL only aborts a transaction when two transactions try to update the exact same row
sp_b90cc0d66c  that's its first-updater-wins rule.
```

`spans.py` split on an em dash mid-sentence. Harmless for cue anchoring — better,
arguably, since a cue can now point at the rule name — but if spans are ever
shown to a human as editable units, that fragment will look like a bug.

**The script reached the gold file's note 4 unprompted, twice.** Both runs state
the contrast the gold calls out — that first-updater-wins fires only on same-row
updates — without the prompt asking for it.

**The retain slot promised a video that did not exist.** Run 1 closed with "Next,
you'll see how explicit locking closes that gap." There is no next video; SSI and
locking are in `out_of_scope`. That was my defect, not the model's: `video_input`
passed the video's objectives and nothing about its position in the course. Fixed
by passing ordinal, total, the next video's objectives when one exists, and
`out_of_scope` — plus a blocking gate on the final video.

---

## Known gaps going into week 4

- **Passive-voice ratio on single-sentence scenes is not a useful measurement.**
  Run 1's s02 read as 100% off one sentence. A minimum sentence count before the
  gate reports would fix it; I have not added one because the threshold would be
  a guess and §9.2 states none.
- **The forward-reference gate is a filter, not a proof.** It catches fixed
  phrasings ("next video", "coming up", "we'll see how"). It misses an implied
  promise with no marker — "explicit locking closes that gap" would sail through.
  Documented in the docstring rather than overclaimed.
- **`new_terms` does not carry across videos.** The running set is per-video, so
  a term introduced in video 1 counts as new again in video 2. Harmless on a
  one-video course; wrong the moment there are two. §9.2's pre-training rule
  wants a per-course term registry, which is a schema change.
- **Gold o2's three anomaly names are still missing**, now across v1, v2 and v3
  of the extractor. That is a content gap, not a granularity artefact, and it is
  the one place the gold's ANSI-vs-PostgreSQL trap remains untested by output.
- **Redundancy (§9.4) is absent by design** — it needs the storyboard, week 4.
