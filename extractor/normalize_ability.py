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

Locale convention is `IDS_DOCK_CONSUME_TITLE_<UPPER(name)>` for the title
and `IDS_DOCK_CONSUME_DESCRIPTION_<UPPER(name)>` for the description.
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


def normalise_ability(
    internal_name: str,
    raw: dict[str, Any],
    translations: dict[str, dict[str, str]] | None = None,
) -> Ability:
    key_upper = internal_name.upper()
    name_i18n = locale.translate(translations or {}, f"IDS_DOCK_CONSUME_TITLE_{key_upper}")
    desc_i18n = locale.translate(translations or {}, f"IDS_DOCK_CONSUME_DESCRIPTION_{key_upper}")

    return Ability(
        id=int(raw["id"]),
        internal_name=internal_name,
        name=name_i18n.get("en") or internal_name,
        name_i18n=name_i18n,
        description=desc_i18n.get("en", ""),
        description_i18n=desc_i18n,
        group=raw.get("group") or None,
        tags=[str(t) for t in _as_list(raw.get("tags"))],
        variants=dict(raw.get("abilities") or {}),
    )
