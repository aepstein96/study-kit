/** Export a live chart SVG as a 2x PNG, and the button that does it.
 *
 * Extracted from the first study that wrote it, when a second one needed the same thing.
 *
 * The subtlety worth keeping: CSS variables and classes do NOT survive serialization. A
 * chart drawn with `fill="var(--accent)"` and `class="grid"` serializes to a document with
 * no stylesheet, so every var resolves to nothing and the PNG comes out blank or black.
 * Computed styles are therefore inlined onto a clone first, and the canvas is painted with
 * the chart's own computed background so a dark-mode export does not come out as dark text
 * on transparent.
 */
const PROPS = [
  "fill", "stroke", "stroke-width", "stroke-dasharray", "opacity",
  "fill-opacity", "stroke-opacity", "font-family", "font-size", "font-weight",
  "text-anchor", "letter-spacing", "paint-order", "stroke-linejoin", "stroke-linecap",
];

export async function svgToPng(svg: SVGSVGElement, filename: string, scale = 2): Promise<void> {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const src = [svg, ...Array.from(svg.querySelectorAll("*"))];
  const dst = [clone, ...Array.from(clone.querySelectorAll("*"))];
  src.forEach((el, i) => {
    const cs = getComputedStyle(el);
    const d = dst[i] as SVGElement;
    for (const p of PROPS) d.style.setProperty(p, cs.getPropertyValue(p));
    d.removeAttribute("class");
  });
  const vb = svg.viewBox.baseVal;
  const w = vb.width || svg.clientWidth;
  const h = vb.height || svg.clientHeight;
  clone.setAttribute("width", String(w));
  clone.setAttribute("height", String(h));
  const svgBg = getComputedStyle(svg).backgroundColor;
  const bg = svgBg && svgBg !== "rgba(0, 0, 0, 0)" ? svgBg
    : getComputedStyle(document.body).backgroundColor;
  const url = URL.createObjectURL(
    new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" }));
  try {
    const img = new Image();
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url; });
    const canvas = document.createElement("canvas");
    canvas.width = w * scale;
    canvas.height = h * scale;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0, w, h);
    canvas.toBlob((b) => {
      if (!b) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    }, "image/png");
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Filename from a chart's aria-label, which every chart here already has for screen readers. */
export function chartFilename(svg: Element, fallback = "chart"): string {
  const name = (svg.getAttribute("aria-label") || fallback)
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);
  return `${name || fallback}.png`;
}
