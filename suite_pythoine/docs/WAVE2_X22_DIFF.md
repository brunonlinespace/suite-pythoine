# 1.0.0-x2.2 — CODE PRESERVATION TRANSFER

Baseline: 1.0.0-x2.1. Two implementation modules relocated without redesign.

- `suite_pythoine/component_catalog.py` → `suite_pythoine/catalogue/component_catalog.py`
- `suite_pythoine/component_policy.py` → `suite_pythoine/catalogue/component_policy.py`
- Added empty `catalogue/__init__.py`.
- Adapted two `__file__` resource expressions only to preserve exact `components.json` and `assets/catalog/` locations.
- Updated the imports of 19 existing production modules; their other source bytes are identical.
- Historical regression tests follow the relocated paths and preserve their original assertions.
- `WAVE2_X22_TRANSFER.json` freezes every x2.1 production hash and explicitly lists every permitted line edit.
- Root `README.md` and `LICENSE` remain unchanged.
- No functionality intentionally changed. GUI and AppImage runtime behavior remain unverified outside the static tests.
