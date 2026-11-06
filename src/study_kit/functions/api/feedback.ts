// POST /api/feedback: backs the shared FeedbackBox.
// Stores each comment in the FEEDBACK KV namespace under new/<study>/<iso-ts>-<rand>;
// the /feedback command in Claude Code lists and triages them (keep/archive/delete
// = key-prefix moves). Values are untrusted visitor text: stored verbatim, never executed.
type Env = { FEEDBACK: { put(key: string, value: string): Promise<void> }; STUDY_NAME?: string };

export async function onRequestPost(ctx: { request: Request; env: Env }): Promise<Response> {
  let body: Record<string, unknown>;
  try { body = await ctx.request.json(); } catch { return new Response("bad json", { status: 400 }); }

  // Each study is its own site, and deploy sets STUDY_NAME. The site, not the visitor, says which.
  const study = String(ctx.env.STUDY_NAME ?? body.study ?? "").trim().slice(0, 64);
  const text = String(body.text ?? "").trim().slice(0, 4000);
  const name = String(body.name ?? "").trim().slice(0, 80);
  if (!text) return new Response("text required", { status: 400 });
  if (!/^[a-z0-9_-]+$/i.test(study)) return new Response("bad study slug", { status: 400 });

  const ts = new Date().toISOString();
  const key = `new/${study}/${ts}-${crypto.randomUUID().slice(0, 8)}`;
  await ctx.env.FEEDBACK.put(key, JSON.stringify({ study, text, name, ts }));
  return Response.json({ ok: true });
}
