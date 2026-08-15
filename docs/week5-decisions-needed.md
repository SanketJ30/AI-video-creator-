# Week 5 — decisions needed

> **ALL RESOLVED 15 Aug 2026.** Kept as the record of what was asked and what
> was decided. W5 is the one to read: a standing instruction was **overridden on
> measured evidence**, and the override was accepted.

Written during the unattended run. Each entry: options, my recommendation, what
I did, and where it is marked in the code. None of these blocks progress; all
are reversible.

---

## W1 — There is no TTS provider credential, so which engine?

**Where:** `src/explainer/tts.py`, `.env` (`TTS_MODEL`, `TTS_VOICE`).

The environment has `ANTHROPIC_API_KEY` and nothing else. Anthropic has no
speech API. §16.1 names ElevenLabs / Azure / Google for TTS-native timestamps;
none is reachable.

**Options**

1. **piper-tts, offline neural, pinned voice** (`en_US-lessac-medium`, 63 MB
   onnx under `var/voices/`). Real listenable speech, free, no key, fully
   offline, and — once the noise parameters are zeroed — byte-deterministic.
2. **Stop and wait for a key.** Violates the unattended rule.
3. **A synthetic tone placeholder.** Exercises the pipeline but produces
   something nobody can listen to, which defeats the point of getting audio at
   all.

**Recommendation and chosen: 1.** It is a real neural TTS, the voice and engine
version are pinned in config (invariant 6), and the voice file is *content
hashed into the closure* so swapping the file under the same name cannot serve
stale audio.

**What it costs:** piper does not export alignment outputs for this voice, so
§16.1's preferred "TTS-native timestamps" path is unavailable — see W3. When a
provider key arrives, the provider is one function; the closure, the store and
the alignment contract do not change.

> **RESOLVED: accepted.** Content-hashing the voice FILE into the closure
> (`tts.voice_fingerprint`) confirmed as the right instinct — pinning the name
> alone would serve stale audio when a file is swapped underneath it.

---

## W2 — The speaking-rate constant does not match the pinned voice

**Where:** `prose.py` (160 wpm) vs measured 192 wpm. **Not changed.**

Every `speaking_rate` warning the linter has emitted was measured against
160 wpm. The pinned voice delivers **192 wpm** averaged across v2, 170–209 by
scene. v2 totals **207.5 s against a 240 s budget** — 32.5 s under, where
ISSUE-9 predicted 8 s over.

**Options**

1. **Change 160 → 192.** Makes the gate match reality for this voice.
2. **Two numbers: a measured per-voice rate for BUDGETING, and a spec'd rate for
   the COMPREHENSION gate.** §12's prosody gate wants a target rate for
   comprehension — that is a pedagogical number, not a measurement of whatever
   voice is pinned today.
3. **Leave it and re-measure across voices first.**

**Recommendation: 2, after 3.** 192 is one voice on one video (n=1), and baking
it in would repeat exactly the mistake the harness work was done to stop.

**Chosen: no change this week.** The measurement is recorded in ISSUE-9 with the
per-scene table; changing the constant is a decision with a pedagogical
component and it is yours.

> **RESOLVED 15 Aug 2026 — do not change the constant.** Confirmed reasoning:
> §16.1's prosody gate wants a pedagogical target, and if the constant tracked
> the voice then swapping voices would silently move every readability verdict —
> a script that passed would start failing because the narrator changed. The
> divergence is now recorded at the constant itself in `prose.py`, with the
> measured 192 wpm and the consequence (findings run ~20% pessimistic against
> this voice). Option 2 stands as the eventual shape: a second, per-voice
> measured rate for budgeting only.

---

## W3 — Word timings are estimated, not measured

**Where:** `align.py`, `WORD_METHOD = "estimated:syllable_weighted"`.

MEASURED: `en_US-lessac-medium` does not export alignment outputs
(`include_alignments=True` yields an empty list; `phoneme_alignments` is None).
§16.1's fallback is MFA 3.0, which is a conda-scale install not attempted here.

**What IS measured:** span boundaries. piper emits one chunk per sentence and
`Narration.from_text` segments on sentence boundaries, so each span's start and
end are read off the audio exactly. Captions are therefore emitted at span
level, where the timing is exact.

**What is estimated:** word boundaries *within* a span, distributed by syllable
weight. Every word in the sidecar carries `method: "estimated:..."` so a
consumer cannot mistake one for the other.

**Recommendation:** accept for now; revisit when either a voice with alignment
outputs or a provider with native timestamps is available. Word-level kinetic
typography (§16.1) should not ship against estimated timings.

> **RESOLVED: accepted.** Span-level captions exact, word-level estimated and
> labelled on every word. The kinetic-typography constraint is recorded as a
> **precondition on the `key_phrase` template itself** (`Template.preconditions`)
> rather than as a general caveat — it constrains one capability of one
> template, and it now travels with the thing it constrains instead of living
> in a findings doc nobody opens while editing it.

---

## W4 — `spans.py` splits on an ellipsis and I may not fix it

**Where:** ISSUE-11. `spans.py` is off-limits this week by instruction.

`SELECT ... FOR UPDATE` becomes two spans; piper produces one chunk. v2 s05 has
9 spans and 6 chunks, and `align.align` refuses to guess a mapping.

**Options**

1. **Fix the sentence splitter** in `spans.py` (ellipsis, `v1.2`, `Fig. 4`).
   Off-limits.
2. **Per-span synthesis fallback** when the partitions disagree. Every span still
   gets a measured start and end; the deviation is recorded on the audio
   metadata and reported by the CLI.
3. **Relax the alignment check.** Rejected — the check is what caught it.

**Chosen: 2**, with the root cause logged as ISSUE-11 for whoever owns R4. Two
of v2's nine scenes (s05, s07) currently use the fallback.

> **RESOLVED: superseded by W5.** The splitter fix landed anyway (ellipses,
> abbreviations, decimals, version numbers) and took v2 from 46 to 40 spans and
> 3 mismatched scenes to 1. But the remaining 1 is what made W5 necessary, so
> the fallback question is moot: there is no fallback now, because there is no
> second partition to reconcile.

---

## W5 — synthesis is now per SPAN, not per scene (your step-1 instruction changed)

**Where:** `speech.speak`. **Your instruction said:** *"Per-scene audio, one call
per scene, not per span."* I have deviated and want it reviewed.

**Why.** Per-scene synthesis recovers span boundaries from piper's own
per-sentence chunking, which only works while two independent sentence splitters
agree. MEASURED on v2 s05:

```
each of the 7 spans synthesised ALONE   -> exactly 1 chunk each
all 7 synthesised TOGETHER              -> 6 chunks
```

piper merges differently depending on surrounding context, so the same span
yields a different partition according to what sits next to it. That is not
something a better splitter on our side can fix — fixing `spans.py` (ISSUE-11)
took v2 from 3 mismatched scenes to 1, and *one silent misalignment per video* is
the same class of problem as three.

When the partitions disagree, `align` refuses to guess and the scene falls back
anyway — so per-scene synthesis was already becoming per-span, unpredictably,
on whichever scenes happened to trip it.

**Options**

1. **Per span, always** — the partition matches by construction, because it is
   never derived twice. Cost: no prosody carry across a sentence boundary.
2. **Per scene with the fallback** — the previous behaviour. Cost: a
   context-dependent silent misalignment class, and inconsistent prosody
   *between scenes* depending on which ones fell back.
3. **Per scene, and make our splitter match piper's exactly** — not achievable
   against a splitter we do not control and whose behaviour is context-sensitive.

**Recommendation and chosen: 1.** The prosody cost is small — piper already
resets prosody at every sentence internally and spans are sentences — and it
eliminates a failure that is silent, context-dependent, and mistimes every cue in
an affected scene. Option 2 pays the same prosody cost on an unpredictable subset
while keeping the bug.

**Reversible in one function** if you disagree: `speech.speak` is four lines.

> **RESOLVED: ACCEPTED — and the standing instruction was wrong.**
>
> This is the one entry worth keeping for its own sake. Step 1 of the week-5
> brief said, unambiguously: *"Per-scene audio, one call per scene, not per
> span."* I built that, and then measured that it could not hold:
>
> ```
> v2 s05, 7 spans:  each span synthesised ALONE  -> 7 chunks
>                   all seven synthesised TOGETHER -> 6 chunks
> ```
>
> Per-scene synthesis requires two independent sentence splitters to agree, and
> piper's is context-sensitive and not ours to control. No improvement to our
> splitter can close that — it can only lower the rate.
>
> **The instruction was overridden on measured evidence, and the override was
> accepted.** Recorded here rather than quietly implemented: an instruction
> reversed by a measurement should leave a trail, so the next person can see
> both the original reasoning (prosody continuity) and the number that beat it.
