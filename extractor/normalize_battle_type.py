"""Build canonical BattleType documents.

GameParams doesn't ship a battle-type catalog — it references modes only as
bare tokens (e.g. `Achievement.battleTypes = ["PVP", "RANKED"]`). The
authoritative enum lives in the client scripts (`BattleDefinitions.py`):

  * `TeamBuildType.<TOKEN>` → integer id used by the matchmaker
  * `BATTLE_TYPES.MAP_TEAMBUILDTYPE_TO_BATTLETYPE[id]` → camelCase
    battle-type name (`RandomBattle`, `RankedBattle`, `PVEBattle`, …)
  * `MatchGroup.BATTLE_TYPE_TO_MATCH[name]` → short match-group slug
    (`pvp`, `pve`, `ranked`, …) — keys missing from this dict yield an
    empty match_group (e.g. `TrainingBattle`, `ClubBattle`).

The ingest pulls those three structures from scripts.zip via wows_shell
on every run (see `download.extract_scripts_enums`) and joins them here.
A new patch that adds a TeamBuildType entry is picked up automatically.

`is_premade` isn't a separate script field — it's inferred from the
TeamBuildType token name suffix (`PVE_PREMADE`). We surface it because
`PVE_PREMADE` (id=7) and `PVE` (id=6) both map to `PVEBattle` and need
distinguishing on the API.

The locale strings come from the same `global.mo` catalogs we use
elsewhere; keys are `IDS_<INTERNAL_NAME_UPPER>` and `..._DESCRIPTION`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from . import locale
from .models import BattleType


@dataclass(frozen=True)
class _BattleTypeDef:
    token: str
    team_build_type: int
    internal_name: str
    match_group: str
    is_premade: bool


def _build_defs(catalog: dict) -> tuple[_BattleTypeDef, ...]:
    """Derive (token, tbt, internal, match_group, is_premade) rows from the
    BattleDefinitions slice of a scripts_enums catalog."""
    bt = catalog["battle_type"]
    tbt_to_battle = bt["tbt_to_battle_type"]
    bt_to_match   = bt["battle_type_to_match_group"]
    rows: list[_BattleTypeDef] = []
    for entry in bt["team_build_type"]:
        tbt = int(entry["value"])
        token = entry["name"]
        if tbt < 0 or tbt >= len(tbt_to_battle):
            continue
        internal = tbt_to_battle[tbt]
        rows.append(_BattleTypeDef(
            token=token,
            team_build_type=tbt,
            internal_name=internal,
            match_group=bt_to_match.get(internal, ""),
            is_premade=token.endswith("_PREMADE"),
        ))
    rows.sort(key=lambda r: r.team_build_type)
    return tuple(rows)


def known_tokens(catalog: dict) -> set[str]:
    return {d.token for d in _build_defs(catalog)}


def collect_referenced_tokens(gameparams: dict[str, Any]) -> set[str]:
    """Walk GameParams and return every token observed in `battleTypes` lists.

    Used by `validate_tokens` to surface unknown tokens introduced by a new
    patch — those would otherwise quietly fall through into the achievement
    documents."""
    seen: set[str] = set()

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "battleTypes" and isinstance(value, (list, tuple)):
                    for token in value:
                        if isinstance(token, str):
                            seen.add(token)
                else:
                    walk(value)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                walk(item)

    walk(gameparams)
    return seen


def validate_tokens(gameparams: dict[str, Any], catalog: dict) -> None:
    referenced = collect_referenced_tokens(gameparams)
    unknown = referenced - known_tokens(catalog)
    if unknown:
        raise RuntimeError(
            f"GameParams references unknown battle-type tokens {sorted(unknown)!r}; "
            "scripts.zip catalog is stale — re-run the ingest to regenerate "
            "scripts_enums.json from the current patch."
        )


def iter_battle_types(
    catalog: dict,
    translations: dict[str, dict[str, str]] | None = None,
) -> Iterable[BattleType]:
    for d in _build_defs(catalog):
        ids_key = f"IDS_{d.internal_name.upper()}"
        name_i18n = locale.translate(translations, ids_key) if translations else {}
        descr_i18n = (
            locale.translate(translations, f"{ids_key}_DESCRIPTION")
            if translations else {}
        )
        yield BattleType(
            token=d.token,
            team_build_type=d.team_build_type,
            internal_name=d.internal_name,
            match_group=d.match_group,
            is_premade=d.is_premade,
            name=name_i18n.get("en") or d.internal_name,
            name_i18n=name_i18n,
            description=descr_i18n.get("en", ""),
            description_i18n=descr_i18n,
        )
