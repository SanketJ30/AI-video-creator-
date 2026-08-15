# ISSUE-19 — scoped generation: the missing half

**Status:** designed, not built. This is Milestone B's core problem.
**Read this first** if you are picking up the render/edit layer.

---

## 1. The problem in one paragraph

Every diagnostic in this system pinpoints defects finely. The Fact Challenger
returns a verdict **per span**. The pedagogy linter returns findings **per span
or per scene**. The content-addressed cache invalidates **per scene**. The
author — `script_writer.generate` — can only rewrite **an entire video**.

So the smallest available response to a two-span problem is a twenty-five-span
re-roll. And **invariant 8** says that re-roll is not a fix: it is a dice throw,
measured to have made a narration worse (5 spans refuted, up from 3, plus a
reintroduction of an error the challenger had already found once).

The precision of the diagnosis has nowhere to go. That caps the value of every
checker in the system regardless of how good its verdicts are, and it is the
reason two known prose defects are shipping.

### Why this is §5.1's premise not holding

§5.1 models a video as a hierarchy — video → scene → span — and the whole
architecture is built on that grain: R1 stores durations per scene, R3 anchors
cues to spans, R4 segments narration into spans at authoring, §11.2 invalidates
per component, §11.4 makes scene renders position-independent so one scene can
re-render alone.

**Everything downstream of authoring honours that grain. Authoring itself does
not.** The object model says a span is a unit; the generator says the video is
the unit. Milestone B's promise — *edit one word in scene 5, verify one scene
re-renders* — is only half true today: the render half works and has the
byte-identity tests to prove it, and the authoring half cannot express the edit.

---

## 2. Two operations, in increasing difficulty

### 2.1 Per-scene regeneration

**Request:** rewrite scene *k*'s narration, holding every other scene
byte-identical.

**What it needs as input**

| input | why | where it is today |
|---|---|---|
| the slot spec for scene *k* | the Gagné slot, its budget and treatment rule | `gagne.plan_slots(script_type, target_seconds)[k]` — deterministic, already available |
| the objective the scene serves | slot-to-objective mapping | `_objective_for_slot` — available |
| **the narration of scenes 1..k-1 and k+1..n** | so the rewrite does not contradict, repeat, or forward-reference its neighbours | available, but **not currently passed to the writer at any granularity** |
| the term registry state **as of scene k** | `new_terms` is a running set in slot order; a scene rewritten in isolation does not know which terms were already introduced *before* it | `termregistry.build` gives the per-course prefix; the within-video prefix is computed inside `_assemble` and is **not exposed** |
| the course's `factual_constraints` | statements the rewrite may not contradict | available, brief v6+ |

**What breaks**

1. **`new_terms` for every LATER scene.** The running set is order-dependent. If
   scene 4 stops introducing "write skew" and scene 6 starts, then scene 6's
   `new_terms` changes without scene 6 being touched. §9.2's pre-training rule
   reads that set, so a rewrite of scene 4 can silently make scene 6 violate a
   pedagogy rule. **The set must be recomputed for the whole video after any
   scene rewrite** — it is deterministic and cheap, but it must be *done*, and
   nothing does it today.
2. **The recall gate (ISSUE-1).** If scene *k* is the recall slot, its
   `recalls_objective_ref` and `assumed_known_terms` must still satisfy
   `termregistry.check_recall_slot`. That gate currently runs inside
   `generate`'s repair loop and would need to run in the scoped path too.
3. **Cues in scene *k*.** Every cue in that scene anchors to a span id that no
   longer exists. **All of scene k's cues are invalidated** and the signal
   designer must re-run for that scene. Cues in other scenes are untouched,
   because R3 anchors are scene-local.
4. **The scene's duration, and therefore the video's.** Duration is derived from
   TTS (R5), so a rewrite changes scene *k*'s duration and every later scene's
   *start* — but starts are derived, not stored (R1), so this costs a manifest
   rewrite and one concat, not a re-render. **This part already works.**
5. **Nothing else.** Other scenes' renders, audio, alignments and cues are
   untouched, and their content hashes prove it.

**Cost of doing it right:** 1 script call + 1 visual/signal call for the scene +
1 TTS call per span + 1 scene render + 1 concat. Versus a full regeneration:
1 script call + 2 storyboard calls + 40 TTS calls + 9 renders. The TTS and
renders are cached, so the real saving is the *blast radius*, not the compute.

### 2.2 Per-span regeneration — what the challenger actually needs

**Request:** rewrite span *j* of scene *k* in place, leaving every other span
byte-identical **including its id**.

This is harder, and the difficulty is not the model call.

**The hard constraint: the span id must survive.**

R3 anchors cues to span ids. `Narration.author` mints ids from `uuid4` and is
**not stable** — that is measured, and it is why `from_stored` exists. So a
per-span rewrite cannot go through `author`: it needs a third constructor that
**replaces one span's text while preserving its id and its neighbours'
identity**. Neither existing constructor does this, deliberately — the two-way
split (`author` mints, `from_stored` requires) was built precisely so that no
code path could mint an id by accident.

    Narration.replace_span(span_id, new_text) -> Narration
        - keeps span_id
        - keeps every other span object identical
        - MUST NOT re-segment: if the new text contains a sentence boundary it
          is still ONE span, or the partition changes and every later cue shifts

That last clause is the subtle one. A rewrite that turns one span into two
sentences either (a) stays one span, giving a span that is not a sentence — the
ISSUE-11 shape, which makes TTS prosody wrong; or (b) becomes two spans, which
mints an id and changes the count, which is a per-scene operation wearing a
per-span costume. **A per-span rewrite must be constrained to produce exactly
one sentence**, and the prompt must say so and the parser must enforce it.

**What breaks**

1. **The span's own cues.** Any cue anchored to span *j* still resolves — the id
   survives — but it may now point at a moment that no longer says what the cue
   is highlighting. A cue whose `rationale` referenced the old words is stale
   even though it resolves. **Cues on the rewritten span must be re-examined;
   cues on other spans are fine.** This is a genuinely new state: *resolvable
   but semantically stale*, which nothing currently detects.
2. **Timings for the whole scene.** Span durations come from TTS per span
   (W5, per-span synthesis). Rewriting span *j* changes its audio length, which
   shifts the start of spans *j+1..m* **within the scene**, which moves every
   cue anchored to them. Those cues resolve correctly because they resolve from
   span timings, not absolute times — so **this is automatic and safe**, and it
   is a direct payoff from R3 and from per-span synthesis. Scene duration
   changes; later scenes' starts shift; nothing re-renders but scene *k*.
3. **`new_terms`.** Same problem as per-scene, one level finer. A term
   introduced in span *j* and removed by the rewrite changes the running set for
   every later span and scene. Recompute video-wide.
4. **Captions and the word sidecar.** Span-level captions are exact and
   regenerate from the new alignment. The word sidecar's estimated timings for
   that span are recomputed. Both are derived; neither is a problem.
5. **The audio cache.** The rewritten span's TTS is a new closure and
   synthesises; every other span in the scene is a **cache hit**, because the
   closure is text + voice + model + rate + params + lexicon and none of those
   changed. This already works and is the single strongest argument for per-span
   synthesis surviving as the design (W5).

**What must be re-run after a per-span rewrite**

```
span j            : TTS (new), alignment (new)
scene k           : timing resolve, cue resolve, render, mux
scenes k+1..n     : NOTHING — starts are derived (R1/§11.4)
video             : manifest, concat, final encode, captions, word sidecar
video-wide        : new_terms recompute, pedagogy linter, fact challenger on
                    the changed span only
```

---

## 3. What the challenger implies about scoping

The Fact Challenger costs **27 frontier calls per 3-sample video** (E1). A
scoped rewrite makes a scoped re-check possible, and the two together are what
make the loop affordable:

- challenge the **changed span plus its scene as context** — 3 calls at 3
  samples, not 27;
- **cache verdicts against span content**, keyed on span text + constraints +
  prompt version, exactly as the render layer keys on its closure. An unchanged
  span does not need re-challenging and its previous verdict is still valid.

Without scoped generation, scoped checking has nothing to scope *to*.

---

## 4. What I would build first, and what I would not

**First: per-scene regeneration.** The scene is already the unit of the Gagné
form, the render, the cache and the mux. Every mechanism it needs exists except
"pass the neighbouring narration as context" and "recompute `new_terms`
video-wide". It is the smaller change and it unlocks most of the value.

**Second: `Narration.replace_span` and per-span rewrite**, with the
one-sentence constraint enforced in the parser rather than requested in the
prompt.

**Third: human edits as a first-class input** — a span whose provenance says
`human` rather than `script_writer@v4`, so a hand-fixed sentence is visible as
hand-fixed and never laundered into looking machine-produced. R6 already puts
provenance on every object; this is a new value in an existing field.

**What I would not build:** a "regenerate this scene" button with no diff and no
re-gating. That is invariant 8 with a UI on it. Whatever regenerates must show
what changed, re-run the gates that previously passed, and make keeping the old
draft the cheap default (E2).

---

## 5. The one-line summary for whoever picks this up

> Everything downstream of authoring already works at span and scene grain, and
> has the tests to prove it. Authoring is the only stage that still thinks the
> video is the atom, and that single mismatch is what makes every checker's
> precision unusable.
