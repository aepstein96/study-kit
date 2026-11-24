import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

// Inline comments: select text (or hover a figure) to comment on it; comments show in a sidebar
// for everyone who can see the site. FeedbackBox mounts this, so every study gets it.
// Backed by /api/annotations in the project's worker (KV keys ann/<study>/<id>); Claude sessions
// read them with `wrangler kv` (see the /feedback command).
// Text is anchored by its quote plus 32 characters either side (the W3C TextQuoteSelector idea),
// figures by their caption or nearest heading plus an ordinal, so edits to the page that don't
// touch the quoted text keep comments attached. Highlights use the CSS Custom Highlight API,
// which paints ranges without touching the DOM React owns.

type Anchor =
  | { kind: "text"; quote: string; prefix: string; suffix: string }
  | { kind: "figure"; label: string; index: number };
type Ann = {
  id: string; anchor: Anchor; text: string; author: string; ts: string; mine?: boolean;
  status?: string; reply?: string;
};

const CTX = 32;
const UI = ".ann-ui, .fb, .fb-jump";
const root = () => document.querySelector("main") ?? document.body;
const ours = (n: Node | null) => !!(n && (n instanceof Element ? n : n.parentElement)?.closest(UI));
const squash = (s: string) => s.replace(/\s+/g, " ").trim();

function textIndex() {
  const w = document.createTreeWalker(root(), NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (ours(n) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  const nodes: Text[] = [], starts: number[] = [];
  let text = "";
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    nodes.push(n as Text); starts.push(text.length); text += (n as Text).data;
  }
  return { nodes, starts, text };
}
type Ix = ReturnType<typeof textIndex>;

function anchorOf(r: Range): Anchor | null {
  if (ours(r.commonAncestorContainer) || !root().contains(r.commonAncestorContainer)) return null;
  const ix = textIndex();
  let s = -1, e = -1;
  ix.nodes.forEach((n, i) => {
    if (!r.intersectsNode(n)) return;
    if (s < 0) s = ix.starts[i] + (n === r.startContainer ? r.startOffset : 0);
    e = ix.starts[i] + (n === r.endContainer ? r.endOffset : n.length);
  });
  const quote = ix.text.slice(s, e);
  if (s < 0 || !quote.trim()) return null;
  return { kind: "text", quote: quote.slice(0, 1000), prefix: ix.text.slice(Math.max(0, s - CTX), s), suffix: ix.text.slice(e, e + CTX) };
}

function rangeOf(ix: Ix, a: Extract<Anchor, { kind: "text" }>): Range | null {
  // Every occurrence of the quote, scored by how much of the stored context still surrounds it.
  let best = -1, bestScore = -1;
  for (let at = ix.text.indexOf(a.quote); at >= 0; at = ix.text.indexOf(a.quote, at + 1)) {
    let sc = 0;
    while (sc < a.prefix.length && ix.text[at - 1 - sc] === a.prefix[a.prefix.length - 1 - sc]) sc++;
    for (let k = 0; k < a.suffix.length && ix.text[at + a.quote.length + k] === a.suffix[k]; k++) sc++;
    if (sc > bestScore) { best = at; bestScore = sc; }
  }
  if (best < 0) return null;
  const at = (off: number, end: boolean) => {
    for (let i = ix.nodes.length - 1; i >= 0; i--)
      if (end ? ix.starts[i] < off : ix.starts[i] <= off) return [ix.nodes[i], off - ix.starts[i]] as const;
    return null;
  };
  const p = at(best, false), q = at(best + a.quote.length, true);
  if (!p || !q) return null;
  const r = document.createRange();
  r.setStart(p[0], p[1]); r.setEnd(q[0], q[1]);
  return r;
}

// Charts and images big enough to be figures (not icons), outermost only.
function figures() {
  const all = [...root().querySelectorAll<HTMLElement | SVGElement>("figure, svg, img, canvas")].filter((el) => {
    if (ours(el)) return false;
    const b = el.getBoundingClientRect();
    return b.width >= 150 && b.height >= 100;
  });
  const outer = all.filter((el) => !all.some((o) => o !== el && o.contains(el)));
  const heads = [...root().querySelectorAll("h1, h2, h3, h4")];
  const counts: Record<string, number> = {};
  return outer.map((el) => {
    const cap = el.querySelector("figcaption")?.textContent || el.getAttribute("aria-label");
    // ponytail: hidden figures (closed <details>) drop out and can shift the ordinal of later
    // figures under the same heading; the label keeps that within one section.
    const h = heads.filter((x) => x.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING).pop();
    const label = squash(cap || (h ? `Figure under “${squash(h.textContent ?? "")}”` : "Figure")).slice(0, 200);
    const index = (counts[label] = (counts[label] ?? -1) + 1);
    return { el, label, index };
  });
}

// Blocks that get a margin "+" on hover; commenting on one quotes the whole block.
const BLOCKS = "p, li, blockquote, h2, h3, h4, dt, dd, td, figcaption";
// x of the right margin: beside the text column when there's room, else just inside its edge.
const gutter = () => {
  const r = root().getBoundingClientRect();
  return (innerWidth - r.right > 56 ? r.right + 14 : r.right - 34) + scrollX;
};
const canHover = () => matchMedia("(hover: hover)").matches;
const HINT_KEY = "ann-hint-seen";
const seen = () => { try { return !!localStorage.getItem(HINT_KEY); } catch { return true; } };

const describe = (a: Anchor) => (a.kind === "text" ? squash(a.quote) : a.index ? `${a.label} (#${a.index + 1})` : a.label);
const clip = (s: string, n = 160) => (s.length > n ? s.slice(0, n) + "…" : s);

export default function Annotations({ study }: { study: string }) {
  const [items, setItems] = useState<Ann[]>([]);
  const [offline, setOffline] = useState(false);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Anchor | null>(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState("");
  const [active, setActive] = useState<string | null>(null);
  const [order, setOrder] = useState<string[]>([]); // ids located on the page, in document order
  const [selBtn, setSelBtn] = useState<{ x: number; y: number; a: Anchor } | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number; el: Element; fig?: Anchor } | null>(null);
  const [marks, setMarks] = useState<{ x: number; y: number; ids: string[] }[]>([]);
  const [hint, setHint] = useState(() => !seen());
  const located = useRef(new Map<string, Range | Element>());
  const api = `/api/annotations?study=${encodeURIComponent(study)}`;

  useEffect(() => {
    fetch(api).then((r) => (r.ok ? r.json() : Promise.reject())).then((d) => setItems(d.items)).catch(() => setOffline(true));
  }, [api]);

  // Find each comment's target on the page; redo whenever the page re-renders.
  useEffect(() => {
    const locate = () => {
      const ix = textIndex(), figs = figures(), map = located.current;
      map.clear();
      document.querySelectorAll("[data-ann-fig]").forEach((el) => el.removeAttribute("data-ann-fig"));
      for (const it of items) {
        const a = it.anchor;
        const hit = a.kind === "text" ? rangeOf(ix, a) : figs.find((f) => f.label === a.label && f.index === a.index)?.el;
        if (hit) map.set(it.id, hit);
        if (hit instanceof Element) hit.setAttribute("data-ann-fig", it.id === active ? "active" : "");
      }
      if ("highlights" in CSS) {
        const ranges = (pick: (id: string) => boolean) =>
          [...map].filter(([id, h]) => h instanceof Range && pick(id)).map(([, h]) => h as Range);
        CSS.highlights.set("ann", new Highlight(...ranges((id) => id !== active)));
        CSS.highlights.set("ann-active", new Highlight(...ranges((id) => id === active)));
      }
      const node = (h: Range | Element) => (h instanceof Range ? h.startContainer : h);
      const next = [...map.keys()].sort((x, y) =>
        node(map.get(x)!).compareDocumentPosition(node(map.get(y)!)) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1);
      setOrder((prev) => (prev.join() === next.join() ? prev : next));
      // One margin marker per line of the page that carries comments (hidden targets have no box).
      const x = gutter(), ms: { x: number; y: number; ids: string[] }[] = [];
      for (const id of next) {
        const b = map.get(id)!.getBoundingClientRect();
        if (!b.height) continue;
        const y = b.top + scrollY, m = ms.find((m) => Math.abs(m.y - y) < 24);
        if (m) m.ids.push(id); else ms.push({ x, y, ids: [id] });
      }
      setMarks(ms);
    };
    locate();
    let t = 0;
    const later = () => { clearTimeout(t); t = window.setTimeout(locate, 300); };
    const mo = new MutationObserver((ms) => { if (!ms.every((m) => ours(m.target))) later(); });
    mo.observe(root(), { childList: true, subtree: true, characterData: true });
    addEventListener("resize", later);
    return () => { mo.disconnect(); clearTimeout(t); removeEventListener("resize", later); };
  }, [items, active, open]);

  // A "Comment" button next to any text selection on the page.
  useEffect(() => {
    let t = 0;
    const onSel = () => {
      clearTimeout(t);
      t = window.setTimeout(() => {
        const s = document.getSelection();
        const r = s && !s.isCollapsed && s.rangeCount ? s.getRangeAt(0) : null;
        const a = r && anchorOf(r);
        if (!r || !a) return setSelBtn(null);
        const b = r.getBoundingClientRect();
        setSelBtn({ x: b.right + scrollX, y: b.bottom + scrollY + 6, a });
      }, 150);
    };
    document.addEventListener("selectionchange", onSel);
    return () => document.removeEventListener("selectionchange", onSel);
  }, []);

  // A "+" in the margin beside whichever paragraph or figure the pointer is over. It stays put
  // while the pointer crosses empty space, so it can be reached from the text.
  // ponytail: hover only; touch screens comment by selecting text (the hint says so).
  useEffect(() => {
    const onOver = (e: MouseEvent) => {
      const t = e.target as Element;
      if (!t.closest || t.closest(".ann-ui") || !root().contains(t) || ours(t)) return;
      const f = figures().find((x) => x.el.contains(t));
      const el = f?.el ?? t.closest(BLOCKS);
      if (!el || !root().contains(el) || !el.textContent?.trim() && !f) return;
      const b = el.getBoundingClientRect();
      setHover({ x: gutter(), y: b.top + scrollY, el, fig: f && { kind: "figure", label: f.label, index: f.index } });
    };
    const clear = () => setHover(null); // a reflow would leave it beside the wrong line
    document.addEventListener("mouseover", onOver);
    addEventListener("resize", clear);
    return () => { document.removeEventListener("mouseover", onOver); removeEventListener("resize", clear); };
  }, []);

  const startBlock = () => {
    if (!hover) return;
    if (hover.fig) return start(hover.fig);
    const r = document.createRange();
    r.selectNodeContents(hover.el);
    const a = anchorOf(r);
    if (a) start(a);
  };

  const dismissHint = () => { setHint(false); try { localStorage.setItem(HINT_KEY, "1"); } catch { /* private mode */ } };

  // Clicking highlighted text opens its comment.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!document.getSelection()?.isCollapsed) return;
      const c = document.caretRangeFromPoint?.(e.clientX, e.clientY);
      if (!c) return;
      for (const [id, h] of located.current)
        if (h instanceof Range && h.isPointInRange(c.startContainer, c.startOffset)) { setActive(id); setOpen(true); return; }
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  useEffect(() => { document.documentElement.classList.toggle("ann-open", open); }, [open]);

  useEffect(() => {
    if (!active || !open) return;
    document.getElementById(`ann-${active}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [active, open]);

  const start = (a: Anchor) => {
    setDraft(a); setText(""); setErr(""); setOpen(true); setSelBtn(null); setHover(null); dismissHint();
    setTimeout(() => document.querySelector<HTMLTextAreaElement>(".ann-compose textarea")?.focus());
  };

  const post = async () => {
    if (!draft || !text.trim() || sending) return;
    setSending(true); setErr("");
    try {
      const r = await fetch(api, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ study, anchor: draft, text: text.trim() }),
      });
      if (!r.ok) throw new Error(await r.text());
      const it: Ann = await r.json();
      setItems((xs) => [...xs, it]); setDraft(null); setText(""); setActive(it.id);
      document.getSelection()?.removeAllRanges();
    } catch {
      setErr(offline ? "Comments work on the live site only." : "Couldn't post. Try again?");
    } finally { setSending(false); }
  };

  const remove = async (id: string) => {
    const r = await fetch(`${api}&id=${encodeURIComponent(id)}`, { method: "DELETE" });
    if (r.ok) setItems((xs) => xs.filter((x) => x.id !== id));
  };

  const jump = (id: string) => {
    setActive(id);
    const h = located.current.get(id);
    const el = h instanceof Range ? h.startContainer.parentElement : h;
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
  };

  const byId = new Map(items.map((x) => [x.id, x]));
  const placed = order.map((id) => byId.get(id)).filter((x): x is Ann => !!x);
  const lost = items.filter((x) => !order.includes(x.id));
  const card = (it: Ann, gone = false) => (
    <li key={it.id} id={`ann-${it.id}`} className={`ann-card${it.id === active ? " ann-on" : ""}${it.status === "resolved" ? " ann-done" : ""}`}
      onClick={() => !gone && jump(it.id)}>
      <blockquote className={it.anchor.kind === "figure" ? "ann-fig" : ""}>{clip(describe(it.anchor))}</blockquote>
      <p className="ann-text">{it.text}</p>
      <p className="ann-meta">
        {it.author} · {new Date(it.ts).toLocaleDateString()}
        {it.status === "resolved" && " · resolved"}
        {it.mine && <button className="ann-link" onClick={(e) => { e.stopPropagation(); remove(it.id); }}>Delete</button>}
      </p>
      {it.reply && <p className="ann-reply">{it.reply}</p>}
    </li>
  );

  return createPortal(
    <div className="ann-ui">
      {selBtn && (
        <button className="ann-pop" style={{ left: selBtn.x, top: selBtn.y }}
          onMouseDown={(e) => e.preventDefault()} onClick={() => start(selBtn.a)}>Comment</button>
      )}
      {marks.map((m) => (
        <button key={m.ids[0]} className={`ann-mark${m.ids.includes(active ?? "") ? " ann-on" : ""}`}
          style={{ left: m.x, top: m.y }} title={`${m.ids.length} comment${m.ids.length > 1 ? "s" : ""}`}
          onClick={() => { setActive(m.ids[0]); setOpen(true); }}>{m.ids.length}</button>
      ))}
      {hover && !selBtn && !marks.some((m) => Math.abs(m.y - hover.y) < 24) && (
        <button className="ann-add" style={{ left: hover.x, top: hover.y }} onClick={startBlock}
          aria-label={hover.fig ? "Comment on this figure" : "Comment on this paragraph"}>
          <span aria-hidden="true">+</span><span className="ann-add-l">{hover.fig ? "Comment on figure" : "Comment"}</span>
        </button>
      )}
      {hint && !open && (
        <div className="ann-coach" role="note">
          <p>You can comment on this page.</p>
          <p className="ann-coach-how">
            {canHover()
              ? <>Select any text, or click the amber <b>+</b> that appears in the margin beside a paragraph or chart.</>
              : <>Select any text, then tap <b>Comment</b>.</>}
          </p>
          <button className="ann-link" onClick={dismissHint}>Got it</button>
        </div>
      )}
      <button className="ann-toggle" onClick={() => { setOpen(!open); dismissHint(); }} aria-expanded={open}>
        {open ? "Close comments" : items.length ? `Comments (${items.length})` : "Comment"}
      </button>
      {open && (
        <aside className="ann-side" aria-label="Comments">
          <h2 className="ann-h">Comments</h2>
          {draft ? (
            <div className="ann-compose">
              <blockquote className={draft.kind === "figure" ? "ann-fig" : ""}>{clip(describe(draft))}</blockquote>
              <textarea rows={4} value={text} placeholder="Your comment…" onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) post(); }} />
              <div className="ann-row">
                <button className="ann-btn" onClick={post} disabled={sending || !text.trim()}>{sending ? "Posting…" : "Post"}</button>
                <button className="ann-link" onClick={() => setDraft(null)}>Cancel</button>
              </div>
              {err && <p className="ann-err">{err}</p>}
            </div>
          ) : (
            <p className="ann-hint">Select any text, or click the + in the margin beside a paragraph or chart. Everyone who can open this site sees comments.</p>
          )}
          {offline && <p className="ann-err">Comments work on the live site only.</p>}
          <ul className="ann-list">{placed.map((it) => card(it))}</ul>
          {lost.length > 0 && (
            <>
              <h3 className="ann-h3">No longer on the page</h3>
              <p className="ann-hint">The text these were attached to has since changed.</p>
              <ul className="ann-list">{lost.map((it) => card(it, true))}</ul>
            </>
          )}
        </aside>
      )}
    </div>,
    document.body,
  );
}
