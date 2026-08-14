# Challenges and Risk Register
## AI Course Video Engine — companion to PRD.md

**Version:** 0.1
**Date:** 13 August 2026
**Purpose:** The honest account. Read this before funding the PRD.

---

## How to read this

Risks are rated on two axes:

- **Severity** — what happens if it lands. `Fatal` = kills the company. `Severe` = kills a quarter or a segment. `Moderate` = costly. `Minor` = annoying.
- **Likelihood** — `Near-certain` / `Likely` / `Possible` / `Unlikely`.

Order is roughly by expected damage. **The first five are the ones that decide whether this works.**

Two summary tables are at the end (§10) if you want to skim.

---

# 1. THE FIVE THAT MATTER MOST

## R1. The chunked re-render architecture is genuinely hard, and it is load-bearing

**Severity: Fatal · Likelihood: Likely**

The entire product thesis rests on one claim: *changing one word re-renders one scene, and the result is frame-and-sample-accurate.* If that doesn't work reliably, you have a slower, more expensive Colossyan.

Why it's hard — each of these is a real, common failure:

- **Non-determinism poisons the cache silently.** A font load race, an unseeded `Math.random()`, a Chromium point-release, a GPU-vs-CPU rasterisation difference — any one produces a different render for the same key. The failure mode isn't a crash; it's a subtly wrong video shipped to a customer, discovered weeks later, with no obvious cause. Cache-poisoning bugs are among the hardest classes of bug to diagnose because the symptom is separated from the cause by an arbitrary amount of time.
- **Concatenation artifacts.** Concatenating lossy inter-frame-coded chunks produces GOP-boundary artifacts and timestamp fights. The fix (lossless intra-only intermediates + single final encode) multiplies intermediate storage — ProRes intermediates for a 40-scene course are large, and storage is now a real line item.
- **Drift accumulates.** 29.97 fps against 48 kHz gives 1601.6 samples/frame. Over 40 scenes that is audible desync. The fix (integer fps, frame-aligned durations, silence padding) is easy to *state* and easy to forget in one code path.
- **Transitions couple neighbours.** Handle-frame rendering doubles the complexity of scene rendering and is easy to get subtly wrong at the head/tail boundary.
- **Invalidation granularity is a design decision you make once.** Get it coarse (After Effects' failure mode — touching a comp property nukes everything) and the cache is worthless. You cannot easily refine it later because the component split is baked into the schema.

**Mitigation**
- **Phase 0 exists for this.** Build it first, before agents, before UI. Eight weeks, hand-authored storyboards, no AI.
- Continuous determinism verification: render the same scene on two workers, compare digests, alarm on mismatch. Run this in production forever.
- Version *everything* into the cache key: Chromium, FFmpeg, codec params, renderer, architecture.
- Golden-file regression suite: a set of reference scenes with known-good digests, checked in CI.
- Hire or contract someone who has built a real video pipeline. This is not a generalist-web-engineer problem, and the cost of learning it on the job is measured in quarters.

**Kill criterion:** if Phase 0 doesn't produce a clean, deterministic edit-one-scene loop in 8 weeks, stop and rethink the thesis. That is what Phase 0 is *for*.

---

## R2. Multi-agent pipelines produce plausible mush at scale

**Severity: Severe · Likelihood: Near-certain (without discipline)**

Your brief asks for "many agents at each and every level to verify everything." The instinct is right; the naive implementation fails in a specific, well-documented way.

- **Error compounding.** Twelve agents at 95% each ≈ 54% end-to-end. Verification helps only if verifiers are genuinely independent and adversarial. They usually aren't — an LLM verifying an LLM's output shares failure modes, especially when both are the same base model with a similar prompt.
- **Verification theatre.** A verifier that says "looks good" 98% of the time is a latency tax with a compliance aesthetic. You need to *measure* verifier catch rate against seeded errors, or you cannot tell whether it works.
- **Latency stacks.** Twelve sequential agents at 20–60 s each is 4–12 minutes before a single frame renders. Users experience this as broken even if the output is excellent.
- **Debuggability collapses.** When the output is wrong, which of twelve agents caused it? Without typed schemas and full provenance you cannot answer, and you cannot improve what you cannot diagnose.
- **The mush failure mode.** Multi-agent systems converge toward safe, generic, unobjectionable output. Every agent smooths an edge. The result passes every check and is boring — which for engaging course content is a product failure, not a quality success.

**Mitigation**
- **Deterministic checks wherever possible.** Contrast, density, word counts, Bloom alignment, DAG cycles, glyph coverage — code, not agents. Faster, free, reliable, and debuggable. This is the single biggest lever.
- **Typed schemas on every handoff.** No free-text between agents.
- **Adversarial verifiers**, prompted to refute rather than review, and different from the generator (different model where practical, different lens always).
- **Seed known errors and measure catch rate per verifier.** Delete verifiers below threshold — an unmeasured verifier is a cost centre.
- **Parallelise the DAG.** Fan out at every point without a real dependency.
- **Protect the edges.** Give the Hook Specialist and Analogy Generator explicit permission to be sharp, and don't let downstream smoothers sand them off. Consider exempting "voice-bearing" slots from consensus-style verification entirely.
- Full provenance (R6 in the PRD) so failures are attributable.

---

## R3. Iteration cost — the thing you're selling — may not survive contact with vendor pricing

**Severity: Severe · Likelihood: Possible**

The promise is "iteration is free." Three things threaten it:

1. **Remotion charges per render, including stills.** Fine-grained scene re-rendering is exactly the behaviour their pricing taxes. Trivial at low volume ($4.80 for a 30-video course's first pass), potentially serious for a product designed around constant iteration. From v5.0 licence telemetry is mandatory, so this isn't a "don't worry about it" situation.
2. **Generative assets don't cache across meaningful edits.** Changing a scene's *concept* means a new Veo generation at $3–37/min with a reroll multiplier. Only *cosmetic* edits are genuinely free. If users mostly make conceptual edits, the free-iteration promise is much narrower than the pitch.
3. **TTS re-runs on any narration change.** Cheap ($0.45/video) but not zero, and it multiplies across languages.

**Mitigation**
- Negotiate Remotion Enterprise **early** — the $500/mo floor with custom terms almost certainly beats $0.01 × millions, and R8 (renderer-agnostic schema) gives you leverage.
- Debounce renders to one per scene per commit.
- Make the *classes* of edit explicit in the UI: cosmetic (free, instant), textual (cheap, ~10 s), conceptual (costs generation, shows an estimate). **Users tolerate cost they can predict; they revolt at cost that surprises them.**
- Aggressive asset-level caching and cross-course dedup.
- Be careful with the marketing claim. "Edits cost what they should" is defensible and still differentiating. "Iteration is free" invites a specific, easily-produced counterexample.

---

## R4. The quality ceiling of AI-generated instructional content

**Severity: Severe · Likelihood: Likely**

Uncomfortable truths from the research:

- **Avatar talking-head has plateaued at "convincingly professional but detectably synthetic."** The remaining gap is behavioural, not resolution. ~350 Synthesia G2 reviews cite unnatural avatars.
- **Embodiment and voice principles did not replicate** in the 2025 meta-analysis. Eye-tracking shows learners over-attend to avatar faces at the expense of instructional graphics. Telling 240 corporate learners mid-session that their instructor was synthetic dropped trust sharply *with no change in objective learning outcomes*.
- **Generative video has a high visual ceiling and a low reliability floor.** 8-second clip caps, unsolved character consistency across shots, 5+ attempts per usable clip reported by Luma users.
- **Effects have declined over time** in the multimedia literature, as studies moved from lab to field and the novelty premium faded.

The blunt version: **you can reliably produce content that is better than a bad human-made course and worse than a good one.** That is a real and large market — most corporate and creator courses are bad — but it is not "indistinguishable from premium human production," and pitching it that way sets up a demo-to-delivery gap that kills deals.

**Mitigation**
- **Compete on pedagogy, not photorealism.** The linter is the differentiator; a competitor can buy the same Veo access tomorrow, but they can't buy the course graph or the evidence-derived rule set.
- Default to motion graphics, which have a *higher* achievable quality ceiling at these budgets than synthetic humans and are pedagogically better supported (text+diagram was the most consistent combination in the meta-analysis).
- Set expectations honestly in sales. Under-promise on visual fidelity, over-deliver on structure, consistency and maintenance.
- **Instrument learning outcomes.** If you can show better outcomes than the human-made baseline, visual fidelity stops being the axis of competition. That is the strongest possible position and it's available to you and nobody else.

---

## R5. Course memory doesn't scale naively, and it's where the differentiation lives

**Severity: Severe · Likelihood: Near-certain**

CourseMemory is Wedge A. It's also the component most likely to quietly degrade.

- **Context explosion.** A 100-video course's memory will not fit in a context window. Naive injection fails, and it fails *gradually* — quality degrades before anything errors.
- **Retrieval quality determines continuity quality.** Miss the relevant prior content and the AI re-teaches or contradicts. This failure is invisible to automated tests and obvious to a human watching the course — the worst combination.
- **Memory drift.** As a course is edited over months, memory can diverge from actual content. Then continuity decisions are made against a fiction.
- **Cascade ambiguity.** Change a definition in video 2 — what should happen to videos 5, 9, 14? Auto-regenerate destroys the author's manual work and their trust. Flagging everything creates alert fatigue. Neither extreme is right and the middle requires judgment.
- **Versioning is genuinely complex.** "What did the course know when video 5 was written?" must be answerable for reproducible regeneration.

**Mitigation**
- **Build retrieval from day one.** Not "we'll add RAG later" — every prompt in the system is shaped by whether memory arrives whole or retrieved. Retrofitting it is a rewrite.
- Derive memory from the graph rather than maintaining it separately where possible; where a cache is needed, verify it against the graph on a schedule and alarm on drift.
- **Impact analysis with a severity model**: contradiction (blocking), staleness (warn), stylistic drift (advisory). Only ever *propose* changes; never auto-apply across videos.
- Test continuity explicitly: seeded contradictions, term-redefinition detection, analogy-collision detection. Build this test suite early; it's the only way to know the wedge works.

---

# 2. TECHNICAL CHALLENGES

## R6. Localisation timing and layout
**Severity: Moderate · Likelihood: Near-certain**

German expands 10–35%, Japanese contracts 10–55%. Short strings — exactly the abridged key phrases §9.4 mandates — expand most (200–300% under 10 characters). Thai needs ~150% Latin line height. Arabic is cursive with contextual shaping, so per-character kinetic typography breaks joining. Han unification means the same codepoint needs different fonts for JP vs SC vs TC readers, and a Japanese reader *will* notice Chinese glyph forms. Missing glyphs render as tofu **successfully** and ship silently.

**Mitigation:** span-ID anchoring (PRD R3) is the structural fix and must be in place before any animation code. Hybrid elastic/rigid timing. Pseudo-localisation in CI with ×1.4 expansion and an RTL pseudo-locale. Hard-fail on missing glyphs. Per-locale font selection, subset per render. Auto-shrink with a floor, then reflow, then human review — never silent truncation.

## R7. Vendor volatility in the model layer
**Severity: Moderate · Likelihood: Near-certain**

OpenAI killed the Sora product on 26 April 2026 and shuts the **Sora API on 24 September 2026** with no listed replacement. Runway became a model router. Veo pricing spans 13× between Lite and quality tiers. Google no longer publishes Veo rate limits. Captions pivoted to Mirage and left this market.

**Mitigation:** every model behind an internal interface with per-model prompt shaping as a plugin. At least two viable providers per capability at all times. Quarterly re-benchmarking of quality *and* price. Request Veo quota increases before launch, not after. Never let a vendor-specific construct into the scene graph schema.

## R8. Stock media licensing
**Severity: Severe if ignored · Likelihood: Near-certain if unaddressed**

Pexels prohibits replicating core functionality and requires prominent attribution on every request, at 20,000 req/month. Unsplash explicitly bars selling unaltered photos "directly or indirectly" and **requires hotlinking** — you cannot legally pull the file into FFmpeg. Both are disqualifying, and both are what a fast-moving team reaches for by default.

Storyblocks is the correct answer (explicit monetisation rights, $20k indemnification per asset, unlimited API calls, flat MAU-scaled fee) — **but their terms bar distributing source files stand-alone.** Content must be incorporated into a finished project.

**Mitigation:** Storyblocks from day one; get the quote during Phase 0 because it moves the unit economics. **Enforce "no raw asset download" in code, not policy** — a single "download assets" button ships a licence breach. Getty/Shutterstock as negotiated Phase 3 add-ons. Never build on Midjourney (no official API; every "Midjourney API" is an unauthorised reseller).

## R9. Reroll rate is the hidden COGS
**Severity: Moderate · Likelihood: Near-certain**

Every cost table in the PRD is a *floor*. Real cost is floor × reroll factor, and 2.5× is a realistic starting point. On Tier 2 that's $22.50 of a $46.21 video — more than all of Tier 1. InVideo users report 15–30% overrun from failed edits; Luma doesn't refund failed subscription generations.

**Mitigation:** Asset QA agent is the highest-ROI component in the system — it directly controls the largest COGS line. Draft-then-approve routing. Reference-image conditioning. Model-specific prompt shaping. **Track reroll factor as a first-class business metric**, reviewed weekly, not as an engineering curiosity.

## R10. Render infrastructure at scale
**Severity: Moderate · Likelihood: Possible**

Bursty load (a customer regenerates a 40-video course), Lambda cold starts, 200× concurrency caps, lossless intermediate storage, CDN costs, and a cache that grows without bound.

**Mitigation:** queue with per-customer fairness and priority tiers; keep warm pools for interactive edits and cold for batch; LRU eviction with pin/bake protection for locked scenes; content-addressed immutable CDN objects with `max-age=31536000` and pointer flips (no invalidation storms); tiered storage for intermediates.

## R11. Screen capture and software demos
**Severity: Moderate · Likelihood: Likely**

Colossyan openly cannot show real software UI, and this excludes the largest single category of training content. If you serve it, you need either a synthetic-UI renderer (deterministic, brandable, annotatable) or ingestion of user-recorded captures — with all the alignment, cropping, redaction, zoom-and-highlight and PII problems that implies.

**Mitigation:** Phase 3. Start with ingestion + AI annotation (auto zoom-to-region, callouts anchored to narration spans) before attempting synthetic UI. Note that a synthetic-UI renderer is a real differentiator worth more than another avatar tier — but it is its own product-sized build.

---

# 3. PEDAGOGY AND PRODUCT CHALLENGES

## R12. The evidence base is weaker than the industry pretends
**Severity: Moderate · Likelihood: Near-certain**

You are building a product on research findings, so you need to know how solid they are.

- Overall multimedia effect **g = 0.37** — real but modest.
- **Segmentation, contiguity, voice and embodiment came out weak or non-significant** in the 2025 meta-analysis. Four of the twelve principles.
- The segmenting meta-analysis gives d ≈ 0.32–0.36 with a pacing moderator suggesting the mechanism is partly "forced pauses create processing time" — which learner-paced designs already provide.
- The widely-cited Guo et al. numbers (6-minute engagement plateau, 2.9 min median for 9–12 min videos, the speaking-rate finding) **could not be verified from the primary source.** The <6 min *recommendation* and the qualitative rankings are verified; the specific percentages circulate widely without traceable provenance. Do not put them in a sales deck.
- Guo et al. measured **engagement (watch time), not learning.** Short videos may be watched more completely without producing more learning.
- Höffler & Leutner's animation effect size (~d 0.37) is from a secondary source and should be checked before external citation.
- "Germane load" has been substantially reinterpreted since ~2010 and some CLT researchers have dropped it as a category. Don't build a UI that asks authors to "increase germane load."

**Mitigation:** cite carefully, and only what you've verified — a marketing claim traced to an unverifiable statistic is a credibility risk with exactly the P3 persona you most need to convince. Treat the thresholds as **defaults to be validated by your own outcome data**, not laws. The strongest position is empirical: "here is what our data shows for courses like yours." Build toward being able to say that.

## R13. Users want the pedagogically worse thing
**Severity: Moderate · Likelihood: Near-certain**

Yue, Bjork & Bjork is unambiguous: learners **preferred** full verbatim on-screen text while performing **worst** with it (.25 recall vs .33 with no text at all, vs .39–.40 for abridged/near-paraphrase). Fluency during learning misleads.

Authors will want: background music (violates coherence), more text on screen (violates redundancy), longer videos (violates segmenting), decorative visuals (violates coherence), and avatars everywhere (violates embodiment). Every one of these will *feel* better and test worse.

**Mitigation:** the system explains and offers a compliant alternative rather than refusing (PRD §10.2.5). Ship the pedagogy report so the constraint is visible and justified rather than mysterious. **Do not optimise on satisfaction surveys** — track satisfaction as a guardrail, optimise on outcomes. Allow override with a logged, provenance-recorded decision; an override you can see is far better than a constraint users route around by leaving.

## R14. Instructional designers may reject the product outright
**Severity: Severe (for the P2/P3 segment) · Likelihood: Possible**

P3 is the gatekeeper. They are professionally sceptical of AI content quality and often correct. If the product reads as "AI replaces the instructional designer," they will block procurement — and they have the standing to do it, because they're the ones who'd have to defend the output.

**Mitigation:** position as *executing* their judgment, not replacing it. The objective graph, the linter, the override system and the exportable pedagogy report are all P3-facing features. Give them named authorship. Recruit 5–10 IDs as design partners in Phase 1 — their objections in month 2 are worth more than any amount of user research in month 12. Ship the OTIO/asset export so they can take work elsewhere; the ability to leave is what makes staying a choice.

## R15. The demo-to-delivery gap
**Severity: Moderate · Likelihood: Likely**

Generation demos beautifully and disappoints in production — Google Vids' AI storyboards need 60–70% manual rework; testers deleted most AI-generated scenes. Your demo will be a curated topic; the customer's first real course will be a messy internal one.

**Mitigation:** **demo the editing, not the generation.** "Watch me change 40 things in 10 minutes" is a differentiated demo and it's an honest one. Onboard with the customer's real content in the first session. Measure and publish time-to-acceptable-course rather than time-to-first-video.

## R16. Chat editing is harder than it looks
**Severity: Moderate · Likelihood: Likely**

Scope ambiguity ("make this shorter" — this scene, video, or course?), destructive misinterpretation, intent drift over long sessions, and the general problem that natural language is a poor instrument for spatial and temporal precision.

**Mitigation:** chat operates on the **current selection**, always. **Diff-before-commit on every action** — this single decision eliminates most of the damage. Undo at graph granularity. Direct manipulation for spatial and temporal work; chat for semantic and bulk work. Don't force chat to do what a drag handle does better.

---

# 4. BUSINESS AND MARKET CHALLENGES

## R17. Incumbents can copy features; the question is whether they'll copy the architecture
**Severity: Severe · Likelihood: Likely**

Synthesia has ~$4B valuation and >$100M ARR. HeyGen ships faster than anyone in the category — Avatar V, Seedance integration, a CLI, agent skills for Claude Code and Cursor, and **HyperFrames**, an open-source HTML/CSS→deterministic-MP4 engine explicitly designed so AI agents author video in HTML. That last one should concern you: HyperFrames is a declarative, deterministic, Git-diffable render layer. It is *architecturally adjacent* to what the PRD proposes, and it is already shipped.

Colossyan already claims edit-without-full-re-render, SCORM on all paid plans, and one-pass course generation.

**But:** none of them have the course graph, and adding it means rewriting their data model. That is a genuine structural moat — the kind that survives a well-funded competitor deciding to compete — *for as long as it takes them to decide it's worth the rewrite.*

**Mitigation:** move fast on Wedge A specifically; it is the only one that's expensive to copy. Land P2 customers whose catalogues create switching costs (their course graph, memory and history live in your system). Be careful about publicly explaining the architecture too precisely too early. And watch HyperFrames — if HeyGen puts a course layer on it, the window narrows sharply.

## R18. Google and Canva bundling
**Severity: Severe · Likelihood: Possible**

Google Vids at $7–22/user/mo inside Workspace, Canva at ~$12/mo. Both currently bad (Vids needs 60–70% rework; Canva Pro gets 20 ultra-credits/month) but both have distribution nobody can buy.

**Mitigation:** they will not build SCORM, xAPI, objective DAGs, or spaced review — those are L&D-specific and outside their product logic. Go deep on the course layer where bundling doesn't reach. Do not compete on "make a video fast."

## R19. Creator churn
**Severity: Moderate · Likelihood: Near-certain for P1**

Solo creators build one course and leave. Course creation is inherently episodic.

**Mitigation:** the maintenance story is the retention story. Spaced-review schedules, freshness alerts ("3 facts in module 2 have changed"), localisation expansion, scene-level analytics that suggest what to improve. **Weight go-to-market toward P2**, where catalogue maintenance is continuous and budget is recurring; treat P1 as acquisition and brand, not as the core business.

## R20. Pricing model risk
**Severity: Moderate · Likelihood: Possible**

Flat-rate minutes with free iteration only works if the cache works (R1) and if customers stay in Tiers 1/1M. A customer who leans on generative B-roll can burn the margin on a single course.

**Mitigation:** hard caps with explicit upgrade prompts on Tier 2/3. Cost estimates shown before every generative action. Monitor per-customer margin weekly, not monthly. Model the abuse case (a customer regenerating a 40-video course nightly) explicitly before launch — someone will do it.

## R21. Enterprise procurement is slow and expensive
**Severity: Moderate · Likelihood: Likely (when you move upmarket)**

SOC 2 Type II, ISO 42001, GDPR, SSO/SAML, SCIM, DPAs, security questionnaires, AI governance documentation, EU AI Act obligations. Synthesia has all of it and markets it heavily. 1EdTech certification for LTI adds another cycle.

**Mitigation:** stay mid-market in Phases 1–2. Start SOC 2 in Phase 2 (it takes 6–12 months of observation, so starting it when the first enterprise deal appears is starting it a year late). Budget properly — this is a real cost line, not overhead.

---

# 5. LEGAL, ETHICAL AND REGULATORY

## R22. AI content disclosure and the trust cliff
**Severity: Moderate · Likelihood: Likely**

The finding is specific and worth taking seriously: when 240 corporate learners were told mid-session that their instructor was synthetic, **trust and engagement dropped sharply** — with no change in objective learning outcomes. Meanwhile the EU AI Act Article 50 transparency obligations apply to synthetic content, and Synthesia has already signed the Code of Practice.

The uncomfortable implication: disclosure is both legally expected and engagement-negative. There is no clever way out of that tension.

**Mitigation:** disclose up front, not mid-session — the damage in the study came from the *reveal*, from learners discovering something they'd been allowed to assume. Framing "AI-produced, expert-authored, reviewed by [name]" is honest and preserves human accountability. **Another argument for motion graphics over synthetic humans**: nobody feels deceived by an animated diagram. Build disclosure metadata into the export formats from Phase 1.

## R23. Factual accuracy and liability
**Severity: Severe · Likelihood: Possible**

Course content teaches. Wrong content in compliance, medical, financial or safety training carries real liability — and unlike a chatbot's answer, a course is authoritative by construction, distributed at scale, and completed under a compliance record.

**Mitigation:** fact-checking with source citation and confidence scoring; anything below threshold surfaces in the UI rather than being silently kept. **Mandatory human sign-off before publication** — not an optional gate, and not skippable by setting, for regulated verticals. Clear ToS on responsibility. Store assertions with sources in CourseMemory so a claim can be audited later. Consider declining regulated verticals until Phase 3+ and the review workflow is proven.

## R24. Voice, likeness and avatar consent
**Severity: Severe · Likelihood: Possible**

Custom avatars and voice clones need documented consent, revocation handling, misuse prevention and deepfake safeguards. **Wav2Lip's public checkpoint is research-only** due to LRS2 training-data terms — commercial use requires a separate Sync Labs contract, and a great many "open source lipsync" tutorials quietly omit this. If anyone on your team ships it, you have a licence breach in production.

**Mitigation:** consent capture with timestamped records and a working revocation path (including "what happens to already-published videos"). Never self-host Wav2Lip. Rent avatars from vendors who carry the consent infrastructure. Content moderation on avatar generation requests — and note Synthesia's 48+ hour moderation turnarounds are a documented customer complaint, so design yours to be fast or narrow.

## R25. Training-data and output provenance
**Severity: Moderate · Likelihood: Possible**

Generative video and image models carry unresolved copyright questions. Enterprise buyers increasingly ask for indemnification.

**Mitigation:** prefer vendors offering indemnification (Storyblocks gives $20k per asset; check Google/Adobe terms for generative output). Prefer rendered diagrams over generated imagery — deterministic, owned, no provenance question, *and* pedagogically better. Track asset provenance in the graph. Get contractual clarity from generative vendors before enterprise sales, not during.

## R26. Accessibility as a legal requirement
**Severity: Moderate · Likelihood: Likely**

WCAG 2.2 AA is contractually required by public sector, education and many enterprises. **1.2.5 Audio Description at AA is the one course products fail.**

**Mitigation:** the self-describing-narration rule (PRD §16.2) turns this from a post-production cost into a design-time constraint — and it's good pedagogy independently. Automate contrast, flash-rate and caption checks. **Reserve the caption safe area in every layout template from day one**; retrofitting it across a template library is painful and will be deferred forever if not done now.

## R27. Data residency and privacy
**Severity: Moderate · Likelihood: Possible**

Customer source material may contain confidential or personal data. Learner xAPI data is personal data under GDPR. Multiple third-party model vendors process both.

**Mitigation:** DPAs with every vendor; regional processing options; explicit data-retention policy (note Veo retains generated video server-side for only 2 days — you must pull and store, which is also a compliance question); the ability to exclude a customer's content from any training or analysis. This is also the one legitimate argument for self-hosting models later, and it's a customer-driven one rather than a cost-driven one.

---

# 6. ORGANISATIONAL AND EXECUTION

## R28. This needs an unusual team
**Severity: Severe · Likelihood: Likely**

Required, and rarely co-located in one team: video pipeline engineering (codecs, timing, determinism — genuinely specialist), distributed systems (caching, DAG, queues), AI/agent engineering, instructional design (real credentials, not a prompt about Bloom's), motion design (the template library *is* the product's visual quality), localisation engineering, and L&D-domain product management.

**Mitigation:** hire or contract the video pipeline specialist **first** — it is the rarest skill and the load-bearing one (R1). Hire a real instructional designer early; the pedagogy layer cannot be built from a literature summary, and it's the differentiator. Motion design can start with a small excellent template set rather than a large mediocre one. Keep the team small and senior through Phase 0–1.

## R29. Scope is enormous
**Severity: Severe · Likelihood: Near-certain**

The PRD describes 12–18 months of work for a strong team. The temptation to build everything at once is the most common way products like this die.

**Mitigation:** the phase gates are real. Phase 0 has an explicit kill criterion. Phase 1 ships one video, motion graphics only, English only — resist every feature that doesn't serve the edit loop. **Phase 2 is the differentiating release** and everything before it is infrastructure for it; if you're going to run out of runway, run out *after* Phase 2, not during Phase 3.

## R30. Latency shapes the product's felt quality
**Severity: Moderate · Likelihood: Likely**

Full pipeline: agents 4–12 min + asset generation 2–10 min + render 1–5 min = potentially 20+ minutes to first video. Users read that as broken regardless of output quality.

**Mitigation:** progressive disclosure — show the objective graph in 30 s, script in 2 min, storyboard with placeholder visuals in 4 min, draft render in 8 min, final on approval. Users tolerate long waits when they can see and act on intermediate results; they don't tolerate a spinner. Parallelise everything without a true dependency. Draft-tier models for previews. **The interactive edit loop must be fast (<60 s) even if first generation is slow** — that's the loop that defines the product experience.

---

# 7. THINGS THAT COULD INVALIDATE THE THESIS

Worth naming explicitly. Each is low-to-moderate probability, high impact.

1. **A frontier model ships genuinely good long-form video with native consistency and audio.** The 8-second clip cap disappears; scene-level composition becomes less necessary. *Your response:* the course graph, memory, pedagogy and standards layers remain valuable — but the render architecture's moat shrinks considerably. Watch clip-length and consistency benchmarks quarterly as a leading indicator.
2. **HeyGen or Colossyan ships course-level continuity.** HyperFrames already gives HeyGen a deterministic declarative render layer; a course graph on top is a plausible 2–3 quarter project for them. *Your response:* speed on Wedge A, and depth in pedagogy and standards where they have less appetite.
3. **The pedagogy differentiation doesn't sell.** Buyers may simply not care, buying on price and speed instead. *Your response:* test this in Phase 1 sales conversations, not Phase 3. If P2 buyers shrug at the pedagogy report, the positioning needs to change while it's still cheap to change.
4. **Learners reject AI-generated instruction as the disclosure norm hardens.** The trust-cliff finding could generalise. *Your response:* motion graphics rather than synthetic humans; human-authored-and-reviewed framing; outcome data as the counter-argument.
5. **Video is the wrong medium.** Interactive, text-first, and conversational tutoring may prove better for many learning objectives — and cheaper. *Your response:* the course graph is medium-agnostic by construction. If video declines, the graph renders to something else. That's a real hedge, and it's worth preserving deliberately in the schema rather than by accident.

---

# 8. WHAT I'D DO DIFFERENTLY FROM YOUR BRIEF

Stated plainly, since you asked for challenges rather than agreement.

**1. Don't make avatars central.** Your brief puts significant weight on avatar training and engagement. The evidence points the other way — embodiment and voice both failed to replicate, learners over-attend to faces at the expense of graphics, and disclosure drops trust with no learning benefit. Motion graphics are cheaper ($5.43 vs $10.44 per video), more localisable, more cache-friendly, more accessible, and better supported by the research. Support avatars; don't build on them.

**2. Fewer agents, more deterministic checks.** "Many agents at each and every level" is the right instinct expressed as the wrong implementation. Deterministic rules are faster, free, more reliable and debuggable. Reserve agents for genuine judgment, and measure every verifier's catch rate against seeded errors.

**3. "AI should train itself" needs precision.** You are renting the generative models; they don't retrain. What can learn: template rankings against outcome data, per-customer style profiles, prompt libraries, a reward model over storyboard decisions, and model-routing policy. That's genuinely valuable — but say it precisely internally, or someone will build a roadmap around fine-tuning Veo.

**4. Constrain generative video hard.** Your brief wants diffusion clips available wherever needed. At $3–37/min before a 1.5–2.5× reroll multiplier, with 8-second caps and unsolved cross-shot consistency, it should be a *garnish* — hero shots and specific B-roll, gated behind an explicit cost-visible action. Not a default.

**5. Add screen capture / synthetic UI to the roadmap.** It's absent from your brief and it's the largest underserved training category — Colossyan openly can't do it. Potentially worth more than another avatar tier.

**6. Make the objective graph the first user-facing artifact.** Your flow goes intake → script → storyboard → render. Inserting *objectives* before script is the single highest-leverage change to the product: it's where errors are cheapest to fix, it's what makes P3 (the gatekeeper) trust the system, and it's what makes course memory possible at all.

**7. Ship the pedagogy report to customers.** Your brief treats quality as internal. Making it external — a scored, cited, itemised report — turns a hidden quality system into a sales asset that no competitor can match.

---

# 9. THE FIRST THREE THINGS TO DO

1. **Fund Phase 0 only.** Eight weeks, 2–3 engineers including one video-pipeline specialist. Build the chunked re-render loop with hand-authored storyboards. No AI, no UI. **The kill criterion is real.**
2. **In parallel, get three quotes**: Storyblocks partner deal, Remotion Enterprise, HeyGen volume. All three materially change the unit economics and all three take weeks to obtain.
3. **In parallel, recruit 5 design partners** — ideally three P2 content teams and two instructional designers. Show them the objective-graph-first flow and the pedagogy report concept before you build either. Their reaction in month 2 is worth more than a year of user research.

---

# 10. SUMMARY TABLES

## By severity

| ID | Risk | Severity | Likelihood |
|---|---|---|---|
| R1 | Chunked re-render architecture is hard and load-bearing | **Fatal** | Likely |
| R2 | Multi-agent pipelines produce plausible mush | Severe | Near-certain |
| R3 | Iteration cost may not survive vendor pricing | Severe | Possible |
| R4 | Quality ceiling of AI instructional content | Severe | Likely |
| R5 | Course memory doesn't scale naively | Severe | Near-certain |
| R8 | Stock media licensing | Severe | Near-certain if unaddressed |
| R14 | Instructional designers reject the product | Severe | Possible |
| R17 | Incumbents copy the architecture | Severe | Likely |
| R18 | Google/Canva bundling | Severe | Possible |
| R23 | Factual accuracy and liability | Severe | Possible |
| R24 | Voice/likeness consent; Wav2Lip licence | Severe | Possible |
| R28 | Unusual team composition required | Severe | Likely |
| R29 | Scope is enormous | Severe | Near-certain |
| R6 | Localisation timing and layout | Moderate | Near-certain |
| R7 | Model vendor volatility | Moderate | Near-certain |
| R9 | Reroll rate as hidden COGS | Moderate | Near-certain |
| R12 | Evidence base weaker than assumed | Moderate | Near-certain |
| R13 | Users want the pedagogically worse thing | Moderate | Near-certain |
| R19 | Creator churn | Moderate | Near-certain |
| R10 | Render infrastructure at scale | Moderate | Possible |
| R11 | Screen capture / software demos | Moderate | Likely |
| R15 | Demo-to-delivery gap | Moderate | Likely |
| R16 | Chat editing complexity | Moderate | Likely |
| R20 | Pricing model risk | Moderate | Possible |
| R21 | Enterprise procurement cost | Moderate | Likely |
| R22 | AI disclosure trust cliff | Moderate | Likely |
| R25 | Output provenance / copyright | Moderate | Possible |
| R26 | Accessibility as legal requirement | Moderate | Likely |
| R27 | Data residency and privacy | Moderate | Possible |
| R30 | Latency shapes felt quality | Moderate | Likely |

## Decisions that must be made before writing code

These are irreversible-in-practice. Each one, if deferred, becomes a rewrite.

| Decision | Why it can't wait |
|---|---|
| Scene graph schema is renderer-agnostic | Otherwise no engine portability, no negotiating leverage |
| Store durations, never absolute positions | Otherwise the cache is worthless |
| RationalTime, integer fps, 48 kHz | Otherwise accumulating A/V drift |
| Cues anchor to narration span IDs | Otherwise localisation and script editing are impossible |
| Component-level invalidation granularity | Otherwise coarse invalidation destroys the cache's value |
| Stable scene IDs + objectiveIds on every item | Otherwise xAPI/cmi5 identifiers can't be added without breaking historical learner data |
| Retrieval over course memory, not full injection | Otherwise every prompt in the system needs rewriting at scale |
| Caption safe area in every layout template | Otherwise a painful retrofit across the whole template library |
| No raw asset download, enforced in code | Otherwise a Storyblocks licence breach ships |
| `timingSensitivity: rigid \| elastic` in the scene schema | Otherwise the hybrid localisation strategy is unavailable |

---

*Companion document: **PRD.md**.*
