"""Map raw GameParams Achievement entries to canonical Achievement docs.

Locale keys follow the pattern `IDS_ACHIEVEMENT_<UI_NAME>` for the title and
`IDS_ACHIEVEMENT_DESCRIPTION_<UI_NAME>` for the description. Achievements
without locale entries (typically test or hidden ones) come through with
`name` falling back to `ui_name` and an empty `description`.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import locale
from .models import Achievement


def iter_achievements(gameparams: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for name, entry in gameparams.items():
        if not isinstance(entry, dict):
            continue
        ti = entry.get("typeinfo")
        if isinstance(ti, dict) and ti.get("type") == "Achievement":
            yield name, entry


def normalise_achievement(
    internal_name: str,
    raw: dict[str, Any],
    translations: dict[str, dict[str, str]] | None = None,
) -> Achievement:
    ui_name = raw["uiName"]
    name_i18n = (
        locale.translate(translations, f"IDS_ACHIEVEMENT_{ui_name}")
        if translations and ui_name else {}
    )
    descr_i18n = (
        locale.translate(translations, f"IDS_ACHIEVEMENT_DESCRIPTION_{ui_name}")
        if translations and ui_name else {}
    )
    return Achievement(
        id=raw["id"],
        internal_name=internal_name,
        ui_name=ui_name,
        name=name_i18n.get("en") or ui_name or internal_name,
        name_i18n=name_i18n,
        description=descr_i18n.get("en", ""),
        description_i18n=descr_i18n,
        type=raw["type"],
        ui_type=raw["uiType"],
        nation=raw["typeinfo"]["nation"],
        enabled=bool(raw.get("enabled", True)),
        hidden=bool(raw.get("hidden", False)),
        multiple=bool(raw.get("multiple", False)),
        one_per_battle=bool(raw.get("onePerBattle", False)),
        show_progress=bool(raw.get("showProgress", True)),
        group=bool(raw.get("group", False)),
        battle_types=list(raw.get("battleTypes") or []),
        ship_categories=list(raw.get("shipCategories") or []),
        min_ship_level=int(raw.get("minShipLevel", 0)),
        max_ship_level=int(raw.get("maxShipLevel", 0)),
    )
