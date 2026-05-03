"""Build canonical Ribbon and SubRibbon documents from the scripts_enums catalog.

Ribbons aren't part of GameParams — the authoritative enum lives in the
client scripts as the `Ribbon` and `SubRibbon` classes. Their home module
is obfuscated and renamed every patch, so `tools/dump_scripts_enums.py`
locates the classes by name (`find_class` pattern) and dumps every
class-level instance into `scripts_enums.json` under the `ribbon` and
`subribbon` keys. We just consume that here — no checked-in fallback.

Each entry carries its `ids` string (`RIBBON_MAIN_CALIBER`,
`SUBRIBBON_MAIN_CALIBER_PENETRATION`, …) so we look those up in `global.mo`
directly. A handful of subribbons share their `IDS_*` key with the parent
ribbon (the legacy single-subribbon case), which is fine — the lookup just
returns the same translation twice.
"""
from __future__ import annotations

from typing import Iterable

from . import locale
from .models import Ribbon, SubRibbon


def _build_parent_index(ribbons: list[dict]) -> dict[int, int]:
    """Map subribbon.id → parent ribbon.id, derived from `subRibbons` lists.

    Subribbons not referenced by any ribbon (the legacy id-aligned duplicates
    such as MAIN_CALIBER id=0) get no entry — the caller leaves
    `parent_ribbon_id` as None for those."""
    parent: dict[int, int] = {}
    for r in ribbons:
        for sub_id in r.get("subRibbons", []):
            parent[sub_id] = r["id"]
    return parent


def iter_ribbons(
    catalog: dict,
    translations: dict[str, dict[str, str]] | None = None,
) -> Iterable[Ribbon]:
    for row in catalog["ribbon"]["entries"]:
        ids_key = row["ids"]
        name_i18n = (
            locale.translate(translations, f"IDS_RIBBON_{ids_key}")
            if translations else {}
        )
        yield Ribbon(
            id=row["id"],
            const_name=row["const_name"],
            ids_key=ids_key,
            name=name_i18n.get("en") or row["const_name"],
            name_i18n=name_i18n,
            icon_name=row["iconName"],
            subribbon_ids=list(row.get("subRibbons", [])),
        )


def iter_subribbons(
    catalog: dict,
    translations: dict[str, dict[str, str]] | None = None,
) -> Iterable[SubRibbon]:
    parent_index = _build_parent_index(catalog["ribbon"]["entries"])
    for row in catalog["subribbon"]["entries"]:
        ids_key = row["ids"]
        name_i18n = (
            locale.translate(translations, f"IDS_RIBBON_{ids_key}")
            if translations else {}
        )
        # Legacy id-aligned subribbons (MAIN_CALIBER, TORPEDO, …) have no
        # `IDS_RIBBON_SUBRIBBON_*` entry — they share their label with the
        # parent ribbon, so fall back to the ribbon-level key.
        if not name_i18n and translations:
            name_i18n = locale.translate(
                translations, f"IDS_RIBBON_RIBBON_{row['const_name']}"
            )
        yield SubRibbon(
            id=row["id"],
            const_name=row["const_name"],
            ids_key=ids_key,
            parent_ribbon_id=parent_index.get(row["id"]),
            name=name_i18n.get("en") or row["const_name"],
            name_i18n=name_i18n,
            icon_name=row["iconName"],
        )
