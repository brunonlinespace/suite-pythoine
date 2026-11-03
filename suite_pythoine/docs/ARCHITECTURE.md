# Suite Pythoine architecture — 1.0.0-x1.8

Wave 1 is presentation decoupling **only**. No x2 controller/ownership rearchitecture has taken place.

```text
suite_pythoine/
├── app.py                           # existing SuiteWindow, lifecycle actions and coordination
├── ui/
│   ├── dialogs/preferences.py       # x1.2 Preferences dialogs
│   ├── pages/
│   │   ├── installed_applications.py # x1.3 inventory view
│   │   ├── application.py           # x1.4 installed Application Page and shared identity header
│   │   ├── version_history_page.py  # x1.4 version-history view
│   │   └── store_catalogue.py       # x1.5 Get More/Store view + enrichment
│   ├── diagnostic_helpers.py        # x1.7 shared diagnostic presentation helpers
│   ├── helpers.py                  # x1.1 UI helpers
│   └── widgets/                   # x1.1 widgets
├── qa/extracted_page_sources.py     # Qt-free historical QA source adapter
├── qa/decoupling_x16_regressions.py # cross-page ownership/source freeze
└── tools/performance_compare.py    # Qt-free opt-in trace comparator
```

The 10 presentation builders have one owner each. The original `SuiteWindow` entry points remain simple forwarding methods, with existing tracing decorators. The Store backend, repository refresh, download security checks, installer orchestration, active versions and removal remain untouched. The shared identity-header and Store-enrichment delegates eliminate the need for a duplicate UI implementation.

x1.6 reduces imports in the shell that are no longer consumed after the x1.1–x1.5 moves. No call graph or behavior changes. Existing historical source tests still use live extracted builder bodies; new x1.6 QA guards against accidental parallel implementations and compares the unmodified production tree to issued x1.5.

Any future **x2** ownership/control extraction requires a separately approved scope and desktop acceptance evidence; do not assume that static checks alone prove GUI/performance parity.
