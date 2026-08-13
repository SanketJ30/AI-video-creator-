---
description: Implement one pipeline stage handler end to end
---

Implement the handler for stage `$ARGUMENTS` in the production graph.

Work in this order and do not skip steps:

1. Read the stage's `StageSpec` in `src/explainer/graphs/production.py` and the
   PRD section named in its `description=`. Quote back the spec (scope, pool,
   tier, deps, config_keys, video_input_keys) and say whether it is right. If it
   is wrong, fix the spec first and explain what would have broken.
2. Read `src/explainer/stages/base.py` — specifically THE ONE RULE about only
   reading declared inputs.
3. If the spec has `prompt=`, write or review `prompts/<name>.v1.md`.
4. Write the handler in `src/explainer/stages/production_handlers.py`. Pin the
   model from `ctx.model_version`. Schema-validate the output and raise
   `StageFailure(msg, "llm_schema")` on invalid output so the retry policy
   re-prompts with the validation error.
5. Set `implemented=True`.
6. Run `make verify && make test`. Both must pass.
7. Run the stage on one real video and show me the actual output — not a summary
   of it.

Do not add caching, retries, or job-state handling inside the handler. The
orchestrator and worker own all of that.
