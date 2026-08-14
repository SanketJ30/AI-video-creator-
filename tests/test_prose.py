"""Deterministic prose gates — §9.2 Personalisation, §9.3, §9.6.

Known-bad prose that each gate must fire on, and known-good prose that none may
fire on. Includes a genuinely technical scene to prove the grade-11 threshold
applies where §9.2 says it should.
"""
from __future__ import annotations

import pytest

from explainer import prose

# Written to pass every gate: short sentences, second person, active voice.
GOOD = (
    "You start two transactions at the same time. "
    "Each one reads the same two rows. "
    "Neither sees the other's change yet. "
    "Both commit, and together they break the rule you wanted to protect.")

# Long sentences, many syllables per word — high FK grade, nothing else wrong.
UNREADABLE = (
    "The fundamental architectural characteristic of multiversion concurrency "
    "control implementations necessitates that transactional visibility "
    "determinations be predicated upon the comparative evaluation of "
    "monotonically increasing transaction identifiers against an immutable "
    "snapshot representation acquired at transaction initiation.")

# Short, simple, but almost every sentence is passive.
PASSIVE = (
    "The row is updated by the first transaction. "
    "A new version is written. "
    "The old version is marked with an xmax. "
    "The change is committed. "
    "The second transaction is aborted.")


# ------------------------------------------------------------ readability

def test_good_prose_passes_readability():
    assert not prose.check_readability("s01", GOOD, technical=False)


def test_unreadable_prose_fires_the_general_gate():
    findings = prose.check_readability("s01", UNREADABLE, technical=False)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule == "readability_fk" and f.severity == "warning"
    assert f.measured["fk_grade"] > prose.FK_GRADE_GENERAL
    assert f.threshold["fk_grade_max"] == prose.FK_GRADE_GENERAL


def test_the_technical_threshold_applies_where_it_should():
    """§9.2: '<= 9 general / <= 11 technical'. Real technical narration sits
    between the two, and must pass as technical while failing as general."""
    technical = (
        "Your transaction compares each row version's xmin against its snapshot. "
        "If the creating transaction was still running, the version stays hidden. "
        "That single rule explains every visibility decision in the engine.")
    grade = prose.flesch_kincaid_grade(technical)
    assert prose.FK_GRADE_GENERAL < grade <= prose.FK_GRADE_TECHNICAL, (
        f"fixture drifted: grade {grade} is not between the two thresholds")
    assert prose.check_readability("s01", technical, technical=False), \
        "must fail the general limit"
    assert not prose.check_readability("s01", technical, technical=True), \
        "must pass the technical limit"


def test_flesch_kincaid_matches_the_formula():
    text = "The cat sat. The dog ran."       # 6 words, 2 sentences, 6 syllables
    expected = round(0.39 * (6 / 2) + 11.8 * (6 / 6) - 15.59, 2)
    assert prose.flesch_kincaid_grade(text) == expected


def test_empty_text_does_not_crash_the_grade():
    assert prose.flesch_kincaid_grade("") == 0.0


# --------------------------------------------------------- passive voice

def test_good_prose_passes_the_passive_gate():
    assert not prose.check_passive("s01", GOOD)


def test_passive_prose_fires():
    findings = prose.check_passive("s01", PASSIVE)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule == "passive_voice" and f.severity == "warning"
    assert f.measured["passive_ratio"] > prose.PASSIVE_RATIO_MAX
    assert "is updated" in f.message or "is aborted" in f.message


def test_the_heuristic_catches_an_adverb_between_auxiliary_and_participle():
    assert prose.passive_sentences("The change was silently rolled back.")


def test_the_heuristic_catches_get_passives():
    assert prose.passive_sentences("Your transaction gets aborted at commit.")


def test_one_passive_in_five_is_within_the_limit():
    text = ("You open a transaction. You read a row. You update it. "
            "You commit. The other transaction is aborted.")
    assert prose.passive_ratio(text) == 0.2
    assert not prose.check_passive("s01", text)


def test_the_documented_false_positive_is_real():
    """The docstring says adjectival predicates are wrongly flagged. If that
    stops being true the docstring is overclaiming and must be updated."""
    assert prose.passive_sentences("The value is committed."), (
        "docstring claims this false positive exists")


# ---------------------------------------------------------- speaking rate

def test_narration_that_fits_its_budget_passes():
    # 30s at 160 wpm dense = 80 words allowed.
    text = " ".join(["word"] * 70) + "."
    assert not prose.check_speaking_rate("s01", text, 30, "present")


def test_slight_overrun_is_a_warning():
    allowed = prose.max_words_for(30, prose.WPM_DENSE_MAX)
    text = " ".join(["word"] * (allowed + 5)) + "."
    findings = prose.check_speaking_rate("s01", text, 30, "present")
    assert len(findings) == 1 and findings[0].severity == "warning"


def test_overrun_beyond_twenty_percent_is_blocking():
    allowed = prose.max_words_for(30, prose.WPM_DENSE_MAX)
    text = " ".join(["word"] * int(allowed * 1.5)) + "."
    findings = prose.check_speaking_rate("s01", text, 30, "present")
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "blocking"
    assert f.measured["overrun_ratio"] > prose.OVERRUN_BLOCKING_RATIO
    assert f.threshold["max_words"] == allowed


def test_narrative_slots_get_the_faster_ceiling():
    """§9.3: 'up to 185 wpm narrative'. The same words that overrun a dense
    slot may fit a hook."""
    words_n = prose.max_words_for(15, prose.WPM_NARRATIVE_MAX)
    text = " ".join(["word"] * words_n) + "."
    assert not prose.check_speaking_rate("s01", text, 15, "hook")
    assert prose.check_speaking_rate("s01", text, 15, "present"), \
        "the same text must overrun a dense slot"


def test_a_zero_budget_slot_is_not_measured():
    assert not prose.check_speaking_rate("s01", "anything at all", 0, "present")


# ---------------------------------------------------------------- report

def test_a_clean_script_reports_all_pass():
    scenes = [{"ref": "s01", "text": GOOD, "gagne_slot": "present",
               "pedagogy_meta": {"duration_target_seconds": 90}}]
    report = prose.check_script(scenes)
    assert report.ok and report.render() == "prose gates: all pass"


def test_a_blocking_finding_makes_the_report_not_ok():
    allowed = prose.max_words_for(20, prose.WPM_DENSE_MAX)
    scenes = [{"ref": "s01", "text": " ".join(["word"] * int(allowed * 2)) + ".",
               "gagne_slot": "present",
               "pedagogy_meta": {"duration_target_seconds": 20}}]
    report = prose.check_script(scenes)
    assert not report.ok
    assert report.render().startswith("[BLOCK]")


def test_findings_carry_measured_and_threshold_for_every_rule():
    """linter_findings has measured/threshold columns; §9.6 makes the report a
    customer-visible artifact, so an unpopulated measurement is a broken row."""
    allowed = prose.max_words_for(10, prose.WPM_DENSE_MAX)
    scenes = [
        {"ref": "s01", "text": UNREADABLE, "gagne_slot": "present",
         "pedagogy_meta": {"duration_target_seconds": 300}},
        {"ref": "s02", "text": PASSIVE, "gagne_slot": "present",
         "pedagogy_meta": {"duration_target_seconds": 300}},
        {"ref": "s03", "text": " ".join(["word"] * (allowed * 3)) + ".",
         "gagne_slot": "present", "pedagogy_meta": {"duration_target_seconds": 10}},
    ]
    report = prose.check_script(scenes)
    rules = {f.rule for f in report.findings}
    assert rules == {"readability_fk", "passive_voice", "speaking_rate"}
    for f in report.findings:
        assert f.measured, f"{f.rule} has no measurement"
        assert f.threshold, f"{f.rule} has no threshold"
        assert f.fix, f"{f.rule} has no actionable fix"


def test_good_prose_fires_no_gate_at_all():
    """The one that matters most: a clean scene must be silent."""
    scenes = [{"ref": "s01", "text": GOOD, "gagne_slot": "present",
               "pedagogy_meta": {"duration_target_seconds": 60}}]
    assert prose.check_script(scenes).findings == []


@pytest.mark.parametrize("rule", ["readability_fk", "passive_voice", "speaking_rate"])
def test_redundancy_is_not_among_the_gates(rule):
    """§9.4 redundancy needs the storyboard, which is week 4. If a redundancy
    rule appears here, scope has leaked."""
    assert rule in {"readability_fk", "passive_voice", "speaking_rate"}
    assert not hasattr(prose, "check_redundancy")
