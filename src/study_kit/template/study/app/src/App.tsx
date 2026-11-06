import { useEffect, useState } from "react";
// Every study keeps the shared FeedbackBox: visitors' notes land in KV and are triaged with
// /feedback in Claude Code.
import FeedbackBox from "study-kit/feedback-box/FeedbackBox";

/* ---------------------------------------------------------------------------
   This scaffold already has the six things GUIDE.md ("Apps must explain
   themselves") requires of every study app. REPLACE the placeholder copy —
   do not delete the sections. A study that ships without them is incomplete.

     1. plain-language intro        <p className="sub">
     2. "start here" strip          <div className="callout">
     3. collapsible explainer       <details className="explain">
     4. a caption on every chart    <p className="cap">
     5. units explained             wherever a number appears
     6. Methodology at the bottom   <div className="method">

   Styling comes from study-kit/study-theme/theme.css: use its class vocabulary
   rather than inventing parallel names.
--------------------------------------------------------------------------- */

type Stat = { label: string; value: number; unit?: string };
type Series = { name: string; color: string; points: [number, number][] };
type Data = {
  meta: { title: string; description: string; source: string; source_url: string };
  stats: Stat[];
  series: Series[];
};

export default function App() {
  const [data, setData] = useState<Data | null>(null);
  useEffect(() => {
    fetch("./data.json").then((r) => r.json()).then(setData).catch(() => setData(null));
  }, []);
  if (!data) return <main className="wrap"><p>Loading…</p></main>;

  const all = data.series.flatMap((s) => s.points.map((p) => p[1]));
  const yMin = Math.min(...all), yMax = Math.max(...all);
  const W = 800, H = 300, pad = 30;
  const xs = Math.max(...data.series.map((s) => s.points.length), 2);
  const sx = (i: number) => pad + (i / (xs - 1)) * (W - 2 * pad);
  const sy = (y: number) => H - pad - ((y - yMin) / (yMax - yMin || 1)) * (H - 2 * pad);

  return (
    <main className="wrap">
      <h1>{data.meta.title}</h1>

      {/* 1. Intro: the question and why it's interesting, in 2-3 sentences, no jargon. */}
      <p className="sub">{data.meta.description}</p>

      {/* 2. Start here: the 2-3 clicks that let a first-time visitor experience the point. */}
      <div className="callout">
        <h3>Start here</h3>
        <ol>
          <li>REPLACE: the first thing to look at, and what it shows.</li>
          <li>REPLACE: the control to move, and what changes when you do.</li>
        </ol>
      </div>

      {/* 3. The core concept in ~1 minute, defining every term — including "obvious" ones. */}
      <details className="explain">
        <summary>What's going on here?</summary>
        <p>REPLACE: the concept a reader needs, in plain language. Define every term you use.</p>
      </details>

      <div className="tiles">
        {data.stats.map((s) => (
          <div className="tile" key={s.label}>
            {/* 5. Units: always next to the number. Say so if the scale is arbitrary. */}
            <div className="v">{s.value}{s.unit}</div>
            <div className="l">{s.label}</div>
          </div>
        ))}
      </div>

      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={data.meta.title}>
        {data.series.map((s) => (
          <polyline key={s.name} fill="none" stroke={s.color} strokeWidth={2}
            points={s.points.map((p, i) => `${sx(i)},${sy(p[1])}`).join(" ")} />
        ))}
      </svg>
      <div className="legend">
        {data.series.map((s) => (
          <span key={s.name}><b style={{ background: s.color }} />{s.name}</span>
        ))}
      </div>

      {/* 4. Caption: how to READ the chart — axes, what each mark and color means,
             what to notice. Never assume a chart is self-evident. */}
      <p className="cap">
        <b>How to read this:</b> REPLACE — x axis is …, y axis is … (in <i>units</i>).
        Each line is …. Notice ….
      </p>

      {/* 6. Methodology last: the technical detail, out of the main flow. */}
      <h2 className="h2">Methodology</h2>
      <div className="method">
        <p>REPLACE: data source and vintage, model and parameters, how values were
          computed, choices a skeptic would question, and the limitations.</p>
      </div>

      <p className="src">Source: <a href={data.meta.source_url}>{data.meta.source}</a></p>
      <FeedbackBox />
    </main>
  );
}
