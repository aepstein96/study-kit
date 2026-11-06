/** Runnable check for scales.ts. Run with `node tests/chart-scales-selftest.ts`, which strips TS
 * types natively since v23. Asserts the maths, including the one
 * behavioural fix the extraction exists to carry: the zero-width-domain guard. */
import { linScale, roundedLinearAxis, logAxis } from "../chart-scales/scales.ts";

let bad = 0;
function eq(name: string, got: unknown, want: unknown) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g !== w) { bad++; console.log(`FAIL ${name}: want ${w} got ${g}`); }
}

// linScale: endpoints, midpoint, inverted (screen-y) range
const x = linScale([2000, 2020], [56, 790]);
eq("x maps domain start to range start", x(2000), 56);
eq("x maps domain end to range end", x(2020), 790);
eq("x maps midpoint to midpoint", x(2010), (56 + 790) / 2);
const y = linScale([0, 100], [298, 16]); // inverted: bigger value = higher on screen = smaller y
eq("inverted y: 0 sits at the bottom", y(0), 298);
eq("inverted y: 100 sits at the top", y(100), 16);

// THE guard: a collapsed domain must not produce NaN (three of four hand-rolled copies did)
const flat = linScale([7, 7], [10, 90]);
eq("zero-width domain yields a finite number, not NaN", Number.isFinite(flat(7)), true);

// roundedLinearAxis: the linear mode
eq("973 rounds up to 1000 with decade step", roundedLinearAxis(973), {
  top: 1000, ticks: [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000] });
eq("42 rounds to 50", roundedLinearAxis(42).top, 50);
eq("exact power stays put", roundedLinearAxis(100).top, 100);

// logAxis: decade ticks, always at least one decade wide
eq("0.5..4000 spans decades -1..4", logAxis(0.5, 4000), {
  l0: -1, l1: 4, ticks: [0.1, 1, 10, 100, 1000, 10000] });
eq("degenerate lo==hi still spans one decade", logAxis(10, 10).l1 - logAxis(10, 10).l0 >= 1, true);

console.log(bad ? `${bad} FAILED` : "chart-scales selftest: all cases pass");
process.exit(bad ? 1 : 0);
