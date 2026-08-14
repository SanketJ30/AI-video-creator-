# Week 4 — decisions needed

Written during the unattended run. Each entry is a question I would normally
have stopped to ask. For each: the options, my recommendation, what I actually
did, and where the choice is marked `PROVISIONAL` in the code.

**All of these are reversible and none of them blocks week 5.** They are marked
so a review can find them; none is presented as settled.

---

## D1 — Does §9.3's "≤3 simultaneous text elements" count strings or slots?

**Where:** `linter.text_element_count`. **Marked:** `PROVISIONAL(D1)`.
Full write-up: ISSUE-6 in `known-issues.md`.

Measured across all 11 registered templates with a minimal realistic fill:

| counting | max across registry | fires on |
|---|---:|---|
| individual strings | 5 | `table_build` (4), `terminal_replay` (5) |
| filled slots | 2 | nothing, ever |

**Options**

1. **Count strings** — a 2×2 table is 4 elements and warns. Faithful to §9.3's
   number; every table and terminal scene carries a warning a human dismisses.
2. **Count slots** — a table is one element. Nothing in the registry can ever
   exceed 3, so the rule is dead code.
3. **Amend §9.3** to distinguish independent text elements from the rows of one
   structured element, and give a row-count number.

**Recommendation: 1, and raise 3 with a human.** A build's rows arrive one at a
time but they do not leave — at the end of a `table_build` all its cells are on
screen together, which is what "simultaneous" measures. Option 2 buys a quiet
report by making the rule mean nothing, which is the worse failure.

**Chosen: 1.** Warning, never blocking.

---

## D2 — Are `premise` and `subject` on-screen text?

**Where:** `templates.Param.on_screen`, set `False` on `cold_open.premise` and
`concept_illustration.subject`. **Marked:** `PROVISIONAL(D2)`.

§9.4's priority rule was firing on s01 and s08 of the real MVCC video — two
scenes that display no text at all. `cold_open.premise` ("the situation, not the
answer") and `concept_illustration.subject` describe **what the shot depicts**;
they are briefs for the imagery, and `asset` is the thing that renders. Nothing
is typeset from them.

**Options**

1. **They are briefs, not text** — exclude from every §9.3/§9.4 measurement.
2. **They are text** — keep counting them, and accept that two templates always
   warn.
3. **The registry is wrong** — split each into a brief param and a caption
   param.

**Recommendation and chosen: 1.** I authored these templates in step 1 and the
ambiguity is mine, so clarifying my own parameter semantics is in scope. The
flag is declared per parameter rather than inferred, so the same ambiguity
cannot recur silently when a template is added.

**Measured effect: 20 warnings → 18 on video v2. Both removed findings were
false.**

Worth a human eye because it changes what the headline §9.4 number means.

---

## D3 — What share of a video may one template carry?

**Where:** `linter.AUTHORED_TEMPLATE_SHARE_MAX = 0.40`.
**Already marked AUTHORED AND UNREVIEWED**; also logged as ISSUE-4.

You resolved this mid-run: report the distribution, flag a template exceeding a
stated share, mark it authored, log the spec gap against old-PRD §13.5, and do
not reconstruct §13.5 myself. That is what is implemented.

**The 0.40 itself is still unreviewed.** It fires on v2 at 44% (`table_build`,
4 of 9). A different number between 0.34 and 0.44 changes whether v2 is flagged
at all. Warning-only, never blocking.

---

## D4 — Should video-level rules run on a single scene?

**Where:** `linter.scene_findings` vs `linter.lint`. **No mark needed** — this
one I am confident about.

`video_outside_target_band` and `template_variety` measure a *video*. A
one-scene input fires both by construction (60 s < 180 s; one template = 100%),
which made a "clean scene" unit test impossible to write honestly. Split into
`scene_findings(scene)` and `lint(scenes)`; the video-level rules run only in
`lint`. Recorded here because it changes what `lint` means on a partial video,
not because I think it is wrong.

---

## D5 — What luminance change counts as a flash transition?

**Where:** `a11y.flash_windows(threshold=0.10)`. **Marked:** `PROVISIONAL(D5)`.

§16.2 gives the **rate** (>3/s) and the **area** (>25% of frame) but not what
counts as one transition. 0.10 is PEAT's own general-flash definition (relative
luminance change ≥0.10 where the darker state is below 0.80), not a number I
chose — but it is not in v0.2 either, so it is listed.

**Cannot be validated until there are frames to run it on (week 5+).** The
criterion is implemented and tested against synthetic sequences: 3 transitions
pass, 4 fail, a small-area flash does not count, a shimmer between two
near-whites does not count.

---

## D6 — Contrast with no palette: info, warning, or silence?

**Where:** `a11y.check_contrast`, returns `contrast_unresolved` at `info`,
once per video. **Marked:** `PROVISIONAL(D6)`.

There is no palette anywhere in the system — `brand_version` is a bare string
and v0.2 names no colours.

**Options**

1. **Report `unresolved` at info** — the gate stays visible; nine scenes produce
   one note.
2. **Silence** — §4.3 makes the report customer-visible, so a silent absence
   reads as compliance on a WCAG AA gate. Rejected.
3. **Invent a palette** to make the check run. Rejected outright — it would
   produce a compliance number about colours nobody chose.

**Chosen: 1.** Phase 5 owns brand; this becomes a real check then.

---

## Not a decision — just flagged

**ISSUE-7, new this week and BLOCKING.** v2 declares `snapshot` a new term; v1
already taught it. `new_terms` is seeded empty per video, so the code and the
model make the same mistake and the agreement rate reads 9/9. The fix is a set
union over rows already in the database — deterministic, no threshold to invent
— and it supplies the registry ISSUE-1's recall-slot gate needs. It is a Stage
2c defect and week 4 is Stage 2d, so it is logged, not chased, on the same
reasoning you applied to ISSUE-1.
