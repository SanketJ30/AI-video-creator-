# Script Plan — the beat list

You turn a lesson plan into the ordered beat list for one video. You do **not**
write narration here; a separate per-beat stage does that. Your output defines
the spine.

Why the split: each beat's narration is generated and hashed independently, so
editing beat 7 costs one regeneration instead of twelve (PRD §5.3). If you put
narration in this artifact you break that property.

## Rules

- 8–14 beats, 6–8 minutes total (D4). Estimate seconds per beat and give a total.
- Preserve the lesson plan's sequence unless it violates pre-training; if you
  reorder, say why.
- Give each beat a `brief`: two or three sentences telling the beat writer what
  this beat must accomplish, which claims it rests on, and what it must not
  assume yet.
- `role` is one of: `hook`, `context`, `definition`, `mechanism`,
  `worked_example`, `contrast`, `callback`, `consolidation`, `outro`.
- Plan at least one **callback** to an earlier video in the series where the
  curriculum makes one available. This is the series continuity the product is
  built on.
- Carry `signal[]` through from the lesson plan — the storyboard maps it to
  visual emphasis.

## Output

Return JSON only.

```json
{
  "video_id": "v2",
  "estimated_seconds": 420,
  "beats": [
    {
      "beat_id": "b01",
      "ordinal": 1,
      "role": "hook",
      "brief": "<what this beat must accomplish>",
      "claims": ["c03"],
      "objective": "o1",
      "signal": ["left_rows"],
      "load": {"new_symbols": 0, "new_terms": 1, "new_relationships": 1, "score": 2},
      "est_sec": 14
    }
  ],
  "callbacks": [{"beat_id": "b06", "to_video": "v1", "concept": "inner_join"}]
}
```
