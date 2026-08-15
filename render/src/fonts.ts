/**
 * Font loading — §11.3 hermeticity, two bullets of it.
 *
 * > "Network fetches at render time → forbidden. All assets resolved to
 * >  content-addressed local paths before render."
 * > "Font loading races → embed as base64 or pin via a fully-resolved
 * >  document.fonts.ready."
 *
 * So: Inter comes from `@fontsource/inter`, a package in `node_modules` that
 * the bundler inlines. It is **not** a Google Fonts CDN call — that would be a
 * network fetch at render time and would make the render non-hermetic, which on
 * a content-addressed cache means bytes that differ by whether a CDN was up.
 *
 * The second bullet is the subtler one. Chromium will happily paint a frame in
 * the fallback family while the webfont is still decoding, so frame 0 renders
 * in Segoe UI and frame 30 renders in Inter — a render that is not
 * reproducible, and one whose only symptom is that the first half-second looks
 * slightly wrong. `delayRender` holds the render until `document.fonts.ready`
 * resolves AND the specific faces report loaded.
 *
 * Inter is SIL OFL 1.1. The family name is referenced through `tokens.font`, so
 * swapping to the design system's real family is one value change there.
 */
import "@fontsource/inter/400.css";
import "@fontsource/inter/600.css";
import { continueRender, delayRender } from "remotion";

/** The faces the type scale actually uses (§6: weights 400 and 600 only). */
const FACES = ['400 16px "Inter"', '600 16px "Inter"'] as const;

let started = false;

/**
 * Call once from the composition root. Idempotent — Remotion mounts the tree
 * per frame in some modes, and a second delayRender handle that never resolves
 * would hang the render rather than fail it.
 */
export const ensureFontsLoaded = (): void => {
  if (started || typeof document === "undefined") return;
  started = true;

  const handle = delayRender("loading Inter (§11.3: no font race)");
  Promise.all(FACES.map((f) => document.fonts.load(f)))
    .then(() => document.fonts.ready)
    .then(() => continueRender(handle))
    .catch(() => {
      // Continuing on failure would render the fallback family and produce
      // bytes that differ from every other render of the same scene. Better to
      // let the render time out loudly than to poison the cache quietly.
      // eslint-disable-next-line no-console
      console.error("Inter failed to load; refusing to render in a fallback");
    });
};
