"""Map raw GameParams Modernization entries to canonical Modernization docs.

Modernizations are slot upgrades (Engine Boost Mod 1, Concealment System Mod 1,
…). The integer `id` WG assigns to each is what surfaces as a `source` in the
post-battle `subtotal_economics` stream when an upgrade granted a modifier;
that's the join key the replay parser uses via `GAME_PARAMS_BY_ID`.

Locale convention is `IDS_<UPPER(name)>` / `IDS_<UPPER(name)>_DESCR`. WG uses
the GameParams record key (`PCM001_DamageControl_Mod_I`) as-is for the
uppercase form.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import locale
from .models import Modernization


def iter_modernizations(gameparams: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for name, entry in gameparams.items():
        if not isinstance(entry, dict):
            continue
        ti = entry.get("typeinfo")
        if isinstance(ti, dict) and ti.get("type") == "Modernization":
            yield name, entry


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def normalise_modernization(
    internal_name: str,
    raw: dict[str, Any],
    translations: dict[str, dict[str, str]] | None = None,
) -> Modernization:
    key_upper = internal_name.upper()
    name_i18n = locale.translate(translations or {}, f"IDS_{key_upper}")
    desc_i18n = locale.translate(translations or {}, f"IDS_{key_upper}_DESCR")

    slot_raw = raw.get("slot")
    slot = int(slot_raw) if isinstance(slot_raw, (int, float)) else None

    price_credit = raw.get("costCR")
    price_gold = raw.get("costGold")

    return Modernization(
        id=int(raw["id"]),
        internal_name=internal_name,
        name=name_i18n.get("en") or internal_name,
        name_i18n=name_i18n,
        description=desc_i18n.get("en", ""),
        description_i18n=desc_i18n,
        slot=slot,
        group=raw.get("group") or None,
        tags=[str(t) for t in _as_list(raw.get("tags"))],
        ship_level=[int(v) for v in _as_list(raw.get("shiplevel")) if isinstance(v, (int, float))],
        ship_restrictions=[str(s) for s in _as_list(raw.get("ships"))],
        nation_restrictions=[str(s) for s in _as_list(raw.get("nation"))],
        species_restrictions=[str(s) for s in _as_list(raw.get("shiptype"))],
        price_credit=int(price_credit) if isinstance(price_credit, (int, float)) else None,
        price_gold=int(price_gold) if isinstance(price_gold, (int, float)) else None,
        modifiers=dict(raw.get("modifiers") or {}),
    )
