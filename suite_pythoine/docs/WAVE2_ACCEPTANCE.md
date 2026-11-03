# Suite Pythoine — Wave 2 desktop and performance acceptance protocol

**Prepared in `1.0.0-x2.0`; execution status: PENDING.** This document provides repeatable steps, not fabricated desktop test results. Real tests must use Fedora/KDE with PyQt6 and the dependencies expected by Suite.

## Preconditions

1. Keep verified extracted source copies of `0.12.3` (behavior reference), `1.0.0-x1.8` (immediate source/performance reference) and `1.0.0-x2.0` (candidate). Do not run against live personal managed-installation data; use a disposable test account or sandboxed test home and representative fixture installations. Note: redirecting only XDG config/data does not guarantee every system or home path is isolated.
2. Record OS, Python, Qt/PyQt6 versions, session type (Wayland/X11), desktop, installed test components/versions, and build type (portable vs AppImage). Use the same inventory and settings on both candidates.
3. Run `bash suite_pythoine/qa/static-qa.sh` in each release's own source directory. A passing static gate is a prerequisite, not GUI sign-off.

## Behavior preservation checklist — compare 0.12.3, x1.8 and x2.0

- Startup/exit; Dashboard list/grid and repeated Refresh; sidebar toggle/navigation; themes and status; keyboard shortcuts.
- Installed Applications search/filter/sort and selection, including zero, one, multiple and Recovery-only version fixtures.
- Application Page and Version History; exact-version actions, active-version state, pending confirmation and cancel paths.
- Preferences Apply/OK/Cancel and persistence after restart.
- Get More/Store catalogue search, detail navigation, offline/no-network response; where safe, complete one verified controlled installation.
- ZIP Portable and AppImage paths; routing/open-with behavior; external launch and desktop-integration conditions.
- Recovery, Restore, Purge/Prune and Remove Assets only with disposable fixtures; check cancellation and non-target files before destructive tests.
- In each case compare the **observable state and result**, not just whether a window appears. Flag any difference with source version, exact steps, observed outcome and logs.

## Performance capture (opt-in; default tracing remains OFF)

Use the included original tracer in **both** `x1.8` and `x2.0` (the raw `0.12.3` reference does not contain the same tracing API). In each source directory launch with a unique disposable cache path, for example:

```bash
mkdir -p /tmp/pythoine-wave2-x18-cache
XDG_CACHE_HOME=/tmp/pythoine-wave2-x18-cache SUITE_PYTHOINE_PERF=1 python3 main.py
```

Repeat with `x2.0` using `/tmp/pythoine-wave2-x20-cache` and the corresponding source. For consistent results, run at least five **comparable** repetitions for each operation/version, with equal test data. The logs should be at `suite-pythoine/performance.jsonl` under each chosen cache. Avoid conflating traces collected under different inventory sizes or machine loads. Keep user data out of diagnostic fixtures.

Compare with the existing Qt-free tool, e.g. from the `x2.0` root:

```bash
python3 -m suite_pythoine.tools.performance_compare \
  --log /tmp/pythoine-wave2-x18-cache/suite-pythoine/performance.jsonl \
  --log /tmp/pythoine-wave2-x20-cache/suite-pythoine/performance.jsonl \
  --baseline-version 1.0.0-x1.8 \
  --candidate-version 1.0.0-x2.0 \
  --min-samples 5
```

Report median, p95, sample counts, test environment, UI effects and variance for startup, inventory refresh, installed applications, Application Page, Version History, catalogue, and Store detail. The existing tool returns **INCOMPLETE** when any expected operation lacks sufficient samples; it never automatically asserts equivalence from numerical ratios. The original `0.12.3` may be compared with external wall-clock/UI responsiveness measurements only under comparable conditions and with methodology recorded.

## Go/no-go

Mark a phase accepted only after (1) full source/release gate, (2) matching GUI behavior on disposable fixtures, (3) path/resource and AppImage/Portable launcher checks, and (4) measured performance evidence where a desktop build is available. Where an environment or data is unavailable, record **NOT VERIFIED** rather than PASS. Do not change the frozen operational contracts to make a structural migration fit.
