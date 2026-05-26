"""Map raw GameParams Exterior entries (signals + camos + permoflags).

All three exterior families share `typeinfo.type == "Exterior"` and differ
only by `typeinfo.species` (`Flags`, `Camouflage`, `Permoflage`). The integer
`id` per entry is what surfaces as a `source` in post-battle economy modifier
rows for flag/camo-granted bonuses; that's the join key the replay parser
resolves via `GAME_PARAMS_BY_ID`.

Locale convention is `IDS_<UPPER(name)>` / `IDS_<UPPER(name)>_DESCRIPTION`
(e.g. `IDS_PCEF005_SM_SIGNALFLAG` / `IDS_PCEF005_SM_SIGNALFLAG_DESCRIPTION`).
"""
from __future__ import annotations

from typing import Any, Iterable

from . import locale
from .models import Exterior


def iter_exteriors(gameparams: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for name, entry in gameparams.items():
        if not isinstance(entry, dict):
            continue
        ti = entry.get("typeinfo")
        if isinstance(ti, dict) and ti.get("type") == "Exterior":
            yield name, entry


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def normalise_exterior(
    internal_name: str,
    raw: dict[str, Any],
    translations: dict[str, dict[str, str]] | None = None,
) -> Exterior:
    key_upper = internal_name.upper()
    name_i18n = locale.translate(translations or {}, f"IDS_{key_upper}")
    desc_i18n = locale.translate(translations or {}, f"IDS_{key_upper}_DESCRIPTION")

    species = (raw.get("typeinfo") or {}).get("species") or "Unknown"

    cost_cr = raw.get("costCR")
    cost_gold = raw.get("costGold")

    return Exterior(
        id=int(raw["id"]),
        internal_name=internal_name,
        kind=str(species),
        name=name_i18n.get("en") or internal_name,
        name_i18n=name_i18n,
        description=desc_i18n.get("en", ""),
        description_i18n=desc_i18n,
        group=raw.get("group") or None,
        tags=[str(t) for t in _as_list(raw.get("tags"))],
        cost_credits=int(cost_cr) if isinstance(cost_cr, (int, float)) else None,
        cost_gold=int(cost_gold) if isinstance(cost_gold, (int, float)) else None,
        modifiers=dict(raw.get("modifiers") or {}),
    )
