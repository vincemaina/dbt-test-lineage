# .repo-manual

An **AI-authored, human-read orientation manual** for this repo, kept in version control.

- `manual/` — one Markdown page per system/module. Each page has a generated region (skeleton until
  narrated) and a human region that is never overwritten.
- `index/` — the deterministic structural index (files, symbols, import/call graph).
- `manual.json` — page structure + provenance + freshness hashes.
- `plan.json` — pages still needing narrative (the orchestrator's to-do list).

Regenerate with `repo-manual generate`. Pages whose source files changed show as **stale**
(`repo-manual stale`); only those are rewritten.
