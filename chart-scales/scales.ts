/** The chart-frame maths every study re-derived — extracted after it was written from scratch
 * four times (docs/TOOLBOX.md → "Open decisions → Charts").
 *
 * Deliberately NOT a chart component: the four studies draw genuinely different things, and a
 * component covering them all would need a config surface bigger than the code it replaces.
 * What was actually duplicated — and is shared here — is the frame: the linear domain→range
 * map (written four times with four naming conventions) and the tick generators (written once,
 * and needed by the next chart that wants a log axis).
 *
 * The one behavioural fix baked in: the `|| 1` zero-width-domain guard. Only one of the four
 * hand-rolled copies had it; the other three divide by zero when a domain collapses (a
 * single-point series, a filter that leaves one value) and every mark lands on NaN — which SVG
 * renders as nothing, silently. Self-test: scripts/checks/chart-scales-selftest.py.
 */

/** Linear map from domain [d0,d1] to range [r0,r1]. For an inverted (screen-y) axis just pass
 * the range high-to-low: `linScale([yMin, yMax], [H - padB, padT])`. */
export const linScale =
  ([d0, d1]: [number, number], [r0, r1]: [number, number]) =>
  (v: number): number =>
    r0 + ((v - d0) / ((d1 - d0) || 1)) * (r1 - r0);

/** Zero-baseline linear axis: top rounded up to one significant step so gridlines read as round
 * numbers. Returns the rounded top and the tick values 0..top. */
export function roundedLinearAxis(hi: number): { top: number; ticks: number[] } {
  const step = Math.pow(10, Math.floor(Math.log10(Math.abs(hi) || 1)));
  const top = Math.ceil(hi / step) * step || step;
  return { top, ticks: Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step) };
}

/** Decade log axis spanning [lo, hi] (both > 0): floor/ceil decade exponents, always at least
 * one decade wide, ticks at the powers of ten. */
export function logAxis(lo: number, hi: number): { l0: number; l1: number; ticks: number[] } {
  const l0 = Math.floor(Math.log10(lo));
  const l1 = Math.max(l0 + 1, Math.ceil(Math.log10(hi)));
  return { l0, l1, ticks: Array.from({ length: l1 - l0 + 1 }, (_, i) => 10 ** (l0 + i)) };
}
