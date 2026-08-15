# Constraints on the editor design (Phase 4+)

Things measured during Milestone A that constrain how the editor in PRD Phase 4
can be built. Recorded here rather than only in a week's findings, because a
findings doc is read once and an editor is designed later.

---

## E1 — The Fact Challenger cannot run on every save

**Measured.** A full challenge of one 9-scene video is **27 frontier-tier calls**
at 3 samples, costing **$0.70 per sample** and **~$2.10 per 3-sample run**.
Wall-clock is minutes, not seconds.

That is comfortably affordable as a **gate before review or publish** — §21's
per-video agent budget absorbs it and it is the highest-value agent in the
system. It is **not** affordable as a per-keystroke or per-save check in an
editor, and it is not fast enough to be one even if it were free.

**What this constrains.**

1. **The editor cannot promise live factual feedback.** Anything that looks like
   a spell-checker underline for facts is a promise this agent cannot keep at
   interactive latency.
2. **Challenges must be diff-scoped.** Re-challenging a whole video after a
   one-sentence edit is 27 calls to re-examine 39 unchanged spans. The unit of
   work is the span, findings already attach to spans, and a changed span is
   cheaply identifiable — so the editor should challenge *changed spans plus
   their scene's context*, not the video.
3. **Verdicts must be cached against span content.** A span whose text has not
   changed does not need re-challenging, and its previous verdict is still
   valid. This is the same content-addressing the render layer uses; the key is
   the span text plus the constraints plus the prompt version.
4. **Sampling is a deliberate, explicit action.** Three samples exist because the
   agent is stochastic and one clean pass proves nothing (invariant 8). The
   editor must not quietly run one sample and present it as a verdict — either
   it runs the full sample count or it labels the result as provisional.
5. **A cheaper tier is worth measuring, but not assuming.** Whether a mid-tier
   model retains the adversarial capability is an open question. The negative
   control (0/51 false positives) and positive control (caught at 0.90) are the
   instruments that would answer it — run both against the cheaper model before
   trusting it, never reason about it from price.

**What it does not constrain.** The deterministic linters (§9.6, §16.2) are free
and instant, and *should* run on every save. The split §9.6 draws between
deterministic and model-based work is also the split between what an editor can
do live and what it must schedule.

---

## E2 — Regeneration is not an edit affordance

Invariant 8: regenerating a stochastic stage is not a fix, it is a re-roll.
MEASURED — a deliberate regeneration to remove one blocking claim produced a
narration scoring worse, and reintroduced an error the challenger had already
found once.

**What this constrains.** A "regenerate this scene" button is a trap: it looks
like a fix and is a dice roll, and the user has no way to know the new draft is
worse without paying for a full challenge. If such a button exists it must:

- show what changed, not just replace the text;
- re-run the gates that passed before, because the new draft has not passed
  them;
- make keeping the previous draft the cheap default.

The correct edit affordance for a factual error is **editing the constraint**
(`brief.factual_constraints`) or **editing the sentence**, then regenerating —
in that order.

---

## E3 — the editor must be able to act on a single span

**Measured, ISSUE-19.** The Fact Challenger pinpoints defects to a span. The
script writer can only regenerate a whole video. So the smallest response to a
two-span problem is a 25-span re-roll — and invariant 8 says that re-roll is not
a fix, it is a dice throw that has already been observed to make a narration
worse.

**The precision of the diagnosis currently has nowhere to go.** Every finding
below the severity of "regenerate everything" is unactionable, which caps the
value of the challenger regardless of how good its verdicts are.

**What the editor needs, in order of how much it unlocks:**

1. **Regenerate one scene**, holding every other scene byte-identical. The scene
   is already the unit of the Gagné form, of the render, and of the cache; it is
   the obvious first grain.
2. **Regenerate one span in place**, given the surrounding narration as fixed
   context. This is what a challenger finding actually calls for. It needs the
   span's id to survive the rewrite, or every cue anchored to it breaks (R3) —
   which is a different operation from `Narration.author`, and neither
   constructor does it today.
3. **Accept a human edit as a first-class input**, distinguished in provenance
   from a generated one, so a hand-fixed span is visible as hand-fixed rather
   than laundered into looking machine-produced.

**Constraint on all three:** whatever regenerates must re-run the gates that
passed before. A scene regenerated in isolation has not been challenged, has not
been linted, and its `new_terms` have not been recomputed against the registry.
