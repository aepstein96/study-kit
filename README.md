# study-kit

Run many small research studies from one project. Each study turns a question into provenance-tracked
data, an analysis you can audit, and a static interactive app published as its own site. Built to be
driven by Claude Code, and usable without it.

Pairs with [lesson-engine](https://github.com/aepstein96/lesson-engine), which turns your sessions into
lessons that load into future ones. Neither requires the other.

```bash
uv tool install git+https://github.com/aepstein96/study-kit
study-kit init my-project --title "My project"
cd my-project && git init
study-kit new first-study      # scaffold a study
study-kit verify first-study   # analysis, types, build, serve, screenshot, data checks
study-kit deploy               # every study to its own Cloudflare Pages site, plus a project index
```

## What's in it

- **`research_toolkit`** (Python): cached downloads that record source, parameters, timestamp and
  SHA-256 in a committed provenance file, plus path helpers.
- **React and CSS for study apps:** a feedback box, chart scales, chart export and a base theme,
  imported as `study-kit/...`.
- **The `study-kit` command**, a project template, a guide for agents, and Claude Code commands.

## Layout of a project

```
my-project/
  project.json          title, description
  CLAUDE.md             imports the guide and AGENTS.md
  AGENTS.md             knowledge specific to this project
  first-study/
    study.json          title, two-sentence description, random URL key
    plan.md  report/  src/connector.py  analysis/analyze.py  data/  app/
```

## Deploy destination lives on your machine

A project repo says nothing about where it publishes, so you can hand it to someone as-is. Put this
in `~/.config/study-kit/deploy.toml`:

```toml
prefix = "ab"                   # starts every site name; pages.dev names are global
feedback_kv_id = "<namespace>"  # optional: a Workers KV namespace for FeedbackBox comments
```

Then log in with `wrangler login`, or set `CLOUDFLARE_API_TOKEN`. Sites are created the first time
they deploy, named `<prefix>-<study>-<urlKey>.pages.dev`. Cloudflare allows 100 Pages projects per
account, and each study and project index uses one.

Site URLs are unguessable but public: there is no login in front of them yet.

## Versions

Studies depend on the kit by git tag, and `study-kit bump v0.2.0` moves a project to a new one.

## License

MIT
