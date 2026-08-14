# Script snapshot — mvcc-write-skew / v1

    run id          v3-run5 configuration, sample taken 15 Aug 2026
    brief version   v5
    objective graph 7 objectives (4 taught)
    extractor       objective_extractor@v3+b5687d51
    planner         curriculum_planner@v1+ad8ed399
    script writer   script_writer@v2+6fa223e0
    models          claude-opus-5 (extraction) / claude-sonnet-5 (plan, script)
    body sha256     93b9b17489a4

Raw, unedited output of `explainer script show mvcc-write-skew v1`. This file
exists because the terminal paste keeps scrolling out of reach, and week 4's
§9.4 on-screen-text rules are specified against THIS narration.

The header carries the run id and brief version deliberately: an earlier copy of
this file went stale silently when the graph was regenerated beneath it. If the
brief version here does not match `explainer course brief mvcc-write-skew`, this
snapshot is out of date and any §9.4 number computed from it is not attributable.

SCOPE: this is video 1 of 2. max_videos was raised to 2 on 15 Aug so the
objective graph had room for the anomaly taxonomy, which recovered to 3 of 3
samples. Video 2 ("Spotting write skew and fixing it", objectives o6 and o7)
exists in the curriculum plan as the continuity demo and is NOT built for
Milestone A — so the write-skew narration itself lives in a video that has no
script yet. Week 4's §9.4 numbers are measured against video 1 only.

`duration=null` on every scene is CHALLENGES R5 holding: duration is derived from
TTS, which is week 5. The `sp_` ids are the span ids cues anchor to (R3/R4).

```
v1  [procedure_demo]  How Postgres picks which row version you see
budget 240s  objectives o4, o5

 1. s01  hook       target 15s  duration=null  elastic  obj=o4  load=low
      sp_38f0bbd163  You update a row and commit.
      sp_41777ef3d0  A second session, already mid-transaction, queries that same row a moment later - and gets the old value back.
      sp_9197c6eafe  No error, no lag.
      sp_307e3add02  What is Postgres actually storing under the hood?

 2. s02  objective  target 10s  duration=null  elastic  obj=o4  load=low
      sp_c3e0bde6c1  You'll see how Postgres keeps several versions of a row and picks the one you get.

 3. s03  recall     target 20s  duration=null  elastic  obj=o4  load=low
      sp_eebbd50f86  Recall that every transaction gets a transaction id, an xid, the moment it starts touching data.
      sp_95277ad66b  Lower xids mean earlier transactions.
      sp_d2a6cf40d6  Keep that ordering in mind - it's how Postgres will decide, in a moment, which version of a row counts as done and which doesn't.

 4. s04  present    target 90s  duration=null  rigid  obj=o4  load=high
      new terms: xmin, xmax, snapshot
      sp_fd66440171  Here's the mechanism.
      sp_7070617359  When you run an UPDATE in Postgres, it doesn't overwrite the row in place.
      sp_645c8bfcb9  It writes a brand new copy of the row, right there on disk, and leaves the old copy sitting next to it.
      sp_763ea49959  Both versions exist at the same time.
      sp_ef96d56af6  Each version carries two hidden fields: xmin and xmax.
      sp_7aa2fd69f2  Xmin holds the xid of the transaction that inserted that version.
      sp_b6433ca49b  Xmax holds the xid of the transaction that deleted or updated it away - the transaction that made it obsolete.
      sp_56f3d195d7  A freshly inserted row has xmin set and xmax empty.
      sp_9b0397b713  Once another transaction updates that row, its xmax gets filled in with the updating transaction's xid, and a new row version appears with that same xid as its xmin.
      sp_dc4b87dda4  So for one logical row, you might have two physical versions sitting in the table: the old one, xmin 100, xmax 105, and the new one, xmin 105, xmax empty.
      sp_20e79dfad5  Now, which one do you see?
      sp_d5e53a67b3  Postgres decides using a snapshot - a rule for which xids count as 'already done' and which don't.
      sp_5cb55e3885  A version is visible to you only if its xmin belongs to a committed transaction your snapshot includes, and its xmax does not - meaning nothing that counts, from your point of view, has deleted it yet.

 5. s05  guide      target 52s  duration=null  rigid  obj=o5  load=high
      new terms: repeatable read
      sp_805dd0c422  Let's trace two sessions against one row.
      sp_735c35c10a  Session A runs BEGIN, then SELECT, and sees balance 100.
      sp_7a9e8947f2  Session B runs BEGIN, then UPDATE, setting balance to 200, and commits as xid 105.
      sp_2bf23b30f8  Here's the detail that trips people up: A's snapshot isn't taken at BEGIN.
      sp_a7a61a0ddb  It's taken at A's first statement - that SELECT.
      sp_ec0216100c  At that moment, B hasn't committed yet, so the snapshot treats xid 105 as still running, not done.
      sp_7160d2cee2  Now A runs a second SELECT, after B's commit.
      sp_5dede9931e  Under Repeatable Read - the isolation level that locks in one snapshot for your whole transaction - A keeps using that same snapshot from its first statement.
      sp_8fe328b93f  So even though B has committed, A's snapshot still doesn't count 105 as done.
      sp_487a3874c0  The old row version, xmin 100 xmax 105, is still what A sees.

 6. s06  elicit     target 17s  duration=null  elastic  obj=o5  load=medium
      sp_7999c1e84e  Pause here.
      sp_58702a1471  Session A runs a third SELECT, but only after it commits and starts a brand new transaction with a fresh BEGIN and SELECT.
      sp_7a487a509d  What does it read now - the old balance, or the new one?
      sp_3bad714357  Work it out before moving on.

 7. s07  feedback   target 19s  duration=null  elastic  obj=o5  load=medium
      sp_3cf15ebd36  It reads 200, the new balance.
      sp_f640f1101d  Once A commits, its old snapshot is gone.
      sp_270ce6abbb  The next BEGIN and SELECT grab a fresh snapshot, one where xid 105 already counts as committed.
      sp_d194ccca50  It's tempting to think the old value should stick, but repeatability only holds inside one transaction, not across it.

 8. s08  assess     target 10s  duration=null  elastic  obj=o5  load=medium
      sp_f2f1eea4d9  Given a new timeline with three sessions interleaving BEGIN, SELECT and UPDATE, write down what each SELECT reads and when its snapshot was taken.
      [WARNING] readability_fk: Flesch-Kincaid grade 11.96 exceeds the technical limit of 11.0.
      [WARNING] passive_voice: 100% of sentences look passive, over the 20% limit. Flagged: "Given a new timeline with three sessions interleaving BEGIN, SELECT and UPDATE, write down what each SELECT reads and when its snapshot was taken."

 9. s09  retain     target 6s  duration=null  elastic  obj=o5  load=low
      sp_18ad052d81  Sum up in one sentence how a snapshot decides what you see.
      sp_32f98f1224  Next: write skew.

9 scenes, 42 spans, 2 findings
```
