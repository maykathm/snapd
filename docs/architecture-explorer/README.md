# snapd Architecture Explorer

`index.html` is a self-contained, offline-friendly interactive guide to snapd's
architecture, aimed at developers who are new to the codebase. It covers entry
points and the execution/confinement pipeline, the overlord/ensure-loop model,
state/changes/tasks, interfaces and declaration policy, the daemon's REST API,
the full state-manager map, assertions, an end-to-end install/refresh
walkthrough, Ubuntu Core/device lifecycle, and an interactive "where do I work
on X?" feature finder.

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
