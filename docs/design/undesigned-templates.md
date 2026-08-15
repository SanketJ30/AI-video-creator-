# The five undesigned templates — Sanket's call

**Status: gated out of planner selection.** Not deleted, not redesigned by me.
Each is re-enabled by filling in one field (`Template.design_section`) once a
layout exists. This document is the decision input.

---

## Why this needed a decision at all

`docs/design/video-design-system.md` §9 designs **six** templates. The registry
holds **eleven**. The other five render legibly — correct tokens, correct type
scale, inside the §4 content region — but their composition was improvised by
me, not designed.

**Measured, and this is the part that made it urgent:**

- The visual planner was shown **all eleven** and could select any of them.
- `labelled_diagram` **was selected on this course**, two storyboard runs ago.
- The current storyboard happens to use only the designed six.

So nothing undesigned is shipping *today*, but it was one re-plan away — an
improvised layout in a video whose composition nobody reviewed. That is not a
scope note; it is a live risk that happened to be off this run.

**Gated** rather than left open, because the gate is reversible in one field and
the risk is not: a video that ships with an improvised layout is reviewed as if
it were designed.

---

## The five, and what each is for

### 1. `labelled_diagram` — the one the course actually reaches for

**Purpose:** nodes and edges that build up, with one focus target. The default
for structure, flow and relationships (§4.4).

**Params:** `title`, `nodes` (≤7, `{id, label}`), `edges` (≤10), `focus`.

**Why it matters most:** this is the template the MVCC course chose when it was
available, and the one a diagram-heavy technical course will keep reaching for.
§9.6's `concept_illustration` now covers a *vertical flow*, but not a graph with
edges and a focus target.

**Overlap to consider:** `concept_illustration` (§9.6) may already cover enough
of this that `labelled_diagram` is redundant. The distinction is edges — a flow
is a chain, a diagram is a graph.

---

### 2. `terminal_replay` — code and command output

**Purpose:** an ordered sequence of terminal steps with a caption. §17 of the
design system *does* cover the treatment (mono, ≥26px, quiet blocks, highlight
only the relevant line, signal colour for the current line) — but §9 gives it no
**layout**.

**Params:** `steps` (≤8, `{label, detail}`), `caption`.

**Why it matters:** any course teaching a CLI, SQL or a language needs this, and
§17 already specifies most of its behaviour. **This is the cheapest of the five
to design** — arguably §17 plus a frame is already the design.

---

### 3. `ui_walkthrough` — screen demonstration

**Purpose:** numbered steps over a screenshot or synthetic UI.

**Params:** `surface` (asset ref), `steps` (≤8).

**Why it matters:** it is the only `SCREEN_DEMO` kind in the registry, and §16.2
gives it a specific accessibility obligation (1.2.1 — a silent screen capture
needs a descriptive transcript).

**Blocked on something else:** its primary content is `surface`, an **asset**.
Like `cold_open` before §0's decision, it cannot render its actual subject
without the asset pipeline. Designing a layout for it before that exists would
design a frame around a hole.

---

### 4. `series_build` — data visualisation

**Purpose:** a chart built series by series.

**Params:** `title`, `chart` (enum), `series`, `highlight`.

**Why it matters:** §15 of the design system is *entirely* about chart
behaviour — "show axes, reveal the data, animate the trend, signal the point,
show the explanation" — and §2 notes the source presentation "uses charts
extensively". So the **motion** is specified and the **layout** is not.

**Honest note:** the current renderer draws this as a list of labels, not a
chart. It has no axes, no plotting, no geometry. Calling it a data-viz template
today is generous; designing it means building a chart renderer, which is the
largest of the five by a distance.

---

### 5. `term_card` — vocabulary

**Purpose:** one term and its defining characteristic. §9.2's pre-training rule
wants a vocabulary scene before a scene introducing ≥3 new terms, and this is
the template that would serve it.

**Params:** `term`, `characteristic`, `icon`.

**Overlap to consider:** `key_phrase` (§9.3) and `title_card` (§9.2) between
them may already cover this. A term card is close to a title card with different
semantics. **This is the strongest retire candidate** — and retiring it means
§9.2's pre-training rule has no dedicated template, which is a pedagogy decision
rather than a visual one.

---

## The decision, per template

|  | template | recommend | why |
|---|---|---|---|
| 1 | `labelled_diagram` | **design** | the course reaches for it; edges and focus are not covered by §9.6 |
| 2 | `terminal_replay` | **design** | §17 already specifies the treatment; cheapest of the five |
| 3 | `ui_walkthrough` | **defer** | blocked on the asset pipeline; designing around a hole |
| 4 | `series_build` | **defer or scope** | §15 specifies the motion, but there is no chart renderer to move |
| 5 | `term_card` | **retire?** | probably covered by `key_phrase`/`title_card`; retiring is a pedagogy call about §9.2 |

**These are recommendations, not decisions.** I have not designed any of them and
have not retired any of them. Every one stays in the registry with its schema,
validation and renderer intact.

## To re-enable one

Set its `design_section` in `templates.py` to the section that specifies it:

```python
Template(name="terminal_replay", version="1.1.0", design_section="§9.7", ...)
```

`selectable()` picks it up immediately, the planner is offered it, and
`test_every_selectable_template_names_its_design_section` starts holding it to
the same standard as the other six.
