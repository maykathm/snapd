# snapd Architecture Explorer

`index.html` is a self-contained, offline-friendly interactive guide to snapd's
architecture, aimed at developers who are new to the codebase. It covers:

- how a snap runs: entry points, `snap run` → `snap-confine` → `snap-exec`, and
  the confinement backends;
- how snapd runs itself: the overlord and ensure loop, state/changes/tasks,
  interfaces and declaration policy, the REST API, the manager map, assertions;
- the snap lifecycle: an install/refresh task-chain walkthrough, data layout,
  services, hooks, configuration, auto-refresh, the store, validation sets,
  components, desktop integration, snapshots, notices and prompting;
- Ubuntu Core in depth: device anatomy and partitions, a stage-by-stage boot
  process, image building and install mode, recovery systems and factory reset,
  gadget/kernel/snapd updates, registration, system configuration, snap-repair,
  remodeling and full disk encryption;
- a "where do I work on X?" finder, conventions and a glossary.

Each section opens with a plain-language summary; "Go deeper" panels hold the
code-level detail. Press `/` to search.

Open it directly in a browser — no build step or server required:

```sh
xdg-open docs/architecture-explorer/index.html
```

It has no external dependencies (no CDN scripts/fonts); everything is inline
so it keeps working without network access.

This page is a learning aid, not authoritative documentation. When it and the
source disagree, trust the source and the documents it was built from:
[`ARCHITECTURE.md`](../../ARCHITECTURE.md), [`overlord/README.md`](../../overlord/README.md),
[`interfaces/builtin/README.md`](../../interfaces/builtin/README.md), and [`CODING.md`](../../CODING.md).
Please send a PR updating it if you spot drift.
