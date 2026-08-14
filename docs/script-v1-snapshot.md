# Script snapshot — mvcc-write-skew / v1

Raw, unedited output of `explainer script show mvcc-write-skew v1`, captured
14 Aug 2026 from **brief v3** — the run after the anomaly-taxonomy diagnosis:

    objective_extractor@v3+b5687d51   (claude-opus-5)
    curriculum_planner@v1+ad8ed399    (claude-sonnet-5)
    script_writer@v2+6fa223e0         (claude-sonnet-5)

This file exists because the terminal paste keeps scrolling out of reach. Week 4
§9.4 specifies the relationship between this narration and on-screen text, so it
has to be readable outside the session that generated it.

Nothing below is edited. Two things to read deliberately rather than skim past:
`duration=null` on every scene is CHALLENGES R5 holding — duration is derived
from TTS, which is week 5 — and the `sp_` ids are the span ids cues will anchor
to (R3/R4), which is what §9.4's on-screen text gets measured against.

The script_type is `compare_contrast`, not `explainer`: the lead objective is
now analyze-level, and §9.1's Bloom table puts compare/contrast there. This is
the first run in which §8's second conceptual branch has been exercised.

```
v1  [compare_contrast]  Snapshots, row versions, and write skew
budget 240s  objectives o1, o2

 1. s01  hook       target 15s  duration=null  elastic  obj=o1  load=low
      sp_97b1389464  You run a SELECT inside a transaction.
      sp_3c9b5b0325  A moment earlier, someone else committed an update to that exact row.
      sp_0b18f029a6  Your SELECT still shows the old value.
      sp_375ca3b309  No error.
      sp_c742d20ede  No warning.
      sp_016f647f2f  What is your transaction actually looking at?

 2. s02  objective  target 10s  duration=null  elastic  obj=o1  load=low
      sp_6d24448e21  You'll work out exactly which row version each transaction can see, and why.

 3. s03  recall     target 20s  duration=null  elastic  obj=o1  load=low
      new terms: repeatable read, snapshot
      sp_119f9d6aa3  You already know that every transaction gets an xid, and that isolation means hiding concurrent changes from each other.
      sp_4df21a82c5  In PostgreSQL's Repeatable Read level, that hiding works through a snapshot: a fixed list of transactions that counted as already committed.
      sp_553425a35d  Your transaction checks everything it sees against that list.
      [WARNING] readability_fk: Flesch-Kincaid grade 11.01 exceeds the technical limit of 11.0.

 4. s04  present    target 90s  duration=null  rigid  obj=o1  load=high
      new terms: xmin, xmax
      sp_74a9b645d9  Here's how that snapshot decides what you see.
      sp_b590ecf9ca  Postgres never overwrites a row in place.
      sp_8870aefe10  Every row version carries two hidden fields.
      sp_00e9eec182  Xmin holds the id of the transaction that created that version.
      sp_251fe44d45  Xmax holds the id of the transaction that deleted or replaced it, once that happens.
      sp_1be4821053  When transaction B updates a row, Postgres writes a brand new version with xmin set to B's xid.
      sp_5ea3aa663f  At the same moment, it stamps the old version's xmax with that same xid.
      sp_a12c712c22  Both versions now sit in the table.
      sp_729cda171d  A version is visible to your transaction only if its xmin belongs to a transaction your snapshot counts as committed, and its xmax is empty, or belongs to a transaction your snapshot does not count as committed.
      sp_ec7345e15e  Here's the detail that trips people up: your snapshot doesn't form at BEGIN.
      sp_c4fbb7d198  It forms at your transaction's first statement.
      sp_e8b1f9001e  So picture transaction A opening with BEGIN, then sitting idle.
      sp_144b6fb912  Transaction B updates the row and commits while A waits.
      sp_0017388cec  Only then does A run its first SELECT.
      sp_dab334875e  A's snapshot forms at that instant, after B's commit, so A sees B's new version right away.
      sp_055a6377ea  Every later statement in A reuses that exact snapshot, so from here on A is frozen in time, no matter what else commits.

 5. s05  guide      target 38s  duration=null  rigid  obj=o2  load=high
      new terms: write skew
      sp_b53b863b21  Picture two on-call doctors.
      sp_c78bd57be6  The rule: at least one must stay on call.
      sp_82b447fe29  Transaction A reads the table, sees two doctors on call, and updates its own row to off-call
      sp_7f927ffedb  that's fine, one will still be on.
      sp_7256b7fd2b  Transaction B, in its own Repeatable Read transaction, read the same two-doctors count before A committed.
      sp_a1b4141100  B's snapshot never saw A's change, so B also updates its own row to off-call.
      sp_3a3515058e  Both commit.
      sp_6b160e4c46  Neither touched the row the other wrote, so nothing conflicts.
      sp_67ecaf1f58  But now zero doctors are on call.
      sp_1a9baf4406  That's write skew: each read was true, each write looked safe alone, but together they break the rule.
      [WARNING] speaking_rate: 105 words need 39.4s at 160 wpm but the guide slot budgets 38s (4% over; 101 words fit).

 6. s06  elicit     target 18s  duration=null  elastic  obj=o2  load=medium
      sp_4f0161ae3a  Now suppose two transactions each check a shared balance, confirm it covers a withdrawal, and then both update the very same account row.
      sp_f17e7a2535  Before I tell you: do both commit, producing write skew — or does Postgres abort one of them?
      sp_db81dd9288  Think about which row each transaction actually writes to.
      [WARNING] speaking_rate: 49 words need 18.4s at 160 wpm but the elicit slot budgets 18s (2% over; 48 words fit).

 7. s07  feedback   target 24s  duration=null  rigid  obj=o2  load=high
      new terms: write-write conflict, serialization failure
      sp_f335aadeed  Postgres aborts one of them.
      sp_cc0885ebea  Both transactions target the exact same row — that's a write-write conflict.
      sp_cf757a79db  The second one to update it hits a version that changed after its snapshot formed, so Repeatable Read throws a serialization failure, and it must retry.
      sp_44003d90b8  A and B, though, wrote two different rows, so Postgres never saw a conflict there.
      sp_dcd426799d  Write skew slips through because the two transactions never touch the same row
      sp_3806f941df  only the shared rule breaks.
      [WARNING] speaking_rate: 75 words need 28.1s at 160 wpm but the feedback slot budgets 24s (17% over; 64 words fit).

 8. s08  assess     target 15s  duration=null  elastic  obj=o2  load=medium
      sp_bb48a0e581  Here's one for you: two transactions each read expense rows, confirm the total is under budget, then each update a different row, adding an expense that pushes the true total over.
      sp_85b076dcf6  Neither errors.
      sp_718ddf755d  Name the anomaly, and the invariant it breaks.
      [WARNING] speaking_rate: 41 words need 15.4s at 160 wpm but the assess slot budgets 15s (2% over; 40 words fit).

 9. s09  retain     target 10s  duration=null  elastic  obj=o2  load=low
      sp_f2f0643302  Pause and say back, in your own words, how xmin, xmax, and snapshot timing decide what you see
      sp_ebc8d72755  and what makes write skew invisible to the engine.

9 scenes, 50 spans, 5 findings
```
