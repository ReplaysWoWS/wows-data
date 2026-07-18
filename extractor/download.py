"""Download WoWS client assets from WGC and extract `content/GameParams.data`.

Two external CLIs do the heavy lifting:

  * `wgc-download` — pulls individual files out of the multi-GB client `.dspkg`
    archive on Wargaming's CDN via HTTP range requests. We use it to fetch
    the `.idx` files (WG's binary index for each .pkg) and the one `.pkg` that
    holds GameParams.data (`system_data_0001.pkg`, ~177 MB).
  * `wowsunpack` — knows how to read the WG-proprietary .idx + .pkg pair to
    extract individual files. We use just its `extract` subcommand; its
    `game-params` JSON converter is unmaintained and crashes on patch 15.x,
    so we run our own pickle decoder on the raw bytes (see gameparams.py).

The intermediate `.idx` files and the pkg are kept on disk so subsequent runs
of the same patch are fast (wgc-download skips files of the right size).
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

LIVE_GAME_ID = "WOWS.WW.PRODUCTION"
PT_GAME_ID = "WOWS.PT.PRODUCTION"

GAMEPARAMS_PKG = "res_packages/system_data_0001.pkg"
GUI_PKG = "res_packages/gui_0001.pkg"

# Source paths inside the unpacked client tree where ship icon PNGs live.
# Mirrors extractor/icons sources; kept here so wowsunpack only extracts what
# we ship to the API, not all 2 GB of GUI assets.
_ICON_PATHS = (
    "gui/ship_icons",
    "gui/ship_own_icons",
    "gui/ship_dead_icons",
    "gui/ship_previews/medium",
    "gui/nation_flags/tiny",
    "gui/nation_flags/small",
    "gui/nation_flags/big",
    "gui/nation_flag_tree",
    "gui/service_kit/ship_classes",
    "gui/bg/training_room_maps_preview",
    "gui/bg/maps_bg_blur",
    "gui/maps_bg",
    "gui/achievements",
    "gui/crew_commander/base",
    "gui/crew_commander/skills",
    "gui/service_kit/battle_types",
    "gui/ribbons",
)

_VERSION_RE = re.compile(r"\b(\d+\.\d+\.\d+\.\d+)\.(\d+)\b")


@dataclass(frozen=True)
class Version:
    """A WoWS client build identifier.

    `client_version` is the human-readable patch (e.g. "15.3.0.0"); `build` is
    the monotonic CDN build number Wargaming uses internally."""

    client_version: str
    build: int

    def tag(self, is_pt: bool) -> str:
        return f"{self.client_version}{'.PT' if is_pt else ''}"


def _run(args: list[str], **kwargs) -> str:
    """Run a subprocess; on failure raise with the captured stderr in the message."""
    proc = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command {args!r} exited {proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return proc.stdout


def latest_version(game_id: str = LIVE_GAME_ID) -> Version:
    """Query WGC for the newest available build of `game_id`."""
    output = _run(["wgc-download", "list", game_id])
    matches = _VERSION_RE.findall(output)
    if not matches:
        raise RuntimeError(f"could not parse version from wgc-download output:\n{output}")
    cv, build = max(matches, key=lambda m: int(m[1]))
    return Version(client_version=cv, build=int(build))


@lru_cache(maxsize=None)
def _content_build(game_id: str, resource: str, _catalog_build: int) -> int:
    """Discover the `bin/<build>/` dir used *inside* a resource archive.

    `wgc-download list` reports the launcher *catalog* build, which Wargaming
    sometimes bumps ahead of the actual content package (a launcher metadata
    refresh without re-packing the client). When that happens the catalog build
    (e.g. 12700454) no longer equals the build embedded in the dspkg's internal
    paths (e.g. bin/12668706/...), so filters built from the catalog build match
    zero files. Read the real build straight from the archive itself via
    `--list` — cheap (range requests, no full download).

    The archive can hold more than one `bin/<build>/` dir (an older base build
    lingers next to the current one, e.g. 12506899 alongside 12668706). The
    authoritative build is the one stamped in the dspkg filename
    (`wows.ww_15.5.0.0.12668706_client.dspkg`); we parse that, and only fall
    back to the newest `bin/<build>/` dir if the name isn't in the listing.

    `_catalog_build` is only a cache key: it changes every patch so the lru_cache
    re-resolves on a new version (important in --loop mode where game_id is
    constant). The returned value comes from the archive listing, not this arg.
    """
    output = _run(["wgc-download", "extract", game_id, resource, "--list"])
    # Authoritative: the build stamped in the dspkg name, e.g.
    # `wows.ww_15.5.0.0.12668706_client.dspkg`.
    name_match = re.search(r"\.(\d+)_\w+\.dspkg\b", output)
    if name_match:
        return int(name_match.group(1))
    # Fallback: newest bin/<build>/ dir present in the file index.
    builds = {int(b) for b in re.findall(r"\bbin/(\d+)/", output)}
    if not builds:
        raise RuntimeError(
            f"could not determine the content build for the {resource!r} "
            f"archive of {game_id} (no dspkg name or bin/<build>/ path in "
            f"--list output):\n{output}"
        )
    return max(builds)


_LOCALE_MO_RE = re.compile(r"(\S*res/texts)/[\w@-]+/LC_MESSAGES/global\.mo")


@lru_cache(maxsize=None)
def _locale_texts_prefix(game_id: str, _catalog_build: int) -> str:
    """Find the in-archive dir holding the per-language text dirs.

    The locale archive nests its texts under `bin/<build>/res/texts/`, but that
    build is *not* reliably the one stamped in the dspkg name: for 15.6.0.0 WG
    shipped `wows.ww_15.6.0.0.12866372_locale.dspkg` whose internal paths still
    carried the previous build, so a filter built from the name matched zero of
    the archive's 67 files. Unlike the client archive there is only ever one
    texts tree here, so instead of guessing a build we read the real prefix out
    of `--list` (cheap: range requests, no full download) and use it verbatim.

    `_catalog_build` is only a cache key — see `_content_build`.
    """
    output = _run(["wgc-download", "extract", game_id, "locale", "--list"])
    prefixes = {p.lstrip("/") for p in _LOCALE_MO_RE.findall(output)}
    if not prefixes:
        raise RuntimeError(
            f"could not find any `res/texts/<lang>/LC_MESSAGES/global.mo` in the "
            f"locale archive of {game_id}; its layout may have changed:\n{output}"
        )
    if len(prefixes) > 1:
        raise RuntimeError(
            f"locale archive of {game_id} has more than one texts tree "
            f"({sorted(prefixes)}); pick one explicitly"
        )
    return prefixes.pop()


def extract_locales(version: Version, game_id: str, dest: Path) -> Path:
    """Pull every `texts/<lang>/LC_MESSAGES/global.mo` from the locale dspkg.

    Returns the directory containing the per-language subfolders. ~30 MB."""
    dest.mkdir(parents=True, exist_ok=True)
    prefix = _locale_texts_prefix(game_id, version.build)
    _run([
        "wgc-download", "extract", game_id, "locale",
        "--filter", f"{prefix}/*/LC_MESSAGES/global.mo",
        "-d", str(dest),
    ])
    texts_dir = dest / prefix
    if not texts_dir.exists():
        raise RuntimeError(f"locale extraction produced no texts dir at {texts_dir}")
    return texts_dir


def extract_gameparams(version: Version, game_id: str, dest: Path) -> Path:
    """Pull what's needed and return path to the raw `GameParams.data`.

    Steps:
      1. wgc-download → `bin/<build>/idx/*.idx` (small, ~30 MB total)
      2. wgc-download → `res_packages/system_data_0001.pkg` (~177 MB)
      3. wowsunpack extract content/GameParams.data → raw bytes on disk
    """
    dest.mkdir(parents=True, exist_ok=True)
    build = _content_build(game_id, "client", version.build)
    idx_dir = dest / "bin" / str(build) / "idx"
    pkg_dir = dest / "res_packages"
    raw_dir = dest / "raw"

    _run([
        "wgc-download", "extract", game_id, "client",
        "--filter", f"bin/{build}/idx/*.idx",
        "-d", str(dest),
    ])
    _run([
        "wgc-download", "extract", game_id, "client",
        GAMEPARAMS_PKG,
        "-d", str(dest),
    ])

    _run([
        "wowsunpack",
        "--idx-files", str(idx_dir),
        "--pkg-dir", str(pkg_dir),
        "extract",
        "--out-dir", str(raw_dir),
        "content/GameParams.data",
    ])
    out = raw_dir / "content" / "GameParams.data"
    if not out.exists():
        raise RuntimeError(f"wowsunpack produced no GameParams.data at {out}")
    return out


def extract_scripts_enums(
    version: Version,
    game_id: str,
    dest: Path,
    dump_script: Path,
    wows_shell_dir: Path = Path("/opt/wows_shell"),
) -> Path:
    """Pull scripts.zip, run wows_shell against it, return path to the JSON.

    Steps:
      1. wgc-download → `bin/<build>/res/scripts.zip` (~40 MB, encrypted .pyc).
      2. Stage scripts.zip into the wows_shell `data/` dir so its embedded
         importer finds it (the binary hard-codes `./data/scripts.zip`).
      3. Run `wows_shell <dump_script>` from that dir; the script writes
         `/tmp/scripts_enums.json`.
      4. Move the JSON next to the staged scripts.zip and return its path.

    The dump script is python2 (wows_shell embeds patched CPython 2.7) and
    lives at `tools/dump_scripts_enums.py` in the repo. Regenerated every
    ingest so a new patch's TeamBuildType / Ribbon / GameMode entries land
    automatically — no manual step.
    """
    dest.mkdir(parents=True, exist_ok=True)
    build = _content_build(game_id, "client", version.build)
    scripts_zip_rel = f"bin/{build}/res/scripts.zip"
    _run([
        "wgc-download", "extract", game_id, "client",
        scripts_zip_rel,
        "-d", str(dest),
    ])
    src = dest / scripts_zip_rel
    if not src.exists():
        raise RuntimeError(f"wgc-download produced no scripts.zip at {src}")

    # wows_shell's importer reads `./data/scripts.zip` relative to its CWD.
    # Stage by copying so we don't disturb the unpacked client tree.
    staging = dest / "scripts_shell"
    (staging / "data").mkdir(parents=True, exist_ok=True)
    staged_zip = staging / "data" / "scripts.zip"
    if staged_zip.exists():
        staged_zip.unlink()
    staged_zip.write_bytes(src.read_bytes())

    # Make the dump script available alongside, then run.
    staged_script = staging / dump_script.name
    staged_script.write_bytes(dump_script.read_bytes())

    out_json = Path("/tmp/scripts_enums.json")
    if out_json.exists():
        out_json.unlink()
    _run(
        [str(wows_shell_dir / "wows_shell"), staged_script.name],
        cwd=staging,
    )
    if not out_json.exists():
        raise RuntimeError(
            f"wows_shell ran but did not produce {out_json}; "
            "check the dump script wrote the file"
        )
    final = dest / "scripts_enums.json"
    final.write_bytes(out_json.read_bytes())
    return final


def extract_icons(version: Version, game_id: str, dest: Path) -> Path:
    """Pull the gui pkg and extract ship icon PNGs into a staging directory.

    The gui pkg is large (~2 GB) and ranged downloads inside a pkg aren't
    supported by the wgc-download / pkg layout, so this is the slow part of
    the ingest. Output is per-patch staging (`<dest>/icons-staging/`) which
    the caller promotes into the content-addressed blob store.
    """
    dest.mkdir(parents=True, exist_ok=True)
    build = _content_build(game_id, "client", version.build)
    idx_dir = dest / "bin" / str(build) / "idx"
    pkg_dir = dest / "res_packages"
    staging = dest / "icons-staging"

    # gui.idx is needed alongside the pkg; reuse it if extract_gameparams
    # already pulled all idx files. Fetching it again is cheap (~few MB).
    _run([
        "wgc-download", "extract", game_id, "client",
        "--filter", f"bin/{build}/idx/gui.idx",
        "-d", str(dest),
    ])
    _run([
        "wgc-download", "extract", game_id, "client",
        GUI_PKG,
        "-d", str(dest),
    ])

    args = [
        "wowsunpack",
        "--idx-files", str(idx_dir),
        "--pkg-dir", str(pkg_dir),
        "extract",
        "--out-dir", str(staging),
    ]
    args.extend(_ICON_PATHS)
    _run(args)

    if not staging.exists():
        raise RuntimeError(f"wowsunpack produced no staging dir at {staging}")
    return staging
