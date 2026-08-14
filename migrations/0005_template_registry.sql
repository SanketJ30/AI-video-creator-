-- Template registry columns (Sequence v0.2 §4.4, §16.2).
--
-- `templates` already exists from migration 0001 with name/version/param_schema/
-- min_sec/max_sec/supports_signaling/golden_frame_uri and the compile-failure
-- counters. Three things it does not carry, all needed before a template can be
-- planned against rather than merely rendered.
--
-- CAPTION SAFE AREA is the one that cannot wait. §16.2's automated gates
-- reserve "the bottom 15% as a caption exclusion zone in every layout template",
-- and CHALLENGES lists it in the irreversible-decisions table with the reason:
-- "Otherwise a painful retrofit across the whole template library." A template
-- shipped without one has to be re-laid-out later, and every scene built on it
-- re-rendered. It is a column rather than a param_schema key because it is a
-- property OF the template, not an input TO it — a caller must not be able to
-- pass a different safe area and have it honoured.
--
-- `kind` groups the §4.4 composition types (animated diagram, kinetic type,
-- data viz, screen demo, illustration, title/hook) so the visual planner can
-- select by category before selecting by name.
--
-- `renderer` records what the template was authored against. It exists to keep
-- R8 (renderer-agnostic scene graph) honest: the value must stay 'agnostic' for
-- everything in the registry, and a row that names a concrete engine is a
-- deliberate, visible exception rather than a silent leak.

alter table templates
    add column if not exists kind text,
    add column if not exists description text,
    add column if not exists caption_safe_area jsonb
        not null default '{"bottom": 0.15, "top": 0.0, "left": 0.0, "right": 0.0}'::jsonb,
    add column if not exists renderer text not null default 'agnostic',
    add column if not exists min_font_px int not null default 24;

comment on column templates.caption_safe_area is
    'Fractions of frame height/width reserved from layout. §16.2 requires the '
    'bottom 15% as a caption exclusion zone in EVERY layout template. Reserved '
    'from day one on purpose: retrofitting it across a shipped template library '
    'means re-laying-out every template and re-rendering every scene built on '
    'one (CHALLENGES, irreversible decisions).';

comment on column templates.min_font_px is
    '§11.6: ">=24 px minimum font at 1080p". Aggressive encoding destroys '
    'smaller text via ringing, and the §9.3 density rules push the same way.';

comment on column templates.renderer is
    'Must be ''agnostic'' (R8). A concrete engine name here is a visible '
    'exception, not a silent coupling.';
