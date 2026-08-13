# Explainer pipeline

Implementation of PRD v4 — an AI-native explainer video pipeline that produces
pedagogically sequenced video series, editable at beat granularity.

**Status: Phase 1 (skeleton) complete.** Schema, content-addressed artifact
store, beat-level invalidation, orchestrator, three worker pools, CLI. No real
model calls, no renders, no UI yet — those are Phases 2–4.

Spec: `docs/prd/PRD_v4.md`. Engineering rules: `CLAUDE.md`.

## Setup

```bash
git clone <repo> && cd explainer-pipeline
./scripts/bootstrap.sh      # installs, starts postgres, migrates, verifies
```

Or by hand:

```bash
cp .env.example .env
pip install -e ".[dev]"
make up          # docker compose postgres
make db          # apply migrations
make verify      # Phase 1 exit criteria
```

### Using Supabase instead of local Postgres

Set `DATABASE_URL` to the **session pooler** string (port 5432), not the
transaction pooler. The worker claims jobs with `SELECT ... FOR UPDATE SKIP
LOCKED` inside an explicit transaction, which pgbouncer's transaction mode will
not carry correctly.

```
DATABASE_URL=postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

Then `make db`. Nothing else changes — the schema uses only `pgcrypto` and
standard types.

For artifacts you can stay on the local filesystem through Phase 8 (`iteration
speed dominates`, D12), or point at Supabase Storage / R2 / S3:

```
ARTIFACT_BACKEND=s3
S3_BUCKET=explainer-artifacts
S3_ENDPOINT=https://<ref>.storage.supabase.co/storage/v1/s3
AWS_ACCESS_KEY_ID=... / AWS_SECRET_ACCESS_KEY=...
```

## The check that matters

`make verify` runs the Phase 1 exit criteria from PRD §16 as executable checks:

```
[PASS] DAG expands to the expected node count                     17 nodes
[PASS] cold run enqueues every node                               17 queued
[PASS] every node produced an artifact                            17/17
[PASS] unchanged re-run is 100% cache hits                        cache_hit_rate=100%
[PASS] identical inputs on another video reuse every artifact     v2 cache_hit_rate=100%
[PASS] editing beat 3 invalidates exactly its downstream closure  6 nodes
[PASS] the other 4 beats keep their hashes
[PASS] untouched artifacts are byte-identical after the edit      11/11
[PASS] locked beat is exempt from upstream invalidation
[PASS] dead worker's job is reaped back to queued
[PASS] pipeline completes after the crash                         17/17
[PASS] hashing is deterministic across passes
[PASS] manifest reports cache hit rate and cost

PHASE 1 EXIT CRITERIA: MET
```

Run it before every commit. It is the regression gate for the invalidation
model — the subsystem PRD §5.1 calls the most important in the document, and the
one that cannot be retrofitted later.

## Walkthrough

See the machinery on the fake graph:

```bash
explainer series create demo --title "demo series"
explainer video create demo/v1 --beats 5 --graph fake
explainer resolve demo/v1                  # 17 nodes, all queued
explainer run --drain                      # three pools, one process
explainer resolve demo/v1                  # 17 cached, cache_hit_rate=100%

explainer beat edit demo/v1 b03 --text "rewritten" --instruction "beat was confusing"
explainer resolve demo/v1 --dry-run        # exactly 6 nodes queued:
                                           #   script:b03, tts:b03,
                                           #   pacing:b02, pacing:b03, pacing:b04,
                                           #   assembly
explainer beat lock demo/v1 b05            # pin b05 against upstream churn
explainer diff demo/v1                     # what a change would touch, before spending
explainer manifest demo/v1
```

The real pipeline:

```bash
explainer graph production                 # all 13 stages, deps, built or todo
```

## How it works

A node's hash is a SHA-256 over its **full input closure** — upstream artifact
hashes, prompt version, model version, code version (per-directory git tree SHA),
and the config values that stage actually consumes:

```
hash(artifact) = H(upstream hashes + prompt_version + model_id/version
                   + code_version + config)
```

Because the hash comes from inputs, every hash in the DAG is known before
anything runs. So the entire plan is hashed and enqueued in one pass, and
invalidation is not a graph walk — a changed input simply produces a hash with no
artifact behind it. Everything else is a cache hit, byte-identical.

Granularity is the **beat**, never the video. Editing beat 7 costs one script
call, one TTS call, one render and a remix — seconds and cents — and leaves the
eleven approved beats untouched. That last part is a trust property, not a
performance one: the second time the system quietly changes something a human
approved, they stop trusting any output.

Three worker pools (`agent`, `render`, `media`) because their resource profiles
differ completely; one pool means a single long render starves twelve cheap LLM
calls.

## Layout

```
migrations/          §6.3 schema
prompts/             versioned prompt files — bump the filename to bump the version
docs/prd/PRD_v4.md   the spec
src/explainer/       hashing, store, dag, orchestrator, worker, manifest, cli
  graphs/            fake (Phase 1 fixture) + production (13 real stages)
  stages/            handler contract + handlers
tests/               hashing, DAG shape, exit criteria
.claude/commands/    /add-stage, /verify, /phase-check
```

## What's next

Phase 2: ugly vertical slice, and it is a **GO/NO-GO**. One topic, four beats,
research → script → TTS → two Remotion templates → FFmpeg → watch it. Ugly is a
requirement, not a tolerance. The deliverable that matters most is the written
list of surprises.

Do not build gates, the editor, critics, curriculum, sound design or captions in
Phase 2. Each phase's **not** list is as binding as its deliverables.
