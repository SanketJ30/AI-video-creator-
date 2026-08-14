"""Escalation: the one way this system is allowed to fail (invariant 7, §7.1).

    "`escalated` is a first-class state, not a failure. Every failure path ends
     in a recorded state with the error, the offending input, and a
     human-actionable next step."

Raising `Escalated` without recording it defeats the point, so `raise_escalated`
does both in one call. If there is no database connection to hand (a unit test,
a dry run), the exception still carries everything a human needs — it just is
not queryable later, and `recorded` says so.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import db


@dataclass(eq=False)   # keep Exception identity semantics and hashability
class Escalated(RuntimeError):
    """A failure a human has to look at. Never caught and swallowed."""

    message: str
    stage: str
    error_class: str
    offending_input: dict = field(default_factory=dict)
    next_step: str = "inspect the offending input and re-run"
    recorded: bool = False

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message

    def render(self) -> str:
        lines = [f"ESCALATED  {self.stage}  [{self.error_class}]",
                 f"  {self.message}",
                 f"  next step: {self.next_step}"]
        if self.offending_input:
            blob = json.dumps(self.offending_input, indent=2, sort_keys=True)
            lines.append("  offending input:")
            lines += [f"    {ln}" for ln in blob.splitlines()[:40]]
        if not self.recorded:
            lines.append("  (not recorded — no database connection was available)")
        return "\n".join(lines)


def record(conn, *, stage: str, error_class: str, error: str,
           course_id: str | None = None, offending_input: dict | None = None,
           next_step: str) -> str:
    row = db.one(conn, """
        insert into escalations(course_id, stage, error_class, error,
                                offending_input, next_step)
        values (%s, %s, %s, %s, %s, %s) returning id
    """, (course_id, stage, error_class, error,
          json.dumps(offending_input or {}), next_step))
    return str(row["id"])


def raise_escalated(conn, *, stage: str, error_class: str, message: str,
                    next_step: str, course_id: str | None = None,
                    offending_input: dict | None = None) -> Escalated:
    """Record the escalation on its OWN connection, then raise. Always raises.

    The separate connection is the whole point. The caller is almost always
    inside a transaction that is about to roll back — that is what an escalation
    means — and writing the row on `conn` would roll it back too. The failure
    would then be invisible in `escalations`, which is precisely the 2am silent
    death invariant 7 exists to prevent. `conn` is still taken, as the signal
    that a database is configured at all.
    """
    recorded = False
    if conn is not None:
        try:
            with db.tx() as own:
                record(own, stage=stage, error_class=error_class, error=message,
                       course_id=course_id, offending_input=offending_input,
                       next_step=next_step)
            recorded = True
        except Exception:
            # Losing the escalation row must not lose the escalation. The
            # exception below still carries the error, the input and the fix.
            recorded = False
    raise Escalated(message=message, stage=stage, error_class=error_class,
                    offending_input=offending_input or {}, next_step=next_step,
                    recorded=recorded)


def open_escalations(conn, course_id: str | None = None) -> list[dict]:
    sql = """select id, course_id, stage, error_class, error, next_step, created_at
               from escalations where not resolved"""
    params: list = []
    if course_id:
        sql += " and course_id = %s"
        params.append(course_id)
    return db.query(conn, sql + " order by created_at desc", params)
