# Suite Pythoine 1.0.0-x1.8 QA

Run `bash suite_pythoine/qa/static-qa.sh` from the source root. Its retained historical checks cover the filesystem, installations, Recovery, Purge, Prune, catalogue, Store, routing, desktop, UI source contracts and all previous x1 extractions. `qa/decoupling_x16_regressions.py` adds cross-page builder/import ownership, frozen-production hashes and comparator unit checks. The x1.5 construction-AST and out-of-scope `SuiteWindow` hash checks remain in force. The new `qa/decoupling_x17_regressions.py` also checks shared helper AST fidelity, original `SuiteWindow` AST, default-off tracing and explicit opt-in in separate subprocesses.

`x1.6` is the Wave 1 closure only after the following desktop steps are completed independently:

1. On a Fedora KDE machine with PyQt6 available, test startup, Dashboard, Installed Applications (search/sort/select/remove-asset UI), Application Page, Version History, Get More/Store and Preferences, including the established menu shortcuts, themes and navigation.
2. Run the **issued x1.0** and x1.6 on a comparable representative application library with tracing enabled for both: `SUITE_PYTHOINE_PERF=1 python3 main.py`. Repeat startup and each page operation at least five times. Use a controlled inventory and avoid combining cold vs warm runs when comparing results.
3. Collect the opt-in JSONL at `${XDG_CACHE_HOME:-~/.cache}/suite-pythoine/performance.jsonl` (or separate traces from each build), then run:

   `python3 -m suite_pythoine.tools.performance_compare --log /path/to/x10.jsonl --log /path/to/x16.jsonl --baseline-version 1.0.0-x1.0 --candidate-version 1.0.0-x1.6`

   Inspect median/p95 and count for each operation; the comparator requires five usable samples per version and operation. Missing data yields exit status 2 and INCOMPLETE, not a parity verdict. Exact 0.12.3 performance can only be compared if compatible diagnostic data are separately available; x1.0 is the trace-capable baseline.
4. Compare visible output, configuration persistence, and memory/responsiveness for the same inventory. Investigate any slowdowns or behavioral discrepancies before approving x2. Never reissue 1.0.0-x1.6 with changed source; use a new version if corrective changes become necessary.

**Limit:** This build environment does not contain PyQt6 or prior real desktop traces. Static tests and synthetic comparator unit tests cannot establish Qt GUI/performance parity.
