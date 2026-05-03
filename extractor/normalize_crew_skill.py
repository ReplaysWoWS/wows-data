"""Map raw GameParams Skill blocks to canonical CrewSkill docs.

Skills are nested per-Crew under `Skills` (82 entries each, but the same
skill key appears in multiple crews with identical payloads). We dedupe
across all Crew entries on the skill's GameParams key — the first hit wins
and any subsequent collisions are checked for `skillType` consistency so a
divergent payload fails the ingest loudly.

Locale convention is `IDS_SKILL_<UPPER_SNAKE(name)>` for the display name
and `IDS_SKILL_DESC_<UPPER_SNAKE(name)>` for the long description. Many
descriptions ship as a single space — that's WG's data, we surface it as-is.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from . import locale
from .models import CrewSkill


_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _upper_snake(name: str) -> str:
    """`PlanesTorpedoUwReduced` → `PLANES_TORPEDO_UW_REDUCED`."""
    return _CAMEL_RE.sub("_", name).upper()


def iter_skill_keys(gameparams: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    """Walk every Crew entry and yield each unique (skill_key, skill_payload).

    Identical payloads under the same key across crews are collapsed; a
    payload divergence (different `skillType` for the same key) raises so
    the operator notices before bad data lands in Mongo.
    """
    seen: dict[str, dict[str, Any]] = {}
    for entry in gameparams.values():
        if not isinstance(entry, dict):
            continue
        ti = entry.get("typeinfo")
        if not (isinstance(ti, dict) and ti.get("type") == "Crew"):
            continue
        skills = entry.get("Skills") or {}
        for skill_key, payload in skills.items():
            if not isinstance(payload, dict):
                continue
            existing = seen.get(skill_key)
            if existing is None:
                seen[skill_key] = payload
                continue
            if existing.get("skillType") != payload.get("skillType"):
                raise RuntimeError(
                    f"skill {skill_key!r} has divergent skillType across crews: "
                    f"{existing.get('skillType')} vs {payload.get('skillType')}"
                )
    for k in sorted(seen):
        yield k, seen[k]


def normalise_crew_skill(
    skill_key: str,
    raw: dict[str, Any],
    translations: dict[str, dict[str, str]] | None = None,
) -> CrewSkill:
    upper = _upper_snake(skill_key)
    name_i18n = locale.translate(translations or {}, f"IDS_SKILL_{upper}")
    desc_i18n = locale.translate(translations or {}, f"IDS_SKILL_DESC_{upper}")
    tier_raw = raw.get("tier") or {}
    # Coerce per-class tier values to int. WG stores them as ints already but
    # the permissive unpickler returns whatever was on the wire, so guard.
    tiers = {str(k): int(v) for k, v in tier_raw.items() if isinstance(v, (int, float))}
    return CrewSkill(
        id=int(raw["skillType"]),
        internal_name=skill_key,
        name=name_i18n.get("en") or skill_key,
        name_i18n=name_i18n,
        description=desc_i18n.get("en", ""),
        description_i18n=desc_i18n,
        tiers=tiers,
        is_epic=bool(raw.get("isEpic", False)),
        is_trigger=bool(raw.get("uiTreatAsTrigger", False)),
    )
