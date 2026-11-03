"""1.0.0-x1.8: immutable GitHub README, exact user license and clean repository root."""
from __future__ import annotations
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCKED_README_SHA256 = "392895da769ac770766a7338081f50be349e7af72892682758f26fe94d23ea95"
UPLOADED_LICENSE_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"


def run_regressions(errors: list[str]) -> None:
    def check(condition: bool, detail: str) -> None:
        if not condition:
            errors.append("1.0.0-x1.8 repository contract: " + detail)

    readme = ROOT / "README.md"
    license_path = ROOT / "LICENSE"
    copying = ROOT / "COPYING"
    check(readme.is_file(), "missing immutable root README.md")
    if readme.is_file():
        raw = readme.read_bytes()
        check(hashlib.sha256(raw).hexdigest() == LOCKED_README_SHA256,
              "immutable root README.md was modified")
        for text in ("MaqaronyPad", "MaqaronyDesk", "RiqatonyPad", "RiqatonyDesk",
                     "github.com/brunonlinespace/maqaronypad",
                     "github.com/brunonlinespace/maqaronydesk",
                     "github.com/brunonlinespace/riqatonypad",
                     "github.com/brunonlinespace/riqatonydesk"):
            check(text.encode() in raw, "README missing " + text)
        for text in ("Markopad", "Marko Plus", "Ricopad", "Rico Plus", "/markopad",
                     "/marko-plus", "/ricopad", "/rico-plus", "Plus"):
            check(text.encode() not in raw, "README contains retired text " + text)
    check(license_path.is_file(), "missing root LICENSE")
    if license_path.is_file():
        check(hashlib.sha256(license_path.read_bytes()).hexdigest() == UPLOADED_LICENSE_SHA256,
              "root LICENSE does not match supplied license")
        check(copying.is_file() and license_path.read_bytes() == copying.read_bytes(),
              "existing operational COPYING must be preserved")
    check((ROOT / '.gitignore').is_file(), 'missing root .gitignore')
    check((ROOT / 'suite_pythoine/docs/README.md').is_file(),
          'existing in-app documentation path must remain')
