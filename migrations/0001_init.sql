-- PRD v4 §6.3 — data model. Phase 1 skeleton.
-- Runs on any Postgres 14+, including Supabase.
--
-- INVARIANTS ENCODED HERE (see CLAUDE.md before changing any of them):
--   1. artifacts.hash is the GLOBAL primary key. Same input closure = one row,
--      forever, across every video and series. This is where §5's cost curve
--      comes from. artifacts.video_id is the FIRST producer only (provenance),
--      never part of identity.
--   2. beats.beat_id is stable forever. beats.ordinal is mutable (Gate B
--      reorder). Never key anything on ordinal.
--   3. jobs is unique on (video_id, node_key, hash) — one row per node per
--      input closure. Re-resolving after an edit creates a NEW row; the old
--      row stays as history. That history is the hash-diff in §14.4.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- series scope

create table if not exists series (
    id                 uuid primary key default gen_random_uuid(),
    slug               text unique not null,
    title              text not null,
    owner_id           text,
    curriculum_yaml    text,
    curriculum_version int  not null default 1,
    audience_level     text not null default 'intermediate',   -- D1
    locale             text not null default 'en',             -- D7
    brand_version      text not null default '1.0.0',
    status             text not null default 'draft',
    created_at         timestamptz not null default now()
);

create table if not exists videos (
    id            uuid primary key default gen_random_uuid(),
    series_id     uuid not null references series(id) on delete cascade,
    video_id      text not null,                               -- v1, v2, ...
    title         text not null default '',
    status        text not null default 'draft',
    current_stage text,
    brand_version text not null default '1.0.0',
    priority      int  not null default 0,
    -- Which pipeline graph this video runs: 'production' or 'fake' (the Phase 1
    -- fixture). Stored rather than inferred from the title, because inferring it
    -- means a rename silently changes which code path runs.
    graph         text not null default 'production'
                  check (graph in ('production', 'fake')),
    -- The video-level brief: topic, angle, target length. Any stage that reads
    -- this must declare `video_input_keys` on its StageSpec, or its output will
    -- depend on an input that is not in its hash closure.
    inputs        jsonb not null default '{}'::jsonb,
    published_at  timestamptz,
    created_at    timestamptz not null default now(),
    unique (series_id, video_id)
);

create table if not exists beats (
    id          uuid primary key default gen_random_uuid(),
    video_id    uuid not null references videos(id) on delete cascade,
    ordinal     int  not null,                                 -- mutable
    beat_id     text not null,                                 -- b07, stable
    inputs      jsonb not null default '{}'::jsonb,            -- the beat brief
    locked      boolean not null default false,
    locked_hash text,
    role        text,
    load_score  numeric,
    created_at  timestamptz not null default now(),
    unique (video_id, beat_id)
);
create index if not exists beats_video_ord on beats(video_id, ordinal);

-- Per-node lock snapshot. beats.locked is the flag a human toggles; this table
-- pins every beat-scoped node of that beat to the hash it had at lock time, so
-- upstream churn cannot disturb approved work (§5.4).
create table if not exists beat_locks (
    beat_pk   uuid not null references beats(id) on delete cascade,
    node_key  text not null,
    hash      text not null,
    locked_at timestamptz not null default now(),
    primary key (beat_pk, node_key)
);

-- ------------------------------------------------------------------- artifacts

create table if not exists artifacts (
    hash           text primary key,          -- input-closure hash (§5.2)
    kind           text not null,             -- stage key: script, tts, render…
    video_id       uuid references videos(id) on delete set null,  -- first producer
    beat_id        text,
    storage_uri    text not null,
    content_sha256 text,                      -- integrity of the blob itself
    bytes          bigint,
    mime           text,
    cost_usd       numeric not null default 0,
    duration_ms    int,
    model_version  text,
    prompt_version text,
    code_version   text,
    meta           jsonb not null default '{}'::jsonb,
    created_at     timestamptz not null default now()
);
create index if not exists artifacts_kind on artifacts(kind);

-- The invalidation graph, written at resolve time (§5.1).
create table if not exists artifact_edges (
    parent_hash text not null,
    child_hash  text not null,
    primary key (parent_hash, child_hash)
);
create index if not exists artifact_edges_child on artifact_edges(child_hash);

-- ------------------------------------------------------------------------ jobs

create table if not exists jobs (
    id           uuid primary key default gen_random_uuid(),
    video_id     uuid not null references videos(id) on delete cascade,
    node_key     text not null,               -- "script:b03" or "assembly"
    stage        text not null,
    beat_id      text,
    hash         text not null,               -- the artifact this job produces
    pool         text not null check (pool in ('agent','render','media')),
    -- The exact closure this job was hashed from: upstream label->hash, prompt
    -- version, model version, code version, config, extra. The worker recomputes
    -- the hash from this and refuses to run if it does not match `hash`, which
    -- catches closure drift between enqueue and execute.
    context      jsonb not null default '{}'::jsonb,
    state        text not null default 'queued'
                 check (state in ('queued','running','succeeded','failed',
                                  'escalated','cancelled','cached','locked')),
    attempts     int  not null default 0,
    priority     int  not null default 0,
    worker_id    text,
    heartbeat_at timestamptz,
    not_before   timestamptz,                 -- backoff / dependency gating
    error        text,
    error_class  text,
    queue_wait_ms int,
    exec_ms      int,
    started_at   timestamptz,
    finished_at  timestamptz,
    created_at   timestamptz not null default now(),
    unique (video_id, node_key, hash)
);
create index if not exists jobs_pickup on jobs(state, pool, priority desc, created_at);
create index if not exists jobs_video on jobs(video_id, node_key);
create index if not exists jobs_heartbeat on jobs(state, heartbeat_at);

-- ---------------------------------------------------------- human + compounding

create table if not exists gate_sessions (
    id              uuid primary key default gen_random_uuid(),
    video_id        uuid not null references videos(id) on delete cascade,
    gate            text not null check (gate in ('0','a','b','c')),
    user_id         text,
    opened_at       timestamptz not null default now(),
    closed_at       timestamptz,
    active_seconds  int not null default 0,    -- S2 lives here (idle-gated)
    sections_reviewed jsonb not null default '{}'::jsonb,
    outcome         text
);

-- This table IS the preference dataset (§10.5). Never truncate it.
create table if not exists edits (
    id               uuid primary key default gen_random_uuid(),
    video_id         uuid not null references videos(id) on delete cascade,
    beat_id          text,
    gate             text,
    kind             text not null check (kind in ('edit','regenerate','reorder',
                                                   'lock','unlock','template_swap')),
    instruction_text text,
    reason_text      text,
    before           jsonb,
    after            jsonb,
    accepted         boolean,
    created_at       timestamptz not null default now()
);

create table if not exists templates (
    id                 uuid primary key default gen_random_uuid(),
    name               text not null,
    version            text not null,
    param_schema       jsonb not null default '{}'::jsonb,
    min_sec            numeric,
    max_sec            numeric,
    supports_signaling boolean not null default false,
    golden_frame_uri   text,
    compile_failures   int not null default 0,
    uses_count         int not null default 0,
    unique (name, version)
);

create table if not exists brand_versions (
    semver      text primary key,
    tokens      jsonb not null default '{}'::jsonb,
    motion      jsonb not null default '{}'::jsonb,
    audio       jsonb not null default '{}'::jsonb,
    caption     jsonb not null default '{}'::jsonb,
    thumbnail   jsonb not null default '{}'::jsonb,
    wcag_report jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);

create table if not exists lexicon (
    term            text not null,
    locale          text not null default 'en',
    spoken_form     text not null,
    added_by        text,
    source_video_id text,
    created_at      timestamptz not null default now(),
    primary key (term, locale)
);

create table if not exists prompt_versions (
    name       text not null,
    version    text not null,
    body       text not null,
    body_sha   text not null,
    model_hint text,
    git_sha    text,
    created_at timestamptz not null default now(),
    primary key (name, version, body_sha)
);

create table if not exists eval_runs (
    id                  uuid primary key default gen_random_uuid(),
    trigger             text not null check (trigger in ('prompt_bump','manual','nightly')),
    golden_set_version  text,
    hash_diff           jsonb not null default '{}'::jsonb,
    scores              jsonb not null default '{}'::jsonb,
    reviewer_correlation numeric,
    created_at          timestamptz not null default now()
);

-- One row per resolve() call. This is where §6.5's cache-hit-rate health metric
-- comes from: it has to be captured at resolve time, because once the artifacts
-- exist you can no longer tell what was served vs what was built.
create table if not exists resolutions (
    id             uuid primary key default gen_random_uuid(),
    video_id       uuid not null references videos(id) on delete cascade,
    target         text,
    planned        int not null,
    cached         int not null default 0,
    locked         int not null default 0,
    queued         int not null default 0,
    unimplemented  int not null default 0,
    blocked        int not null default 0,
    cache_hit_rate numeric,
    created_at     timestamptz not null default now()
);
create index if not exists resolutions_video on resolutions(video_id, created_at desc);
