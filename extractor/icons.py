"""Content-addressed storage for client image blobs (PNGs and JPGs).

Each unique image is stored once, named by its SHA-256 plus the source file
suffix, sharded by the first two hex chars (`blobs/<2>/<sha>.<ext>`). Same
image across patches → one blob. The model documents carry the *filename*
(`<sha>.<ext>`) — not just the SHA — so the URL builder can serve mixed
formats and StaticFiles can hand out the right Content-Type via the
extension.

Why CAS instead of `<patch>/<variant>/<short>.png`:
  - Most ship icons don't change between patches. The naive layout
    duplicates them every patch (~140K files / ~28 GB per year). CAS
    stores each unique image once (~12 K files / ~1.2 GB per year).
  - Filename = content hash → URLs are immutable → trivial cacheability
    (`Cache-Control: public, max-age=31536000, immutable`).

Atomic write: copy to `*.png.tmp`, then `os.rename`. On the same filesystem
this is atomic, so concurrent ingests writing the same blob are safe (one
wins; both write identical bytes anyway).
"""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path


def promote(src: Path, blobs_root: Path) -> str:
    """Hash `src`, store under `blobs_root/<2>/<sha><ext>`, return the filename.

    Returned value is `<sha>.<ext>` (e.g. `a1b2…d4ef.png`); the model fields
    persist this verbatim and the URL builder shards on `filename[:2]`."""
    suffix = src.suffix.lower()
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    filename = f"{sha}{suffix}"
    shard_dir = blobs_root / sha[:2]
    dest = shard_dir / filename
    if dest.exists():
        return filename
    shard_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(suffix + ".tmp")
    shutil.copyfile(src, tmp)
    os.rename(tmp, dest)
    return filename


# Where in the wowsunpack staging tree each Ship.icons field is sourced from.
# Stable contract: model field paths on the left, WG client paths on the right.
SILHOUETTE_SOURCES: dict[str, str] = {
    "default": "gui/ship_icons",
    "own":     "gui/ship_own_icons",
    "dead":    "gui/ship_dead_icons",
}
MEDIUM_SOURCE = "gui/ship_previews/medium"


def collect_for_ship(staging_root: Path, short_index: str) -> tuple[dict[str, Path], Path | None]:
    """Find which icon files exist on disk for one ship.

    Returns (silhouette_paths, medium_path_or_None). Variants missing for a
    given ship are simply omitted — not every ship has every variant
    (CVs, subs, special hulls vary)."""
    silhouette: dict[str, Path] = {}
    for key, src_dir in SILHOUETTE_SOURCES.items():
        p = staging_root / src_dir / f"{short_index}.png"
        if p.is_file():
            silhouette[key] = p
    med = staging_root / MEDIUM_SOURCE / f"{short_index}.png"
    return silhouette, (med if med.is_file() else None)


# Nation flag art lives in three pre-rendered sizes; filenames use the raw
# GameParams nation name (e.g. `flag_Japan.png`, `flag_United_Kingdom.png`).
NATION_FLAG_SOURCES: dict[str, str] = {
    "tiny":  "gui/nation_flags/tiny",
    "small": "gui/nation_flags/small",
    "big":   "gui/nation_flags/big",
}


# Class-marker icons. The `_big` variant lives in a `ship_classes_big/`
# subdir with a `_big` filename suffix; flavoured variants (premium/special/
# elite) sit alongside `default` in `ship_classes/` itself with the flavour
# baked into the filename. The species string is lowercased verbatim
# ("AirCarrier" → "aircarrier") to match the file naming.
_SHIP_CLASSES_DIR = "gui/service_kit/ship_classes"


def collect_for_ship_type(staging_root: Path, species: str) -> dict[str, Path]:
    """Find which class-marker icon variants exist on disk for one species.

    Missing variants are simply omitted; e.g. Auxiliary ships only `default`."""
    slug = species.lower()
    base = staging_root / _SHIP_CLASSES_DIR
    candidates: dict[str, Path] = {
        "default": base / f"icon_default_{slug}.png",
        "big":     base / "ship_classes_big" / f"icon_{slug}_big.png",
        "premium": base / f"icon_default_{slug}_premium.png",
        "special": base / f"icon_default_{slug}_special.png",
        "elite":   base / f"icon_default_{slug}_elite.png",
    }
    return {k: p for k, p in candidates.items() if p.is_file()}


# Per-space art shipped inside the gui pkg (no need to pull the 50 GB
# sdcontent space pkgs). Two parallel directories, both keyed by the same
# mixed-case dir-style filename (`s06_Atoll.jpg`, `53_Shoreside.jpg`,
# `04_Archipelago.jpg`). Locale keys are uppercase, so we case-insensitively
# match via a pre-built `{NAME_UPPER: path}` index per directory.
_SPACE_BG_SOURCES: dict[str, str] = {
    "preview": "gui/bg/training_room_maps_preview",  # ~5–35 KB thumbnails
    "bg":      "gui/bg/maps_bg_blur",                 # ~85–235 KB blurred bg
    "full":    "gui/maps_bg",                          # ~300 KB – 2 MB sharp bg
}


def index_space_bgs(staging_root: Path) -> dict[str, dict[str, Path]]:
    """Scan the gui/bg/ map directories once → {variant: {STEM_UPPER: path}}.

    Returned variants are the keys of `_SPACE_BG_SOURCES`. Missing source
    dirs (older patches, skip-icons run) yield an empty inner dict."""
    out: dict[str, dict[str, Path]] = {}
    for variant, src_dir in _SPACE_BG_SOURCES.items():
        base = staging_root / src_dir
        if base.is_dir():
            out[variant] = {p.stem.upper(): p for p in base.iterdir() if p.is_file()}
        else:
            out[variant] = {}
    return out


def collect_for_space(bg_index: dict[str, dict[str, Path]], key: str) -> dict[str, Path]:
    """Find which gui/bg variants exist for one space key.

    `key` is the locale slug verbatim (uppercase, e.g. "S06_ATOLL"); we
    uppercase-match against each variant's filename-stem index. Missing
    variants are simply omitted — coverage is partial (~76/83 preview,
    ~80/83 bg) and a few legacy keys have no art at all."""
    out: dict[str, Path] = {}
    upper = key.upper()
    for variant, stems in bg_index.items():
        p = stems.get(upper)
        if p is not None:
            out[variant] = p
    return out


_ACHIEVEMENT_DIR = "gui/achievements"


def collect_for_achievement(staging_root: Path, ui_name: str) -> dict[str, Path]:
    """Find the small + large medal art for one achievement.

    Files are `icon_achievement_<UI_NAME>.png` (small) and
    `..._L.png` (large). Both are optional — hidden / event achievements
    sometimes ship neither."""
    base = staging_root / _ACHIEVEMENT_DIR
    out: dict[str, Path] = {}
    small = base / f"icon_achievement_{ui_name}.png"
    if small.is_file():
        out["default"] = small
    large = base / f"icon_achievement_{ui_name}_L.png"
    if large.is_file():
        out["large"] = large
    return out


_CREW_PORTRAIT_DIR = "gui/crew_commander/base"


def collect_for_crew(staging_root: Path, raw_nation: str, person_name: str) -> Path | None:
    """Locate the portrait PNG for one commander, or None if not present.

    Standard crew use generic `base_<r>_<c>.png` slot art keyed to nation
    rather than the specific commander; we only treat a per-commander file
    (`<personName>.png` under the nation dir) as a real portrait. Some
    unique commanders also lack a dedicated file (e.g. influencer collabs
    that ship with promo art elsewhere) — those just stay null."""
    if not person_name:
        return None
    p = staging_root / _CREW_PORTRAIT_DIR / raw_nation / f"{person_name}.png"
    return p if p.is_file() else None


_BATTLE_TYPE_DIR = "gui/service_kit/battle_types"


def collect_for_battle_type(staging_root: Path, internal_name: str) -> dict[str, Path]:
    """Find the four sizes of battle-type marker art for one mode.

    `default` is the un-suffixed file; `small`/`tiny`/`big` are the suffixed
    siblings. Disabled-state PNGs are intentionally skipped — same image
    rendered greyed-out, can be reproduced client-side."""
    base = staging_root / _BATTLE_TYPE_DIR
    candidates: dict[str, Path] = {
        "default": base / f"{internal_name}.png",
        "small":   base / f"{internal_name}_small.png",
        "tiny":    base / f"{internal_name}_tiny.png",
        "big":     base / f"{internal_name}_big.png",
    }
    return {k: p for k, p in candidates.items() if p.is_file()}


_RIBBON_DIR = "gui/ribbons"
_SUBRIBBON_DIR = "gui/ribbons/subribbons"


def collect_for_ribbon(staging_root: Path, icon_name: str) -> Path | None:
    """Locate the PNG for one ribbon by its script-level `iconName`.

    Returns None if missing — a couple of newer/internal ribbons ship without
    art and that's fine."""
    p = staging_root / _RIBBON_DIR / f"{icon_name}.png"
    return p if p.is_file() else None


def collect_for_subribbon(staging_root: Path, icon_name: str) -> Path | None:
    """Locate the PNG for one sub-ribbon by its script-level `iconName`."""
    p = staging_root / _SUBRIBBON_DIR / f"{icon_name}.png"
    return p if p.is_file() else None


def collect_for_nation(staging_root: Path, raw_name: str) -> dict[str, Path]:
    """Find which flag size variants exist on disk for one nation.

    Missing sizes are simply omitted; not every nation ships every variant
    (event/special pseudo-nations sometimes only have `tiny`)."""
    out: dict[str, Path] = {}
    for key, src_dir in NATION_FLAG_SOURCES.items():
        p = staging_root / src_dir / f"flag_{raw_name}.png"
        if p.is_file():
            out[key] = p
    # Tree backdrops live in a sibling directory and use a bare filename
    # (no `flag_` prefix), so they don't fit the SOURCES table cleanly.
    tree = staging_root / "gui/nation_flag_tree" / f"{raw_name}.png"
    if tree.is_file():
        out["tree"] = tree
    return out
