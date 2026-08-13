# PRD v4 — AI-Native Explainer Video Pipeline

**Status:** Build-ready. Decisions resolved in §2 as stated assumptions — override any of them and the affected sections are marked.
**Supersedes:** PRD v3 (which superseded v2)
**Owner:** Sanket Jadhav, Board Infinity
**Last updated:** 13 August 2026

---

## 0. What changed from v3, and why this version exists

v3 was a strong **product and methodology** document. Its pipeline order is correct, its pedagogical corrections are right, and its invalidation model is the right foundation. This version keeps essentially all of that thinking.

What v3 could not do was start a build. It specified a *pipeline* and never specified a *system*. A developer reading v3 on day one could not answer: what runs the 13 stages, what database holds state, what the editor looks like, who builds it, how long it takes, or where video 1's quality comes from before the preference dataset exists.

v4 adds those four missing layers and re-cuts the roadmap so each phase has a duration, a team, a cost, and a stop condition.

| Added in v4 | Why |
|---|---|
| **§2 — Decisions resolved** | v3 shipped with 8 blocking decisions open while calling itself build-ready. Those are now answered as assumptions you can override in one sitting |
| **§6 — System architecture** | The single largest gap. Orchestration, data model, storage, render infra, failure semantics, observability |
| **§7 — Build vs. buy** | v3 named no vendors and no boundaries. This is where a month gets lost |
| **§8 — The editor specification** | v3 called this ~70% of the engineering and then described it in a 7-row table |
| **§9 — Agent quality & cold start** | v3's quality mechanism was a preference dataset that doesn't exist until video 30. This answers where videos 1–30 get their quality |
| **§16 — Phased delivery plan** | Every phase now has weeks, people, cost, exit criteria, and an explicit *not* list |
| **§19 — Kill criteria** | v3 had a risk register but no condition under which you stop |

| Corrected in v4 | Detail |
|---|---|
| Stale cross-references | v3's status line and §12.1 and Phase 0 all pointed to "§14.5" for the render engine decision. §14 was the agent roster; the decision was D5 in §17. All references rebuilt |
| Phase count and sequencing | v3's 8 phases mixed craft work, infrastructure, and product with no resourcing. Re-cut into 10 phases along skill boundaries so they can actually be staffed |
| "15 human-min" presented as settled | Re-framed as the project's central unproven hypothesis, with a measurement plan and a fallback |

**Nothing was removed from v3's substance.** The v2→v3 arguments have been moved to Appendix C so the body of this document reads as instructions rather than as a rebuttal.

### 0.1 How to read this

- **§1–§5** — the product. Mostly v3, condensed, decisions applied.
- **§6–§9** — the system. New. This is what you hand an engineer.
- **§10–§15** — specifications carried forward from v3 (pedagogy, audio, render, evals), edited for the resolved decisions.
- **§16–§19** — the plan. Phases, team, cost, risks, kill criteria.
- **Appendices** — schemas, the v2→v3 history, glossary.

If you have thirty minutes, read §2, §16, and §19.

---

## 1. Product goal

**Input:** a topic, positioned inside a series plan, with a declared audience level and locale.

**Output:** a branded, narrated, 1080p MP4 — pedagogically sequenced, factually verified with per-claim provenance, visually varied, fully sound-designed, publish-ready in 16:9 and 9:16 — produced within a stated cost, latency, and **human-attention** budget, and editable at **beat granularity** without disturbing approved work.

**Product shape:** an internal web application with an editor. Not a terminal script, not a public SaaS (yet).

### 1.1 The one-sentence differentiator

Anyone can generate a video. What a freelancer with a good After Effects template **cannot** do is produce a *pedagogically sequenced series* where video 6 correctly assumes what video 2 taught — and get cheaper and better with every video shipped. That is the product. Everything in this document serves it.

### 1.2 Why this matters specifically for Board Infinity

Stated so the build has a business anchor, not just a technical one:

- Course content refresh is currently a linear cost. Every updated module costs roughly what the original cost. This system makes refresh a **diff**, not a rebuild — change one concept, re-render three beats.
- Learner outcomes are measurable on your own platform. That makes S4 (comprehension) a real metric rather than an aspiration, which most video pipelines cannot claim.
- A multi-video series with genuine prerequisite continuity is the format your product already sells. The unit of the pipeline matches the unit of the business.

### 1.3 Explicit non-goals (v1–v3 of the product)

- Not a general-purpose video tool. Explainer/educational only.
- Not live-action, not talking-head, not screencast.
- **No AI-generated B-roll.** Cut, not deferred (§13.3).
- **No second render engine.** One engine until a measured failure justifies a second.
- Not fully autonomous. A human holds editorial sign-off, permanently, by design.
- **Not a product other companies can buy.** Internal tool. Revisit no earlier than 100 videos shipped.

---

## 2. Decisions resolved

v3 listed 8 blocking decisions and 6 confirmable ones, then described itself as build-ready. It was not. Here they are answered.

**These are assumptions drawn from Board Infinity's context — career upskilling, own learning platform, Indian and international learners. Read this section first and correct anything wrong. Each row names what breaks if the answer changes.**

### 2.1 Blocking decisions

| # | Decision | **v4 answer** | Confidence | If this changes |
|---|---|---|---|---|
| **D1** | Who is the learner? | **Working professionals and final-year students, 21–32, with domain exposure but not mastery. Default `audience_level: intermediate`.** Per-series override allowed | High | §11.3 worked-example strategy inverts. Affects lesson plan prompts only — cheap to change if `audience_level` is in the schema from Phase 1 |
| **D2** | Target volume | **Scale. 100+ videos in year one.** Optimize human-minutes and compounding above per-video perfection | High | If the real answer is 10–20, cut Phase 9 entirely, keep the reviewer advisory-only, and hand-do the compounding. Roughly a third off the build |
| **D3** | Human-minutes budget | **≤ 15 min/video at video 20+, ceiling 30.** Treated as the project's central hypothesis, not a settled number (§4.1) | Medium | This is the number the whole architecture serves. See §19 kill criteria |
| **D4** | Target length | **6–8 minutes.** 8–14 beats | High | Under 4 min the per-video fixed costs dominate and the series framing weakens. Over 12 min render latency and gate time both blow past budget |
| **D5** | Render engine | **Remotion.** Reasoning in §13.1 | High | Reversing this after Phase 5 costs the entire template library. Decide before Phase 2 ends |
| **D6** | Publishing destination | **Board Infinity's own platform first** (comprehension measurable), **YouTube second** for top-of-funnel. Both aspect ratios from Phase 7 | High | If YouTube-only, S4 becomes unmeasurable and §12.4's feedback loop loses its safety constraint — which is the loop's whole point |
| **D7** | Locale | **Ship EN only. Put `locale` in the schema from Phase 1.** Hindi/Hinglish edition is a Phase 9+ option, not a commitment | High | Costs roughly nothing now. Retrofitting means every template that baked text into a render gets rewritten |
| **D8** | Editorial sign-off owner | **A single named editorial owner with veto over publish, and sole authority to change `curriculum.yaml` and the rubric.** Not a committee | High | Gates without a named owner become theater. This is the cheapest decision here and the one most often skipped |

### 2.2 Confirmable decisions

| # | Decision | **v4 answer** |
|---|---|---|
| D9 | Phase 2/3 pilot series | A 4-video series from your existing catalogue where prerequisites are real. Recommended: **SQL for analysts** (`joins → aggregation → window functions → query optimization`) — genuine dependency chain, code and diagram heavy, and you already have SME coverage. Write `curriculum.yaml` by hand first |
| D10 | Fact sourcing | **Closed corpus** for v1: 3–5 trusted references per domain, plus official documentation for anything technical. Verifiable beats plausible. Add web search only for topics needing currency |
| D11 | Frontier model | Whichever you have reliable production access to. **Not the bottleneck** (§15.2) — spend the time on §5 and §14 instead |
| D12 | Render compute | **Local/dev machines for Phases 2–8** (iteration speed dominates), **Remotion Lambda from Phase 9.** Do not build render infrastructure before you have something worth rendering at volume |
| D13 | Music source | Licensed library (Epidemic Sound class), 5–8 track palette per tone |
| D14 | AI-disclosure posture | **Decide in Phase 0, publish it.** Recommended: a standing disclosure in the course description — "visuals and narration produced with AI tooling; content authored and reviewed by Board Infinity subject experts." Honest, and it makes the human sign-off a feature rather than a liability |

### 2.3 The decision behind the decisions

D2 is the one that shapes everything. At 10 videos, most of this document is over-engineering — you would hand-craft, use gates liberally, and skip the compounding machinery entirely. At 100+, every hour spent on §5 (invalidation) and §9 (agent quality) pays back several times over.

**If you are not confident in D2, do not start Phase 3.** Run Phases 0–2 — about eight weeks — and decide with a real video in front of you.

---

## 3. The six design principles

Every decision derives from these. When a future addition conflicts with one, the principle wins.

**P1 — Nothing enters the pipeline that cannot be measured.**
No stage, agent, or gate ships without a metric saying whether it helped. A stage that can't be evaluated can't be improved and can't be justified.

**P2 — Human attention is the scarcest resource.**
Not tokens, not GPU. Gates must *earn* their minutes against a hard budget and are demoted when they stop paying for themselves.

**P3 — Errors are caught where they are cheapest to fix.**
Adversarial critique sits adjacent to the stage that produced the artifact, not at the end. A fact error found at stage 1 costs cents; found after render it costs the whole video.

**P4 — Every video must make the next video cheaper.**
Templates, lexicon, brand, curriculum, and captured human preference are first-class versioned assets. If video 30 costs what video 5 cost, the product failed even if the videos are good.

**P5 — Additions must justify themselves against deletions.**
This document has a stage budget. Adding a stage requires naming what it replaces or a measured failure it fixes.

**P6 — Build the smallest thing that produces a watchable video, then make it good.** *(new in v4)*
v3's phase ordering already implied this. Stating it as a principle prevents the most likely failure mode of a team that has read this document: building six weeks of beautiful infrastructure before anyone has watched anything. Every phase from 2 onward must end with something you can play.

---

## 4. Success criteria

A score from a model panel is not a target — it is unfalsifiable and rewards document length. These five are the definition of done, measured on the golden set (§14) or in production.

| # | Commitment | Target | Measured by |
|---|---|---|---|
| **S1** | **Accuracy** | 20 consecutive videos, zero factual errors | Human SME audit, blind, post-publish |
| **S2** | **Human efficiency** | ≤ 15 human-min per finished video at steady state (video 20+) | Timer on gate sessions. Instrumented, not estimated |
| **S3** | **Perceived quality** | ≥ 40% of target learners rate ours ≥ a hand-made reference in blind A/B | Blind pairwise test, n ≥ 30 |
| **S4** | **Learning** | ≥ 80% correct on the video's own comprehension items | CFU items shipped with each video (§11.4), delivered through your platform |
| **S5** | **Compounding** | Video 30's human-min AND $ measurably lower than video 5's | Per-video telemetry, plotted |

Interim ramp: ≤ 45 human-min at video 5, ≤ 30 at video 10, ≤ 15 at video 20.

### 4.1 On S2 — the honest version

v3 presented ≤15 human-minutes as a target. It is better understood as **the project's central unproven hypothesis.**

The whole architecture — progressive trust, batch queues, edit-with-instruction, beat locking — exists to serve it. If it turns out that reviewing a 7-minute educational video for factual and pedagogical correctness simply *takes* 30 minutes of a competent person's attention, then this is a good video tool with a mediocre economic story, not the product described in §1.1.

**So measure it from the very first video.** Not from video 20. A stopwatch on Gate A from day one, recorded in `manifest.json`, plotted weekly. If the curve is flat at video 10, that is a finding, and §19 tells you what to do about it.

S2 and S5 are the ones that will be tempting to drop. They are the ones that decide whether this is a product or a demo.

---

## 5. Architecture — the pipeline

```
┌─ SERIES SCOPE (once per series) ────────────────────────────────────┐
│                                                                     │
│ [0] CURRICULUM PLANNER          ──► curriculum.yaml                 │
│     agent proposes, human owns      concept IDs, per-video          │
│                                     teaches[]/assumes[], order,     │
│                                     narrative spine, callback plan  │
│                                                                     │
│     ══ GATE 0: Series Plan ══  (once, ~20 min, amortized over 6+)   │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─ VIDEO SCOPE (per video) ───▼───────────────────────────────────────┐
│                                                                     │
│ [1] RESEARCH            ║ FACT CHALLENGER  (parallel, adversarial)  │
│     └─► verified_facts.json  — per-claim source + confidence        │
│                                                                     │
│ [2] INSTRUCTIONAL DESIGN ║ PEDAGOGY CRITIC (parallel, adversarial)  │
│     reads curriculum.yaml + audience_level + known_issues[]         │
│     └─► lesson_plan.json + learning_objectives.json                 │
│                                                                     │
│ [3] SCRIPT  (draft → self-critique → 3 hook variants)               │
│     └─► script.json  — beats w/ signaling flags, lexicon applied    │
│                                                                     │
│     ══ GATE A: Teaching & Script ══  ~10 min                        │
│        one surface · facts + plan + script + hook candidates        │
│        edit-with-instruction · diff view · per-beat lock            │
│        auto-approves unflagged sections once trusted (§8.6)         │
│                              │                                      │
│ [4] STORYBOARD  ║ VISUAL/BRAND CRITIC (parallel)                    │
│     typed template selection · transition grammar · variety budget  │
│     signaling → visual emphasis mapping                             │
│     └─► storyboard.json                                             │
│                                                                     │
│     ══ GATE B: Storyboard ══  ~8 min                                │
│        reorder · split/merge · swap template · lock · regenerate     │
│                              │                                      │
│ [5] TTS         pinned voice+model · lexicon.json · cached          │
│     └─► narration/*.wav + beat timestamps                           │
│                                                                     │
│ [6] RENDER      Remotion · typed templates · compile-repair ×3      │
│                 · keyframe visual verification (VLM)                │
│     └─► scenes/*.mp4                                                │
│                                                                     │
│ [7] PACING      code, not a model — duration match + pause insert   │
│                                                                     │
│ [8] SOUND DESIGN  licensed palette · ducking · SFX budget           │
│                   · −14 LUFS / −1 dBTP                              │
│                                                                     │
│ [9] ASSEMBLY (FFmpeg)   └─► rough_cut.mp4                           │
│                                                                     │
│ [10] EMERGENT REVIEWER  — ONLY what needs a finished video:         │
│      A/V sync · visual-narration match · pronunciation · loudness   │
│      · finish quality. Has rubric + facts; not generator's rationale│
│      └─► findings[] {severity, dimension, timestamp, fix}           │
│                                                                     │
│     ══ GATE C: Watch It ══  ~10 min                                 │
│        fixes invalidate ONLY affected beats (§5.3)                  │
│                              │                                      │
│ [11] FINISHING & DELIVERY                                           │
│      3 thumbnail candidates · styled captions (keyword ≠ verbatim)  │
│      · 16:9 + 9:16 · transcript · sources w/ per-claim→beat map     │
│                                                                     │
│ [12] FEEDBACK LOOP                                                  │
│      watch-time AND comprehension · drop-off vs re-watch split      │
│      watch-time alone may NEVER override a pedagogical choice       │
│      └─► known_issues[] → Gate A of next revision                   │
└─────────────────────────────────────────────────────────────────────┘
```

**13 stages. 3 per-video gates + 1 amortized series gate.**

The cross-cutting subsystems that v3 listed here — compounding assets, eval infrastructure, budgets, and the shared schema — are specified in §10, §14, §15, and Appendix A.

### 5.1 Artifact & invalidation model — the foundation

> The single most important subsystem in this document. Built in Phase 1. Retrofitting it after Phase 5 is a rewrite, not a refactor.

**The problem it solves.** At Gate C you watch the cut and beat 7 is confusing. You edit its script. That legitimately invalidates beat 7's TTS, its timestamps, its render, the pacing of beats 6 and 8, transitions on both sides, SFX placement, global loudness, total runtime, captions, and the 9:16 cut.

Without an explicit dependency model, "Edit" silently means "regenerate everything" — expensive, slow, and **non-deterministically changing the 11 beats you already approved.** That is the failure mode that kills pipelines like this. It is not a performance concern. It is a trust concern: the second time the system quietly changes something you approved, you stop trusting any output, and the human-minutes curve goes the wrong way forever.

### 5.2 Content addressing

Every artifact is keyed by a hash of its full input closure:

```
hash(artifact) = H(
    [hashes of all upstream input artifacts]
  + prompt_template_version
  + model_id + model_version
  + code_version         (renderer / template / pacing logic)
  + config               (voice_id, brand_version, locale, audience_level)
)
```

A stage re-runs **iff** its input hash changed. Everything else is served from store.

Implementation notes added in v4:

- Hash is SHA-256 over a **canonical JSON serialization** — sorted keys, no whitespace, explicit null handling. Non-canonical serialization is the classic source of phantom cache misses.
- `code_version` is the git SHA of the template/renderer directory, not of the whole repo. Otherwise every unrelated commit invalidates every render.
- Prompt templates live in `prompts/` as versioned files. Editing a prompt bumps its version, which changes hashes downstream, which triggers a regression run (§14.4). That loop is the point.
- Model provider version strings are captured at call time and recorded, not assumed from config. Providers update silently.

### 5.3 Beat-level granularity

Granularity is the **beat**, never the video. `script.json` is not one artifact — it is N beat artifacts plus an ordering. Editing beat 7's text changes exactly one leaf hash, and the invalidation set is:

```
beat7.script → beat7.tts → beat7.render → pacing(6,7,8)
             → transitions(6→7, 7→8) → assembly → mix → captions → exports
```

Beats 1–6 and 8–12 keep their existing renders **byte-identical**. Cost of that edit: one TTS call, one render, one remix. Seconds and cents.

### 5.4 What this buys, beyond editing

- **Resumability** — crash mid-render resumes; nothing recomputed.
- **Honest cost model** — the manifest shows exactly what each change cost. S5 becomes plottable.
- **Regression testing** — change a prompt, hash-diff the golden set, see precisely which videos would change *before* rendering anything (§14.4).
- **Cheap brand sweeps** — bump `brand@1.2.0 → 1.3.0`; only brand-dependent artifacts re-render.
- **Beat locking** — a human-locked beat is pinned to its current hash and exempt from upstream invalidation until explicitly unlocked. This is how the human protects work they like from downstream churn.

### 5.5 Global-scope exceptions

Three artifacts are inherently whole-video scoped and must be marked as such so the invalidation graph stays honest: **loudness normalization**, **total runtime**, and **transition continuity across a locked-beat boundary**. These are cheap to recompute; the point is not to pretend they are beat-local.

---

## 6. System architecture — new in v4

v3 said "an application with an editor" and then never described the application. This section is what you hand an engineer.

### 6.1 Topology

```
┌──────────────────────────────────────────────────────────────┐
│  BROWSER — Editor (Next.js + React)                          │
│  Series dashboard · Gate 0/A/B/C surfaces · Batch queue      │
│  Video player w/ beat timeline · Manifest & cost views       │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTPS / JSON + SSE for job progress
┌───────────────────────────▼──────────────────────────────────┐
│  API SERVER (FastAPI, Python)                                │
│  Auth · Series/Video CRUD · Gate actions · Job submission    │
│  Artifact resolution · Cost preview · SSE progress stream    │
└───┬────────────────────┬──────────────────┬──────────────────┘
    │                    │                  │
┌───▼──────────┐  ┌──────▼────────┐  ┌──────▼──────────────────┐
│ POSTGRES     │  │ OBJECT STORE  │  │ ORCHESTRATOR            │
│ state, jobs, │  │ (S3 / R2)     │  │ DAG resolution          │
│ metadata,    │  │ content-      │  │ hash → run or serve     │
│ manifests,   │  │ addressed     │  │ dispatch to workers     │
│ prefs, evals │  │ blobs         │  │ retry / escalate        │
└──────────────┘  └───────────────┘  └──────┬──────────────────┘
                                            │
              ┌─────────────────────────────┼──────────────────┐
              │                             │                  │
      ┌───────▼────────┐         ┌──────────▼──────┐  ┌────────▼───────┐
      │ AGENT WORKERS  │         │ RENDER WORKERS  │  │ MEDIA WORKERS  │
      │ LLM + vision   │         │ Remotion +      │  │ FFmpeg, TTS,   │
      │ calls, schema  │         │ Chromium        │  │ loudness, mux  │
      │ validation     │         │ (CPU/GPU heavy) │  │                │
      └────────────────┘         └─────────────────┘  └────────────────┘
```

Three worker pools, not one. They have completely different resource profiles: agent workers are I/O-bound and cheap to scale, render workers are CPU/GPU-bound and are your latency wall (§15.2), media workers are short and bursty. A single pool means one long render starves twelve cheap LLM calls.

### 6.2 The orchestrator — and why not Temporal

This is the most consequential engineering choice in the document after the render engine, and v3 did not mention it.

**Recommendation: a custom orchestrator over Postgres. Roughly 800–1,200 lines. Not a workflow engine.**

The reasoning: durable-execution frameworks (Temporal, Prefect, Airflow) solve "resume a long workflow after a crash." You are already solving that, and solving it better, with content-addressed artifacts — a crashed run resumes because every completed step is a cache hit, not because a framework replayed an event log. Adopting Temporal means maintaining two sources of truth about what has run, and fighting the framework every time hash-based skip logic disagrees with workflow state.

What you actually need is small:

```
resolve(video_id, target_stage):
    dag   = build_dag(video)              # from stage deps + beat list
    for node in topological_order(dag):
        h = compute_hash(node)
        if artifact_exists(h) or beat_locked(node):
            mark_cached(node); continue
        enqueue(node, pool=node.pool, priority=video.priority)
```

Plus a `jobs` table with `SELECT ... FOR UPDATE SKIP LOCKED` for worker pickup, a heartbeat column, and a reaper for dead workers. That is the whole thing.

**Revisit at:** more than ~30 concurrent videos, or the moment you need cross-service transactional guarantees. Neither is true before Phase 9.

**If your team already runs Temporal in production**, use it — familiarity beats elegance. Make the artifact store authoritative for *whether work is needed* and let Temporal own *retries and timeouts only*.

### 6.3 Data model

Minimum viable schema. Names are indicative.

```sql
series          id, slug, title, owner_id, curriculum_yaml, curriculum_version,
                audience_level, locale, brand_version, status, created_at

videos          id, series_id, video_id (v1/v2…), title, status,
                current_stage, brand_version, priority, published_at

beats           id, video_id, ordinal, beat_id (b07), locked bool,
                locked_hash, role, load_score, created_at
                -- ordinal is mutable (reorder); beat_id is stable forever

artifacts       hash PK, kind, video_id, beat_id nullable, storage_uri,
                bytes, mime, cost_usd, duration_ms, model_version,
                prompt_version, code_version, created_at
                -- hash is the primary key. Same content = one row, ever

artifact_edges  parent_hash, child_hash          -- the invalidation graph

jobs            id, video_id, node_key, pool, state, attempts, priority,
                worker_id, heartbeat_at, error, started_at, finished_at
                -- state: queued|running|succeeded|failed|escalated|cancelled

gate_sessions   id, video_id, gate (0|a|b|c), user_id,
                opened_at, closed_at, active_seconds,   -- S2 lives here
                sections_reviewed jsonb, outcome

edits           id, video_id, beat_id, gate, kind (edit|regenerate|reorder|
                lock|template_swap), instruction_text, reason_text,
                before jsonb, after jsonb, accepted bool, created_at
                -- this table IS the preference dataset (§10.5)

templates       id, name, version, param_schema jsonb, min_sec, max_sec,
                supports_signaling, golden_frame_uri, compile_failures,
                uses_count

brand_versions  semver PK, tokens jsonb, motion jsonb, audio jsonb,
                caption jsonb, thumbnail jsonb, wcag_report jsonb, created_at

lexicon         term PK, spoken_form, locale, added_by, source_video_id,
                created_at

prompt_versions name, version, body, model_hint, created_at, git_sha

eval_runs       id, trigger (prompt_bump|manual|nightly), golden_set_version,
                hash_diff jsonb, scores jsonb, reviewer_correlation,
                created_at
```

Two design notes that matter:

1. **`artifacts.hash` is the primary key, globally.** Two videos that happen to produce an identical title card share one row and one render. This is where a meaningful slice of S5's cost curve comes from, and it is free if you get the key right on day one.
2. **`beats.ordinal` is mutable but `beats.beat_id` is not.** Reordering at Gate B must not change beat identity, or every edit history and every lock breaks. v3's schema implied this; stating it prevents an obvious mistake.

### 6.4 Job states and failure semantics

v3 specified compile-repair (3 attempts, then escalate) and nothing else. Full policy:

| Failure | Retries | Backoff | Then |
|---|---|---|---|
| LLM API 429 / 5xx | 5 | exponential, 2s→60s | escalate |
| LLM schema validation fail | 3 | none — re-prompt with the validation error | escalate with the last invalid output attached |
| Render compile error | 3 | none — feed traceback + scene spec back | escalate to human with error + template name; increment `templates.compile_failures` |
| Render timeout (> 5× template max duration) | 1 | — | escalate; likely an infinite animation |
| TTS provider error | 3 | exponential | escalate |
| FFmpeg non-zero exit | 2 | none | escalate with full stderr |
| Worker heartbeat lost > 120s | ∞ | requeue immediately | job returns to `queued`, attempt count preserved |

**`escalated` is a first-class state, not a failure.** It surfaces in the editor as a card on the video with the error, the offending input, and a "retry / edit input / skip beat" choice. A pipeline that dies silently at 2 a.m. and shows a red dot in a log is a pipeline nobody trusts.

**Partial delivery is allowed.** If beat 9 will not render after escalation, the video assembles without it and Gate C shows a gap marker. Better than a pipeline that produces nothing.

### 6.5 Observability

Per-video trace, cost-attributed, in `manifest.json` and queryable in Postgres:

- **Cost** — every LLM, TTS, and vision call records tokens/characters, unit price, and total, attributed to a stage and beat. Without per-beat attribution, S5 is a total with no explanation.
- **Latency** — wall-clock per stage, queue wait separated from execution time. Queue wait masquerading as slow rendering will mislead you for a month.
- **Cache hit rate** — the health metric for §5. Below ~60% on a re-run means hashing is broken, usually via non-canonical serialization.
- **Human-minutes** — active time in gate sessions, measured with an idle timeout (30s of no interaction stops the clock). A tab left open overnight must not read as 9 hours of review.
- **`compile_failure_rate` per template** — v3 correctly names this the best build-health metric.

Logging: structured JSON, one line per job transition, `video_id` and `beat_id` on every line. Grafana or equivalent from Phase 3 — early enough to catch the curve bending, not so early it's a distraction.

### 6.6 Environments and prompt lifecycle

- **Three environments:** local dev, staging (full pipeline, cheap models, golden set only), production.
- **Prompts are code.** They live in git under `prompts/`, are reviewed in PRs, and are versioned. There is no prompt-editing UI in v1 — the moment prompts become editable at runtime, the artifact hash lies and regression testing becomes meaningless.
- **Changing a prompt** bumps its version → invalidates downstream hashes → triggers a golden-set hash-diff → shows exactly which videos would change → you render only those and compare rubric scores. This loop (§14.4) is how the system improves. It is the closest thing here to "training."
- **Model version pinning.** Model IDs are pinned in config, never "latest." When a provider deprecates a version, that is a deliberate migration with a regression run, not a surprise on a Tuesday.

### 6.7 Security and access

Internal tool, so keep this proportionate:

- SSO against your existing identity provider. Two roles: **editor** (can approve/publish) and **contributor** (can run and edit, cannot publish).
- Object store is private; the editor serves media through short-lived signed URLs.
- Source corpus (§2.2 D10) may contain licensed textbook material — store it in a separate bucket, never include raw excerpts in published artifacts, and keep `sources.md` to citations rather than quotations.
- Per-series API cost cap with a hard stop, because a runaway loop against a frontier model is a real and boring way to lose money.

---

## 7. Build vs. buy

v3 named no vendors and no boundaries. This is where teams lose a month.

| Component | Decision | Choice | Why |
|---|---|---|---|
| LLM inference | **Buy** | Frontier API for research/ID/reviewer, mid-tier for script/storyboard/sound | Not the bottleneck (§15.2). Do not self-host |
| Vision / VLM | **Buy** | Same provider where possible | Keyframe verification is low-volume |
| TTS | **Buy** | Bake-off in Phase 0 across 3 providers | Highest-frequency quality failure (§12.1). Worth real evaluation time |
| Render engine | **Buy the framework, build the templates** | Remotion | Templates are your compounding asset (§10.1 below) |
| Render compute | **Build then buy** | Local Phases 2–8, Remotion Lambda from Phase 9 | Do not build render infra before you have something worth rendering |
| Orchestration | **Build** | Custom over Postgres (§6.2) | Your invalidation model already is the orchestrator |
| Artifact store | **Build over S3/R2** | Thin content-addressed layer | ~300 lines. Nothing off-the-shelf fits the hash closure |
| Audio mixing | **Buy the tools, build the chain** | FFmpeg + `ffmpeg-normalize` / `pyloudnorm` | Deterministic, free, well understood |
| Music | **License** | Epidemic Sound class, curated palette | Legal item, not a taste item (§12.2) |
| Editor frontend | **Build** | Next.js + React + Tailwind | It is the product surface. Nothing generic will fit |
| Video player w/ beat timeline | **Buy the base, build the timeline** | Video.js or Media Chrome + custom overlay | Beat-scrubbing is specific to you |
| Eval harness | **Build** | Python, in-repo | Tightly coupled to your hashes and rubric |
| Auth | **Buy** | Existing SSO | Never build auth for an internal tool |
| Observability | **Buy** | Grafana Cloud / Axiom free tier | Sufficient at this scale |

**The three things you are genuinely building** are the artifact/invalidation layer, the template library, and the editor. Everything else is integration. If a week disappears into something not on that list of three, that is the signal to stop and buy.

---

## 8. The editor — new in v4

v3 correctly identified this as ~70% of the engineering and then described the entire product surface in a seven-row table. This section is the specification.

**Design premise:** the editor is not a form over a pipeline. It is a review tool whose only job is to spend the human's 15 minutes as well as possible. Every screen is judged by that.

### 8.1 Screens

| # | Screen | Purpose | Phase |
|---|---|---|---|
| E1 | **Series dashboard** | All series, all videos, status, cost and human-min to date, S5 curve | 4 |
| E2 | **Curriculum editor** (Gate 0) | Edit `curriculum.yaml` as a structured view — concepts, per-video teaches/assumes, callbacks, spine. Agent proposals shown as suggestions to accept/reject | 4 |
| E3 | **Gate A workspace** | Facts + lesson plan + script + 3 hooks on one surface | 4 |
| E4 | **Gate B storyboard** | Scene strip, template swap, reorder/split/merge, per-scene preview | 6 |
| E5 | **Gate C review player** | Video with beat-marked timeline, reviewer findings pinned to timestamps | 6 |
| E6 | **Batch queue** | Same gate section across N videos in one sitting (§8.6) | 9 |
| E7 | **Video detail** | Manifest, artifact tree, cost breakdown, edit history, rubric scores | 5 |
| E8 | **Escalation inbox** | Jobs in `escalated` state with error, input, and recovery actions | 5 |

### 8.2 Gate A workspace — layout

The most important screen in the product. One surface, three panes:

```
┌────────────────────────────────────────────────────────────────────┐
│  v2 · "The dot product, geometrically"        ⏱ 04:12  Gate A      │
│  ⚠ 2 flagged  ·  ✓ 3 sections auto-approved (trusted)              │
├──────────────┬───────────────────────────────┬─────────────────────┤
│ OUTLINE      │  SCRIPT (beats)               │  EVIDENCE           │
│              │                               │                     │
│ ▸ Hook   ⚠   │  ┌─ b01 · hook ────────────┐  │  Beat b07 claims:   │
│ ▸ b01        │  │ [3 candidates ▾]        │  │                     │
│ ▸ b02  🔒    │  │ h2 selected             │  │  c07 ✓ upheld       │
│ ▸ …          │  └─────────────────────────┘  │  "a·b=|a||b|cosθ"   │
│ ▸ b07   ⚠    │                               │  Stewart 8e §12.3   │
│ ▸ …          │  ┌─ b07 ─────────────  load 3│  │  sympy ✓          │
│              │  │ Because the cosine of   │  │                     │
│ ─────────    │  │ ninety degrees is zero… │  │  c11 ⚠ challenger   │
│ FLAGGED (2)  │  │                    [🔒] │  │  dissents           │
│ • c11 fact   │  └─────────────────────────┘  │  → "only true for   │
│ • b09 load 6 │                               │     non-zero vecs"  │
│              │  ┌─ b08 ──────────── load 6 ⚠│  │                   │
│              │  │ …                       │  │  Objective o1 ✓     │
├──────────────┴───────────────────────────────┴─────────────────────┤
│  💬 "make b08 slower and split the second example into its own beat"│
│                                    [Preview change · ~$0.04 · 12s] │
└────────────────────────────────────────────────────────────────────┘
```

Design rules, each with a reason:

- **Flagged items are the entry point, not the top of the document.** The human should be able to review only the two flagged things and approve, without scrolling. Trusted sections collapse.
- **Evidence is adjacent, never behind a click.** A fact check that requires opening a tab does not happen at video 8.
- **The instruction box is always visible and always scoped.** With nothing selected it applies to the video; with a beat selected it applies to that beat.
- **The timer is visible.** Making S2 legible to the person spending it changes their behaviour — this is deliberate.

### 8.3 Edit-with-instruction — the core interaction

This is what makes the tool AI-native rather than form-native, and it is the hardest thing here to make feel good. Spec:

**Contract:** the agent returns a **patch**, never a rewrite. A patch is a list of typed operations:

```json
{
  "ops": [
    {"op": "replace", "beat_id": "b08", "field": "narration",
     "from": "…", "to": "…"},
    {"op": "split",   "beat_id": "b08", "at_sentence": 3,
     "new_beat_id": "b08a"},
    {"op": "set",     "beat_id": "b08", "field": "duration_hint", "to": "slow"}
  ],
  "rationale": "Split at the second example; load was 6, now 3 and 3.",
  "affects": ["b08.script","b08.tts","b08.render","b08a.*","pacing(7,8,9)"],
  "estimated_cost_usd": 0.04,
  "estimated_seconds": 12
}
```

Then:

1. **Preview, always.** Ops render as an inline diff. Nothing applies without an explicit accept.
2. **Per-op accept/reject.** If the agent does three things and you want two, you take two. Whole-patch-or-nothing is what makes people stop using the feature.
3. **Locked beats are refused, visibly.** If an instruction would touch a locked beat, the op is shown greyed with "b02 is locked — unlock to apply." Silently ignoring the lock is worse than failing.
4. **Cost preview before, actual cost after.** Both recorded.
5. **The instruction text is stored** whether accepted or rejected. Rejected instructions are as informative as accepted ones — arguably more.
6. **Failure mode is honest.** If the model cannot express the request as ops, it says so and offers a manual edit. It never silently does something adjacent.

**Latency target: under 3 seconds to preview.** Above roughly 5 seconds people go back to typing manually, and the feature — and with it the S2 hypothesis — dies quietly.

### 8.4 Diff view

- Word-level diff for narration, structural diff for beat order, side-by-side frames for storyboard/render changes.
- **Every regeneration shows a diff against what you last approved**, not against the immediately previous state. After three regenerations you care about drift from the approved baseline.
- Approving without a diff is not approval. No screen in this product has an approve button without one.

### 8.5 The other affordances

| Affordance | Spec | Why |
|---|---|---|
| **Beat lock** | Pin a beat to its current hash; exempt from upstream invalidation (§5.4). Lock icon on every beat, one click, no dialog | How the human protects good work from downstream churn |
| **Regenerate + reason** | Reason field **required**, free text, one line, with 4 quick-pick chips (`too verbose` `wrong tone` `factually off` `boring`) to keep it under 3 seconds | §10.5 preference dataset. A required field people hate is a field people game — chips fix that |
| **Side-by-side candidates** | 3 hooks, 3 thumbnails, 3 titles. Radio selection, no scroll | Picking from 3 is faster *and* better than judging 1 |
| **Reorder / split / merge** | Gate B, drag on the scene strip; also expressible as an instruction | Beat boundaries are semantic (§11.2); the human must be able to move them |
| **Cost preview** | "This change re-runs 4 artifacts, ~$0.30, ~90s" on every mutating action | Makes the invalidation model legible instead of magic |
| **Undo** | Full undo stack per gate session, artifact-backed | Free, given content addressing — the old hashes still exist. Not having it would be a choice |

### 8.6 Progressive trust and batching

Gates are exception handlers, not tollbooths (P2).

- Track `edit_rate` per gate **section** over a rolling 20 videos.
- A section with `edit_rate < 10%` is **demoted to a notification** — auto-approved, still logged, still auditable, one click to open.
- **Flagged items always surface** regardless of trust: challenger dissent, load-budget violation, prerequisite gap, `template_gap`, low-confidence claim, `known_issues[]` from feedback.
- Trust is per *section*, not global, and **resets on a prompt-version bump for that stage.**
- **Batch across videos, not within one.** Reviewing 10 videos' fact sheets in one sitting is far cheaper per unit than 10 separate context loads. E6 provides this.

**v4 addition — a trust floor.** Even a fully trusted section is force-surfaced on a random 1-in-10 videos. Without it, trust decays into blindness: a stage silently degrades after a model update, `edit_rate` stays at 0 because nobody is looking, and you find out at video 40. The sampling costs about a minute and is the cheapest insurance in the document.

### 8.7 Accessibility of the editor itself

Keyboard-first, because this is a tool used for hours: `j`/`k` between beats, `a` approve section, `e` focus instruction box, `l` lock, `⌘↵` apply. Full screen-reader labelling on diffs. This is not a nice-to-have — an editor that requires the mouse for every action cannot hit 15 minutes.

---

## 9. Agent quality and the cold start — new in v4

v3's quality mechanism was the preference dataset, which does not exist until roughly video 30. That leaves videos 1–30 unexplained, and those are the videos that decide whether anyone keeps using the thing.

**First, the framing correction: you are not training models. You are engineering context.** No fine-tuning appears anywhere in this plan, and that is deliberate — it is the wrong tool at this scale, you do not have the data, and it would freeze quality against a model generation that will be obsolete before you finish.

### 9.1 The four levers, in order of value

**1. Structured output contracts.** The single biggest quality lever, and it is engineering, not prompting. Every agent returns JSON validated against a schema; validation failure re-prompts with the specific error. An agent that must fill `{"load": {"new_symbols": int, "new_terms": int, "score": int}}` is forced to actually count, and its output is checkable by code. Free rigour.

**2. Task decomposition.** Already done — 12 narrow agents instead of one. A narrow agent with one job and a schema beats a clever prompt every time.

**3. Context engineering.** What each agent *sees* matters more than how it is *asked*. Concretely:
   - Research sees the closed corpus and `known_issues[]`, not the open web.
   - Instructional Design sees `curriculum.yaml`, `audience_level`, and what prior videos actually taught — not a topic string.
   - Script sees the lesson plan, verified facts, the lexicon, the house-style guide, and 3–5 few-shot beats from your gold corpus.
   - The Emergent Reviewer sees the rubric and `verified_facts.json` but **not** the generator's reasoning. Fresh ≠ amnesiac; a reviewer without the fact sheet can only check plausibility.

**4. Few-shot examples.** Highest leverage per token, and the reason §9.2 exists.

### 9.2 Solving the cold start — the seed corpus

Before any agent runs in anger, a human produces a small gold corpus. **This is Phase 0 work and it is not optional.**

| Asset | Quantity | Who | Serves |
|---|---|---|---|
| **Gold scripts** | 3 complete, hand-written, 8–14 beats each | Editorial owner + SME | Few-shot examples for the Script agent; the standard everything is measured against |
| **Gold lesson plans** | The same 3, written *after* the scripts, reverse-engineered | Editorial owner | Few-shot for the ID agent; also proves the schema can express real teaching |
| **Reference videos** | 3 — hand-made, or existing videos you would be proud to have made | — | Ceiling calibration for the rubric; the B-side of S3's blind A/B |
| **House style guide** | ~1 page | Editorial owner | Injected into every writing agent's prompt. Voice, person, sentence length, what you never say |
| **Anchored rubric** | 6 dimensions × 5 levels, written anchors | Editorial owner | §14.2. The ruler |
| **Seed lexicon** | 30–60 entries | SME | §10.2. Starts non-empty because technical TTS is reliably wrong |

Writing three scripts by hand feels like a detour when the entire point is not writing scripts by hand. It is the highest-leverage week in the project. **Without a gold standard, every downstream judgement — the rubric, the critics, the reviewer, your own gate decisions — is calibrated against nothing.**

### 9.3 The improvement loop — the real "training"

```
   observe            diagnose             change              verify
 ─────────────      ─────────────       ─────────────      ──────────────
 rubric scores  →   which dimension  →  edit the prompt →  hash-diff golden
 gate edit_rate     is scoring low?      / add few-shot     set → re-render
 escalations        which agent?         / tighten schema   only changed →
 reviewer finds     which stage?         / add template     compare scores
        ▲                                                          │
        └──────────────────────────────────────────────────────────┘
                       accept if scores improve, revert if not
```

Properties that make this real rather than vibes:

- A prompt change is a versioned commit that automatically triggers a regression run.
- The hash diff shows what *would* change before you spend money rendering.
- Improvements are accepted on measured rubric deltas, not on the change feeling better.
- Reverting is one commit, because prompts are code.

**Cadence:** weekly during Phases 3–8, then per-change.

### 9.4 The preference dataset — where v3's mechanism kicks in

From Phase 4 the `edits` table accumulates. Every `Regenerate` requires a one-line reason; every `Edit` stores `(before, after, stage, beat_id, instruction, accepted)`.

After ~30 videos this is a few hundred labelled examples of your specific taste. It feeds:

- **Few-shot rotation** — the 5 most relevant recent accepted edits injected into the relevant agent's prompt, selected by embedding similarity to the current beat.
- **Rubric refinement** — recurring rejection reasons that the rubric does not name are rubric gaps.
- **Trust decisions** — `edit_rate` per section drives §8.6.

A "Regenerate" button with no reason field throws away the most valuable signal the product generates. This was v3's sharpest observation and it survives intact.

### 9.5 When fine-tuning would actually make sense

Not before ~200 videos, and then only for **cost, not quality**: distil the Script and Storyboard agents (high frequency, narrow task, abundant in-domain examples) into a small fine-tuned model to cut per-video cost. Research, ID, and the Reviewer stay frontier — they are low-frequency and need the reasoning.

Explicitly **not** on the roadmap. Listed so nobody proposes it in month two.

### 9.6 Agent roster

| Agent | Job | Tier | Notes |
|---|---|---|---|
| **Curriculum Planner** | Proposes series arc, concept IDs, teaches/assumes, callbacks | frontier | Proposes only; never silently mutates the file |
| Research | Claims + sources + CAS/doc checks | frontier + retrieval | Closed corpus (D10) |
| **Fact Challenger** | Prompted to *refute* each claim | frontier | Asymmetric framing: a verifier confirms, a refuter finds |
| Instructional Design | Lesson plan, CTML-grounded, load-budgeted, objectives + CFU | frontier | §10 |
| **Pedagogy Critic** | Load spikes, prerequisite gaps, framework misuse | mid-high | Parallel, adversarial |
| Script | Draft → self-critique for flow/voice/callbacks → 3 hook variants | mid-high | Absorbed Hook Specialist + Continuity Pass |
| Brand *(once)* | 5 brand systems (§10.4), WCAG-checked, semver | mid + vision, heavy human edit | Human authors, agent assists |
| Storyboard | Typed template selection + transitions + variety + signaling map | mid | |
| **Visual/Brand Critic** | Compliance, legibility, variety, signaling correctness | mid + vision | Parallel |
| Renderer | Typed templates, compile-repair, keyframe verify | code + vision | §13.2 |
| Pacing | Duration match + pause insertion | **code, no model** | §8.5 of v3 — committed to code |
| Sound Design | Curated palette, ducking, SFX budget, LUFS | mid + DSP | §12.3 |
| Emergent Reviewer | Only what needs a finished video | frontier + vision | §13.4 |
| Finishing & Delivery | 3 thumbnails, styled captions, dual aspect | mid + vision | |
| Feedback | Watch-time **+** comprehension, labelled advisories | rule-based + mid | §12.4 |

12 active agents, 3 of them cheap parallel critics that replaced one expensive late reviewer. Cut from v2 and not returning: Diffusion Clip, Render Router, Hook Specialist, Script Continuity Pass.

---

## 10. Compounding assets (P4)

Versioned, human-owned or human-curated, and the reason video 50 is cheaper than video 1. **Each has a named owner and a growth mechanism.** An asset without a growth mechanism is just a file.

### 10.1 Scene template library — target ~15 by Phase 5

Agents **do not write freehand render code.** They select a template and fill a typed schema. This is simultaneously the determinism fix, the brand-compliance fix, the compile-failure fix, and a compounding asset.

Starter set, re-cut in v4 for concept/technical content rather than v3's math-first list:

`title_card` · `bullet_build` · `labeled_diagram_reveal` · `process_flow` · `side_by_side_compare` · `table_build` · `code_walkthrough` (syntax-highlighted, line-by-line reveal) · `terminal_replay` · `axis_plot` · `data_table_to_chart` · `callout_overlay` · `pan_zoom_across` (Ken Burns over large diagrams) · `worked_example_steps` · `recap_strip` · `question_hold` (deliberate pause-and-think beat)

`equation_build` and `equation_transform` are added only if a quantitative series demands them — and if they become frequent, that is the measured failure that would justify revisiting D5.

Each template ships with: a typed param schema, a golden-frame test, declared max/min duration, brand-token bindings, and a `supports_signaling` flag.

**Owner:** motion designer. **Growth mechanism:** when the Storyboard agent cannot express a scene it emits `template_gap` with a spec; the human decides whether to build it. Every template added makes all future videos cheaper.

### 10.2 `lexicon.json` — pronunciation, forever

Human-owned. SSML/phoneme overrides, non-empty on day one because technical TTS is reliably wrong. For a technical/business curriculum the seed set is acronyms, product names, and code tokens rather than mathematical notation:

```json
{
  "SQL":      "sequel",
  "JOIN":     "join",
  "O(n log n)": "big oh of n log n",
  "PostgreSQL": "post-gres-Q-L",
  "df":       "data frame",
  "k-NN":     "k nearest neighbours",
  "CI/CD":    "C I C D",
  "i18n":     "internationalisation",
  "%":        "percent",
  "≈":        "approximately"
}
```

**Owner:** SME. **Growth mechanism:** every pronunciation error caught at Gate C or by the reviewer becomes a lexicon entry *before the fix is accepted*. Errors are permanently retired, not re-fixed per video.

### 10.3 `curriculum.yaml` — the concept graph, human-owned

**The atomic unit of this product is the series, not the video.** v2 generated a video then tried to reverse-engineer continuity from a library. That is backwards, and it made the continuity checker the hardest component in the system while calling it lightweight.

**In:** domain, audience level, series length, locale. **Out:** `curriculum.yaml` — agent-proposed, human-edited, human-owned.

```yaml
series: sql-for-analysts
audience_level: intermediate
locale: en
concepts:
  sql.join.inner:   {label: "Inner join"}
  sql.join.outer:   {label: "Outer join", aka: ["left join", "right join"]}
  sql.groupby:      {label: "Aggregation with GROUP BY"}
  sql.window:       {label: "Window functions"}
  sql.plan:         {label: "Query plan"}
videos:
  - id: v1
    title: "Joins, and what actually happens to your rows"
    teaches: [sql.join.inner, sql.join.outer]
    assumes: []
  - id: v2
    title: "GROUP BY is a machine that eats rows"
    teaches: [sql.groupby]
    assumes: [sql.join.inner]
    recap:  [sql.join.inner]              # explicit, planned — not discovered
  - id: v3
    title: "Window functions: aggregation without losing rows"
    teaches: [sql.window]
    assumes: [sql.groupby, sql.join.inner]
    callback: {video: v2, asset: rows_collapsing_animation}   # §10.6
narrative_spine: >
  Rows combine → rows collapse → rows keep their identity while still
  seeing their neighbours → the database decides how. Each video ends on
  the question the next one answers.
```

**Why this fixes so much at once:** continuity is trivial because the plan *is* the source of truth. Callbacks become plannable instead of accidental. Recaps are placed by design. Prerequisite conflicts are impossible by construction. Titles and thumbnails become series-consistent. And Phase 3 has real signal on day one.

**Owner:** editorial owner. **Growth mechanism:** the agent proposes new edges as the library grows; the human approves. It never silently mutates the file.

Twenty minutes of human authoring per series, and it is 100% correct — versus an auto-built graph that drifts into synonym soup by video 15.

### 10.4 `brand@semver`

Versioned, not locked. Every manifest records the brand version it rendered against; §5.4 makes bringing old videos forward cheap. Locking bakes in pre-first-output taste forever.

Brand is **not just tokens.** It is five systems:

1. **Visual** — palette, type scale, spacing, stroke weights, layout grid
2. **Motion** — easing curves, standard durations, entrance/exit signature
3. **Audio** — underscore family, SFX palette, voice identity
4. **Caption** — font, position, background treatment, reveal style
5. **Thumbnail/title** — composition grammar, type treatment, series marking

Authored **once by a human with taste** (or one strong agent pass plus heavy human edit), then enforced by code via template bindings. Includes an automated **WCAG AA contrast check** at token generation — cheap, and the difference between "fine on my monitor" and "readable on a phone in daylight."

**Owner:** motion designer + editorial owner.

### 10.5 The preference dataset

Every `Regenerate` requires a one-line reason. Every `Edit` stores `(before, after, stage, beat_id, instruction, accepted)`. Fully specified in §9.4 — listed here because it is an asset, not a feature.

**Owner:** the system, automatically. **Growth mechanism:** every gate session. The only asset here that grows without anyone deciding to grow it, which is exactly why v3 was right to flag that discarding it would be the costliest omission in v2.

### 10.6 Reusable visual assets

The `rows_collapsing_animation` built for video 2 is addressable and callable in video 3. Registered in the series asset index with its template and params, so a callback is a **reference, not a rebuild** — which is also what makes cross-video visual callbacks possible rather than coincidental.

---

## 11. Pedagogical specification

This is what the Instructional Design agent's prompt encodes.

### 11.1 Mayer's CTML — the principles that matter for this format

| Principle | Implementation |
|---|---|
| **Segmenting** | Beat boundaries at natural conceptual breaks + deliberate pause beats (`question_hold`). Pacing owns pause lengths |
| **Pre-training** | The lesson plan **must** name and label key components *before* explaining the process they participate in. Hard rule for technical content |
| **Signaling** | A field on every beat (`signal: [element_ids]`) that the storyboard maps to visual emphasis and the renderer consumes. The chain from "this is the important part" to "highlight this thing" must be mechanical, not aspirational |
| **Modality** | Explain in narration over visuals; never as on-screen paragraphs |
| **Coherence** | Enforced by cutting decorative visuals — and why diffusion B-roll was cut (§13.3) |
| **Redundancy** | Resolved in §11.5 |
| **Spatial/temporal contiguity** | Labels adjacent to referents; narration synced to the visual moment (stage 7 guarantees this) |

### 11.2 Cognitive load — weighted budget, semantic boundaries

CLT is about *working-memory* load. It says nothing about one new term per segment, and **splitting tightly-related elements across beats increases load** (split-attention effect) by forcing the learner to hold partial state across a boundary. A worked example introducing three related ideas *together* in one coherent beat is often lower load than three separate beats.

```
beat_load = 2×(new symbols/syntax) + 1×(new terms) + 1×(new relationships among known elements)
target:   ≤ 4 per beat
hard cap:   6  → agent must justify in the plan; surfaces as a flag at Gate A
```

**Beat boundaries are chosen semantically, not by load counting.** Load is a budget to respect, not a splitting algorithm.

Flow, voice, and callbacks are a **self-critique pass inside the Script agent**, not a separate stage. Two agents fighting each other's constraints produces inconsistent output forever, because neither can win.

### 11.3 Worked examples — gated on audience level

The **expertise reversal effect** is real: worked examples help novices and actively *hurt* advanced learners, who do better generating solutions themselves. `audience_level` is a **required** field in `curriculum.yaml`.

| `audience_level` | Strategy |
|---|---|
| `novice` | Full worked example → faded → independent |
| `intermediate` | Faded example → independent, brief |
| `advanced` | Pose the problem first; generation before exposition; skip the worked example |

Per D1 the default is `intermediate`. This single field is why D1 is a blocking decision.

### 11.4 Learning objectives + CFU items — making pedagogy falsifiable

The ID agent emits `learning_objectives.json` alongside the lesson plan:

```json
{
  "objectives": [
    {"id": "o1", "text": "Predict the row count of an inner join",
     "concept": "sql.join.inner", "bloom": "apply"}
  ],
  "misconceptions_targeted": [
    "Learners often assume a join returns at most as many rows as the left table"
  ],
  "cfu_items": [
    {"objective": "o1",
     "q": "Table A has 3 rows, B has 2 rows, all keys match. Inner join row count?",
     "answer": "6", "distractors": ["3", "2", "5"]}
  ]
}
```

This ships **even if nothing consumes it yet**, because it is what makes the ID agent falsifiable (P1) and what S4 measures. `misconceptions_targeted` also gives the reviewer something concrete to check against.

Per D6 these items are delivered through your own platform, which is what makes S4 real.

### 11.5 Resolving the redundancy ↔ captions contradiction

Mayer's **redundancy principle** says on-screen text duplicating narration hurts learning. The Finishing agent produces burned-in captions. Both cannot silently be true.

1. **Captions are an accessibility and sound-off provision.** They override the redundancy principle for that use case. A deliberate, stated exception.
2. **Pedagogical on-screen text is keyword-only signaling — never a verbatim transcript.** Labels, key terms, code being discussed. If on-screen text ever equals what the voice is saying, that is a violation.
3. Captions are **rendered as a separable layer**, so the caption-off export is genuinely redundancy-compliant.

Written into both the Storyboard and Finishing agent prompts.

### 11.6 Accessibility & localization

Cheap to build in now, expensive to retrofit — particularly localization, where the failure mode is discovering that on-screen text is baked into renders.

| Requirement | Spec | Enforced at |
|---|---|---|
| Caption reading speed | ≤ 17 CPS; split lines rather than compress | Finishing + reviewer |
| Contrast | WCAG AA on all brand token pairs, checked at token generation | §10.4 |
| Flashing content | No luminance flash > 3 Hz | Template golden-frame tests |
| Mobile legibility | Min type size verified against a 5" viewport in keyframe verification | §13.2 |
| **Localization readiness** | On-screen text is a **template parameter, never baked into a render**. `locale` in every artifact hash from Phase 1 | Schema + templates |
| Audio description viability | Visual-heavy beats flagged `visual_only: true` so a described variant is possible later | Storyboard |

**On D7:** the expensive artifacts — curriculum plan, lesson plan, storyboard, renders — are language-independent. Only script, TTS, and captions vary by locale. A Hindi/Hinglish edition is therefore *cheap* under this architecture and near-impossible without it. Even shipping EN only, the Phase 1 cost is putting `locale` in the schema and keeping text out of render code.

---

## 12. Audio specification

The highest-impact "premium feel" lever, and the place a channel lives or dies in week one.

### 12.1 TTS — your highest-frequency quality failure

| Requirement | Spec |
|---|---|
| **Pronunciation** | `lexicon.json` (§10.2), applied pre-synthesis. Non-negotiable |
| **Prosody** | Emphasis on `signal[]` words; pause length at beat boundaries is a pacing input |
| **Version pinning** | Voice ID **and model version** pinned and recorded per video. Providers update silently — video 40 will not match video 1, and without pinning you cannot tell why |
| **Voice chain** | De-ess → EQ → light compression → limiter. Does more for "premium" than adding music, and costs nothing |
| **Caching** | Content-addressed by (text + voice + version). A beat edit costs one beat of TTS |
| **Selection test** | Trial 3 providers on the *same deliberately hard script* — acronyms, code identifiers, numbers with units, list intonation. Judge on **technical pronunciation and prosody-under-emphasis**, not on how pleasant the voice sounds reading prose |

### 12.2 Music — a licensing decision, not a taste decision

Generated music has murky provenance and shifting rights terms; library music has clear terms but subscription cost and per-platform restrictions. For an organisation publishing educational content at volume, this is a legal item.

**Decision: licensed library music** (Epidemic Sound / Artlist / Musicbed class), with a **curated 5–8 track palette per tone**, registered in `brand.audio`. Clear rights, and it makes the library sound more *coherent* than per-video generation would. Generated music is out of scope pending a rights review.

### 12.3 Mix spec

| Parameter | Value |
|---|---|
| Integrated loudness (16:9) | **−14 LUFS** (dialogue-anchored) |
| Integrated loudness (9:16) | **−16 LUFS** |
| True peak | **≤ −1 dBTP** |
| Music bed under narration | **−16 dB**, sidechain-ducked (attack 80 ms, release 400 ms) |
| Music bed in gaps | −22 dB floor, no full silence |
| **SFX budget** | **≤ 1 per 15 s**, and **none on beats with `beat_load ≥ 5`** |
| Batch consistency | Loudness verified across the whole series, not per-video |

The SFX budget matters: an agent told "place SFX on transitions and reveals" will place them on *every* transition and reveal, and the result sounds like a mobile game. A whoosh during the hardest beat is a coherence-principle violation with extra steps.

### 12.4 Feedback loop — engagement is not learning

The most consequential error available here is wiring the only closed feedback loop to watch-time. The one signal that reshapes the system over time would then optimise for retention, not comprehension.

These are sometimes **inversely related.** Fluency is the classic trap — a smooth, fast, beautiful explanation feels great, gets watched to completion, and produces *worse* retention than a slower one that forces the learner to generate. Desirable difficulty, the generation effect, and seductive details all point the same way. A watch-time-only loop would systematically strip out every pause, every "try this yourself," and every deliberate slow build, because each creates a drop-off dip. In eighteen months you would have competent, forgettable content, and the ID agent would be expensive decoration justifying decisions the analytics already made.

**The loop:**

1. **Two signals:** watch-time/retention **and** comprehension (S4, via §11.4 CFU items or an LMS quiz delta).
2. **Drop-off and re-watch are distinguished.** A dip at 0:45 is ambiguous — "boring," or "this is the hard part and they rewound." A re-watch spike is a *difficulty* signal, and the right response is usually "add a recap," not "cut it."
3. **Hard constraint, written into the agent's prompt:**
   > **Watch-time data may never be the sole justification for a pedagogical change.** A proposed change that reduces a comprehension objective requires human sign-off at Gate A.
4. Output is a labelled `known_issues[]` fed to Gate A of the next revision — advisory, never auto-applied.

---

## 13. Render specification

### 13.1 One engine — Remotion

v2's "Render Router → Manim + Remotion" was one line describing a genuinely hard subsystem, with routing logic never specified. Who picks the engine per scene? What happens when a Manim scene cross-dissolves into a Remotion scene? Are brand tokens *truly* identical across two independent renderers — font metrics, easing curves, colour management and gamma, frame rate, anti-aliasing, subpixel text? In practice no, and the mismatch is visible. It also breaks match-cuts, which require a shared element pixel-registered in two coordinate systems.

**Decision (D5): Remotion.** Reasoning:

- Content per D1/D9 is concept, framework, code, and data — typography, layout, and code presentation dominate. That is Remotion's home ground and Manim's weak spot.
- Brand as five systems (§10.4) is enforceable through CSS tokens and React props. In Manim, brand consistency is hand-maintained per scene.
- The hiring pool is React developers, which you almost certainly already have. Manim expertise is scarce and mostly academic.
- The editor is a web app. Sharing a rendering vocabulary between preview and final render is worth a great deal at Gate B.

**Cost of the choice, stated honestly:** equation-heavy animation is materially harder in Remotion. If a future series is genuinely mathematical, the honest options are a Manim-rendered asset imported as video into a Remotion composition (a bounded exception, not a second engine), or accepting simpler equation treatment. A second full engine requires a **measured, named failure** (P5).

### 13.2 Compile-repair + visual verification

**More projects of this kind die here than anywhere else.** An LLM writing render code produces code that fails to compile, uses a deprecated API, silently renders objects off-canvas, overlaps two labels into illegibility, or animates for 4 s when the narration needs 11.

Three mitigations, in order of value:

1. **Templates over freehand codegen** (§10.1). The agent selects a template and fills a typed schema. This removes most of the failure class rather than handling it. *This is the actual fix.*
2. **Compile-repair loop.** On exception: feed traceback + scene spec back, max 3 attempts, then escalate to the human with the error (§6.4). Log `compile_failure_rate` per template — the single best build-health metric.
3. **Keyframe visual verification.** Extract 2–3 keyframes per scene, hand to a vision model with the scene's declared intent: *"does this frame show what was specified? is any text clipped, overlapping, or unreadable at 5-inch scale? is the signalled element actually emphasised?"* Cheap, and plausibly delivers more perceived-quality gain than the entire sound-design stage — because nothing else looks at the pixels until a human does at Gate C.

### 13.3 Diffusion B-roll — cut, not deferred

The decisive argument is not cost. It is that B-roll gets scoped to "non-content-bearing scenes only," and **non-content-bearing scenes are exactly where Mayer's coherence principle says put nothing.** Decorative visuals during explanation measurably hurt learning (seductive details). The feature would be scoped to precisely the place where it does the most harm, at the highest cost and lowest brand consistency in the system.

**Replaced by:** `pan_zoom_across`, typographic title cards, and a small curated stock library. Removes an agent, a gate, and a class of cost and nondeterminism.

Kept as a one-line someday note: *hooks and cold opens only, post-Phase-9, if ever.*

### 13.4 Emergent Reviewer — narrow by design

Checks **only** properties that genuinely require a finished video:

- A/V sync drift
- Does the visual at t=32 s match what the narration says at t=32 s (VLM, sampled)
- **Pronunciation QA** — failures become lexicon entries (§10.2)
- Loudness compliance (−14 LUFS ±0.5, true peak ≤ −1 dBTP)
- Caption timing and reading speed (≤ 17 CPS)
- Finish quality: does this feel finished

Everything else moved upstream to the stage that can cheaply fix it (P3).

**Context:** it receives the rubric (§14.2) and `verified_facts.json`. It does **not** receive the generator's reasoning. Fresh ≠ amnesiac — a reviewer without the fact sheet can only check plausibility, not accuracy.

**Output is structured and adjudicated,** never prose:

```json
{"severity": "blocker|major|advisory",
 "dimension": "sync|visual_match|pronunciation|loudness|captions|finish",
 "timestamp": 32.4, "beat_id": "b07",
 "claim": "Narration says 'left join' while the diagram shows an inner join",
 "suggested_fix": "regenerate b07 render with join_type=left"}
```

`blocker` blocks delivery. `advisory` surfaces at Gate C without blocking. An unstructured prose review is unactionable and will be ignored by video 5.

### 13.5 Transition grammar & variety budget

- Every scene node declares its transition to the next: `hard_cut` | `cross_dissolve` | `match_cut{shared_element}` | `wipe_reveal`.
- **Variety budget:** the same template may not fire more than **2 times consecutively**; the agent must substitute or justify, and a justification surfaces as a Gate B flag.
- `match_cut` requires both scenes to share a registered element — trivially satisfied given one engine.

---

## 14. Eval infrastructure — built before the thing it judges

**Build the ruler before you measure.** Without a golden set, a rubric, and ground truth, S1–S5 are unmeasurable and "quality" is a vibe with a decimal point.

### 14.1 Golden set — 10 topics

- 6 conceptual/technical, 2 code-heavy, 2 deliberately nasty: one with well-known learner misconceptions, one containing a contested or frequently-misstated fact.
- At least 4 drawn from a single series, so Stage 0 continuity is exercised.
- **3 reference videos** — hand-made, or existing videos you would be proud to have made. This is your **ceiling calibration**; without a reference, "good" has no scale and S3 has nothing to A/B against.

### 14.2 Anchored rubric — 6 dimensions × 1–5

An unanchored 1–5 scale is noise. Every level needs a written anchor and, where possible, a golden-set example.

| Dimension | 1 | 3 | 5 |
|---|---|---|---|
| Factual accuracy | Any error | Correct, thin sourcing | Correct, per-claim sourced, verified where checkable |
| Instructional soundness | No discernible sequence | Reasonable order, load spikes | Framework-justified, load-budgeted, prerequisites honoured |
| Narrative coherence | Disconnected facts | Ordered but flat | Hook pays off, callbacks land, single through-line |
| Visual craft | Static/repetitive/illegible | Clean, some repetition | Varied, purposeful transitions, signaling reinforces meaning |
| Audio craft | Inconsistent levels, TTS artifacts | Clean narration, no design | Mastered, ducked, restrained SFX, correct pronunciation |
| Finish | Raw render | Captions + thumbnail present | Publish-ready, both aspect ratios, series-consistent |

### 14.3 Reviewer calibration

You score 10 golden-set videos. The Emergent Reviewer scores the same 10, blind. **Measure agreement.**

- Correlation ≥ 0.7 → the reviewer is usable as a gate.
- Below 0.7 → the reviewer is decoration, and you need to know that **before Phase 9**, not after shipping 20 videos it approved.
- Re-run calibration on every reviewer prompt-version bump.

### 14.4 Regression harness

Every prompt/template/code change re-runs the golden set. Because of §5.2 the first pass is a **hash diff** — you see which artifacts *would* change before spending anything on rendering. Then render only the changed ones and diff scores.

**Tracked per video in `manifest.json`:** `fact_error_count` · `edit_rate` per gate section · `human_minutes` · `beats_regenerated` · `compile_failure_rate` per template · `template_gap` count · `cost_usd` · `wall_clock_min` · `cache_hit_rate` · `retention_15s` · `comprehension_rate`

The first five are build-health metrics. Watch **`compile_failure_rate` and `human_minutes`** most closely — they are the two that predict whether this ships.

---

## 15. Budgets — first-class constraints

These numbers determine the architecture, not the reverse.

### 15.1 Per-video targets

| Budget | Target | Hard ceiling |
|---|---|---|
| Inference cost | ≤ $6 | $12 |
| Wall clock (machine) | ≤ 30 min | 60 min |
| **Human minutes** | **≤ 15** (video 20+) | 30 |

Confirm all three against Phase 2 measurements before committing to Phase 3.

### 15.2 Where the time and money actually go

| Stage | Tier | Cost | Wall clock |
|---|---|---|---|
| 0 Curriculum Planner | frontier | $$ | 3–5 min *(once per series)* |
| 1 Research ‖ Challenger | frontier + retrieval | $$ | 2–5 min |
| 2 ID ‖ Pedagogy Critic | frontier | $ | 1–2 min |
| 3 Script (+critique, 3 hooks) | mid | ¢ | 1–2 min |
| 4 Storyboard ‖ Visual Critic | mid | ¢ | 1–2 min |
| 5 TTS | — | ¢–$ | 1 min |
| **6 Render** | **code** | **compute** | **10–40 min ← the real latency wall** |
| 7 Pacing | code | ~0 | seconds |
| 8 Sound design | mid + DSP | ¢ | 2 min |
| 10 Emergent Reviewer | frontier + vision | $$ | 3 min |
| 11 Finishing | mid + vision | ¢ | 2 min |

**Read the render row.** Latency is dominated by rendering, not LLM calls. Two consequences:

1. Beat-level invalidation and caching (§5) are worth more to iteration speed than any model choice. Prioritise accordingly.
2. The two-engine decision was more expensive than it looked, on the axis that actually hurts.

Model tier is **not** your bottleneck. Spend less time on D11 than instinct suggests.

---

## 16. Phased delivery plan

**Two sequencing rules govern everything below.**

1. **Build the ruler before the thing it measures** — evals and the gold corpus come first, or you cannot tell whether any later phase worked.
2. **Every phase from 2 onward ends with something you can play** (P6). The most likely way this project fails is six beautiful weeks of infrastructure before anyone watches anything.

Each phase names what it does **not** do. That list is as binding as the deliverables.

---

### Phase 0 — Decide & seed the gold corpus
**2 weeks · editorial owner (full), SME (half), motion designer (half) · no engineers**

The only phase with no code. It exists because everything downstream calibrates against what is produced here.

**Build:**
1. Confirm or overturn every decision in §2. One sitting, written down.
2. **3 gold scripts**, hand-written, 8–14 beats, in the target series (D9).
3. **3 gold lesson plans**, written *after* the scripts, reverse-engineered from them.
4. **3 reference videos** — made, or chosen from work you would be proud of.
5. **House style guide**, ~1 page.
6. **Anchored rubric** (§14.2), 6 × 5 with written anchors.
7. **Golden set** — 10 topics chosen and briefed (§14.1).
8. **Seed `lexicon.json`** — 30–60 entries.
9. **TTS bake-off** — 3 providers on the same deliberately hard script; pin voice + model version.
10. **Brand v1.0.0 draft** — five systems (§10.4), WCAG-checked.
11. AI-disclosure posture written and approved (D14).

**Exit criteria:**
- You can hand two people the rubric and the same video and get scores within 1 point on every dimension.
- A voice is pinned, and someone has listened to it read your hardest paragraph.

**Not in this phase:** any code, any agent, any infrastructure decision beyond D5.

**Why it is first:** writing three scripts by hand feels like a detour when the whole point is not writing scripts by hand. It is the highest-leverage week in the project. Without a gold standard, every downstream judgement is calibrated against nothing.

---

### Phase 1 — Skeleton
**3 weeks · 2 backend engineers**

The foundation that cannot be retrofitted. No agents. No UI. CLI only.

**Build:**
1. Postgres schema (§6.3), including `locale`, `audience_level`, `brand_version`, `model_versions` from day one.
2. Content-addressed artifact store over S3/R2, canonical JSON hashing (§5.2).
3. Beat-level DAG resolution and invalidation (§5.3).
4. Job table, worker pool, `SKIP LOCKED` pickup, heartbeat, reaper (§6.2).
5. Failure and escalation semantics (§6.4).
6. Prompt-version registry, git-backed (§6.6).
7. `manifest.json` writer with cost and timing capture.
8. Local dev environment: one command, everything up.

**Exit criteria:**
- Run a **fake** 4-stage pipeline over 5 fake beats. Change beat 3's input. Confirm: exactly beats 3's downstream artifacts re-run, everything else is a cache hit, byte-identical.
- Kill a worker mid-job. Confirm it requeues and completes.
- Cache hit rate on an unchanged re-run is 100%.

**Not in this phase:** any real LLM call, any real render, any UI, any orchestration framework.

**Why now:** §5 says retrofitting this after Phase 5 is a rewrite. It is three weeks now or three months later.

---

### Phase 2 — Ugly vertical slice · **GO / NO-GO**
**3 weeks · 2 backend engineers + editorial owner (light)**

**One topic. Four beats. Deliberately ugly. End to end to a watchable MP4.**

Research → short script → TTS → two Remotion templates → FFmpeg assembly → **watch it.**

**Build:**
1. Two real agents (research, script) with schema-validated output.
2. Two Remotion templates, hand-written, wired to brand tokens.
3. TTS integration with the lexicon applied.
4. FFmpeg assembly.
5. First real numbers into §15.2 — actual cost, actual wall clock.

**Exit criteria:**
- **An MP4 exists and you have watched it.**
- **A written list of surprises.** This artefact matters more than the video.
- Real measured cost and latency for a 4-beat video.

**Not in this phase:** gates, editor, critics, curriculum, sound design, captions, quality of any kind. Ugly is a requirement, not a tolerance.

**This is the go/no-go.** Eight weeks in, you have a real video, real numbers, and a real surprise list. If the numbers are wildly off §15.1, or the surprise list contains something structural, **stop and re-plan before Phase 3.** That is a success outcome for this phase, not a failure.

**Why text-only would have been the wrong Phase 2:** LLMs producing decent research → plan → script is the *least* uncertain part of this system. The unknown-unknowns all live in render, sync, pronunciation, and does-it-feel-right. Sixty ugly seconds teaches you more than five perfect lesson plans.

---

### Phase 3 — Teaching spine
**4 weeks · 2 backend engineers + editorial owner (half) + SME (quarter)**

Where the actual differentiator (§1.1) gets built. Still no editor — a read-only web view of artifacts is enough.

**Build:**
1. `curriculum.yaml` for the D9 series, **hand-authored first**, then the Curriculum Planner agent that proposes against it.
2. Full Instructional Design agent (§11) with load budgeting and `learning_objectives.json`.
3. Script agent with self-critique and 3 hook variants.
4. Fact Challenger and Pedagogy Critic — parallel, adversarial.
5. Closed-corpus retrieval (D10).
6. Golden-set regression harness (§14.4) and hash-diff runner.
7. Structured logging + Grafana.

**Exit criteria:**
- **Video 3 correctly recaps what video 1 taught, unprompted, from the plan.** This single behaviour is the product thesis; if it does not work, nothing later matters.
- Changing a prompt produces a hash diff naming exactly which golden-set videos would change.
- Load budget violations surface as structured flags.

**Not in this phase:** the editor, storyboard, brand enforcement, audio design.

---

### Phase 4 — The editor, part 1: Gate A
**5 weeks · 1 frontend + 1 backend + designer (half) + editorial owner (light)**

The largest single phase, and the one most likely to be under-scoped. §8 is the spec.

**Build:**
1. E1 series dashboard, E2 curriculum editor, E3 Gate A workspace.
2. **Edit-with-instruction** (§8.3) — patch contract, preview, per-op accept/reject, lock refusal, cost preview. Sub-3-second preview latency.
3. Diff view (§8.4).
4. Beat lock, regenerate-with-reason + chips, side-by-side candidates.
5. `edits` and `gate_sessions` tables live — **the preference dataset starts accumulating here.**
6. Human-minutes instrumentation with idle timeout.
7. SSE job progress.
8. Keyboard shortcuts (§8.7).

**Exit criteria:**
- **A non-engineer takes a video through Gate A without touching a terminal.**
- A stopwatch number for Gate A exists and is written to the manifest.
- Edit-with-instruction preview is under 3 seconds at p90.

**Not in this phase:** Gate B, Gate C, batching, progressive trust.

**Watch for:** this phase slipping to 8 weeks. If it does, cut side-by-side candidates and keyboard shortcuts, never edit-with-instruction or the diff.

---

### Phase 5 — Templates, brand, and visual craft
**4 weeks · 1 backend + motion designer (full) + 1 frontend (half)**

**Build:**
1. **~15 typed templates** (§10.1), each with param schema, golden-frame test, duration bounds, brand bindings.
2. Brand v1.0.0 implemented as code — five systems, semver, WCAG check in CI.
3. Storyboard agent with typed template selection, transition grammar, variety budget.
4. Visual/Brand Critic.
5. **Compile-repair loop** (§13.2) with `compile_failure_rate` telemetry.
6. **Keyframe visual verification** (VLM).
7. E7 video detail and E8 escalation inbox.

**Exit criteria:**
- `compile_failure_rate` **< 5%** across the golden set.
- Visual verification catches a **deliberately broken scene** you plant (clipped text, off-canvas object).
- A brand version bump re-renders only brand-dependent artifacts.

**Not in this phase:** the storyboard editing UI (Phase 6), audio.

---

### Phase 6 — Gate B and Gate C
**3 weeks · 1 frontend + 1 backend + designer (half)**

**Build:**
1. E4 storyboard editor — scene strip, drag reorder, split/merge, template swap, per-scene preview.
2. E5 review player — beat-marked timeline, findings pinned to timestamps, click-to-fix.
3. Fix-from-Gate-C wired to beat-level invalidation, with cost preview.

**Exit criteria:**
- At Gate C, fix one beat and confirm the other beats' renders are **byte-identical** afterwards. Show the hashes.
- Full path from topic to rough cut with three human touchpoints and a measured total human-minutes number.

**Not in this phase:** finishing, thumbnails, dual aspect.

---

### Phase 7 — Audio and finish
**3 weeks · 1 backend + motion designer (half) + editorial owner (light)**

The "feels finished" phase.

**Build:**
1. Pacing as **code** (§9.6) — duration match, pause insertion at beat boundaries.
2. Voice chain: de-ess → EQ → compression → limiter.
3. Licensed music palette, sidechain ducking, SFX budget enforcement.
4. LUFS/true-peak normalisation, verified per series.
5. Finishing: 3 thumbnail candidates, styled captions as a separable layer, transcript, `sources.md` with per-claim→beat map.
6. **16:9 and 9:16 exports** (D6).

**Exit criteria:**
- **The first video you would publish without apologising.**
- Score it on the rubric against a Phase 0 reference video. Note the gap honestly.
- Loudness verified across a 3-video batch, not just one.

**Not in this phase:** the Emergent Reviewer.

---

### Phase 8 — Emergent Reviewer and calibration
**2 weeks · 1 backend + editorial owner (half)**

**Build:**
1. Narrow reviewer (§13.4) — structured findings only, blocker/major/advisory.
2. Findings surfaced in E5, pinned to timestamps.
3. Pronunciation failures auto-proposed as lexicon entries.
4. **Run the §14.3 calibration.**

**Exit criteria:**
- Reviewer/human score correlation **≥ 0.7** on the golden set.
- **If correlation < 0.7, fix the reviewer before Phase 9.** A miscalibrated gate is worse than no gate — it launders bad output as approved.

---

### Phase 9 — Compounding, trust, and scale
**4 weeks, then ongoing · 1 backend + 1 frontend (half) + editorial owner (light)**

Where P4 either proves out or doesn't.

**Build:**
1. Preference dataset wired into prompts — few-shot rotation by embedding similarity (§9.4).
2. **Progressive trust** demotion live (§8.6), including the 1-in-10 trust floor.
3. E6 batch queue — same gate section across N videos.
4. Comprehension signal wired to your platform (S4), CFU delivery and scoring.
5. Feedback loop with the §12.4 hard constraint enforced in the prompt.
6. Remotion Lambda for burst rendering (D12).
7. **Plot S5.**

**Exit criteria:**
- Human-minutes and cost per video are **measurably falling** across videos 5 → 20.
- S1–S5 all measured, not estimated.

**If S5 is flat, stop and fix that before scaling.** A flat compounding curve means you built a pipeline, not a product — and scaling a pipeline just multiplies its costs.

---

### 16.1 Timeline at a glance

```
Wk  1  3  5  8 11 15 20 24 27 30 34
    ├──┤                                Phase 0  Decide & seed        2w
       ├─────┤                          Phase 1  Skeleton             3w
             ├─────┤                    Phase 2  Vertical slice ★     3w
                   ├───────┤            Phase 3  Teaching spine       4w
                           ├─────────┤  Phase 4  Editor / Gate A      5w
                                     ├──────┤   Phase 5  Templates    4w
                                            ├────┤ Phase 6  Gate B/C  3w
                                                 ├────┤ Phase 7 Audio 3w
                                                      ├──┤ Ph 8 Rev.  2w
                                                         ├────┤ Ph 9  4w
★ = go/no-go decision point
```

**~33 weeks, roughly 7.5 months**, to S1–S5 measured with a small team. Phases 4 and 5 can overlap by about two weeks if the frontend and motion designer are separate people.

Two intermediate milestones worth naming to stakeholders:

- **Week 8** — a watchable video exists (end of Phase 2).
- **Week 27** — the first publishable video exists (end of Phase 7).

---

## 17. Team and cost

### 17.1 Roles

| Role | Phases | Load | Why they are non-negotiable |
|---|---|---|---|
| **Editorial owner** | 0–9 | ~50% throughout | D8. Owns the rubric, `curriculum.yaml`, publish veto. Without a named person, gates become theatre |
| **Backend engineer × 2** | 1–9 | full | The artifact layer, orchestration, agents, render integration |
| **Frontend engineer** | 4–9 | full from Phase 4 | The editor is the product surface and ~40% of total engineering |
| **Motion designer** | 0, 5, 7 | full in those phases, ~20% otherwise | Brand as five systems and 15 templates. An LLM cannot originate visual identity — this is the most commonly skipped role and the most visible when missing |
| **SME** | 0, 3, ongoing audits | ~20% | Seed lexicon, corpus curation, S1 blind audits |

**Minimum viable team: 4 people** — editorial owner, 2 backend, 1 frontend — **plus a motion designer for roughly 8 weeks total.** Below that, the schedule stretches rather than the scope shrinking.

### 17.2 Running cost

Infrastructure and services only; salaries excluded since they vary.

| Item | Build phases (monthly) | At 20 videos/month |
|---|---|---|
| LLM + vision inference | $200–600 | ~$120 (20 × ~$6) |
| TTS | $50–150 | $60–200 |
| Render compute | ~$0 (local) | $150–400 (Lambda) |
| Object storage + egress | $20–60 | $80–200 |
| Postgres (managed) | $50 | $100 |
| Music licence | $20–50 | $20–50 |
| Observability | $0–50 | $50 |
| **Total** | **~$350–950/mo** | **~$600–1,100/mo** |

Well under $10/video at volume, against a §15.1 target of $6 inference. The gap is render compute, which is a scaling knob rather than a per-video cost.

**The real cost is the team.** Infrastructure is rounding error, which is worth saying out loud before anyone optimises the wrong number.

---

## 18. Risk register

| Risk | Sev | Mitigation | Owner |
|---|---|---|---|
| Generated render code fails to compile or renders wrong | **High** | Typed templates (§10.1) + repair loop + keyframe verify (§13.2). Track `compile_failure_rate` | Backend |
| **Phase 4 (editor) doubles in scope** | **High** | Named cut list in the phase. Edit-with-instruction and diff are the two things that may never be cut | Frontend |
| Gate fatigue → human stops reviewing carefully → quality regresses invisibly | **High** | 15-min budget (S2), progressive trust (§8.6), **1-in-10 trust floor**, batch queue, `edit_rate` telemetry | Editorial |
| Feedback loop optimises away pedagogy | **High** | Comprehension signal (S4) + hard constraint (§12.4) | Editorial |
| Reviewer miscalibrated; you trust a gate that does not work | **High** | §14.3 calibration before Phase 9; recalibrate on every prompt bump | Backend |
| Editing one beat silently breaks approved beats | **High** | §5 invalidation + beat locking. **Phase 1, not later** | Backend |
| **Cache misses from non-canonical serialization** | **High** | Canonical JSON, `cache_hit_rate` as a monitored metric. Symptom: everything is slow and nobody knows why | Backend |
| **No motion designer allocated** | **High** | §17.1. Brand and templates cannot be produced by agents alone. Most commonly skipped role | Sanket |
| TTS mispronounces technical terms consistently | Med | `lexicon.json` + pronunciation QA + hard-script bake-off | SME |
| Voice/model drift makes the library inconsistent | Med | Version pinning recorded per video (§12.1) | Backend |
| Series aesthetic frozen by first-video taste | Med | `brand@semver` + cheap re-render sweep (§10.4) | Motion |
| Music rights exposure | Med | Licensed library only; generated music out of scope (§12.2) | Editorial |
| Cost/latency blows up at batch | Med | §15 budgets measured in Phase 2; caching (§5) | Backend |
| **Remotion turns out wrong for a future quantitative series** | Med | Bounded exception: Manim-rendered asset imported as video. Never a second engine without a measured failure | Backend |
| `curriculum.yaml` drifts from reality as the library grows | Low | Agent proposes edges, human approves | Editorial |
| Scope creep re-inflates the stage count | Med | **P5.** Additions require a named deletion or a measured failure | Sanket |

---

## 19. Kill criteria and decision reviews

v3 had a risk register but no condition under which you stop. Sunk cost is the real risk in a project this shape, and the only defence is writing the exit conditions down before you are emotionally invested.

### 19.1 Hard checkpoints

| When | Question | Stop / re-plan if |
|---|---|---|
| **End of Phase 2** (wk 8) | Does an ugly video exist, and what did it cost? | Per-video cost > $25 or wall clock > 90 min at 4 beats, **or** the surprise list contains something structural (e.g. Remotion cannot express your content class) |
| **End of Phase 3** (wk 15) | Does video 3 recap video 1 from the plan? | It does not, after two prompt iterations. That is the differentiator (§1.1); without it this is a generic video generator |
| **End of Phase 4** (wk 20) | Gate A human-minutes on a real video? | **> 45 min.** The S2 ramp target for video 5 is 45. Double that at Phase 4 means the trajectory to 15 does not exist |
| **End of Phase 8** (wk 30) | Reviewer/human correlation? | **< 0.7 after one fix round.** Ship without the reviewer as a gate — advisory only — and re-scope |
| **Video 20** | Is S5 falling? | Human-minutes flat across videos 5 → 20. **This is the real kill criterion** |

### 19.2 What "stop" means

Not necessarily abandonment. Three graceful degradations, in order of preference:

1. **Narrow the scope.** Drop the series framing, keep single-video generation with a good editor. Still valuable, much cheaper. Loses the §1.1 differentiator.
2. **Move the human earlier.** If review time will not compress, invert the model: a human writes the script, the system does research support, storyboard, render, audio, and finish. Human-minutes go up, but the *skill* required drops from "instructional designer plus editor plus motion designer" to "subject expert," which may be the better business answer anyway.
3. **Keep the parts that worked.** The artifact/invalidation layer, template library, and audio chain are independently useful even if the agent pipeline is not. None of the Phase 0–2 work is wasted in any scenario.

### 19.3 Scheduled decision reviews

- **Weekly during Phases 3–8:** rubric scores and `human_minutes` on the golden set. Fifteen minutes, two numbers.
- **End of every phase:** exit criteria met, yes or no, written down. A phase that exits without meeting its criteria must record why.
- **Every 10 videos from Phase 7:** plot S1–S5. Any flat curve is an agenda item.

---

## Appendix A — Core schemas

### A.1 `script.json` (beat is the unit)

```json
{
  "video_id": "v2", "locale": "en", "audience_level": "intermediate",
  "brand_version": "1.3.0",
  "hook_selected": "h2",
  "hook_candidates": [
    {"id": "h1", "strategy": "provocative_question", "text": "…", "est_sec": 12},
    {"id": "h2", "strategy": "stakes_first",         "text": "…", "est_sec": 14},
    {"id": "h3", "strategy": "pattern_interrupt",    "text": "…", "est_sec": 11}
  ],
  "beats": [{
    "id": "b07",
    "ordinal": 7,
    "narration": "Every row on the left finds every matching row on the right — which is why three rows and two rows can give you six.",
    "claims": ["c07", "c11"],
    "objective": "o1",
    "signal": ["left_rows", "result_count"],
    "load": {"new_symbols": 0, "new_terms": 1, "new_relationships": 2, "score": 3},
    "role": "worked_example",
    "visual_only": false,
    "locked": false,
    "hash": "b7f3a1c9…"
  }]
}
```

### A.2 `storyboard.json`

```json
{
  "scenes": [{
    "beat_id": "b07",
    "template": "labeled_diagram_reveal",
    "params": {"left_rows": 3, "right_rows": 2, "join_type": "inner",
               "highlight": "cartesian_matches"},
    "signal_map": {"left_rows": "highlight_pulse",
                   "result_count": "scale_in_accent"},
    "transition_out": {"type": "match_cut", "shared_element": "result_count"},
    "duration_target_sec": 8.4,
    "variety_check": {"consecutive_same_template": 1, "ok": true},
    "hash": "9de2f0…"
  }],
  "template_gaps": []
}
```

### A.3 `manifest.json` — what makes S1–S5 measurable

```json
{
  "video_id": "v2", "series": "sql-for-analysts",
  "brand_version": "1.3.0",
  "model_versions": {"research": "…", "id": "…", "script": "…",
                     "tts": "voice_x@2026-06"},
  "artifacts": {"b07.render": {"hash": "…", "cached": true, "cost_usd": 0.0}},
  "metrics": {
    "fact_error_count": 0,
    "edit_rate": {"gate_a": 0.08, "gate_b": 0.22, "gate_c": 0.10},
    "human_minutes": 17.5,
    "beats_regenerated": 2,
    "compile_failure_rate": 0.03,
    "template_gaps": 0,
    "cache_hit_rate": 0.81,
    "cost_usd": 5.10,
    "wall_clock_min": 26,
    "retention_15s": null,
    "comprehension_rate": null
  },
  "rubric_scores": {"factual": 5, "instructional": 4, "narrative": 4,
                    "visual": 4, "audio": 4, "finish": 5}
}
```

### A.4 Deliverables per video

```
out/<series>/<video_id>/
  final_16x9.mp4            1080p, −14 LUFS, −1 dBTP
  final_9x16.mp4            1080×1920, −16 LUFS
  captions.srt              plain
  captions_styled.ass       burned-in variant
  thumbnail_{a,b,c}.png     3 candidates, human picks
  transcript.md
  sources.md                per-claim → beat/timestamp map
  learning_objectives.json  objectives + CFU items
  manifest.json             every artifact hash, model version, brand
                            version, cost, timings
```

`manifest.json` is not bookkeeping — it is what makes S5 and §14.4 measurable.

---

## Appendix B — Glossary

| Term | Meaning |
|---|---|
| **Beat** | The atomic unit of a video. One idea, one narration passage, one scene. 8–14 per video |
| **Gate** | A human review checkpoint. Four exist: 0 (series), A (teaching/script), B (storyboard), C (finished cut) |
| **Artifact** | Any generated output, keyed by a hash of its full input closure |
| **Invalidation** | Determining which artifacts must be regenerated after a change |
| **Beat lock** | Pinning a beat to its current hash so upstream changes cannot disturb it |
| **CFU** | Check For Understanding — a comprehension item shipped with each video |
| **CTML** | Cognitive Theory of Multimedia Learning (Mayer). The pedagogical framework in §11 |
| **Load budget** | The weighted count of new elements per beat. Target ≤ 4, hard cap 6 |
| **Signaling** | Marking which elements matter, so the renderer can emphasise them |
| **Progressive trust** | Auto-approving gate sections whose edit rate has fallen below 10% |
| **Golden set** | 10 fixed topics used for regression testing and rubric calibration |
| **Template gap** | A flag raised when the Storyboard agent cannot express a scene with existing templates |
| **S1–S5** | The five success commitments in §4 |
| **P1–P6** | The six design principles in §3 |

---

## Appendix C — v2 → v3 → v4 history

Retained so the reasoning behind removed features is not re-litigated. **Consult before proposing an addition (P5).**

### C.1 v2 → v3

| v2 element | v3 disposition | Rationale |
|---|---|---|
| Course Continuity Check (auto knowledge graph) | → Stage 0 Curriculum Planner, human-owned `curriculum.yaml` | Auto concept-graph construction is identity resolution plus decay modelling, not "lightweight." A human authors it in 20 min and it is correct |
| Hook Specialist (own agent + gate) | Merged into Script; rubric + 3 candidates | Needed a rubric and a choice, not a stage and a gate |
| Script Continuity Pass (own stage) | Merged into Script as self-critique | It existed to undo the damage of the 1-term-per-beat rule. The rule was fixed instead |
| Gates 2 + 2b + 3 | Merged → Gate A | Same question. Splitting tripled context-switch cost while giving the human *less* context |
| Adversarial Reviewer at stage 15, 5 dimensions | Split → 4 stage-adjacent critics + 1 emergent reviewer | P3. One agent with five hats produces mush |
| Diffusion Clip Agent | **Cut** | Highest cost, lowest control, scoped to exactly where the coherence principle says put nothing |
| Manim + Remotion + Router | **One engine** | Doubles the hardest surface; makes cross-engine match-cuts near-impossible; benefit never measured |
| Brand locked at first run | `brand@semver` + re-render sweep | Locking bakes in pre-first-output taste forever |
| "≤1 new symbol/term per beat" | Weighted load budget ≤4, semantic boundaries | Not what CLT says; caused the disjointedness a whole stage was added to fix |
| Feedback loop on watch-time | + comprehension signal, + hard constraint | Retention ≠ learning, sometimes inversely |
| — | + artifact/invalidation model | Without it, "editable at every stage" is false |
| — | + eval infrastructure | Without it, success is unfalsifiable |
| — | + compile-repair + visual verification | The #1 practical build risk, unmentioned in v2 |
| — | + budgets | They determine architecture, not the reverse |

**Net:** 17 stages → 13, 6+ gates → 3 (+1 amortised), 15 agents → 12.

### C.2 v3 → v4

v3's substance was kept. v4 added the engineering and delivery layers it lacked:

| Gap in v3 | v4 response |
|---|---|
| 8 blocking decisions open while claiming build-ready | §2 — all answered as overridable assumptions |
| No system architecture | §6 — topology, orchestrator, data model, failure semantics, observability |
| No vendor or boundary decisions | §7 — build vs. buy, with the three things you actually build named |
| Editor called 70% of engineering, specified in 7 rows | §8 — screens, layout, the patch contract, latency targets |
| Quality mechanism did not exist until video 30 | §9 — seed gold corpus, context engineering, the improvement loop |
| Phases had no duration, team, or cost | §16–§17 — 10 phases, 33 weeks, named roles, running cost |
| No stop condition | §19 — five hard checkpoints and three graceful degradations |
| Stale cross-references (§14.5 for a decision in §17) | All references rebuilt and verified |
| S2 presented as a target | §4.1 — reframed as the central hypothesis, measured from video 1 |

**The one thing v4 asks you to do that v3 did not:** spend two weeks in Phase 0 writing three scripts by hand before any code is written. Everything downstream is calibrated against them.

---

*End of PRD v4.*
