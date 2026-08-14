"""The Gagné nine-slot template (Sequence v0.2 §9.1, §6 Stage 2c).

    "Why Gagné as the scene template is the key move: it converts 'write a
     storyboard' from open-ended generation into slot-filling with typed slots,
     each with its own duration budget, visual treatment rule and validation."

Pure data and code. No model calls, ever — this module is the form the script
writer fills in, and a form that argues with itself is not a form.

## How time is allocated, and why it is split in two

§9.1 states absolute seconds for the first four slots and states nothing for the
last five:

    1 hook       <=15s   gain attention
    2 objective  <=10s   stated verbatim; reused as the scene title
    3 recall     <=20s   link to a prior objective BY ID (course memory)
    4 present    60-120s chunks, Mayer rules apply
    5 guidance           signalling, worked example, analogy
    6 elicit             pause-and-do prompt
    7 feedback           reveal + explanation
    8 assess             linked assessment item, SAME Bloom level
    9 retain             summary + spaced-review scheduling hook

**Slots 1-4 are absolute and identical across every variant.** They are capped
for cognitive reasons, not budget reasons: a hook stops working past about
fifteen seconds whether the video is three minutes or six. They do not scale
with `target_seconds_per_video`, and no variant may reweight them.

**Slots 5-9 absorb the remainder**, distributed by per-variant weight. That is
the only place a variant's character legitimately lives, and the only place this
module authors numbers at all — see AUTHORED_TAIL_WEIGHTS, which is marked and
meant to be overwritten.

The video's total is therefore *derived*: 135 fixed seconds plus whatever the
brief's budget leaves. If the remainder is too small to run a guidance-through-
retain cycle, `plan_slots` raises rather than squeezing silently.

## Variants that cannot exist under §9.1

Two of the nine script types named in §6 Stage 2c raise instead of being
implemented, both because the spec as written does not admit them:

  * **Interview/Dialogue** — `videos_v2.script_type` in migration 0002 does not
    allow it, and a two-voice format needs a narration model this pipeline does
    not have.
  * **Review/Recap** — a recap video is mostly retrieval of prior material, but
    §9.1 caps `recall` at 20s and floors `present` at 60s. A template obeying
    both spends its bulk presenting new material, which is not a recap. §9.1
    describes a teaching video; a video that teaches nothing new is out of scope
    for v1 rather than a reason to raise the caps.

## What is NOT here

No duration in seconds is ever stored on a scene by anything downstream of this
module. `plan_slots` returns a *budget*, which the script writer records in
`pedagogy_meta.duration_target_seconds`. Real duration is derived from TTS
(CHALLENGES R5); authoring one would make a guess look like a measurement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Slot(str, Enum):
    """The nine events. Order is the canonical presentation order.

    These strings are the `gagne_slot` CHECK constraint in migration 0002. A
    tenth slot means a migration, not an edit here.
    """

    HOOK = "hook"
    OBJECTIVE = "objective"
    RECALL = "recall"
    PRESENT = "present"
    GUIDE = "guide"
    ELICIT = "elicit"
    FEEDBACK = "feedback"
    ASSESS = "assess"
    RETAIN = "retain"

    @property
    def ordinal(self) -> int:
        return list(Slot).index(self)


# ===========================================================================
# SPEC — Sequence v0.2 §9.1. Do not change without changing the PRD.
# ===========================================================================

# (floor, ceiling) in seconds. None means the spec states none.
SPEC_CAPS: dict[Slot, tuple[int | None, int | None]] = {
    Slot.HOOK: (None, 15),
    Slot.OBJECTIVE: (None, 10),
    Slot.RECALL: (None, 20),
    Slot.PRESENT: (60, 120),
}

CAPPED_SLOTS: tuple[Slot, ...] = (Slot.HOOK, Slot.OBJECTIVE, Slot.RECALL, Slot.PRESENT)
TAIL_SLOTS: tuple[Slot, ...] = (Slot.GUIDE, Slot.ELICIT, Slot.FEEDBACK,
                                Slot.ASSESS, Slot.RETAIN)

# ===========================================================================
# AUTHORED AND UNREVIEWED — every number below was invented by the agent that
# wrote this file, not taken from Sequence v0.2. They are gathered here rather
# than scattered through the variants so they can be overwritten in one place.
#
# Three tables. Overwrite freely; the tests check structure, not these values.
# ===========================================================================

# [AUTHORED] Slot 4 `present` is the one capped slot the spec gives as a BAND
# (60-120s) rather than a ceiling. 90 is the midpoint. Slots 1-3 take the spec
# ceiling directly, so they are not authored.
AUTHORED_PRESENT_SECONDS = 90

# [AUTHORED] The least time a tail slot can be given and still do its job — a
# prompt, a reveal, a question, a close each need a sentence or two. Drives the
# minimum viable video budget.
AUTHORED_MIN_TAIL_SLOT_SECONDS = 8

# [AUTHORED] Per-variant weighting of the tail budget (slots 5-9). Each row sums
# to 1.0. This is where a variant's character lives and where the judgment calls
# are: a procedure spends its tail guiding, a myth-busting video spends it on the
# elicit/feedback correction pair.
AUTHORED_TAIL_WEIGHTS: dict[str, dict[Slot, float]] = {
    #                    guide  elicit  feedback  assess  retain
    "explainer":        {Slot.GUIDE: 0.34, Slot.ELICIT: 0.16, Slot.FEEDBACK: 0.22,
                         Slot.ASSESS: 0.17, Slot.RETAIN: 0.11},
    "worked_example":   {Slot.GUIDE: 0.48, Slot.ELICIT: 0.15, Slot.FEEDBACK: 0.19,
                         Slot.ASSESS: 0.11, Slot.RETAIN: 0.07},
    "case_study":       {Slot.GUIDE: 0.40, Slot.ELICIT: 0.16, Slot.FEEDBACK: 0.22,
                         Slot.ASSESS: 0.13, Slot.RETAIN: 0.09},
    "compare_contrast": {Slot.GUIDE: 0.36, Slot.ELICIT: 0.17, Slot.FEEDBACK: 0.23,
                         Slot.ASSESS: 0.14, Slot.RETAIN: 0.10},
    "procedure_demo":   {Slot.GUIDE: 0.50, Slot.ELICIT: 0.16, Slot.FEEDBACK: 0.18,
                         Slot.ASSESS: 0.10, Slot.RETAIN: 0.06},
    "scenario":         {Slot.GUIDE: 0.30, Slot.ELICIT: 0.24, Slot.FEEDBACK: 0.26,
                         Slot.ASSESS: 0.11, Slot.RETAIN: 0.09},
    "myth_busting":     {Slot.GUIDE: 0.26, Slot.ELICIT: 0.24, Slot.FEEDBACK: 0.31,
                         Slot.ASSESS: 0.11, Slot.RETAIN: 0.08},
}

# ===========================================================================
# End of authored numbers.
# ===========================================================================

CAPPED_SLOT_SECONDS: dict[Slot, int] = {
    Slot.HOOK: SPEC_CAPS[Slot.HOOK][1],
    Slot.OBJECTIVE: SPEC_CAPS[Slot.OBJECTIVE][1],
    Slot.RECALL: SPEC_CAPS[Slot.RECALL][1],
    Slot.PRESENT: AUTHORED_PRESENT_SECONDS,
}
CAPPED_TOTAL_SECONDS = sum(CAPPED_SLOT_SECONDS.values())
MIN_TAIL_SECONDS = AUTHORED_MIN_TAIL_SLOT_SECONDS * len(TAIL_SLOTS)
MIN_VIABLE_BUDGET_SECONDS = CAPPED_TOTAL_SECONDS + MIN_TAIL_SECONDS


# Slots deliberately unimplemented, with the reason a human needs. Keyed by the
# name a caller would plausibly ask for.
UNIMPLEMENTED_VARIANTS: dict[str, str] = {
    "interview_dialogue": (
        "§6 Stage 2c names Interview/Dialogue, but videos_v2.script_type in "
        "migration 0002 does not allow it and a two-voice format needs a "
        "narration model this pipeline does not have. Implementing it means a "
        "migration and a spans.py change, not an entry in this table."),
    "recap": (
        "A recap video is mostly retrieval of prior material, but §9.1 caps "
        "`recall` at 20s and floors `present` at 60s — so a template obeying "
        "both spends its bulk presenting new material, which is not a recap. "
        "§9.1 describes a teaching video. A video that teaches nothing new is "
        "out of scope for v1; do not raise the caps to accommodate it."),
}


@dataclass(frozen=True)
class SlotSpec:
    """One slot's contract. `treatment` is what the narration is FOR — it is
    handed to the script writer as the slot's instruction, so it is written as
    a directive rather than a description."""

    slot: Slot
    required: bool
    treatment: str
    seconds: int
    # True where the seconds come from §9.1 rather than from this file.
    spec_capped: bool = False


# The treatment rules. Identical across variants — a hook is a hook whatever the
# script type. §9.1 supplies the one-line purpose; the rest is its working form.
TREATMENTS: dict[Slot, str] = {
    Slot.HOOK: (
        "Gain attention with a concrete situation the learner recognises. A "
        "question they cannot yet answer, or a result that looks wrong. Never a "
        "definition, never a preview of the video's structure."),
    Slot.OBJECTIVE: (
        "State what the learner will be able to do, verbatim from the objective. "
        "This text is reused as the scene title, so it must stand alone."),
    Slot.RECALL: (
        "Activate the specific prior objective this builds on, naming it. If the "
        "prerequisite is assumed rather than taught, restate it in one sentence "
        "rather than referring to a video that does not exist."),
    Slot.PRESENT: (
        "Teach the mechanism. One conceptual chunk; if it needs two, it needed "
        "two scenes. Mayer's rules apply hardest here: no aside, no fun fact, "
        "nothing on screen the narration does not refer to."),
    Slot.GUIDE: (
        "Guide with a worked example, an analogy, or explicit signalling through "
        "the hard step. Show the reasoning, not just the result."),
    Slot.ELICIT: (
        "Prompt the learner to do something before being told the answer — "
        "predict, choose, or explain in their own words. End on the prompt; do "
        "not answer it here."),
    Slot.FEEDBACK: (
        "Reveal the answer to the elicit prompt and explain why it is right, "
        "including why the plausible wrong answer is wrong."),
    Slot.ASSESS: (
        "Pose the linked assessment item at the SAME Bloom level as the "
        "objective. Recall questions do not verify an apply-level objective."),
    Slot.RETAIN: (
        "Summarise what the learner can now do and point forward. §9.5 wants "
        "this learner-generated where possible: prompt them to summarise rather "
        "than summarising for them."),
}

# §9.2 Generative activity: "Every video ends with at least one generative
# prompt ... Non-optional in the template." Plus the three slots without which
# there is no video at all.
ALWAYS_REQUIRED: frozenset[Slot] = frozenset(
    {Slot.HOOK, Slot.OBJECTIVE, Slot.PRESENT, Slot.ELICIT})


@dataclass(frozen=True)
class Variant:
    """One script type. Slots 1-4 are fixed by §9.1; only the tail differs."""

    name: str
    description: str
    tail_weights: dict[Slot, float] = field(default_factory=dict)
    optional: frozenset[Slot] = frozenset()

    @property
    def slots(self) -> list[Slot]:
        return list(Slot)          # every variant uses all nine

    def required_slots(self) -> list[Slot]:
        return [s for s in self.slots if s not in self.optional]

    def tail_weight(self, slot: Slot) -> float:
        return self.tail_weights.get(slot, 0.0)


VARIANT_DESCRIPTIONS: dict[str, str] = {
    "explainer": "Teach one mechanism end to end. §8's default for conceptual "
                 "material that is not a comparison.",
    "worked_example": "Work a problem through step by step, then fade support. "
                      "§9.1 puts this at Apply.",
    "case_study": "Walk a real situation and draw the principle out of it. §9.1 "
                  "puts case walkthrough at Analyze.",
    "compare_contrast": "Set two things side by side and make the difference the "
                        "lesson. §8's other conceptual option.",
    "procedure_demo": "Show how to do it, in order, on the real surface. §8 routes "
                      "procedural knowledge here.",
    "scenario": "Put the learner inside a situation and make them choose. "
                "Narrative pacing (§9.3 allows up to 185 wpm).",
    "myth_busting": "State the belief, show it failing, replace it. The elicit and "
                    "feedback pair carries the correction.",
}

VARIANTS: dict[str, Variant] = {
    name: Variant(name=name, description=VARIANT_DESCRIPTIONS[name],
                  tail_weights=weights)
    for name, weights in AUTHORED_TAIL_WEIGHTS.items()
}


class VariantError(KeyError):
    pass


class BudgetError(ValueError):
    """The video budget cannot host a §9.1-shaped video. Names the minimum."""


def variant(name: str) -> Variant:
    if name in VARIANTS:
        return VARIANTS[name]
    if name in UNIMPLEMENTED_VARIANTS:
        raise VariantError(f"'{name}' is deliberately unimplemented. "
                           f"{UNIMPLEMENTED_VARIANTS[name]}")
    raise VariantError(
        f"no slot-template variant '{name}'. Implemented: {sorted(VARIANTS)}. "
        f"Deliberately unimplemented: {sorted(UNIMPLEMENTED_VARIANTS)}.")


def check_caps() -> list[str]:
    """Check slots 1-4 against §9.1's literal numbers.

    Takes no budget argument on purpose: the capped slots do not scale, so there
    is no budget at which they can drift. Slots 5-9 have no spec caps and so
    nothing to check.
    """
    problems = []
    for slot in CAPPED_SLOTS:
        lo, hi = SPEC_CAPS[slot]
        secs = CAPPED_SLOT_SECONDS[slot]
        if hi is not None and secs > hi:
            problems.append(f"{slot.value}: {secs}s exceeds the §9.1 cap of {hi}s")
        if lo is not None and secs < lo:
            problems.append(f"{slot.value}: {secs}s is under the §9.1 floor of {lo}s")
    return problems


def tail_budget(target_seconds: int) -> int:
    """Seconds left for slots 5-9 after §9.1's fixed allocation."""
    return target_seconds - CAPPED_TOTAL_SECONDS


def plan_slots(script_type: str, target_seconds: int) -> list[SlotSpec]:
    """The form the script writer fills in, in canonical Gagné order.

    Raises `BudgetError` when the remainder cannot host slots 5-9 rather than
    squeezing them: a two-second feedback slot is not a short feedback slot, it
    is a missing one, and silently producing it would push the failure into the
    script where it is much harder to see.
    """
    v = variant(script_type)
    remainder = tail_budget(target_seconds)
    if remainder < MIN_TAIL_SECONDS:
        raise BudgetError(
            f"a {target_seconds}s budget leaves {remainder}s for slots 5-9 "
            f"(guide, elicit, feedback, assess, retain), which needs at least "
            f"{MIN_TAIL_SECONDS}s. §9.1's fixed slots 1-4 take "
            f"{CAPPED_TOTAL_SECONDS}s regardless of budget, so the minimum "
            f"viable target_seconds_per_video is {MIN_VIABLE_BUDGET_SECONDS}s. "
            f"Raise the brief's budget or split the objective across two videos.")

    out: list[SlotSpec] = []
    for slot in Slot:
        if slot in CAPPED_SLOT_SECONDS:
            secs, capped = CAPPED_SLOT_SECONDS[slot], True
        else:
            secs, capped = round(v.tail_weight(slot) * remainder), False
        out.append(SlotSpec(slot=slot, required=slot not in v.optional,
                            treatment=TREATMENTS[slot], seconds=secs,
                            spec_capped=capped))
    return out


def total_seconds(script_type: str, target_seconds: int) -> int:
    """The video's derived total — what the slots actually add up to."""
    return sum(s.seconds for s in plan_slots(script_type, target_seconds))
