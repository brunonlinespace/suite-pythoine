"""0.9.3 trusted catalogue icon fallback regressions."""
from __future__ import annotations

import hashlib
from pathlib import Path

from suite_pythoine.catalogue.component_catalog import bundled_catalog_icon_path


EXPECTED = {
    "portapad": ("portapad.png", "159aa17f552dde3adfaf9b5cf42e692f099f13fb3a8a7610aecaca38c7bc06e6"),
    "ricopad": ("ricopad.png", "9c7f2f64aa65b1f7f4039ac327ee8860f421e34247d5d763fa5c15cda4fc2ff5"),
    "kapitulindo": ("kapitulindo.png", "ecad81b7884a9252fbb286599700ee91c815d56fa55f6c0299f71040c2ebacee"),
    "sheepy-pad": ("sheepy-pad.png", "cd65ced104b6d6da4bd8987372cd0583446c31ff168deb1ef4c987a80fde0078"),
    "timblee-pad": ("timblee-pad.svg", "8036f12b61e2f6776487ae635805428e82c04a21a00c26a6849f12d1156a300f"),
    "jsts-pad": ("jsts-pad.svg", "e5362faf99fc4406ed2ad1514f724c548d7deadc5e1e5a51a5906638fd74cc2a"),
    "markopad": ("markopad.png", "14e86eb89a52024379e61277aac6c3f7a4c976fe6baf46c408931bd0f5935c3f"),
    "rico-plus": ("rico-plus.png", "0aa61398556f029c8ee343b48d351c17b66fd82f8ce0c8b9801c97e07fbea882"),
    "marko-plus": ("marko-plus.png", "22a09047102f543744843917d42c76be48cee58b360afb91b6acd2779e9dfd3c"),
    "python-lair": ("python-lair.png", "76d06c88c4c48960047ae2197a89193da3ae7e224cb24d14b2cc08a624522bdf"),
    "beespector": ("beespector.png", "b4181a9134087442840e5161879674bc31969c8ed278885d6fdc36d053ebfd48"),
    "beespector-lite": ("beespector-lite.png", "bfd809c9099e4ba55ff560328c2b7644214c895d92407f178a06e641a5fa4898"),
    "nuxpad": ("nuxpad.png", "4fbd994d213b5fbcd4cb66e91f514e5ade9a3c13a4b33b739d8d97d7f8ead984"),
    "texypad": ("texypad.png", "8475cc3d7416fb33d80f580bc88176266ff6d9add8d36c3f4ca83d68fadf9af1"),
}


def run_regressions(errors: list[str]) -> None:
    def require(truth: bool, message: str) -> None:
        if not truth:
            errors.append("0.9.3 corrections: " + message)

    hashes: set[str] = set()
    for component_id, (filename, expected_hash) in EXPECTED.items():
        icon = bundled_catalog_icon_path(component_id)
        require(icon is not None, f"missing trusted fallback for {component_id}")
        if icon is None:
            continue
        require(icon.name == filename, f"wrong fallback filename for {component_id}: {icon.name}")
        require(icon.is_file() and not icon.is_symlink(), f"unsafe fallback asset for {component_id}")
        digest = hashlib.sha256(icon.read_bytes()).hexdigest()
        require(digest == expected_hash, f"fallback asset changed for {component_id}")
        hashes.add(digest)
    require(len(hashes) == len(EXPECTED), "catalogue fallbacks were aliased/deduplicated")

    # The Hub and unknown identities must never borrow another application's logo.
    # Additional trusted app identities gained their own curated assets in 0.11-exp3.1.
    require(bundled_catalog_icon_path("suite-pythoine") is None, "Hub unexpectedly received an application fallback icon")
    require(bundled_catalog_icon_path("definitely-unknown") is None, "unknown identity received a fallback icon")

    package = Path(__file__).resolve().parent.parent
    wizard = (package / "appimage_wizard.py").read_text(encoding="utf8")
    require("existing_icon or bundled_catalog_icon_path(inspection.editor_id)" in wizard,
            "direct AppImage wizard does not preserve existing/Portable icon precedence before catalogue fallback")
    require("Application icon source: trusted catalogue fallback" in wizard,
            "direct AppImage technical details do not identify catalogue fallback use")
    require("no portable/source or trusted catalogue fallback available" in wizard,
            "direct AppImage no-icon diagnostic does not reflect the fallback chain")

    catalog = (package / "components.json").read_text(encoding="utf8")
    require('"icon"' not in catalog and '"icon_path"' not in catalog,
            "0.9.3 unexpectedly added icon paths to the replaceable catalogue schema")

    builder = (package / "packaging" / "fedora" / "build-appimage.sh").read_text(encoding="utf8")
    require('--add-data "${VERIFIED_SOURCE}/suite_pythoine/assets:suite_pythoine/assets"' in builder,
            "frozen Hub build no longer includes bundled catalogue assets")

    print("PASS: 0.9.3 distinct trusted catalogue icon fallbacks and AppImage-only precedence")
