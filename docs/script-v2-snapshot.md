# Script snapshot — mvcc-write-skew / v2

    run id          v3-run5 configuration, sample taken 15 Aug 2026
    brief version   v5
    objective graph 7 objectives (4 taught)
    extractor       objective_extractor@v3+b5687d51
    planner         curriculum_planner@v1+ad8ed399
    script writer   script_writer@v2+c0a77029
    models          claude-opus-5 (extraction) / claude-sonnet-5 (plan, script)
    body sha256     47833a387aad

Raw, unedited output of `explainer script show mvcc-write-skew v2`. This file
exists because the terminal paste keeps scrolling out of reach, and week 4's
§9.4 on-screen-text rules are specified against THIS narration.

The header carries the run id and brief version deliberately: an earlier copy of
this file went stale silently when the graph was regenerated beneath it. If the
brief version here does not match `explainer course brief mvcc-write-skew`, this
snapshot is out of date and any §9.4 number computed from it is not attributable.

SCOPE: this is video 2 of 2, and it is the one Milestone A builds. v1 ("How
Postgres picks which row version you see", objectives o4 and o5) stays in the
graph unbuilt as v2's prerequisite. v2 was chosen over v1 deliberately: the topic
exists for write skew and the ANSI-vs-PostgreSQL trap, and building the
prerequisite video would mean week 6's review judges the easy half while the trap
never reaches the screen. Building v2 also makes §9.1 slot 3 testable — the
recall slot has a real prior video to link back to, which is the course-memory
mechanism behind Wedge A.

Week 4's §9.4 numbers are measured against THIS narration: v3-run5 configuration,
brief v5, video v2.

FINDING VISIBLE IN THE RECALL SLOT BELOW: the course-memory link is not being
made. `_course_position` passes v1's two objectives with their learner-facing
statements, and prompts/script_writer.v2.md instructs the recall slot to activate
one of them by name. The model instead recalled what Repeatable Read blocks —
which is this video's own content, not the previous video's. Wiring correct,
prompt correct, behaviour wrong. Not fixed here; fixing it is a prompt version
and belongs with the rest of the Stage 2c work.

`duration=null` on every scene is CHALLENGES R5 holding: duration is derived from
TTS, which is week 5. The `sp_` ids are the span ids cues anchor to (R3/R4).

```
v2  [procedure_demo]  Spotting write skew and fixing it
budget 240s  objectives o6, o7

 1. s01  hook       target 15s  duration=null  elastic  obj=o6  load=low
      sp_378f4b4314  Two doctors are on call tonight.
      sp_f4cf308783  Each checks the schedule, sees a colleague listed too, and taps 'off duty.' Postgres commits both requests without a single error.
      sp_70d8e1e9ce  But when the board refreshes, nobody's covering the shift tonight.
      sp_5cff6d5311  What happened?

 2. s02  objective  target 10s  duration=null  elastic  obj=o6  load=low
      sp_40ffa17000  You'll spot write skew in a transaction pair that Postgres lets commit without complaint.

 3. s03  recall     target 20s  duration=null  elastic  obj=o6  load=medium
      sp_836dafb0b5  You already know how Postgres's Repeatable Read isolation behaves: it blocks a non-repeatable read, blocks a phantom, and blocks two transactions from losing an update when they write the same row
      sp_6d94d3c56a  each one stopped with a could-not-serialize error.
      sp_bab37b1c8f  Today's transactions won't trigger any of that.
      sp_5837ce3d92  They'll pass every check Repeatable Read runs, and still get it wrong.
      [WARNING] readability_fk: Flesch-Kincaid grade 11.07 exceeds the technical limit of 11.0.
      [WARNING] speaking_rate: 57 words need 21.4s at 160 wpm but the recall slot budgets 20s (8% over; 53 words fit).

 4. s04  present    target 90s  duration=null  rigid  obj=o6  load=high
      new terms: snapshot, write skew
      sp_3dc90ed249  Here's the mechanism.
      sp_c6249782cc  Both doctors start their transactions at the same instant, so Postgres hands each one a snapshot
      sp_ade42574d7  a frozen view of the on-call table as it looked the moment the transaction began.
      sp_acde26c2a5  In that snapshot, two doctors show as on call.
      sp_88c9f341ee  Doctor A runs a check: 'is anyone else on call besides me?' The snapshot says yes, so A updates A's own row to off duty.
      sp_b51bf5d0cd  At the same moment, Doctor B runs the identical check against B's own snapshot, sees the same two doctors, and updates B's own row too.
      sp_b735cd9656  Neither transaction writes the row the other one reads.
      sp_4f06ffeab0  A only writes A's row; B only writes B's row.
      sp_1c3727ba32  Repeatable Read watches for two transactions writing the same row
      sp_8a2f1d1015  that collision is what triggers a could-not-serialize error.
      sp_c0aefbdd27  Here there's no collision, so Postgres has nothing to catch.
      sp_0a69c74ccc  Both commit cleanly, and the table now shows zero doctors on call.
      sp_4f71576f79  The rule that broke
      sp_4ad90a3a7d  at least one doctor must stay on call
      sp_a28aff68ec  was never a fact about one row.
      sp_6075dc41f2  It's a fact about the relationship between rows, and each transaction only ever read that relationship, never locked it.
      sp_52f3f3ceb8  That gap, reading a condition and writing based on it while the condition itself goes unprotected, is write skew.

 5. s05  guide      target 52s  duration=null  elastic  obj=o7  load=high
      new terms: serializable isolation, select for update
      sp_e2fb27decd  Take the options one at a time, using the doctors.
      sp_6569746940  A table lock works: lock the whole table before either transaction reads it, and the second one waits.
      sp_45c77acb4b  That kills the anomaly, but it also blocks every doctor updating any unrelated row
      sp_98cdf3d3bf  you've traded a bug for a bottleneck.
      sp_e5241cf44d  SELECT FOR UPDATE looks better: lock the rows you read.
      sp_fb5e4ab259  But neither doctor's query updates the row it reads
      sp_d3de4b56b2  each reads the whole list and writes only its own row.
      sp_b66b284d03  Locking a read that never touches the write target is easy to get wrong.
      sp_46ad1d4dd0  A constraint could work if the rule lived in one row, but 'at least one doctor on call' is a fact about the whole table, and a plain CHECK can't see across rows.
      sp_45347d358b  That leaves SERIALIZABLE: it does the work of noticing the conflict for you, without you having to track which rows matter.
      [WARNING] speaking_rate: 147 words need 55.1s at 160 wpm but the guide slot budgets 52s (7% over; 138 words fit).

 6. s06  elicit     target 17s  duration=null  elastic  obj=o7  load=medium
      sp_b50d301a19  Look at the doctors one more time.
      sp_a930117a98  If you could make only one change to stop this for good, which would it be: turn on SERIALIZABLE, add SELECT FOR UPDATE to the read, lock the whole table, or write a constraint?
      sp_67b27540b1  Pick one, and be ready to say what it costs you.
      [WARNING] speaking_rate: 52 words need 19.5s at 160 wpm but the elicit slot budgets 17s (16% over; 45 words fit).

 7. s07  feedback   target 19s  duration=null  elastic  obj=o7  load=medium
      sp_bc85099a61  SERIALIZABLE is the fix.
      sp_93758ba6db  Postgres tracks what each transaction reads, not just writes, and aborts one with a serialization error when the two could only make sense running one after another.
      sp_3274235d57  The cost: your app must retry that transaction.
      sp_5941201954  A table lock also stops it, but it blocks every doctor's update, not just the two in conflict.
      [WARNING] speaking_rate: 57 words need 21.4s at 160 wpm but the feedback slot budgets 19s (14% over; 50 words fit).

 8. s08  assess     target 10s  duration=null  elastic  obj=o7  load=medium
      sp_b9eca96a44  New case: two withdrawals check a shared balance rule, then hit different accounts.
      sp_c6ed8a4b5f  Which fix do you recommend, and what's the cost of choosing it?

 9. s09  retain     target 6s  duration=null  elastic  obj=o7  load=low
      sp_8f3f52a97d  Before you move on, say aloud how you'd spot write skew and pick its fix.

9 scenes, 46 spans, 5 findings
```
