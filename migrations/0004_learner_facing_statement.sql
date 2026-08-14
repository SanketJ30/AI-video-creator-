-- §9.1: the objective slot states the objective "verbatim; reused as the scene
-- title", inside a <=10s cap.
--
-- Week 3 found those two requirements in direct conflict. A v2-extracted
-- objective carries a condition and a criterion because §5.3's alignment check
-- needs them, and the full statement runs to 40 words — 180 wpm in a 10-second
-- slot, FK 13.02. Reading the schema record aloud was never what "verbatim"
-- meant.
--
-- So the short form becomes stored data rather than a generation-time
-- abridgement. One stable string, emitted by the extractor next to the full
-- statement, shared by the promise, the scene title and the assessment. It is
-- validated at EXTRACTION time: a stored short form that cannot be spoken in
-- its slot is an extraction error, not something for the script writer to work
-- around later.
--
-- Deliberately nullable: every objective row written before this migration has
-- no short form, and back-filling one here would mean inventing learner-facing
-- copy in SQL. Re-extract instead.

alter table objectives
    add column if not exists learner_facing_statement text;

comment on column objectives.learner_facing_statement is
    'Speakable short form of the objective (<=22 words, active voice, <=10s at '
    '135wpm). Spoken verbatim by the Gagne objective slot and reused as that '
    'scene''s title. Validated in code at extraction time. NULL means the row '
    'predates objective_extractor v3 — re-extract rather than back-filling.';
