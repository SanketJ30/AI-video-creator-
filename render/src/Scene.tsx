import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import {
  canvas, color, columns, contentHeight, contentLeft, contentTop, contentWidth,
  font, motion, space, type as typeScale,
} from "./tokens";
import {
  build, focusAmount, focusScale, mix, reveal, resolveAmount, started,
} from "./motion";

/**
 * THE R8 BOUNDARY, and the design system's only implementation.
 *
 * CHALLENGES R8: the scene graph is renderer-agnostic. `templates.py` describes
 * a template as a name, typed parameters and a duration band — no React, no JSX,
 * no component names, no CSS. This file is the ONLY place that turns that
 * description into pixels, and the only place that knows Remotion exists.
 *
 * Layouts follow `docs/design/video-design-system.md` §9, section by section.
 * Colour, size, space and motion come from `tokens.ts` (§3–§6, §10–§11); there
 * are no literals here and a test enforces that.
 *
 * ## Which templates §9 actually designs
 *
 * §9 designs SIX: cold_open, title_card, key_phrase, state_timeline,
 * table_build, concept_illustration. The registry holds ELEVEN. The other five
 * — labelled_diagram, term_card, series_build, terminal_replay, ui_walkthrough —
 * are rendered here from the token layer so they remain usable and legible, but
 * they have no design section. That gap is recorded as ISSUE-20 rather than
 * papered over: inventing a seventh layout language here is exactly the "six
 * unrelated motion-graphics templates" outcome §0 warns against.
 *
 * ## Hermeticity (§11.3)
 *
 * No Date.now(), no Math.random(), no network fetches. Motion is a pure
 * function of `frame`, which is what makes a Remotion composition cacheable.
 * The webfont is pinned in `fonts.ts` before any frame paints.
 */

type Cue = {
  kind: string;
  target: string;
  atSeconds: number;
  params?: Record<string, unknown>;
};

type SceneProps = {
  template: string;
  slots: Record<string, unknown>;
  cues: Cue[];
  captionSafeBottom: number;
  minFontPx: number;
  durationInFrames: number;
  /**
   * §3's semantic role for the WHOLE scene, decided by the visual planner from
   * the narration and the Gagné slot (ISSUE-21).
   *
   * The renderer previously inferred this from layout structure — `highlight_row`
   * meant "answer", the last step of a timeline meant "resolution". Both were
   * the renderer deciding pedagogy from shape, and once a producer exists they
   * are wrong even when they look right. Removed.
   */
  resolutionState: "neutral" | "broken" | "caution" | "resolved";
};

export const sceneSchemaDefaults: SceneProps = {
  template: "key_phrase",
  slots: { phrase: "placeholder" },
  cues: [],
  captionSafeBottom: 0.15,
  minFontPx: 24,
  durationInFrames: 90,
  resolutionState: "neutral",
};

// ------------------------------------------------------------- helpers

const asList = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const asText = (v: unknown): string => (typeof v === "string" ? v : "");

const label = (item: unknown): string => {
  if (typeof item === "string") return item;
  if (item && typeof item === "object") {
    const o = item as Record<string, unknown>;
    return asText(o.label) || asText(o.text) || asText(o.detail) || "";
  }
  return "";
};

const cells = (row: unknown): string[] => {
  const c = (row as Record<string, unknown>)?.cells;
  return Array.isArray(c) ? c.map((x) => asText(x)) : [];
};

/**
 * §3: an emphasised text element moves toward the signal role — "look here".
 *
 * CONTINUOUS, not boolean. The previous version took `isCued()` and switched
 * colour in one frame, which collapsed §10.3's 340 ms rise into a step — the
 * strobe. `amount` comes from `focusAmount`.
 */
const emphasis = (amount: number, to: string = color.signal): React.CSSProperties =>
  amount <= 0.001
    ? {}
    : { color: mix(color.ink, to, amount) };

/**
 * §3's roles for a scene-level state. `signal` is deliberately absent: it is the
 * CUE-level role meaning "currently being discussed", and a scene does not have
 * a "being discussed" state — every scene is being discussed.
 */
const STATE_INK: Record<string, string> = {
  broken: color.error,
  caution: color.warning,
  resolved: color.answer,
};
const STATE_SURFACE: Record<string, string> = {
  broken: color.errorSoft,
  caution: color.warningSoft,
  resolved: color.answerSoft,
};

/**
 * WHEN a scene's state appears, decided by what the role MEANS.
 *
 * A single default was wrong, and s04 is the case that proves it: a 74.5 s scene
 * whose subject is an invariant being violated read `broken` only for its last
 * 7.4 s, because every state was driven by §10.4's RESOLVE progress of 0.9.
 *
 * `broken` and `caution` are CONDITIONS that hold for the scene — the invariant
 * is violated for the whole of s04, not at the end of it. `resolved` is an
 * ARRIVAL, and a late reveal is exactly what §10.4 describes: "transition from
 * neutral/signal to answer state". So the verb still fits `resolved`; it never
 * fitted the other two.
 *
 * 0.15 rather than 0: the state should land after the scene's opening REVEAL
 * has settled, so the frame is not already tinted before anything is on it.
 */
const STATE_ONSET: Record<string, number> = {
  broken: 0.15,
  caution: 0.15,
  resolved: 0.9,
};

// ------------------------------------------------------------ the shell

export const Scene: React.FC<SceneProps> = ({
  template,
  slots,
  cues,
  captionSafeBottom,
  minFontPx,
  resolutionState,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, height } = useVideoConfig();
  const seconds = frame / fps;
  const safeBottomPx = Math.round(height * captionSafeBottom);

  // §10.3 FOCUS. The cue's TIME came from the resolver, which computed it from
  // the cue's span anchor (R3); this only shapes the moment around it. A
  // target's focus is the strongest of the cues pointing at it.
  const ordered = [...cues].sort((a, b) => a.atSeconds - b.atSeconds);
  const motionFocusSeconds = motion.focus.ms / 1000;
  const focusOf = (target: string): number =>
    ordered.reduce((best, c, i) => {
      if (c.target !== target) return best;
      // §8: one dominant visual question. Emphasis persists until a LATER cue
      // takes over, then decays — attention MOVES rather than blinking off.
      //
      // STRICTLY later, and later than the END of this cue's rise (ISSUE-23).
      // Two cues anchored to the SAME span is the signal designer's normal
      // output whenever one sentence carries two signals — s09 has exactly
      // that — and without this guard `release === rise start`, which makes
      // focusAmount's input range [t, t+rise, t, t+rise]. That is not
      // monotonically increasing and `interpolate` promises nothing about it;
      // measured, it snapped the phrase's colour over the scene's last two
      // frames. A cue that does not supersede this one leaves it persisting,
      // which is the `null` branch and the correct reading of §8.
      const riseEnd = c.atSeconds + motionFocusSeconds;
      const next = ordered
        .slice(i + 1)
        .find((n) => n.target !== target && n.atSeconds > riseEnd);
      return Math.max(
        best,
        focusAmount(seconds, c.atSeconds, next ? next.atSeconds : null),
      );
    }, 0);
  const cueFocus = (slot: string, i: number, id?: string): number =>
    Math.max(
      focusOf(slot),
      focusOf(`${slot}[${i}]`),
      id ? focusOf(`${slot}.${id}`) : 0,
    );
  const isCued = (slot: string, i: number, id?: string) =>
    cueFocus(slot, i, id) > 0.01;

  /*
    §13 NARRATION SYNCHRONISATION, using the anchors that already exist.

    §14's disclosure order is proportional to scene duration, but §9.2's cues
    are anchored to SPANS — the narration. Those two clocks disagree, and the
    disagreement is visible: on a 4-row table over 120 frames, row 3 is
    disclosed at 3.2 s while a cue anchored to a word spoken at 2.0 s fires on
    it 1.2 s EARLIER. The renderer would emphasise a row that is not on screen.

    §13: "The visual corresponding to a spoken idea should be visible when that
    idea is being explained, not several seconds before or after." So when the
    narration reaches an element, that element is disclosed — the spoken time
    wins over the proportional one, because the spoken time is the one anchored
    to meaning.
  */
  const cueStartOf = (target: string): number | null =>
    cues.reduce<number | null>(
      (best, c) =>
        c.target === target && (best === null || c.atSeconds < best)
          ? c.atSeconds
          : best,
      null,
    );
  const narrationReached = (slot: string, i: number, id?: string): boolean =>
    [slot, `${slot}[${i}]`, id ? `${slot}.${id}` : ""]
      .filter(Boolean)
      .some((target) => {
        const at = cueStartOf(target);
        return at !== null && seconds >= at;
      });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: color.surface,
        color: color.ink,
        fontFamily: font.sans,
      }}
    >
      {/*
        §10.4 RESOLVE at scene level.

        §3 gives `answerSoft`, `warningSoft` and `errorSoft` explicitly as
        CONTAINER colours — "Answer/resolution container", "Error container".
        A scene that is showing a state says so with its container, which is
        what those tokens are for, and no element has to be singled out.

        Fades in over §10.4's band near the end of the scene: "transition from
        neutral/signal to answer state ... supporting content settles."
      */}
      {resolutionState !== "neutral" ? (
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            right: 0,
            bottom: safeBottomPx,
            backgroundColor: STATE_SURFACE[resolutionState],
            borderLeft: `${space.xs}px solid ${STATE_INK[resolutionState]}`,
            opacity: resolveAmount(frame, fps, durationInFrames,
                                   STATE_ONSET[resolutionState]),
          }}
        />
      ) : null}

      {/*
        §4's safe content region. Absolutely positioned rather than padding on a
        centred flex column: a centred column with one short child centres that
        child and leaves the rest of the frame dead, which was ISSUE-17. Each
        template owns its vertical anchor inside this box.
      */}
      <div
        style={{
          position: "absolute",
          left: contentLeft,
          top: contentTop,
          width: contentWidth,
          height: contentHeight,
        }}
      >
        <Body
          template={template}
          slots={slots}
          minFontPx={minFontPx}
          isCued={isCued}
          cueFocus={cueFocus}
          narrationReached={narrationReached}
          frame={frame}
          fps={fps}
          durationInFrames={durationInFrames}
        />
      </div>

      {/* §16.2's caption exclusion zone, reserved as layout. */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: safeBottomPx,
        }}
      />
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------ the layouts

const Body: React.FC<{
  template: string;
  slots: Record<string, unknown>;
  minFontPx: number;
  isCued: (slot: string, i: number, id?: string) => boolean;
  cueFocus: (slot: string, i: number, id?: string) => number;
  narrationReached: (slot: string, i: number, id?: string) => boolean;
  frame: number;
  fps: number;
  durationInFrames: number;
}> = ({
  template, slots, minFontPx, isCued, cueFocus, narrationReached, frame, fps,
  durationInFrames,
}) => {
  const t = typeScale;
  // §6's floor, clamping UP only. Nothing here shrinks to fit: when copy
  // overflows, `linter.check_type_fits` blocks and names §6's four remedies.
  const px = (r: { size: number }) => Math.max(r.size, minFontPx);

  // §12's hierarchy, as three helpers so a component cannot accidentally
  // animate a divider (level 1 gets nothing).
  /** §12 level 2 — content entering. */
  const enter = (order = 0) => reveal(frame, fps, order * 6);
  /** §12 level 2 — content being constructed, one item at a time (§10.2). */
  const buildStep = (i: number, n: number) =>
    build(frame, fps, i, n, durationInFrames);
  /**
   * §14 — has item i been disclosed yet?
   *
   * Either the scene has progressed past its share (§14's proportional
   * disclosure) OR the narration has reached it (§13). The second is what
   * stops a cue emphasising an element that is not on screen.
   */
  const shown = (i: number, n: number, slot?: string) =>
    started(frame, i, n, durationInFrames) ||
    (slot ? narrationReached(slot, i) : false);
  // The scene's RESOLVE amount is applied once, at scene level, on the state
  // container above — the two locals that used to live here fed the removed
  // `highlight_row`-means-answer guess (ISSUE-21) and were left behind. One of
  // them was `resolveAmt > 0.5`, which is exactly the boolean-over-a-continuous-
  // amount shape that ISSUE-22 was.

  switch (template) {
    // ================================================== §9.1 cold_open
    //
    // "Use a strong left-aligned composition ... Vertical center around
    // 42–48% ... Do not center the sentence vertically by default. The current
    // centered approach creates dead space beneath the content."
    case "cold_open": {
      const supporting = asText(slots.premise_line);
      return (
        <div
          style={{
            position: "absolute",
            // §9.1: content starts around x = 120–160 in frame terms. The
            // content region already begins at 96, so a 32 inset lands at 128.
            left: space.lg,
            // §9.1's 42–48% optical centre, measured on the frame and
            // expressed against the content box.
            top: canvas.height * 0.44 - contentTop,
            width: columns(9),
            transform: "translateY(-50%)",
          }}
        >
          {asText(slots.module_label) ? (
            <div
              style={{
                fontSize: px(t.label),
                fontWeight: t.label.weight,
                letterSpacing: 2,
                color: color.signal,
                marginBottom: space.md,
              }}
            >
              {asText(slots.module_label).toUpperCase()}
            </div>
          ) : null}

          <div
            style={{
              fontSize: px(t.display),
              fontWeight: t.display.weight,
              lineHeight: t.display.line,
              ...enter(1),
              ...emphasis(cueFocus("headline", 0)),
            }}
          >
            {asText(slots.headline)}
          </div>

          {supporting ? (
            <div
              style={{
                fontSize: px(t.body),
                fontWeight: t.body.weight,
                color: color.inkMuted,
                marginTop: space.lg,
              }}
            >
              {supporting}
            </div>
          ) : null}
        </div>
      );
    }

    // ================================================= §9.2 title_card
    //
    // "Top-left anchored ... Do not vertically center title cards."
    case "title_card":
      return (
        <div style={{ width: columns(11) }}>
          {asText(slots.module_label) ? (
            <div
              style={{
                fontSize: px(t.label),
                fontWeight: t.label.weight,
                letterSpacing: 2,
                color: color.signal,
                marginBottom: space.md,
              }}
            >
              {asText(slots.module_label).toUpperCase()}
            </div>
          ) : null}
          <div
            style={{
              fontSize: px(t.h1),
              fontWeight: t.h1.weight,
              lineHeight: t.h1.line,
              ...enter(1),
              ...emphasis(cueFocus("title", 0)),
            }}
          >
            {asText(slots.title)}
          </div>
          {asText(slots.subtitle) ? (
            <div
              style={{
                fontSize: px(t.body),
                fontWeight: t.body.weight,
                lineHeight: t.body.line,
                color: color.inkMuted,
                marginTop: space.md,
                width: columns(9),
                ...emphasis(cueFocus("subtitle", 0)),
              }}
            >
              {asText(slots.subtitle)}
            </div>
          ) : null}
        </div>
      );

    // ================================================= §9.3 key_phrase
    //
    // "Use a large left-aligned text block ... 10 columns maximum ... Do not
    // put the sentence in a giant centered box."
    //
    // The emphasis line is §9.3's resolution — "the second clause becomes the
    // resolution" — so when cued it takes the ANSWER role, not signal. That is
    // §3's distinction doing real work: the phrase is what is being discussed,
    // the emphasis is what it resolves to.
    case "key_phrase":
      return (
        <div
          style={{
            position: "absolute",
            top: contentHeight * 0.32,
            width: columns(10),
          }}
        >
          <div
            style={{
              fontSize: px(t.display),
              fontWeight: t.display.weight,
              lineHeight: t.display.line,
              ...enter(0),
              ...emphasis(cueFocus("phrase", 0)),
            }}
          >
            {asText(slots.phrase)}
          </div>
          {asText(slots.emphasis) ? (
            <div
              style={{
                fontSize: px(t.h2),
                fontWeight: t.h2.weight,
                // §9.3 says this slot IS the resolution, and the template used
                // to act on that by colouring a cued emphasis green. That was
                // template-level pedagogy — the same class of inference as
                // `highlight_row` meaning "answer", one level down.
                //
                // Replaced, not supplemented: emphasis takes the CUE-level
                // signal role ("look here"), and whether the scene is showing a
                // resolved state is `resolutionState`'s job. A key_phrase whose
                // clause is a caveat rather than an answer now reads correctly,
                // which it could not before.
                color:
                  cueFocus("emphasis", 0) > 0.001
                    ? mix(color.inkMuted, color.signal, cueFocus("emphasis", 0))
                    : color.inkMuted,
                marginTop: space.lg,
              }}
            >
              {asText(slots.emphasis)}
            </div>
          ) : null}
        </div>
      );

    // ============================================== §9.4 state_timeline
    //
    // "For parallel processes, use two horizontal lanes ... The lanes must have
    // a visible relationship ... 'two lanes but no visual language
    // distinguishing them' should be fixed by giving each lane: a persistent
    // label, distinct position, shared timeline, clear relationship markers.
    // Do not solve parallelism with different colors alone."
    //
    // Each lane gets a persistent label, its own baseline, and numbered markers
    // on a SHARED horizontal time axis — step n sits at the same x in every
    // lane, which is what makes the parallelism readable rather than decorative.
    case "state_timeline": {
      const tracks = asList(slots.tracks).map(label);
      const steps = asList(slots.steps);
      const laneOf = (step: unknown) => {
        const name = label((step as Record<string, unknown>)?.track);
        const i = tracks.indexOf(name);
        return i < 0 ? 0 : i;
      };
      const stepCount = Math.max(1, steps.length);
      const axisLeft = columns(2) + space.md;
      const axisWidth = contentWidth - axisLeft;
      const xOf = (i: number) => axisLeft + (axisWidth * (i + 0.5)) / stepCount;

      return (
        <div style={{ position: "relative", width: "100%", height: "100%" }}>
          {asText(slots.invariant) ? (
            <div
              style={{
                display: "inline-block",
                padding: `${space.xs}px ${space.md}px`,
                borderRadius: 8,
                border: `1px solid ${color.signalBorder}`,
                // Bg-Hover tier, not Bg — see the note on `surfaceSignalHover`.
                backgroundColor: color.surfaceSignalHover,
                color: color.ink,
                fontSize: px(t.bodyStrong),
                fontWeight: t.bodyStrong.weight,
                marginBottom: space.lg,
              }}
            >
              {asText(slots.invariant)}
            </div>
          ) : null}

          {/*
            Lanes share the remaining height rather than taking a fixed 160px
            each, which left the bottom half of the frame empty (ISSUE-17). Two
            lanes fill the region; five lanes compress evenly.
          */}
          {tracks.map((track, lane) => (
            <div
              key={lane}
              style={{
                position: "relative",
                height: `${100 / Math.max(1, tracks.length)}%`,
              }}
            >
              {/* persistent lane label — §9.4's "lane language" */}
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  top: "50%",
                  transform: "translateY(-50%)",
                  width: columns(2),
                  fontSize: px(t.label),
                  fontWeight: t.label.weight,
                  letterSpacing: 2,
                  color: mix(color.inkMuted, color.signal,
                             cueFocus("tracks", lane)),
                }}
              >
                {track.toUpperCase()}
              </div>

              {/* the lane's own baseline — structure, §12 level 1 */}
              <div
                style={{
                  position: "absolute",
                  left: axisLeft,
                  right: 0,
                  top: "50%",
                  height: 2,
                  backgroundColor: color.structure,
                }}
              />

              {steps.map((st, i) => {
                if (laneOf(st) !== lane) return null;
                if (!shown(i, steps.length, "steps")) return null;
                const stepFocus = cueFocus("steps", i);
                // §9.4: "The active state is blue." The last step is NOT
                // assumed to be the resolution — that was the renderer
                // inferring pedagogy from position, and `resolutionState` is
                // the producer now (ISSUE-21).
                const marker = mix(color.structure, color.signal, stepFocus);
                // CONTINUOUS. `filled = stepFocus > 0.5` flipped the chip's
                // fill and its numeral at the midpoint of §10.3's rise — 86 px
                // switching in one frame, the same defect as the strobe one
                // level down. The chip now fills as the focus arrives.
                const chipFill = mix(color.surface, marker, stepFocus);
                const chipInk = mix(color.inkMuted, color.surface, stepFocus);
                return (
                  <div
                    key={i}
                    style={{
                      position: "absolute",
                      left: xOf(i),
                      // Centred on the lane's own baseline, so two lanes fill
                      // the region instead of hugging its top edge.
                      top: "50%",
                      marginTop: -space.lg,
                      // Wide enough that a short label does not wrap mid-phrase.
                      width: (axisWidth / stepCount) * 1.6,
                      ...buildStep(i, steps.length),
                      transform: `translateX(-50%) scale(${focusScale(stepFocus)})`,
                    }}
                  >
                    <div
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: 10,
                        backgroundColor: chipFill,
                        border: `2px solid ${marker}`,
                        color: chipInk,
                        fontSize: px(t.label),
                        fontWeight: t.label.weight,
                        textAlign: "center",
                        lineHeight: "32px",
                        margin: "0 auto",
                      }}
                    >
                      {i + 1}
                    </div>
                    <div
                      style={{
                        marginTop: space.xs,
                        fontSize: px(t.body),
                        lineHeight: t.body.line,
                        textAlign: "center",
                        ...emphasis(stepFocus),
                      }}
                    >
                      {label(st)}
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      );
    }

    // ================================================ §9.5 table_build
    //
    // "Header #FAFAFA, text #262626, border #D9D9D9, radius 8. Rows white,
    // subtle divider, selected/current row #F5FAFF, active signal #148AFF."
    //
    // "When a new row enters, old rows stay stable." And on cell emphasis:
    // "row receives soft blue background, relevant cell receives signal
    // emphasis. Do not color the entire table blue."
    case "table_build": {
      const cols = asList(slots.columns).map(label);
      const rows = asList(slots.rows);
      const grid = `repeat(${Math.max(1, cols.length)}, 1fr)`;
      // `highlight_row` is a LAYOUT hint — which row the scene is about. It is
      // no longer read as "this row is the answer": that was the renderer
      // deciding pedagogy from structure, and `resolutionState` is the producer
      // now (ISSUE-21).
      return (
        <div style={{ width: "100%", fontSize: px(t.body) }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: grid,
              gap: `0 ${canvas.gutter}px`,
              backgroundColor: color.surfaceSubtle,
              border: `1px solid ${color.structure}`,
              borderRadius: 8,
              padding: `${space.sm}px ${space.md}px`,
              fontSize: px(t.label),
              fontWeight: t.label.weight,
              letterSpacing: 2,
              color: color.ink,
            }}
          >
            {cols.map((c, i) => (
              <div key={i}>{c.toUpperCase()}</div>
            ))}
          </div>

          {rows.map((r, i) => {
            if (!shown(i, rows.length, "rows")) return null;
            const rowFocus = cueFocus("rows", i);

            return (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: grid,
                  gap: `0 ${canvas.gutter}px`,
                  padding: `${space.md}px`,
                  borderBottom: `1px solid ${color.structureSubtle}`,
                  // §9.5: the current row takes the soft signal surface; the
                  // resolved row takes the answer surface — §3's distinction.
                  backgroundColor:
                    rowFocus > 0.001
                      ? mix(color.surface, color.surfaceSignalHover, rowFocus)
                      : color.surface,
                  lineHeight: t.body.line,
                  ...buildStep(i, rows.length),
                }}
              >
                {cells(r).map((c, j) => (
                  <div
                    key={j}
                    style={{
                      // Only the leading cell takes the accent, not the whole
                      // table — §9.5: "Do not color the entire table blue."
                      color:
                        j === 0 && rowFocus > 0.001
                          ? mix(color.ink, color.signal, rowFocus)
                          : color.ink,
                      // WEIGHT IS NOT AN EMPHASIS CHANNEL HERE. §9.5 states the
                      // treatment as colour — "row receives soft blue
                      // background, relevant cell receives signal emphasis" —
                      // and weight is the one property that cannot interpolate:
                      // 400 and 600 are different glyphs, so a cued row
                      // un-bolds in a single frame when the focus decays. Seen
                      // on the finished video at s05 and s07, ~1000 px changing
                      // at once with identical colours before and after.
                      fontWeight: t.body.weight,
                    }}
                  >
                    {c}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      );
    }

    // ========================================= §9.6 concept_illustration
    //
    // "Typographic/diagrammatic only. External imagery is optional and
    // future-facing." §0 closes ISSUE-15 here: the asset slot stays
    // architecturally optional and the template draws cards, connectors and
    // numbered markers from the design system instead of waiting for stock.
    //
    // §9.6's example is a vertical flow: RAW DATA → FEATURES → MODEL → …
    case "concept_illustration": {
      const steps = asList(slots.steps).map(label);
      const caption = asText(slots.caption);
      const flow = steps.length ? steps : caption ? [caption] : [];
      const heading = steps.length ? caption : "";
      return (
        <div style={{ width: columns(8) }}>
          {heading ? (
            <div
              style={{
                fontSize: px(t.h2),
                fontWeight: t.h2.weight,
                marginBottom: space.lg,
                ...emphasis(cueFocus("caption", 0)),
              }}
            >
              {heading}
            </div>
          ) : null}

          {flow.map((node, i) => {
            if (!shown(i, flow.length, "steps")) return null;
            // CONTINUOUS. This single boolean drove FIVE properties — card
            // border, card surface, marker fill, marker numeral and label ink —
            // and flipped all of them together in one frame: 6510 sampled
            // pixels, 5% of the frame, measured on the finished video. It was
            // the strobe defect surviving one level below `emphasis()`.
            const f = Math.max(cueFocus("steps", i), cueFocus("caption", i));
            const isLast = i === flow.length - 1;
            return (
              <div key={i}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: space.md,
                    padding: `${space.md}px`,
                    borderRadius: 10,
                    border: `1px solid ${mix(color.structure, color.signalBorder, f)}`,
                    backgroundColor: mix(color.surface, color.surfaceSignalHover, f),
                    ...buildStep(i, flow.length),
                  }}
                >
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: 8,
                      backgroundColor: mix(color.surfaceSubtle, color.signal, f),
                      color: mix(color.inkMuted, color.surface, f),
                      fontSize: px(t.label),
                      fontWeight: t.label.weight,
                      textAlign: "center",
                      lineHeight: "32px",
                    }}
                  >
                    {i + 1}
                  </div>
                  <div
                    style={{
                      fontSize: px(t.h3),
                      fontWeight: t.h3.weight,
                      ...emphasis(f),
                    }}
                  >
                    {node}
                  </div>
                </div>
                {/* §9.6's connector, at structural weight (§12 level 1) */}
                {!isLast ? (
                  <div
                    style={{
                      width: 2,
                      height: space.md,
                      backgroundColor: color.structure,
                      marginLeft: space.lg,
                    }}
                  />
                ) : null}
              </div>
            );
          })}
        </div>
      );
    }

    // ==================================================================
    // Templates the design system does NOT cover — ISSUE-20.
    //
    // §9 designs six; the registry holds eleven. These five render from the
    // token layer so they stay usable and legible, but they have no design
    // section, and inventing one here would produce exactly the "six unrelated
    // motion-graphics templates" outcome §0 warns against.
    // ==================================================================

    case "term_card":
      return (
        <div style={{ width: columns(9) }}>
          <div
            style={{
              fontSize: px(t.h1),
              fontWeight: t.h1.weight,
              ...emphasis(cueFocus("term", 0)),
            }}
          >
            {asText(slots.term)}
          </div>
          <div
            style={{
              fontSize: px(t.body),
              color: color.inkMuted,
              marginTop: space.md,
              ...emphasis(cueFocus("characteristic", 0)),
            }}
          >
            {asText(slots.characteristic)}
          </div>
        </div>
      );

    case "labelled_diagram": {
      const nodes = asList(slots.nodes);
      return (
        <div style={{ width: "100%" }}>
          {asText(slots.title) ? (
            <div
              style={{
                fontSize: px(t.h2),
                fontWeight: t.h2.weight,
                marginBottom: space.lg,
              }}
            >
              {asText(slots.title)}
            </div>
          ) : null}
          <div style={{ display: "flex", gap: space.md, flexWrap: "wrap" }}>
            {nodes.map((n, i) => {
              if (!shown(i, nodes.length, "nodes")) return null;
              const id = asText((n as Record<string, unknown>)?.id);
              const f = cueFocus("nodes", i, id);
              return (
                <div
                  key={i}
                  style={{
                    fontSize: px(t.h3),
                    fontWeight: t.h3.weight,
                    padding: `${space.md}px ${space.lg}px`,
                    border: `1px solid ${mix(color.structure, color.signalBorder, f)}`,
                    backgroundColor: mix(color.surface, color.surfaceSignalHover, f),
                    borderRadius: 10,
                    ...emphasis(f),
                    ...buildStep(i, nodes.length),
                  }}
                >
                  {label(n)}
                </div>
              );
            })}
          </div>
        </div>
      );
    }

    case "series_build": {
      const series = asList(slots.series);
      return (
        <div style={{ width: columns(10) }}>
          {asText(slots.title) ? (
            <div
              style={{
                fontSize: px(t.h2),
                fontWeight: t.h2.weight,
                marginBottom: space.lg,
              }}
            >
              {asText(slots.title)}
            </div>
          ) : null}
          {series.map((s, i) =>
            shown(i, series.length, "series") ? (
              <div
                key={i}
                style={{
                  fontSize: px(t.body),
                  padding: `${space.xs}px 0`,
                  borderBottom: `1px solid ${color.structureSubtle}`,
                  ...emphasis(cueFocus("series", i)),
                }}
              >
                {label(s)}
              </div>
            ) : null,
          )}
        </div>
      );
    }

    case "terminal_replay": {
      const steps = asList(slots.steps);
      return (
        <div
          style={{
            width: columns(10),
            padding: `${space.md}px`,
            borderRadius: 10,
            border: `1px solid ${color.structure}`,
            backgroundColor: color.surfaceSubtle,
          }}
        >
          {steps.map((s, i) =>
            shown(i, steps.length, "steps") ? (
              <div
                key={i}
                style={{
                  fontFamily: font.mono,
                  fontSize: px(t.mono),
                  lineHeight: t.mono.line,
                  // §17: highlight only the relevant line.
                  ...emphasis(cueFocus("steps", i)),
                }}
              >
                <span style={{ color: color.inkSubtle }}>$ </span>
                {label(s)}
              </div>
            ) : null,
          )}
        </div>
      );
    }

    case "ui_walkthrough": {
      const steps = asList(slots.steps);
      return (
        <div style={{ width: columns(9) }}>
          {steps.map((s, i) =>
            shown(i, steps.length, "steps") ? (
              <div
                key={i}
                style={{
                  fontSize: px(t.body),
                  padding: `${space.xs}px 0`,
                  ...emphasis(cueFocus("steps", i)),
                }}
              >
                {i + 1}. {label(s)}
              </div>
            ) : null,
          )}
        </div>
      );
    }

    default:
      // An unknown template must be loud, not blank: a silently empty scene is
      // one nobody notices until the whole video is assembled. §3's error role
      // is what "this is broken" looks like.
      return (
        <div
          style={{
            fontSize: px(t.h2),
            color: color.error,
            fontWeight: t.h2.weight,
          }}
        >
          UNKNOWN TEMPLATE: {template}
        </div>
      );
  }
};
