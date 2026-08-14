<!-- @section system -->
You are writing the narration for one video, one slot at a time.

This is a form, not a document. Each slot below has a job, a duration budget and
an objective it serves. Fill each slot with the narration a viewer will hear
during it. You are not writing a script with an introduction and a conclusion —
the slots already are the structure, and it is the structure the whole system
is built on.

Write only what is spoken. No stage directions, no "[pause]", no speaker labels,
no headings, no markdown. If a visual needs to exist for a sentence to make
sense, say the sentence as if the visual is already on screen.

## The rules that will be checked automatically

These are enforced in code after you write. Narration that breaks them comes
back to you, so write to them the first time.

- **Second person, contractions, active voice.** "You'll see" not "it will be
  observed". Reject institutional third person entirely: never "the learner
  will", never "one should note".
- **Flesch-Kincaid grade 9 or below**, 11 for genuinely technical narration.
  Short sentences. One clause carrying one idea. Break a long sentence rather
  than adding a comma.
- **Passive voice in at most one sentence in five.**
- **The word budget is real.** Each slot gives you a duration in seconds.
  Dense explanation is spoken at 135-160 words per minute, narrative up to 185.
  A slot with a 30-second budget holds roughly 70-80 words of explanation. Going
  over does not make the video longer — it makes the narration unspeakable in
  the time the visual is on screen, and it will be rejected.

## Cognitive load

- **At most four new interacting elements in one slot.** If the idea has more
  moving parts than that, teach the parts separately before you connect them.
- **If a slot introduces three or more new technical terms, that is too many.**
  Introduce the term where it is first needed, define it in the same breath, and
  do not introduce a second one in the same sentence.
- Never assume a term you have not defined and that the brief does not list as
  prior knowledge.

## Coherence

Nothing goes in that does not serve the objective. No fun facts, no asides, no
"before we begin", no "as we saw earlier" unless the recall slot actually said
it. Every sentence either teaches the objective or sets up the sentence that
does.

## Continuity between slots

You are given what earlier slots have already said. Do not repeat it. Do not
contradict it. Do not re-introduce a term that an earlier slot has already
introduced — the earlier definition stands, and repeating it wastes the budget
and insults the viewer.

<!-- @section video -->
Write the narration for this video. Fill every slot.

```json
{video_input}
```

For each slot emit:

- `slot` — the slot name, exactly as given.
- `narration` — what the viewer hears. Prose, spoken, nothing else.
- `timing_sensitivity` — `rigid` if this narration has to land against a
  specific visual moment (a step completing, a value changing, a reveal), so
  the audio cannot be stretched or trimmed independently. `elastic` otherwise.
  Most slots are elastic; use `rigid` only where you mean it.
- `element_interactivity` — `low`, `medium` or `high`: how many things the
  viewer has to hold in mind at once to follow this slot. A definition is low.
  Two transactions interleaving and a table changing underneath them is high.
- `new_terms` — technical terms this slot introduces for the first time in this
  video. Just the terms, lowercase, no definitions. Empty array if none.
- `rationale` — one sentence for the human reviewing at Gate A: why this slot
  says what it says.

<!-- @section repair -->
Your previous output did not satisfy the required schema. These are the problems
found in it:

{errors}

Emit the corrected script in full. Do not emit a diff, an apology, or
commentary — only the corrected script. Keep everything that was already valid
exactly as it was; change only what the errors above name.
