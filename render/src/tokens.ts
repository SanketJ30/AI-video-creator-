/**
 * THE TOKEN LAYER — docs/design/video-design-system.md §3.
 *
 * The single place a colour, size, space or duration is written down. Every
 * component reads from here; a hex literal anywhere else is a test failure
 * (`test_no_component_contains_a_hex_literal`).
 *
 * §3: "Do not create new colors." Every value below is mapped from the source
 * design system's existing tokens, with the source token named beside it. The
 * renderer does not invent a replacement when a token already exists.
 *
 * ## Why roles and not colours
 *
 * ISSUE-18 was that four hex literals did all the work and hierarchy was
 * bold-vs-regular. The deeper defect §3 names: "the problem where 'attention'
 * and 'answer' become visually identical". So these are SEMANTIC roles and the
 * distinction between them is the point:
 *
 *   signal  (blue)   "look here / this is being discussed now"
 *   answer  (green)  "this is the correct, resolved, confirmed state"
 *   error   (red)    "this is wrong, broken, a failure"
 *   warning (orange) "be careful / this deserves attention"
 *
 * A component that wants "emphasis" must decide WHICH emphasis it means. That
 * choice is the design system doing its job.
 */

// ---------------------------------------------------------------- colour
//
// §3's mapping table, verbatim. Source token names kept so a change in the
// design system can be traced to the role it moves.

export const color = {
  /** colorBgBase / colorBgContainer — default video background */
  surface: "#FFFFFF",
  /** colorBgLayout — secondary canvas, quiet region */
  surfaceSubtle: "#FAFAFA",
  /**
   * colorPrimaryBg — highlighted area.
   *
   * NOT USED as an emphasis surface; `surfaceSignalHover` is. See below.
   */
  surfaceSignal: "#F5FAFF",
  /**
   * colorPrimaryBgHover — stronger highlight state, and the tier this renderer
   * uses wherever a surface means "emphasised".
   *
   * ## VIDEO NEEDS MORE SEPARATION THAN A SCREEN UI
   *
   * MEASURED, WCAG ratio against `surface`:
   *
   *     signalSoft   #F5FAFF   1.050:1     <- the Bg tier
   *     answerSoft   #F7FDFA   1.030:1
   *     warningSoft  #FFFDF5   1.018:1
   *     errorSoft    #FFF5F5   1.070:1
   *     surfaceSignalHover #E6F3FF 1.127:1 <- the Bg-Hover tier
   *
   * The Bg tier is a screen-UI container colour: it is read on a calibrated
   * monitor at reading distance, next to other white cards that give it an
   * edge to be seen against. A video is watched at phone size after H.264,
   * whose 4:2:0 chroma subsampling and quantisation both operate at a scale
   * larger than a 1.02:1 step. A 69%-of-frame `answerSoft` fill measured on
   * the finished MP4 was indistinguishable from white.
   *
   * So this is not "the design system is wrong" — it is the same tokens read
   * in a medium they were not tuned for. §3 says "do not create new colors",
   * and this does not: it steps one rung up a ramp the design system already
   * defines.
   */
  surfaceSignalHover: "#E6F3FF",

  /** colorText — primary readable text */
  ink: "#262626",
  /** colorTextBase — rare maximum emphasis */
  inkStrong: "#141414",
  /** colorTextSecondary — supporting copy */
  inkMuted: "#595959",
  /** colorTextTertiary — captions, metadata */
  inkSubtle: "#8C8C8C",
  /** colorTextDisabled — non-active reference information */
  inkDisabled: "#BFBFBF",

  /** colorBorder — main rules, card borders */
  structure: "#D9D9D9",
  /** colorBorderSecondary — chart grids, quiet dividers */
  structureSubtle: "#F5F5F5",

  /** colorPrimary — "look here" / active emphasis */
  signal: "#148AFF",
  /** colorPrimaryActive — strong active emphasis */
  signalStrong: "#0073E5",
  /** colorPrimaryBg — background behind signal */
  signalSoft: "#F5FAFF",
  /** colorPrimaryBorder — signal containers */
  signalBorder: "#99CCFF",

  /*
    BLOCKED, and deliberately not worked around.

    The three soft tokens below have the same video-vs-screen problem as
    `signalSoft` (1.018–1.070:1 against surface — see `surfaceSignalHover`), and
    they carry the scene state, so they matter more than signal does: `broken`,
    `caution` and `resolved` are rendered as containers in exactly these colours.

    The fix is the same one rung up the ramp — but §3's mapping table gives a
    Bg-Hover tier for the SIGNAL role only. It has `colorPrimaryBgHover`; it does
    not list `colorSuccessBgHover`, `colorWarningBgHover` or `colorErrorBgHover`,
    and the source design system is not in this repo, so those values cannot be
    read from anywhere here.

    §3 opens with "Do not create new colors." Interpolating a plausible hover
    tier would be creating three, so these stay on the Bg tier until the real
    values are supplied. What is needed is four numbers, not a design decision:

        colorSuccessBgHover   ->  answerSoftHover
        colorWarningBgHover   ->  warningSoftHover
        colorErrorBgHover     ->  errorSoftHover

    (`colorSuccessBorder` / `colorWarningBorder` / `colorErrorBorder` would be
    better still: the signal equivalent, `colorPrimaryBorder` #99CCFF, measures
    1.689:1 — an order of separation above the Bg-Hover tier's 1.127:1.)

    Until then the visible state signal is the 12 px rule in the saturated role
    colour, which does read: error 4.814:1, answer 2.368:1, warning 2.051:1.
  */

  /** colorSuccess — confirmed / correct / resolution */
  answer: "#05C170",
  /** colorSuccessBg — answer container. BLOCKED at 1.030:1, see above. */
  answerSoft: "#F7FDFA",

  /** colorWarning — caution / deserves attention */
  warning: "#FCA106",
  /** colorWarningBg. BLOCKED at 1.018:1, see above. */
  warningSoft: "#FFFDF5",

  /** colorError — wrong / broken / failure */
  error: "#D13845",
  /** colorErrorBg. BLOCKED at 1.070:1, see above. */
  errorSoft: "#FFF5F5",
} as const;

// ------------------------------------------------------------ typography
//
// §6. The family is referenced through the token layer so swapping to the
// design system's real family is ONE value change rather than six template
// edits. Inter is self-hosted under render/public/fonts — §11.3 forbids a
// network fetch at render time, and a Google Fonts CDN call is exactly that.

export const font = {
  sans: "Inter, 'Segoe UI', Helvetica, Arial, sans-serif",
  mono: "'JetBrains Mono', Consolas, Menlo, monospace",
} as const;

/**
 * §6's 1920×1080 scale. Where the spec gives a range, the chosen value is
 * recorded here and the range is kept in the comment — §6 gives the range, so
 * inventing outside it would be inventing a value the spec already gives.
 *
 * §6's floor is absolute: "Never solve a layout problem by shrinking type below
 * 24 px." Nothing here goes below 24, and `linter.check_type_fits` makes the
 * consequence a BLOCKING finding rather than a silent shrink.
 */
export const type = {
  /** §6 Display 72–88 / 600 — cold open, major title */
  display: { size: 80, weight: 600, line: 1.1 },
  /** §6 H1 56–64 / 600 — template title */
  h1: { size: 60, weight: 600, line: 1.15 },
  /** §6 H2 40–48 / 600 — major section, card title */
  h2: { size: 44, weight: 600, line: 1.2 },
  /** §6 H3 32–36 / 600 — item title */
  h3: { size: 34, weight: 600, line: 1.25 },
  /** §6 Body 28–32 / 400 */
  body: { size: 30, weight: 400, line: 1.4 },
  /** §6 Body strong 28–32 / 600 */
  bodyStrong: { size: 30, weight: 600, line: 1.4 },
  /** §6 Caption 24–26 / 400–500 */
  caption: { size: 26, weight: 400, line: 1.4 },
  /** §6 Label 24 / 600 — "THE LESSON", "STEP 1" */
  label: { size: 24, weight: 600, line: 1.2 },
  /** §6 Numeric display 64–88 / 600 */
  numeric: { size: 72, weight: 600, line: 1.1 },
  /** §6 Mono 26–30 / 400–600 — §17 sets a 26 floor for code */
  mono: { size: 28, weight: 400, line: 1.5 },
} as const;

/** §6/§11.6 — the floor, asserted in tests on both sides of the boundary. */
export const MIN_FONT_PX = 24;

// --------------------------------------------------------------- spacing
//
// §5: "12 → 16 → 24 → 32 → 48 → 64 → 96 → 128". Derived multiples of the
// source system's 12/16/24, not new brand tokens. §5: "Avoid random values
// such as 37, 53, 71."

export const space = {
  xs: 12,
  sm: 16,
  md: 24,
  lg: 32,
  xl: 48,
  xxl: 64,
  frame: 96,
  breathe: 128,
} as const;

export const SPACING_SCALE = [12, 16, 24, 32, 48, 64, 96, 128] as const;

// ---------------------------------------------------------------- canvas
//
// §4. Margins 96/96/72/64, 12 columns, 24 px gutter.
//
// ONE DEVIATION, deliberate and recorded: §4 gives a 64 px bottom margin, but
// §16.2 reserves the bottom 15% of the frame (162 px at 1080) as a caption
// exclusion zone, and CHALLENGES lists that among the irreversible decisions.
// Content laid out to a 64 px bottom would sit under the captions. §4 permits
// the implementation to "adjust this slightly to accommodate the renderer";
// this adjustment is not slight, so it is stated rather than absorbed.
// §16.2 wins. The 64 px value survives as the gap between content and the
// caption zone.

export const canvas = {
  width: 1920,
  height: 1080,
  marginLeft: 96,
  marginRight: 96,
  marginTop: 72,
  /** §16.2's caption exclusion zone, which supersedes §4's 64 px. */
  captionZone: 162,
  /** §4's 64 px, kept as the content-to-caption-zone gap. */
  marginBottom: 64,
  columns: 12,
  gutter: 24,
} as const;

export const contentLeft = canvas.marginLeft;
export const contentTop = canvas.marginTop;
export const contentWidth = canvas.width - canvas.marginLeft - canvas.marginRight;
export const contentHeight =
  canvas.height - canvas.marginTop - canvas.captionZone - canvas.marginBottom;

/** Width of `n` grid columns including the gutters between them (§4). */
export const columns = (n: number): number => {
  const col = (contentWidth - canvas.gutter * (canvas.columns - 1)) / canvas.columns;
  return col * n + canvas.gutter * (n - 1);
};

// ----------------------------------------------------------------- motion
//
// §10's five verbs with §10's duration bands, and §11's easing.
//
// The bands are the spec's. The chosen value inside each band is recorded so a
// reviewer can see the choice; §10 gives the range, so a value outside it would
// be inventing something the spec already decided.

export const motion = {
  /** §10.1 REVEAL 300–500 ms — information entering. Up-shift + opacity. */
  reveal: { ms: 400, shiftPx: 24 },
  /** §10.2 BUILD 400–700 ms — information being constructed. */
  build: { ms: 520, shiftPx: 16 },
  /** §10.3 FOCUS 250–450 ms — attention onto something already visible. */
  focus: { ms: 340, scale: 1.02 },
  /** §10.4 RESOLVE 400–700 ms — the lesson reaching its answer. */
  resolve: { ms: 560 },
  /** §10.5 TRANSITION — between concepts. Crossfade preferred. */
  transition: { ms: 400 },
} as const;

/**
 * §11: "quick to start → controlled → settled". No bounce, no elastic
 * overshoot, no mechanical linear. Standard material-style decelerate — the
 * learner should barely notice the easing itself.
 */
export const EASE: readonly [number, number, number, number] = [0.4, 0.0, 0.2, 1];

/** §10.3: FOCUS may scale "only 1–3%". Anything larger is out of spec. */
export const MAX_FOCUS_SCALE = 1.03;
