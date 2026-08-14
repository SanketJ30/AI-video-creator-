"""The lint report as a human reads it — §4.3 makes it customer-visible.

These test the RENDERING, not the rules. A finding whose measured value never
reaches the page is a finding nobody can act on, and that failure is invisible
to every test in test_linter.py.
"""
from __future__ import annotations

from explainer import linter as L
from explainer.cli import _kv, _render_lint
from explainer.prose import Finding


def report(findings):
    return L.LintReport(findings=findings, scene_count=1,
                        not_implemented=dict(L.MODEL_BASED_RULES))


def strip(text: str) -> str:
    """typer.style emits ANSI when colour is forced; tests read plain text."""
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def finding(**kw):
    base = dict(rule="onscreen_text_share", severity="warning", subject="s01",
                message="19 on-screen words against 57 narrated",
                measured={"onscreen_words": 19, "narration_words": 57},
                threshold={"max_share": 0.2, "max_words": 11},
                fix="cut to key phrases")
    base.update(kw)
    return Finding(**base)


def test_the_measured_value_and_the_threshold_both_reach_the_page():
    """The whole point: 19 against a limit of 11 is a near miss; 56 against 11
    is a different conversation. A report that prints only the message makes
    them look the same."""
    out = strip(_render_lint(report([finding()])))
    assert "onscreen_words=19" in out
    assert "max_words=11" in out
    assert "measured" in out and "allowed" in out


def test_findings_are_grouped_by_severity_worst_first():
    out = strip(_render_lint(report([
        finding(severity="info", rule="c"),
        finding(severity="warning", rule="b"),
        finding(severity="blocking", rule="a")])))
    assert (out.index("BLOCKING") < out.index("WARNING") < out.index("INFO"))


def test_each_group_carries_its_count():
    out = strip(_render_lint(report([finding(rule="a"), finding(rule="b")])))
    assert "WARNING (2)" in out


def test_findings_within_a_group_are_ordered_by_scene():
    out = strip(_render_lint(report([finding(subject="s09"),
                                     finding(subject="s02")])))
    assert out.index("[s02]") < out.index("[s09]")


def test_an_authored_threshold_says_so_on_the_page():
    """The user's standing rule: every invented number is marked where it is
    used, not only where it is defined."""
    out = strip(_render_lint(report([finding(
        rule="template_variety", subject="video",
        measured={"template": "table_build", "share": 0.44, "authored": True},
        threshold={"max_share": 0.4})])))
    assert "AUTHORED AND UNREVIEWED" in out


def test_the_authored_flag_is_not_printed_as_a_measurement():
    """`authored=True` is metadata about the rule, not something measured."""
    out = strip(_render_lint(report([finding(
        measured={"share": 0.44, "authored": True}, threshold={})])))
    assert "share=0.44" in out
    assert "authored=True" not in out


def test_a_clean_report_still_lists_what_was_not_checked():
    """§4.3: on a customer-visible report a silent absence reads as a pass."""
    out = strip(_render_lint(report([])))
    assert "no findings" in out
    assert "NOT CHECKED" in out
    assert "coherence_relevance_score" in out


def test_the_fix_reaches_the_page():
    out = strip(_render_lint(report([finding()])))
    assert "fix: cut to key phrases" in out


def test_kv_renders_empty_as_a_dash_rather_than_nothing():
    assert _kv({}) == "-"
    assert _kv({"authored": True}) == "-"
    assert _kv({"a": 1, "b": 2}) == "a=1, b=2"
