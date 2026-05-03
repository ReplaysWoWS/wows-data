"""Map raw GameParams Crew entries to canonical Crew docs.

Locale lookup: the display name lives at `IDS_<PERSON_NAME_UPPER>` (e.g.
`IDS_ASHIKAGA_TERU`). There is no consistent description IDS pattern across
commanders — different campaigns / events ship bios under bespoke keys
(`IDS_PCQC010_HALSEY_DESCR`, etc.) — so we don't try to surface a unified
description here. Clients that need a bio can do their own lookup.

The standard 82-entry `Skills` tree is intentionally not stored per crew. It
varies across only ~24 distinct payloads in patch 15.x and would otherwise
duplicate multiple KB into every commander doc. Per-commander talents
(`UniqueSkills`) are kept as a raw dict so unique commanders carry their
distinguishing data.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import locale
from .models import Crew, CrewCost, CrewShipRestrictions, CrewTrainingLevels
from .normalize_ship import _wg_nation


def iter_crew(gameparams: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for name, entry in gameparams.items():
        if not isinstance(entry, dict):
            continue
        ti = entry.get("typeinfo")
        if isinstance(ti, dict) and ti.get("type") == "Crew":
            yield name, entry


def normalise_crew(
    internal_name: str,
    raw: dict[str, Any],
    translations: dict[str, dict[str, str]] | None = None,
) -> Crew:
    cp = raw.get("CrewPersonality") or {}
    person_name = cp.get("personName") or ""
    name_i18n = (
        locale.translate(translations, f"IDS_{person_name.upper()}")
        if translations and person_name else {}
    )
    raw_nation = raw["typeinfo"]["nation"]
    ships_block = cp.get("ships") or {}
    return Crew(
        id=raw["id"],
        internal_name=internal_name,
        index=raw["index"],
        person_name=person_name,
        name=name_i18n.get("en") or person_name or internal_name,
        name_i18n=name_i18n,
        nation=_wg_nation(raw_nation),
        raw_nation=raw_nation,
        is_unique=bool(cp.get("isUnique", False)),
        is_person=bool(cp.get("isPerson", True)),
        is_animated=bool(cp.get("isAnimated", False)),
        has_rank=bool(cp.get("hasRank", False)),
        has_overlay=bool(cp.get("hasOverlay", False)),
        has_custom_background=bool(cp.get("hasCustomBackground", False)),
        has_sample_vo=bool(cp.get("hasSampleVO", False)),
        is_retrainable=bool(cp.get("isRetrainable", True)),
        can_reset_skills_for_free=bool(cp.get("canResetSkillsForFree", False)),
        can_buy=bool(raw.get("canBuy", False)),
        can_charge=bool(raw.get("canCharge", False)),
        subnation=cp.get("subnation") or "",
        peculiarity=cp.get("peculiarity") or "",
        tags=list(cp.get("tags") or []),
        cost=CrewCost(
            credit=int(cp.get("costCR", 0)),
            gold=int(cp.get("costGold", 0)),
            xp=int(cp.get("costXP", 0)),
            elite_xp=int(cp.get("costELXP", 0)),
        ),
        training_levels=CrewTrainingLevels(
            base=int(raw.get("baseTrainingLevel", 1)),
            money=int(raw.get("moneyTrainingLevel", 0)),
            gold=int(raw.get("goldTrainingLevel", 0)),
        ),
        ship_restrictions=CrewShipRestrictions(
            nation=list(ships_block.get("nation") or []),
            ships=list(ships_block.get("ships") or []),
            groups=list(ships_block.get("groups") or []),
            peculiarity=list(ships_block.get("peculiarity") or []),
        ),
        unique_skills=dict(raw.get("UniqueSkills") or {}),
    )
