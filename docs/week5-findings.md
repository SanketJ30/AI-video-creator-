# Week 5 findings — TTS, alignment, timing, render, assembly

Milestone A's back half: from a storyboard to an MP4.

**What everything was measured against:** course `mvcc-write-skew`, brief **v5**,
video **v2** (9 scenes), script regenerated this week under `script_writer@v3`
(step 0), storyboard replanned under `visual_planner@v1` + `signal_designer@v1`.
Voice `piper-tts@1.6.1 / en_US-lessac-medium`. One video, one voice — every rate
below is n=1.

---

## 1. The headline numbers

**There is an MP4.** `C:\Users\Sanket\projects\explainer-pipeline\var\render\mvcc-write-skew-v2.mp4`, 7.79 MB.

> Re-rendered 15 Aug after the ISSUE-11 segmentation fix and the W5 switch to
> per-span synthesis. Numbers below are from that run. The earlier run
> (219.067 s, 46 spans) is superseded: it had 3 scenes on the per-span fallback
> and 6 spans that were fragments rather than sentences.

| | |
|---|---|
| **Measured runtime** | **218.33 s** (00:03:38.33) |
| Resolved runtime | 218.333 s (6550 frames @ 30 fps) |
| **Drift, resolved vs measured** | **0.00 s** |
| Budget | 240 s |
| **Over/under budget** | **−21.67 s (9.0% under)** |
| Format | 1920×1080, h264 High, yuv420p, 30 fps |
| Audio | AAC mono 48 kHz, 181 kb/s, mean −17.5 dB, peak −0.0 dB |
| Narration audio alone | 207.5 s |
| Silence padding | 11.5 s, almost all of it s04 |
| **Byte-identical render** | **YES** — see §3 |
| Scenes | 9 · Spans 40 · Cues 9 · Templates 4 |
| Sidecars | `.vtt` (40 cues), `.srt`, `.words.json` (136 KB) |

**The measured runtime matches the resolved timeline exactly.** That is §11.4's
whole argument working: integer frame counts, audio padded to the frame, concat
demuxer with `-c copy`, one final encode. No drift accumulated across nine
scenes.

Peak audio at −0.0 dB is close to clipping. §7's −14 LUFS / −1 dBTP targets are
week 7 and no loudness normalisation runs yet; noting it so it is not mistaken
for a finished mix.

**It runs under, not over.** Every scene except `s04` is `elastic`, so its
duration is the audio's; the 11 s of padding is `s04`, which is `rigid` at 90 s
and whose narration only fills 79 s.

The video is **not trimmed to fit** and no scene was shortened. §15.3's rules
decided every duration and the total is what they produced.

---

## 2. ISSUE-9 was wrong, and the correction is the most useful thing this week

Week 4 predicted v2 would run **~8 s over** budget once TTS supplied durations.
It runs **21 s under**. The prediction failed because it rested on a constant
nobody had checked against a real voice.

`prose.py` measures speaking rate at **160 wpm**. The pinned voice delivers
**192 wpm** averaged across the video, 170–209 by scene:

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

So **every `speaking_rate` warning the linter has ever emitted was measured
against a rate this pipeline does not produce.** All four "over budget" scenes
are comfortably under.

**The constant was not changed.** 192 is one voice on one video, and §12's
prosody gate wants a *target* rate for comprehension — a pedagogical number, not
a measurement of whatever voice happens to be pinned. Recorded as **W2** in
`week5-decisions-needed.md`; the shape is probably two numbers, one measured
per-voice for budgeting and one spec'd for the gate.

This also makes **ISSUE-10 worse**: the retain slot's 6 s buys 5.76 s of speech,
0.24 s to spare, so there is still no room for §9.1's spaced-review hook.

---

## 3. Byte-identity: the check passed, after finding a real failure

§11.3 calls periodic double-rendering the thing that *"catches nondeterminism
before it corrupts the cache"*. It is wired into `render --check-determinism`
and into the test suite.

| case | frames | result |
|---|---:|---|
| `key_phrase`, no cues | 60 | **byte-identical** |
| `key_phrase`, no cues | 10 | **byte-identical** (in the suite) |
| `table_build`, 2 cues, animated build | 180 | **byte-identical** |

### But TTS was NOT deterministic, and that is the finding

Before any of the above, piper's **default** configuration failed outright. Two
synthesis calls on the same string produced audio of **different lengths**:

```
call 1 : 120832 samples
call 2 : 125952 samples     differing from sample 0
```

Not floating-point drift — VITS's stochastic sampling (`noise_scale` on the
flow, `noise_w_scale` on the duration predictor). Seeding numpy does not reach
it, because the sampling happens inside the ONNX graph.

`noise_scale=0, noise_w_scale=0` makes it byte-identical across fresh processes.
**The price is flatter prosody**, and it is worth paying: §11.3's whole argument
is that a cache returning different bytes for one key is a bug that takes weeks
to find. Pinned by a test so nobody restores the noise for nicer delivery
without seeing what it costs.

### What determinism cost in throughput

`Config.setConcurrency(1)` and `swangle` software rasterisation are both §11.3
hermeticity pins. They make a 6572-frame video a **multi-minute** render on this
machine. That is a real cost and the right trade at this stage, but it is the
first place to look when render latency becomes a budget problem (§15) — the
answer is more workers, not more concurrency inside one.

---

## 4. Numbers I had to raise on

| § | what | why not implemented | what the code does |
|---|---|---|---|
| §12 | *"TTS and voice"* as a section | **§12 is Course memory.** There is no §12 TTS section; TTS guidance is in §16.1, §14.1 and §7.2 Tier 4 | used §16.1's word-timing rules; noted the numbering here rather than citing a section that says something else |
| §16.1 | TTS-native word timestamps | `en_US-lessac-medium` does not export alignment outputs — `include_alignments=True` yields an empty list | **span** boundaries measured from per-sentence chunks; **word** boundaries estimated and labelled `estimated:syllable_weighted` on every word |
| §16.1 | MFA 3.0 fallback | conda-scale install, not attempted | as above |
| §11.4 | handle-frame count `T` for dissolves | v0.2 gives no number | `DEFAULT_HANDLE_FRAMES = 15` exists but **no dissolve is implemented**; a dissolve is refused rather than silently rendered as a cut |
| §11.6 | CMAF packaging, 4 s segments, HLS/DASH | delivery, not assembly; nothing consumes it yet | not built. Scene boundaries are already frame-aligned, which is the precondition |
| §11.5 | licence tier | commercial, not technical | `LICENSE_KEY = "free-license"` — the evaluation clause, stated in code so the tier is not a guess |

### Authored and unreviewed, new this week

| where | value | why |
|---|---|---|
| `tts.SYNTHESIS_PARAMS` | `noise_scale=0, noise_w_scale=0` | forced by §11.3 determinism; the *choice to prioritise determinism over prosody* is the authored part |
| `assembly.FINAL_CRF` | 18 | v0.2 gives no quality target. Visually lossless for flat graphics; §11.6 warns aggressive encoding rings small text |
| `assembly.FINAL_PRESET` | `slow` | throughput/size trade, no spec basis |
| `render.PRORES_PROFILE` | `4444` | §11.4 names ProRes without a profile |
| `align.WORD_METHOD` | syllable-weighted | the distribution model itself; §16.1 expects measured timings |
| Scene palette | 4 hex literals | no brand palette exists (week-4 D6). They live in `Scene.tsx` and arrive through props once Phase 5 binds one |

---

## 5. What surprised me

**0. The first full render was a technically perfect SILENT video.** This is
the finding of the week and it is logged as **ISSUE-12**. A correct 1080p
3:39.07 MP4, correct captions, runtime matching the resolver to the hundredth of
a second, byte-identical renders — and `mean_volume: -91.0 dB` end to end.
Remotion's ProRes output carries its own silent **stereo** track, and ffmpeg's
default audio selection prefers more channels, so it chose that over the
narration's **mono** track without warning.

Every structural check passed because every structural check was right. **The
pipeline verified reproducibility, not correctness** — determinism cheerfully
confirmed the silence was perfectly reproducible silence. Fixed with explicit
`-map 0:v:0 -map 1:a:0`, an `_assert_audible()` gate after every mux, and
`stream_map` added to the mux closure (without which every pre-fix mux would
have been served from cache and stayed silent — the fix would have appeared to
do nothing, which is the worse failure).

This is the same shape as ISSUE-8: a check that measures form passing something
that is wrong in substance.

**1. Fixing our sentence splitter turned out not to be enough.** `spans.py`
treated `...` as a sentence terminator, so `SELECT ... FOR UPDATE` became two
spans while piper produced one chunk. ISSUE-11, now **fixed**: non-terminal dots
(ellipses, `i.e.`, decimals, version numbers) are masked before splitting. v2
went 46 → 40 spans and 3 → 1 mismatched scenes.

The surviving one is the interesting part. MEASURED on s05: each of its 7 spans
yields **exactly 1** piper chunk alone, and all 7 together yield **6**. piper
merges by surrounding context, so no splitter of ours can be made to agree with
it in general. Synthesis is now **per span by construction** (W5) — the spans and
the chunks are the same list rather than two algorithms that happened to match.
40 of 40 spans now align with no reconciliation.

**2. `Narration.from_text` does not produce stable span ids.** Two calls on the
same string returned `sp_86413ddd46` and `sp_939670a2cc`. Anything that
re-derives spans from stored text therefore breaks **every** cue anchor R3
depends on — and breaks it *quietly*, because the regenerated ids are still
well-formed. This was live in my own first draft of the render path. Fixed with
`speech.StoredNarration`, which adapts the stored rows instead of re-segmenting.
**Nothing in a render path may call `from_text` on narration that already
exists.**

**3. The recall gate caught my own design error, not the model's.** Step 0's
first gate keyed on `objective_ref`, which is code-assigned and must be one of
*this* video's objectives. The model was doing exactly the right thing — it
recalled v1's xmin/xmax objective in prose and listed the right
`assumed_known_terms` — and could not satisfy a gate that was asking for
something structurally impossible. The prior-objective link needed its own
field. The escalation was the fix arriving, not a failure.

**4. Remotion rejects FFV1.** A `.mkv` output name maps to `h264-mkv` and
conflicts with `--codec ffv1`. §11.4 names ProRes first anyway, so this cost
nothing — but it is the kind of thing that would have cost a day if it had
surfaced during a deadline instead of on day one.

**5. ISSUE-8 did not recur.** The regenerated s04 does not contain the false
"neither writes the row the other reads" claim. **Nothing detected it** — a
stochastic stage re-rolled and landed differently. Recorded as variance, not a
fix. If anything it strengthens the case for §7.2's Fact Checker: a defect that
appears and disappears across samples is one manual review catches only by luck.

---

## 6. Step 0 — the Wedge A carry-over, and it worked

ISSUE-1 and ISSUE-7 were one piece of work: a per-course term registry.

| | before | after |
|---|---|---|
| recall slot | recalled v2's own content | recalls v1's xmin/xmax objective **by ref** |
| `snapshot` | re-declared new in v2 | **not** re-declared |
| terms v2 re-declares from v1 | 1 | **0** |

The registry is a set union over `scenes.pedagogy_meta` for videos with a lower
teaching ordinal. Deterministic, no model, no threshold. Both gates run **inside
the repair loop**, so a violation is fixed by the model rather than escalated to
a human — which is what happened: one escalated run, then a clean one.

The new recall narration:

> *"You already learned to explain how xmin and xmax decide which row versions a
> Repeatable Read snapshot can see. That rule is what keeps a transaction's own
> reads consistent, row by row, from start to finish. Now watch two
> transactions, each one perfectly consistent by that same rule, that together
> still break a rule neither one touched alone."*

That is the course-memory mechanism working end to end for the first time.

---

## 7. Cost

| step | spend |
|---|---:|
| step 0, escalated run (3 calls) | ~$0.55 |
| step 0, clean run | $0.38 |
| storyboard replan (visual + signal) | $0.16 |
| steps 1–7 (TTS, align, resolve, render, assemble) | **$0.00** — all local |
| **total** | **~$1.09** against a $5 cap |

TTS is free and offline. Rendering is CPU. §21's per-video agent budget is
untouched by anything in week 5.

---

## 8. Issues opened or changed this week

- **ISSUE-11 (new, BLOCKING, worked around)** — ellipsis splits a span;
  spans/chunks disagree.
- **ISSUE-9 (corrected)** — the overrun prediction was wrong; the defect is the
  160 wpm constant.
- **ISSUE-8 (updated)** — did not recur; explicitly not a fix.
- **ISSUE-1 + ISSUE-7 (fixed)** — per-course term registry.
- **ISSUE-10 (worse)** — retain has 0.24 s of headroom, not room for two jobs.
- **ISSUE-12 (new, FIXED)** — the first full render was silent; structural
  checks all passed.

Decisions needing a human: **W1–W4** in `docs/week5-decisions-needed.md`.
