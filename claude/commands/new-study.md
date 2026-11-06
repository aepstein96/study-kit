---
description: Scaffold a new research study in this project and run its pipeline.
---

Create a new study for the question: **$ARGUMENTS**

1. Derive a short kebab-case name from the question, then run `study-kit new <name>` from anywhere
   inside the project. It copies the template and pins the kit version. Run `uv sync` in the study
   and `npm install` in its `app/`.
2. In the new study folder:
   - **Write `plan.md`:** the question, the data source, the analysis, and what the app will show.
     If a lessons list is loaded in this session, go through all of it first and discharge every
     item that applies. The template's headings prompt for them; answer a prompt rather than
     deleting it.
   - **Read the project's `AGENTS.md`** for domain knowledge, and check whether a sibling study
     already holds the data you need.
   - **Before writing anything not specific to this study,** check `study-kit` (see "Shared code"
     in the guide) and existing studies.
   - **Fill `src/connector.py`** with the data source, using `research_toolkit.download`.
     Use the **researcher** agent for anything touching the web.
   - **Fill `analysis/analyze.py`** to produce `app/public/data.json`.
   - **Fill `report/report.md` and `report/references.bib`** with cited findings.
   - **Adapt `app/src/App.tsx`** to the standard in "Apps must explain themselves". Keep the
     `<FeedbackBox />` as the last element. Replace the `<title>` in `app/index.html`.
   - **Fill `study.json`** (a title and exactly two sentences) and draw `app/public/cover.svg`.
3. Run `study-kit verify`.
4. Hand to the **verifier** agent for evidence-based sign-off before committing.
5. Commit and push. The study becomes its own site the next time someone with the Cloudflare login
   runs `study-kit deploy`.
