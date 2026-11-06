import { useRef, useState } from "react";
import "./feedback.css";

// Posts to the /api/feedback Pages Function that `study-kit deploy` adds to every study site,
// which stores comments in KV for triage via the /feedback command in Claude Code.
//   import FeedbackBox from "study-kit/feedback-box/FeedbackBox";
// The study slug defaults to the last URL path segment (the site/s/<slug>-<key>/
// layout; the server strips the -<key> suffix). Pass `study` explicitly only if
// that's wrong for a page.
export default function FeedbackBox({ study }: { study?: string }) {
  const segs = window.location.pathname.split("/").filter(Boolean);
  const slug = study ?? segs[segs.length - 1] ?? "index";
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const boxRef = useRef<HTMLElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);

  const jump = () => {
    boxRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    textRef.current?.focus({ preventScroll: true });
  };

  const send = async () => {
    if (!text.trim() || state === "sending") return;
    setState("sending");
    try {
      const r = await fetch("/api/feedback", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ study: slug, text: text.trim(), name: name.trim() }),
      });
      if (!r.ok) throw new Error(String(r.status));
      setText("");
      setState("sent");
    } catch {
      setState("error");
    }
  };

  return (
    <>
      <button className="fb-jump" onClick={jump}>Leave Feedback</button>
      <section className="fb" ref={boxRef}>
      <h2 className="fb-h">Feedback</h2>
      <p className="fb-sub">
        Spotted something confusing, wrong, or worth adding? Leave a note — it goes
        straight to the author&rsquo;s review queue.
      </p>
      <textarea
        ref={textRef}
        className="fb-text"
        rows={3}
        value={text}
        placeholder="Your feedback…"
        onChange={(e) => { setText(e.target.value); if (state === "sent" || state === "error") setState("idle"); }}
      />
      <div className="fb-row">
        <input
          className="fb-name"
          type="text"
          value={name}
          placeholder="Name (optional)"
          onChange={(e) => setName(e.target.value)}
        />
        <button className="fb-send" onClick={send} disabled={state === "sending" || !text.trim()}>
          {state === "sending" ? "Sending…" : "Send feedback"}
        </button>
      </div>
      {state === "sent" && <p className="fb-note fb-ok">Thanks — received.</p>}
      {state === "error" && (
        <p className="fb-note fb-err">Couldn&rsquo;t send — feedback only works on the published site.</p>
      )}
      </section>
    </>
  );
}
