// Small SVG line chart with a hover crosshair and tooltip. No dependencies.
// All series share the same x values. Colours identify the marks only; text stays in ink colours.
const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(name, attrs, parent) {
  const el = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  if (parent) parent.appendChild(el);
  return el;
}

function niceTicks(min, max, count) {
  const step0 = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= step0);
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return ticks;
}

/**
 * container: element to draw into
 * opts: { x: number[], series: [{ name, color, values: number[] }], xTitle, yUnit,
 *         xFormat(v), markers: bool, leftMargin: px for long y labels, tooltip(i) -> { title, rows: [[label, value]] } }
 */
function lineChart(container, opts) {
  const W = 368, H = 180, m = { top: 12, right: opts.series.length > 1 ? 58 : 12, bottom: 30, left: opts.leftMargin || 44 };
  const pw = W - m.left - m.right, ph = H - m.top - m.bottom;
  const all = opts.series.flatMap((s) => s.values);
  const pad = (Math.max(...all) - Math.min(...all)) * 0.08 || 1;
  const y0 = Math.min(...all) - pad, y1 = Math.max(...all) + pad;
  const x0 = opts.x[0], x1 = opts.x[opts.x.length - 1];
  const sx = (v) => m.left + ((v - x0) / (x1 - x0)) * pw;
  const sy = (v) => m.top + (1 - (v - y0) / (y1 - y0)) * ph;

  container.innerHTML = "";
  container.classList.add("chart");
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.label }, container);

  for (const t of niceTicks(y0, y1, 4)) {
    svgEl("line", { x1: m.left, x2: m.left + pw, y1: sy(t), y2: sy(t), class: "grid" }, svg);
    svgEl("text", { x: m.left - 6, y: sy(t) + 4, class: "tick", "text-anchor": "end" }, svg).textContent =
      t.toLocaleString("en-US") + (opts.yUnit || "");
  }
  svgEl("line", { x1: m.left, x2: m.left + pw, y1: m.top + ph, y2: m.top + ph, class: "axis" }, svg);
  for (const t of niceTicks(x0, x1, 4)) {
    svgEl("text", { x: sx(t), y: H - 14, class: "tick", "text-anchor": "middle" }, svg).textContent =
      opts.xFormat ? opts.xFormat(t) : t;
  }
  svgEl("text", { x: m.left + pw / 2, y: H - 2, class: "tick", "text-anchor": "middle" }, svg).textContent = opts.xTitle;

  for (const s of opts.series) {
    const d = s.values.map((v, i) => `${i ? "L" : "M"}${sx(opts.x[i]).toFixed(1)},${sy(v).toFixed(1)}`).join("");
    svgEl("path", { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round" }, svg);
    if (opts.markers) {
      s.values.forEach((v, i) =>
        svgEl("circle", { cx: sx(opts.x[i]), cy: sy(v), r: 4, fill: s.color, class: "marker" }, svg));
    }
    if (opts.series.length > 1) { // direct label at the line's end, in ink colour
      const last = s.values.length - 1;
      svgEl("text", { x: m.left + pw + 6, y: sy(s.values[last]) + 4, class: "series-label" }, svg).textContent = s.name;
    }
  }

  // hover layer: a crosshair that snaps to the nearest x, and a tooltip
  const cross = svgEl("line", { y1: m.top, y2: m.top + ph, class: "cross", visibility: "hidden" }, svg);
  const dots = opts.series.map((s) => svgEl("circle", { r: 5, fill: s.color, class: "marker", visibility: "hidden" }, svg));
  const tip = document.createElement("div");
  tip.className = "chart-tip";
  tip.hidden = true;
  container.appendChild(tip);
  const hit = svgEl("rect", { x: m.left, y: m.top, width: pw, height: ph, fill: "transparent" }, svg);

  function move(evt) {
    const box = svg.getBoundingClientRect();
    const px = ((evt.clientX - box.left) / box.width) * W;
    let i = 0;
    opts.x.forEach((v, k) => { if (Math.abs(sx(v) - px) < Math.abs(sx(opts.x[i]) - px)) i = k; });
    const cx = sx(opts.x[i]);
    cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
    dots.forEach((d, k) => {
      d.setAttribute("cx", cx); d.setAttribute("cy", sy(opts.series[k].values[i])); d.setAttribute("visibility", "visible");
    });
    const info = opts.tooltip(i);
    tip.innerHTML = "";
    const title = document.createElement("strong");
    title.textContent = info.title;
    tip.appendChild(title);
    for (const [label, value] of info.rows) {
      const row = document.createElement("div");
      row.textContent = `${label}: ${value}`;
      tip.appendChild(row);
    }
    tip.hidden = false;
    const left = (cx / W) * box.width;
    tip.style.left = Math.min(Math.max(left - 70, 0), box.width - 150) + "px";
  }
  function leave() {
    cross.setAttribute("visibility", "hidden");
    dots.forEach((d) => d.setAttribute("visibility", "hidden"));
    tip.hidden = true;
  }
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointerleave", leave);
}
