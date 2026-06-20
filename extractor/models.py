"""Canonical Pydantic models for documents stored in Mongo.

These are the contract our API owns. The shape here is independent of WG's
GameParams field names — the normaliser maps GameParams → these names
explicitly so a renamed source field fails the ingest loudly instead of
silently emitting null on the API.

The API surface (api/routes/encyclopedia.py) reads these documents directly
and resolves icon SHAs to public URLs at response time.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ShipType(str, Enum):
    BATTLESHIP = "battleship"
    CRUISER = "cruiser"
    DESTROYER = "destroyer"
    AIRCARRIER = "aircarrier"
    SUBMARINE = "submarine"
    AUXILIARY = "auxiliary"


class Silhouette(BaseModel):
    """The 122×22 in-list mini-icon set, in three variants from the client.

    All three are the same dimensions and roughly the same shape (top-down
    ship outline filled in colour). They differ only in framing/state:
      - default: tech-tree colour version
      - own:     framed for the "own ship" HUD widget
      - dead:    greyed-out / sunken variant
    """
    model_config = ConfigDict(extra="forbid")
    default: str | None = None
    own: str | None = None
    dead: str | None = None


class Icons(BaseModel):
    """Per-ship icon set. Each value is the SHA-256 hex of a content-addressed
    PNG blob; URLs are built at response time."""
    model_config = ConfigDict(extra="forbid")
    silhouette: Silhouette = Field(default_factory=Silhouette)
    # 435×256 high-res card art used in port / tech-tree detail panels.
    # (The client dir is misleadingly named `ship_previews/medium/`; despite
    # the name it's the larger of the two preview sizes.)
    medium: str | None = None


class Ship(BaseModel):
    # `extra="forbid"` makes the canonical document own its keys: any stray
    # field passed to the constructor (e.g. a half-renamed legacy key) raises
    # a ValidationError, which fails the whole ingest. That's the intent.
    model_config = ConfigDict(extra="forbid")

    id: int
    # WG's short index for the ship (e.g. "PJSB018" for Yamato). Stable
    # across patches and matches the client's gui/ship_*_icons/<short_id>.png
    # filenames. Surfaced on the API as `ship_id_str`.
    short_id: str
    internal_name: str
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    description_i18n: dict[str, str] = Field(default_factory=dict)
    tier: int
    nation: str
    type: ShipType
    is_premium: bool = False
    is_special: bool = False
    has_demo_profile: bool = False
    price_credit: int | None = None
    price_gold: int | None = None
    mod_slots: int | None = None
    icons: Icons = Field(default_factory=Icons)


class NationFlags(BaseModel):
    """Three sizes of nation roundel/flag PNG shipped by the client.

    Each value is the SHA-256 of a content-addressed blob, same convention as
    Icons. Sizes mirror the client's `gui/nation_flags/{tiny,small,big}/`
    directories — kept verbatim rather than renamed because callers tend to
    pick whichever fits their layout."""
    model_config = ConfigDict(extra="forbid")
    tiny: str | None = None
    small: str | None = None
    big: str | None = None
    # Large tech-tree backdrop art (~700–800 KB each); the client renders it
    # behind the ship-tree column for that nation. Sourced from a separate
    # client dir (`gui/nation_flag_tree/`, no `flag_` filename prefix).
    tree: str | None = None


class ShipTypeIcons(BaseModel):
    """Class-marker icons sourced from `gui/service_kit/ship_classes/`.

    `default` is the small stock variant (~16×16). `big` is the larger version
    (~32×32) from the `ship_classes_big/` subdir. `premium`/`special`/`elite`
    are the same shape as `default` with the corresponding visual flavour
    (gold-tinted, etc.) used for those ship categories. Auxiliary only ships a
    `default`; missing flavours are simply omitted."""
    model_config = ConfigDict(extra="forbid")
    default: str | None = None
    big: str | None = None
    premium: str | None = None
    special: str | None = None
    elite: str | None = None


class ShipTypeInfo(BaseModel):
    """One canonical ship type: WG-style key + localised display label + icons.

    `key` is the GameParams `species` string verbatim ("Battleship", "AirCarrier",
    …) — it doubles as our public type identifier and matches the WG response
    shape. The localised label comes from `IDS_<KEY_UPPERCASE>` in global.mo
    (e.g. `IDS_AIRCARRIER` → "Aircraft Carrier")."""
    model_config = ConfigDict(extra="forbid")
    key: str
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    icons: ShipTypeIcons = Field(default_factory=ShipTypeIcons)


class SpaceImages(BaseModel):
    """Per-space art shipped inside the gui pkg.

    `preview` is the small training-room thumbnail (~5–35 KB jpg, sourced from
    `gui/bg/training_room_maps_preview/<Name>.jpg`). `bg` is the blurred
    background card (~85–235 KB jpg, from `gui/bg/maps_bg_blur/`). `full` is
    the same shot un-blurred at higher resolution (~300 KB – 2 MB jpg, from
    `gui/maps_bg/`). Stored as content-addressed filenames (`<sha>.jpg`);
    URLs are built at response time. The proper top-down minimap lives in
    the per-space sdcontent pkgs (~50 GB pull) and is not currently shipped."""
    model_config = ConfigDict(extra="forbid")
    preview: str | None = None
    bg: str | None = None
    full: str | None = None


class Space(BaseModel):
    """One canonical battle space (map / operation arena).

    GameParams doesn't enumerate spaces as first-class entries — the full list
    is server-side. We harvest the set indirectly from the locale catalog: any
    key under `IDS_SPACES/<KEY>` (with an optional matching `_DESCR` sibling)
    is treated as a known space. The label and description are fully localised
    via the same locale plumbing used for ships/nations.

    `key` is the catalog suffix verbatim (e.g. "S13_WW2_OP2", "01_SOLOMON_ISLANDS").
    Includes test/empty maps; consumers can filter on the leading numeric/category
    prefix if they want only matchmaker-eligible arenas. `images` is populated
    populated from `gui/bg/*` art bundled in the gui pkg; coverage is partial
    (~76/83 preview, ~80/83 bg) — a few legacy keys ship no art at all."""
    model_config = ConfigDict(extra="forbid")
    key: str
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    description_i18n: dict[str, str] = Field(default_factory=dict)
    images: SpaceImages = Field(default_factory=SpaceImages)


class AchievementIcons(BaseModel):
    """Achievement medal art shipped at two sizes.

    `default` is the small in-line badge (~64×64 PNG); `large` is the
    detail-card variant (~256×256, the `_L` suffix in the client)."""
    model_config = ConfigDict(extra="forbid")
    default: str | None = None
    large: str | None = None


class Achievement(BaseModel):
    """One in-game achievement / medal.

    Sourced from GameParams entries with `typeinfo.type == "Achievement"`.
    `ui_name` is the suffix used to build the locale keys
    (`IDS_ACHIEVEMENT_<UI_NAME>` for the title, `IDS_ACHIEVEMENT_DESCRIPTION_<UI_NAME>`
    for the description). `nation` is the GameParams `typeinfo.nation` verbatim
    — for achievements this is almost always `"Common"`.

    Fields like the underlying event/counter scripting (`events`, `constants`,
    `keepCounters`) are intentionally dropped — they're how the client decides
    when to award the medal, not user-facing data."""
    model_config = ConfigDict(extra="forbid")
    id: int
    internal_name: str
    ui_name: str
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    description_i18n: dict[str, str] = Field(default_factory=dict)
    type: str
    ui_type: str
    nation: str
    enabled: bool = True
    hidden: bool = False
    multiple: bool = False
    one_per_battle: bool = False
    show_progress: bool = True
    group: bool = False
    battle_types: list[str] = Field(default_factory=list)
    ship_categories: list[str] = Field(default_factory=list)
    min_ship_level: int = 0
    max_ship_level: int = 0
    icons: AchievementIcons = Field(default_factory=AchievementIcons)


class CrewCost(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credit: int = 0
    gold: int = 0
    xp: int = 0
    elite_xp: int = 0


class CrewTrainingLevels(BaseModel):
    """Tier the commander starts at when acquired through each path."""
    model_config = ConfigDict(extra="forbid")
    base: int = 1
    money: int = 0
    gold: int = 0


class CrewShipRestrictions(BaseModel):
    """Which ships this commander is intended for.

    Empty lists mean "no restriction on this dimension". `nation` is GameParams
    raw nation strings (`"Japan"`, `"United_Kingdom"`); `ships` and `groups`
    are short_id / group-tag strings as the client uses them."""
    model_config = ConfigDict(extra="forbid")
    nation: list[str] = Field(default_factory=list)
    ships: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)
    peculiarity: list[str] = Field(default_factory=list)


class Crew(BaseModel):
    """One commander entry from GameParams (`typeinfo.type == "Crew"`).

    The standard 82-skill skill tree is intentionally not stored per crew —
    it's largely shared across commanders and would balloon every doc to
    multiple KB of duplicated payload. `unique_skills` keeps the per-commander
    talents (only the ~12 unique commanders carry these) as the raw GameParams
    block; clients that care can render them, others can ignore the field.
    A separate `/skills` endpoint exposing the canonical skill tree is a
    follow-up if it's actually needed."""
    model_config = ConfigDict(extra="forbid")
    id: int
    internal_name: str
    index: str
    person_name: str
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    nation: str
    raw_nation: str
    is_unique: bool = False
    is_person: bool = True
    is_animated: bool = False
    has_rank: bool = False
    has_overlay: bool = False
    has_custom_background: bool = False
    has_sample_vo: bool = False
    is_retrainable: bool = True
    can_reset_skills_for_free: bool = False
    can_buy: bool = False
    can_charge: bool = False
    subnation: str = ""
    peculiarity: str = ""
    tags: list[str] = Field(default_factory=list)
    cost: CrewCost = Field(default_factory=CrewCost)
    training_levels: CrewTrainingLevels = Field(default_factory=CrewTrainingLevels)
    ship_restrictions: CrewShipRestrictions = Field(default_factory=CrewShipRestrictions)
    unique_skills: dict[str, Any] = Field(default_factory=dict)
    # Portrait art (`gui/crew_commander/base/<RAW_NATION>/<personName>.png`)
    # only exists for unique commanders. Standard commanders use shared
    # `base_<r>_<c>.png` slot art that isn't keyed to a specific person, so
    # we leave their portrait field null rather than store a generic slot.
    portrait: str | None = None


class CrewSkill(BaseModel):
    """One commander skill (perk) from the standard skill tree.

    Skills aren't top-level GameParams entries — they live nested under each
    Crew's `Skills` block. The 82-skill tree is shared across all commanders
    (varies in only ~24 distinct payloads; see `normalize_crew.py`), so we
    dedupe across crews and surface a single canonical encyclopedia.

    `id` is the GameParams `skillType` integer (1..82), which is what the
    client and replay packets use to identify a skill. `internal_name` is the
    GameParams key (`PlanesTorpedoUwReduced`, `DetectionVisibilityRange`, …)
    and is the stable string handle.

    `tiers` is a per-ship-class dict because the same skill can be a
    different tier depending on the class it's mastered on (e.g. a tier-3
    cruiser skill may be tier-4 on battleships). Keys are GameParams class
    names (`Cruiser`, `Destroyer`, `AirCarrier`, `Battleship`, `Submarine`,
    `Auxiliary`); values are 1..4. Skip keys mean "not available on this
    class" (no skills in patch 15.x trip this, but the schema admits it).

    Locale: name from `IDS_SKILL_<UPPER_SNAKE(name)>`, description from
    `IDS_SKILL_DESC_<UPPER_SNAKE(name)>`. WG ships many descriptions blank
    (`' '`) — we pass them through verbatim rather than null them out."""
    model_config = ConfigDict(extra="forbid")
    id: int
    internal_name: str
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    description_i18n: dict[str, str] = Field(default_factory=dict)
    tiers: dict[str, int] = Field(default_factory=dict)
    is_epic: bool = False
    is_trigger: bool = False
    icon: str | None = None


class BattleTypeIcons(BaseModel):
    """Battle-mode marker art, four sizes from `gui/service_kit/battle_types/`.

    `default` (~64×64), `small` (~32×32), `tiny` (~16×16), `big` (~256×256).
    The disabled-state variants the client also ships are intentionally
    skipped — clients can grey out the default at render time."""
    model_config = ConfigDict(extra="forbid")
    default: str | None = None
    small: str | None = None
    tiny: str | None = None
    big: str | None = None


class BattleType(BaseModel):
    """One battle mode (Random/Co-op/Ranked/Clan/Event/Operations/Brawl/…).

    The set is sourced from `BattleDefinitions.TeamBuildType` in the client
    scripts; GameParams references battle types only as bare tokens
    (`Achievement.battleTypes = ["PVP", "RANKED"]`), never as first-class
    entries. We carry the canonical camelCase `internal_name`
    (`RandomBattle`, `RankedBattle`, …), the short `match_group` slug
    (`pvp`, `ranked`, …), and the integer `team_build_type` so callers can
    correlate the same mode across all three vocabularies.

    Locale: name + description come from `IDS_<INTERNAL_NAME_UPPER>` and
    `IDS_<INTERNAL_NAME_UPPER>_DESCRIPTION`. PVE_PREMADE is the premade-
    division variant of PVE Operations and shares display strings with
    PVE; `is_premade` distinguishes them."""
    model_config = ConfigDict(extra="forbid")
    token: str
    team_build_type: int
    internal_name: str
    match_group: str
    is_premade: bool = False
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    description_i18n: dict[str, str] = Field(default_factory=dict)
    icons: BattleTypeIcons = Field(default_factory=BattleTypeIcons)


class Ribbon(BaseModel):
    """One in-battle ribbon (top-level damage/objective marker).

    The ribbon enum lives in the client scripts (look up the `Ribbon` class
    via `find_class("Ribbon")` in a wows_shell REPL — its actual home module
    has an obfuscated mangled name that changes every patch). GameParams
    doesn't reference ribbons at all; `tools/dump_scripts_enums.py` walks
    the `Ribbon` class instances and emits them into `scripts_enums.json`
    each ingest, alongside the other script-level enums.
    `id` matches the integer used over the wire in replay packets and battle-
    results JSON. `const_name` is the script-level Python identifier
    (`MAIN_CALIBER`, `BASE_DEFENSE`, …). `ids_key` is the script-level token
    (`RIBBON_MAIN_CALIBER`); the locale lookup prepends `IDS_RIBBON_` to it
    (`IDS_RIBBON_RIBBON_MAIN_CALIBER` — yes, that double-`RIBBON` prefix is
    really how WG ships it).
    `subribbon_ids` lists the SubRibbon.id children awarded under this
    ribbon's icon — useful for clients that want to roll subribbons up."""
    model_config = ConfigDict(extra="forbid")
    id: int
    const_name: str
    ids_key: str
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    icon_name: str
    icon: str | None = None
    subribbon_ids: list[int] = Field(default_factory=list)


class SubRibbon(BaseModel):
    """One in-battle sub-ribbon (the granular variant under a parent ribbon).

    Sub-ribbons split a parent ribbon into outcome-specific awards (e.g.
    `MAIN_CALIBER` ribbon → `..._PENETRATION`, `..._RICOCHET`, etc.). Each
    has its own icon and `IDS_*` locale key. `parent_ribbon_id` is the
    Ribbon.id of the owning ribbon; it can be null for legacy duplicates
    that share their const_name with the parent (e.g. SubRibbon id=0
    `MAIN_CALIBER` has no listed parent and is effectively a fallback for
    older replays). `ids_key` follows the catalog pattern
    `SUBRIBBON_<...>` (or `SUBSHOT_DOWN_MISSILE` for the lone outlier),
    matching the keys WG ships in `global.mo`."""
    model_config = ConfigDict(extra="forbid")
    id: int
    const_name: str
    ids_key: str
    parent_ribbon_id: int | None = None
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    icon_name: str
    icon: str | None = None


class BattleResult(BaseModel):
    """Replay/battle-results outcome code (`BATTLE_RESULT` in the client scripts).

    `id` is the integer used over the wire (e.g. 0=DEFEAT, 1=VICTORY, 2=DRAW).
    `name` is the script-level constant verbatim. Locale lookup tries
    `IDS_<NAME>` and only the well-known three (VICTORY / DEFEAT / DRAW) hit
    the catalog; the rest fall back to the bare name."""
    model_config = ConfigDict(extra="forbid")
    id: int
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)


class GameMode(BaseModel):
    """In-battle rule-set (`GameMode` in the client scripts).

    Distinct from `BattleType`: BattleType is the matchmaker bucket
    (Random / Ranked / Co-op / …), GameMode is the rule-set within it
    (`STANDARD`, `EPICENTER`, `ARMS_RACE`, `CONVOY_AIRSHIP`, …). Replay
    packets reference modes by this integer id. The duplicate `GAME_MODE`
    table in another module carries an extra `INVALID=-1` and a typo'd
    `STANDART`; we use the cleaner `GameMode` from `Account.py`."""
    model_config = ConfigDict(extra="forbid")
    id: int
    name: str


class EventScenario(BaseModel):
    """Event/operation scenario code (`EVENTS` in `EventBattlesCommon`).

    `code` is the string the matchmaker uses to identify the scenario
    (`PCVE040`, `Portal_Hard`, `Legendary_Battle`, …); these show up in
    battle-results JSON when the match was an event op. Locale via
    `IDS_<CODE_UPPER>` resolves the user-facing label for ~24 of 28 codes
    (e.g. `IDS_PCVE040 → "Arctic Convoy"`, `IDS_LEGENDARY_BATTLE → "Grand
    Battle"`); the remaining handful fall back to the bare code."""
    model_config = ConfigDict(extra="forbid")
    name: str
    code: str
    label: str
    label_i18n: dict[str, str] = Field(default_factory=dict)


class AchievementType(BaseModel):
    """Achievement classification (`ACHIEVEMENT_TYPE` in the client scripts).

    Five values: common / heroic / honorable / service_medal / squad.
    Same vocabulary used in the `type` field of every Achievement document;
    this resource just enumerates the closed universe of valid values for
    clients that want to populate filters. Locale via
    `IDS_ACHIEVEMENT_TYPE_<NAME>`."""
    model_config = ConfigDict(extra="forbid")
    name: str
    slug: str
    name_i18n: dict[str, str] = Field(default_factory=dict)


class Nation(BaseModel):
    """One canonical nation: slug, localised name, and flag art.

    `key` is our slug (e.g. "japan", "uk", "ussr") — the same value that
    appears in `Ship.nation`. `raw_name` is the GameParams form ("Japan",
    "United_Kingdom", "Russia"); we keep it so the ingest can resolve the
    `flag_<RAW>.png` filename the client uses."""
    model_config = ConfigDict(extra="forbid")
    key: str
    raw_name: str
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    flags: NationFlags = Field(default_factory=NationFlags)


class Modernization(BaseModel):
    """One upgrade/modernization from GameParams (`typeinfo.type == "Modernization"`).

    Modernizations are the slot upgrades players bolt onto a ship (Engine Boost
    Mod 1, Concealment System Mod 1, …). Each carries the integer `id` WG
    assigns in GameParams, which is what shows up as a `source` in
    `subtotal_economics` rows in the replay/battle-results stream — the parser
    looks it up via `GAME_PARAMS_BY_ID` to attribute a modifier to its owning
    upgrade.

    `slot` is the upgrade slot number (1..6). `ship_restrictions` is the raw
    list of short_ids the upgrade is mountable on; empty means no restriction.
    `modifiers` is the verbatim `{modifier_name: factor}` dict the client uses
    to compute the actual stat changes — surfaced as-is so callers can render
    the effect text without re-parsing GameParams.

    Locale: title from `IDS_<UPPER_NAME>`, description from
    `IDS_<UPPER_NAME>_DESCR`."""
    model_config = ConfigDict(extra="forbid")
    id: int
    internal_name: str
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    description_i18n: dict[str, str] = Field(default_factory=dict)
    slot: int | None = None
    # WG is inconsistent about this field's type (string, list, or int across
    # different items) and we don't consume it — keep it pass-through as-is.
    group: Any = None
    tags: list[str] = Field(default_factory=list)
    ship_level: list[int] = Field(default_factory=list)
    ship_restrictions: list[str] = Field(default_factory=list)
    nation_restrictions: list[str] = Field(default_factory=list)
    species_restrictions: list[str] = Field(default_factory=list)
    price_credit: int | None = None
    price_gold: int | None = None
    modifiers: dict[str, Any] = Field(default_factory=dict)
    icon: str | None = None


class Exterior(BaseModel):
    """One exterior item (`typeinfo.type == "Exterior"`).

    Covers signal flags, camouflages, and permoflages — all share the same
    GameParams type. `kind` is the `typeinfo.species` (`Flags`, `Camouflage`,
    `Permoflage`) so callers can filter without inspecting the raw payload.
    The integer `id` is what shows up as a `source` for flag/camo-granted
    modifiers in the post-battle economy stream.

    `modifiers` is the verbatim `{modifier_name: factor}` dict (e.g.
    `{"GMShotDelay": 1.05}` for a reload-bonus signal). Surfaced as-is so
    clients can render the effect without re-parsing GameParams.

    Locale: title from `IDS_<UPPER_NAME>`, description from
    `IDS_<UPPER_NAME>_DESCR`."""
    model_config = ConfigDict(extra="forbid")
    id: int
    internal_name: str
    kind: str
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    description_i18n: dict[str, str] = Field(default_factory=dict)
    # WG is inconsistent about this field's type (string, list, or int across
    # different items) and we don't consume it — keep it pass-through as-is.
    group: Any = None
    tags: list[str] = Field(default_factory=list)
    cost_credits: int | None = None
    cost_gold: int | None = None
    modifiers: dict[str, Any] = Field(default_factory=dict)
    icon: str | None = None


class Ability(BaseModel):
    """One consumable (`typeinfo.type == "Ability"`).

    Damage Control Party, Repair Party, Hydro Acoustic Search, Smoke Generator,
    Defensive AA Fire, … The integer `id` is what surfaces as a `source` in
    economy modifier rows whenever a consumable grants a stat bonus.

    Each consumable carries one or more lettered sub-variants (`AbilityList`
    in GameParams) — different durations / cooldowns for premium vs stock
    versions — but those don't have their own ids, so we collapse the
    record around the parent `id` and surface the variants verbatim as
    `variants` for callers that want them.

    Locale: title from `IDS_DOCK_CONSUME_TITLE_<UPPER_NAME>`,
    description from `IDS_DOCK_CONSUME_DESCRIPTION_<UPPER_NAME>`."""
    model_config = ConfigDict(extra="forbid")
    id: int
    internal_name: str
    name: str
    name_i18n: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    description_i18n: dict[str, str] = Field(default_factory=dict)
    # WG is inconsistent about this field's type (string, list, or int across
    # different items) and we don't consume it — keep it pass-through as-is.
    group: Any = None
    tags: list[str] = Field(default_factory=list)
    variants: dict[str, Any] = Field(default_factory=dict)
    icon: str | None = None
