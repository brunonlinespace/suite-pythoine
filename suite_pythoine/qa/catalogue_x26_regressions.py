"""x2.6: strictly eight missing GitHub catalogue declarations, no contract changes."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from suite_pythoine.catalogue.component_catalog import BUNDLED_CATALOG_PATH, catalog_revision, load_catalog
from suite_pythoine.store.store_bridge import trusted_catalogue_projection

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_ADDITIONS = {'texypad': 'brunonlinespace/texypad', 'kapitulindo': 'brunonlinespace/kapitulindo', 'beespector-lite': 'brunonlinespace/beespector-lite', 'crawlindo': 'brunonlinespace/crawlindo', 'youlindo': 'brunonlinespace/youlindo', 'sbookypad': 'brunonlinespace/sbookypad', 'gitten': 'brunonlinespace/gitten', 'python-lair': 'brunonlinespace/python-lair'}
ORIGINAL_DECLARATIONS = {'suite-pythoine': 'brunonlinespace/suite-pythoine', 'maqaronypad': 'brunonlinespace/maqaronypad', 'markopad': 'brunonlinespace/markopad', 'nuxpad': 'brunonlinespace/nuxpad.py', 'riqatonypad': 'brunonlinespace/riqatonypad', 'ricopad': 'brunonlinespace/ricopad', 'sheepy-pad': 'brunonlinespace/sheepy-pad', 'timblee-pad': 'brunonlinespace/timblee-pad', 'jsts-pad': 'brunonlinespace/jsts-pad', 'portapad': 'brunonlinespace/portapad', 'beespector': 'brunonlinespace/beespector', 'linspectacles': 'linspectacles', 'maqaronydesk': 'brunonlinespace/maqaronydesk', 'marko-plus': 'brunonlinespace/marko-plus', 'riqatonydesk': 'brunonlinespace/riqatonydesk', 'rico-plus': 'brunonlinespace/rico-plus', 'store-pythoine': 'brunonlinespace/store-pythoine'}
NON_REPOSITORY_FINGERPRINT = "20ec8ae0cd3ee5fe38b0fbf2b0cc452de90e3bf78b18881989f8f005c1fa21f5"
READ_ME_SHA256 = "392895da769ac770766a7338081f50be349e7af72892682758f26fe94d23ea95"
LICENSE_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"


def run_regressions(errors: list[str]) -> None:
    def check(what: bool, reason: str) -> None:
        if not what: errors.append('1.0.0-x2.6 catalogue-only correction: ' + reason)

    raw = json.loads(BUNDLED_CATALOG_PATH.read_text(encoding='utf-8'))
    rows = raw['components']
    check(raw['catalog_revision'] == 12 and catalog_revision(BUNDLED_CATALOG_PATH) == 12,
          'bundled catalogue revision not advanced to 12')
    check(len(rows) == 25 and len({r['id'] for r in rows}) == 25,
          'catalogue identity count changed')
    without_repository = [{k: v for k, v in r.items() if k != 'repository'} for r in rows]
    digest = hashlib.sha256(json.dumps(without_repository, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    check(digest == NON_REPOSITORY_FINGERPRINT,
          'a non-repository component field was modified')
    by_id = {r['id']:r for r in rows}
    for ident, value in EXPECTED_ADDITIONS.items():
        check(by_id.get(ident, {}).get('repository') == value,
              f'missing or unexpected new repository: {ident}')
    for ident, value in ORIGINAL_DECLARATIONS.items():
        check(by_id.get(ident, {}).get('repository') == value,
              f'previously declared repository modified: {ident}')
    check(set(by_id) == set(EXPECTED_ADDITIONS) | set(ORIGINAL_DECLARATIONS),
          'catalogue identities or repository assignment scope changed')
    profiles = load_catalog(BUNDLED_CATALOG_PATH)
    for ident, value in EXPECTED_ADDITIONS.items():
        check(profiles[ident].repository == value, f'loader lost repository: {ident}')
    projection = trusted_catalogue_projection()
    exported = {r['component_id']:r for r in projection['components']}
    for ident, value in EXPECTED_ADDITIONS.items():
        check(exported.get(ident, {}).get('repository') == value,
              f'Store authorization projection missing repository: {ident}')
    check(hashlib.sha256((ROOT/'README.md').read_bytes()).hexdigest() == READ_ME_SHA256,
          'immutable root README changed')
    check(hashlib.sha256((ROOT/'LICENSE').read_bytes()).hexdigest() == LICENSE_SHA256,
          'root LICENSE changed')
    print('PASS: x2.6 eight GitHub repository declarations, revision 12 and immutable repository files'
          if not any('1.0.0-x2.6 catalogue-only correction:' in e for e in errors) else
          'CHECK: x2.6 catalogue-only correction')
