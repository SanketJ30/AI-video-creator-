# Script snapshot — mvcc-write-skew / v2 (run 3)

    run id          week5 step 0, sample taken 15 Aug 2026
    brief version   v5
    objective graph 7 objectives (4 taught) — v3-run5
    script writer   script_writer@v3   (recall gate: termregistry)
    supersedes      run 2 (script_writer@v2), kept in git history
    body sha256     413bb6f4ff8e

Regenerated for week 5 step 0: the recall slot now links to v1's objectives by
ref and `new_terms` is computed against a per-course registry, so v2 no longer
re-declares anything v1 taught.

NOTE ON ISSUE-8: this run does not contain the false claim at the old
`sp_b735cd9656`. That is sample variance, not a fix — nothing detected it. See
ISSUE-8 in known-issues.md.

```
v2  [procedure_demo]  Spotting write skew and fixing it
budget 240s  objectives o6, o7

 1. s01  hook       target 15s  duration=null  elastic  obj=o6  load=medium
      sp_779baeb479  Two on-call doctors each check the schedule, see someone else covering, and clock off at the same moment.
      sp_b43d774254  Postgres commits both updates cleanly — no error, no warning.
      sp_d6d5c540b8  So why is nobody on call?

 2. s02  objective  target 10s  duration=null  elastic  obj=o6  load=low
      sp_c66a90b2ad  You'll spot write skew in a transaction pair that Postgres lets commit without complaint.

 3. s03  recall     target 20s  duration=null  elastic  obj=o6  load=low
      sp_e8129aae7a  You already learned to explain how xmin and xmax decide which row versions a Repeatable Read snapshot can see.
      sp_87fbfcf003  That rule is what keeps a transaction's own reads consistent, row by row, from start to finish.
      sp_826d91c40c  Now watch two transactions, each one perfectly consistent by that same rule, that together still break a rule neither one touched alone.
      [WARNING] speaking_rate: 58 words need 21.8s at 160 wpm but the recall slot budgets 20s (9% over; 53 words fit).

 4. s04  present    target 90s  duration=null  rigid  obj=o6  load=high
      new terms: write skew, could-not-serialize error
      sp_4fb3dafdf2  Picture two on-call doctors, Alex and Bo.
      sp_d1ee104181  The rule: at least one of them must always be reachable.
      sp_8c21188f75  Alex's transaction checks how many doctors are currently on call, sees two, and decides it's safe to go off duty herself.
      sp_6005e89512  At almost the same moment, Bo's transaction runs the identical check, also sees two, and decides it's safe for him to go off duty too.
      sp_d65ca15911  Both transactions took their snapshot before either write landed, so each one saw the old count of two.
      sp_637d7eca51  Repeatable Read keeps that snapshot consistent for the whole transaction
      sp_8286d8998e  but it makes no promise about a rule that spans two separate rows.
      sp_9f9f419a6b  Alex updates only her own row.
      sp_4ca5431376  Bo updates only his.
      sp_f465724901  Postgres never sees them touch the same row, so it has nothing to flag as a conflict.
      sp_03937d257c  Both commit cleanly.
      sp_4b7c31d8bd  Neither gets a could-not-serialize error — the error Postgres raises when it catches a conflict it can't resolve.
      sp_431e8c3403  Now nobody is on call.
      sp_c9de83fc9c  That's write skew: two transactions each read a shared condition, each act correctly given what they saw, and together they break a rule that neither one violated alone.
      sp_16c1f6e003  Compare that to a non-repeatable read or a phantom: Repeatable Read's snapshot rules those out directly.
      sp_70d544d18d  Compare it to a lost update on that row: Postgres catches the row-level conflict and blocks one transaction with a could-not-serialize error.
      sp_a9c2acdb5a  Write skew gets through because the conflict lives across rows, in the rule connecting them, not in any single row Postgres watches.
      [WARNING] speaking_rate: 245 words need 91.9s at 160 wpm but the present slot budgets 90s (2% over; 240 words fit).

 5. s05  guide      target 52s  duration=null  elastic  obj=o7  load=medium
      new terms: serializable isolation, select for update
      sp_65fead3d5b  Back to Alex and Bo, with four options on the table: turn on SERIALIZABLE isolation, run SELECT ...
      sp_79a14acee2  FOR UPDATE on the rows they read, take a table-level lock, or add a constraint.
      sp_adef07e47e  A constraint checks one row at a time, so it can't see a rule like 'at least one doctor on call'
      sp_7780b0c63b  that rule spans two rows.
      sp_dbcce2e77a  A table lock fixes it too, but now every transaction touching that table queues behind every other one, even ones that never conflict.
      sp_f1331aff61  SELECT ...
      sp_b6d901c2ef  FOR UPDATE on the two on-call rows works directly: Alex locks both before deciding, so Bo waits, sees her result, and doesn't also go off call.
      sp_0254986056  Its cost is you have to know which rows to lock ahead of time.
      sp_2af9c66155  SERIALIZABLE is the general answer: Postgres tracks the dependency between the two transactions and stops one at commit with a could-not-serialize error.
      sp_45ccefa320  Its cost: your application has to retry that transaction from the start.
      [WARNING] speaking_rate: 156 words need 58.5s at 160 wpm but the guide slot budgets 52s (13% over; 138 words fit).

 6. s06  elicit     target 17s  duration=null  elastic  obj=o7  load=medium
      sp_dacf3b5d61  Now picture a shared account with a $500 overdraft limit, checked and debited by two concurrent withdrawals, each pulling from a different sub-account.
      sp_d6a3bd2aa5  Which of the four remedies would you reach for here, and what would it cost you?
      sp_e92b36706a  Decide before you keep watching.

 7. s07  feedback   target 19s  duration=null  elastic  obj=o7  load=medium
      sp_ec6a9c8fca  SELECT ...
      sp_c5049f410a  FOR UPDATE on that balance row is the cheap fix here
      sp_4aa054b057  you know exactly which row backs the limit.
      sp_9c5acedebc  A table lock also works, but it stalls every other transaction on the table, not just these two.
      sp_96473a52e5  Reach for SERIALIZABLE only when you can't pin the rows down in advance, and then you retry on that could-not-serialize error.
      [WARNING] speaking_rate: 59 words need 22.1s at 160 wpm but the feedback slot budgets 19s (18% over; 50 words fit).

 8. s08  assess     target 10s  duration=null  elastic  obj=o7  load=medium
      sp_0b934e23b8  Two transactions each check total warehouse stock, then each ship the last unit from a different bin.
      sp_64489a6b66  Which remedy do you recommend, and what's the cost?
      sp_b900135162  Work it out now.
      [WARNING] speaking_rate: 30 words need 11.2s at 160 wpm but the assess slot budgets 10s (15% over; 26 words fit).

 9. s09  retain     target 6s  duration=null  elastic  obj=o7  load=low
      sp_b44913f049  Sum up in your own words: why does write skew slip past Repeatable Read, and which fix would you defend?
      [WARNING] speaking_rate: 20 words need 6.5s at 185 wpm but the retain slot budgets 6s (11% over; 18 words fit).

9 scenes, 46 spans, 6 findings

```
