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


def _i18n(doc: dict[str, Any], field: str) -> dict[str, str]:
    """Return the per-language translation map for `field`.

    Stored docs already keep translations as `<field>_i18n` dicts; we surface
    them as-is so callers can pick a language without re-querying the API."""
    return doc.get(f"{field}_i18n") or {}


def _ship_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "short_id": doc["short_id"],
        "internal_name": doc.get("internal_name"),
        "name_i18n": _i18n(doc, "name"),
        "description_i18n": _i18n(doc, "description"),
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


def _nation_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": doc["key"],
        "name_i18n": _i18n(doc, "name"),
        "flags": _resolve_url_map(doc.get("flags")),
    }


def _ship_type_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": doc["key"],
        "name_i18n": _i18n(doc, "name"),
        "icons": _resolve_url_map(doc.get("icons")),
    }


def _achievement_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "ui_name": doc["ui_name"],
        "name_i18n": _i18n(doc, "name"),
        "description_i18n": _i18n(doc, "description"),
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


def _crew_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "index": doc["index"],
        "person_name": doc["person_name"],
        "name_i18n": _i18n(doc, "name"),
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


def _crew_skill_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "internal_name": doc["internal_name"],
        "name_i18n": _i18n(doc, "name"),
        "description_i18n": _i18n(doc, "description"),
        "tiers": doc.get("tiers", {}),
        "is_epic": doc.get("is_epic", False),
        "is_trigger": doc.get("is_trigger", False),
        "icon": _icon_url(doc["icon"]) if doc.get("icon") else None,
    }


def _battle_type_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "token": doc["token"],
        "team_build_type": doc["team_build_type"],
        "internal_name": doc["internal_name"],
        "match_group": doc["match_group"],
        "is_premade": doc["is_premade"],
        "name_i18n": _i18n(doc, "name"),
        "description_i18n": _i18n(doc, "description"),
        "icons": _resolve_url_map(doc.get("icons")),
    }


def _ribbon_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "const_name": doc["const_name"],
        "ids_key": doc["ids_key"],
        "name_i18n": _i18n(doc, "name"),
        "icon_name": doc["icon_name"],
        "icon": _icon_url(doc["icon"]) if doc.get("icon") else None,
        "subribbon_ids": doc.get("subribbon_ids", []),
    }


def _subribbon_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "const_name": doc["const_name"],
        "ids_key": doc["ids_key"],
        "parent_ribbon_id": doc.get("parent_ribbon_id"),
        "name_i18n": _i18n(doc, "name"),
        "icon_name": doc["icon_name"],
        "icon": _icon_url(doc["icon"]) if doc.get("icon") else None,
    }


def _battle_result_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "code": doc["name"],
        "name_i18n": _i18n(doc, "name"),
    }


def _game_mode_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {"id": doc["id"], "name": doc["name"]}


def _event_scenario_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": doc["name"],
        "code": doc["code"],
        "label_i18n": _i18n(doc, "label"),
    }


def _achievement_type_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": doc["name"],
        "slug": doc["slug"],
        "label_i18n": _i18n(doc, "name"),
    }


def _modernization_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "internal_name": doc["internal_name"],
        "name_i18n": _i18n(doc, "name"),
        "description_i18n": _i18n(doc, "description"),
        "slot": doc.get("slot"),
        "group": doc.get("group"),
        "tags": doc.get("tags", []),
        "ship_level": doc.get("ship_level", []),
        "ship_restrictions": doc.get("ship_restrictions", []),
        "nation_restrictions": doc.get("nation_restrictions", []),
        "species_restrictions": doc.get("species_restrictions", []),
        "price_credit": doc.get("price_credit"),
        "price_gold": doc.get("price_gold"),
        "modifiers": doc.get("modifiers", {}),
        "icon": _icon_url(doc["icon"]) if doc.get("icon") else None,
    }


def _exterior_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "internal_name": doc["internal_name"],
        "kind": doc["kind"],
        "name_i18n": _i18n(doc, "name"),
        "description_i18n": _i18n(doc, "description"),
        "group": doc.get("group"),
        "tags": doc.get("tags", []),
        "cost_credits": doc.get("cost_credits"),
        "cost_gold": doc.get("cost_gold"),
        "modifiers": doc.get("modifiers", {}),
        "icon": _icon_url(doc["icon"]) if doc.get("icon") else None,
    }


def _ability_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "internal_name": doc["internal_name"],
        "name_i18n": _i18n(doc, "name"),
        "description_i18n": _i18n(doc, "description"),
        "group": doc.get("group"),
        "tags": doc.get("tags", []),
        "variants": doc.get("variants", {}),
        "icon": _icon_url(doc["icon"]) if doc.get("icon") else None,
    }


def _space_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": doc["key"],
        "name_i18n": _i18n(doc, "name"),
        "description_i18n": _i18n(doc, "description"),
        "images": _resolve_url_map(doc.get("images")),
    }


_VERSION_HELP = (
    "Game patch to query, e.g. `15.3.0.0`. "
    "Omit (or leave blank) to use the latest ingested patch."
)


@router.get(
    "/versions",
    summary="List ingested game versions",
    description=(
        "Tells you which game patch the live data is pinned to, plus every "
        "patch we have on file.\n\n"
        "- `current` — version returned when you don't pass `?version=` on "
        "any other endpoint (i.e. the latest live-server patch we have "
        "ingested). `null` if the database is empty.\n"
        "- `current_pt` — same idea for the **public test** server.\n"
        "- `items` — all ingested patches, newest first. Each entry "
        "includes the version string, the timestamp it was extracted, the "
        "WG `game_id`, an `is_pt` flag, and the ship count for that patch.\n\n"
        "Useful for: pinning a client to a specific patch, showing a "
        "version selector in a UI, or detecting when a new patch has been "
        "ingested."
    ),
)
async def list_versions() -> dict[str, Any]:
    db = get_db()
    latest = await db.aliases.find_one({"_id": "latest"})
    latest_pt = await db.aliases.find_one({"_id": "latest_pt"})
    cursor = db.manifests.find(
        {"ready": {"$ne": False}}, {"_id": 0}
    ).sort("extracted_at", -1)
    items = [
        {
            "client_version": doc["client_version"],
            "extracted_at": doc.get("extracted_at"),
            "game_id": doc.get("game_id"),
            "is_pt": doc.get("is_pt", False),
            "ship_count": doc.get("ship_count"),
        }
        async for doc in cursor
    ]
    return {
        "current": latest["client_version"] if latest else None,
        "current_pt": latest_pt["client_version"] if latest_pt else None,
        "items": items,
    }


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
    items = [_ship_view(doc) async for doc in cursor]
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
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        raise HTTPException(404, "no patch ingested yet")
    doc = await get_db().ships.find_one(
        {"client_version": resolved, "id": ship_id}, {"_id": 0}
    )
    if doc is None:
        raise HTTPException(404, f"ship {ship_id} not found in {version or 'latest'}")
    return _ship_view(doc)


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
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().nations.find({"client_version": resolved}, {"_id": 0})
    return {"items": [_nation_view(doc) async for doc in cursor]}


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
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().ship_types.find({"client_version": resolved}, {"_id": 0})
    return {"items": [_ship_type_view(doc) async for doc in cursor]}


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
    items = [_achievement_view(doc) async for doc in cursor]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get(
    "/achievements/{achievement_id}",
    summary="Get a single achievement by id",
    description="Fetch one achievement's record. Returns 404 if not present in the selected patch.",
)
async def get_achievement(
    achievement_id: Annotated[int, Path(description="Numeric achievement id from `/v1/achievements`.")],
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        raise HTTPException(404, "no patch ingested yet")
    doc = await get_db().achievements.find_one(
        {"client_version": resolved, "id": achievement_id}, {"_id": 0}
    )
    if doc is None:
        raise HTTPException(404, f"achievement {achievement_id} not found in {version or 'latest'}")
    return _achievement_view(doc)


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
    items = [_crew_view(doc) async for doc in cursor]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get(
    "/crew/{crew_id}",
    summary="Get a single captain by id",
    description="Fetch one captain's record. Returns 404 if not present in the selected patch.",
)
async def get_crew(
    crew_id: Annotated[int, Path(description="Numeric captain id from `/v1/crew`.")],
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        raise HTTPException(404, "no patch ingested yet")
    doc = await get_db().crew.find_one(
        {"client_version": resolved, "id": crew_id}, {"_id": 0}
    )
    if doc is None:
        raise HTTPException(404, f"crew {crew_id} not found in {version or 'latest'}")
    return _crew_view(doc)


@router.get(
    "/crew-skills",
    summary="List commander skills (the perk tree)",
    description=(
        "Every entry in the standard 82-skill commander perk tree — the grid "
        "you see in port when assigning skill points (Preventive Maintenance, "
        "Concealment Expert, Adrenaline Rush, …). This is the canonical "
        "encyclopedia, deduped across all commanders.\n\n"
        "- `id` — the integer `skillType` from GameParams; this is what "
        "  replay packets and the client use to reference a skill.\n"
        "- `internal_name` — the GameParams skill key "
        "  (`PlanesTorpedoUwReduced`, `DetectionVisibilityRange`, …); stable "
        "  across patches and useful as a join key.\n"
        "- `tiers` — per-ship-class tier (1–4). The same skill can land in "
        "  different tiers depending on the class it's mastered on, so this "
        "  is a dict (`{\"Cruiser\": 4, \"Destroyer\": 4, …}`) rather than a "
        "  single int. A missing class key means the skill is unavailable on "
        "  that class.\n"
        "- `is_epic` — true for the rare 4-point legendary perks.\n"
        "- `is_trigger` — true for skills the UI renders as an active "
        "  trigger (consumable-like) rather than a passive bonus.\n"
        "- `description_i18n` — many skills ship a single space here. That's "
        "  WG's data; we surface it verbatim."
    ),
)
async def list_crew_skills(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": [], "total": 0}
    db = get_db()
    query = {"client_version": resolved}
    total = await db.crew_skills.count_documents(query)
    cursor = db.crew_skills.find(query, {"_id": 0}).sort("id", 1)
    items = [_crew_skill_view(doc) async for doc in cursor]
    return {"items": items, "total": total}


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
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().battle_types.find({"client_version": resolved}, {"_id": 0})
    return {"items": [_battle_type_view(doc) async for doc in cursor]}


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
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().ribbons.find({"client_version": resolved}, {"_id": 0}).sort("id", 1)
    return {"items": [_ribbon_view(doc) async for doc in cursor]}


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
    return {"items": [_subribbon_view(doc) async for doc in cursor]}


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
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().battle_results.find({"client_version": resolved}, {"_id": 0}).sort("id", 1)
    return {"items": [_battle_result_view(doc) async for doc in cursor]}


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
    return {"items": [_game_mode_view(doc) async for doc in cursor]}


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
        "- `label_i18n` — the user-facing name (`\"Arctic Convoy\"`) as a "
        "  per-language dict (`{\"en\": ..., \"ru\": ..., \"de\": ..., …}`)."
    ),
)
async def list_event_scenarios(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().event_scenarios.find({"client_version": resolved}, {"_id": 0}).sort("code", 1)
    return {"items": [_event_scenario_view(doc) async for doc in cursor]}


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
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().achievement_types.find({"client_version": resolved}, {"_id": 0}).sort("slug", 1)
    return {"items": [_achievement_type_view(doc) async for doc in cursor]}


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
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": []}
    cursor = get_db().spaces.find({"client_version": resolved}, {"_id": 0})
    return {"items": [_space_view(doc) async for doc in cursor]}


@router.get(
    "/modernizations",
    summary="List upgrades / modernizations",
    description=(
        "Every slot upgrade (Modernization) in the patch — Engine Boost "
        "Mod 1, Concealment System Mod 1, Main Battery Mod 2, etc. Each "
        "entry carries the integer `id` WG assigns in GameParams; that is "
        "the same id that shows up as a `source` in `subtotal_economics` "
        "rows in the post-battle replay/battle-results stream, which is "
        "how the parser attributes a modifier to its owning upgrade.\n\n"
        "`modifiers` is the verbatim `{modifier_name: factor}` dict the "
        "client uses to compute the stat changes (e.g. "
        "`{\"GMShotDelay\": 0.88}` for a -12% reload upgrade)."
    ),
)
async def list_modernizations(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    slot: Annotated[
        int | None,
        Query(description="Filter to a single upgrade slot (1..6).", examples=[1]),
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
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    query: dict[str, Any] = {"client_version": resolved}
    if slot is not None:
        query["slot"] = slot
    db = get_db()
    total = await db.modernizations.count_documents(query)
    cursor = db.modernizations.find(query, {"_id": 0}).sort("id", 1).skip(offset).limit(limit)
    items = [_modernization_view(doc) async for doc in cursor]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get(
    "/exteriors",
    summary="List exteriors (signal flags, camouflages, permoflages)",
    description=(
        "Every Exterior in the patch — signal flags (`Flags`), regular "
        "camouflages (`Camouflage`), and permanent ship skins "
        "(`Permoflage`). Filter with `?kind=Flags` to narrow to one "
        "family. The integer `id` is the same id surfaced as a `source` "
        "in `subtotal_economics` rows when a flag or camo granted a "
        "stat bonus."
    ),
)
async def list_exteriors(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    kind: Annotated[
        str | None,
        Query(
            description="Filter by exterior family (`Flags`, `Camouflage`, `Permoflage`).",
            examples=["Flags"],
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
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    query: dict[str, Any] = {"client_version": resolved}
    if kind is not None:
        query["kind"] = kind
    db = get_db()
    total = await db.exteriors.count_documents(query)
    cursor = db.exteriors.find(query, {"_id": 0}).sort("id", 1).skip(offset).limit(limit)
    items = [_exterior_view(doc) async for doc in cursor]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get(
    "/abilities",
    summary="List consumables (abilities)",
    description=(
        "Every consumable players can mount — Damage Control Party, "
        "Repair Party, Hydro Acoustic Search, Smoke Generator, Defensive "
        "AA Fire, Spotter / Catapult Fighter, etc. The integer `id` is "
        "the parent GameParams id, which is what surfaces as a `source` "
        "in `subtotal_economics` rows when a consumable granted a "
        "modifier. Lettered sub-variants (different durations/cooldowns "
        "for stock vs premium versions) don't have their own ids and "
        "are surfaced verbatim under `variants`."
    ),
)
async def list_abilities(
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=_MAX_LIMIT, description=f"Maximum items to return (1–{_MAX_LIMIT})."),
    ] = _MAX_LIMIT,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of items to skip — use with `limit` for pagination."),
    ] = 0,
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    query = {"client_version": resolved}
    db = get_db()
    total = await db.abilities.count_documents(query)
    cursor = db.abilities.find(query, {"_id": 0}).sort("id", 1).skip(offset).limit(limit)
    items = [_ability_view(doc) async for doc in cursor]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


_MODIFIER_SOURCE_LOOKUP = (
    # (kind, collection, id_field, view_fn). Order matters: the resolver
    # returns the first hit, and overlap between collections is not expected
    # in WG's id space but we probe the densest types first anyway.
    ("modernization", "modernizations", "id", _modernization_view),
    ("exterior",      "exteriors",      "id", _exterior_view),
    ("ability",       "abilities",      "id", _ability_view),
    ("ship",          "ships",          "id", _ship_view),
    ("crew",          "crew",           "id", _crew_view),
    ("achievement",   "achievements",   "id", _achievement_view),
)


@router.get(
    "/modifier-sources/{source_id}",
    summary="Resolve a GameParams id to its owning entity",
    description=(
        "Given a numeric `source` id from `subtotal_economics` in a replay "
        "or battle-results payload, return the GameParams entity that "
        "granted the modifier — typically a modernization, exterior "
        "(signal/camo/permoflage) or consumable, occasionally a ship, "
        "commander or achievement.\n\n"
        "The response `kind` field tells you which entity type was hit "
        "(`modernization` / `exterior` / `ability` / `ship` / `crew` / "
        "`achievement`); the remaining fields match the corresponding "
        "list endpoint's view. Returns 404 when no entity in the patch "
        "carries that id — WG does occasionally reassign ids between "
        "patches, so pin to `(version, id)` if you're caching."
    ),
)
async def resolve_modifier_source(
    source_id: Annotated[int, Path(description="Numeric `source` id from the replay/battle-results stream.", examples=[4281331632])],
    version: Annotated[str | None, Query(description=_VERSION_HELP, examples=["15.3.0.0"])] = None,
) -> dict[str, Any]:
    resolved = await resolve_version(version)
    if resolved is None:
        raise HTTPException(404, "no patch ingested yet")
    db = get_db()
    for kind, coll, id_field, view_fn in _MODIFIER_SOURCE_LOOKUP:
        doc = await db[coll].find_one(
            {"client_version": resolved, id_field: source_id}, {"_id": 0}
        )
        if doc is not None:
            return {"kind": kind, **view_fn(doc)}
    raise HTTPException(404, f"no entity with id {source_id} in {version or 'latest'}")
