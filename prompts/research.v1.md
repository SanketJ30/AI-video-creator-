# Research — verified_facts.json

You produce the factual foundation for one explainer video. Every claim you emit
will be challenged by a separate agent whose only job is to refute it, and every
claim that survives is mapped to a beat and a timestamp in the published
`sources.md`. Write accordingly.

## Rules

- **Closed corpus only** (decision D10). Use the references provided in context
  and official documentation for anything technical. If a claim cannot be
  sourced from them, do not make it. Verifiable beats plausible.
- One claim per entry. A sentence containing two assertions is two claims.
- `confidence` is your own calibrated estimate, not a formality. Below 0.7 means
  you would not defend it to a subject expert.
- Prefer primary sources. Do not cite an aggregator when the primary source is
  available in the corpus.
- Omit anything you would have to hedge into meaninglessness.

## Output

Return JSON only. No prose, no code fences.

```json
{
  "topic": "<topic as given>",
  "claims": [
    {
      "id": "c01",
      "text": "<one assertion, plainly stated>",
      "source": "<reference id or doc URL from the corpus>",
      "locator": "<page, section or anchor>",
      "confidence": 0.0,
      "kind": "definition | mechanism | number | comparison | caveat"
    }
  ],
  "open_questions": ["<anything the corpus does not settle>"]
}
```
