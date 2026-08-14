# CLAUDE.md

Read this before writing any code in this repo.

## What this is

An AI-native explainer video pipeline. Input: a topic inside a series plan.
Output: a branded, narrated, pedagogically sequenced 1080p MP4, editable at
**beat granularity**, produced inside a stated cost, latency and
**human-attention** budget.

The spec is `docs/prd/Sequence_v0.2.md` — the **anchor document**, and the only
one section references point at. `docs/prd/CHALLENGES.md` sits beside it and
carries the ten irreversible decisions (R1–R8) that migration 0002 encodes.
When this file and Sequence v0.2 disagree, the PRD wins — tell me about the
disagreement rather than silently picking one.

`docs/prd/PRD_v4.md` is **historical**: the superseded Board Infinity PRD. Its
section numbering is different and does not line up with v0.2 — §9.1 is "the
four levers" there and "the Gagné scaffold" here, §5.1 is the artifact model
there and the Scene object here. Read it for background on the invalidation
model only. Never resolve a `§x.y` reference against it.

The differentiator (PRD §1.1): a *pedagogically sequenced series* where video 6
correctly assumes what video 2 taught, that gets cheaper and better with every
video shipped. Every architectural decision serves that. Nothing else does.

**Current state: Phase 1 complete.** The skeleton — schema, content-addressed
store, beat-level invalidation, orchestrator, worker pools, CLI — is built and
its exit criteria pass. No real model calls, no real renders, no UI yet.

## The seven invariants

These are not style preferences. Each one, if broken, breaks something that
cannot be repaired without a rewrite. If a task seems to require breaking one,
stop and say so instead.

**1. Never put `video_id`, `series_id`, timestamps, run ids or worker ids into a
hash closure.** `artifacts.hash` is a global primary key. Two videos that
produce an identical title card must share one row and one render — that is
where a real slice of the cost curve comes from (§6.3). Identity is inputs only.

**2. A handler may only read what its `StageSpec` declares.** Upstream
artifacts, the prompt, `ctx.config` (via `config_keys`), `ctx.beat.inputs` (via
`reads_beat_inputs`), and video fields named in `video_input_keys`. Reading
anything else means the output depends on an input outside the closure, which
means a stale cache hit the moment that field changes. `LocalStore.put` raises
`StoreError` when two different outputs land on one hash — that error always
means this rule was broken, never a real SHA-256 collision. Fix the closure;
never delete the blob to make the error go away.

**3. Beat briefs live in `beats.inputs` rows, never inside a video-scoped
artifact.** If a brief lived in `script_plan`'s output, editing beat 7 would
rehash the plan and invalidate all twelve beats. This is exactly the failure
that §5.1 says kills pipelines like this: the second time the system quietly
changes something a human approved, they stop trusting any output.

**4. `beats.beat_id` is immutable; `beats.ordinal` is mutable.** Gate B reorder
rewrites ordinals only. Key nothing on ordinal — every lock and every edit
history breaks if beat identity moves.

**5. Handler output must be byte-deterministic.** No wall-clock, no `random`
without a seed in the closure, no dict iteration order leaking into output.
Cache hits must be byte-identical or Gate C trust is gone.

**6. Prompts are files in `prompts/`, never runtime-editable.** The moment a
prompt can be edited at runtime the artifact hash lies and regression testing
becomes meaningless (§6.6). No prompt-editing UI in v1. Same rule for model
IDs: pinned in config, never "latest".

**7. `escalated` is a first-class state, not a failure.** A pipeline that dies
silently at 2am and shows a red dot in a log is a pipeline nobody trusts. Every
failure path ends in a recorded state with the error, the offending input, and a
human-actionable next step.

## Architecture in one screen

```
CLI (Phase 1)  →  API + editor (Phase 4+)
                      │
   ┌──────────────────┼───────────────────┐
   │                  │                   │
POSTGRES         OBJECT STORE        ORCHESTRATOR
state, jobs,     content-addressed   DAG resolution
manifests,       blobs (local / S3)  hash → run or serve
edits, evals                        dispatch / retry / escalate
                                          │
              agent workers   render workers   media workers
              (I/O bound)     (the latency     (short, bursty)
                               wall)
```

The orchestrator is ~400 lines over Postgres, deliberately **not** Temporal or
Airflow (§6.2). Durable execution is already solved by content addressing: a
crashed run resumes because every completed step is a cache hit, not because a
framework replayed an event log. Adopting a workflow engine means maintaining
two sources of truth about what has run.

### The one idea worth internalising

A node's hash is computed from its **inputs**, so every hash in the DAG is known
*before anything runs*. That means:

- the whole plan is hashed and enqueued in one pass;
- "invalidation" is not a graph walk that decides what to delete — it is the
  emergent consequence of a changed input producing a hash that has no artifact
  behind it;
- you can show a human exactly which artifacts a change would touch, before
  spending a cent (`explainer diff`, §14.4).

### Two-pass resolution

In the production graph the beat list is an *output* (of `script_plan`). So
`resolve()` runs to `graph.beat_producer`, the handler writes `beats` rows, then
you resolve again to expand beat-scoped stages. `Plan.needs_second_pass` flags
this. Don't try to make it one pass.

## Repo map

```
migrations/0001_init.sql     §6.3 schema. Add new files, never edit applied ones.
prompts/<name>.v<N>.md       Versioned prompts. Bump the filename to bump the version.
docs/prd/Sequence_v0.2.md    THE SPEC. All §x.y references resolve here.
docs/prd/CHALLENGES.md       R1–R8, the irreversible decisions.
docs/prd/PRD_v4.md           Historical. Different numbering — do not cite it.
src/explainer/
  config.py                  Settings + pinned model ids. hashable_config() is the
                             subset that may enter a closure.
  hashing.py                 Canonical JSON + closure_hash. Read the docstring.
  codeversion.py             Per-directory git tree SHA, dirty-aware.
  db.py                      Raw psycopg. No ORM, on purpose.
  store.py                   Content-addressed store: LocalStore / S3Store.
  dag.py                     StageSpec, Node, Graph, the 4 dependency kinds.
  graphs/fake.py             Phase 1 fixture: 4-stage spine over 5 beats.
  graphs/production.py       All 13 real stages, declared; handlers mostly absent.
  stages/base.py             Handler contract. Read before writing a handler.
  stages/fake_handlers.py    Deterministic fixture handlers. Keep them forever.
  orchestrator.py            plan / resolve / hash_diff / lock / edit / reorder.
  worker.py                  Claim, heartbeat, §6.4 retry policy, reaper.
  manifest.py                Appendix A.3 manifest, built from Postgres only.
  verify.py                  Phase 1 exit criteria, executable.
  cli.py                     The Phase 1 interface.
tests/                       Hashing, DAG shape, and the exit criteria.
```

## Commands

```bash
make up                       # postgres + minio via docker compose
make db                       # apply migrations
make verify                   # Phase 1 exit criteria — run this before every commit
make test                     # pytest
explainer doctor              # is postgres/store/prompts reachable
explainer graph production    # every stage: scope, pool, tier, deps, built or todo
explainer resolve S/v1 --dry-run   # plan without enqueueing
explainer diff S/v1           # what a change would touch
explainer run --pools agent,media --drain
explainer jobs S/v1           # escalations first
explainer manifest S/v1
```

## How to add a stage handler

This is the main loop of Phases 2–8. The graph is already wired; you are filling
in handlers.

1. Read the stage's section in `docs/prd/PRD_v4.md` (the `description=` field on
   each `StageSpec` names it).
2. Check its `StageSpec` in `graphs/production.py`. Is the scope, pool, tier,
   dependency shape and `config_keys` right? Fix the spec first if not — a wrong
   `config_keys` produces either phantom invalidation or stale cache hits.
3. Write `prompts/<name>.v1.md` if the stage has `prompt=`.
4. Write the handler in `src/explainer/stages/production_handlers.py`:

```python
@handler("production", "research")
def research(ctx: StageContext) -> StageResult:
    facts = call_model(ctx.prompt_body, ctx.model_version, ...)  # pinned model
    validate(facts)                       # schema-validate; raise StageFailure(
                                          # ..., "llm_schema") on failure
    return StageResult.from_json(facts, cost_usd=..., model_version=...)
```

5. Flip `implemented=True` on the spec.
6. `make verify && make test`, then run the stage on one real video and look at
   the output yourself.

Error classes that drive retries (`StageFailure(msg, error_class)`):
`llm_transient`, `llm_schema`, `render_compile`, `render_timeout`, `tts`,
`ffmpeg`, `internal`. See the table in `worker.py`.

## Roadmap and what "next" means

Phases and exit criteria are in PRD §16. Condensed:

| Phase | What | Exit condition |
|---|---|---|
| 0 | Decide §2, hand-write 3 gold scripts, rubric, golden set, TTS bake-off | two people score the same video within 1 point |
| **1** | **Skeleton — done** | **`make verify` passes** |
| 2 | Ugly vertical slice, **GO/NO-GO** | an MP4 exists, you watched it, and there is a written surprise list |
| 3 | Teaching spine: curriculum.yaml, ID, critics | video 6 correctly assumes what video 2 taught |
| 4 | Editor part 1: Gate A | a human reviews Gate A in the browser |
| 5 | Templates, brand, visual craft | ~15 templates, brand@semver sweep works |
| 6 | Gate B and Gate C | beat-level fixes at Gate C invalidate only affected beats |
| 7 | Audio and finish | −14 LUFS, dual aspect, styled captions |
| 8 | Emergent reviewer + calibration | reviewer correlates with human rubric scores |
| 9 | Compounding, progressive trust, Lambda render | human-minutes trending to ≤15 |

**Phase 2 is next and it is deliberately ugly.** One topic, four beats, research
→ script → TTS → two Remotion templates → FFmpeg → watch it. Ugly is a
requirement, not a tolerance. Do not build gates, editor, critics, curriculum,
sound design or captions in Phase 2. The deliverable that matters most is the
written list of surprises.

Phase 2's real purpose: the unknown-unknowns all live in render, sync,
pronunciation and does-it-feel-right. Sixty ugly seconds teaches more than five
perfect lesson plans.

## Things that look like improvements and are not

Consult PRD Appendix C before proposing an addition (P5). Already decided and
not returning:

- **No AI-generated B-roll / diffusion clips.** Cut, not deferred (§13.3).
- **No second render engine.** Remotion only until a measured failure justifies
  another (D5). Reversing after Phase 5 costs the whole template library.
- **No workflow engine** (§6.2).
- **No prompt-editing UI** (§6.6).
- **No fine-tuning** before the four levers in §9.1 are exhausted.
- **No auto-built concept graph.** `curriculum.yaml` is human-owned (§10.3).
- **Pacing is code, not a model** (§9.6).
- **Not autonomous.** A human holds editorial sign-off permanently, by design.

## Working style in this repo

- Run `make verify` before every commit. It is the regression gate for the
  invalidation model; if it fails, stop and fix that before anything else.
- Prefer deleting to adding. The PRD cut 17 stages to 13 and 15 agents to 12 on
  purpose.
- Comment *why*, not *what* — especially where a subtlety would otherwise get
  "cleaned up" by a future reader.
- When a decision from §2 is in play (audience, volume, budget, engine, locale),
  say which one and what breaks if it changes. Don't quietly assume.
- Budgets are first-class constraints (§15), not aspirations. If a change makes
  a video cost or take materially more, say so in the same breath.
