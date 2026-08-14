"""Agents: the stages that call a model.

An agent is not a stage handler (`stages/base.py`) — handlers are the DAG's
unit of caching and must be byte-deterministic. Agents are the layer underneath:
they own the model call, the typed-output contract, the repair loop and the
escalation path. A handler wraps an agent; an agent never touches the DAG.

Rules that apply to everything in this package:

  * the prompt is a file in `prompts/`, loaded through `explainer.prompts`
    (invariant 6). No prompt text in Python, including repair prompts.
  * the model id comes from `settings().models`, pinned. Never "latest".
  * every object an agent produces carries provenance (R6): which agent, which
    prompt version, which model version, when.
  * every failure path ends in a recorded escalation, never a silent None
    (invariant 7).
"""
