"""Build canonical ShipTypeInfo documents from the species we saw on ships.

Like nations, ship types aren't first-class GameParams entries — they exist
only as `typeinfo.species` strings on Ship entries. We collect the distinct
raw species during ship iteration and look up `IDS_<SPECIES_UPPERCASE>` in
the locale catalogs for the display label (e.g. `IDS_AIRCARRIER` → "Aircraft
Carrier", localised per language).

Locale lookup is best-effort; if a future species lacks an IDS_ entry the
ingest still succeeds with `name_i18n={}` and `name` falling back to the key.
"""
from __future__ import annotations

from . import locale
from .models import ShipTypeInfo, ShipTypeIcons


def normalise_ship_type(
    species: str,
    translations: dict[str, dict[str, str]] | None = None,
) -> ShipTypeInfo:
    name_i18n = locale.translate(translations, f"IDS_{species.upper()}") if translations else {}
    return ShipTypeInfo(
        key=species,
        name=name_i18n.get("en") or species,
        name_i18n=name_i18n,
        icons=ShipTypeIcons(),
    )
