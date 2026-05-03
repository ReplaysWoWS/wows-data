"""Build canonical Space documents from the locale catalog.

WG's GameParams binary doesn't carry a list of battle spaces (maps and
operation arenas) — that lives server-side and is only exposed once the
client connects. The locale catalogs, however, do carry the user-facing
names: any key under `IDS_SPACES/<KEY>` is the display label for a space,
with an optional `IDS_SPACES/<KEY>_DESCR` sibling holding the long blurb.

We treat the catalog as the source of truth for *which* spaces exist. This
includes test maps and a few legacy entries that are no longer in matchmaker
rotation — there's no clean signal to filter those out without server access,
so we ship the union and let consumers filter by key prefix if they want.
"""
from __future__ import annotations

from .models import Space

_PREFIX = "IDS_SPACES/"
_DESCR_SUFFIX = "_DESCR"


def discover_keys(translations: dict[str, dict[str, str]]) -> list[str]:
    """Return sorted, deduplicated list of space keys seen in any locale.

    Only the *base* key (no `_DESCR` suffix) is returned; descriptions are
    optional and looked up alongside the name in `normalise_space`."""
    seen: set[str] = set()
    for catalog in translations.values():
        for full_key in catalog:
            if not full_key.startswith(_PREFIX):
                continue
            tail = full_key[len(_PREFIX):]
            if tail.endswith(_DESCR_SUFFIX):
                tail = tail[: -len(_DESCR_SUFFIX)]
            if tail:
                seen.add(tail)
    return sorted(seen)


def _lookup(translations: dict[str, dict[str, str]], full_key: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for lang, catalog in translations.items():
        text = catalog.get(full_key)
        if text is not None:
            out[lang] = text
    return out


def normalise_space(key: str, translations: dict[str, dict[str, str]]) -> Space:
    name_i18n = _lookup(translations, f"{_PREFIX}{key}")
    descr_i18n = _lookup(translations, f"{_PREFIX}{key}{_DESCR_SUFFIX}")
    return Space(
        key=key,
        name=name_i18n.get("en") or key,
        name_i18n=name_i18n,
        description=descr_i18n.get("en", ""),
        description_i18n=descr_i18n,
    )
