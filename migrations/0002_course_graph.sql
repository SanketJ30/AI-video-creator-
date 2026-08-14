-- Course Graph (PRD v0.2 §5). "This is the most important section in the
-- document. Everything else is downstream."
--
-- The ten irreversible decisions from CHALLENGES are encoded here. Each comment
-- names the rule and the capability it protects, because the failure mode for
-- every one of them is a video that looks fine and a rewrite six months later.
--
--   R1  durations stored, absolute positions NEVER      → the cache has value
--   R2  RationalTime: integer value + integer rate      → no A/V drift
--   R3  cues anchor to span ids, never timestamps       → localisation, editing
--   R4  narration segmented into spans at authoring     → the join key
--   R5  duration DERIVED from TTS, never authored       → honest timing
--   R6  every object carries provenance                 → audit, "why?", §17
--   R7  assets content-addressed and immutable          → free dedupe
--   R8  scene graph renderer-agnostic                   → engine portability
--   +   timingSensitivity rigid|elastic on every scene  → hybrid localisation
--   +   caption safe area in every layout template      → no retrofit

-- ------------------------------------------------------------------ org/brand

create table if not exists organisations (
    id         uuid primary key default gen_random_uuid(),
    name       text not null,
    created_at timestamptz not null default now()
);

create table if not exists brand_kits (
    id         uuid primary key default gen_random_uuid(),
    org_id     uuid not null references organisations(id) on delete cascade,
    semver     text not null,
    -- Colours are stored as SEMANTIC ROLES, not palette slots (§8): a brand whose
    -- primary is mid-grey cannot be the signal colour and still pass 4.5:1. The
    -- theme resolver derives a compliant accent from the brand hue.
    tokens     jsonb not null default '{}'::jsonb,
    motion     jsonb not null default '{}'::jsonb,
    typography jsonb not null default '{}'::jsonb,
    voice      jsonb not null default '{}'::jsonb,
    lexicon    jsonb not null default '{}'::jsonb,
    wcag_report jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (org_id, semver)
);

-- --------------------------------------------------------------------- course

create table if not exists courses (
    id            uuid primary key default gen_random_uuid(),
    org_id        uuid not null references organisations(id) on delete cascade,
    slug          text not null,
    title         text not null,
    audience      jsonb not null default '{}'::jsonb,   -- level, prior knowledge,
                                                        -- native-language ratio (§6)
    locale        text not null default 'en',
    brand_kit_id  uuid references brand_kits(id),
    status        text not null default 'draft',
    created_at    timestamptz not null default now(),
    unique (org_id, slug)
);

-- The Course Brief is itself a versioned, editable object (§6 Stage 1), so
-- "regenerate from an edited brief" is a first-class operation rather than a
-- fresh start.
create table if not exists course_briefs (
    id         uuid primary key default gen_random_uuid(),
    course_id  uuid not null references courses(id) on delete cascade,
    version    int not null,
    brief      jsonb not null,
    provenance jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (course_id, version)
);

-- ----------------------------------------------------------------- objectives

create table if not exists objectives (
    id             uuid primary key default gen_random_uuid(),
    course_id      uuid not null references courses(id) on delete cascade,
    ref            text not null,                       -- stable human ref: o1, o2
    verb           text not null,                       -- Bloom whitelist, enforced in code
    object         text not null,
    condition      text,
    criterion      text,
    bloom_level    text not null check (bloom_level in
                     ('remember','understand','apply','analyze','evaluate','create')),
    knowledge_type text not null check (knowledge_type in
                     ('factual','conceptual','procedural','metacognitive')),
    -- Prerequisites the course does NOT teach: declared assumptions. Lets a
    -- single-video Milestone A stand on honest foundations instead of pretending
    -- it teaches everything it uses.
    assumed        boolean not null default false,
    provenance     jsonb not null default '{}'::jsonb,
    created_at     timestamptz not null default now(),
    unique (course_id, ref)
);

-- The prerequisite DAG. Topological sort DERIVES course order (§5.3); a cycle is
-- a hard error, checked in code before anything is generated.
create table if not exists objective_edges (
    course_id      uuid not null references courses(id) on delete cascade,
    prerequisite_id uuid not null references objectives(id) on delete cascade,
    objective_id   uuid not null references objectives(id) on delete cascade,
    primary key (prerequisite_id, objective_id),
    check (prerequisite_id <> objective_id)
);

-- §5.3: every objective needs >=1 assessment item at the SAME Bloom level.
-- "The most common real-world ID failure is Apply-level objectives assessed by
--  Remember-level MCQs. The engine refuses to ship this."
create table if not exists assessment_items (
    id           uuid primary key default gen_random_uuid(),
    course_id    uuid not null references courses(id) on delete cascade,
    objective_id uuid not null references objectives(id) on delete cascade,
    bloom_level  text not null,
    kind         text not null,                          -- mcq | short | predict | task
    stem         text not null,
    options      jsonb not null default '[]'::jsonb,
    answer       jsonb,
    -- Deep link back into the video: scene + offset (§9.5, §11.6)
    scene_ref    jsonb,
    provenance   jsonb not null default '{}'::jsonb,
    created_at   timestamptz not null default now()
);

-- -------------------------------------------------------------- modules/videos

create table if not exists modules (
    id         uuid primary key default gen_random_uuid(),
    course_id  uuid not null references courses(id) on delete cascade,
    ordinal    int not null,                             -- mutable
    ref        text not null,                            -- stable
    title      text not null,
    -- Merrill arc: activation | demonstration | application | integration
    arc_stage  text,
    provenance jsonb not null default '{}'::jsonb,
    unique (course_id, ref)
);

create table if not exists videos_v2 (
    id           uuid primary key default gen_random_uuid(),
    course_id    uuid not null references courses(id) on delete cascade,
    module_id    uuid references modules(id) on delete set null,
    ordinal      int not null,
    ref          text not null,                          -- stable: v1, v2
    title        text not null,
    script_type  text,          -- explainer | worked_example | case_study | compare
                                -- | procedure | scenario | myth_busting | recap
    target_seconds int,
    -- Derived by the timing resolver from scene durations. NEVER authored (R5).
    duration_value int,
    duration_rate  int,
    status       text not null default 'draft',
    provenance   jsonb not null default '{}'::jsonb,
    created_at   timestamptz not null default now(),
    unique (course_id, ref)
);

create table if not exists video_objectives (
    video_id     uuid not null references videos_v2(id) on delete cascade,
    objective_id uuid not null references objectives(id) on delete cascade,
    primary key (video_id, objective_id)
);

-- --------------------------------------------------------------------- scenes

-- THE UNIT OF CACHING, ADDRESSING AND RE-RENDER (§5.1).
create table if not exists scenes (
    id             uuid primary key default gen_random_uuid(),
    video_id       uuid not null references videos_v2(id) on delete cascade,
    ref            text not null,                        -- stable forever: s01
    ordinal        int not null,                         -- mutable (reorder)
    -- exactly one objective per scene (§5.3)
    objective_id   uuid references objectives(id) on delete set null,
    gagne_slot     text not null check (gagne_slot in
                     ('hook','objective','recall','present','guide',
                      'elicit','feedback','assess','retain')),

    -- Narration as ID'd spans (R4). Cues inside visual_spec anchor to these ids
    -- (R3). Stored as jsonb rather than a table because a scene's spans are
    -- always read and written together, and they enter the cache key as a unit.
    narration      jsonb not null default '[]'::jsonb,
    voice_id       text,
    ssml           text,

    -- Renderer-agnostic (R8). No Remotion-native constructs. Contains
    -- {template, slots{}, cues[], captionSafeArea}.
    visual_spec    jsonb not null default '{}'::jsonb,

    -- DERIVED from TTS (R5), as RationalTime (R2). Absolute start time is
    -- deliberately absent (R1) — it is computed in the timing pass and must
    -- never enter a cache key.
    duration_value int,
    duration_rate  int,

    -- Hybrid localisation strategy (§15.3) depends on this being present from
    -- day one: rigid scenes keep their duration and the audio is time-fitted;
    -- elastic scenes stretch to fit the translated narration.
    timing_sensitivity text not null default 'elastic'
                       check (timing_sensitivity in ('rigid','elastic')),

    pedagogy_meta  jsonb not null default '{}'::jsonb,   -- bloomLevel,
                                                         -- elementInteractivity,
                                                         -- newTerms[], loadScore
    locked         boolean not null default false,
    locked_hash    text,
    provenance     jsonb not null default '{}'::jsonb,   -- R6
    created_at     timestamptz not null default now(),
    unique (video_id, ref)
);
create index if not exists scenes_video_ord on scenes(video_id, ordinal);

-- Transitions are first-class DAG nodes with handle frames (§11.4), because a
-- crossfade between scenes 3 and 4 is a function of both and is therefore not
-- cacheable under either scene's key.
create table if not exists transitions (
    id            uuid primary key default gen_random_uuid(),
    video_id      uuid not null references videos_v2(id) on delete cascade,
    from_scene_id uuid not null references scenes(id) on delete cascade,
    to_scene_id   uuid not null references scenes(id) on delete cascade,
    -- Hard cut is the default: pedagogically supported (coherence) AND
    -- architecturally cheaper. Dissolves only at module boundaries.
    kind          text not null default 'cut',
    handle_frames int not null default 0,
    spec          jsonb not null default '{}'::jsonb,
    unique (from_scene_id, to_scene_id)
);

-- ----------------------------------------------------------- assets + licence

-- R7: assetId = sha256(bytes). Immutable, deduplicated across courses for free.
-- The licence columns are not bookkeeping: §14.3's enforcement rule requires
-- "may this asset leave the system as a stand-alone file?" to be a hard,
-- code-level check that defaults to NO. That check reads these columns.
create table if not exists media_assets (
    content_sha256      text primary key,
    kind                text not null,                  -- image | video | audio | font
    mime                text,
    bytes               bigint,
    storage_uri         text not null,
    source              text not null,                  -- storyblocks | freepik_ai
                                                        -- | generated | own | upload
    source_ref          text,
    licence             text not null,                  -- storyblocks_api_partner
                                                        -- | freepik_enterprise_msa
                                                        -- | owned | unknown
    indemnified         boolean not null default false,
    may_export_standalone boolean not null default false,
    attribution_required  boolean not null default false,
    licence_notes       text,
    provenance          jsonb not null default '{}'::jsonb,
    created_at          timestamptz not null default now()
);

-- Deliberately no default on `may_export_standalone` other than false, and a
-- guard so nothing can be marked exportable while its licence is unknown.
alter table media_assets drop constraint if exists media_assets_export_guard;
alter table media_assets add constraint media_assets_export_guard
    check (not may_export_standalone or licence in ('owned', 'freepik_enterprise_msa'));

create table if not exists scene_assets (
    scene_id  uuid not null references scenes(id) on delete cascade,
    asset_sha text not null references media_assets(content_sha256),
    slot      text not null,
    primary key (scene_id, slot)
);

-- ---------------------------------------------------------------- glossary

create table if not exists glossary_terms (
    id                uuid primary key default gen_random_uuid(),
    course_id         uuid not null references courses(id) on delete cascade,
    term              text not null,
    definition        text not null,
    first_scene_id    uuid references scenes(id) on delete set null,
    aliases           jsonb not null default '[]'::jsonb,
    usage_count       int not null default 0,
    unique (course_id, term)
);

-- --------------------------------------------------------- linter findings

-- The pedagogy linter's output is stored, not just returned: §4.3 and §1.3
-- Wedge C make the report a customer-visible artifact and a sales asset.
create table if not exists linter_findings (
    id         uuid primary key default gen_random_uuid(),
    video_id   uuid not null references videos_v2(id) on delete cascade,
    scene_id   uuid references scenes(id) on delete cascade,
    rule       text not null,
    severity   text not null check (severity in ('blocking','warning','info')),
    message    text not null,
    measured   jsonb not null default '{}'::jsonb,
    threshold  jsonb not null default '{}'::jsonb,
    fix        jsonb,
    resolved   boolean not null default false,
    created_at timestamptz not null default now()
);
create index if not exists linter_video on linter_findings(video_id, severity);
