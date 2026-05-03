"""Normalise the small static enum catalogs sourced from scripts.zip.

Four enums extracted via `wows_shell` (look classes up with
`find_class("BATTLE_RESULT")` etc. — the home modules are obfuscated and
rename every patch):

  * BATTLE_RESULT / GameMode      — int → name (replay decoding)
  * EVENTS                        — name → code (event scenarios)
  * ACHIEVEMENT_TYPE              — name → slug (closed-list lookup)

The catalog is regenerated on every ingest from scripts.zip — see
`download.extract_scripts_enums`. Each `iter_*` takes the loaded catalog
dict so the source of truth flows from one place; locale strategy is
opportunistic per enum and enums without a usable catalog hit just expose
the bare name.
"""
from __future__ import annotations

from typing import Iterable

from . import locale
from .models import (
    AchievementType,
    BattleResult,
    EventScenario,
    GameMode,
)


def iter_battle_results(
    catalog: dict,
    translations: dict[str, dict[str, str]] | None = None,
) -> Iterable[BattleResult]:
    for entry in catalog["battle_result"]["entries"]:
        # Only VICTORY/DEFEAT/DRAW have direct `IDS_<NAME>` keys; the rest
        # (SUCCESS, FAILURE, PORTAL, MATCH, DEATH, TEAM_LADDER_*) fall back
        # to the bare constant name.
        name_i18n = (
            locale.translate(translations, f"IDS_{entry['name']}")
            if translations else {}
        )
        yield BattleResult(
            id=int(entry["value"]),
            name=entry["name"],
            name_i18n=name_i18n,
        )


def iter_game_modes(catalog: dict) -> Iterable[GameMode]:
    for entry in catalog["game_mode"]["entries"]:
        yield GameMode(id=int(entry["value"]), name=entry["name"])


def iter_event_scenarios(
    catalog: dict,
    translations: dict[str, dict[str, str]] | None = None,
) -> Iterable[EventScenario]:
    for entry in catalog["event_scenario"]["entries"]:
        code = str(entry["value"])
        # IDS_<CODE_UPPER> hits ~24/28: PCVE codes are uppercase already
        # (`IDS_PCVE040`); CamelCase codes upper-case cleanly
        # (`Legendary_Battle` → `IDS_LEGENDARY_BATTLE`).
        label_i18n = (
            locale.translate(translations, f"IDS_{code.upper()}")
            if translations else {}
        )
        yield EventScenario(
            name=entry["name"],
            code=code,
            label=label_i18n.get("en") or code,
            label_i18n=label_i18n,
        )


def iter_achievement_types(
    catalog: dict,
    translations: dict[str, dict[str, str]] | None = None,
) -> Iterable[AchievementType]:
    for entry in catalog["achievement_type"]["entries"]:
        name_i18n = (
            locale.translate(translations, f"IDS_ACHIEVEMENT_TYPE_{entry['name']}")
            if translations else {}
        )
        yield AchievementType(
            name=entry["name"],
            slug=str(entry["value"]),
            name_i18n=name_i18n,
        )
