"""End-to-end ingest CLI: download → decode → normalise → write to Mongo.

Usage:
    python -m extractor.ingest                    # latest live build
    python -m extractor.ingest --pt               # latest PT build
    python -m extractor.ingest --if-newer         # skip if Mongo already at latest
    python -m extractor.ingest --loop             # run forever, ticking every --interval
    python -m extractor.ingest --skip-download \\
        --gameparams /path/to/GameParams.data     # use a local file
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError
from pymongo import MongoClient, UpdateOne

from . import (
    download,
    gameparams,
    icons,
    locale,
    normalize_achievement,
    normalize_battle_type,
    normalize_crew,
    normalize_nation,
    normalize_ribbon,
    normalize_scripts_enums,
    normalize_ship,
    normalize_ship_type,
    normalize_space,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest one WoWS patch into MongoDB.")
    parser.add_argument("--pt", action="store_true", help="Pull the PT build instead of live.")
    parser.add_argument(
        "--gameparams",
        type=Path,
        help="Use this pre-extracted raw GameParams.data instead of downloading.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Implies --gameparams must be provided. Skips wgc-download.",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("data/extract"),
        help="Where wgc-download writes the extracted file.",
    )
    parser.add_argument(
        "--client-version",
        help="Override client_version tag (only useful with --gameparams).",
    )
    parser.add_argument(
        "--texts-dir",
        type=Path,
        help="Pre-extracted res/texts/ dir (with <lang>/LC_MESSAGES/global.mo). "
             "Useful with --skip-download to avoid re-downloading the locale dspkg.",
    )
    parser.add_argument(
        "--icons-staging",
        type=Path,
        help="Pre-extracted icons staging dir (with gui/ships_silhouettes/ etc.). "
             "Useful with --skip-download to avoid re-pulling the 2 GB gui pkg.",
    )
    parser.add_argument(
        "--skip-icons",
        action="store_true",
        help="Skip icon extraction entirely (ships will have icons={}).",
    )
    parser.add_argument(
        "--scripts-enums",
        type=Path,
        help="Pre-extracted scripts_enums.json. Useful with --skip-download "
             "to avoid re-running wows_shell against scripts.zip.",
    )
    parser.add_argument(
        "--if-newer",
        action="store_true",
        help="Query wgc-download for the latest version and skip the pipeline "
             "if Mongo's `latest`/`latest_pt` alias already matches.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run forever, sleeping --interval between ticks. Combine with "
             "--if-newer so most ticks are no-ops.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=1800,
        help="Seconds to sleep between ticks when --loop is set (default 1800).",
    )
    args = parser.parse_args()

    if args.skip_download and not args.gameparams:
        parser.error("--skip-download requires --gameparams")
    if args.skip_download and not args.scripts_enums:
        parser.error("--skip-download requires --scripts-enums (no checked-in fallback)")
    if args.if_newer and args.skip_download:
        parser.error("--if-newer needs to query wgc-download; incompatible with --skip-download")

    if args.loop:
        return _loop(args)
    return _run_once(args)


def _loop(args) -> int:
    """Run the pipeline forever, swallowing per-tick failures.

    The container is meant to be `restart: unless-stopped`, but we'd rather
    keep ticking through transient flakes (Mongo not ready on first boot,
    wgc-download blip) than crash and rely on Docker to restart us — that
    would lose the in-process backoff and spam the restart log."""
    print(f"[ingest] loop mode: interval={args.interval}s")
    while True:
        try:
            _run_once(args)
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            print(f"[ingest] tick failed: {type(e).__name__}: {e}", file=sys.stderr)
            traceback.print_exc()
            try:
                _record_last_run(status="error", error=f"{type(e).__name__}: {e}")
            except Exception as inner:
                # Don't let last_run write failure (e.g. Mongo down) crash the loop.
                print(f"[ingest] could not record last_run: {inner}", file=sys.stderr)
        print(f"[ingest] sleeping {args.interval}s")
        time.sleep(args.interval)


_PARTITIONED_COLLECTIONS = (
    "ships", "nations", "ship_types", "spaces", "achievements", "crew",
    "battle_types", "ribbons", "subribbons", "battle_results", "game_modes",
    "event_scenarios", "achievement_types",
)


def _drop_partition(db, partition: str) -> None:
    """Delete all docs under a data_partition tag across every collection.

    Called after a re-ingest swap to clear the previous (now orphaned)
    shadow partition. Safe even if some collections are empty for it."""
    for coll in _PARTITIONED_COLLECTIONS:
        db[coll].delete_many({"client_version": partition})
    print(f"[ingest] dropped orphaned partition {partition}")


def _record_last_run(*, status: str, version_seen: str | None = None,
                     version_ingested: str | None = None,
                     error: str | None = None) -> None:
    """Best-effort heartbeat doc so /health can show the loop is alive."""
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB", "wows")
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
    try:
        client[db_name].last_run.update_one(
            {"_id": "ingest"},
            {"$set": {
                "status": status,
                "version_seen": version_seen,
                "version_ingested": version_ingested,
                "error": error,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
    finally:
        client.close()


def _run_once(args) -> int:
    game_id = download.PT_GAME_ID if args.pt else download.LIVE_GAME_ID

    translations = {}
    icons_staging: Path | None = args.icons_staging
    scripts_enums_path: Path | None = args.scripts_enums
    dump_script = Path(__file__).resolve().parent.parent / "tools" / "dump_scripts_enums.py"
    if args.gameparams:
        gp_path = args.gameparams
        version_tag = args.client_version or f"local-{int(time.time())}"
        print(f"[ingest] using local GameParams.data: {gp_path}")
        if args.texts_dir:
            translations = locale.load_all(args.texts_dir)
            print(f"[ingest] loaded {len(translations)} locales from {args.texts_dir}: {sorted(translations)}")
    else:
        version = download.latest_version(game_id)
        version_tag = version.tag(is_pt=args.pt)
        print(f"[ingest] latest {game_id}: {version_tag} (build {version.build})")
        if args.if_newer:
            mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
            db_name = os.environ.get("MONGO_DB", "wows")
            client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
            try:
                alias_id = "latest_pt" if args.pt else "latest"
                alias = client[db_name].aliases.find_one({"_id": alias_id})
            finally:
                client.close()
            if alias and alias.get("client_version") == version_tag:
                print(f"[ingest] --if-newer: Mongo already at {version_tag}, skipping")
                _record_last_run(status="skipped", version_seen=version_tag)
                return 0
            print(f"[ingest] --if-newer: Mongo at {alias.get('client_version') if alias else None}, ingesting {version_tag}")
        gp_path = download.extract_gameparams(version, game_id, args.workdir / version_tag)
        print(f"[ingest] extracted GameParams.data to {gp_path}")
        texts_dir = download.extract_locales(version, game_id, args.workdir / version_tag)
        translations = locale.load_all(texts_dir)
        print(f"[ingest] loaded {len(translations)} locales: {sorted(translations)}")
        if not args.skip_icons:
            icons_staging = download.extract_icons(version, game_id, args.workdir / version_tag)
            print(f"[ingest] extracted icons staging to {icons_staging}")
        if scripts_enums_path is None:
            scripts_enums_path = download.extract_scripts_enums(
                version, game_id, args.workdir / version_tag, dump_script,
            )
            print(f"[ingest] extracted scripts_enums to {scripts_enums_path}")

    if scripts_enums_path is None:
        raise RuntimeError(
            "no scripts_enums.json available — pass --scripts-enums when "
            "using --skip-download, or run without --skip-download to let "
            "wows_shell extract it from the patch's scripts.zip"
        )
    catalog = json.loads(scripts_enums_path.read_text())
    print(f"[ingest] loaded scripts_enums catalog: {sorted(catalog)}")

    print("[ingest] decoding GameParams.data ...")
    raw = gameparams.decode(gp_path)
    print(f"[ingest] decoded {len(raw)} top-level entries")

    blobs_root = Path(os.environ.get("ICONS_BLOBS_DIR", "/app/data/icons/blobs"))
    promoted_blobs = 0

    # Track raw GameParams nation names (e.g. "Japan", "United_Kingdom") as we
    # see them on ships. We need the raw form to resolve `flag_<RAW>.png`.
    raw_nations: dict[str, None] = {}
    raw_species: dict[str, None] = {}
    ships: list[dict] = []
    for name, entry in normalize_ship.iter_ships(raw):
        raw_nations.setdefault(entry["typeinfo"]["nation"], None)
        raw_species.setdefault(entry["typeinfo"]["species"], None)
        try:
            ship = normalize_ship.normalise_ship(name, entry, translations)
        except (ValidationError, KeyError, ValueError) as e:
            # Re-raise with the offending entry's internal name in the message
            # so the operator can find the broken record without grepping the
            # stack trace.
            raise RuntimeError(
                f"normalisation failed for ship {name!r}: {type(e).__name__}: {e}"
            ) from e
        if icons_staging and not args.skip_icons:
            sil_srcs, med_src = icons.collect_for_ship(icons_staging, ship.short_id)
            for key, src in sil_srcs.items():
                setattr(ship.icons.silhouette, key, icons.promote(src, blobs_root))
                promoted_blobs += 1
            if med_src is not None:
                ship.icons.medium = icons.promote(med_src, blobs_root)
                promoted_blobs += 1
        ships.append(ship.model_dump(mode="json"))
    print(f"[ingest] normalised {len(ships)} ships")

    nations: list[dict] = []
    for raw_name in sorted(raw_nations):
        nation = normalize_nation.normalise_nation(raw_name, translations)
        if icons_staging and not args.skip_icons:
            for size, src in icons.collect_for_nation(icons_staging, raw_name).items():
                setattr(nation.flags, size, icons.promote(src, blobs_root))
                promoted_blobs += 1
        nations.append(nation.model_dump(mode="json"))
    print(f"[ingest] normalised {len(nations)} nations")

    ship_types: list[dict] = []
    for species in sorted(raw_species):
        st = normalize_ship_type.normalise_ship_type(species, translations)
        if icons_staging and not args.skip_icons:
            for variant, src in icons.collect_for_ship_type(icons_staging, species).items():
                setattr(st.icons, variant, icons.promote(src, blobs_root))
                promoted_blobs += 1
        ship_types.append(st.model_dump(mode="json"))
    print(f"[ingest] normalised {len(ship_types)} ship types")

    space_bg_index = (
        icons.index_space_bgs(icons_staging)
        if icons_staging and not args.skip_icons
        else {}
    )
    spaces: list[dict] = []
    for key in normalize_space.discover_keys(translations):
        sp = normalize_space.normalise_space(key, translations)
        for variant, src in icons.collect_for_space(space_bg_index, key).items():
            setattr(sp.images, variant, icons.promote(src, blobs_root))
            promoted_blobs += 1
        spaces.append(sp.model_dump(mode="json"))
    print(f"[ingest] normalised {len(spaces)} spaces")

    achievements: list[dict] = []
    for name, entry in normalize_achievement.iter_achievements(raw):
        try:
            ach = normalize_achievement.normalise_achievement(name, entry, translations)
        except (ValidationError, KeyError, ValueError) as e:
            raise RuntimeError(
                f"normalisation failed for achievement {name!r}: {type(e).__name__}: {e}"
            ) from e
        if icons_staging and not args.skip_icons:
            for variant, src in icons.collect_for_achievement(icons_staging, ach.ui_name).items():
                setattr(ach.icons, variant, icons.promote(src, blobs_root))
                promoted_blobs += 1
        achievements.append(ach.model_dump(mode="json"))
    print(f"[ingest] normalised {len(achievements)} achievements")

    crews: list[dict] = []
    for name, entry in normalize_crew.iter_crew(raw):
        try:
            cr = normalize_crew.normalise_crew(name, entry, translations)
        except (ValidationError, KeyError, ValueError) as e:
            raise RuntimeError(
                f"normalisation failed for crew {name!r}: {type(e).__name__}: {e}"
            ) from e
        if icons_staging and not args.skip_icons:
            portrait = icons.collect_for_crew(icons_staging, cr.raw_nation, cr.person_name)
            if portrait is not None:
                cr.portrait = icons.promote(portrait, blobs_root)
                promoted_blobs += 1
        crews.append(cr.model_dump(mode="json"))
    print(f"[ingest] normalised {len(crews)} crew")

    normalize_battle_type.validate_tokens(raw, catalog)
    battle_types: list[dict] = []
    for bt in normalize_battle_type.iter_battle_types(catalog, translations):
        if icons_staging and not args.skip_icons:
            for variant, src in icons.collect_for_battle_type(icons_staging, bt.internal_name).items():
                setattr(bt.icons, variant, icons.promote(src, blobs_root))
                promoted_blobs += 1
        battle_types.append(bt.model_dump(mode="json"))
    print(f"[ingest] normalised {len(battle_types)} battle types")

    ribbons_docs: list[dict] = []
    for r in normalize_ribbon.iter_ribbons(catalog, translations):
        if icons_staging and not args.skip_icons:
            src = icons.collect_for_ribbon(icons_staging, r.icon_name)
            if src is not None:
                r.icon = icons.promote(src, blobs_root)
                promoted_blobs += 1
        ribbons_docs.append(r.model_dump(mode="json"))
    print(f"[ingest] normalised {len(ribbons_docs)} ribbons")

    subribbons_docs: list[dict] = []
    for sr in normalize_ribbon.iter_subribbons(catalog, translations):
        if icons_staging and not args.skip_icons:
            src = icons.collect_for_subribbon(icons_staging, sr.icon_name)
            if src is not None:
                sr.icon = icons.promote(src, blobs_root)
                promoted_blobs += 1
        subribbons_docs.append(sr.model_dump(mode="json"))
    print(f"[ingest] normalised {len(subribbons_docs)} sub-ribbons")

    battle_results = [r.model_dump(mode="json") for r in normalize_scripts_enums.iter_battle_results(catalog, translations)]
    game_modes     = [r.model_dump(mode="json") for r in normalize_scripts_enums.iter_game_modes(catalog)]
    event_scenarios = [r.model_dump(mode="json") for r in normalize_scripts_enums.iter_event_scenarios(catalog, translations)]
    achievement_types = [r.model_dump(mode="json") for r in normalize_scripts_enums.iter_achievement_types(catalog, translations)]
    print(
        f"[ingest] normalised {len(battle_results)} battle results, "
        f"{len(game_modes)} game modes, "
        f"{len(event_scenarios)} event scenarios, "
        f"{len(achievement_types)} achievement types"
    )
    print(f"[ingest] promoted {promoted_blobs} icon blobs total")

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB", "wows")
    client = MongoClient(mongo_url)
    db = client[db_name]

    # Pick a data partition tag for this run. For a fresh version it's just
    # the version_tag itself. If we're re-ingesting the version that `latest`
    # currently aliases, write under a shadow tag instead so live readers
    # keep seeing the previous complete partition until we atomically flip
    # the alias at the end of this function.
    alias_id = "latest_pt" if args.pt else "latest"
    existing_alias = db.aliases.find_one({"_id": alias_id}) or {}
    previous_partition = existing_alias.get("data_partition") or existing_alias.get("client_version")
    if existing_alias.get("client_version") == version_tag:
        data_partition = f"{version_tag}__r{int(time.time())}"
        print(f"[ingest] re-ingest of live version {version_tag}; staging under {data_partition}")
    else:
        data_partition = version_tag

    # Each (client_version, id) pair is a unique document. Re-running the
    # ingest replaces the matching docs in place — handy while iterating.
    db.ships.create_index([("client_version", 1), ("id", 1)], unique=True)
    db.ships.create_index([("client_version", 1), ("nation", 1)])
    db.ships.create_index([("client_version", 1), ("type", 1)])
    db.nations.create_index([("client_version", 1), ("key", 1)], unique=True)
    db.ship_types.create_index([("client_version", 1), ("key", 1)], unique=True)
    db.spaces.create_index([("client_version", 1), ("key", 1)], unique=True)
    db.achievements.create_index([("client_version", 1), ("id", 1)], unique=True)
    db.achievements.create_index([("client_version", 1), ("ui_name", 1)])
    db.crew.create_index([("client_version", 1), ("id", 1)], unique=True)
    db.crew.create_index([("client_version", 1), ("index", 1)])
    db.crew.create_index([("client_version", 1), ("nation", 1)])
    db.battle_types.create_index([("client_version", 1), ("token", 1)], unique=True)
    db.ribbons.create_index([("client_version", 1), ("id", 1)], unique=True)
    db.ribbons.create_index([("client_version", 1), ("const_name", 1)])
    db.subribbons.create_index([("client_version", 1), ("id", 1)], unique=True)
    db.subribbons.create_index([("client_version", 1), ("parent_ribbon_id", 1)])
    db.battle_results.create_index([("client_version", 1), ("id", 1)], unique=True)
    db.game_modes.create_index([("client_version", 1), ("id", 1)], unique=True)
    db.event_scenarios.create_index([("client_version", 1), ("code", 1)], unique=True)
    db.achievement_types.create_index([("client_version", 1), ("name", 1)], unique=True)

    extracted_at = datetime.now(timezone.utc).isoformat()
    ops = []
    for ship in ships:
        ship["client_version"] = data_partition
        ship["extracted_at"] = extracted_at
        ops.append(UpdateOne(
            {"client_version": data_partition, "id": ship["id"]},
            {"$set": ship},
            upsert=True,
        ))
    if ops:
        result = db.ships.bulk_write(ops, ordered=False)
        print(f"[ingest] mongo: upserted={result.upserted_count} modified={result.modified_count}")

    nation_ops = []
    for nation in nations:
        nation["client_version"] = data_partition
        nation["extracted_at"] = extracted_at
        nation_ops.append(UpdateOne(
            {"client_version": data_partition, "key": nation["key"]},
            {"$set": nation},
            upsert=True,
        ))
    if nation_ops:
        result = db.nations.bulk_write(nation_ops, ordered=False)
        print(f"[ingest] mongo nations: upserted={result.upserted_count} modified={result.modified_count}")

    type_ops = []
    for st in ship_types:
        st["client_version"] = data_partition
        st["extracted_at"] = extracted_at
        type_ops.append(UpdateOne(
            {"client_version": data_partition, "key": st["key"]},
            {"$set": st},
            upsert=True,
        ))
    if type_ops:
        result = db.ship_types.bulk_write(type_ops, ordered=False)
        print(f"[ingest] mongo ship_types: upserted={result.upserted_count} modified={result.modified_count}")

    space_ops = []
    for sp in spaces:
        sp["client_version"] = data_partition
        sp["extracted_at"] = extracted_at
        space_ops.append(UpdateOne(
            {"client_version": data_partition, "key": sp["key"]},
            {"$set": sp},
            upsert=True,
        ))
    if space_ops:
        result = db.spaces.bulk_write(space_ops, ordered=False)
        print(f"[ingest] mongo spaces: upserted={result.upserted_count} modified={result.modified_count}")

    ach_ops = []
    for ach in achievements:
        ach["client_version"] = data_partition
        ach["extracted_at"] = extracted_at
        ach_ops.append(UpdateOne(
            {"client_version": data_partition, "id": ach["id"]},
            {"$set": ach},
            upsert=True,
        ))
    if ach_ops:
        result = db.achievements.bulk_write(ach_ops, ordered=False)
        print(f"[ingest] mongo achievements: upserted={result.upserted_count} modified={result.modified_count}")

    crew_ops = []
    for cr in crews:
        cr["client_version"] = data_partition
        cr["extracted_at"] = extracted_at
        crew_ops.append(UpdateOne(
            {"client_version": data_partition, "id": cr["id"]},
            {"$set": cr},
            upsert=True,
        ))
    if crew_ops:
        result = db.crew.bulk_write(crew_ops, ordered=False)
        print(f"[ingest] mongo crew: upserted={result.upserted_count} modified={result.modified_count}")

    bt_ops = []
    for bt in battle_types:
        bt["client_version"] = data_partition
        bt["extracted_at"] = extracted_at
        bt_ops.append(UpdateOne(
            {"client_version": data_partition, "token": bt["token"]},
            {"$set": bt},
            upsert=True,
        ))
    if bt_ops:
        result = db.battle_types.bulk_write(bt_ops, ordered=False)
        print(f"[ingest] mongo battle_types: upserted={result.upserted_count} modified={result.modified_count}")

    rib_ops = []
    for r in ribbons_docs:
        r["client_version"] = data_partition
        r["extracted_at"] = extracted_at
        rib_ops.append(UpdateOne(
            {"client_version": data_partition, "id": r["id"]},
            {"$set": r},
            upsert=True,
        ))
    if rib_ops:
        result = db.ribbons.bulk_write(rib_ops, ordered=False)
        print(f"[ingest] mongo ribbons: upserted={result.upserted_count} modified={result.modified_count}")

    sub_ops = []
    for sr in subribbons_docs:
        sr["client_version"] = data_partition
        sr["extracted_at"] = extracted_at
        sub_ops.append(UpdateOne(
            {"client_version": data_partition, "id": sr["id"]},
            {"$set": sr},
            upsert=True,
        ))
    if sub_ops:
        result = db.subribbons.bulk_write(sub_ops, ordered=False)
        print(f"[ingest] mongo subribbons: upserted={result.upserted_count} modified={result.modified_count}")

    def _bulk(coll_name: str, docs: list[dict], key_field: str) -> None:
        if not docs:
            return
        ops = []
        for d in docs:
            d["client_version"] = data_partition
            d["extracted_at"] = extracted_at
            ops.append(UpdateOne(
                {"client_version": data_partition, key_field: d[key_field]},
                {"$set": d},
                upsert=True,
            ))
        result = db[coll_name].bulk_write(ops, ordered=False)
        print(
            f"[ingest] mongo {coll_name}: "
            f"upserted={result.upserted_count} modified={result.modified_count}"
        )

    _bulk("battle_results",     battle_results,     "id")
    _bulk("game_modes",         game_modes,         "id")
    _bulk("event_scenarios",    event_scenarios,    "code")
    _bulk("achievement_types",  achievement_types,  "name")

    # Atomic publish: write the manifest with `ready: True` first (single
    # doc, atomic), then flip the alias (single doc, atomic). Until both
    # writes land, readers via `latest` keep seeing the previous partition.
    db.manifests.update_one(
        {"client_version": version_tag},
        {"$set": {
            "client_version": version_tag,
            "data_partition": data_partition,
            "extracted_at": extracted_at,
            "ship_count": len(ships),
            "is_pt": args.pt,
            "game_id": game_id,
            "ready": True,
        }},
        upsert=True,
    )
    db.aliases.update_one(
        {"_id": alias_id},
        {"$set": {
            "client_version": version_tag,
            "data_partition": data_partition,
            "updated_at": extracted_at,
        }},
        upsert=True,
    )

    # Now that the alias points at the new partition, drop the previous one
    # if it was a shadow we replaced. Best-effort: if cleanup fails, the
    # orphans are harmless (no manifest, no alias references them) and the
    # next successful run will retry.
    if previous_partition and previous_partition != data_partition:
        still_referenced = db.manifests.count_documents(
            {"data_partition": previous_partition}
        )
        if not still_referenced:
            _drop_partition(db, previous_partition)
    db.last_run.update_one(
        {"_id": "ingest"},
        {"$set": {
            "status": "success",
            "version_seen": version_tag,
            "version_ingested": version_tag,
            "error": None,
            "finished_at": extracted_at,
        }},
        upsert=True,
    )

    # Drop the heavy intermediates now that Mongo has the upserted state and
    # the icon SHAs are already promoted into ICONS_BLOBS_DIR. Keep the
    # version-tagged dir itself so a future manual `--client-version=X` re-run
    # has somewhere to land; just clear its bulky children. Skipped when the
    # caller fed us pre-extracted artifacts (we don't own those paths).
    if not args.gameparams:
        version_dir = args.workdir / version_tag
        for child in ("bin", "res_packages", "raw", "icons-staging", "scripts_shell"):
            target = version_dir / child
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)

    print(f"[ingest] done. version={version_tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
