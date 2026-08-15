# Week 6 — plan

**Not started.** This document states what Milestone A's exit criteria require,
what is met, what is not, and the honest state of the video against §22's bar.
It deliberately does not propose a build.

---

## 1. What §22 actually asks for

> **Milestone A — Proof of Good (4–6 weeks, solo + Claude).** Build only: intake
> → objective graph → deterministic linter → Gagné storyboard → **one**
> motion-graphics video (Tier 1M), rendered once. English only. MP4 + captions.
> **No cache, correct schema.** Stock hook via Storyblocks trial;
> illustration/B-roll via Freepik AI (§14.3).
>
> **Success:** an instructional designer reviews the objective graph **and** the
> rendered video and says *"I'd sign off on this."* If they won't, fix the
> pedagogy engine before spending a day on the render cache.

Two things about that wording are easy to skim past and both matter:

1. **The criterion is a person, not a metric.** Nothing in this repo can
   self-certify it. Every number below is evidence for that conversation, not a
   substitute for it.
2. **It covers the objective graph AND the video.** A graph an ID accepts with a
   video they don't is a fail, and so is the reverse.

§0.5 adds the hard rule that binds A to B:

> even in Milestone A, where there is no cache, the scene-graph schema must be
> built exactly as **R1–R8** demand … If Claude improvises the schema in
> Milestone A to move fast, Milestone B is poisoned before it starts.

---

## 2. What is met

| Requirement | State | Evidence |
|---|---|---|
| Intake → objective graph | **met** | `brief.py`, `objective_extractor` v3, 7 objectives, gold-aligned |
| Deterministic linter | **met** | `linter.py` + `a11y.py`; §9.6's split kept, model-side rules named as absent rather than faked |
| Gagné storyboard | **met** | `gagne.py` nine slots, `visual_planner` v2, `signal_designer` v1 |
| One motion-graphics video, rendered | **met** | 218.33 s, 1920×1080 h264 30 fps, 9 scenes |
| English only | **met** | locale column exists, unused (D7) |
| MP4 + captions | **met** | `.mp4`, `.vtt` (40 cues), `.srt`, word sidecar |
| **Correct schema (R1–R8)** | **met** | durations stored not positions; `RationalTime`; cues span-anchored; narration segmented at authoring; duration derived from TTS; provenance on every object; content-addressed store; renderer-agnostic spec with translation confined to `Scene.tsx` |

**Ahead of the brief:** §22 says "no cache" and the content-addressed cache is
built anyway. That is not a problem — §0.5's warning is about improvising the
*schema*, and the schema is R1–R8 correct. It does mean the Milestone B kill
criterion ("is the chunked re-render loop clean and deterministic?") has partial
evidence already: byte-identical renders verified on three cases including an
animated build with cues.

---

## 3. What is not met

### 3.1 The asset pipeline is absent — and §22 names it explicitly

> *Stock hook via Storyblocks trial; illustration/B-roll via Freepik AI (§14.3).*

Neither exists. No asset is fetched, generated, stored or rendered. Three of
eleven templates depend on one — `cold_open`, `concept_illustration`,
`ui_walkthrough` — and this is the direct cause of two logged defects:

- **ISSUE-15**: `concept_illustration` renders **0.43% ink** — a caption alone in
  an empty 1080p frame, on two of nine scenes.
- The `cold_open` blank (fixed by requiring a `headline`) was the same cause:
  the template's actual content is a shot that does not exist.

This is the single largest gap between what §22 asked for and what was built.

**Correction on the record.** The sparse scenes were initially attributed
entirely to absent visual design and filed against Phase 5. That was wrong: it
made a stated Milestone A deliverable look like deferred polish. §22 names the
asset pipeline explicitly, so ISSUE-15 belongs to Milestone A's scope, not
Phase 5's. ISSUE-17 and ISSUE-18 are genuinely Phase 5 and stay there.

### 3.2 The success criterion has not been tested

No instructional designer has reviewed anything. **Milestone A is therefore
unproven, not passed.** The two gaps below are the ones I would expect that
review to fail on, which is why they are named rather than left for the reviewer
to discover.

### 3.3 The two named visual gaps blocking sign-off

**ISSUE-17 — no vertical composition.** All nine scenes occupy the upper-left;
the bottom 30–40% is dead in every one. The layout system in its entirety is
`justifyContent: center` plus caption-zone padding, applied identically to a
four-word headline and a four-row table.

**ISSUE-18 — typography and colour do no work.** One font family, one weight
distinction (700/400), two derived sizes, four hex literals authored in
`Scene.tsx` because no palette exists (D6). Hierarchy is bold-vs-regular and
nothing else; the accent meaning "attention" is the accent meaning "this is the
answer".

Both are **absence of design, not bugs**. §22 puts brand and visual craft in
Phase 5. Both are logged and neither is fixed, because inventing a layout and
colour system here would author a large set of unreviewed numbers in precisely
the area where a specialist's judgement is the whole value.

**Week 6's review must be scoped against a known-incomplete visual layer.** The
question to put to an ID is not "is this finished" — it is *"is the pedagogy
right, and would this be signable once a designer has done the visual layer?"*
Presenting it as finished would get a "no" that tells us nothing about the
pedagogy engine, which is the thing §22 says to fix first.

---

## 4. Honest state of the video

| | |
|---|---|
| Runtime | 218.33 s measured, 218.33 s resolved, **zero drift** |
| Budget | 240 s → 21.67 s under |
| Format | 1920×1080, h264 High, yuv420p, 30 fps |
| Audio | AAC mono 48 kHz, mean −17.5 dB, peak −0.0 dB |
| Scenes / spans / cues | 9 / 40 / 24, no scene without a cue |
| Templates used | 5 of 11; longest identical run 1 |
| **Ink coverage, peak** | **3.15%** |
| Silence in s04 | 3.75 s trailing + 6.25 s distributed (was 11.00 s trailing) |

**What is genuinely good.** The pedagogical spine works end to end. The recall
slot links to v1's objectives by ref and v2 re-declares none of v1's terms —
Wedge A demonstrated, not asserted. Timing is exact: nine scenes concatenate
with no accumulated drift. Every scene draws something, every scene carries
signalling, the table is a real table and the timeline is a real timeline.

**What is not good, stated plainly.**

- **Peak ink coverage is 3.15%.** The densest frame in the video has content on
  three percent of it. Nothing here looks designed, and that number is the
  honest summary of ISSUE-17 and ISSUE-18 together.
- **Two scenes are near-empty** (0.43%) because their illustration does not
  exist.
- **Peak audio at −0.0 dB** is at the clipping ceiling. §7's −14 LUFS / −1 dBTP
  targets are Phase 7 and no loudness normalisation runs.
- **Prosody is flat by choice.** VITS noise is zeroed for determinism (§11.3).
  That is the right trade for the cache and it is audible.
- **ISSUE-8 is unresolved.** The pivotal factual error did not recur in the
  current script, but **nothing detected it** — a stochastic stage landed
  differently. §7.2's Fact Checker does not exist. An ID reviewing the narration
  is currently the only defence against a confidently-wrong claim.

---

## 5. What week 6 must decide before it builds anything

These are decisions, not tasks, and they are yours:

1. **Does the ID review happen now, against a known-incomplete visual layer, or
   after Phase 5 work?** §22's sequencing argues for now — *"if they won't, fix
   the pedagogy engine before spending a day on the render cache"* puts pedagogy
   ahead of polish, and the cache is already built. Reviewing now gets the
   pedagogy verdict early and cheaply.
2. **Does the asset pipeline get built to close §22's stated scope**, or is
   Milestone A declared complete-without-assets and the gap carried forward? It
   is named in the brief, so declaring it out of scope is a change to the brief.
3. **Is ISSUE-8 tolerable for a review?** A reviewer shown a script with an
   undetected factual error, in a system with no fact checker, may reasonably
   refuse to sign off on grounds that have nothing to do with the pedagogy
   engine.

## 6. Open, carried into week 6

| issue | state |
|---|---|
| ISSUE-3 | MAX_TOKENS, standing: a fourth overrun means examining `effort`, not the ceiling |
| ISSUE-4 | no variety budget in v0.2 — needs to return to the PRD |
| ISSUE-6 | §9.3's 3-element cap vs table templates — spec question |
| ISSUE-8 | **BLOCKING** — factual error class, needs §7.2's Fact Checker |
| ISSUE-10 | retain slot has 0.24 s of headroom for §9.1's two jobs |
| ISSUE-15 | `concept_illustration` at 0.43% ink — asset pipeline |
| ISSUE-17 | vertical composition — Phase 5 |
| ISSUE-18 | typography and colour — Phase 5 |

Fixed and closed this week: ISSUE-1, 7, 11, 12, 13, 14, 16.
