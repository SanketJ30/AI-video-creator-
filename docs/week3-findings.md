# Week 3 findings — curriculum planning and script generation

What the script writer actually produced against the MVCC objectives, which
gates fired, and what surprised me. Run on 14 Aug 2026 against `claude-opus-5`
(frontier, curriculum planner and script writer both on `claude-sonnet-5`, the
`mid` pin).

## What was generated

`explainer curriculum plan mvcc-write-skew` → one video, one model call, $0.0155.

```
1. v1   [explainer] Why concurrent transactions can break your invariants
       objectives: o1, o2  budget: 240s
```

That is the acceptance criterion for step 1 met on real data: `max_videos=1`,
two taught objectives, exactly one video carrying both. The planner's own
rationale for merging them:

> o2 is the direct payoff of the snapshot/xmin-xmax mechanics taught in o1 —
> predicting write skew requires exactly the read-prediction skill just built,
> so splitting them would force re-explaining the same snapshot timeline twice.

`explainer script generate mvcc-write-skew v1` → 9 scenes, one model call,
$0.1859. No repair round trip; the form came back filled on the first attempt.

| scene | slot | target | words | wpm needed | spans | new terms | timing |
|---|---|---:|---:|---:|---:|---|---|
| s01 | hook | 15s | 36 | 144 | 6 | — | elastic |
| s02 | objective | 10s | 30 | **180** | 1 | — | elastic |
| s03 | recall | 20s | 51 | 153 | 3 | snapshot | elastic |
| s04 | present | 90s | 220 | 147 | 16 | xmin, xmax | **rigid** |
| s05 | guide | 36s | 89 | 148 | 9 | first-updater-wins | **rigid** |
| s06 | elicit | 17s | 27 | 95 | 3 | — | elastic |
| s07 | feedback | 23s | 54 | 141 | 6 | write skew | elastic |
| s08 | assess | 18s | 46 | 153 | 3 | — | elastic |
| s09 | retain | 12s | 25 | 125 | 2 | — | elastic |

578 words over a 241s budget — a 144 wpm average, inside §9.3's 135–160 band for
dense explanation. 49 spans. Every `duration_value` is null.

## Which gates fired

Four findings, all warnings, no blockers. Three of the four land on one scene.

**s02, speaking rate.** The single worst measurement in the run:

> By the end of this scene, you'll predict what each statement in two concurrent
> Repeatable Read transactions reads, naming the row's xmin and xmax and when
> its snapshot was taken.

30 words in a 10-second slot. That needs 180 wpm, and §9.1 caps the objective
slot at 10s absolutely, so there is nowhere for the surplus to go. `26 words
fit`. 15% over — under the 20% blocking threshold, so it warned.

**s02, readability.** FK grade 13.02 against the technical limit of 11.0. Same
sentence. It is one 30-word sentence with three subordinate clauses.

**s02, passive voice.** 100% of sentences — but there is only one sentence, and
the gate flagged it on "was taken". This is the documented false-positive class:
"when its snapshot **was taken**" is a genuine passive, but in a subordinate
clause where the alternative ("when PostgreSQL took its snapshot") is worse
prose. A one-sentence scene also makes the ratio meaningless: any single passive
sentence reads as 100%.

**s03, readability.** FK grade 12.09, again over 11.0. The offending sentence is
44 words with a colon and two "Recall that" openers.

## What surprised me

**The objective slot is the hardest slot in the template, and I did not expect
that.** §9.1 gives it ≤10 seconds and says the objective is "stated verbatim;
reused as the scene title". But the extracted objective statements are long —
o1's is 40 words with its condition and criterion — and "verbatim" plus "10
seconds" is only satisfiable if the objective statement is itself under about 26
words. Three of the four findings are on this one slot, and they are all the same
underlying problem. The v2 objective extractor was rewarded for precise,
criterion-bearing objective statements; the objective *slot* punishes exactly
that. Nothing in either prompt knows about the other's constraint.

**The model chose `rigid` timing sensitivity for precisely the two scenes where
it matters,** and I had expected it to default everything to elastic. s04 walks a
timeline ("Transaction one starts, runs its first select, and takes its snapshot
right there") and s05 walks the on-call schedule; both need narration landing
against a visual step. The other seven are elastic. That is the right answer and
it came unprompted from a one-line instruction.

**`new_terms` computed in code disagreed with the model zero times on this run.**
I built the running-set computation expecting to catch the model re-declaring
"write skew" in three scenes; `model_claimed_new_terms` and the computed
`new_terms` are identical for all nine scenes. The safeguard cost nothing and
proved unnecessary *here* — but it is a single 9-scene video, which is the easiest
possible case for a model to track. I would not remove it.

**Span segmentation split one sentence in a place I would not have.** s05 has:

```
sp_9d69309186  PostgreSQL only aborts a transaction when two transactions try to update the exact same row
sp_b90cc0d66c  that's its first-updater-wins rule.
```

`spans.py` split on an em dash mid-sentence, leaving a fragment that reads oddly
alone. For cue anchoring this is harmless — arguably better, since a cue can now
point at the rule name specifically — but if spans are ever surfaced to a human
as editable units, that fragment will look like a bug.

**The script is pedagogically better than I expected on the one thing the gold
graph cared about.** s07 states the mechanism the gold file's extraction note 4
calls out — "First-updater-wins only fires when two transactions update the same
row, and here they update different rows" — and s09 closes with a
learner-generated summary prompt rather than an engine-narrated one, which is
what §9.5 asks for and which nothing in the slot treatment explicitly demanded
beyond "prompt them to summarise rather than summarising for them".

**The retain slot promises a video that does not exist.** s09 ends "Next, you'll
see how explicit locking closes that gap." There is no next video — the v2
objective extractor put SSI and locking in `out_of_scope`, and the curriculum
plan has one video. The script writer was given the objectives but not the
course's shape, so it wrote a forward reference into a course that ends here.
That is a real defect and it is mine, not the model's: `video_input` passes the
video's own objectives and the assumed knowledge, and nothing about what comes
after.

## Known gaps going into week 4

- The objective-slot overrun above is structural, not a one-off. Either the
  objective statement gets an abridged form for the slot, or §9.1's 10s cap needs
  a documented exception. Not fixed in week 3 — it needs a decision.
- The forward reference in `retain` needs the video's position in the course
  passed into the prompt.
- Passive-voice ratio on single-sentence scenes is not a useful measurement. A
  minimum sentence count before the gate reports would fix it; I have not added
  one because the threshold is a guess and §9.2 states none.
- Redundancy (§9.4) is absent by design — it needs the storyboard.
