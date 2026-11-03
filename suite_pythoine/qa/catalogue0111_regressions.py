"""0.11.1 trusted catalogue additions and supported Legacy products (Qt-free)."""
from __future__ import annotations
from .extracted_page_sources import read_app_with_presentations

import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from suite_pythoine.catalogue.component_catalog import (
    COMPONENT_PROFILES, BUNDLED_CATALOG_PATH, bundled_catalog_icon_path,
    catalog_revision, load_catalog, catalog_fingerprint, extension_union, mime_type_union,
)
from suite_pythoine.registry import _profile_for, builtin_profiles
from suite_pythoine.store.store_bridge import trusted_catalogue_projection
from suite_pythoine.routing.routing_index import RoutingTarget
from suite_pythoine.routing.silent_dispatch import document_candidates

PACKAGE = Path(__file__).resolve().parent.parent
PAIRS = (
    ("ricopad", "riqatonypad", "editor", (".rtf",)),
    ("markopad", "maqaronypad", "editor", (".md", ".markdown", ".mdown", ".mkd")),
    ("rico-plus", "riqatonydesk", "extension", ()),
    ("marko-plus", "maqaronydesk", "extension", ()),
)


def run_regressions(errors: list[str]) -> None:
    prefix = "0.11.1 product-catalogue: "

    def check(ok: bool, message: str) -> None:
        if not ok:
            errors.append(prefix + message)

    check(catalog_revision(BUNDLED_CATALOG_PATH) >= 11, "bundled revision must not regress below 11")
    profiles = load_catalog()
    check(set(profiles) == set(COMPONENT_PROFILES) and len(profiles) == 25,
          "old trusted applications were dropped or new ones are missing")
    check(catalog_fingerprint(profiles) == catalog_fingerprint(COMPONENT_PROFILES),
          "trusted catalogue fingerprint was not kept deterministic")
    for prior, replacement, kind, formats in PAIRS:
        check(prior in profiles and replacement in profiles,
              f"missing predecessor/successor: {prior}/{replacement}")
        if prior not in profiles or replacement not in profiles:
            continue
        old, new = profiles[prior], profiles[replacement]
        check(old.lifecycle == 'legacy' and new.lifecycle == 'current',
              f"incorrect lifecycle: {prior}/{replacement}")
        check(old.kind == new.kind == kind and old.extensions == new.extensions == formats,
              f"kind/format drift: {prior}/{replacement}")
        check(old.publisher_id == new.publisher_id == 'brunonlinespace',
              f"untrusted publisher: {prior}/{replacement}")
        check(old.component_id != new.component_id and old.config_subdir != new.config_subdir,
              f"installation identity collision: {prior}/{replacement}")
        check(old.identity_hints and new.identity_hints and
              not set(map(str.casefold, old.identity_hints)) & set(map(str.casefold, new.identity_hints)),
              f"identity alias collision: {prior}/{replacement}")
        check(old.appimage_prefixes and new.appimage_prefixes and
              not set(map(str.casefold, old.appimage_prefixes)) & set(map(str.casefold, new.appimage_prefixes)),
              f"AppImage prefix collision: {prior}/{replacement}")
        check(old.capabilities == new.capabilities,
              f"capability compatibility changed: {prior}/{replacement}")
        if kind == 'editor':
            check(old.is_routable and new.is_routable and old.can_create and new.can_create,
                  f"Pad routing or create disabled: {prior}/{replacement}")
        else:
            check(not old.is_routable and not new.is_routable and not new.can_create,
                  f"Desk unexpectedly granted file routing: {replacement}")
        check(bundled_catalog_icon_path(prior) is not None and
              bundled_catalog_icon_path(replacement) is not None,
              f"catalogue icons absent: {prior}/{replacement}")
        # Explicit manifest IDs take precedence over folder/name fallback matching.
        for component in (old, new):
            cid, _profile = _profile_for(Path('UnrelatedName'), {'id': component.component_id, 'name': component.name})
            check(cid == component.component_id, f"declared manifest identity changed: {component.component_id}")
        # Compatible historic folder/name-only packages remain recognizable too.
        for component in (old, new):
            cid, _profile = _profile_for(Path(component.component_id), {})
            check(cid == component.component_id, f"name-only identity regressed: {component.component_id}")

    check(all(profile.lifecycle == 'current' for component_id, profile in profiles.items()
              if component_id not in {old for old, _, _, _ in PAIRS}),
          "non-legacy applications were incorrectly downgraded")
    for ext in ('.rtf','.md','.markdown','.mdown','.mkd'):
        check(ext in extension_union(), f"format union missing {ext}")
    for media in ('text/rtf','application/rtf','text/markdown'):
        check(media in mime_type_union(), f"MIME union missing {media}")

    # Check that preferences can still select either product independently, while
    # ambiguous formats must use the existing chooser rather than prefer a successor.
    for prior, replacement, kind, formats in PAIRS[:2]:
        old, new = profiles[prior], profiles[replacement]
        targets = [RoutingTarget(x.component_id, x.name, x.kind, x.extensions,
                                 'auto', ('python3', '/app/main.py'), None,
                                 Path('/tmp/nonexecuting'), '1.0', x.capabilities)
                   for x in (old,new)]
        choices = document_candidates(targets, formats[0])
        check({item.component_id for item in choices} == {prior,replacement},
              f"routing chooser cannot see both Pads: {prior}/{replacement}")
        for preference in (prior,replacement):
            preferred = next((candidate for candidate in choices
                              if candidate.component_id == preference), None)
            check(preferred is not None and preferred.component_id == preference,
                  f"routing preference cannot retain choice: {preference}")

    projection = trusted_catalogue_projection()
    shown = {item['component_id']:item for item in projection['components']}
    check(len(shown)==len(profiles), "Store dropped catalogue identities")
    for ident, profile in profiles.items():
        check(shown.get(ident, {}).get('lifecycle') == profile.lifecycle,
              f"Store lost product lifecycle: {ident}")

    # Separate Legacy product lifecycle from `EditorVersionInfo.legacy`, which
    # diagnoses version metadata fallback and must never be used for product badges.
    from suite_pythoine.registry import EditorVersionInfo
    check(EditorVersionInfo('1.0').legacy is False and profiles['ricopad'].lifecycle == 'legacy',
          'product Legacy was conflated with version metadata fallback')

    # Schema-1 independently verified catalogues remain compatible; absent
    # lifecycle defaults to current and malformed lifecycle cannot be injected.
    payload=json.loads(BUNDLED_CATALOG_PATH.read_text(encoding='utf-8'))
    with TemporaryDirectory(prefix='suite-0111-catalogue-') as folder:
        path=Path(folder)/'components.json'
        copy=json.loads(json.dumps(payload))
        copy['components'][0].pop('lifecycle',None)
        path.write_text(json.dumps(copy), encoding='utf-8')
        check(load_catalog(path)['suite-pythoine'].lifecycle == 'current',
              'schema-1 catalogues without lifecycle lost compatibility')
        copy['components'][0]['lifecycle']='archived'
        path.write_text(json.dumps(copy), encoding='utf-8')
        try:
            load_catalog(path)
        except ValueError:
            pass
        else:
            check(False, 'untrusted lifecycle status was accepted')

    app=read_app_with_presentations()
    board=(PACKAGE/'ui/shell/dashboard.py').read_text(encoding='utf-8')
    check('profile.lifecycle == "legacy"' in app and '· Legacy' in app and
          'Product lifecycle: Legacy' in app, 'Legacy missing from installed/inactive App Pages')
    check('profile.lifecycle == "legacy"' in board and '· Legacy' in board,
          'Legacy missing from Dashboard cards')
    check('profile.component_id not in installed_ids' in app,
          'Get More catalogue no longer separates installed/uninstalled IDs')
    check('self.install_editor_zip(candidate)' in app and
          'inspection.editor_id != profile.component_id' in app,
          'Get More install no longer requires identity match')

    print('PASS: 0.11.1 new/legacy catalogue identity, visual status, routing and Store regressions'
          if not any(item.startswith(prefix) for item in errors)
          else 'CHECK: 0.11.1 catalogue regressions')
