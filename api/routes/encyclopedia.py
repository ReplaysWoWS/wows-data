"""Encyclopedia REST endpoints under /v1.

The shape is our own — see extractor/models.py for the canonical document
schema. SHAs in stored documents are rewritten to public URLs at response
time; everything else is returned as stored.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query

from ..db import get_db, resolve_version
from ..settings import settings

router = APIRouter(prefix="/v1", tags=["encyclopedia"])

_MAX_LIMIT = 200
_MAX_ID_LIST = 200


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v for v in (s.strip() for s in value.split(",")) if v]


def _icon_url(filename: str) -> str:
    """Build a public URL for a content-addressed image blob.

    `filename` is `<sha>.<ext>`; the shard prefix is the first two hex chars
    and matches the on-disk layout in extractor/icons.py."""
    return f"{settings.icon_url_prefix.rstrip('/')}/{filename[:2]}/{filename}"


def _resolve_url_map(shas: dict[str, Any] | None) -> dict[str, str]:
    if not shas:
        return {}
    return {k: _icon_url(v) for k, v in shas.items() if v}


def _resolve_ship_icons(icons: dict[str, Any] | None) -> dict[str, Any]:
    if not icons:
        return {}
    out: dict[str, Any] = {}
    sil = _resolve_url_map(icons.get("silhouette"))
    if sil:
        out["silhouette"] = sil
    if icons.get("medium"):
        out["medium"] = _icon_url(icons["medium"])
    return out


def _localise(doc: dict[str, Any], field: str, language: str, fallback_key: str) -> str:
    i18n = doc.get(f"{field}_i18n") or {}
    return i18n.get(language) or doc.get(field) or doc.get(fallback_key) or ""


def _ship_view(doc: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "short_id": doc["short_id"],
        "name": _localise(doc, "name", language, "internal_name"),
        "description": _localise(doc, "description", language, "internal_name"),
        "tier": doc["tier"],
        "nation": doc["nation"],
        "type": doc["type"],
        "is_premium": doc["is_premium"],
        "is_special": doc["is_special"],
        "has_demo_profile": doc["has_demo_profile"],
        "mod_slots": doc["mod_slots"],
        "price_credit": doc["price_credit"],
        "price_gold": doc["price_gold"],
        "icons": _resolve_ship_icons(doc.get("icons")),
    }


def _nation_view(doc: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        "key": doc["key"],
        "name": _localise(doc, "name", language, "key"),
        "flags": _resolve_url_map(doc.get("flags")),
    }


def _ship_type_view(doc: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        "key": doc["key"],
        "name": _localise(doc, "name", language, "key"),
        "icons": _resolve_url_map(doc.get("icons")),
    }


def _achievement_view(doc: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "ui_name": doc["ui_name"],
        "name": _localise(doc, "name", language, "ui_name"),
        "description": _localise(doc, "description", language, "ui_name"),
        "type": doc["type"],
        "ui_type": doc["ui_type"],
        "nation": doc["nation"],
        "enabled": doc["enabled"],
        "hidden": doc["hidden"],
        "multiple": doc["multiple"],
        "one_per_battle": doc["one_per_battle"],
        "show_progress": doc["show_progress"],
        "group": doc["group"],
        "battle_types": doc["battle_types"],
        "ship_categories": doc["ship_categories"],
        "min_ship_level": doc["min_ship_level"],
        "max_ship_level": doc["max_ship_level"],
        "icons": _resolve_url_map(doc.get("icons")),
    }


def _crew_view(doc: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "index": doc["index"],
        "person_name": doc["person_name"],
        "name": _localise(doc, "name", language, "person_name"),
        "nation": doc["nation"],
        "is_unique": doc["is_unique"],
        "is_person": doc["is_person"],
        "is_animated": doc["is_animated"],
        "has_rank": doc["has_rank"],
        "has_overlay": doc["has_overlay"],
        "has_custom_background": doc["has_custom_background"],
        "has_sample_vo": doc["has_sample_vo"],
        "is_retrainable": doc["is_retrainable"],
        "can_reset_skills_for_free": doc["can_reset_skills_for_free"],
        "can_buy": doc["can_buy"],
        "can_charge": doc["can_charge"],
        "subnation": doc["subnation"],
        "peculiarity": doc["peculiarity"],
        "tags": doc["tags"],
        "cost": doc["cost"],
        "training_levels": doc["training_levels"],
        "ship_restrictions": doc["ship_restrictions"],
        "unique_skills": doc["unique_skills"],
        "portrait": _icon_url(doc["portrait"]) if doc.get("portrait") else None,
    }


def _battle_type_view(doc: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        "token": doc["token"],
        "team_build_type": doc["team_build_type"],
        "internal_name": doc["internal_name"],
        "match_group": doc["match_group"],
        "is_premade": doc["is_premade"],
        "name": _localise(doc, "name", language, "internal_name"),
        "description": _localise(doc, "description", language, "internal_name"),
        "icons": _resolve_url_map(doc.get("icons")),
    }


def _ribbon_view(doc: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "const_name": doc["const_name"],
        "ids_key": doc["ids_key"],
        "name": _localise(doc, "name", language, "const_name"),
        "icon_name": doc["icon_name"],
        "icon": _icon_url(doc["icon"]) if doc.get("icon") else None,
        "subribbon_ids": doc.get("subribbon_ids", []),
    }


def _subribbon_view(doc: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "const_name": doc["const_name"],
        "ids_key": doc["ids_key"],
        "parent_ribbon_id": doc.get("parent_ribbon_id"),
        "name": _localise(doc, "name", language, "const_name"),
        "icon_name": doc["icon_name"],
        "icon": _icon_url(doc["icon"]) if doc.get("icon") else None,
    }


def _battle_result_view(doc: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "name": _localise(doc, "name", language, "name"),
        "code": doc["name"],
    }


def _game_mode_view(doc: dict[str, Any], _language: str) -> dict[str, Any]:
    return {"id": doc["id"], "name": doc["name"]}


def _event_scenario_view(doc: dict[str, Any], language: str) -> dict[str, Any]:
    label_i18n = doc.get("label_i18n") or {}
    return {
        "name": doc["name"],
        "code": doc["code"],
        "label": label_i18n.get(language) or doc.get("label") or doc["code"],
    }


def _achievement_type_view(doc: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        "name": doc["name"],
        "slug": doc["slug"],
        "label": _localise(doc, "name", language, "name"),
    }


def _space_view(doc: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        "key": doc["key"],
        "name": _localise(doc, "name", language, "key"),
        "description": _localise(doc, "description", language, "key"),
        "images": _resolve_url_map(doc.get("images")),
    }


_VERSION_HELP = (
    "Game patch to query, e.g. `15.3.0.0`. "
    "Omit (or leave blank) to use the latest ingested patch."
)
_LANGUAGE_HELP = (
    "Language for `name` / `description` fields. "
    "Common values: `en`, `ru`, `de`, `fr`, `es`, `pl`, `cs`, `tr`, `ja`, `zh_sg`. "
    "Falls back to the internal name when a translation is missing."
)


@router.get(
    "/ships",
    summary="List ships",
    description=(
        "Returns every ship available in the selected patch — Tier I rowboats "
        "all the way up to Tier XI superships, including premiums, special "
        "ships, event boats and test hulls. Use the filters to narrow by "
        "nation or class. The response is paginated; bump `offset` by `limit` "
        "to walk through the catalog.\n\n"
        "**Tip:** the `id` field is the same numeric id used everywhere else "
        "in the WoWs ecosystem (replay packets, battle results, the WG API), "
        "so it's safe to use as a stable join key."
    ),
)
async def list_ships(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
    id: Annotated[
        str | None,
        Query(
            description="Comma-separated ship ids to fetch in one call.",
            examples=["3553818608,3762729968"],
        ),
    ] = None,
    nation: Annotated[
        str | None,
        Query(
            description=(
                "Comma-separated nation keys. See `/v1/nations` for the full list "
                "(`usa`, `japan`, `germany`, `ussr`, `uk`, `france`, `italy`, …)."
            ),
            examples=["usa,japan"],
        ),
    ] = None,
    type: Annotated[
        str | None,
        Query(
            description=(
                "Comma-separated ship-class keys. See `/v1/ship-types` "
                "(`Destroyer`, `Cruiser`, `Battleship`, `AirCarrier`, `Submarine`)."
            ),
            examples=["Battleship,Cruiser"],
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=_MAX_LIMIT, description=f"Maximum items to return (1–{_MAX_LIMIT})."),
    ] = _MAX_LIMIT,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of items to skip — use with `limit` for pagination."),
    ] = 0,
) -> dict[str, Any]:
    ids = _split_csv(id)
    nations = _split_csv(nation)
    types = _split_csv(type)

    for name, vals in (("id", ids), ("nation", nations), ("type", types)):
        if len(vals) > _MAX_ID_LIST:
            raise HTTPException(400, f"{name} list exceeds {_MAX_ID_LIST} entries")

    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    query: dict[str, Any] = {"client_version": resolved}
    if ids:
        try:
            query["id"] = {"$in": [int(s) for s in ids]}
        except ValueError as e:
            raise HTTPException(400, "id must be a CSV of integers") from e
    if nations:
        query["nation"] = {"$in": nations}
    if types:
        query["type"] = {"$in": types}

    db = get_db()
    total = await db.ships.count_documents(query)
    cursor = db.ships.find(query, {"_id": 0}).skip(offset).limit(limit)
    items = [_ship_view(doc, language) async for doc in cursor]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get(
    "/ships/{ship_id}",
    summary="Get a single ship by id",
    description=(
        "Fetch one ship's record. `ship_id` is the numeric id you'll see "
        "in `/v1/ships` responses, in replay packets, and in the public WG "
        "API. Returns 404 if the ship doesn't exist in the selected patch "
        "(ships do come and go between patches — premiums get retired, new "
        "lines get added)."
    ),
)
async def get_ship(
    ship_id: Annotated[int, Path(description="Numeric ship id from `/v1/ships`.", examples=[3553818608])],
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        raise HTTPException(404, "no patch ingested yet")
    doc = await get_db().ships.find_one(
        {"client_version": resolved, "id": ship_id}, {"_id": 0}
    )
    if doc is None:
        raise HTTPException(404, f"ship {ship_id} not found in {resolved}")
    return _ship_view(doc, language)


@router.get(
    "/nations",
    summary="List nations",
    description=(
        "Every nation that has at least one ship in the selected patch. "
        "Use the `key` field as the value for `?nation=` filters on other "
        "endpoints. `flags` maps a slot name (e.g. `default`, `tiny`) to "
        "an icon URL — handy for rendering a flag next to a ship."
    ),
)
async def list_nations(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().nations.find({"client_version": resolved}, {"_id": 0})
    return {"items": [_nation_view(doc, language) async for doc in cursor]}


@router.get(
    "/ship-types",
    summary="List ship classes",
    description=(
        "The five ship classes: Destroyer, Cruiser, Battleship, Aircraft "
        "Carrier and Submarine. The `key` field is what you pass to "
        "`/v1/ships?type=…`. Each entry includes class icons in a few "
        "flavours (default / premium / elite) for UI use."
    ),
)
async def list_ship_types(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().ship_types.find({"client_version": resolved}, {"_id": 0})
    return {"items": [_ship_type_view(doc, language) async for doc in cursor]}


@router.get(
    "/achievements",
    summary="List achievements",
    description=(
        "All in-game achievements (Kraken Unleashed, Confederate, Devastating "
        "Strike, Dreadnought, …) with their localised names and descriptions, "
        "plus the rules that govern them: which battle modes count, ship-tier "
        "limits, whether they can be earned more than once, etc.\n\n"
        "By default only **player-visible** achievements are returned. Pass "
        "`include_hidden=true` to also include internal markers used by the "
        "engine but never shown to players."
    ),
)
async def list_achievements(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
    type: Annotated[
        str | None,
        Query(
            description=(
                "Comma-separated achievement-type keys. See `/v1/achievement-types` "
                "(`common`, `heroic`, `honorable`, `service_medal`, `squad`)."
            ),
            examples=["heroic,honorable"],
        ),
    ] = None,
    nation: Annotated[
        str | None,
        Query(
            description="Comma-separated nation keys (only nation-flavoured achievements have a value here).",
            examples=["usa,japan"],
        ),
    ] = None,
    include_hidden: Annotated[
        bool,
        Query(description="Include hidden / internal achievements (default: only visible ones)."),
    ] = False,
    limit: Annotated[
        int,
        Query(ge=1, le=_MAX_LIMIT, description=f"Maximum items to return (1–{_MAX_LIMIT})."),
    ] = _MAX_LIMIT,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of items to skip — use with `limit` for pagination."),
    ] = 0,
) -> dict[str, Any]:
    types = _split_csv(type)
    nations = _split_csv(nation)

    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    query: dict[str, Any] = {"client_version": resolved}
    if types:
        query["type"] = {"$in": types}
    if nations:
        query["nation"] = {"$in": nations}
    if not include_hidden:
        query["hidden"] = False

    db = get_db()
    total = await db.achievements.count_documents(query)
    cursor = db.achievements.find(query, {"_id": 0}).skip(offset).limit(limit)
    items = [_achievement_view(doc, language) async for doc in cursor]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get(
    "/achievements/{achievement_id}",
    summary="Get a single achievement by id",
    description="Fetch one achievement's record. Returns 404 if not present in the selected patch.",
)
async def get_achievement(
    achievement_id: Annotated[int, Path(description="Numeric achievement id from `/v1/achievements`.")],
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        raise HTTPException(404, "no patch ingested yet")
    doc = await get_db().achievements.find_one(
        {"client_version": resolved, "id": achievement_id}, {"_id": 0}
    )
    if doc is None:
        raise HTTPException(404, f"achievement {achievement_id} not found in {resolved}")
    return _achievement_view(doc, language)


@router.get(
    "/crew",
    summary="List captains (crew)",
    description=(
        "Every captain (commander) available in the patch — generic captains, "
        "the per-nation defaults, and the named **unique** ones (Yamamoto, "
        "Halsey, Kuznetsov, …). Each entry tells you which nation they belong "
        "to, whether they have unique skills, retraining costs, ship "
        "restrictions, and a portrait URL.\n\n"
        "Set `is_unique=true` to only return named/unique commanders."
    ),
)
async def list_crew(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
    nation: Annotated[
        str | None,
        Query(description="Comma-separated nation keys.", examples=["usa,uk"]),
    ] = None,
    is_unique: Annotated[
        bool | None,
        Query(description="`true` → only unique/named captains; `false` → only generic; omit for both."),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=_MAX_LIMIT, description=f"Maximum items to return (1–{_MAX_LIMIT})."),
    ] = _MAX_LIMIT,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of items to skip — use with `limit` for pagination."),
    ] = 0,
) -> dict[str, Any]:
    nations = _split_csv(nation)

    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    query: dict[str, Any] = {"client_version": resolved}
    if nations:
        query["nation"] = {"$in": nations}
    if is_unique is not None:
        query["is_unique"] = is_unique

    db = get_db()
    total = await db.crew.count_documents(query)
    cursor = db.crew.find(query, {"_id": 0}).skip(offset).limit(limit)
    items = [_crew_view(doc, language) async for doc in cursor]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get(
    "/crew/{crew_id}",
    summary="Get a single captain by id",
    description="Fetch one captain's record. Returns 404 if not present in the selected patch.",
)
async def get_crew(
    crew_id: Annotated[int, Path(description="Numeric captain id from `/v1/crew`.")],
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        raise HTTPException(404, "no patch ingested yet")
    doc = await get_db().crew.find_one(
        {"client_version": resolved, "id": crew_id}, {"_id": 0}
    )
    if doc is None:
        raise HTTPException(404, f"crew {crew_id} not found in {resolved}")
    return _crew_view(doc, language)


@router.get(
    "/battle-types",
    summary="List battle modes",
    description=(
        "All battle modes the matchmaker knows about — Random, Co-op, "
        "Ranked, Clan Battles, Brawl, Operations, training rooms and so on. "
        "Each entry has a localised `name` and `description`, plus a few "
        "ids you can use to join with other data:\n\n"
        "- `token` — string id used inside the achievement records "
        "  (`/v1/achievements`).\n"
        "- `team_build_type` — numeric matchmaker id seen in replays.\n"
        "- `match_group` — short slug WG uses internally (`pvp`, `ranked`, "
        "  `cooperative`, …)."
    ),
)
async def list_battle_types(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().battle_types.find({"client_version": resolved}, {"_id": 0})
    return {"items": [_battle_type_view(doc, language) async for doc in cursor]}


@router.get(
    "/ribbons",
    summary="List top-level ribbons",
    description=(
        "The little badges that pop up over your reticle when you score a "
        "hit, set a fire, capture a point, etc. Each ribbon has a localised "
        "name, an icon, and a list of `subribbon_ids` (granular variants — "
        "fetch them from `/v1/sub-ribbons`).\n\n"
        "The `id` field matches the integer ribbon id seen in replay "
        "packets and battle-results JSON.\n\n"
        "**Note:** ribbons and sub-ribbons are two separate enums in the "
        "game, with their own independent integer id spaces. A ribbon "
        "with `id=14` is **not** the same thing as a sub-ribbon with "
        "`id=14`. Always treat the two collections as disjoint."
    ),
)
async def list_ribbons(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().ribbons.find({"client_version": resolved}, {"_id": 0}).sort("id", 1)
    return {"items": [_ribbon_view(doc, language) async for doc in cursor]}


@router.get(
    "/sub-ribbons",
    summary="List sub-ribbons (granular ribbon variants)",
    description=(
        "Many ribbons have finer-grained variants — a main-battery hit, "
        "for example, can land as a regular penetration, an over-pen, a "
        "ricochet, or a citadel. Sub-ribbons capture those variants.\n\n"
        "Set `parent_ribbon_id` to narrow the response to children of a "
        "single ribbon (e.g. `parent_ribbon_id=0` for the main-battery "
        "hit-quality breakdown). A handful of legacy entries have no "
        "parent — those are duplicates kept for backwards compatibility "
        "with old replays.\n\n"
        "**Note:** sub-ribbons live in their own integer id space, "
        "separate from `/v1/ribbons`. The `parent_ribbon_id` field "
        "points into the **ribbon** id space — it is not a sub-ribbon id."
    ),
)
async def list_subribbons(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
    parent_ribbon_id: Annotated[
        int | None,
        Query(
            description="Filter to sub-ribbons of a single parent ribbon (its `id` from `/v1/ribbons`).",
            examples=[0],
        ),
    ] = None,
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    query: dict[str, Any] = {"client_version": resolved}
    if parent_ribbon_id is not None:
        query["parent_ribbon_id"] = parent_ribbon_id
    cursor = get_db().subribbons.find(query, {"_id": 0}).sort("id", 1)
    return {"items": [_subribbon_view(doc, language) async for doc in cursor]}


@router.get(
    "/battle-results",
    summary="List battle outcome codes",
    description=(
        "The list of possible match outcomes — Victory, Defeat, Draw, plus "
        "a few rarer cases (technical defeats, unfinished matches, etc.). "
        "`id` is the numeric outcome you'll see in replays and battle-results "
        "JSON; `code` is the human-readable constant (`VICTORY`, `DEFEAT`, "
        "…); `name` is the localised label."
    ),
)
async def list_battle_results(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().battle_results.find({"client_version": resolved}, {"_id": 0}).sort("id", 1)
    return {"items": [_battle_result_view(doc, language) async for doc in cursor]}


@router.get(
    "/game-modes",
    summary="List in-battle rule-sets",
    description=(
        "**Different from `/v1/battle-types`!** Battle types are the *queue* "
        "(Random / Co-op / Ranked / …); game modes are the *rules played "
        "inside the match* — Standard, Domination, Epicenter, Arms Race, "
        "Convoy and so on. A single battle type can spawn matches with "
        "different game modes.\n\n"
        "Replay packets reference modes by the integer `id` returned here."
    ),
)
async def list_game_modes(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().game_modes.find({"client_version": resolved}, {"_id": 0}).sort("id", 1)
    return {"items": [_game_mode_view(doc, "en") async for doc in cursor]}


@router.get(
    "/event-scenarios",
    summary="List Operation / event scenarios",
    description=(
        "The catalog of PvE Operations and limited-time event scenarios — "
        "Narai, Newport, Aegis, Arctic Convoy, the seasonal event ops, etc. "
        "Each entry has:\n\n"
        "- `code` — the id used in battle-results JSON when the match was an "
        "  event op (e.g. `PCVE040`, `Legendary_Battle`).\n"
        "- `name` — the internal constant.\n"
        "- `label` — the user-facing name (`\"Arctic Convoy\"`), localised "
        "  via `?language=`."
    ),
)
async def list_event_scenarios(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().event_scenarios.find({"client_version": resolved}, {"_id": 0}).sort("code", 1)
    return {"items": [_event_scenario_view(doc, language) async for doc in cursor]}


@router.get(
    "/achievement-types",
    summary="List achievement categories",
    description=(
        "The five categories every achievement falls into: `common`, "
        "`heroic`, `honorable`, `service_medal`, `squad`. The `slug` here "
        "is the same vocabulary used in `Achievement.type` and the "
        "`?type=` filter on `/v1/achievements`."
    ),
)
async def list_achievement_types(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().achievement_types.find({"client_version": resolved}, {"_id": 0}).sort("slug", 1)
    return {"items": [_achievement_type_view(doc, language) async for doc in cursor]}


@router.get(
    "/spaces",
    summary="List maps and arenas",
    description=(
        "Every battle map known to the client — Random/Ranked maps, "
        "Operation arenas, training grounds, and a few legacy/test maps "
        "kept around for older replays. `key` is the internal map id, "
        "`name` and `description` are localised, and `images` maps a slot "
        "name (e.g. `minimap`, `preview`) to a static URL.\n\n"
        "If you only want maps currently in matchmaking rotation, filter "
        "client-side — the API returns the full catalog."
    ),
)
async def list_spaces(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    language: Annotated[str, Query(description=_LANGUAGE_HELP, examples=["en"])] = "en",
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().spaces.find({"client_version": resolved}, {"_id": 0})
    return {"items": [_space_view(doc, language) async for doc in cursor]}
