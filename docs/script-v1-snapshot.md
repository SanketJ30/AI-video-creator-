# Script snapshot — mvcc-write-skew / v1

Raw, unedited output of `explainer script show mvcc-write-skew v1`, captured
14 Aug 2026 from week 3 run 2:

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

```
v1  [explainer]  Why concurrent reads can miss each other's writes
budget 240s  objectives o1, o2

 1. s01  hook       target 15s  duration=null  elastic  obj=o1  load=medium
      sp_2295b26d67  Session A reads a row.
      sp_70c82b8c5d  Session B updates that same row and commits.
      sp_5eaa606612  Session A reads it again — same query, same transaction — and sees the exact same old value.
      sp_620c57675d  No error, no wait.
      sp_694a37086b  Why does the row look frozen to A, even though B already committed?

 2. s02  objective  target 10s  duration=null  elastic  obj=o1  load=low
      sp_e427e4e669  You'll work out exactly what each transaction can see, and why.

 3. s03  recall     target 20s  duration=null  elastic  obj=o1  load=low
      new terms: repeatable read, snapshot
      sp_5226399096  Remember that Postgres stamps every transaction with an increasing xid the moment it starts.
      sp_fa5068fb94  Remember too that isolation controls what one transaction can see of concurrent work.
      sp_901d265e18  Repeatable Read fixes that view for a transaction's entire duration using a snapshot
      sp_224072b017  a frozen record of which transactions counted as committed at one instant.
      [WARNING] readability_fk: Flesch-Kincaid grade 11.82 exceeds the technical limit of 11.0.

 4. s04  present    target 90s  duration=null  rigid  obj=o1  load=high
      new terms: xmin, xmax
      sp_329e8ef1c8  Here's the mechanism.
      sp_56ca949bd9  Under Repeatable Read, Postgres doesn't take that snapshot at BEGIN
      sp_321e421195  it takes it at your transaction's first real statement, the first SELECT or UPDATE.
      sp_e12f7823bd  Every row version in the table carries two hidden fields.
      sp_a9ae608543  Xmin is the id of the transaction that created that version.
      sp_10cbf954a4  Xmax is the id of the transaction that expired it
      sp_c7436d1b54  deleted it, or replaced it with a newer version.
      sp_e39db7e5f0  A row version is visible to you only if xmin's transaction had committed before your snapshot moment, and xmax is either empty or belongs to a transaction that hadn't committed yet at that moment.
      sp_244b4be649  Now trace it.
      sp_0208e0e7dc  Session A's first SELECT fires at time T1, locking in its snapshot.
      sp_ae96754de3  It reads a row with xmin 100 — committed long before T1 — and xmax empty.
      sp_0dcd72fddb  Visible.
      sp_26bb675148  Session B then updates that same row: the old version gets xmax 105, a new version gets xmin 105, and B commits at T2, after T1.
      sp_4e557fb8e2  Session A runs the same SELECT again, still inside the same transaction.
      sp_d222249c06  Repeatable Read means it reuses the T1 snapshot, not a fresh one.
      sp_2c0444d568  Xmax 105 committed after T1, so the old version still counts as not-yet-expired for A.
      sp_65918d6d33  A reads xmin 100 again.
      sp_6383850856  Same row, same value, both times, because A's whole transaction lives inside one snapshot.

 5. s05  guide      target 36s  duration=null  rigid  obj=o2  load=high
      sp_384c449de0  Picture two on-call doctors, Alice and Bob, with one rule: at least one has to stay on call.
      sp_9634eb6937  Transaction one reads the on-call table, counts two doctors, checks the rule
      sp_ccee603eb3  fine
      sp_3ea2675d4e  and takes Alice off call.
      sp_f9b5492a05  Transaction two starts before transaction one commits.
      sp_e66df9181c  It reads the same table and still sees two doctors, because Postgres took its snapshot before Alice's row changed.
      sp_23ec16511d  It checks the rule — also fine — and takes Bob off call.
      sp_d6a6891c3c  Both transactions touch different rows, so nothing conflicts.
      sp_f106edde35  Both commit.

 6. s06  elicit     target 17s  duration=null  elastic  obj=o2  load=medium
      new terms: serialization error
      sp_2e712836c5  Both transactions commit clean — no serialization error, the abort Postgres throws when it catches a real conflict.
      sp_6af877e819  It doesn't catch one here.
      sp_ec4a44b3a5  Pause: how many doctors are on call once both commits land, and which rule does that quietly break?

 7. s07  feedback   target 23s  duration=null  elastic  obj=o2  load=medium
      new terms: write skew
      sp_393a97b57b  Zero.
      sp_795b389d2c  Both doctors go off call, breaking the invariant that at least one must stay on call
      sp_4d8276dafc  a rule spanning both rows together, not one.
      sp_96a005387f  That's write skew: each transaction reads a set of rows, checks the rule, then writes a different row.
      sp_89a3add784  Their writes never touch, so Postgres sees no conflict.

 8. s08  assess     target 18s  duration=null  elastic  obj=o2  load=medium
      sp_df40d1b436  Try this one yourself.
      sp_2badad709f  Two transactions each read a shared inventory count of 10 units, both confirm that's enough to reserve their own separate order of 6 units, and both then commit.
      sp_9c421e99a7  Does this produce write skew, and which invariant breaks?

 9. s09  retain     target 12s  duration=null  elastic  obj=o2  load=low
      sp_fbe77af772  Pause and put it in your own words: what makes a snapshot fix what a transaction sees, and why can two rule-respecting transactions still break a rule that spans rows they never both touched?
      [WARNING] readability_fk: Flesch-Kincaid grade 13.98 exceeds the technical limit of 11.0.

9 scenes, 49 spans, 2 findings
```
