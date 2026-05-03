"""Map raw GameParams Ship entries to canonical Ship documents.

Every field is pulled explicitly. Source-shape changes (renamed key, removed
field, unexpected enum value) raise — the goal is to fail the whole ingest
loudly the moment WG ships something we haven't accounted for, rather than
silently emit nulls and break clients downstream.

The shape of Ship is defined in extractor/models.py and is what the API
serves directly.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import locale
from .models import Ship, ShipType

_SPECIES_TO_TYPE: dict[str, ShipType] = {
    "Battleship": ShipType.BATTLESHIP,
    "Cruiser": ShipType.CRUISER,
    "Destroyer": ShipType.DESTROYER,
    "AirCarrier": ShipType.AIRCARRIER,
    "Submarine": ShipType.SUBMARINE,
    "Auxiliary": ShipType.AUXILIARY,
}

# GameParams' nation strings → our taxonomy. Most ships use one of these;
# unknown values pass through lowercased so the ingest doesn't crash on a
# brand-new nation, but we'll see them in the data and can curate the table.
_NATION_TO_WG: dict[str, str] = {
    "Russia": "ussr",
    "Pan_America": "pan_america",
    "Pan_Asia": "pan_asia",
    "Commonwealth": "commonwealth",
    "United_Kingdom": "uk",
    "USA": "usa",
    "Japan": "japan",
    "Germany": "germany",
    "France": "france",
    "Italy": "italy",
    "Poland": "poland",
    "Spain": "spain",
    "Netherlands": "netherlands",
    "Europe": "europe",
}


def _wg_nation(raw: str) -> str:
    return _NATION_TO_WG.get(raw, raw.lower())


def _species_to_type(raw: str) -> ShipType:
    try:
        return _SPECIES_TO_TYPE[raw]
    except KeyError as e:
        raise ValueError(f"unknown ship species {raw!r}; add to _SPECIES_TO_TYPE") from e


def iter_ships(gameparams: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for name, entry in gameparams.items():
        if not isinstance(entry, dict):
            continue
        ti = entry.get("typeinfo")
        if isinstance(ti, dict) and ti.get("type") == "Ship":
            yield name, entry


def normalise_ship(
    internal_name: str,
    raw: dict[str, Any],
    translations: dict[str, dict[str, str]] | None = None,
) -> Ship:
    # Required fields read with []: missing key = patch broke our assumptions,
    # we want a hard fail with the offending ship's name.
    ti = raw["typeinfo"]
    short = raw["index"]
    name_key = f"IDS_{short.upper()}"

    name_i18n = locale.translate(translations, name_key) if translations else {}
    descr_i18n = locale.translate(translations, f"{name_key}_DESCR") if translations else {}

    return Ship(
        id=raw["id"],
        short_id=short,
        internal_name=internal_name,
        name=name_i18n.get("en") or internal_name,
        name_i18n=name_i18n,
        description=descr_i18n.get("en", ""),
        description_i18n=descr_i18n,
        tier=raw["level"],
        nation=_wg_nation(ti["nation"]),
        type=_species_to_type(ti["species"]),
        is_premium=bool(raw.get("isPaperShip") or raw.get("isPremium")),
        is_special=bool(raw.get("isSpecial")),
        has_demo_profile=bool(raw.get("isDemoShip")),
        price_credit=raw.get("costCR"),
        price_gold=raw.get("costGold"),
        mod_slots=raw.get("modSlots"),
    )
