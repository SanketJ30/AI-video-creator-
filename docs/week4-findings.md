# Week 4 findings — storyboard and the pedagogy linter

Stage 2d (§6): template choice, signal placement, and the deterministic half of
the §9.6 linter. Plus the §16.2 accessibility gates.

**What everything below was measured against:** course `mvcc-write-skew`, brief
**v5** (`max_videos: 2`), video **v2** (`procedure_demo`, 9 scenes, 239 s),
script from week 3's Stage 2c run, storyboard from this week's `visual_planner
v1` + `signal_designer v1`. The objective graph is **v3-run5**. One video, one
topic — every rate in this document is n=1 unless it says otherwise.

---

## 1. Numbers I raised on rather than implemented

The standing rule is: where a rule needs a number v0.2 does not give, raise
rather than guess. Five did.

| § | rule as stated | why it is not implemented | what the code does |
|---|---|---|---|
| §9.4 | `audience.nonNativeRatio > threshold` allows more on-screen text | v0.2 names no threshold and no way to measure the ratio | `check_nonnative_text_allowance` raises `UnspecifiedThreshold` |
| §9.4 | `content.termDensity is high` allows more on-screen text | "high" has no number and no definition of density | `check_term_density_allowance` raises `UnspecifiedThreshold` |
| §9.4 | `0.3 < semantic_similarity < 0.85` between on-screen phrase and narration | numbers ARE given; needs embeddings, and §9.6 puts relevance scoring on the model side | listed in `MODEL_BASED_RULES`, not approximated |
| §9.2 | Coherence: `relevanceScore` below 0.85 blocks | number IS given; §9.6 assigns it to the model | listed in `MODEL_BASED_RULES` |
| §9.3 | "≤6 words per line for emphasis" | number IS given; a slot string does not know where it wraps, and no template declares which slots render as one line | `MAX_WORDS_PER_LINE` transcribed, listed in `DEFERRED_RULES["words_per_line"]` |

The last one is worth dwelling on. `MAX_WORDS_PER_LINE` was defined, correctly
transcribed, and **read by nothing** — a rule that looks implemented and does
nothing. Nobody would have noticed from the constant block. There is now a test
(`test_every_spec_constant_is_either_enforced_or_named_as_not_enforced`) that
fails if any spec constant is defined and unused without a `DEFERRED_RULES`
entry saying why.

### The one authored number

| constant | value | status |
|---|---|---|
| `AUTHORED_TEMPLATE_SHARE_MAX` | 0.40 | **AUTHORED AND UNREVIEWED** |

v0.2 has no variety budget at all. PRD_v4 §13.5 had one and was superseded
(ISSUE-4). Rather than reconstruct a dead PRD's rule, the linter reports the
**distribution** and warns when one template exceeds the share. It is warning-
only, never blocking, and the CLI prints "AUTHORED AND UNREVIEWED" on the
finding itself — where it is used, not only where it is defined.

On v2 it fires: `table_build` carries 4 of 9 scenes (44%).

---

## 2. Were the animate-vs-static decisions defensible?

**Yes — and the gate is doing real work rather than rubber-stamping.**

| scene | slot | template | motion | referent changes? |
|---|---|---|---|---|
| s01 | hook | cold_open | static_reveal | false |
| s02 | objective | title_card | static_reveal | false |
| s03 | recall | table_build | static_reveal | false |
| **s04** | **present** | **state_timeline** | **animate** | **true** |
| s05 | guide | table_build | static_reveal | false |
| s06 | elicit | table_build | static_reveal | false |
| s07 | feedback | table_build | static_reveal | false |
| s08 | assess | concept_illustration | static_reveal | false |
| s09 | retain | key_phrase | static_reveal | false |

One scene of nine animates, and it is the right one. s04's `what_changes`:

> *the on-call table's state changes from two doctors on call to zero on call as
> both transactions run their reads, writes, and commits across time*

That is a referent that genuinely changes over time — two transactions
interleaving — which is exactly the condition §8 sets. `state_timeline` is the
one template in the registry built for it.

The interesting cases are the four `table_build` scenes marked `static_reveal`.
A table that builds row by row *is* moving, so calling it static looks wrong at
first glance. It is not: the gate asks whether the **referent** changes over
time, not whether pixels move. A comparison of four isolation-level behaviours
is a fixed set of facts revealed progressively — the anomalies do not change
while you watch. Marking those `animate` would have been the failure mode, and
the model did not.

**Caveat, stated plainly:** this is 9 scenes on one topic, and the check_motion
gate is a *validity* check — it rejects `animate` without a stated
`what_changes`, but nothing rejects an unjustified `static_reveal`. A model that
marked everything static would pass the gate silently. That asymmetry is
deliberate (the expensive, wrong-looking choice is the one worth gating) but it
means "9/9 defensible" is weaker evidence than it reads.

---

## 2b. ISSUE-8 — the pivotal claim of s04 is stated backwards · BLOCKING

Found by a human reading the script; **no gate in the pipeline can reach it.**

`sp_b735cd9656`: *"Neither transaction writes the row the other one reads."*
False, and the exact inversion — those two rw-antidependencies **are** write
skew. The true statement is that neither writes the row the other *writes*.
It contradicts `sp_1c3727ba32` one line later and `sp_93758ba6db` in s07, and
the same confusion in s05 (`sp_fb5e4ab259` / `sp_d3de4b56b2`) is why
`SELECT FOR UPDATE` gets wrongly dismissed.

The linter reports s04 clean on every rule it has, because every §9.6
deterministic rule is about *form*. §7.2's **Fact Checker** is the agent for
this and it does not exist. `MODEL_BASED_RULES["factual_confidence"]` reserves
the slot so the absence is visible in every report.

**Withdrawal on record:** I previously offered the extractor getting Repeatable
Read right as evidence the Fact Checker might not be load-bearing. Wrong. The
extractor was right about a fact it was asked to *classify*; the script writer
was wrong about a fact it was asked to *explain*, in the scene carrying the
video's thesis, in prose fluent enough to read as authoritative. It is
load-bearing. Full write-up: ISSUE-8.

Not fixed by hand: the pipeline produced it and the pipeline must catch it.

---

## 3. s05 — an open reviewable call, not a defect

s05 (`guide`, 52 s) uses `table_build` to lay out four candidate fixes against
"fixes it?" and "cost". The reviewable question is whether the *guide* slot —
Gagné's "provide learning guidance" — is well served by a comparison table at
all, or whether it wants a worked path through one option.

Left as-is. It is a legitimate treatment, the alternative is not obviously
better, and changing it on my own judgement would be exactly the "quietly
changes something a human approved" failure. **Recorded as an open call for a
human, not a defect to fix.**

---

## 4. `new_terms` agreement rate — and why 100% is the bad news

Computed from stored `pedagogy_meta.model_claimed_new_terms` vs the
code-computed `new_terms`:

| video | scenes | agreement |
|---|---:|---:|
| v1 | 9 | 9/9 (100%) |
| v2 | 9 | 9/9 (100%) |

Four runs now, 36 scenes, zero disagreements. **This is not the reassurance it
looks like.** v2 declares `snapshot` a new term; v1 already taught it. The code
and the model agree because `first_use_only` seeds its running set empty at the
start of every video, so both make the same mistake. The agreement rate is
measuring consistency, not correctness.

Logged as **ISSUE-7 (BLOCKING)**. The fix is a set union over rows already in
the database — deterministic, no model call, no threshold to invent — and it
also supplies the second half of the recall-slot gate ISSUE-1 needs. Same root
cause as ISSUE-1: no cross-video memory, which is Wedge A.

---

## 5. What the linter actually found on v2

18 warnings, 0 blocking, 239 s.

| rule | count | § |
|---|---:|---|
| onscreen_text_share | 5 | §9.4 |
| onscreen_object_count | 5 | §9.3 |
| onscreen_text_elements | 5 | §9.3 |
| static_title_too_long | 1 | §9.2 |
| onscreen_text_density | 1 | §9.3 |
| template_variety | 1 | authored |

The §9.3/§9.4 clustering is real and is one storyboard behaviour, not three: the
visual planner puts the *content* on screen rather than an abridgement of it.
s04's `steps` list is seven full sentences — 56 on-screen words against §9.3's
30. §9.4's evidence says that is worse than showing nothing.

**Two of the original 20 were false**, and finding that out is the most useful
thing this step produced — see §6.

---

## 6. Three defects the review surface found in my own week-4 code

None of these were found by tests. All three were found by running the thing and
looking at the output, which is the week-2 lesson holding.

1. **`ScenePlan.rationale` was parsed and then dropped by `visual_spec()`.** The
   model produces it, the parser keeps it, the serializer silently omitted it.
   §10 makes the storyboard the surface a human edits, and a template choice
   with no stated reason is one a reviewer can only accept or reject, never
   correct. Found by writing `storyboard show --rationale` and getting nothing.

2. **`script_writer.load` did not select `visual_spec`.** Nothing downstream
   could read the storyboard the storyboard stage had just written.

3. **`cold_open.premise` and `concept_illustration.subject` are briefs for the
   imagery, not typeset text.** §9.4's priority rule was firing on s01 and s08,
   two scenes that display no text at all. `Param.on_screen` now states this per
   parameter. Same class of bug as `focus` (a node id counted as an on-screen
   word), found the same way — by measuring a fixture before asserting on it.

The measurement: **20 warnings before the fix, 18 after. Both removed findings
were false.** A 10% false-positive rate on the first real video is the number to
watch as more templates arrive.

---

## 7. §9.3 vs the template registry — ISSUE-6

§9.3 caps simultaneous text elements at 3. Measured across all 11 registered
templates with a minimal realistic fill, exactly two exceed it — `table_build`
(4) and `terminal_replay` (5) — and both do so *by construction*: a 2×2 table is
the smallest useful table and is already 4 elements.

Counting filled *slots* instead (a table = one element) was implemented,
measured, and reverted: it drops the maximum across all 11 templates to 2, which
makes the rule unfireable and therefore worthless. So the count is right and the
conflict is real. It is a spec question, logged as ISSUE-6 with three options.

Current behaviour: warning, never blocking. On v2 it compounds with
`template_variety` on the same four scenes.

---

## 8. §16.2 accessibility — what runs and what cannot

| gate | status |
|---|---|
| 1.2.2 caption presence | **runs** — a scene with no narration can never be captioned |
| 1.2.1 silent screen capture | **runs** — a SCREEN_DEMO scene with no narration |
| §11.6 font ≥24px | **runs** — registry and per-scene override |
| §16.2 caption exclusion zone | **runs** — template and per-scene override |
| 1.4.3 / 1.4.11 contrast | **maths implemented and tested; cannot run** |
| 2.3.1 flash | **criterion implemented and tested; cannot run** |
| 1.2.5 audio description | model-based (§9.2 coherence), not here |

**Contrast has no input.** `brand_version` is a bare string; there is no palette
anywhere in the system and v0.2 names no colours. `check_contrast` returns an
`unresolved` finding rather than passing, once per video. No colour was
invented. Phase 5 owns brand.

**Flash has no input.** It needs rendered frames — week 5 at the earliest.

The maths is written now anyway, and tested against WCAG's *published* values
rather than against itself: 21:1 black on white, `#767676` passing AA at 4.54
and `#777777` failing at 4.48, `#808080` at luminance 0.216. That last one
matters — a linear implementation returns ~0.5 and silently passes failing
contrast. A self-consistent fixture would not have caught it.

### One derived fact worth knowing

§11.6 requires ≥24 px at 1080p. WCAG's large-text boundary is 18 pt. CSS defines
1 pt = 4/3 px, so **24 px is exactly 18 pt**: at the registry's own minimum font
size every text layer is already WCAG "large text" and the bar is 3:1, not
4.5:1. Raising `MIN_FONT_PX` is safe; *lowering* it silently moves every layer to
the stricter threshold. Pinned by a test so that cannot happen quietly.

---

## 8b. Two patterns recorded before week 5

**ISSUE-9 — the speaking-rate overruns are systematic.** Four of nine scenes run
past their budget (s03, s05, s06, s07) and every one of them is `elastic`, so
under §11.2 they stretch rather than truncate. Targets sum to 239 s against a
240 s budget; stretched to fit their words the scenes total **248.4 s, +8.4 s
over**. The one scene with real slack (s04, −12.9%) is `rigid` and will not give
it back. Stage 2c prompt issue, not a week 5 timing issue. **Prediction on
record: v2 finishes long by roughly 8 s before any TTS-rate variance.**

**ISSUE-10 — the retain slot gets 2.5% of the video.** s09 is budgeted 6 s = 15
words. §9.1 asks that slot for *"summary + spaced-review scheduling hook"* — two
jobs — and the scene does one. Source is `AUTHORED_TAIL_WEIGHTS` leaving retain
2.5% after `present` takes 90 s of 239 (37.7%). **Flagged for review, not
adjusted**: tuning a weight against one video is the n=1 mistake the harness work
exists to prevent.

---

## 9. Standing items carried forward

- **ISSUE-3 (MAX_TOKENS, STANDING).** 16000 → 32000 → 64000, three raises for
  the same cause. **A fourth overrun is not a ceiling problem** — it means
  examining `effort` and the prompt's growth, not the ceiling.
- **ISSUE-1 (recall slot, BLOCKING).** Stage 2c, not fixed in week 4 by
  agreement. The deterministic gate is available and needs no invented
  threshold: set membership against the previous video's objective refs and
  `new_terms`. ISSUE-7 supplies the registry it needs.
- **ISSUE-4 (no variety budget, SPEC GAP).** Needs to come back into the PRD,
  not be reconstructed here.
- **ISSUE-5 (§9.2 signalling vs 5 non-signalling templates, OPEN).** On v2, 4 of
  9 scenes are exempt from a rule §9.2 states without exceptions.
- **ISSUE-6 (§9.3 vs table templates).** RESOLVED to count strings; the §9.3
  amendment question stays open for the PRD.
- **ISSUE-7 + ISSUE-1 (term registry / recall gate, BLOCKING).** Merged into one
  piece of work and scheduled at the **front of week 5, before any TTS**.
- **ISSUE-8 (s04 factual error, BLOCKING).** New. Needs §7.2's Fact Checker.
- **ISSUE-9 (systematic speaking-rate overrun, MEASURED).** New.
- **ISSUE-10 (retain slot weighting, OPEN).** New.

---

## 10. Every authored and unreviewed number, in one place

| where | constant | value | why it is not from v0.2 |
|---|---|---|---|
| `linter.py` | `AUTHORED_TEMPLATE_SHARE_MAX` | 0.40 | v0.2 has no variety budget (ISSUE-4) |
| `templates.py` | duration bands (`min_sec`/`max_sec`) per template | various | §4.4 names composition types, §9.1 budgets slots; nothing states how long a layout needs |
| `templates.py` | `supports_signalling=False` on 5 templates | — | §9.2 says "never zero" without exception; the flag is my judgement (ISSUE-5) |
| `templates.py` | `on_screen=False` on `cold_open.premise`, `concept_illustration.subject` | — | v0.2 does not distinguish displayed text from a brief for the imagery |
| `a11y.py` | flash luminance delta | 0.10 | PEAT's own general-flash definition, not v0.2's — v0.2 gives the rate and area but not what counts as a transition |

Everything else in `linter.py`, `a11y.py` and `gagne.py` is transcribed from a
stated number and guarded by a test that fails if it drifts.
