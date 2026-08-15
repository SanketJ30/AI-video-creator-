# Design system implementation — audit of §13 and §14

Written before building anything for these two sections, because much of what
they ask for already existed in the pipeline under different names.

---

## §13 Narration synchronisation — mostly already built, one real gap

> "The animation should follow the spoken explanation, not run independently …
> The visual corresponding to a spoken idea should be visible when that idea is
> being explained, not several seconds before or after."

### Already existed, under the name "signalling"

| §13 asks for | exists as | since |
|---|---|---|
| animation follows the spoken explanation | every cue anchors to a **span id**, never a timestamp (CHALLENGES R3) | week 4 |
| the visual appears when the idea is explained | `signal_designer` picks the span whose words name the thing being signalled | week 4 |
| "not several seconds before or after" | §9.2's ±150 ms offset tolerance, enforced by `check_offset` | week 4 |
| a spoken time becoming a concrete moment | `resolver.resolve_cue` resolves a span anchor to a local time, never absolute | week 5 |

So §13's mechanism was already in place. Nothing needed inventing — and
inventing a second timing system in the renderer would have produced a second
opinion about narration synchronisation, with the wrong one winning, since the
anchored one is the one tied to the words.

### The real gap, found by looking

**§14's disclosure clock and §9.2's cue clock disagreed.**

Disclosure was proportional to scene duration: item *i* of *n* appears at
`(i+1)/(n+1)`. Cues are anchored to narration. On a 4-row table over 120 frames
at 30 fps:

```
row 3 discloses at    (3+1)/(4+1) x 120 / 30  =  3.2 s
cue on rows[3] fires at                           2.0 s
                                               ---------
the cue emphasised a row that was not on screen for another 1.2 s
```

**Fixed** by letting the narration pull an element forward: an item is disclosed
when its proportional turn arrives **or** when a cue targeting it fires. The
spoken time wins, because it is the one anchored to meaning. This used the
anchors the signal designer already emits — no new field, no new agent, five
lines.

### Still missing, and not faked

**BUILD order itself is not narration-anchored** — it is only pulled forward by
cues. §13's own example is a build following the words:

> "First, we collect the data." → **DATA** appears.
> "Then we train a baseline." → **BASELINE** appears and connects to DATA.

An element with no cue still discloses on the proportional clock. Closing this
properly needs a **step → span mapping that nothing currently emits**: the
visual planner would have to say which span each build step belongs to. That is
a new field and a prompt change.

It is **not** inferred here. A guessed mapping — item *i* → span ⌊*i·m/n*⌋ —
would look synchronised and be wrong in exactly the cases that matter, which is
the same failure mode the estimated word timings already carry (W3). Recorded
rather than approximated.

---

## §14 Progressive disclosure — already built

> "The renderer should default to one conceptual unit at a time rather than
> everything at once."

Implemented since week 4 as `revealed()`, now `started()` / `shown()` in
`motion.ts`. Two properties the design system names explicitly were already
true:

- **§9.5: "when a new row enters, old rows stay stable."** `started` is
  monotonic in `frame`, so a disclosed item never un-discloses. There is now a
  test saying why that matters.
- **§9.4: "previously introduced information should remain visible … this
  preserves the learner's mental map."** Same mechanism.

What §14 added was the *reason*, which is now a comment in the code rather than
folklore.

---

## What this audit actually records

Two of the six implementation steps needed almost no new code, because the
pipeline had already built the mechanism for a different stated reason — R3's
span anchoring exists for localisation and editing, and turns out to be exactly
what §13 needs.

The work was reading before writing. The one thing worth building was a
five-line reconciliation of two clocks that had been quietly disagreeing since
week 4, and it was only visible because the design system asked a question the
pipeline had not been asked before.
