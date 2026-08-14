# Product Requirements Document
## AI Course Video Engine — working name: **Sequence**

**Version:** 0.2 (Cross-functional review integrated)
**Date:** 14 August 2026
**Owner:** Ravi
**Status:** Pre-build. Written to be argued with.
**Reviewed by:** Product (15y SaaS), Instructional Design (12y EdTech), Motion Design (20y vector/animation)

### Changelog — what v0.2 adds over v0.1

This revision folds in a cross-functional working session. Nothing in v0.1 was deleted; the following was **added or sharpened**:

- **§0.5 — Build posture: who builds this.** The honest answer to "can this be built with only Claude + Supabase + Git, no developers." Short version: yes for the quality proof, no for the moat. Introduces the **Milestone A / Milestone B** split.
- **§4.4 — Output composition.** Locks in what a Sequence video *actually is*: motion-graphics-first (animated diagrams, kinetic type, data viz, screen demos, illustrations, generated B-roll), narrated, with **stock video woven in deliberately for hooks and problem-framing** — stock as seasoning, not the meal.
- **§14.3 — Stock and generated-media sourcing, rewritten.** Adds the Freepik decision (AI-generation output vs stock-library redistribution — they have different licences) alongside the Storyblocks recommendation, and a per-need sourcing table.
- **§2.1 — Audience sharpening.** Early validation should target a P3 (instructional designer) *inside* a small P2 (content team). Do not anchor early signal on P1 solo creators.
- **§22 — Roadmap reframed** around the two proofs and the one specialist hire.

---

## 0. Read this first — the one-page version

### 0.1 The bet

Every AI video tool on the market generates **assets**. None of them generate **curricula**.

Synthesia, HeyGen, Colossyan, Coursebox, Articulate AI — all of them take an input (a doc, a prompt, a script) and emit a video. The ones that emit "courses" do it in a single generation pass from a single source document, which produces coherence by accident, not by design. The moment you want to regenerate lesson 4 six months later, that coherence is gone. Nobody ships a system where **video N is conditioned on the actual, final content of videos 1…N−1**.

That is the gap. It is not a feature gap — it is an architectural gap, and it is defensible, because retrofitting it into a video-asset generator means rewriting the data model.

**Sequence is a course-graph engine that happens to output video.** The durable artifact is not an MP4. It is a versioned, addressable, pedagogically-typed graph of objectives → videos → scenes → assets, with a persistent memory of what has been taught, in what words, with what visual metaphors, and with what result. Video is a render target of that graph. So are quizzes, transcripts, translations, SCORM packages, and spaced-review schedules.

### 0.2 The three things that must be true for this to work

1. **The scene graph is the source of truth, and the renderer is a compiler backend.** If Remotion JSX (or any engine's native format) becomes the durable artifact, everything else in this document becomes impossible — chunked re-render, localization, course memory, engine portability.
2. **Pedagogy is enforced by a linter, not suggested by a prompt.** The quality difference between this and a wrapper around Veo is whether the storyboard passes hard, numeric, evidence-derived checks before it renders. See §9.
3. **Iteration must be nearly free.** Every competitor charges full price to re-render after a one-word edit, and this is the single most-cited complaint in the market. Course content is *edited constantly*. If a comma change costs $40, the product is unusable for its intended job.

### 0.3 Recommended build posture — answering your open question

You asked me to pick. **Hybrid: own the graph, the pedagogy engine, and the render pipeline. Rent every generative model.**

The research makes this near-unambiguous:

| Layer | Own or rent | Why |
|---|---|---|
| Course graph, scene graph, cache/DAG | **Own** | This is the entire moat. Nobody else has it. |
| Pedagogy/ID engine + linter | **Own** | Second moat. Cheap to build, expensive to copy credibly. |
| Render pipeline (compositing, timing, captions, stitch) | **Own** | Rendering is **<0.5% of COGS** ($0.02–0.05/min). Owning it costs almost nothing and buys total control, deterministic caching, and no vendor lock. |
| Text-to-video (B-roll, generative clips) | **Rent** | 80–90% of COGS. Self-hosting arbitrage is *gone*: Wan-14B self-hosted lands at ~$1.50/min at 100% GPU utilisation and ~$3.75/min at a realistic 40% — **at or above Veo 3.1 Lite's API price of $1.80–3.00/min**. Renting is cheaper and better. |
| Avatars | **Rent** | HeyGen Avatar III is $1.00/min with **$1.00 one-time custom avatar creation**. Open-source (MuseTalk 256px, LatentSync 512px) is not competitive, and Wav2Lip is a legal landmine (LRS2 licence taint — research-only). |
| TTS | **Rent** | Rounding error: $0.45 for a 5-min video at ElevenLabs Multilingual rates. |
| LLM agent layer | **Rent** | ~$0.90–1.50 per video. 1–2% of COGS. Use the best model available; do not optimise here. |
| Stock media | **Rent, carefully** | Licensing is the biggest legal trap in the product. See §14.3. |

Fine-tuning your own models is a **Phase 4 question at the earliest**, and even then only for style-consistency LoRAs, not base models. The one place in-house training pays off early is not a video model at all — it's the **template/quality reward model** that learns which storyboards actually work (§17).

### 0.4 What this document is not

It is not a plan you can hand to engineers on Monday. It is a spec of the *right shape* of the system plus an honest account of where it will hurt. §22 is the phased roadmap; §23 is the list of decisions I could not make for you.

Read the companion document, **CHALLENGES.md**, before you fund anything. It is the more important of the two.

### 0.5 Build posture — who builds this, and can it be done without engineers

The open practical question: *can this be built with only Claude (writing the code), Supabase (the graph store), and Git — with no developer on the team?*

The honest answer is a split, and the split matters more than either half. There are two completely different technical problems hiding under "build the video engine," and confusing them is a classic way products like this die.

**Problem 1 — Make one good video.** Topic → objective graph → linter → storyboard → *one* narrated motion-graphics video, rendered once. Remotion for layout, ElevenLabs for TTS, a forced-alignment pass for word timing, FFmpeg to mux, Supabase for the graph, Git for versioning. This is ordinary data/logic/UI work plus a well-trodden Remotion render path. **A determined non-engineer can build this with Claude.** It proves the product is *good*.

**Problem 2 — Make editing cheap.** Change one word → exactly one scene re-renders, frame-accurate and sample-accurate, and it stays true after 40 edits across an 8-video course. This is the content-addressed cache, RationalTime discipline, the hermeticity checklist, handle-frame transitions, and the two-phase timing resolver. It is **CHALLENGES R1 (Fatal)** and the reason **R28** says hire the video-pipeline specialist *first*. The failure mode is not a crash you can debug — it is a subtly-wrong video discovered by a customer three weeks later with no traceable cause. This is **not** a "Claude writes it Tuesday" problem.

Problem 1 is buildable solo. Problem 2 is the moat. **The gap between them is the whole game**, and §4.3 already says it: *the demo is the editing, not the generation.* The thing you can build alone is the thing that is not yet defensible.

The reconciliation — and it respects the "single video first" instinct — is to treat the first step as **two milestones**, not one:

| | Milestone A — Proof of *Good* | Milestone B — Proof of *Cheap Iteration* (= Phase 0, §22) |
|---|---|---|
| **What** | Objective graph → linter → storyboard → one rendered video | Hand-authored storyboards, edit-one-scene loop, no AI |
| **Proves** | The pedagogy engine + visual quality clear the bar an ID would sign off on | The chunked re-render is clean, deterministic, sync-accurate |
| **Who** | **Solo + Claude + Supabase + Git** | **+ one video-pipeline contractor, 6–8 weeks** |
| **Risk it retires** | "Is this worth building?" | "Is the moat buildable?" |

**Hard rule that ties the two together:** even in Milestone A, where there is no cache, the scene-graph schema must be built exactly as **R1–R8** demand (durations not positions, RationalTime, span-anchored cues, renderer-agnostic). The *cache* can come later; the *data model that makes the cache possible* cannot. If Claude improvises the schema in Milestone A to move fast, Milestone B is poisoned before it starts. This is the "core so strong the phases integrate" that the whole product depends on — and it is, literally, the graph. The ten irreversible schema decisions are enumerated in the CHALLENGES "decisions before writing code" table; get those right once and localisation, SCORM, xAPI, and the cache all attach without a rewrite.

**Recommendation:** build Milestone A entirely solo to find out if the product is worth it. Then bring in **one** video-pipeline contractor for Milestone B / Phase 0 — not a team, not a permanent hire yet, just the rarest skill on the one Fatal-risk problem. If Phase 0 fails its kill criterion even with a specialist, you have saved yourself a year of solo effort on something that could not have worked.

---

# PART I — STRATEGY

## 1. Market context

### 1.1 What exists (August 2026)

The landscape splits into five camps.

**Enterprise avatar SaaS.** Synthesia (~$4B valuation, >$100M ARR, ~65k customers) and HeyGen. Both converged on the same architecture in 2026: avatar spine + generative B-roll. Synthesia 3.0 uses Veo 3 behind Express-2 avatars; HeyGen composes Seedance 2.0 shots around Avatar V. Neither ships avatar-only or generative-only anymore.

**L&D-native challengers.** Colossyan is the closest thing to a course product: document → modules + lessons + assessments in one pass, SCORM on all paid plans, xAPI, branching, and — notably — a claim of editing without full re-render. Coursebox and Mindsmith are in the same lane.

**Authoring incumbents bolting on AI.** Articulate 360 ($1,449–1,749/user/yr, localisation add-on from **$5,000/yr**), iSpring, Adobe Captivate, Camtasia. They own the SCORM/LMS trust relationship and the instructional designer's workflow. Their AI is assistive, not generative-first. They are slow but they are where the budget already sits.

**Generative clip vendors.** Veo 3.1, Seedance 2.x, Kling 3.0, Runway Gen-4.5, Luma, Hailuo. Runway is now effectively a model *router*, reselling third-party models alongside its own.

**Bundled threats.** Google Vids ships inside Workspace at $7–22/user/mo. Canva Magic Studio at ~$12/mo. Both are distribution monsters and both are currently bad at this — Vids' AI storyboards need 60–70% manual rework, Canva gives Pro users 20 ultra-credits/month, making AI video a demo rather than a capability. Assume they get better.

### 1.2 The structural complaints — this is the product brief

Ranked by frequency and severity across G2, Reddit and review sites:

1. **Iteration is priced like creation.** *"Re-rendering after a small script edit costs you the same as a fresh video"* (HeyGen, G2). InVideo users report 15–30% credit overrun from failed edits. Luma doesn't refund failed subscription generations. This is the #1 complaint in the category and it is fatal for course work.
2. **Credit systems are opaque and expiring.** HeyGen credits expire at 12 months, Higgsfield top-ups at 90 days, most don't roll over. Coursebox meters *five separate things* (page credits, images, tutor messages, video minutes, voice minutes).
3. **Uncanny valley / avatar fatigue.** ~350 Synthesia G2 reviews cite unnatural avatars; ~314 cite gesture inconsistency; ~116 HeyGen reviews cite lack of emotional depth. Compounds past ~60 seconds.
4. **Enterprise paywalls on exactly what L&D needs.** Synthesia gates SCORM, brand kits *and* translation behind quote-only Enterprise — a $768/yr Creator customer literally cannot ship to an LMS.
5. **Render latency, even for trivial edits.**
6. **Weak precise editing controls** — the gap between "the prompt got me 80%" and "change this exact thing."
7. **Pronunciation failures** on brand names, acronyms, domain jargon.
8. **Hidden per-asset fees.** Custom avatars ~$1,000/yr at Synthesia and Colossyan; Coursebox branded app $3,000/yr.
9. **Can't show software UI.** Colossyan admits avatars cannot display real computer interfaces — this excludes the largest single category of corporate training.
10. **Lock-in with no export path.** Opus Clip's Premiere/Resolve export is notable precisely because nobody else offers one.

Items 1, 5 and 6 are all consequences of one architectural choice: treating the video as the artifact. Sequence attacks that root cause.

### 1.3 The three defensible wedges

**Wedge A — Course continuity.** Nobody has it. §12.

**Wedge B — Free iteration.** Chunked, content-addressed, DAG-invalidated re-render means a word change costs one scene, not one video. §11. This is simultaneously the biggest cost lever *and* the biggest UX differentiator.

**Wedge C — Pedagogy as an enforced contract.** Every competitor markets "engaging." None publish what that means. Sequence ships a linter with numeric thresholds derived from the actual multimedia-learning literature, and exposes the report to the buyer. For an EdTech buyer selling learning outcomes, this is a purchasing argument, not a feature. §9.

### 1.4 An uncomfortable finding you should absorb now

The 2025 meta-analysis of Mayer's multimedia research (92 articles, 181 studies, overall effect g = 0.37) found that the principles which **replicated strongly** were: *coherence* (removing extraneous material), *personalisation* (conversational tone), and *prompting self-explanation*. The principles that came out **weak or non-significant** were: *segmentation*, *contiguity*, *voice* (human vs machine), and *social presence / embodiment*.

Read that again. **Embodiment and voice — the two things the entire avatar industry sells — did not replicate.** Separately, eye-tracking on 87 undergraduates showed learners over-attend to avatar faces at the expense of instructional graphics, and a study of 240 corporate learners found that when they were told mid-session that their instructor was synthetic, trust and engagement dropped sharply *with no change in objective learning outcomes*.

**Implication:** the reliable wins are **subtractive** (cut, tighten, remove) and **generative** (make the learner do something), not **additive** (more avatar, more animation, more cinematic polish). The market instinct — and, respectfully, parts of your brief — pulls toward additive. The engine's default posture should be aggressively minimal, with richness available on request rather than by default.

This is not an argument against building avatars. It is an argument against making them the product's spine, and for instrumenting the question (§20) rather than assuming the answer.

---

## 2. Users, jobs and positioning

### 2.1 Primary segment (your selection): EdTech and course creators

Three concrete personas:

**P1 — The Solo Expert Creator.** Domain expert, sells courses on their own platform or Teachable/Kajabi. 5–40 videos per course. Has the knowledge; lacks production skill, time and budget. Currently records themself on Loom or hires a freelancer at $500–2,000/video.
*JTBD:* "Turn what I know into a course that looks like a funded company made it, without me being on camera or learning After Effects."
*Buying trigger:* launch deadline. *Churn risk:* one course and done — see §21.4.

**P2 — The EdTech Content Team.** 3–15 people at a company selling courses (upskilling, test prep, professional certification). Ships 50–500 videos/year, in 2–8 languages, on a curriculum that gets revised every term.
*JTBD:* "Ship and *maintain* a large catalogue without the maintenance cost growing linearly with the catalogue."
This is the **best-fit segment**: they feel the iteration-cost pain acutely, they have real localisation needs, and they have recurring budget. Land here.

**P3 — The Instructional Designer.** Employed by P2 or by a corporate L&D function. Uses Articulate today. Deeply sceptical of AI content quality, and correct to be.
*JTBD:* "Do the thinking; stop doing the production."
**Critical:** this persona is the *gatekeeper* who can kill a purchase. The pedagogy linter and the full-manual-override path exist substantially to win this person. If the product feels like it takes their judgment away, they will block it. If it feels like it executes their judgment at scale, they will champion it.

**Early-validation sharpening (v0.2).** Build for P2, acquire via P1, but the person to put in the room *first* is a **P3 inside a small P2** — an instructional designer at a 5–15-person course company that revises curriculum every term and ships in 2–4 languages. They feel the iteration-cost pain, they hold recurring budget, and winning the ID wins the team. Do **not** anchor early signal on P1 solo creators: they build one course and churn (§21.4, CHALLENGES R19), so they will tell you the product is great and then leave — the most misleading possible validation signal.

### 2.2 Secondary segments (design for, don't optimise for)

Corporate L&D (needs SCORM/xAPI, brand governance, SSO — mostly a packaging problem once the core exists) and marketing teams (short-form, brand-heavy — the same engine with a different template pack and no course layer).

### 2.3 Positioning statement

> For content teams who ship and maintain course catalogues, Sequence is a course engine that generates and *maintains* video curricula. Unlike AI video generators, which produce disconnected assets you must re-make from scratch to change, Sequence keeps the course as a living graph — so every video knows what came before it, and changing one line changes one scene.

### 2.4 Anti-personas

- **The one-off social video maker.** Solved well and cheaply by InVideo/Fliki/Opus Clip. Our course layer is pure overhead for them.
- **The cinematic storyteller.** Wants Runway. Our constraint system is in their way.
- **The buyer who wants zero involvement.** "Give me a prompt box and walk away" is a demo, not a product. Our value is in controlled iteration; a customer who never iterates is paying for the wrong thing.

---

# PART II — THE SYSTEM

## 3. Product principles

These are tie-breakers for design arguments. In priority order.

1. **The graph is the truth.** Any feature that requires the video file to be authoritative is rejected.
2. **Subtract before you add.** Default output is minimal. Richness is opt-in, per-scene, with a reason.
3. **Nothing is a black box.** Every AI decision is inspectable ("why is this highlighted?") and reversible at that granularity.
4. **Edits are cheap and local.** Any change costs the smallest correct unit of work. If a change is expensive, that is a bug in the DAG, not a fact of life.
5. **Fail loudly, never silently.** Missing asset, missing glyph, failed contrast check → hard stop with a clear message. Never substitute a default and ship.
6. **The learner outranks the author.** Where author preference and learning evidence conflict, evidence wins and the author is told why. (Grounded: learners *preferred* the pedagogically worst text condition in Yue et al. Satisfaction surveys will actively mislead you.)
7. **Every artifact is addressable and versioned.** Scenes, assets, objectives, assessment items, translations — all content-addressed, all diffable.
8. **Escape hatches are features.** Export the timeline (OTIO), export the assets, export SCORM. Lock-in earns short-term retention and long-term distrust; L&D buyers specifically ask about exit before they buy.

---

## 4. Scope

### 4.1 In scope for v1 (first shippable product)

- Course intake → objective graph → per-video scripts → storyboards → rendered video
- Motion-graphics-first output (diagrams, kinetic type, data viz, screen capture, stock/generated imagery), narrated
- **Optional** avatar layer (rented, composited, isolated — §13)
- Chat-based + direct-manipulation storyboard control
- Chunked render with content-addressed cache
- Course memory across videos in a course (§12)
- Auto captions (WebVTT + SRT), word-level timing
- Localisation to a defined initial language set
- Brand kit (colours, type, logo, tone)
- Export: MP4, WebVTT/SRT, SCORM 1.2, and hosted embed
- Pedagogy linter with visible report

### 4.2 Explicitly out of scope for v1

| Not building | Why | Revisit |
|---|---|---|
| Fine-tuned in-house video models | Economics don't work; see §0.3 | Phase 4 |
| Real-time/interactive conversational avatars | Different product (Tavus/Synthesia Roleplay territory); huge scope | Phase 4 |
| An LMS | Integrate, don't compete | Never |
| Live collaborative multiplayer editing | Expensive; sequential collaboration suffices at these team sizes | Phase 3 |
| Mobile authoring | Review/comment on mobile is enough | Phase 3 |
| Full audio description tracks | Design around it — see §16.2 | Phase 3 |
| Marketplace / creator economy | Distraction | Never |
| Text-to-video as the primary visual mode | Cost and reliability; B-roll only | Phase 3 |

### 4.3 The v1 quality bar

A v1 that is not worth shipping: "the AI generated a 5-minute video and it was fine."
A v1 that is worth shipping: **"I generated an 8-video course, watched it, changed 40 things across it by talking to the system, and every change took under 90 seconds and cost nothing."**

The demo is the *editing*, not the generation. Everyone demos generation.

### 4.4 Output composition — what a Sequence video actually is

To remove any ambiguity about the visual product (this is not a slides tool, and it is not a talking-head tool):

**A Sequence video is a narrated motion-graphics video.** The default on-screen content is:
- **Animated diagrams** — structure, flow, relationships, systems
- **Kinetic typography** — key phrases, definitions, emphasis (abridged per §9.4, never walls of text)
- **Data coming to life** — charts and figures that build and animate
- **Screen demos / synthetic UI** — for software and procedural content (§14.1, the category Colossyan can't serve)
- **Illustrations** — conceptual/abstract visuals with a specific look
- **Generated B-roll** — used sparingly, where motion is genuinely the point (§14.2)

…all under **voice narration**.

**Woven into that, used deliberately: short stock video clips.** Their job is specific — a **hook** at the open, or a **real-world shot that grounds the problem** before the animation explains it. Stock is the seasoning, not the meal: it establishes the concrete before you cut to the abstract explanation that does the teaching. This maps exactly onto the Asset Director routing (§14.1): real-world referents → stock; everything structural, quantitative, or abstract → rendered diagram (the default) or illustration.

**On talking-head avatars — explicitly not the spine.** "Motion-graphics-first" is a statement about *what fills the frame by default*, not a statement against video. A talking head is the least cinematic thing you can put on screen; animated explainers are where the visual quality lives, they learn better (§1.4), they localise without re-shooting, and they are deterministic and cache-friendly. Avatars remain a **supported, off-by-default, isolated layer** (§13) for the buyers and personal-brand creators who specifically want a face — never the engine's assumption.

The composition priority, per scene, is therefore: **rendered diagram/UI → illustration → stock (hook/real-world) → generated B-roll (sparingly) → avatar (opt-in)**. Cost, control, localisability, and pedagogical evidence all point the same way, and the Asset Director enforces it.

---

## 5. The Course Graph — core data model

This is the most important section in the document. Everything else is downstream.

### 5.1 Object hierarchy

```
Organisation
 └─ BrandKit            (colours, type scale, logo, motion signature, voice/tone, lexicon)
 └─ Course
     ├─ CourseMemory    (§12 — the differentiator)
     ├─ Objective[]     (DAG, prerequisite edges)
     ├─ Module[]        (Merrill arc: Activation → Demonstration → Application → Integration)
     │   └─ Video[]     (Gagné 9-event slot template)
     │       └─ Scene[] ← THE UNIT OF CACHING, ADDRESSING AND RE-RENDER
     │           ├─ id                 stable UUID, survives reorder
     │           ├─ objectiveId        exactly one
     │           ├─ gagneSlot          hook | objective | recall | present | guide |
     │           │                     elicit | feedback | assess | retain
     │           ├─ narration          { spans[], voiceId, ssml, prosodyProfile }
     │           ├─ visualSpec         { template, slots{}, cues[], timingSensitivity }
     │           ├─ assets[]           content-hash references
     │           ├─ pedagogyMeta       { bloomLevel, elementInteractivity, newTerms[] }
     │           ├─ duration           DERIVED — never authored
     │           └─ provenance         which agent/human set what, when, why
     ├─ AssessmentItem[]  (objectiveId, bloomLevel, sceneRef{videoId, sceneId, tStart})
     ├─ Glossary          (term → definition → firstIntroducedSceneRef)
     └─ ReviewSchedule    (uniform-lag spaced review; §9.5)
```

### 5.2 Non-negotiable modelling rules

Each of these is derived from a specific failure mode. Violating any one of them breaks a downstream capability.

**R1 — Store durations, never absolute timeline positions.**
A scene renders to `[0, duration)` in its own local time. Absolute offsets are computed in a *timing resolution pass* before render. If absolute start time enters the cache key, every upstream edit invalidates everything downstream and the cache is worthless. **This is the single highest-leverage detail in the architecture.**

**R2 — Time is rational, never float.**
Steal OTIO's `RationalTime` (integer value + integer rate). Never store seconds as a float; never store a frame count without its rate. This eliminates an entire class of drift bugs. Use **integer fps (30) and 48 kHz** — 30 fps × 48 kHz = exactly 1600 samples/frame. 29.97 gives 1601.6 and guarantees accumulating drift across 40 scenes.

**R3 — Every animation cue anchors to a narration span ID, never a timestamp.**

```jsonc
// WRONG — breaks in every locale, and on every script edit
{ "highlight": "term-A", "at": 4.2 }

// RIGHT — resolves per-locale from that locale's word alignment
{ "highlight": "term-A", "anchor": { "spanId": "s12-w3" }, "offset": -0.1 }
```

Translation preserves span IDs (translators receive a segmented, ID-tagged script — XLIFF 2.x — not free prose). The timing resolver maps span IDs to per-locale word timings. **This decision must be made before a single line of animation code is written.** Retrofitting it is a rewrite.

**R4 — Narration text is segmented into spans at authoring time.** Spans are the join key between script, audio, captions, cues and translations. A span is roughly a clause.

**R5 — Duration is derived from TTS output, never authored.** Authors write words and intent; the system computes time.

**R6 — Every object carries provenance.** Which agent proposed it, which human accepted or overrode it, when, and why. This drives the "why did you do that?" affordance (Principle 3), the audit trail enterprises demand, and the training signal for §17.

**R7 — Assets are content-addressed and immutable.** `assetId = sha256(bytes)`. Deduplicates across courses for free.

**R8 — The scene graph must be renderer-agnostic.** No engine-native constructs in the schema. Remotion is a compiler backend; Revideo or a WebCodecs pipeline must be swappable without a schema migration. This is your exit option against Remotion's per-render licensing (§11.5).

### 5.3 Objective schema and validation

```jsonc
Objective {
  id, verb,            // from a Bloom verb whitelist
  object, condition, criterion,
  bloomLevel,          // remember | understand | apply | analyze | evaluate | create
  knowledgeType,       // factual | conceptual | procedural | metacognitive
  prerequisiteObjectiveIds[]
}
```

Hard validation, enforced at generation time:

- **Reject non-observable verbs**: understand, know, learn, appreciate, be familiar with, be aware of. Force a measurable substitute.
- **Constructive alignment:** every objective must have ≥1 assessment item at the *same* Bloom level. The most common real-world ID failure is Apply-level objectives assessed by Remember-level MCQs. The engine refuses to ship this.
- Every video maps to **1–2 objectives**; every scene maps to **exactly one**.
- `prerequisiteObjectiveIds` form a DAG → topological sort **derives course order**. A video may not depend on an objective taught later. Cycle detection is a hard error.

The prerequisite DAG doubles as the course-sequencing algorithm *and* mirrors the render DAG structurally — the same invalidation machinery serves both.

---

## 6. End-to-end user journey

Mapping your four stages onto the system.

### Stage 1 — Intake

**Inputs:** course title and description; source material (docs, PDF, slides, URLs, existing video, or nothing but a prompt); audience (level, prior knowledge, native-language mix, role); target length per video and course; language(s); brand kit; template family; tone; reference/sample video (optional, §17.3).

**Design notes:**
- Ask for **audience prior knowledge** explicitly. It drives the expertise-reversal adaptation (§9.3) and it is the input every competitor omits.
- Ask for **native-language ratio**. It flips the on-screen-text rules (§9.4).
- The intake form is short by default with progressive disclosure. Every field has a defensible default; nothing blocks generation.
- **Output of this stage is a Course Brief object**, itself editable and versioned. Regenerating from an edited brief is a first-class operation.

### Stage 2 — Curriculum and script

Not one step. Four, each independently inspectable and re-runnable:

**2a. Objective extraction** → the objective DAG. *The user reviews and edits this before anything else is generated.* This is the highest-leverage review point in the entire product and must not be skipped or buried — a wrong objective graph poisons everything downstream, and it is cheap to fix here and expensive to fix later.

**2b. Curriculum planning** → modules and videos, mapped to objectives, sequenced by the DAG, with per-video duration budgets.

**2c. Script generation** — per video, using the Gagné 9-slot template (§9.1) with typed slots. Each slot has a duration budget and a treatment rule. *This converts open-ended generation into constrained slot-filling, which LLMs do dramatically more reliably.*

**2d. Verification** — fact-check, citation, terminology, redundancy-against-course-memory, readability, tone. §19.

**Script types** (your "many types of scripts"): implemented as **slot-template variants**, not separate prompts — Explainer, Worked Example, Case Study, Compare-Contrast, Procedure/Demo, Story/Scenario, Myth-Busting, Interview/Dialogue, Review/Recap. Each is a different arrangement and weighting of the same nine typed slots. This keeps them all subject to the same linter.

### Stage 3 — Storyboard

The heart of the product. §10 covers the control surface in detail.

The planner assigns, per scene: visual template, element treatment, animation vs static-with-reveal, signal cues anchored to narration spans, asset requirements (stock / generated / diagram / screen capture / avatar), and brand application. Every decision is annotated with its rationale and the rule that produced it.

The linter then runs (§9.6). **Scenes that fail hard checks do not render.** They surface as blocking issues with a one-click fix proposal.

### Stage 4 — Render

Preview-first, always. Draft-tier generation and low-res render for approval, then selective high-quality re-render of approved scenes only. This roughly halves effective generative cost (§21.2) and is also better UX.

Chunked, cached, DAG-invalidated. §11.

### Stage 5 — Maintain (the stage nobody else has)

Edit any scene from chat or direct manipulation. Change propagates through the DAG; only genuinely affected scenes re-render. Course memory updates. Downstream videos that referenced changed content are **flagged for review, not silently regenerated** — silent cascade regeneration is a trust-destroying behaviour.

---

## 7. Agent architecture

You asked for "many agents at each and every level to verify everything." Right instinct; needs discipline. Unstructured agent swarms produce plausible mush and unbounded cost. The structure below is a **DAG of typed agents with schema'd handoffs and explicit verification gates.**

### 7.1 Design rules for the agent layer

1. **Every agent has a typed output schema.** No free-text handoffs between agents. Validation failure → retry with the error, max 2 retries, then escalate to human.
2. **Verifiers are adversarial and separate from generators.** A verifier's job is to *refute*. Never let a generator grade its own work.
3. **Verification is proportional to blast radius.** Objective graph errors poison a whole course → 3 independent verifiers. A single scene's colour choice → 1 cheap check.
4. **Deterministic checks beat agentic checks.** Contrast ratio, text density, word count, flash rate, glyph coverage, cycle detection — all code, not LLM. Reserve agents for judgment.
5. **Budget per stage.** Agent cost is 1–2% of COGS, so this is about latency and quality, not money. But an unbounded retry loop is an unbounded latency loop.

### 7.2 The agent map

**Tier 0 — Orchestrator.** Owns the pipeline DAG, retry policy, human-in-loop gates, cost/latency budget, and the provenance log.

**Tier 1 — Curriculum**
- *Objective Extractor* → objective DAG
- *Prerequisite Mapper* → edges + topological order
- *Curriculum Planner* → modules, videos, duration budgets
- ✅ *Objective Verifier* ×3 (independent lenses: measurability/Bloom-verb compliance; DAG acyclicity + coverage of source material; assessment alignment)

**Tier 2 — Script**
- *Script Writer* (slot-filling against Gagné template)
- *Hook Specialist* (first 15s; disproportionate impact on completion)
- *Analogy/Example Generator*
- ✅ *Fact Checker* — claims extracted, each independently verified with sources, confidence scored. Anything below threshold gets flagged in the UI, never silently kept.
- ✅ *Redundancy Checker* — against **CourseMemory**, not just within the video (§12)
- ✅ *Tone/Brand Checker* — against BrandKit lexicon and banned terms
- ✅ *Readability Gate* — deterministic: Flesch-Kincaid ≤ 9 general / ≤ 11 technical; passive voice ≤ 20%

**Tier 3 — Storyboard**
- *Visual Planner* — template + treatment per scene
- *Signal Designer* — cue placement anchored to spans
- *Asset Director* — decides generate vs stock vs diagram vs screen-capture vs avatar, and writes the generation prompts
- *Motion Designer* — animation vs static-with-reveal; timing envelopes
- ✅ *Pedagogy Linter* — mostly deterministic (§9.6)
- ✅ *Accessibility Linter* — deterministic (§16)
- ✅ *Brand Compliance Checker* — deterministic where possible

**Tier 4 — Asset**
- *Prompt Engineer* (per target model, with model-specific prompt shaping)
- *Asset Generator* (routes to image/video/TTS providers)
- ✅ *Asset QA* — does the returned asset match the request? Character/style consistency? Artifacts? Text-in-image errors? **This is the agent that controls your reroll rate and therefore your COGS.** It is the single highest-ROI agent in the system.

**Tier 5 — Assembly**
- *Timing Resolver* (span alignment → absolute timing, per locale)
- *Caption Generator*
- *Render Orchestrator* (DAG walk, cache lookup, dispatch)
- ✅ *Frame QA* — post-render deterministic checks: contrast on actual rendered frames, flash rate, caption-safe-area occlusion, tofu-glyph detection

**Tier 6 — Course-level**
- *Continuity Agent* — cross-video coherence, callbacks, term consistency
- *Assessment Designer* — items aligned to objectives at matching Bloom level
- *Localisation Agent* — per-locale span-preserving translation + layout reflow
- ✅ *Course Reviewer* — whole-course pass: sequencing, coverage gaps, pacing, redundancy, difficulty curve

### 7.3 Human-in-the-loop gates

Three mandatory (skippable only by explicit setting), everything else optional:

1. **Objective graph approval** — before any script is written
2. **Script approval** — before any asset is generated (assets are where the money goes)
3. **Storyboard approval** — before high-quality render

Everything after that is direct manipulation, not approval.

---

## 8. Course intelligence layer — what the AI actually decides

You asked that AI decide what elements appear, what gets highlighted, how it relates to brand, and where animation goes. Here is the decision list, made explicit so it can be tested, tuned and overridden.

| Decision | Driven by | Overridable at |
|---|---|---|
| Number of videos, and their boundaries | Objective DAG + 6-min cap; split at objective boundaries, never mid-explanation | Curriculum view |
| Script type per video | Bloom level + knowledge type (procedural → Procedure/Demo; conceptual → Explainer/Compare) | Per video |
| Scene count and slot allocation | Gagné template + duration budget + element interactivity | Per video |
| Visual template per scene | Bloom level + content type (see table §9.1) | Per scene |
| Animate vs static-with-reveal | **Does the referent genuinely change over time?** If no → static + progressive reveal | Per scene |
| What gets highlighted, and when | Signal Designer, anchored to narration spans, ±150 ms | Per cue |
| On-screen text content | Abridged near-paraphrase, ≤20% of narration word count (§9.4) | Per element |
| Brand colour application | Semantic roles (`accent-signal`, `surface`, `bg`), not literal palette slots — see below | BrandKit |
| Stock vs generated vs diagram | Asset Director: real-world referent → stock; abstract concept → diagram; illustrative scene → generated | Per asset |
| Avatar presence | Off by default; on for hook/outro if brand requires; **auto-hidden during any diagram or code scene** | Per scene |
| Pacing / speaking rate | Modulated by element interactivity: 135–160 wpm for dense explanation, up to 185 for narrative | Per scene |
| Assessment placement and type | Objective Bloom level + segment boundaries | Per item |

**On brand colours — a detail that matters more than it looks.** Do not map brand palettes literally onto scene elements. Map them to **semantic roles**, and let the theme resolver satisfy contrast constraints. A brand whose primary is a mid-grey cannot use it as the signal colour and pass WCAG 4.5:1 against a light surface. The resolver derives a compliant accent from the brand hue, preserving identity while guaranteeing legibility. This is exactly the kind of thing that makes output look professional versus look like a template with the wrong colours pasted in.

---

## 9. The pedagogy engine

This is Wedge C. It is what separates a course engine from a video generator, and — usefully — it is cheap to build relative to its differentiating power.

### 9.1 The scaffold

```
COURSE   ← Merrill: anchor in a real-world problem
  MODULE ← Merrill cycle: Activation → Demonstration → Application → Integration
    VIDEO ← Gagné's Nine Events as a typed slot template:
              1 hook          ≤15s   gain attention
              2 objective     ≤10s   stated verbatim; reused as the scene title
              3 recall        ≤20s   link to a prior objective BY ID (course memory)
              4 present       60–120s chunks, Mayer rules apply
              5 guidance      signalling, worked example, analogy
              6 elicit        pause-and-do prompt
              7 feedback      reveal + explanation
              8 assess        linked assessment item, SAME Bloom level
              9 retain        summary + spaced-review scheduling hook
      SCENE ← Mayer's 12 principles + CLT thresholds, as a LINTER
```

**Why Gagné as the scene template is the key move:** it converts "write a storyboard" from open-ended generation into **slot-filling with typed slots**, each with its own duration budget, visual treatment rule and validation. This is the difference between reliably good LLM output and occasionally good LLM output. ADDIE and SAM are project lifecycles, not content structures — they map to the *product's pipeline*, not to the content.

Visual treatment selected by Bloom level, not by aesthetics:

| Cognitive process | Video treatment |
|---|---|
| Remember | Definition scene, term card, mnemonic |
| Understand | Animated explanation, analogy, contrast pair |
| Apply | Worked example → faded example → practice |
| Analyze | Case walkthrough, compare/contrast, error hunt |
| Evaluate | Trade-off discussion, decision framework |
| Create | Project brief, scaffolded build |

### 9.2 Mayer's principles as enforceable rules

Each rule below has a threshold because a rule without a threshold is a vibe.

**Coherence** *(strongest, most reliable effect)*
> Reject: background music under narration (music permitted only in silent intros/outros/transitions); decorative imagery with no referent; any visual element not named or pointed at by the script within ±3 s; "fun fact" asides. Compute `relevanceScore = (elements with a narration referent) / (total elements)`. **Fail below 0.85.**

**Signalling**
> Every scene contains **1–3** signalling events. Never zero, never more than 3 concurrent. Permitted signals: colour highlight, arrow/pointer, scale-pulse (≤120%, ≤400 ms), dimming of non-focal regions to ~40% opacity. **Onset time-locked to the narration word within ±150 ms** — early beats late.

**Redundancy** — see §9.4, it is more nuanced than the slogan.

**Spatial contiguity**
> A label sits within **≤5% of frame width** of its referent, or is connected by an explicit leader line. Ban legends and keys — inline the labels. Ban sidebar text referring to a main-area diagram.

**Temporal contiguity**
> An animation depicting concept X starts within **±0.5 s** of the narration mentioning X. Enforced automatically from word-level alignment. Never "narrate, then animate."

**Segmenting**
> Video length **hard cap 6:00**, target 3–5. Explicit segment boundary every **60–120 s** or at each conceptual unit, whichever is shorter. Emit chapter markers to WebVTT and the player.

**Pre-training**
> If a scene introduces **≥3 new technical terms**, the planner must emit a preceding vocabulary scene (name + one-line characteristic + icon). A per-course term registry enforces that a term's *first* appearance anywhere is a definition, and drives glossary generation.

**Modality**
> Explanation is **always narrated**, never delivered as on-screen prose to be read. Ban walls of bullets. Exception: code, formulas, and high-technical-vocabulary or non-native contexts get full on-screen text with narration that *talks around* rather than reads.

**Multimedia**
> No scene may be narration over a blank or static title for **>8 s**. Every scene has a visual spec. This rule alone forbids the default output of most competitors.

**Personalisation** *(replicated strongly)*
> Second person, contractions, active voice. **Flesch-Kincaid ≤ 9** general / **≤ 11** technical. Passive voice **≤ 20%**. Reject institutional third person ("the learner will…", "one should note").

**Voice** *(did NOT replicate)*
> Natural-prosody neural TTS by default; **do not** default to human VO. Enforce prosody gates: speaking rate, ≥600 ms pause at segment boundaries, sentence-level pitch variation. Human VO is an upsell, not a requirement. *A/B this.*

**Embodiment / Image** *(did NOT replicate)*
> **Default: no talking head.** If a presenter is required, constrain to PiP ≤20% of frame and require gaze/gesture directed at the content — embodiment, not mere presence, is the active ingredient. **Auto-hide the presenter during any scene containing a diagram or code.**

**Generative activity** *(among the strongest replicating effects)*
> Every video ends with at least one generative prompt: pause-and-predict, "explain this in your own words," or a retrieval question. **Non-optional in the template.** Likely higher ROI than any visual polish in the product.

### 9.3 Cognitive load thresholds

| Dimension | Rule |
|---|---|
| New interacting elements per scene | **≤4**. More → planner must decompose into an isolated-elements → interacting-elements sequence |
| Simultaneous on-screen objects | **≤7**; **≤4** if any carry text |
| On-screen text density | **≤25–30 words** visible at once; **≤6 words per line** for emphasis; **≤3** simultaneous text elements |
| Speaking rate | **135–160 wpm** technical; up to **185 wpm** narrative/review. Modulate by element interactivity |
| Settling beat | **≥1.5 s** of silence with the visual held after each new concept |
| Simultaneous change budget | Never animate >2 properties of >2 objects at once |
| Expertise adaptation | At `audience.expertise = expert`: strip pre-training scenes, reduce signalling density, shorten worked examples to faded/completion problems |

That last row implements the **expertise reversal effect** — scaffolding that helps novices actively harms experts. No competitor models this.

### 9.4 The redundancy rule — the most differentiated decision in the product

The industry gets this wrong in both directions. The evidence (Yue, Bjork & Bjork 2013; 253-second lesson, ~500 words, system-paced, proportion correct):

| Condition | Recall | Transfer |
|---|---|---|
| Narration only, no animation | .11 | .27 |
| **Identical** full on-screen text + narration | .25 | .36 |
| Control: animation + narration, no text | .33 | .34 |
| **Far-change** (very different wording) | .28 | .30 |
| **Near-change** (slight synonym substitution) | **.40** | **.49** |
| **Abridged** (key phrases only) | **.39** | **.50** |

Four findings that should shape the engine:

1. **Identical full text + narration is worse than no text at all** for recall (.25 vs .33). The classic redundancy effect, replicated.
2. **Abridged key-phrase text is the best condition** (.39/.50) and beats no-text substantially. *On-screen text is not the problem; verbatim complete on-screen text is the problem.*
3. **Slight discrepancy helps.** Near-change (.40/.49) matches abridged. Minor mismatch forces comparison — a desirable difficulty.
4. **Too much discrepancy hurts as much as identical** (.28/.30). There is a sweet spot.

And the finding that should shape your *research process*: learners **preferred** the identical-text condition despite performing worst with it. Fluency during learning misleads. **User satisfaction surveys will push you toward the pedagogically worse design.** Instrument learning outcomes, not preference (§20.3).

**Engine rule:**

```
IF the scene has an animation/diagram (visual channel occupied):
    on_screen_text = ABRIDGED key phrases, ≤20% of narration word count
    PREFER NEAR-PARAPHRASE over verbatim extraction     ← counterintuitive, evidence-backed
    NEVER render a full narration sentence
ELSE IF the scene is code / formula / data table / proper nouns:
    on_screen_text = the artifact at full fidelity
    narration TALKS ABOUT it; does not read it verbatim
ELSE IF audience.nonNativeRatio > threshold OR content.termDensity is high:
    permit fuller on-screen text; captions default ON
ALWAYS:
    captions available as a LEARNER-TOGGLED track
    default caption state: OFF for native-audience, ON for localised/technical
```

Implementation detail that matters: generate the on-screen phrase **from the concept, not by substring-extracting the narration**, then verify `0.3 < semantic_similarity < 0.85` — inside the sweet spot between "identical" and "far-change." This is a genuinely novel, evidence-grounded behaviour that no competitor has, and it is nearly free to implement.

### 9.5 Retrieval, spacing and interleaving

Effect sizes (Latimier, Peyre & Ramus 2021): spaced vs massed retrieval practice **g = 1.01** unadjusted, **g = 0.74** after publication-bias correction. That is very large for education research. Expanding vs uniform spacing schedules: **g = 0.034, p = .59 — no difference.**

**That second number saves you months of engineering.** You do not need SM-2, Anki-style adaptive scheduling, or a half-life regression model. **Fixed uniform lags capture essentially the entire effect.** Build the simple thing.

```
PER VIDEO
  1 pre-question before the explanation (pretesting; also drives attention)
  1–2 embedded retrieval checks at segment boundaries (free recall > MCQ where gradeable)
  1 end-of-video summary that is LEARNER-GENERATED (prompted), not engine-narrated

PER MODULE (3–6 videos)
  a mixed quiz drawing from ALL videos in the module (interleaving)
  explicitly DO NOT block by video — shuffle across objectives

PER COURSE
  uniform-lag spaced review: +1 day, +7 days, +21 days
  every review item is CONTENT-ADDRESSED to a scene → deep-links to timestamp playback
  interleave across modules in later reviews
```

That last line is where the chunk architecture pays a pedagogical dividend: **a missed question links to the exact 40 seconds that taught it.** Every assessment item carries `sceneRef {videoId, sceneId, tStart}`. Nearly free given the data model, and impossible for a competitor whose artifact is an MP4.

### 9.6 The linter

Runs at storyboard time, before any expensive generation. Split by enforcement type:

**Deterministic (code, fast, free)** — text density, word counts, element counts, contrast ratios, cue count per scene, video duration, term-registry violations, readability, passive-voice ratio, objective-assessment Bloom alignment, DAG acyclicity, glyph coverage, caption safe area.

**Model-based (agentic, slower)** — relevance scoring (does every visual have a narration referent?), semantic-similarity band for on-screen text, analogy quality, hook strength, factual confidence.

**Severity model:**
- **Blocking** — will not render. Contrast failure, missing glyph, Bloom misalignment, DAG cycle, flash-rate violation, coherence score < 0.85.
- **Warning** — renders, flagged in the report. Duration overrun, high element count, weak hook.
- **Advisory** — logged for the learning loop (§17).

**Ship the report to the customer.** A pedagogy score with itemised, cited rationale is a sales asset for an EdTech buyer who has to defend content quality to their own customers. No competitor can produce one.

---

## 10. Storyboard and control surface

You said: "AI will decide everything but we should have full control over how the content is coming on the screen." That is exactly right, and the design problem is that these two goals fight unless the granularity of control matches the granularity of the AI's decisions.

**Principle: every AI decision is a named, addressable, overridable object.** Not "regenerate the scene" — but "change this cue's timing," "swap this asset," "make this static instead of animated," "this term should not be highlighted."

### 10.1 Three coordinated views

**A. Course view** — objective DAG, module/video sequence, coverage map, pedagogy scorecard, per-video status and cost. Drag to reorder (which, per R1, invalidates nothing but the manifest). This is the instructional designer's home.

**B. Storyboard view** — scene strip with thumbnails, narration, slot type, duration, cue markers, and per-scene status/cost. The primary working surface. Inline editing of narration; scene split/merge/reorder; per-scene lock ("pin/bake" — never re-render this even if the theme changes, borrowed from Nuke's explicit disk-cache nodes).

**C. Scene view** — canvas + timeline. Direct manipulation of elements, cues anchored to narration words (visible as markers *on the words*, not on a time ruler — this is the UI expression of R3 and it makes the anchoring model legible to users), asset swap, treatment toggle.

### 10.2 The chat control layer

Chat is a **command surface over the graph**, not a separate creative channel. Critical design decisions:

1. **Chat operates on the current selection.** "Make this punchier" with a scene selected is unambiguous. Without a selection it asks. Scope disambiguation is the main failure mode of chat editing and most tools ignore it.
2. **Chat emits a diff, not a result.** The user sees exactly what will change before it commits: `Scene 7: narration span 3 rewritten · cue 'depreciation' retimed +0.2s · asset unchanged · re-render cost: 1 scene`.
3. **Every chat action is undoable at graph granularity.**
4. **Chat can operate at any level:** "make the whole course more conversational" (course-level), "shorten module 2" (module), "this scene is too dense" (scene), "highlight the second bullet instead" (element).
5. **The system pushes back.** "I can add background music under narration, but it violates the coherence principle and typically hurts retention. Want me to do it anyway, or add it to the intro only?" — enforcing Principle 6 without being obstructive. Always offer the compliant alternative.

**Bidirectional:** the AI raises issues in the same thread. "Scene 12 introduces four new terms with no pre-training scene. Want me to add one?"

### 10.3 Interaction budget — the real UX metric

Track **time-to-acceptable-course**, not time-to-first-generation. Every competitor optimises the latter and that is why Google Vids needs 60–70% manual rework and still markets as instant.

Target: **≤ 15 minutes of human interaction per finished 5-minute video** at steady state, including review. Instrument this from day one; it is your true north.

---

## 11. Chunked rendering architecture

This is Wedge B and the load-bearing engineering.

### 11.1 The model — borrow from Bazel, not from NLEs

The best prior art is **Bazel's action cache and remote execution**, not video tooling.

| Bazel | Sequence |
|---|---|
| Action | Render one scene component to an intermediate |
| Action key = hash(command + input digests + env + toolchain) | `sceneKey = H(sceneSpec_canonical ‖ H(assets) ‖ H(theme) ‖ rendererVersion ‖ codecParams ‖ fps ‖ resolution)` |
| Merkle tree of inputs | Recursive hash over the scene subtree — nested asset changes propagate upward automatically |
| Action Cache + CAS | `sceneKey → {mp4Digest, wavDigest, durationFrames, captionsDigest}` and `digest → object storage`. **Deduplicates identical scenes across different courses for free.** |
| Hermeticity | The hard requirement. Any nondeterminism = cache poisoning. |

### 11.2 Component-level invalidation — borrow from Blender

Blender's dependency graph splits an object into Transform / Geometry / Shading components so a transform change doesn't invalidate geometry. Do the same: split a scene into **Audio / Layout / Motion / Captions** components.

```
narration.text     → invalidate: TTS, alignment, captions, duration, motion timing,
                                  layout (if text-driven), pixels
narration.voiceId  → invalidate: TTS, alignment, captions*, duration, motion timing, pixels
visualSpec.slots.* → invalidate: layout, pixels
theme.*            → invalidate: layout, pixels   (NOT audio, NOT alignment)  ← the big win
scene ordering     → invalidate: NOTHING at scene level; manifest/stitch only  ← the other big win
transition[i]      → invalidate: that transition + tail of scene i + head of scene i+1
rendererVersion    → invalidate: all pixels; audio survives
```

The theme row means a brand colour change across a 40-video course **does not re-run a single TTS call**. The ordering row means reordering scenes costs a manifest rewrite and one concat.

Blender's other two lessons worth stealing: **copy-on-write evaluation** (immutable scene-graph versions, so a preview render and a final render of different revisions coexist without locking) and **two-phase tag-then-flush** (resolve all durations/timing globally first, *then* render pixels — never interleave, because durations cascade).

And the anti-pattern, from After Effects: **coarse invalidation granularity destroys the value of caching.** AE's notorious failure is that touching a comp-level property nukes the whole cache. Design edge granularity before you write the cache.

### 11.3 Hermeticity checklist

Every item here has bitten someone in production:

- `Math.random()`, `Date.now()`, `new Date()` → seed a PRNG from `sceneId`; inject a fixed clock
- Font loading races → embed as base64 or pin via a fully-resolved `document.fonts.ready`
- **Network fetches at render time → forbidden.** All assets resolved to content-addressed local paths before render
- Chromium / FFmpeg / codec versions → **part of the cache key**. A libx264 bump changes bytes
- GPU vs CPU rasterisation → pin, or key on it explicitly
- Floating-point layout drift across CPU architectures → key on architecture, or accept perceptual-hash equality rather than bit equality

**Verification:** periodically render the same scene twice on different workers and compare digests. Alarm on mismatch. This catches nondeterminism *before* it corrupts the cache — and a corrupted cache is a class of bug that will otherwise take weeks to diagnose.

### 11.4 A/V sync — the hardest correctness problem

**Problem: narration length changes shift everything downstream.**
Solved by R1 + two-phase evaluation. Scene renders are position-independent; the cache key must not include absolute start time.

**Problem: sample-accurate concatenation.**
- Force **integer frame counts** for every scene duration. Pad TTS audio with silence to `ceil(samples / samplesPerFrame) × samplesPerFrame`
- **30 fps + 48 kHz = exactly 1600 samples/frame.** Accept 29.97 only under a broadcast delivery contract
- Render intermediates as **lossless/intra-only** (ProRes or MJPEG/FFV1 + PCM), concat with `-c copy`, then a **single final encode**. Never concat lossy inter-frame chunks — GOP-boundary artifacts and timestamp fights
- Explicitly reset PTS at concat; use the concat *demuxer* with a manifest, not the concat *filter* (which re-encodes)

**Problem: transitions cross chunk boundaries.**
A crossfade between scenes 3 and 4 is a function of both, so it isn't cacheable under either key. **Model transitions as first-class DAG nodes** with **handle frames** (extra T frames beyond nominal duration, exactly like VFX handles):

```
Transition(i, i+1) = f(tail(scene_i, T), head(scene_{i+1}, T), spec)
key = H(sceneKey_i, sceneKey_{i+1}, spec, T)
```

Editing scene 5's text then invalidates scene 5, transition(4,5), transition(5,6). Three renders, not forty.

**Prefer hard cuts by default** — pedagogically supported (coherence: fancy transitions are extraneous processing) *and* architecturally cheaper. Offer dissolves only at module boundaries, where they usefully signal segmentation.

**Problem: continuous audio beds.**
Music spanning the video is a global dependency that would invalidate on any duration change. **Render music as a full-length stem, mix at stitch time.** Music never enters a scene's cache key. Same for persistent lower-thirds and progress bars — or better, make those **player-side chrome rather than burned pixels.**

**The stitch manifest** is itself content-addressed: `H(ordered sceneKeys + transitionKeys + audioStemKeys + encodeParams)`. "Did anything change?" is one hash comparison, and two courses sharing an intro dedupe for free.

### 11.5 Renderer selection and the licensing trap

**Recommendation: Remotion for the authoring/layout layer, FFmpeg for stitching, with Revideo and Diffusion Studio (`@diffusionstudio/core`, MPL-2.0) documented as escape hatches.** R8 keeps the escape hatch real.

Remotion is React rendered to video: compositions are pure functions of `(frame, props)` — exactly the property content-addressed caching needs. Its ecosystem, DOM typography and layout are genuinely hard to replicate.

**But read the licence carefully, because it is pointed against this architecture:**

| Tier | Trigger | Price |
|---|---|---|
| Free | Individuals, teams ≤3 people, non-profits | $0 |
| **Remotion for Automators** | 4+ people, automated pipelines serving end users | **$0.01 per render, $100/mo minimum** |
| Remotion for Creators | 4+ people, low-volume human-driven | $25/mo per seat |
| Enterprise | Custom terms | from $500/mo |

Critical details: **"1 render" includes still images** — every thumbnail, quiz card and poster frame is billable. Team size **aggregates across contractors and agencies**. There is **no revenue threshold** — it is purely headcount plus volume. From v5.0, telemetry via `licenseKey` is mandatory, so non-compliance is technically detectable.

Sequence is unambiguously "Remotion for Automators," and **per-render pricing is structurally misaligned with fine-grained scene re-rendering** — the exact thing that makes the product good. A 30-video course at 8 scenes = ~240 scene renders plus ~240 stills ≈ $4.80 for a first pass, which is trivial. But an iterative product could plausibly do 50–100× that per course.

Mitigations, in order: (a) **debounce re-renders** — one render per scene per commit, not per keystroke; (b) negotiate Enterprise early, where the $500/mo floor with custom terms almost certainly beats $0.01 × millions; (c) keep R8 credible so the escape hatch has leverage in that negotiation.

Compute is cheap either way: **Remotion Lambda from $0.01/min, realistically $0.03–0.05/min** including cold starts and egress. Editframe is ~$0.02/min. Shotstack at $0.20–0.30/min is 5–10× more but removes the orchestration build — **plausibly the right pre-PMF trade**, with a migration to owned rendering once volume justifies it. Note Shotstack caps at 1080p below a 50,000 min/yr commitment.

### 11.6 Delivery — align chunks to segments

Package once with **CMAF** (fMP4), serve both HLS and DASH manifests over shared segments. Segment duration 4 s. Skip low-latency variants entirely — irrelevant for VOD.

**Deliberately align scene boundaries to segment boundaries.** Force an IDR/keyframe at every scene start; set scene durations to multiples of segment duration where feasible. Then:

- **Patch-level publishing:** fixing scene 7 re-uploads 2–3 segments and rewrites the manifest — not the whole video
- **Deep-linkable concepts:** `#t=` into an exact scene, driving the assessment→scene links from §9.5
- **Localisation:** swap only the audio rendition per language where the video layer is shared (§15.3)
- **Analytics:** xAPI `played-segments` maps cleanly onto scene IDs (§18.2)

**Manifest versioning:** treat manifests as immutable and content-addressed (`/v/{manifestHash}/index.m3u8`) with a mutable course-level pointer. Every segment and manifest gets `immutable, max-age=31536000`; publishing a fix flips one small pointer object. **No cache-invalidation storms, ever.**

Codec note: course content is mostly flat graphics, text and screen capture — the ideal case for aggressive encoding. But aggressive encoding destroys small text via ringing, so enforce **≥24 px minimum font at 1080p**, which the CLT density rules already push you toward.

---

## 12. Course memory — the differentiator

Wedge A. This is why the product is a course engine and not a video generator.

### 12.1 What it stores

```jsonc
CourseMemory {
  objectivesTaught:   [{ objectiveId, videoId, sceneId, bloomLevel, timestamp }],
  termRegistry:       [{ term, definition, firstIntroducedRef, usageCount, aliases[] }],
  analogiesUsed:      [{ concept, analogy, sceneRef, embedding }],
  visualMetaphors:    [{ concept, template, colourRole, sceneRef }],
  examplesUsed:       [{ domain, entities[], sceneRef }],
  narrativeThreads:   [{ threadId, description, appearances[sceneRef] }],
  assertions:         [{ claim, sourceRefs[], confidence, sceneRef }],
  difficultyCurve:    [{ videoId, elementInteractivityScore, newTermCount }],
  learnerSignals:     [{ sceneId, dropOffRate, rewatchRate, itemAccuracy }]   // Phase 3
}
```

### 12.2 What it does

**Prevents re-teaching.** Before writing video N, the Continuity Agent queries: which objectives are already taught? Which terms already defined? A term defined in video 2 is *used* in video 7, not redefined. If it is high-value and 5+ videos back, a one-clause reminder — not a definition scene.

**Enables real callbacks.** "Remember the pipeline diagram from module 1? We're adding a stage." Backed by a real `sceneRef`, so the player can offer an inline jump-back — a feature that only exists because scenes are addressable.

**Prevents analogy collision.** Storing analogy embeddings means video 9 doesn't reach for the same "it's like a library card catalogue" that video 3 used, and — more subtly — doesn't reuse the same analogy for a *different* concept, which is actively confusing.

**Maintains visual consistency.** If "data flow" was a blue left-to-right arrow chain in module 1, it stays that in module 4. This kind of consistency is what makes a course feel authored rather than assembled, and it's invisible when present and jarring when absent.

**Manages the difficulty curve.** Tracks element interactivity and new-term count per video. Flags spikes: "Video 6 introduces 11 new terms; the course average is 4. Split it?"

**Enables coherent regeneration — the killer capability.** Six months later you regenerate video 4. It is *still* conditioned on 1–3 and *still* consistent with 5–8, because the memory is durable and separate from any video file. **This is the thing no competitor can do**, because their one-shot generators discard the intermediate state, and their artifact is an MP4.

**Guards consistency on edit.** If you change a definition in video 2, the system finds every downstream dependency and flags them for review. **It does not silently regenerate them** — silent cascading regeneration destroys trust faster than any quality problem.

### 12.3 Implementation

Structured store (Postgres) for exact lookups (terms, objectives, refs) + vector store for semantic ones (analogies, examples, assertions). Memory is **versioned alongside the course graph**, so "what did the course know at the time video 5 was written?" is answerable — necessary for reproducible regeneration and for debugging continuity bugs.

**Scale note:** the memory is injected into agent context. For a 100-video course it will exceed a sensible context window. Build **retrieval over the memory from day one** (relevance-ranked slices per generation task), not naive full injection. Retrofitting retrieval after the fact is a rewrite of every prompt in the system.

---

## 13. Avatars

### 13.1 Position

Avatars are a **supported, non-default, isolated layer**. The evidence (§1.4) does not support making them the spine, and the architecture actively penalises it (§15.4). But buyers ask for them, some brands require a face, and hook/outro presence is a legitimate use.

### 13.2 Rules

- **Off by default.** On for hook and outro if the brand requires.
- **Auto-hidden during any scene containing a diagram, code, or dense visual.** (Embodiment rule + the eye-tracking finding that learners over-attend to faces at the expense of graphics.)
- **PiP ≤20% of frame** when co-present with content.
- **Rendered as an isolated compositing layer** — alpha/chroma-keyed, composited at stitch time. This is what keeps the rest of the frame shared across locales.
- Never the sole visual for >8 s (multimedia principle).

### 13.3 Vendor

**HeyGen.** Avatar III at **$1.00/min** (720p/1080p) is the best price-performance in the category; Avatar IV at $4.00/min for hero use. **Custom avatar creation is $1.00 per call** — versus **$1,000/year** at Synthesia and Colossyan, with up to 10 days' processing at Synthesia. That is not a marginal difference; it makes per-customer branded avatars economically trivial rather than an enterprise upsell.

Tavus ($40–65 per replica, $0.26–0.35/min conversational) is the right choice if and when you build interactive/conversational avatars — a Phase 4 question.

**Do not self-host.** MuseTalk (256×256, MIT) and LatentSync (512, Apache-2.0) are not competitive with Avatar III at $1.00/min once you price in GPU, engineering and quality-gate infrastructure. **Wav2Lip is a legal landmine** — the public checkpoint is research-only due to LRS2 training-data terms, and commercial use requires a separate contract with Sync Labs. A great many "open source lipsync" tutorials quietly ignore this. Revisit self-hosting only above ~10,000 min/month.

### 13.4 On "training the avatar so much that it brings more engagement"

Worth being direct: the evidence says this is the wrong place to invest. Embodiment and voice both failed to replicate; learners over-attend to faces at the cost of the content; and telling learners the instructor is synthetic drops trust sharply *with no change in learning outcomes*. Money spent making an avatar 10% more lifelike buys less than the same money spent on the pedagogy linter, the hook, or the retrieval prompts.

Build it well enough to satisfy buyers who require it. Don't build the company on it. And instrument it — if your own data contradicts the literature for your specific audience, that is a genuinely valuable finding and you'll be the only one who has it.

---

## 14. Asset sourcing and generation

### 14.1 The routing decision

The Asset Director picks per element, in this priority order:

1. **Rendered diagram/data-viz** — for anything abstract, structural or quantitative. Cheapest, most consistent, most on-brand, most accessible, fully deterministic, and *pedagogically superior* — text+diagram combinations performed most consistently in the 2025 meta-analysis, while animation/simulation effects were positive but unstable. **Default here.**
2. **Screen capture / synthetic UI** — for software training. This is the category Colossyan admits it cannot serve, and it is the largest single category of corporate training. A synthetic-UI renderer (deterministic, brandable, annotated) is a differentiator worth more than another avatar tier.
3. **Stock** — for real-world referents (people, places, objects) and, specifically, for the **hook / problem-framing** shot that grounds a concept before the animation explains it (§4.4). Source: **Storyblocks** (§14.3).
4. **Generated image / illustration** — for illustrative/conceptual scenes needing a specific look. Cheap and controllable. Source: **Freepik AI generation** on MSA terms (§14.3).
5. **Generated video** — for motion where motion is the point. **Expensive; use sparingly.** Sources: Veo / Kling / Freepik AI video, behind the swappable model interface (R7).

### 14.2 Generative model routing and the reroll problem

Current cost floor per minute of generated video (API rates, before rerolls):

| Tier | Model | $/min |
|---|---|---|
| Draft/preview | Hailuo 2.3 512p / Veo 3.1 Lite 720p | $0.60–3.00 |
| Production B-roll | Veo 3.1 Lite 1080p / Veo 3.1 Fast / Kling 3.0 | $3.00–7.20 |
| Hero shots | Veo 3.1 quality / Luma 1080p / Seedance 1080p | $14.40–36.00 |

**The reroll factor is your #1 margin lever**, larger than any vendor negotiation. Going from 2.5× to 1.5× rerolls saves ~$15 on a Tier-2 5-minute video and ~$30 on Tier 3. Concretely:

- **Draft-then-approve routing.** Generate on Lite, get storyboard approval, re-render only approved shots at Fast/quality. Roughly halves effective cost.
- **Asset QA agent** (§7.2 Tier 4) is the highest-ROI agent in the system.
- **Reference-image conditioning** for character/style consistency: generate reference sheets with Gemini 3.1 Flash Image (~$0.067/image), feed them to Veo image-to-video (accepts up to 3 reference images). Same references across shots = the cleanest character-consistency story currently available.
- **Cache aggressively** — generated assets are content-addressed and reusable across scenes, videos and courses.

**Structural constraint to design around:** Veo clips are **4/6/8 seconds only**. 300 s of fully generative video is ~38 separate generations, each an independent chance at continuity failure. Fully-generative long-form is a *quality* problem before it is a cost problem. Do not build the product's default on it.

**Vendor note:** OpenAI has exited video generation. The Sora product was killed 26 April 2026 and the **Sora API shuts down 24 September 2026** with no listed replacement. Do not build on Sora. Runway is now largely a router reselling third-party models. Assume this churn continues — **the model layer must be swappable behind an internal interface**, with per-model prompt shaping as a plugin.

Also unresolved: Google no longer publishes Veo RPM/daily quotas — they're gated per usage tier. **Request a quota increase before launch**, not after.

### 14.3 Stock and generated-media sourcing — read this before writing any code

This is where an AI video SaaS gets sued. The question is never "may I use this clip" — it is **"may I bake this asset into a video and hand it to my paying end users, automatically, at scale?"** That is *multi-tenant redistribution inside an automated product*, and most stock APIs prohibit it. Verified against current terms, August 2026.

#### The two use-cases, mapped to sources

Per §4.4, we need media for two jobs, and they route to different sources:

| Need | Source | Why |
|---|---|---|
| **Hook / real-world "here's the problem" footage** (people, places, situations) | **Storyblocks** (buy the partner deal) | The only vendor with explicit SaaS redistribution rights *and* indemnification for real stock footage |
| **Illustrations & generated B-roll** (abstract/conceptual, specific look) | **Freepik — AI-generation output** (on Enterprise-MSA terms) | Under the MSA you own the Output and can commercialise it; good pricing; access already held |
| **Diagrams, kinetic type, data viz, screen demos** | **Own engine (Remotion)** | Deterministic, on-brand, free, most accessible, pedagogically strongest — the default |

#### Vendor-by-vendor

**✅ Storyblocks — the correct answer for real footage.** Explicitly built for this: partners monetise its content inside their own platform. 100% royalty-free, worldwide distribution, **$20,000 indemnification per asset**, **unlimited search and download API calls**, and a flat fee scaled by library count and monthly active users — not per-download, not rev-share. Existing API partners include Pictory and Lumen5 — direct precedent for exactly this product.

> **Hard constraint from their terms:** you may not distribute or resell **source files** on a stand-alone basis; content must be incorporated into a finished project. **Therefore: never expose a raw asset download button.** Stock assets may only leave the system baked into a rendered video. Enforce this in code, not policy — a single "download assets" button ships a licence breach to every customer.

**⚠️✅ Freepik — but only the AI-generation half, and only on the right tier.** Freepik has two products with *different* licences, and the distinction is the whole trap:

- **Freepik stock library** (their photos/videos): their commercial terms permit using a resource as the *main element of an end product* only when working for **one specific client**. Selling that same asset into products for **multiple clients is treated as redistribution and is prohibited.** A SaaS baking Freepik stock into videos for many paying customers is the multi-client case. **Do not use the Freepik stock library as a redistribution source on a standard plan.**
- **Freepik AI-generated output** (images/video you generate via their AI tools): under the **Enterprise Master Services Agreement**, you own all rights in the Output and may reproduce, modify and commercialise it for any lawful purpose, *with indemnification* against third-party IP claims when you follow the agreement. That **is** SaaS-safe — and it is the right home for the "illustrations" and "generated B-roll" rows in §4.4. Indemnity excludes: registered trademarks used in prompts, continued use after an infringement notice, unauthorised Input, and combining Output with third-party content in ways that create liability.

  **Action:** confirm in writing that your Freepik access is on terms granting **Output ownership + indemnification for multi-tenant commercial redistribution** (the Enterprise-MSA language), not the default stock/API tier. The standard plan and the Enterprise MSA are different animals; the safe language lives in the MSA. Freepik AI video also gives a second provider for generative B-roll, which R7 wants anyway.

**⛔ Pexels — prohibited.** Terms bar replicating core Pexels functionality, require a prominent Pexels link on every API request, and cap at **200 req/hour, 20,000 req/month**. The attribution requirement is incompatible with white-label course output.

**⛔ Unsplash — explicitly prohibited.** *"You cannot use the API to sell unaltered Unsplash photos directly or indirectly."* You **must hotlink** `photo.urls` and may not rehost — disqualifying on its own, because you cannot pull a file into FFmpeg or Remotion and comply. Plus a mandatory `download_location` ping and attribution with UTM params on every use.

**⚠️ Getty and Shutterstock** are enterprise-negotiated with no public rates. Getty directs you to an account rep. Shutterstock's SaaS redistribution requires a negotiated partner licence. Treat both as Phase 3 premium add-ons if customers demand specific footage.

**⚠️ Midjourney has no official public API.** Any "Midjourney API" is an unauthorised reseller — ToS and business-continuity risk. Do not build on it.

#### Budget

- **Storyblocks:** ~$2,000–5,000/month for a partner deal (estimate — they don't publish; get a quote during Phase 0, it moves the unit economics). At 1,000 videos/month that's $2–5/video; at 5,000, $0.40–1.00.
- **Freepik AI:** flexible pay-per-use on generation; confirm MSA pricing and the indemnification tier before it enters the production path.

#### Enforcement rule (applies to every source above)

Content-address every fetched/generated asset, tag it with its **source + licence + indemnification status** in provenance (R6), and make "may this asset leave the system as a stand-alone file?" a hard, code-level check that defaults to **no**. Stock and MSA-covered media exit only baked into a rendered video. This one rule keeps you compliant across all sources at once.

*Sources verified Aug 2026: Freepik Enterprise legal & usage-rights docs (support.freepik.com, freepik.com/ai/docs); Freepik commercial-use support article; Storyblocks partner terms as summarised in v0.1 research.*

---

## 15. Localisation

### 15.1 Architecture

R3 (span-anchored cues) is what makes this tractable. Translation preserves span IDs; the timing resolver re-resolves per locale from that locale's TTS word timings. Translators work on a **segmented, ID-tagged script in XLIFF 2.x**, never free prose. **MT and human translators must not merge or reorder segments.**

### 15.2 Text expansion — plan for it in the layout system

Expansion from English varies by *source string length*, and short strings expand most — which is a problem, because §9.4 tells you to use short abridged key phrases:

| English source length | Average expansion |
|---|---|
| ≤10 chars | **200–300%** |
| 11–20 | 180–200% |
| 21–30 | 160–180% |
| 31–50 | 140–160% |
| >70 | 130% |

Per-language: German +10–35%, Spanish/Portuguese +15–30%, Polish +20–30%, French +15–20%, Arabic +20–25%, Hindi +15–35%, Russian +15%; contracting: Korean −10–15%, Hebrew −20–30%, Finnish −25–30%, Japanese **−10% to −55%** (huge variance).

Vertical metrics matter too: **Thai needs ~150% of Latin line height**; CJK, Arabic (especially Nastaliq) and Devanagari all need substantially more.

**Layout rules:**
- Every text slot declares `maxChars` for the source language; the layout engine reserves `ceil(sourceWidth × factor(lang, sourceLen))` using the length-bucket table above
- Auto-shrink with a **floor** at the 24 px legibility/encoding minimum. Floor breached → reflow to more lines → still broken → **flag for human review, never silently truncate**
- Line-height ×1.5 for Thai; ×1.3–1.4 for Devanagari / Arabic-Nastaliq / CJK
- **Never concatenate translated fragments. Never bake text into images.**
- CI pseudo-localisation pass: render every layout with a ×1.4-expanded accented pseudo-string and an RTL pseudo-locale

### 15.3 Timing drift — three strategies

| Strategy | Mechanism | Trade-off |
|---|---|---|
| **A. Elastic** | Scene duration derived from that locale's TTS; cues anchored to span IDs; re-run timing per locale | Correct, but requires re-render per locale |
| **B. Fixed** | Constrain translation to fit source duration (transcreation) and/or adjust speaking rate ±10% | Video renders once; **only audio + captions swap** → per-language HLS audio renditions over shared video segments. Big saving, but translation quality suffers |
| **C. Hybrid — recommended** | Scenes with no on-screen text and no tight sync (title cards, static holds, transitions) → fixed, absorbing drift in silence padding. Scenes with text or animation sync → elastic | Best cost/quality. Requires the scene spec to declare `timingSensitivity: rigid \| elastic` |

Declare `timingSensitivity` in the schema from day one. **Drift budget:** silence padding up to ~15% of scene duration to absorb contraction; beyond that, re-render at the new duration. For expansion, extend the scene — **never speed TTS beyond +8%** or the prosody gate fails.

### 15.4 RTL and script handling

- **Mirror the layout, not the content.** Reading order, alignment, progress direction, next-arrows all flip. Charts with a semantic axis (time series, ascending scales), code and mathematical notation **do not**. Tag each element `mirroring: auto | never`.
- **Bidi isolation** (`FSI`/`PDI` or CSS `unicode-bidi: isolate`) for Latin brand names and code identifiers inside Arabic strings. Getting this wrong produces reversed gibberish that nobody on an English-speaking team will notice.
- **Arabic is cursive with contextual glyph shaping** — per-character animation breaks joining. **Rule: word-level or line-level reveal only for Arabic/Urdu/Devanagari; per-character kinetic typography is Latin/Cyrillic/CJK only.** This is a common and embarrassing bug in kinetic-type products.
- **Fonts:** Noto, **subset per render** from the scene's known glyph set (include the subset hash in the cache key). Select **by locale, not by codepoint** — Noto Sans CJK SC/TC/JP/KR are four different fonts, and Han unification means the same codepoint renders differently; a Japanese reader will find Chinese glyph forms wrong. Per-script optical size multipliers (~+10–15% for Arabic and Devanagari to match Latin's perceived size). **Validate glyph coverage before render and hard-fail on missing glyphs** — tofu (□) renders *successfully* and will silently ship.

### 15.5 Avatars and localisation

The strong architectural recommendation: **design so you don't need lip-sync.** With motion graphics + voiceover, localisation is: swap the audio stem, swap the on-screen text, re-resolve timings. No lip-sync problem exists.

The moment a face is in frame you acquire a per-language *visual* re-render dependency (breaking the shared-video-segment optimisation), uncanny-valley risk that varies by language and phoneme inventory, and per-minute costs scaling with languages × content — for a feature whose learning benefit did not replicate. If a presenter is contractually required, the isolated compositing layer (§13.2) contains the damage.

---

## 16. Captions and accessibility

### 16.1 Captions

**Soft captions by default (WebVTT track), not burn-in.** Burn-in makes captions part of the render (so a typo costs a full re-render), breaks per-language reuse (N renders instead of one video + N VTT files), and removes user control. Burn in only for social exports and explicit open-caption requests — and when you do, apply it as a **final-stage filter on the stitched master**, never inside a scene render, so it stays out of the cache key.

**Word timing:** take **TTS-native timestamps first** (ElevenLabs character-level, Azure `WordBoundary`, Google SSML `<mark>` timepoints). Free, exact, deterministic, cacheable. Fall back to **MFA 3.0** for human VO — it is roughly 5× better than WhisperX at word boundaries (21.75 ms vs 110.90 ms mean error on Buckeye; at a strict 10 ms tolerance, 48.76% vs 1.31%). WhisperX only for arbitrary uploaded audio with no script. **Do not use Gentle** — effectively unmaintained.

Emit **WebVTT** (primary, supports inline timestamp tags for karaoke-style word timing), **SRT** (universal LMS fallback), and a **JSON word-timing sidecar** (your own format) driving kinetic typography, search-within-video and chapter navigation. Don't overload WebVTT for that last job.

On-screen word highlighting *is* part of the visual design and belongs in the scene render — driven by the sidecar, and constrained by §9.4 to key terms only.

### 16.2 WCAG 2.2

| SC | Level | Obligation |
|---|---|---|
| 1.2.1 Audio-only/Video-only | A | Descriptive transcript for silent screen-capture segments |
| **1.2.2 Captions** | **A** | Non-negotiable. WebVTT. |
| 1.2.3 AD or Media Alternative | A | Satisfiable with a descriptive transcript |
| **1.2.5 Audio Description** | **AA** | **The expensive one** — transcript no longer sufficient |
| 1.4.2 Audio Control | A | Don't autoplay, or provide controls |
| **2.3.1 Three Flashes** | **A** | Automated check required |
| 1.4.3 Contrast | AA | 4.5:1 normal, 3:1 large (≥18 pt / 14 pt bold) |
| 1.4.11 Non-text Contrast | AA | 3:1 for meaningful graphics — applies to diagrams, arrows, chart elements |

**The AD trick — a real architectural advantage.** 1.2.5 at AA is where course products fail, because it normally means fitting descriptions into narration gaps or producing an extended-AD version. But **the engine authors both narration and visuals from the same scene spec**, so it can enforce a **self-describing narration** rule: narration must verbally convey every essential visual element. If it does, 1.2.5 is satisfied *without a separate AD track*. Make this a hard linter rule — it is simultaneously good pedagogy (temporal contiguity + modality) and a compliance win. Fallback: generate an AD stem from `visualSpec` and mix it as an alternate audio rendition, which is a solved generation problem here rather than a voice-over job.

**Automated gates:**

```
PER-SCENE (pre-render)
  contrast: WCAG ratio for every text layer against its resolved background
            (sample worst-case region for gradients/images); fail <4.5:1 (<3:1 if ≥18pt)
  caption presence: every narrated scene has aligned word timings
  self-describing narration: every visualSpec element has a narration referent
            (reuses the coherence check from §9.2)

PER-RENDER (post-render, on frames)
  flash detection: sliding 1s window over luminance change and red-flash area
            per PEAT/Harding criteria; fail >3 transitions/s over >25% of frame
  caption safe area: reserve the bottom 15% as a caption exclusion zone
            in every layout template
```

Reserving the caption safe zone in layout templates **from day one** is the cheap fix that avoids a painful retrofit across every template you'll ever ship.

---

## 17. Learning and self-improvement

You asked for AI that trains itself regularly and generates template variations. Here's the honest version — what's real, what's plausible, and what's fantasy.

### 17.1 What is real and worth building

**Outcome-linked template performance.** Every scene carries `template`, `treatment`, `bloomLevel`, and (via xAPI) learner drop-off, rewatch rate, and downstream item accuracy. That is a genuine supervised signal linking *design choices* to *learning outcomes*, at a granularity no competitor has because their unit is the video, not the scene.

**What to do with it:**
- Rank templates by scene-level completion and downstream item accuracy, conditioned on content type and audience
- Feed the ranking into the Visual Planner as a prior
- Surface it to the customer: "scenes using the compare-contrast template in this course have 23% higher item accuracy"

**Requirement:** this needs real learner data at volume. It is a **Phase 3+ capability** and should be architected for in Phase 1 (the scene-level xAPI emission) but not promised earlier.

**Human-feedback learning.** Every override is a labelled preference pair: the AI proposed X, the human chose Y, in context C. Store it in provenance (R6). Two uses: per-customer style adaptation (immediately valuable, cheap, and the thing that makes the product feel like it learns *your* style) and, at aggregate scale, a reward model over storyboard decisions.

**Template variation as constrained search.** Templates are parameterised (layout, reveal order, motion signature, density, colour role assignment). Generating variants is sampling the parameter space subject to the linter. A/B them against outcome data. **Don't let an LLM free-form invent templates** — you get inconsistency and linter failures. Constrained search over a designed space gives you novelty with a quality floor.

### 17.2 What is not real

**"The AI trains itself on a regular basis"** in the sense of retraining generative models — no. You are renting those models. What updates is: your template ranking, your per-customer style profile, your prompt library, your reward model, and your model-routing policy. That is genuinely valuable and worth saying plainly, but it is a different mechanism from what the phrase implies. Be precise about this internally so nobody builds a roadmap around fine-tuning Veo.

**Fully autonomous quality improvement** — no. There is a floor set by the base models, and there's a real risk of a self-reinforcing loop optimising toward whatever the reward proxy measures. Keep humans in the evaluation loop, and — per §9.4 — **do not use learner satisfaction as the reward signal**, because learners systematically prefer the pedagogically worse design.

### 17.3 Reference video replication ("if a sample is provided, replicate or upgrade it")

Decomposable and worth building, at three levels:

1. **Style extraction (achievable, Phase 2).** Analyse the reference: pacing, shot/scene durations, colour palette, type treatment, motion signature, narration density, wpm, on-screen text ratio, transition style, music presence. Emit a **BrandKit + template profile**. This is measurement, and it's reliable.
2. **Structural extraction (achievable, Phase 2).** Transcribe, segment, identify the Gagné slots present, extract the objective structure and hook pattern. Emit a **template variant**. Reliable enough to be useful, and it's the thing customers actually mean when they say "make it like this."
3. **"Upgrade it" (Phase 3, and be careful).** Run the reference *through the linter* and report where it violates the principles, then generate a version that fixes those violations while preserving the extracted style. **This is a genuinely compelling demo** — "here's your existing video, here are its 7 pedagogical problems, here's the fixed version" — and it's a strong sales motion into P2/P3. Caveat: "upgrade" is subjective, so frame it as *specific, cited fixes*, never as a general claim of superiority.

**Legal note:** style extraction from a customer's own video is fine. Extracting from a *competitor's* video that a customer uploads is a question you should get answered before shipping the feature, not after.

---

## 18. Export, integration, delivery

### 18.1 Export targets

One content source, four export targets:

1. **Hosted embed + LTI 1.3 / Advantage** (Deep Linking, Assignment & Grade Services, Names & Role Provisioning) — flagship. Content stays on your infrastructure, so you can update videos without re-shipping packages, and you get real analytics. Pursue 1EdTech certification for HED credibility.
2. **cmi5 package** — xAPI's richness with standardised launch/session/completion semantics. "xAPI with the rules put back in." The right target for modern LMSs.
3. **SCORM 1.2** — the universal fallback. Completion and score only, no video-behaviour tracking, same-origin sandboxed. A meaningful share of enterprise buyers will demand it. **Ship it on all paid tiers**, not gated to Enterprise — this is a direct wedge against Synthesia, whose Enterprise-only SCORM gate is the single biggest structural complaint from L&D buyers.
4. **Raw MP4 + WebVTT + SRT**, plus **OTIO timeline export** for customers who want a human editor to polish in Resolve or Premiere. That escape hatch is a real enterprise-sales feature and an antidote to the lock-in complaint.

SCORM 2004 only if a customer needs multi-SCO sequencing — sequencing support is the flakiest part of SCORM 2004 across LMSs.

### 18.2 xAPI Video Profile

Emit `initialized`, `played`, `paused`, `seeked`, `interacted`, `completed`, `terminated` with the profile's required extensions. **`played-segments`** is the important one — watched intervals give you drop-off curves and rewatch heatmaps.

**The win from the chunk architecture:** because scenes are addressable and aligned to HLS segments, you can map `played-segments` to **scene IDs** and answer *"which concept did learners re-watch or abandon"* rather than *"which video."* That is a genuinely differentiated analytics product, and it closes the loop back into §17.1.

**Do the standards work early.** Decide **now** that every scene has a stable ID and every assessment item has an `objectiveId` — these become xAPI object IRIs and cmi5 AU identifiers, and they cannot be added retroactively without breaking historical learner data.

---

## 19. Quality gates

Consolidated view of everything that must pass before a course ships.

| Gate | Type | Blocking? | Stage |
|---|---|---|---|
| Objective measurability (Bloom verb whitelist) | Deterministic | Yes | Curriculum |
| Objective DAG acyclicity + ordering | Deterministic | Yes | Curriculum |
| Objective↔assessment Bloom alignment | Deterministic | Yes | Curriculum |
| Source coverage (are all key concepts covered?) | Agentic ×2 | Warn | Curriculum |
| Factual verification with sources | Agentic | Warn + flag | Script |
| Readability, passive voice, tone | Deterministic | Yes | Script |
| Course-memory redundancy | Agentic | Warn | Script |
| Brand lexicon / banned terms | Deterministic | Yes | Script |
| Coherence score ≥0.85 | Agentic | Yes | Storyboard |
| Signal count 1–3 per scene | Deterministic | Yes | Storyboard |
| Text density thresholds | Deterministic | Yes | Storyboard |
| On-screen text similarity band (0.3–0.85) | Agentic | Yes | Storyboard |
| Element-interactivity ≤4 new | Deterministic | Warn | Storyboard |
| Contrast ratios | Deterministic | Yes | Storyboard + frames |
| Caption safe area | Deterministic | Yes | Storyboard |
| Glyph coverage | Deterministic | Yes | Pre-render |
| Asset match to request | Agentic | Yes | Asset |
| Character/style consistency | Agentic | Warn | Asset |
| Flash rate (PEAT/Harding) | Deterministic | Yes | Post-render |
| A/V sync drift | Deterministic | Yes | Post-render |
| Render determinism spot-check | Deterministic | Alarm | Continuous |
| Whole-course pacing and difficulty curve | Agentic | Warn | Course |

**Escalation:** any blocking gate that fails twice after auto-repair goes to a human with a clear explanation and a proposed fix. Never silently degrade and ship.

---

## 20. Metrics

### 20.1 Product

- **Time-to-acceptable-course** (the true north; target ≤15 min human interaction per finished 5-min video)
- **Edit-to-render latency** (target: scene-level change visible in <60 s)
- **Cache hit rate on edit** (target: >90% of scenes untouched by a typical edit)
- Generation acceptance rate (proportion of scenes shipped without human override)
- **Reroll factor** (target ≤1.5×) — this is a COGS metric wearing a product-metric hat
- Linter pass rate on first generation

### 20.2 Business

Activation (first course published), courses/customer/month, videos/course, retention at 3/6/12 months, **gross margin per video** (§21), expansion (languages, seats, volume), NPS split by persona — **watching P3 (instructional designers) separately, because they are the gatekeepers**.

### 20.3 Learning outcomes — the one nobody else measures

This is a positioning asset, not just an internal metric. Via xAPI: scene-level completion and drop-off, rewatch heatmaps, assessment item accuracy by objective, and — where customers permit — pre/post gains.

**Explicitly do not optimise on learner satisfaction.** Yue et al. showed learners prefer the pedagogically worst condition. Track satisfaction as a *guardrail* (don't let it collapse), optimise on outcomes.

Being able to say *"courses built on Sequence produce X% higher assessment accuracy"* with real data is worth more than any feature on the roadmap. Design the data collection to support that claim from Phase 1, even if you can't make it until Phase 3.

---

## 21. Unit economics and pricing

### 21.1 COGS per 5-minute video

Shared assumptions: 300 s runtime, ~4,500 characters of narration; ElevenLabs Multilingual at $0.10/1K chars; LLM pipeline ~$0.90; Storyblocks amortised at $2.50/video (1,000 videos/mo on a $2,500/mo deal — *estimate, get a quote*); Remotion Lambda + licence $0.16.

**Tier 1 — Avatar + slides + stock**

| Line | Cost |
|---|---|
| LLM pipeline | $0.90 |
| TTS | $0.45 |
| Avatar (HeyGen Avatar III, 300 s) | $5.01 |
| Images (10 × Nano Banana 2) | $0.67 |
| Stock (amortised) | $2.50 |
| Music | $0.75 |
| Render + licence | $0.16 |
| **Total** | **$10.44** |

Budget variant (HeyGen TTS, no music): **$9.44**. Premium (Avatar IV): **$25.44**.
*Avatar is 48% of COGS.*

**Tier 1M — Motion-graphics only (no avatar) — the recommended default**

Strip the avatar line: **≈$5.43**. This is the cheapest, most pedagogically defensible, most localisable, and most cache-friendly configuration. **It should be the product's default output**, which is a pleasant alignment of evidence and economics.

**Tier 2 — Avatar + generative B-roll** (150 s avatar + 150 s generative, Veo 3.1 Fast 1080p, 2.5× rerolls)

| Line | Cost |
|---|---|
| LLM | $1.00 |
| TTS | $0.45 |
| Avatar (150 s) | $2.51 |
| **Generative B-roll** | **$37.50** |
| Seed/slide images | $1.34 |
| Stock | $2.50 |
| Music | $0.75 |
| Render | $0.16 |
| **Total** | **$46.21** |

Budget (Veo 3.1 Lite 720p, 1.5× rerolls): **$15.46**. Premium (Veo 3.1 quality): **$83.71**.
*B-roll is 81% of COGS; the reroll factor alone is $22.50 of it — more than all of Tier 1.*

**Tier 3 — Fully generative** (~38 clips): **$83.72** base, **$28.54** budget, **$308.27** premium (Veo 3.1 quality with native audio).
*Generative video is 90% of COGS.*

### 21.2 Summary and implications

| Tier | Budget | Base | Premium | $/min (base) |
|---|---|---|---|---|
| 1M — Motion graphics only | ~$4.50 | **$5.43** | — | **$1.09** |
| 1 — Avatar + slides + stock | $9.44 | **$10.44** | $25.44 | **$2.09** |
| 2 — Avatar + generative B-roll | $15.46 | **$46.21** | $83.71 | **$9.24** |
| 3 — Fully generative | $28.54 | **$83.72** | $308.27 | **$16.74** |

1. **Tiers 1M and 1 support flat-rate subscription pricing.** Tiers 2 and 3 do not — they need metering or hard caps.
2. **Reroll reduction is the largest single margin lever.** Engineering spent on the Asset QA agent, prompt quality and reference conditioning returns more than any vendor negotiation.
3. **Model routing is the second lever.** Draft on Lite → approve → re-render approved shots at quality roughly halves effective Tier 2/3 cost.
4. **LLM, TTS and rendering are rounding errors** (<5% combined at every tier). Use the best available; optimising there is misallocated effort.
5. **The cache is a COGS line, not just a UX feature.** In a market where everyone re-charges for iteration, structurally cheaper iteration is both a better product *and* a better margin.

### 21.3 Pricing model

Reject the credit model. It is the #1 and #2 complaint in the category and it makes iteration feel dangerous — which is precisely the behaviour this product needs to encourage.

**Proposed:** per-seat + a generous **finished-minutes** allowance, with **iteration free**. You bill for output minutes published, not for renders. This is only economically possible *because* of the cache architecture, which means the pricing model is itself a moat — a competitor whose re-render costs full price cannot copy it.

Metering applies only to Tier 2/3 generative B-roll, exposed as a clearly-labelled premium action with a visible cost estimate before the user commits ("this scene will use ~12 s of generative video, est. $0.90"). Never surprise-bill.

**Do not gate SCORM, translation, or brand kits behind Enterprise.** That gate is the single loudest structural complaint against the market leader; being the vendor who doesn't do it is worth more than the upsell.

### 21.4 The churn risk you should plan for now

P1 (solo creators) build one course and leave. **This is the primary business risk of the creator segment**, and it's why the maintenance story matters commercially as well as technically: the product must be valuable *between* courses. Levers: the spaced-review schedule (ongoing learner value), content-freshness alerts ("3 facts in module 2 have changed since publication — review?"), localisation expansion, and analytics that surface which scenes to improve. Land P2 and the problem largely dissolves; build for P2 and P1 becomes acquisition rather than the core business.

---

## 22. Roadmap

**Build-posture framing (v0.2).** The first step is *two proofs, not one* (see §0.5). **Milestone A — Proof of Good** validates that the pedagogy engine plus visual quality produce something an ID would publish; it is **solo-buildable with Claude + Supabase + Git**, uses the correct R1–R8 schema, and renders *one* video with no cache. **Milestone B is Phase 0 below** — the deterministic edit-one-scene loop, which needs **one video-pipeline contractor for 6–8 weeks**. Do A to learn whether it's worth building; do B to learn whether the moat is buildable. Everywhere else, work stays solo-and-Claude for as long as possible.

### Milestone A — Proof of Good (4–6 weeks, solo + Claude) — *new in v0.2*

Build only: intake → objective graph → deterministic linter → Gagné storyboard → **one** motion-graphics video (Tier 1M), rendered once. English only. MP4 + captions. **No cache, correct schema.** Stock hook via Storyblocks trial; illustration/B-roll via Freepik AI (§14.3). **Success:** an instructional designer reviews the objective graph and the rendered video and says "I'd sign off on this." If they won't, fix the pedagogy engine before spending a day on the render cache.

### Phase 0 — De-risk / Milestone B (6–8 weeks, + one specialist, before committing)

Build only:
1. Scene graph schema + timing resolver + content-addressed cache + Remotion render + FFmpeg stitch
2. **Prove the edit-one-scene loop end to end**, with correct A/V sync across a 10-scene video
3. Hand-author 3 storyboards, no AI. Render, edit one word in scene 5, verify: 1 scene re-renders, sync holds, cost is near zero
4. Prototype the pedagogy linter against those 3 storyboards
5. Get quotes: Storyblocks, Remotion Enterprise, HeyGen volume, Veo quota

**Kill criterion:** if the chunked re-render loop isn't clean and deterministic after 8 weeks, the whole thesis is at risk and you should know that before spending on agents or UI. This phase exists to find that out cheaply.

### Phase 1 — Single-video MVP (3–4 months)

Milestones A and B fused. Intake → objectives → script → storyboard → render, for **one video**. Motion graphics only (Tier 1M). Full agent pipeline through Tier 5. Deterministic linter rules. Storyboard + scene views. Chat editing at scene level. English only. MP4 + WebVTT export. (Team: solo + Claude for the agent/UI/graph work; the Phase-0 specialist stays engaged for the render/cache layer.)

**Success:** a domain expert with no video skills produces a 5-minute video they'd publish, in under 30 minutes, and can edit it fluidly afterwards.

### Phase 2 — The course layer (3–4 months) — *the differentiating release*

Course graph + objective DAG + curriculum planner. **CourseMemory with retrieval.** Continuity agent. Assessment generation with `sceneRef` links. Module structure. Course view. Brand kit. Reference-video style extraction (§17.3 levels 1–2). SCORM 1.2 + hosted embed. Optional avatar layer. Agentic linter rules.

**Success:** an 8-video course where video 7 demonstrably builds on video 2 — and regenerating video 4 preserves that.

### Phase 3 — Scale and depth (4–6 months)

Localisation (hybrid timing strategy, 8–12 languages). cmi5 + LTI 1.3 + xAPI Video Profile with scene-level statements. Generative B-roll with draft-then-approve routing. Screen capture / synthetic UI renderer. Spaced review schedules. Analytics dashboard. Team collaboration. Storyblocks integration. Template learning loop v1. Accessibility gate suite complete. Reference-video "upgrade" mode.

### Phase 4 — Compounding (ongoing)

Outcome-linked template optimisation at real data volume. Per-customer style models. Interactive/branching video. Conversational avatars (Tavus). Fine-tuned style LoRAs if and only if volume justifies. Getty/Shutterstock premium tier. Marketplace of template packs.

---

## 23. Open decisions — what I could not decide for you

1. **Hosted-only, or SCORM-package parity?** Hosted (LTI) is architecturally better and enables everything in §12 and §18.2. Packaged SCORM is what many buyers demand. Supporting both well is real cost; supporting only hosted loses deals. Decide before Phase 2, because it shapes the export layer.
2. **Remotion, or own the renderer from day one?** Remotion is faster to build on and its licence is genuinely misaligned with fine-grained re-rendering. My recommendation is Remotion + R8 discipline + early Enterprise negotiation — but a founder with strong graphics engineering could reasonably go straight to WebCodecs and never look back.
3. **Ship without avatars in v1?** The evidence says yes; the market says buyers will ask. I lean yes — differentiate on the course layer, add avatars in Phase 2 when they're cheap to bolt on as an isolated layer. But you'll lose some demos.
4. **How much control to expose in v1?** Full scene-level canvas editing is a large build. A constrained version (swap, retime, toggle, reorder — no free-form canvas) covers most needs at a fraction of the cost. I'd start constrained and let usage data pull you toward the canvas.
5. **Which 8–12 languages first?** Depends entirely on your target customers. Note that RTL and Indic add disproportionate engineering (§15.4), so sequence them deliberately rather than alphabetically.
6. **Do you sell the pedagogy score externally?** It's a strong differentiator and a hostage to fortune — publishing a rubric invites scrutiny of your own output against it. I think it's worth it, but it's a company-identity decision, not a product one.

---

*Companion document: **CHALLENGES.md** — the risk register. Read it before funding anything in this document.*
