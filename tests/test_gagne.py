"""The Gagné slot template — §9.1, §6 Stage 2c.

Pure structure. Every assertion is about the template being a well-formed form;
none of it is about whether the resulting video is any good.

Note what is NOT tested: the values in AUTHORED_TAIL_WEIGHTS. Those are invented
and unreviewed, so a test asserting a particular number would only assert that
nobody had changed my guess. What IS tested is that the tail rows are structurally
sound and that §9.1's capped slots match the PRD literally.
"""
from __future__ import annotations

import pytest

from explainer import gagne
from explainer.gagne import (ALWAYS_REQUIRED, CAPPED_SLOTS, SPEC_CAPS,
                             TAIL_SLOTS, VARIANTS, Slot)

BUDGET = 300          # the MVCC course's target_seconds_per_video


# ------------------------------------------------------------------ shape

def test_there_are_exactly_nine_slots():
    assert len(list(Slot)) == 9


def test_slot_values_match_the_migration_check_constraint():
    assert [s.value for s in Slot] == [
        "hook", "objective", "recall", "present", "guide",
        "elicit", "feedback", "assess", "retain"]


def test_capped_and_tail_slots_partition_the_nine():
    assert set(CAPPED_SLOTS) | set(TAIL_SLOTS) == set(Slot)
    assert not set(CAPPED_SLOTS) & set(TAIL_SLOTS)


def test_every_slot_has_a_treatment_rule():
    for s in Slot:
        assert gagne.TREATMENTS.get(s), f"{s.value} has no treatment rule"


# ------------------------------------------------------------- §9.1 caps

def test_capped_slots_respect_the_literal_spec_numbers():
    """The whole point of the rebuild: slots 1-4 are absolute and come from
    §9.1, so this compares against the PRD, not against a budget."""
    assert not gagne.check_caps(), "; ".join(gagne.check_caps())


def test_the_spec_caps_are_transcribed_correctly():
    """Guards the transcription itself — if someone 'fixes' a cap here, the
    PRD and the code have silently diverged."""
    assert SPEC_CAPS[Slot.HOOK] == (None, 15)
    assert SPEC_CAPS[Slot.OBJECTIVE] == (None, 10)
    assert SPEC_CAPS[Slot.RECALL] == (None, 20)
    assert SPEC_CAPS[Slot.PRESENT] == (60, 120)


@pytest.mark.parametrize("budget", [180, 240, 300, 360])
def test_capped_slots_do_not_scale_with_the_budget(budget):
    """They are capped for cognitive reasons, not budget reasons."""
    form = {s.slot: s for s in gagne.plan_slots("explainer", budget)}
    for slot in CAPPED_SLOTS:
        assert form[slot].seconds == gagne.CAPPED_SLOT_SECONDS[slot]
        assert form[slot].spec_capped is True


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_capped_slots_are_identical_across_variants(name):
    form = {s.slot: s.seconds for s in gagne.plan_slots(name, BUDGET)}
    for slot in CAPPED_SLOTS:
        assert form[slot] == gagne.CAPPED_SLOT_SECONDS[slot]


# --------------------------------------------------------- tail weighting

@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_tail_weights_sum_to_one(name):
    total = sum(VARIANTS[name].tail_weights.values())
    assert abs(total - 1.0) < 1e-9, f"{name} tail sums to {total}"


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_tail_weights_cover_exactly_the_five_tail_slots(name):
    assert set(VARIANTS[name].tail_weights) == set(TAIL_SLOTS)


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_no_tail_slot_carries_zero_or_negative_weight(name):
    for slot, w in VARIANTS[name].tail_weights.items():
        assert w > 0, f"{name}/{slot.value} has weight {w}"


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_variant_invents_no_tenth_slot(name):
    assert set(VARIANTS[name].tail_weights) <= set(Slot)


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_variant_includes_the_always_required_slots(name):
    assert ALWAYS_REQUIRED <= set(VARIANTS[name].slots)


def test_variants_differ_in_where_the_tail_time_goes():
    """If every variant weighted the tail identically they would not be
    variants — the §6 Stage 2c claim is that the arrangement differs."""
    assert (VARIANTS["procedure_demo"].tail_weight(Slot.GUIDE)
            > VARIANTS["explainer"].tail_weight(Slot.GUIDE))
    assert (VARIANTS["myth_busting"].tail_weight(Slot.FEEDBACK)
            > VARIANTS["procedure_demo"].tail_weight(Slot.FEEDBACK))
    assert (VARIANTS["scenario"].tail_weight(Slot.ELICIT)
            > VARIANTS["explainer"].tail_weight(Slot.ELICIT))


# ------------------------------------------------------------- the form

def test_plan_slots_returns_all_nine_in_canonical_order():
    form = gagne.plan_slots("explainer", BUDGET)
    assert [s.slot for s in form] == list(Slot)
    assert all(s.treatment for s in form)


def test_plan_slots_allocates_the_whole_budget_within_rounding():
    total = gagne.total_seconds("explainer", BUDGET)
    assert abs(total - BUDGET) <= len(TAIL_SLOTS), (
        f"derived total {total}s vs budget {BUDGET}s")


def test_the_tail_absorbs_the_remainder_not_the_capped_slots():
    small = {s.slot: s.seconds for s in gagne.plan_slots("explainer", 200)}
    large = {s.slot: s.seconds for s in gagne.plan_slots("explainer", 360)}
    for slot in CAPPED_SLOTS:
        assert small[slot] == large[slot]
    for slot in TAIL_SLOTS:
        assert large[slot] > small[slot]


# ------------------------------------------------------------- budgeting

def test_a_budget_too_small_raises_and_names_the_minimum():
    """Do not squeeze silently: a two-second feedback slot is a missing one."""
    with pytest.raises(gagne.BudgetError) as e:
        gagne.plan_slots("explainer", 140)
    msg = str(e.value)
    assert str(gagne.MIN_VIABLE_BUDGET_SECONDS) in msg
    assert "split the objective" in msg


def test_the_minimum_viable_budget_is_itself_viable():
    form = gagne.plan_slots("explainer", gagne.MIN_VIABLE_BUDGET_SECONDS)
    assert all(s.seconds > 0 for s in form)


# --------------------------------------------- deliberately unimplemented

@pytest.mark.parametrize("name,needle", [
    ("interview_dialogue", "migration 0002"),
    ("recap", "not a recap"),
])
def test_unimplemented_variants_raise_with_the_reason(name, needle):
    with pytest.raises(gagne.VariantError) as e:
        gagne.variant(name)
    assert needle in str(e.value)


def test_recap_is_not_silently_available_via_plan_slots():
    with pytest.raises(gagne.VariantError):
        gagne.plan_slots("recap", BUDGET)


def test_implemented_variants_are_the_seven_that_survive_9_1():
    assert set(VARIANTS) == {
        "explainer", "worked_example", "case_study", "compare_contrast",
        "procedure_demo", "scenario", "myth_busting"}


def test_an_unknown_name_lists_both_implemented_and_unimplemented():
    with pytest.raises(gagne.VariantError) as e:
        gagne.variant("documentary")
    assert "Implemented:" in str(e.value) and "unimplemented:" in str(e.value)
