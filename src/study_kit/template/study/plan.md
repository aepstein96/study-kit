# Plan

<!-- Before filling this in, read the lessons list (loaded with CLAUDE.md, if this machine has one).
     That file is the single source; the prompts below are reminders to THINK about the
     obligations it imposes, not a copy of the list. Answer a prompt or explain why it doesn't
     apply — deleting one unanswered is how a study ships with the check silently skipped. -->

## Question
<the research question>

## Data source
<which reliable source, and why; the exact endpoint/params>
<suitability metric: how you'll MEASURE that candidate data exhibits the phenomenon — score
candidates with it before building on one; expect traps: default units, per-item licenses>

## Analysis
<what you'll compute; the key statistics>

## App
<what the interactive app will let the user see/do>
<how it will be explained to a lay reader — see "Apps must explain themselves" in .claude/GUIDE.md:
intro, start-here strip, collapsible explainer, chart captions, units, Methodology section>
<if any output is judged by ear/eye rather than by number: which standard reference asset
(sampled instrument, canonical renderer, reference dataset) presents it — or why none exists>

## Verification
- Numbers in `report/report.md` recomputed from `app/public/data.json`
- Pipeline invariants asserted: <bounds / feasibility ("intervention can't lose to baseline") / conservation>
- Heuristics validated against a known-answer case; free parameters tested for insensitivity
- If an optimiser should dominate a baseline (or replaces an older strategy): assert it does,
  on the same metric — greedy sequential passes can lose to a global baseline unless
  warm-started from it
- **Pre-registered reject threshold:** <the number that would make you report a negative result —
  write it BEFORE seeing results, so the validation set can't become a training set>
- If extending prior work: reproduce its published numbers first, from its own data
- If comparing two totals: confirm both sides share an accounting basis (cash vs capitalised,
  members vs whole industry, nominal vs real and which base year)
- `tsc --noEmit` + `npm run build` pass
- App renders (screenshot)
