"""Build canonical Nation documents from the ships we just ingested.

Nations aren't first-class entries in GameParams — they only appear as
`typeinfo.nation` strings on Ship entries. We collect the distinct raw
names during ship iteration, then for each one:
  - map it to our slug (matches `Ship.nation`)
  - look up `IDS_<RAW_UPPERCASE>` in the locale catalogs for the display name
  - the ingest layer separately promotes the matching `flag_<RAW>.png` files

Same fail-loudly stance as ship normalisation: an unknown raw nation falls
through to `raw.lower()`, but the locale lookup is best-effort (some
event/pseudo nations don't have an IDS_ entry — `name_i18n` ends up empty)."""
from __future__ import annotations

from . import locale
from .models import Nation
from .normalize_ship import _wg_nation


def normalise_nation(
    raw_name: str,
    translations: dict[str, dict[str, str]] | None = None,
) -> Nation:
    key = _wg_nation(raw_name)
    name_i18n = locale.translate(translations, f"IDS_{raw_name.upper()}") if translations else {}
    return Nation(
        key=key,
        raw_name=raw_name,
        name=name_i18n.get("en") or key,
        name_i18n=name_i18n,
    )
