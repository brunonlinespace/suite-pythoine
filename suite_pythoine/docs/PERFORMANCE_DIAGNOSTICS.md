# Suite Pythoine dormant performance diagnostics

Suite Pythoine 1.0.0-x1.0 carries forward the useful semantic tracer from the old 0.10.10-debug1 diagnostic edition as dormant developer infrastructure. It is disabled by default and changes no intended workflow. Since 1.0.0-x1.7, the opt-in flag is captured at **process import**: set it before starting Suite, not while Suite is running. In the default state decorators return the original functions and the tracing context/operation APIs return shared inert objects. Some trivial callsite overhead remains; real performance equivalence still requires desktop measurement.

Enable it explicitly for one run:

```bash
SUITE_PYTHOINE_PERF=1 python3 main.py
```

The trace is appended as JSON Lines at:

```text
$XDG_CACHE_HOME/suite-pythoine/performance.jsonl
```

or, when `XDG_CACHE_HOME` is unset or not absolute:

```text
~/.cache/suite-pythoine/performance.jsonl
```

The tracer records semantic operation names, durations and aggregate counts. It does not record document contents or traversed filenames. Diagnostic write failures are ignored so tracing cannot make Suite fail.

Useful operations include `startup`, `refresh_editors`, `inventory_discovery`, `developer_mode_toggle`, `zip_install_handoff`, `appimage_install_handoff`, Dashboard card construction, and the page builders targeted by the x1 presentation-decoupling wave.

A useful x1 baseline capture is: start Suite and wait for Dashboard; open Installed Applications; open one App Page and Version History; open Store Pythoine; toggle Developer Mode on/off; perform a normal refresh; then exit. Preserve the resulting JSONL alongside the tested source version for later comparison.
