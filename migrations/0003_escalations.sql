-- Escalations (invariant 7 / §7.1): `escalated` is a first-class state, not a
-- failure. Every failure path ends in a recorded row carrying the error, the
-- offending input, and a human-actionable next step.
--
-- `jobs` already records this for DAG nodes. This table covers the work that
-- happens OUTSIDE the per-video DAG — course-scoped intake, objective
-- extraction, curriculum edits — which has no job row to hang a state on. A
-- pipeline that dies at 2am and shows a red dot in a log is a pipeline nobody
-- trusts; both tables exist so there is nowhere for a failure to hide.

create table if not exists escalations (
    id              uuid primary key default gen_random_uuid(),
    course_id       uuid references courses(id) on delete cascade,
    stage           text not null,          -- 'objective_extractor', ...
    error_class     text not null,          -- llm_schema | llm_transient | internal
    error           text not null,
    -- The exact input that produced the failure, so a human can reproduce it
    -- without guessing which brief version was in play.
    offending_input jsonb not null default '{}'::jsonb,
    -- Prose, imperative, addressed to the person who has to unblock this.
    next_step       text not null,
    resolved        boolean not null default false,
    resolved_note   text,
    created_at      timestamptz not null default now()
);

create index if not exists escalations_open
    on escalations(resolved, created_at desc);
create index if not exists escalations_course
    on escalations(course_id, created_at desc);
