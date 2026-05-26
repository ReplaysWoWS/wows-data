"""Map raw GameParams Ability entries (consumables) to canonical Ability docs.

Consumables (Damage Control Party, Repair Party, Hydro Acoustic Search, …)
have `typeinfo.type == "Ability"`. Each carries a parent integer `id` that
shows up as the `source` for consumable-granted modifier rows in the
post-battle economy stream.

Each Ability record bundles one or more lettered sub-variants under
`abilities` — different durations/cooldowns for stock vs. premium versions
of the same consumable. The sub-variants don't get their own GameParams id,
so we collapse the record around the parent id and surface the raw variant
dict verbatim for callers that need it.

Locale keys are scoped to a *variant*, not the parent record:
`IDS_DOCK_CONSUME_TITLE_<UPPER(parent)>_<UPPER(variant_key)>` and the
matching `..._DESCRIPTION_...` form (e.g. `PCY001` + variant `CrashCrew`
→ `IDS_DOCK_CONSUME_TITLE_PCY001_CRASHCREW`). The parent record has no
locale entry of its own, so we walk the `abilities` dict and use the
first variant that resolves as the canonical name/description.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import locale
from .models import Ability


def iter_abilities(gameparams: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for name, entry in gameparams.items():
        if not isinstance(entry, dict):
            continue
        ti = entry.get("typeinfo")
        if isinstance(ti, dict) and ti.get("type") == "Ability":
            yield name, entry


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _resolve_ability_locale(
    parent_upper: str,
    variants: dict[str, Any],
    translations: dict[str, dict[str, str]],
    *,
    description: bool,
) -> dict[str, str]:
    """Walk the variant dict and return the first variant whose locale key resolves.

    WG never localises the parent record itself — only its lettered
    sub-variants. We pick the first variant (in dict order) that has a
    catalog entry so the resulting `name_i18n` / `description_i18n`
    isn't empty just because we hit a private/internal variant first."""
    field = "DESCRIPTION" if description else "TITLE"
    for variant_key in variants:
        if not isinstance(variant_key, str):
            continue
        key = f"IDS_DOCK_CONSUME_{field}_{parent_upper}_{variant_key.upper()}"
        hit = locale.translate(translations, key)
        if hit:
            return hit
    return {}


def normalise_ability(
    internal_name: str,
    raw: dict[str, Any],
    translations: dict[str, dict[str, str]] | None = None,
) -> Ability:
    key_upper = internal_name.upper()
    variants = dict(raw.get("abilities") or {})
    name_i18n = _resolve_ability_locale(key_upper, variants, translations or {}, description=False)
    desc_i18n = _resolve_ability_locale(key_upper, variants, translations or {}, description=True)

    return Ability(
        id=int(raw["id"]),
        internal_name=internal_name,
        name=name_i18n.get("en") or internal_name,
        name_i18n=name_i18n,
        description=desc_i18n.get("en", ""),
        description_i18n=desc_i18n,
        group=raw.get("group") or None,
        tags=[str(t) for t in _as_list(raw.get("tags"))],
        variants=variants,
    )
