# Course Video Renderer — Light Theme Visual & Motion System

**Status:** Design specification for Milestone A / renderer testing  
**Target:** Course-based educational videos  
**Canvas:** 1920 × 1080, 16:9  
**Theme:** Light only  
**Primary source of truth:** `Final config.json`  
**Visual reference:** `Light theme.pptx`  
**External stock/video assets:** Deferred until Storyblocks/asset pipeline is available

---

## 0. Executive decision

For the current renderer test, the video system should be **100% light-theme, typography/diagram/UI-visual driven, and based on the existing design-system tokens**.

Do **not** introduce a new color palette, dark theme, gradients, decorative illustration language, or stock footage dependency.

The six renderer templates should behave like a **motion version of the existing course presentation system**, not like six unrelated motion-graphics templates.

### `concept_illustration` decision

For Milestone A:

> **`concept_illustration` does not require external imagery.**

It should work as a **typographic + diagrammatic composition** using:

- cards
- lines
- connectors
- numbered markers
- simple shapes
- data visualizations
- UI-like elements
- existing icons where available
- emphasis/highlight states

The `asset` slot should remain architecturally optional so Storyblocks/Freepik/generated media can be introduced later without redesigning the template.

This is the safest test because it lets us validate the actual renderer, layout system, information hierarchy, and motion language before adding asset retrieval/licensing complexity.

---

# 1. What this system is trying to achieve

This renderer is for **course videos**, not marketing videos.

The learner should feel:

- "I understand what the instructor is explaining."
- "I know where I should look."
- "I can see the concept being built."
- "I can distinguish an example from the answer."
- "I can follow a process without losing my place."
- "The visuals are helping me learn, not competing with the narration."

The visual system therefore prioritizes:

1. **Hierarchy**
2. **Signaling**
3. **Progressive disclosure**
4. **Spatial consistency**
5. **Narration-to-visual synchronization**
6. **Low visual noise**
7. **Repeatable layouts**
8. **Fast comprehension**

It should not prioritize:

- constant movement
- cinematic transitions for their own sake
- decorative animation
- random camera movement
- excessive zooming
- gradients everywhere
- stock imagery as a requirement
- making every frame look "busy"

Research on multimedia learning strongly supports this direction: signaling helps guide attention, segmenting helps manage essential processing, spatial/temporal contiguity helps learners connect related visual and verbal information, and removing extraneous material reduces unnecessary cognitive load.

---

# 2. Source-of-truth hierarchy

There are three inputs to this specification.

## Tier 1 — Design system

`Final config.json`

This is the **token authority**.

The renderer should not invent replacement values when an appropriate token already exists.

Important existing values include:

- Primary: `#148AFF`
- Success: `#05C170`
- Warning: `#FCA106`
- Error: `#D13845`
- Base/background: `#FFFFFF`
- Primary background: `#F5FAFF`
- Primary border: `#99CCFF`
- Primary active: `#0073E5`
- Text: `#262626`
- Secondary text: `#595959`
- Tertiary text: `#8C8C8C`
- Border: `#D9D9D9`
- Secondary border: `#F5F5F5`
- Layout background: `#FAFAFA`
- Base spacing: `16`
- Small spacing: `12`
- Large spacing: `24`
- Radius: `10`
- Small radius: `8`
- Strong font weight: `600`
- Existing box shadows: low-elevation shadows

These values are directly represented in the supplied configuration.

## Tier 2 — Course presentation language

`Light theme.pptx`

The presentation establishes the intended educational visual language:

- white/light canvas
- strong dark-blue/navy-looking heading treatment
- blue as the primary visual signal
- restrained borders
- generous whitespace
- numbered structures
- cards
- charts
- tables
- explanatory callouts
- "THE LESSON" / "BIGGEST GAINS" / similar editorial labels
- step-by-step educational storytelling
- diagrams and data rather than decorative imagery

Representative examples include:

- Introduction to Machine Learning: title + description + six concept cards
- Reading a Learning Curve: chart + explanatory lesson callout
- What the Cohort Data Says: chart + three explanatory insights
- Your Skill Profile: chart + biggest-gains panel
- Worked Example: Bias & Variance
- From Raw Data to Live Demo: four sequential steps
- Deriving the Update Rule: four numbered steps

The presentation repeatedly uses the same information architecture rather than inventing a new composition for every slide.

## Tier 3 — Motion research

External research should influence **how the existing design behaves**, not override the brand/design system.

---

# 3. Semantic token layer for video

The renderer needs semantic roles even though the source JSON is currently expressed largely as component/global tokens.

Do not create new colors.

Map the existing tokens as follows.

| Video role | Source token | Value | Use |
|---|---|---:|---|
| `surface` | `colorBgBase` / `colorBgContainer` | `#FFFFFF` | Default video background |
| `surface-subtle` | `colorBgLayout` | `#FAFAFA` | Secondary canvas / quiet region |
| `surface-signal` | `colorPrimaryBg` | `#F5FAFF` | Highlighted area |
| `surface-signal-hover` | `colorPrimaryBgHover` | `#E6F3FF` | Stronger highlight state |
| `ink` | `colorText` | `#262626` | Primary readable text |
| `ink-strong` | `colorTextBase` / notification heading where needed | `#000000` / `#141414` | Rare maximum-emphasis text |
| `ink-muted` | `colorTextSecondary` | `#595959` | Supporting copy |
| `ink-subtle` | `colorTextTertiary` | `#8C8C8C` | Captions / metadata |
| `ink-disabled` | `colorTextDisabled` | `#BFBFBF` | Non-active reference information |
| `structure` | `colorBorder` | `#D9D9D9` | Main rules / card borders |
| `structure-subtle` | `colorBorderSecondary` | `#F5F5F5` | Chart grids / quiet dividers |
| `signal` | `colorPrimary` | `#148AFF` | "Look here" / active emphasis |
| `signal-strong` | `colorPrimaryActive` | `#0073E5` | Strong active emphasis |
| `signal-soft` | `colorPrimaryBg` | `#F5FAFF` | Background behind signal |
| `signal-border` | `colorPrimaryBorder` | `#99CCFF` | Signal containers |
| `answer` | `colorSuccess` | `#05C170` | Confirmed/correct/resolution state |
| `answer-soft` | `colorSuccessBg` | `#F7FDFA` | Answer/resolution container |
| `warning` | `colorWarning` | `#FCA106` | Caution / attention |
| `warning-soft` | `colorWarningBg` | `#FFFDF5` | Warning container |
| `error` | `colorError` | `#D13845` | Wrong/broken/failure state |
| `error-soft` | `colorErrorBg` | `#FFF5F5` | Error container |

### Video is not a screen UI: the soft container tiers need one rung more

**Added after measuring the finished MP4 — a general lesson, not a one-off fix.**

Soft container tokens tuned for a screen at reading distance **do not survive
H.264 at phone size.** WCAG ratio against `surface`:

| token | value | vs surface |
|---|---:|---:|
| `signal-soft` | `#F5FAFF` | 1.050:1 |
| `answer-soft` | `#F7FDFA` | 1.030:1 |
| `warning-soft` | `#FFFDF5` | 1.018:1 |
| `error-soft` | `#FFF5F5` | 1.070:1 |
| `surface-signal-hover` | `#E6F3FF` | **1.127:1** |

A screen UI reads these on a calibrated monitor at reading distance, next to
other white cards that give the fill an edge to sit against. A video is watched
at phone size *after* compression, and H.264's 4:2:0 chroma subsampling and
quantisation both operate at a scale larger than a 1.02:1 step. Measured on the
finished video: an `answer-soft` fill covering **69% of the frame** was
indistinguishable from white. The only part of the state treatment a viewer
could actually see was a 12 px rule in the saturated role colour.

**The rule this gives:** where a screen UI uses the `Bg` tier for an emphasised
surface, video uses the **`Bg-Hover` tier**. This is not a new colour — §3's
"do not create new colors" holds — it is one rung up a ramp the design system
already defines.

**Applied to `signal`, and BLOCKED for the other three.** §3's table above gives
a Bg-Hover tier for the signal role only. It does not list `colorSuccessBgHover`,
`colorWarningBgHover` or `colorErrorBgHover`, and interpolating them would be
creating three colours. Those three carry the scene state (`broken`, `caution`,
`resolved`), so they matter *more* than signal does. Four values from the source
system unblock it; a border tier for the three roles would be better still, since
signal's `colorPrimaryBorder` #99CCFF measures 1.689:1.

**The general form, worth applying beyond colour:** any token chosen for
legibility on a screen has been tuned against a viewing distance, a display and
no compression. Video changes all three. Type size already got this treatment —
§6's 24 px floor exists for the same reason — and contrast is the second place it
bites.

### Important distinction

Do not use blue for everything.

Blue means:

> **"Look here / this is currently being discussed."**

Green means:

> **"This is the correct, resolved, successful, or confirmed state."**

Red means:

> **"This is wrong, broken, or a failure."**

Orange means:

> **"Be careful / this deserves attention."**

This directly fixes the problem where "attention" and "answer" become visually identical.

---

# 4. Light-theme canvas rules

## Default frame

- 1920 × 1080
- Background: `#FFFFFF`
- No decorative background pattern
- No gradient background
- No dark section unless a future theme explicitly introduces one
- No unnecessary shadow on the canvas itself

## Safe content region

Use a consistent content grid.

### Recommended frame margins

- Left: 96 px
- Right: 96 px
- Top: 72 px
- Bottom: 64 px

This produces a usable content area of approximately:

**1728 × 944 px**

The exact implementation may adjust this slightly to accommodate the renderer, but the visual principle is fixed:

> The learner should recognize the same content boundary across templates.

## Grid

Use a **12-column conceptual grid**.

Recommended:

- 12 columns
- 24 px gutter
- 96 px outer margin

The grid should be used for alignment, not visibly rendered.

### Why

The current issue is not simply "too much whitespace."

The deeper issue is that the layouts are not making consistent decisions about where information belongs.

A grid gives the renderer repeatable spatial anchors.

---

# 5. Spacing system

The source design system uses:

- 12 px
- 16 px
- 24 px

as explicit spacing values.

For video composition, extend these into a **derived scale** rather than inventing arbitrary values:

`12 → 16 → 24 → 32 → 48 → 64 → 96 → 128`

These are not new brand tokens. They are layout multiples derived from the existing system.

## Usage

- 12: tiny internal spacing
- 16: standard component gap
- 24: related content separation
- 32: section/component gap
- 48: major group separation
- 64: title-to-content separation
- 96: major frame inset
- 128: large visual breathing room

Avoid random values such as 37, 53, 71, etc. unless the content genuinely requires them.

---

# 6. Typography system

The source config exposes the font family as:

`var(--font-sans)`

Therefore the renderer must use the same configured sans-serif family.

Do not hardcode a different font inside a template.

The supplied presentation also establishes a strong typographic hierarchy: large, dark headings; quieter descriptive text; compact uppercase labels; and strong numeric emphasis.

## Recommended 1920×1080 video scale

The existing renderer has a 24 px minimum. Keep that constraint.

| Role | Size | Weight | Typical use |
|---|---:|---:|---|
| Display | 72–88 px | 600 | Cold open / major title |
| H1 | 56–64 px | 600 | Template title |
| H2 | 40–48 px | 600 | Major section / card title |
| H3 | 32–36 px | 600 | Item title |
| Body | 28–32 px | 400 | Narration-supporting copy |
| Body strong | 28–32 px | 600 | Important phrase |
| Caption | 24–26 px | 400–500 | Metadata / supporting text |
| Label | 24 px | 600 | `THE LESSON`, `STEP 1`, etc. |
| Numeric display | 64–88 px | 600 | Metrics / answers |
| Mono | 26–30 px | 400–600 | Code / formulas / technical values |

### Rule

**Never solve a layout problem by shrinking type below 24 px.**

If content does not fit:

1. reduce copy
2. restructure
3. split into another scene
4. change layout

Do not cram.

---

# 7. Typography behavior for course videos

The video should not reproduce a full PowerPoint slide verbatim.

The presentation can contain more information because the learner can scan and pause.

A video has narration competing for attention.

Therefore:

### Presentation

Can show:

> title + subtitle + chart + three explanations

### Video

Should usually reveal:

> title → chart → one explanation → next explanation → conclusion

This is a critical difference.

The renderer should transform static information architecture into **temporal information architecture**.

---

# 8. Visual hierarchy

Every frame should have exactly one dominant visual question.

Examples:

### Bad

Everything is blue, bold, animated and moving.

### Good

The learner can answer:

> "What am I supposed to look at right now?"

The hierarchy should generally be:

**1. Current concept**

**2. Current evidence/example**

**3. Supporting context**

**4. Metadata**

The renderer should not give equal visual weight to all four.

---

# 9. Six-template system

---

# 9.1 `cold_open`

## Purpose

Start a course video with a strong learning hook.

This is not a marketing hero.

It should establish the **problem/question/paradox** that the lesson will resolve.

Examples:

> Why does more data eventually stop helping?

> Why can a model be 99% accurate and still be useless?

> What actually happens during gradient descent?

## Layout

Use a strong left-aligned composition.

### Frame

- Content starts around x = 120–160
- Main text occupies approximately 8–9 columns
- Vertical center around 42–48%
- Optional small lesson/module label above
- Main statement is the dominant object

Do not center the sentence vertically by default.

The current centered approach creates dead space beneath the content.

## Recommended structure

```text
MODULE 03 · MODEL EVALUATION

Why can a model be
99% accurate
and still fail?

[small supporting line]
The answer is hidden in the mistakes.
```

### Hierarchy

- module label: 24 px / signal
- question: 72–88 px / ink
- one emphasized phrase: signal or answer depending on meaning
- supporting line: 28 px / ink-muted

## Motion

Sequence:

1. Module label appears first.
2. Main question enters as one unit.
3. Key phrase receives a subtle signal treatment.
4. Supporting line appears only after the question is readable.

Do not animate each word independently.

### Timing

Typical cold open:

- label: 300–400 ms
- headline: 500–700 ms
- emphasis: 250–400 ms
- supporting line: 300–500 ms

Total entrance should normally stay around 1.2–2.0 seconds.

---

# 9.2 `title_card`

## Purpose

Introduce a new concept, module, lesson, or section.

The presentation already uses strong title + description structures, e.g. "Introduction to Machine Learning" followed by a short explanation and concept list.

The video version should preserve that hierarchy while revealing it over time.

## Layout

### Top-left anchored

- title starts at x ≈ 96–120
- y ≈ 72–100
- title width: 10–11 columns
- subtitle directly below
- optional lesson/module label above title

Do not vertically center title cards.

## Structure

```text
LESSON 04 · MODEL EVALUATION

Reading a Learning Curve

How to tell when a model has stopped
learning and started memorizing.
```

Optional:

```text
01  Training loss
02  Validation loss
03  Early stopping
```

These secondary items should appear only when useful.

## Motion

1. Lesson label
2. Title
3. Subtitle
4. Optional supporting concepts

Motion should feel like **orientation**, not spectacle.

---

# 9.3 `key_phrase`

## Purpose

Make one important statement memorable.

This is the most important template for narration-led teaching.

Use it when the instructor says something equivalent to:

> "The model has not learned the pattern. It has memorized the training data."

## Layout

Use a large left-aligned text block.

Recommended width:

- 10 columns maximum
- approximately 1300–1500 px max line width

Use 2–4 lines maximum for the primary phrase.

### Example

```text
More data is not
always the best
next dollar.
```

Then:

```text
More data
```

can be signaled if that is the current topic.

## Do not

- animate every word
- put the sentence in a giant centered box
- add unrelated illustration
- add a decorative background

## Motion

Use **phrase reveal**, not word karaoke.

Recommended behavior:

1. sentence appears
2. important clause is emphasized
3. final phrase resolves

Example:

```text
A model can perform well
on training data...

↓
but still fail in production.
```

The second clause becomes the resolution.

---

# 9.4 `state_timeline`

## Purpose

Explain:

- process
- progression
- before/after
- parallel states
- cause/effect
- stages
- workflows
- algorithm steps

The supplied presentation already uses strong step-based structures, including "From Raw Data to Live Demo" and "Deriving the Update Rule."

## Core layout

Use a **horizontal progression** for 3–5 states.

For parallel processes, use **two horizontal lanes**.

### Single lane

```text
STEP 1        STEP 2        STEP 3        STEP 4
Explore  →    Train    →    Validate →    Ship
```

### Two lanes

```text
SYSTEM A   ─────●────────●────────●──────
                 ↓
SYSTEM B   ─────●────────●────────●──────
```

The lanes must have a visible relationship.

The current problem described as "two lanes but no visual language distinguishing them" should be fixed by giving each lane:

- a persistent label
- distinct position
- shared timeline
- clear relationship markers

Do not solve parallelism with different colors alone.

---

## Lane language

Use:

- lane label
- baseline
- numbered/active markers
- signal color for current step
- muted structure for completed/future steps

For example:

**Training**

`01 → 02 → 03 → 04`

**Validation**

`01 → 02 → 03 → 04`

The active state is blue.

A confirmed resolution can become green.

---

## Motion

This template should use the strongest **BUILD** behavior.

Sequence:

1. Timeline appears.
2. Step 1 appears.
3. Step 2 connects to step 1.
4. Step 3 connects.
5. Current step receives emphasis.
6. Final state resolves.

Previously introduced information should remain visible unless there is a pedagogical reason to remove it.

This preserves the learner's mental map.

---

# 9.5 `table_build`

## Purpose

Teach comparisons, classifications, specifications, metrics, or decision frameworks.

The supplied presentation already has a strong table language in "Choosing Your First Algorithm."

The video version should **build the table progressively**.

## Layout

Use approximately:

- x = 96–144
- width = 1680–1728
- top = 240–300
- bottom = 900 maximum

Header:

- `#FAFAFA`
- text `#262626`
- border `#D9D9D9`
- radius where applicable: 8 px

Rows:

- white
- subtle divider
- selected/current row: `#F5FAFF`
- active signal: `#148AFF`

## Example

```text
Algorithm       Best for       Speed       Risk
───────────────────────────────────────────────
Regression      Baseline       Fast        Non-linear
Decision Tree   Rules          Fast        Overfit
Random Forest   Tabular        Medium      Slower
```

## Motion

Do not reveal the whole table at once.

Recommended:

1. Header
2. First row
3. Second row
4. Third row
5. Current row highlight
6. Final comparison state

### Important

When a new row enters:

**old rows stay stable.**

Do not reanimate the entire table every time.

This is essential for reducing visual noise.

## Cell emphasis

If narration says:

> "Random Forest is a strong tabular default."

Then:

- row remains visible
- row receives soft blue background
- relevant cell receives signal emphasis

Do not color the entire table blue.

---

# 9.6 `concept_illustration`

## Purpose

Explain something that is difficult to communicate through text alone.

Examples:

- architecture
- cause/effect
- system relationship
- conceptual model
- process
- abstract mechanism
- data flow

## Milestone A decision

**Typographic/diagrammatic only.**

External imagery is optional and future-facing.

## Visual vocabulary

Use the existing design system:

- white surfaces
- light-blue signal surfaces
- blue connectors
- dark text
- muted structure
- cards
- circles
- numbered markers
- simple icons
- charts
- UI-like blocks

Avoid:

- random 3D illustrations
- decorative gradients
- unrelated stock photography
- cartoon characters
- visual metaphors that do not directly support the lesson

## Example: ML pipeline

```text
RAW DATA
   │
   ▼
FEATURES
   │
   ▼
MODEL
   │
   ▼
PREDICTION
   │
   ▼
EVALUATION
```

Each block can be introduced as the narrator explains it.

## Motion

Use **BUILD + FOCUS**.

1. Show starting point.
2. Introduce next concept.
3. Draw connector.
4. Highlight current concept.
5. Continue.
6. Finish with the complete system.

The finished diagram should remain on screen long enough for the learner to form the complete mental model.

---

# 10. Motion grammar

The renderer should not have dozens of unrelated animation presets.

Use a small motion vocabulary.

## 10.1 `REVEAL`

Use when information is simply entering.

Examples:

- title
- subtitle
- card
- label

Behavior:

- slight upward movement
- opacity increase
- no bounce
- no overshoot

Recommended duration:

**300–500 ms**

---

# 10.2 `BUILD`

Use when information is being constructed.

Examples:

- timeline
- algorithm steps
- diagram
- table rows
- process

Behavior:

- new element enters
- previous elements remain stable
- connector appears with the new relationship

Recommended duration:

**400–700 ms**

---

# 10.3 `FOCUS`

Use when directing attention to something already visible.

Examples:

- one table row
- one chart point
- one word/phrase
- one diagram node

Behavior:

- subtle color change
- soft background highlight
- optional scale change of only 1–3%
- surrounding content does not disappear

Recommended duration:

**250–450 ms**

Avoid pulsing continuously.

---

# 10.4 `RESOLVE`

Use when the lesson reaches its answer.

Examples:

- answer to a question
- final result
- correct option
- conclusion
- key takeaway

Behavior:

- transition from neutral/signal to answer state
- answer uses success semantics
- supporting content settles

Recommended duration:

**400–700 ms**

---

# 10.5 `TRANSITION`

Use between concepts.

Preferred:

- crossfade
- directional slide when spatially meaningful
- content replacement using shared anchors

Avoid:

- spinning
- 3D flips
- camera whip
- random zooms
- flashy wipes

The transition should communicate:

> "We are moving to the next idea."

not:

> "Look at this animation."

---

# 11. Easing philosophy

Use smooth, restrained easing.

### General rule

Motion should feel:

**quick to start → controlled → settled**

Avoid:

- exaggerated bounce
- elastic overshoot
- slow theatrical movement
- mechanical linear motion for everything

For educational content, the learner should barely notice the easing itself.

The object should feel intentionally placed.

---

# 12. Motion hierarchy

Not every element deserves the same motion.

### Level 1 — Structural

No animation or extremely subtle entrance.

Examples:

- grid
- divider
- card border
- background
- axes

### Level 2 — Content

Normal reveal/build.

Examples:

- title
- body copy
- cards
- table rows

### Level 3 — Attention

Focus animation.

Examples:

- active value
- chart point
- current step
- important term

### Level 4 — Resolution

Strongest motion emphasis.

Examples:

- answer
- conclusion
- final state

This hierarchy prevents "everything moving all the time."

---

# 13. Narration synchronization

The animation should follow the **spoken explanation**, not run independently.

Example narration:

> "First, we collect the data."

Visual:

**DATA** appears.

Narration:

> "Then we train a baseline."

Visual:

**BASELINE** appears and connects to DATA.

Narration:

> "Finally, we validate the result."

Visual:

**VALIDATE** appears.

This is temporal contiguity in practice.

The visual corresponding to a spoken idea should be visible **when that idea is being explained**, not several seconds before or after.

---

# 14. Progressive disclosure

The renderer should default to:

> **one conceptual unit at a time**

rather than:

> **everything at once**

For example, do not immediately display:

```text
Step 1
Step 2
Step 3
Step 4
Conclusion
Example
Formula
Footnote
```

Instead:

```text
Step 1
↓
Step 2
↓
Step 3
↓
Step 4
↓
Conclusion
```

This is especially important for:

- algorithms
- formulas
- workflows
- diagrams
- tables
- complex charts

---

# 15. Charts and data visualization behavior

The supplied presentation uses charts extensively.

The video renderer should treat charts as **explanatory objects**, not decorative objects.

## Recommended sequence

### Step 1

Show axes / frame.

### Step 2

Reveal the data.

### Step 3

Animate the important movement/trend.

### Step 4

Signal the important point.

### Step 5

Show the explanation.

Example:

```text
Training loss
     \
      \
       \____
            \
```

Then:

```text
Validation loss
     \
      \
       \__
          \__
```

Then highlight:

> "Validation loss starts rising."

The learner sees the exact evidence while hearing the explanation.

---

# 16. Tables and comparisons

Tables should not behave like static spreadsheets.

Use them as **progressive decision aids**.

Example:

### Narration

> "Regression is a good baseline."

Reveal:

**Regression → Baseline**

### Narration

> "Decision trees are easier to interpret."

Focus:

**Interpretability → High**

### Narration

> "But they can overfit."

Focus:

**Risk → Overfits easily**

This transforms a static table into an instructional sequence.

---

# 17. Formula/code treatment

For formulas or code:

- use the mono style
- minimum 26 px
- keep code blocks visually quiet
- highlight only the relevant line
- use signal color for current line
- use answer color only for a confirmed result
- avoid highlighting multiple lines simultaneously

### Example

```text
loss = mean((y - prediction)²)
```

Then:

```text
prediction
```

is signaled while the instructor explains it.

Do not animate every character.

---

# 18. Callouts

The presentation already uses explanatory panels such as:

- "THE LESSON"
- "BIGGEST GAINS"
- explanatory insight blocks

These should become a reusable video pattern.

## Callout structure

```text
THE LESSON

Both curves fall together at first.
When validation loss rises while
training loss keeps falling,
overfitting has begun.

[ Early stopping ]
```

Use:

- white or `#F5FAFF` surface
- `#99CCFF` border
- `#262626` body
- `#148AFF` label
- `#05C170` only when the callout represents a confirmed/correct state

---

# 19. Course-video content rules

Because this is course content, every template should obey these rules.

## Rule 1 — One teaching point per scene

If a scene needs three unrelated ideas, split it.

## Rule 2 — Text supports narration

Do not turn the video into a transcript.

## Rule 3 — Visuals explain relationships

Whenever possible, use:

- arrows
- diagrams
- comparisons
- charts
- spatial grouping

instead of another paragraph.

## Rule 4 — Keep the learner's mental map

When something has been established and is still relevant, keep it visible.

## Rule 5 — Use color sparingly

Blue should indicate the current teaching focus.

Green should indicate resolution/correctness.

Red should indicate failure/wrongness.

Orange should indicate caution.

## Rule 6 — No decorative movement

Every animation should answer:

> "What does this help the learner understand?"

If there is no answer, remove it.

---

# 20. Stock footage / Storyblocks integration later

Storyblocks should be treated as an **optional media layer**, not a template dependency.

Current:

```text
Course content
     ↓
Text / diagrams / charts / UI visuals
     ↓
Renderer
```

Future:

```text
Course content
     ↓
Text / diagrams / charts / UI visuals
     +
Optional media asset
     ↓
Renderer
```

The layout should remain usable if:

- no asset exists
- asset search fails
- asset licensing is unavailable
- an asset is unsuitable

This prevents the video generator from becoming dependent on external asset availability.

---

# 21. Asset slot design for future use

Keep the `asset` slot semantically optional.

The template should specify:

```text
asset:
  optional
  role:
    - supporting_visual
    - contextual_footage
    - demonstration
```

Do not define:

```text
asset = required
```

for `concept_illustration`.

When Storyblocks becomes available, assets can be inserted into a reserved visual region without changing the semantic structure.

---

# 22. Template content constraints

## `cold_open`

- 1 main statement
- 1 optional supporting line
- 1 emphasis target
- no more than ~3 text levels

## `title_card`

- 1 title
- 1 subtitle
- optional 3–6 supporting concepts

## `key_phrase`

- 1 key statement
- 2–4 lines maximum
- 1 emphasis target

## `state_timeline`

- 3–5 states recommended
- 2 lanes maximum in Milestone A
- 1 active state at a time

## `table_build`

- 3–6 columns recommended
- 3–7 rows recommended
- 1 active row at a time

## `concept_illustration`

- 3–8 conceptual nodes
- 1 primary relationship
- optional supporting annotations

If the content exceeds these limits, the authoring layer should split it into multiple scenes rather than compress the design.

---

# 23. Recommended template anatomy

All templates should share:

```text
┌──────────────────────────────────────────────────────┐
│ lesson/module context                         LOGO   │
│                                                      │
│ TITLE                                                │
│ Subtitle / context                                   │
│                                                      │
│                                                      │
│                 MAIN CONTENT                         │
│                                                      │
│                                                      │
│                                                      │
│ supporting metadata / source                         │
└──────────────────────────────────────────────────────┘
```

Not every template must literally show every region.

The important point is that **the spatial language is shared**.

---

# 24. Logo behavior

The presentation includes a logo area consistently.

For video:

- logo should remain small
- top-right is preferred if the source course requires persistent branding
- it must never compete with the teaching content
- no entrance animation on every scene
- preferably static or only introduced once per chapter/section

If the renderer already handles a persistent brand layer, keep the logo outside individual templates.

---

# 25. Scene transitions

Preferred transition hierarchy:

### Same concept → same spatial region

Use a **crossfade/replacement**.

### Same concept → next build state

Use **no full-scene transition**.

Simply continue building.

### New concept

Use a short fade/slide transition.

### New module

Use `title_card`.

This prevents the video from feeling like a PowerPoint slideshow.

---

# 26. The most important change from the current renderer

The renderer should move from:

> **"Put content in the center and animate it."**

to:

> **"Choose a layout based on the instructional job, then reveal the information according to the narration."**

The six templates are not merely visual styles.

They are six **teaching behaviors**:

| Template | Teaching job |
|---|---|
| `cold_open` | Create the question |
| `title_card` | Orient the learner |
| `key_phrase` | Make an idea memorable |
| `state_timeline` | Show progression/relationship |
| `table_build` | Compare/classify |
| `concept_illustration` | Explain a system/relationship |

This should be the mental model Claude Code uses.

---

# 27. R8 renderer-agnostic requirement

The specification must remain renderer-agnostic.

The spec should describe:

- position
- hierarchy
- semantic role
- visual state
- timing intent
- transition behavior
- content constraints

The spec should **not** describe:

- Remotion APIs
- React components
- `useCurrentFrame`
- `interpolate`
- `spring`
- frame numbers tied to implementation
- renderer-specific scene graph objects

Example:

### Correct

> "The active table row receives a soft signal background while surrounding rows remain unchanged."

### Incorrect

> "At frame 42, call interpolate() to change background from X to Y."

Claude Code can translate the first into the renderer.

---

# 28. Motion timing defaults

These are starting points for testing, not immutable laws.

| Motion | Duration |
|---|---:|
| Micro emphasis | 200–300 ms |
| Focus | 250–450 ms |
| Standard reveal | 300–500 ms |
| Text entrance | 400–600 ms |
| Build step | 400–700 ms |
| Resolution | 400–700 ms |
| Major section transition | 500–800 ms |

### Stagger

Recommended default:

**80–160 ms**

Use stagger only when it helps the learner understand sequence.

Avoid 200–500 ms stagger between every item; it makes educational content feel artificially slow.

---

# 29. Motion should follow meaning

Use this decision table:

| Situation | Motion |
|---|---|
| New information | REVEAL |
| Information being constructed | BUILD |
| Narrator points to existing information | FOCUS |
| Correct/result state | RESOLVE |
| New concept | TRANSITION |
| Decorative element | NONE |

This is the core motion grammar.

---

# 30. What not to do

## Do not

- center every scene
- use one animation for everything
- animate every word
- use blue for every semantic role
- shrink text to fit
- make every scene visually dense
- create a new card style for every template
- use stock imagery simply because it exists
- add decorative gradients
- use unnecessary shadows
- use bounce/elastic effects for normal educational content
- constantly zoom in/out
- animate previously revealed content repeatedly
- hide the learner's reference points
- make tables move around after they have been established

---

# 31. Visual QA checklist

Before accepting a rendered scene, check:

### Layout

- [ ] Is the content aligned to the shared grid?
- [ ] Is there a clear primary focus?
- [ ] Is the content using the frame efficiently?
- [ ] Is there excessive empty space?
- [ ] Is there unnecessary crowding?
- [ ] Are margins consistent?

### Typography

- [ ] No text below 24 px
- [ ] Title is clearly dominant
- [ ] Supporting text is visually subordinate
- [ ] Line lengths are readable
- [ ] No unnecessary all-caps body copy

### Color

- [ ] Background is light
- [ ] Blue indicates attention/current state
- [ ] Green indicates resolution/correctness
- [ ] Red indicates wrong/broken state
- [ ] Orange indicates warning/caution
- [ ] No invented colors

### Motion

- [ ] Animation has a teaching purpose
- [ ] Previously revealed information remains stable
- [ ] Current information receives appropriate emphasis
- [ ] No unnecessary bounce
- [ ] No excessive stagger
- [ ] Motion is synchronized with narration
- [ ] Final state is held long enough to understand

### Learning

- [ ] Can the learner tell what to look at?
- [ ] Does the visual clarify the narration?
- [ ] Is unnecessary information removed?
- [ ] Is the relationship between elements obvious?
- [ ] Is the scene trying to teach too much at once?

---

# 32. Acceptance criteria for Milestone A

Milestone A should be considered successful when:

### Visual consistency

All six templates look like they belong to the same course product.

### Token fidelity

The renderer uses the supplied design-system values rather than creating a parallel palette.

### Light theme

Every scene works in light theme without requiring dark-theme variants.

### Typography

The hierarchy is readable at 1920×1080 and respects the existing 24 px floor.

### Layout

The six templates have intentional spatial systems rather than generic centered content.

### Motion

There are at least five distinct semantic motion behaviors:

- reveal
- build
- focus
- resolve
- transition

### Educational behavior

Complex information can be progressively revealed without reanimating everything already visible.

### Concept illustration

A meaningful conceptual diagram can be created without external stock footage.

### Asset independence

The renderer does not fail when no external asset is available.

### Renderer agnostic

The design specification does not depend on Remotion-specific implementation details.

---

# 33. Recommended first test course content

Use the supplied machine-learning presentation as the test corpus.

This is useful because it already contains:

- concept lists
- metrics
- tables
- charts
- worked examples
- timelines/processes
- formulas
- comparisons
- explanatory callouts
- learning objectives

Representative content includes:

### Concept introduction

"Introduction to Machine Learning"

with:

- Supervised Learning
- Unsupervised Learning
- Reinforcement Learning
- Model Evaluation
- Feature Engineering
- Model Deployment

### Data visualization

"Reading a Learning Curve"

with training loss and validation loss.

### Process

"From Raw Data to Live Demo"

with four steps.

### Worked example

"Worked Example: Bias & Variance"

with question → explanation → application.

### Algorithm comparison

"Choosing Your First Algorithm"

with algorithm, best use, speed, interpretability and risk.

These are ideal renderer test cases because they cover the six template jobs.

---

# 34. Suggested test sequence

Do not implement all six templates and immediately render an entire course.

Test in this order:

## Test 1 — `key_phrase`

Use:

> More data is not always the best next dollar.

Goal:

Validate typography, hierarchy and basic motion.

## Test 2 — `table_build`

Use the algorithm comparison.

Goal:

Validate progressive disclosure and row stability.

## Test 3 — `state_timeline`

Use:

> Explore → Train → Improve → Ship

Goal:

Validate sequential construction.

## Test 4 — `concept_illustration`

Use:

> Raw Data → Features → Model → Prediction → Evaluation

Goal:

Validate diagrammatic teaching without external assets.

## Test 5 — `title_card`

Use:

> Introduction to Machine Learning

Goal:

Validate orientation.

## Test 6 — `cold_open`

Create a lesson question from the existing content.

Goal:

Validate opening rhythm and hierarchy.

Only after these work should the system be evaluated as a full video.

---

# 35. Final design philosophy

The renderer should feel like:

**A well-designed educational presentation that learned how to move.**

Not:

**A motion-graphics template that happens to contain educational text.**

The visual language should stay calm.

The motion should be purposeful.

The hierarchy should be obvious.

The blue should guide attention.

The green should resolve.

The timeline should build.

The table should teach.

The diagram should explain.

The narration should determine when things happen.

And the learner should never have to ask:

> "What am I supposed to be looking at?"

---

# 36. Research basis

The motion and instructional recommendations in this document are informed by established multimedia-learning research.

### Richard E. Mayer — Multimedia Learning

Key principles applied here:

- **Coherence:** remove unnecessary visual information.
- **Signaling:** cue important information.
- **Spatial contiguity:** keep related words/visuals close.
- **Temporal contiguity:** synchronize related narration and visuals.
- **Segmenting:** break complex material into manageable parts.
- **Modality:** avoid simply duplicating the entire narration as on-screen text.

### Effective Educational Videos

Educational-video literature similarly recommends:

- signaling important information
- segmenting information
- eliminating extraneous visual elements
- using complementary visual and auditory channels
- keeping instructional videos focused

### Guo, Kim & Rubin — edX video engagement research

Their large-scale study of millions of edX viewing sessions found strong engagement benefits associated with shorter video segments and certain more personal/drawing-based instructional formats.

For this renderer, the relevant lesson is not to copy Khan Academy's aesthetic. It is:

> **The online video format should be designed for active viewing rather than treated as a recording of a slide deck.**

---

# 37. Sources used for research

1. Mayer, Richard E. — *Multimedia Learning*.
2. Mayer & Fiorella — *Principles for Reducing Extraneous Processing in Multimedia Learning*.
3. Brame, Cynthia J. — *Effective Educational Videos: Principles and Guidelines for Maximizing Student Learning from Video Content*.
4. Guo, Philip J.; Kim, Juho; Rubin, Rob — *How Video Production Affects Student Engagement: An Empirical Study of MOOC Videos*, ACM Learning @ Scale, 2014.
5. Research on signaling/cueing, segmenting, coherence, spatial contiguity and temporal contiguity in multimedia learning.

---

# 38. Handoff to Claude Code

The implementation brief should be:

> Implement the six course-video templates using the supplied design-system configuration as the only color/style source of truth.
>
> The renderer is light-theme only for Milestone A.
>
> Use a shared 1920×1080 grid and consistent typography hierarchy.
>
> Implement six instructional layouts:
>
> 1. `cold_open`
> 2. `title_card`
> 3. `key_phrase`
> 4. `state_timeline`
> 5. `table_build`
> 6. `concept_illustration`
>
> The templates should be renderer-agnostic at the specification level.
>
> Implement semantic motion behaviors:
>
> - REVEAL
> - BUILD
> - FOCUS
> - RESOLVE
> - TRANSITION
>
> Animation should follow narration and progressively reveal information. Previously established content should remain stable unless the instructional structure requires replacement.
>
> `concept_illustration` must work without external imagery. Treat its asset slot as optional and future-compatible with Storyblocks/Freepik.
>
> Do not introduce new colors, gradients, dark theme variants, decorative motion, or unrelated illustration styles.
>
> Preserve the existing 24 px minimum text constraint.
>
> Validate the implementation against the supplied Light Theme presentation examples before considering Milestone A complete.

---

## Bottom line

The design system already gives us the **visual ingredients**.

The presentation already gives us the **course visual language**.

The renderer now needs the **spatial rules + teaching behaviors + motion grammar** that turn those static ingredients into educational video.

That is the purpose of this specification.
