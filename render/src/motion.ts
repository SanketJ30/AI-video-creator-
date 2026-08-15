import { Easing, interpolate } from "remotion";
import { EASE, MAX_FOCUS_SCALE, motion } from "./tokens";

/**
 * THE MOTION GRAMMAR — design system §10–§12.
 *
 * §10: "The renderer should not have dozens of unrelated animation presets.
 * Use a small motion vocabulary." Five verbs, each with the duration band §10
 * gives and the easing §11 describes.
 *
 *   REVEAL      information entering                 300–500 ms
 *   BUILD       information being constructed        400–700 ms
 *   FOCUS       attention onto something visible     250–450 ms
 *   RESOLVE     the lesson reaching its answer       400–700 ms
 *   TRANSITION  between concepts                     — see below
 *
 * ## Why this is not a second timing system
 *
 * Cues already resolve from span anchors to concrete local times in
 * `resolver.resolve_cue` (R3): the pipeline decides WHEN a signal fires from
 * the narration, before anything renders. This module decides only what the
 * moment LOOKS like — the shape of the 340 ms around a time that was already
 * computed. It never chooses a time of its own.
 *
 * That division is the point. A renderer that picked its own cue times would
 * be a second opinion about narration synchronisation (§13), and the first
 * opinion is the one anchored to the words.
 *
 * ## TRANSITION is deliberately absent from this file
 *
 * §10.5's TRANSITION operates BETWEEN concepts, which in this pipeline means
 * between scenes — and §11.4 of the PRD makes that a hard cut by default,
 * modelled as a first-class node in `assembly.Transition` with its own cache
 * key. Implementing a within-scene crossfade here would put transitions in two
 * places. The verb exists in the token file so its duration is recorded; the
 * mechanism lives in assembly.
 *
 * ## §12's motion hierarchy
 *
 * Level 1 structural (grids, dividers, baselines, card borders) gets no
 * animation at all. Level 2 content gets REVEAL or BUILD. Level 3 attention
 * gets FOCUS. Level 4 resolution gets RESOLVE, the strongest emphasis. The
 * helpers below are named for the level they serve so a component cannot
 * accidentally animate a divider.
 */

const easing = Easing.bezier(EASE[0], EASE[1], EASE[2], EASE[3]);

/** Frames a duration in milliseconds occupies at this fps. */
const frames = (ms: number, fps: number) => Math.max(1, (ms / 1000) * fps);

/**
 * §10.1 REVEAL — "slight upward movement, opacity increase, no bounce, no
 * overshoot". For an element that simply enters.
 */
export const reveal = (
  frame: number,
  fps: number,
  startFrame = 0,
): React.CSSProperties => {
  const t = interpolate(
    frame,
    [startFrame, startFrame + frames(motion.reveal.ms, fps)],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing },
  );
  return {
    opacity: t,
    transform: `translateY(${(1 - t) * motion.reveal.shiftPx}px)`,
  };
};

/**
 * §10.2 BUILD — "new element enters, previous elements remain stable".
 *
 * `index` of `count` items across a scene of `durationInFrames`. The start is
 * the same fraction §14's progressive disclosure uses, so the build and the
 * disclosure order cannot disagree.
 */
export const build = (
  frame: number,
  fps: number,
  index: number,
  count: number,
  durationInFrames: number,
): React.CSSProperties => {
  const start = ((index + 1) / (count + 1)) * durationInFrames;
  const t = interpolate(
    frame,
    [start, start + frames(motion.build.ms, fps)],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing },
  );
  return {
    opacity: t,
    transform: `translateY(${(1 - t) * motion.build.shiftPx}px)`,
  };
};

/** Has this build-step started? §14: previously revealed items stay revealed. */
export const started = (
  frame: number,
  index: number,
  count: number,
  durationInFrames: number,
) => frame >= ((index + 1) / (count + 1)) * durationInFrames;

/**
 * §10.3 FOCUS — how strongly a cue is emphasising, 0..1.
 *
 * Rises over the focus duration, holds, and falls back. §10.3: "surrounding
 * content does not disappear", and "avoid pulsing continuously" — so this is
 * one pass, not an oscillation.
 *
 * `atSeconds` comes from the resolver, which computed it from the cue's span
 * anchor. This function does not choose it.
 */
export const focusAmount = (
  seconds: number,
  atSeconds: number,
  holdSeconds = 1.2,
): number => {
  const rise = motion.focus.ms / 1000;
  return interpolate(
    seconds,
    [atSeconds, atSeconds + rise, atSeconds + holdSeconds,
     atSeconds + holdSeconds + rise],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing },
  );
};

/**
 * §10.3's optional scale, "only 1–3%".
 *
 * The PRD's §9.2 permits a `scale_pulse` up to 120%; the design system is
 * stricter and sits inside that bound, so taking the design system's limit
 * satisfies both. `MAX_FOCUS_SCALE` is 1.03 and this cannot exceed it.
 */
export const focusScale = (amount: number): number =>
  1 + (MAX_FOCUS_SCALE - 1) * Math.max(0, Math.min(1, amount));

/**
 * §10.4 RESOLVE — "transition from neutral/signal to answer state ...
 * supporting content settles". Returns 0..1 across the resolve duration once
 * the scene passes `atProgress`.
 */
export const resolveAmount = (
  frame: number,
  fps: number,
  durationInFrames: number,
  atProgress = 0.9,
): number => {
  const start = atProgress * durationInFrames;
  return interpolate(
    frame,
    [start, start + frames(motion.resolve.ms, fps)],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing },
  );
};

/**
 * §10.3: which motion verb a cue kind performs.
 *
 * The signal designer emits four kinds (§9.2 of the PRD): highlight, pointer,
 * scale_pulse, dim. All four are ATTENTION events — §12 level 3 — so all four
 * map to FOCUS, differing in what they change rather than in when or for how
 * long. Mapping them to four different verbs would be the "dozens of unrelated
 * animation presets" §10 opens by rejecting.
 */
export const VERB_FOR_CUE: Record<string, "focus"> = {
  highlight: "focus",
  pointer: "focus",
  scale_pulse: "focus",
  dim: "focus",
};
