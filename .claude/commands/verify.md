---
description: Run the invalidation-model regression gate and explain any failure
---

Run `make verify`, then `make test`.

If anything fails, do not fix it by relaxing the check. Diagnose which of the
seven invariants in CLAUDE.md was broken and report:

- which check failed and what it asserts about the system
- the actual vs expected node sets or hashes
- which invariant the failure implies was violated
- the smallest fix that restores the invariant

A `StoreError` about differing bytes for one hash always means a handler read an
input its `StageSpec` does not declare. Never delete the blob to clear it.
