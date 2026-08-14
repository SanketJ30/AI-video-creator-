import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";

/**
 * THE R8 BOUNDARY.
 *
 * CHALLENGES R8: the scene graph is renderer-agnostic. `templates.py` describes
 * a template as a name, typed parameters and a duration band — no React, no JSX,
 * no component names, no CSS. This file is the ONLY place that turns that
 * description into pixels, and the only place that knows Remotion exists.
 *
 * Everything upstream of here — the planner, the signal designer, the linter,
 * the resolver, the manifest — deals in `{template, slots, cues}`. If a second
 * engine is ever justified (§11.5 keeps the escape hatch real) this file is what
 * gets rewritten, not the pipeline.
 *
 * ## Hermeticity (§11.3)
 *
 * No Date.now(), no Math.random(), no network fetches, no remote fonts. Motion
 * is a pure function of `frame`, which is what makes a Remotion composition
 * cacheable in the first place. Colours are literals here because no brand
 * palette exists yet (see a11y.check_contrast / week4 D6) — when Phase 5 binds
 * one it arrives through props like everything else.
 *
 * The type is deliberately loose: slots are validated in Python against the
 * template's own param schema before they ever reach this file, and duplicating
 * that schema in TypeScript would create a second source of truth.
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
  // Decided by the resolver (§11.2 phase one), carried here. Never computed
  // in this file: R1 keeps duration in one place.
  durationInFrames: number;
};

export const sceneSchemaDefaults: SceneProps = {
  template: "key_phrase",
  slots: { phrase: "placeholder" },
  cues: [],
  captionSafeBottom: 0.15,
  minFontPx: 24,
  durationInFrames: 90,
};

const INK = "#12151c";
const PAPER = "#f7f7f4";
const ACCENT = "#c8442b";
const MUTED = "#6b7280";

/** §9.2 signalling, resolved: is this cue active at this frame? */
const cueActive = (cue: Cue, seconds: number) =>
  seconds >= cue.atSeconds && seconds < cue.atSeconds + 1.2;

/** A build reveals its items in order across the scene, deterministically. */
const revealed = (index: number, count: number, progress: number) =>
  progress >= (index + 1) / (count + 1);

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

export const Scene: React.FC<SceneProps> = ({
  template,
  slots,
  cues,
  captionSafeBottom,
  minFontPx,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, height } = useVideoConfig();
  const seconds = frame / fps;
  const progress = durationInFrames > 1 ? frame / (durationInFrames - 1) : 1;

  // §16.2: the bottom 15% is a caption exclusion zone in EVERY template. It is
  // reserved here as layout, not decoration, so no template can opt out.
  const safeBottomPx = Math.round(height * captionSafeBottom);

  const active = new Set(
    cues.filter((c) => cueActive(c, seconds)).map((c) => c.target),
  );
  const isCued = (slot: string, i: number, id?: string) =>
    active.has(slot) ||
    active.has(`${slot}[${i}]`) ||
    (id ? active.has(`${slot}.${id}`) : false);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: PAPER,
        color: INK,
        // §11.3: system fonts only. A webfont is a network fetch at render time
        // and a font-loading race; both are named hermeticity failures.
        fontFamily: "Segoe UI, Helvetica, Arial, sans-serif",
        padding: 96,
        paddingBottom: safeBottomPx + 48,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
      }}
    >
      <Body
        template={template}
        slots={slots}
        progress={progress}
        minFontPx={minFontPx}
        isCued={isCued}
      />
    </AbsoluteFill>
  );
};

const Body: React.FC<{
  template: string;
  slots: Record<string, unknown>;
  progress: number;
  minFontPx: number;
  isCued: (slot: string, i: number, id?: string) => boolean;
}> = ({ template, slots, progress, minFontPx, isCued }) => {
  // §11.6 / §11.2: no size below minFontPx at 1080p. Aggressive encoding rings
  // small text, and the a11y linter enforces the same floor upstream.
  const big = Math.max(minFontPx * 3, 72);
  const mid = Math.max(minFontPx * 2, 48);
  const small = Math.max(minFontPx, 32);

  switch (template) {
    case "key_phrase":
      return (
        <div style={{ fontSize: big, fontWeight: 700, lineHeight: 1.15 }}>
          {asText(slots.phrase)}
        </div>
      );

    case "title_card":
      return (
        <div>
          <div style={{ fontSize: big, fontWeight: 700, lineHeight: 1.15 }}>
            {asText(slots.title)}
          </div>
          {asText(slots.subtitle) ? (
            <div style={{ fontSize: mid, color: MUTED, marginTop: 24 }}>
              {asText(slots.subtitle)}
            </div>
          ) : null}
        </div>
      );

    case "term_card":
      return (
        <div>
          <div style={{ fontSize: big, fontWeight: 700 }}>
            {asText(slots.term)}
          </div>
          <div style={{ fontSize: mid, color: MUTED, marginTop: 24 }}>
            {asText(slots.characteristic)}
          </div>
        </div>
      );

    case "cold_open":
      // `premise` describes the SHOT, not on-screen text (week4 D2), so it is
      // deliberately not typeset. With no asset pipeline yet the frame is held
      // plain rather than inventing text the storyboard did not ask for.
      return <div />;

    case "concept_illustration":
      return (
        <div style={{ fontSize: mid, color: MUTED }}>
          {asText(slots.caption)}
        </div>
      );

    case "table_build": {
      const cols = asList(slots.columns);
      const rows = asList(slots.rows);
      return (
        <div style={{ fontSize: small, lineHeight: 1.5 }}>
          <div style={{ display: "flex", gap: 32, fontWeight: 700, marginBottom: 16 }}>
            {cols.map((c, i) => (
              <div key={i} style={{ flex: 1 }}>{label(c)}</div>
            ))}
          </div>
          {rows.map((r, i) =>
            revealed(i, rows.length, progress) ? (
              <div
                key={i}
                style={{
                  padding: "12px 0",
                  borderTop: `2px solid ${MUTED}33`,
                  color: isCued("rows", i) ? ACCENT : INK,
                  fontWeight: isCued("rows", i) ? 700 : 400,
                }}
              >
                {label(r)}
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
            fontFamily: "Consolas, Menlo, monospace",
            fontSize: small,
            lineHeight: 1.6,
          }}
        >
          {steps.map((s, i) =>
            revealed(i, steps.length, progress) ? (
              <div key={i} style={{ color: isCued("steps", i) ? ACCENT : INK }}>
                <span style={{ color: MUTED }}>$ </span>
                {label(s)}
              </div>
            ) : null,
          )}
        </div>
      );
    }

    case "state_timeline": {
      const tracks = asList(slots.tracks);
      const steps = asList(slots.steps);
      return (
        <div style={{ fontSize: small }}>
          <div style={{ display: "flex", gap: 48, marginBottom: 32 }}>
            {tracks.map((t, i) => (
              <div
                key={i}
                style={{
                  flex: 1,
                  fontWeight: 700,
                  fontSize: mid,
                  color: isCued("tracks", i) ? ACCENT : INK,
                }}
              >
                {label(t)}
              </div>
            ))}
          </div>
          {asText(slots.invariant) ? (
            <div style={{ color: MUTED, marginBottom: 24 }}>
              {asText(slots.invariant)}
            </div>
          ) : null}
          {steps.map((s, i) =>
            revealed(i, steps.length, progress) ? (
              <div
                key={i}
                style={{
                  padding: "8px 0",
                  color: isCued("steps", i) ? ACCENT : INK,
                }}
              >
                {label(s)}
              </div>
            ) : null,
          )}
        </div>
      );
    }

    case "labelled_diagram": {
      const nodes = asList(slots.nodes);
      return (
        <div>
          {asText(slots.title) ? (
            <div style={{ fontSize: mid, fontWeight: 700, marginBottom: 32 }}>
              {asText(slots.title)}
            </div>
          ) : null}
          <div style={{ display: "flex", gap: 48, flexWrap: "wrap" }}>
            {nodes.map((n, i) => {
              const id =
                n && typeof n === "object"
                  ? asText((n as Record<string, unknown>).id)
                  : undefined;
              return revealed(i, nodes.length, progress) ? (
                <div
                  key={i}
                  style={{
                    fontSize: mid,
                    padding: "24px 32px",
                    border: `4px solid ${isCued("nodes", i, id) ? ACCENT : INK}`,
                    borderRadius: 12,
                    color: isCued("nodes", i, id) ? ACCENT : INK,
                  }}
                >
                  {label(n)}
                </div>
              ) : null;
            })}
          </div>
        </div>
      );
    }

    case "series_build": {
      const series = asList(slots.series);
      return (
        <div style={{ fontSize: small }}>
          {asText(slots.title) ? (
            <div style={{ fontSize: mid, fontWeight: 700, marginBottom: 32 }}>
              {asText(slots.title)}
            </div>
          ) : null}
          {series.map((s, i) =>
            revealed(i, series.length, progress) ? (
              <div key={i} style={{ padding: "10px 0" }}>{label(s)}</div>
            ) : null,
          )}
        </div>
      );
    }

    case "ui_walkthrough": {
      const steps = asList(slots.steps);
      return (
        <div style={{ fontSize: small, lineHeight: 1.6 }}>
          {steps.map((s, i) =>
            revealed(i, steps.length, progress) ? (
              <div key={i} style={{ padding: "8px 0" }}>
                {i + 1}. {label(s)}
              </div>
            ) : null,
          )}
        </div>
      );
    }

    default:
      // An unknown template must be loud, not blank: a silently empty scene is
      // one nobody notices until the whole video is assembled.
      return (
        <div style={{ fontSize: mid, color: ACCENT, fontWeight: 700 }}>
          UNKNOWN TEMPLATE: {template}
        </div>
      );
  }
};
