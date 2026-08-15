# The Fact Challenger — first run and positive control

§7.2 Tier 2, built adversarially: the agent is prompted to **refute** each
claim, not to verify it. ISSUE-8 is why.

Findings attach to **spans**, not scenes. A verdict on a scene tells a reviewer
to re-read ninety seconds; a verdict on `sp_b735cd9656` tells them which
sentence.

---

## 1. The positive control — it caught the known false claim

A checker that has never been shown a known-false claim has been *run*, not
*tested*. The control is the pre-fix v2 s04 narration, recovered from git
(`fd7f250`) and frozen at `tests/gold/issue8_positive_control.json` — 17 spans,
containing the claim you identified.

**Result: caught, at the top severity.**

```
BLOCKING (1)
  [sp_b735cd9656]  refuted   confidence 0.90

  claim:  Neither transaction writes a row that the other transaction reads.

  attack: The check "is anyone else on call besides me?" scans the on-call set,
          so A's query reads B's row and B's query reads A's row. A then writes
          A's row (which B read) and B writes B's row (which A read). So each
          transaction writes a row the other one read — that read-write
          antidependency in both directions is precisely what makes this write
          skew rather than a benign pair of updates. The true statement is
          about writes, not reads: there is no write-write overlap.

  should say: "Neither transaction writes the row the other one writes — but
          each writes a row the other one read, and that read-write dependency
          is invisible to Repeatable Read."

  contradicts: sp_52f3f3ceb8
```

That is the diagnosis, the mechanism and the correction, unprompted.

It also found the contradiction **from both directions**: challenging
`sp_52f3f3ceb8` independently, it wrote *"this definition is undermined by
sp_b735cd9656 … sp_b735cd9656 is the false one."*

### Two further errors in the control that nobody had noticed

| span | verdict | finding |
|---|---|---|
| `sp_ade42574d7` | refuted (0.65) | *"a frozen view … the moment the transaction began"* — in Repeatable Read the snapshot is taken at the **first statement**, not at `BEGIN` |
| `sp_c0aefbdd27` | unsupported (0.60) | *"Postgres has nothing to catch"* overstates: the limitation is Repeatable Read's, not PostgreSQL's — SERIALIZABLE catches exactly this |

**Control totals:** 11 claims extracted from 17 spans, 2 refuted, 1 blocking,
$0.1496.

The 6 spans that produced no claim were questions, framing and scenario
stipulations — correctly skipped.

---

## 2. The current v2 — not clean

25 claims across 9 scenes. **3 refuted, 1 blocking.**

### BLOCKING — s05 `sp_e94ffb9700`, confidence 0.78

> **claim:** With `SELECT ... FOR UPDATE` on the two on-call rows, Bo waits for
> Alex, then sees Alex's committed result and therefore does not also go off
> call.
>
> **attack:** Under REPEATABLE READ, a blocked `FOR UPDATE` waiting on a row
> Alex then commits does **not** re-read the new version: PostgreSQL aborts the
> waiter with ERROR 40001, *"could not serialize access due to concurrent
> update"*. Re-reading the newly committed row after the lock is released is
> READ COMMITTED behaviour. So *"Bo waits, sees her result"* is the wrong
> mechanism for the stated isolation level, and the outcome for Bo is an error,
> not a corrected read.

A real error, and a subtle one: the narration describes Read Committed semantics
inside a video whose entire subject is Repeatable Read.

### The other two refutations

- **s05 `sp_b94dd033f2`** (0.68) — *"a constraint checks one row at a time"* is
  false as a general statement: `UNIQUE`, `EXCLUDE` and `FOREIGN KEY` are all
  cross-row. Only `CHECK` is row-local. The conclusion holds for the wrong
  reason, which would mislead a learner who then assumes `UNIQUE` cannot catch a
  cross-row conflict.
- **s07 `sp_4182784a44`** (0.60) — *"a table lock stalls every other
  transaction"* is only true of `ACCESS EXCLUSIVE`; other lock modes leave
  ordinary readers running.

Four further spans came back `unsupported` — missing preconditions rather than
falsehoods (s03, s05, s06, s07).

---

## 3. What this establishes, and what it does not

**Establishes:** the checker detects the specimen it was built for, at high
confidence, with a correct mechanism and a usable correction. It also found four
errors nobody had gone looking for, in narration that had already passed every
deterministic gate and two human readings.

**Does not establish that it catches everything.** Two named limits:

1. **No negative control yet.** Nothing here measures the false-positive rate. A
   narration known to be fully correct, challenged and coming back clean, is the
   missing half — and without it a confident-sounding `refuted` on a true claim
   would look identical to a real find.
2. **No sources.** §7.2 says *"independently verified with sources"*; this
   version verifies against model knowledge. A `survives` means *an adversarial
   reading did not break it*, not *a source confirms it*. Both limits print
   under every report rather than living only in this document.

**One authored number:** `AUTHORED_MIN_CONFIDENCE = 0.70`, marked. It gates the
agent's confidence in its **own verdict**, not the truth of the claim. Below it
a refutation is demoted to a warning and **never discarded**, because ISSUE-8's
lesson is that silence is the expensive failure.

**Cost:** $0.1496 (control) + $0.6019 (v2) = **$0.75**, one frontier-tier call
per scene. §21's per-video agent budget absorbs this, and this is the one agent
where the frontier tier is clearly worth paying for.

---

## 4. Consequence for the ID review

**The video currently has a blocking factual error in s05.** `docs/week6-plan.md`
listed *"is ISSUE-8 tolerable for a review?"* as an open decision; it is now
answerable against a specific span rather than a worry.

Fixing it is a Stage 2c regeneration, not a render change — and regeneration is
stochastic, so the honest sequence is: regenerate, re-challenge, and only then
put it in front of a reviewer.


---

## 5. Negative control — zero false positives, 51 verdicts

A checker that has only ever been shown a false claim has no measured
false-positive rate. `tests/gold/negative_control.json` holds **17 claims I
believe are true**, in two groups, run at **3 samples**.

**Result: 51/51 `survives`. No `refuted`, no `unsupported`. False-positive rate
0/51.**

Confidence ran 0.60–0.95, lowest on `cnt_03` (the first-statement snapshot
timing), which is the subtlest claim in the set — the ordering is what you would
want.

### The claims, so you can check them

**Group A — obviously true** (all `survives` ×3)

| id | claim |
|---|---|
| `obv_01` | An UPDATE writes a new row version rather than overwriting in place. |
| `obv_02` | Each row version records the creating transaction id in `xmin`. |
| `obv_03` | Under Repeatable Read, reading the same row twice returns the same data even if another transaction committed a change in between. |
| `obv_04` | VACUUM reclaims row versions no longer visible to any running transaction. |
| `obv_05` | A plain SELECT does not block a concurrent UPDATE of the same row, and vice versa. |
| `obv_06` | The default isolation level is Read Committed. |
| `obv_07` | Under Read Committed each statement sees a snapshot taken when that statement began, so two statements in one transaction can see different data. |
| `obv_08` | Row versions written by a transaction that rolls back are never visible to others. |

**Group B — true but counterintuitive**, where a false positive is most likely
(all `survives` ×3)

| id | claim |
|---|---|
| `cnt_01` | PostgreSQL's Repeatable Read is stronger than the standard requires: it also prevents phantom reads. |
| `cnt_02` | Under SERIALIZABLE, a transaction that ran only SELECTs can still be aborted with a serialization failure. |
| `cnt_03` | Under Repeatable Read the snapshot is taken at the first data-reading or -writing statement, not at BEGIN. |
| `cnt_04` | Under Repeatable Read, a `SELECT ... FOR UPDATE` waiting on a row another transaction updated and committed fails with a serialization error rather than returning the newer version. |
| `cnt_05` | Two transactions can each commit under Repeatable Read and together leave a rule violated that neither violated alone. |
| `cnt_06` | A rolled-back INSERT still consumes its sequence value, so identity columns can have gaps. |
| `cnt_07` | One long-running transaction can stop VACUUM removing dead rows in tables it never touched. |
| `cnt_08` | Under Read Committed, an UPDATE that blocks on a locked row re-evaluates its WHERE clause against the newly committed version once the lock is released. |
| `cnt_09` | `xmax` can be set on a row that was never deleted, because it also records a locking or updating transaction. |

**What 0/51 does and does not mean.** It is a genuine clean result on the
hardest cases I could author. It is not proof of a zero rate: with 51 trials and
zero events, the rule of three puts the 95% upper bound near **6%**. And these
are claims *I* wrote — a blind spot of mine is a blind spot of the control.

**Cost:** $0.6822.

---

## 6. Regeneration did NOT fix s05 — it made the narration worse

Per the agreed sequence: regenerate (Stage 2c), re-challenge at 3 samples, then
review. The re-challenge is why the sequence exists.

**Regenerated v2, 33 spans, 3 samples: only 16 of 33 spans survive all three.**
The previous narration had 1 blocking and 3 refuted out of 25 claims; this one
has **five spans refuted in a majority of samples**.

| span | verdicts | the claim, and why it is wrong |
|---|---|---|
| s03 `sp_2b87c24c98` | refuted ×3 (.68/.65/.75) | *"each transaction gets a snapshot taken at its start"* — **the exact error the challenger found in the ISSUE-8 control**, reintroduced verbatim in a different sentence |
| s05 `sp_0f3ed1403d` | refuted ×3 (.70/.65/.60) | *"a database constraint can keep the count of on-call doctors from dropping below one"* — no PostgreSQL constraint expresses a cross-row aggregate; CHECK is per-row and may not contain subqueries |
| s07 `sp_4dc2a0d2e8` | refuted ×2, unsupported ×1 | *"FOR UPDATE … the second transaction merely has to wait"* — **the same Read-Committed-vs-Repeatable-Read confusion as the s05 claim this regeneration was meant to fix** |
| s07 `sp_a2dfca023e` | refuted ×2, unsupported ×1 | SERIALIZABLE framing |
| s05 `sp_8d720ccd66` | refuted ×2, unsupported ×1 | — |

### What this establishes

**Regenerating a stochastic stage is not a fix for a factual error.** It is a
re-roll. This run removed the specific blocking claim and introduced a
`constraint can enforce a cross-row count` error that is arguably worse, plus a
restatement of the very Read-Committed confusion it was supposed to remove.

It also shows the errors are **not random**: the same two confusions —
snapshot-taken-at-BEGIN, and FOR-UPDATE-just-waits — recur across independent
generations. That is a property of the prompt and the topic, not bad luck, and
it means the fix belongs in Stage 2c's prompt (state the isolation-level
semantics the narration must respect) rather than in another regeneration.

**The video is not ready for an ID review**, and the blocker is now measured
rather than suspected. The previous narration is still in git; on the current
evidence it is the better of the two, which is itself worth knowing.

**Cost:** $0.4219 regeneration + $2.1101 re-challenge (3 × 33 spans) = $2.53.

### A note on what re-challenging costs

Three samples over nine scenes is 27 frontier-tier calls. At $0.70 per
three-sample video this is affordable for a gate run before review, and it is
**not** affordable as a per-save check in an editor. §21's budget absorbs the
former; the latter would need a cheaper tier or a diff-scoped run that
challenges only changed spans.
