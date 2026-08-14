# Script snapshot — mvcc-write-skew / v1

    run id          v3-run4 configuration, sample taken 15 Aug 2026
    brief version   v4
    objective graph 5 objectives (2 taught)
    extractor       objective_extractor@v3+b5687d51
    planner         curriculum_planner@v1+ad8ed399
    script writer   script_writer@v2+6fa223e0
    models          claude-opus-5 (extraction) / claude-sonnet-5 (plan, script)
    body sha256     3c795c89e6d6

Raw, unedited output of `explainer script show mvcc-write-skew v1`. This file
exists because the terminal paste keeps scrolling out of reach, and week 4's
§9.4 on-screen-text rules are specified against THIS narration.

The header carries the run id and brief version deliberately: an earlier copy of
this file went stale silently when the graph was regenerated beneath it. If the
brief version here does not match `explainer course brief mvcc-write-skew`, this
snapshot is out of date and any §9.4 number computed from it is not attributable.

KNOWN GAP IN THIS NARRATION: it does not name dirty read, non-repeatable read or
phantom read. That is the v3-run4 configuration's measured behaviour — 0 of 3
samples named all three — not a one-off. See the re-establishment header in
tests/gold/mvcc_alignment.yaml.

`duration=null` on every scene is CHALLENGES R5 holding: duration is derived from
TTS, which is week 5. The `sp_` ids are the span ids cues anchor to (R3/R4).

```
v1  [explainer]  Predict what a transaction reads and spot write skew
budget 240s  objectives o1, o2

 1. s01  hook       target 15s  duration=null  elastic  obj=o1  load=low
      sp_f15c23b91f  Two doctors share on-call duty.
      sp_28a7a9e42a  Hospital rule: at least one has to be on call at all times.
      sp_b3e81281b2  Each one checks the schedule, sees the other's still on call, and signs off.
      sp_ac63ecac57  Both queries were correct.
      sp_6b5aad9a06  Both transactions commit.
      sp_be86458452  Now nobody's on call.
      sp_a70976151d  How?

 2. s02  objective  target 10s  duration=null  elastic  obj=o1  load=low
      sp_6f5dc6b7a9  You'll work out exactly what each transaction can see, and why.

 3. s03  recall     target 20s  duration=null  elastic  obj=o1  load=low
      new terms: repeatable read, snapshot
      sp_1d6687bedf  Remember: Postgres tags every transaction with an xid.
      sp_e1ba03fbb3  Isolation, the 'I' in ACID, promises your transaction a consistent view of the data while others run concurrently.
      sp_0ae658bb9f  Repeatable Read keeps that promise with a snapshot
      sp_7441dc2246  a fixed picture of which transactions count as committed, and it stays fixed until you commit.
      [WARNING] readability_fk: Flesch-Kincaid grade 11.44 exceeds the technical limit of 11.0.

 4. s04  present    target 90s  duration=null  rigid  obj=o1  load=high
      new terms: xmin, xmax
      sp_ddf6ab63a0  Here's the mechanism.
      sp_2edfee100d  Every row version carries two hidden columns: xmin, the id of the transaction that created it, and xmax, the id of the transaction that deleted or replaced it.
      sp_e89b290061  A version is visible to you only if xmin's transaction had committed before your snapshot started, and xmax is either blank or belongs to a transaction that hadn't committed yet.
      sp_2f32e0042f  Here's the detail that trips people up: you don't get your snapshot at BEGIN.
      sp_0d54aa40f1  You get it at your first real statement — your first SELECT or UPDATE.
      sp_762ac4892f  Anything that commits between BEGIN and that first statement lands inside your snapshot, fully visible.
      sp_6aae3aa5ba  Anything that commits after your first statement stays invisible for the rest of your transaction, no matter how many statements follow.
      sp_af2a97991c  So to predict a read, don't ask what's true right now.
      sp_39bfbe5d8e  Ask, for every version of the row: which xid is its xmin, did that xid commit before your snapshot started, and does xmax rule this version out.
      sp_43ba60b4d6  Answer those three questions and you know exactly what the SELECT returns
      sp_b42499abd9  what your snapshot locked in, not what's changed since.

 5. s05  guide      target 36s  duration=null  rigid  obj=o2  load=high
      new terms: write skew, invariant
      sp_cc967dc0d5  Walk through the doctors with xids.
      sp_4420e1f624  T1 and T2 both start Repeatable Read and take snapshots.
      sp_6e4df036a2  Each reads the same two rows — both marked on-call, both xmins already committed.
      sp_421d60c025  Each decides it's safe to go off-call, and each updates only its own row.
      sp_2410d5fed1  Neither write touches the row the other read or wrote, so Postgres has nothing to flag.
      sp_9607377e85  Both commits succeed
      sp_4a211b44ad  but the invariant, 'at least one doctor on call,' spans both rows, and no single write ever touched both.
      sp_f08b646895  That's write skew: two safe transactions, one broken rule, and nothing Postgres could catch.

 6. s06  elicit     target 17s  duration=null  elastic  obj=o2  load=medium
      sp_7fde129522  Now try a variant.
      sp_cfcd0a870f  Same two transactions, same snapshots
      sp_8aba868d3b  but this time T1 updates T2's row instead of its own, setting T2 off-call directly, then commits.
      sp_6162cf6084  What happens when T2 tries to commit its own update to that same row?
      sp_426e243c5b  Write skew, or something else?
      [WARNING] speaking_rate: 46 words need 17.2s at 160 wpm but the elicit slot budgets 17s (2% over; 45 words fit).

 7. s07  feedback   target 23s  duration=null  rigid  obj=o2  load=medium
      new terms: same-row conflict, serialization failure
      sp_167d5fd759  That's not write skew — it's a same-row conflict.
      sp_c3d981ec7c  Both transactions try to write the same row version.
      sp_8094debab2  Postgres detects that at commit time and aborts the second committer with a serialization failure, forcing a retry.
      sp_4743f15529  Write skew only happens when each transaction writes a different row than the other read
      sp_71dc1bd43c  that's what let the doctors slip through undetected.

 8. s08  assess     target 18s  duration=null  elastic  obj=o2  load=medium
      sp_ad34e074ab  Two transactions each check a shared balance, then withdraw from two different accounts that together must stay non-negative.
      sp_b14a6228b1  Neither write touches a row the other read.
      sp_b20328c160  Write skew, or a serialization failure?
      sp_a3ded570a3  Name the invariant at risk.

 9. s09  retain     target 12s  duration=null  elastic  obj=o2  load=low
      sp_19992c27e9  You can now trace what a Repeatable Read transaction sees, and catch write skew before it ships.
      sp_67dbbf7932  Say out loud: which invariant in your own schema spans more than one row?

9 scenes, 47 spans, 2 findings
```
