# Run inside monstrofil/wows-sandbox's wows_shell, NOT cpython3:
#   PYTHONHOME=3rdparty/cpython ./wows_shell <this script>
#
# Dumps the script-level enums, battle-type tables, and Ribbon/SubRibbon
# instance catalogs that the ingest pipeline needs. The output JSON is read
# directly by extractor/normalize_*.py - there is no checked-in fallback,
# so this script runs every ingest cycle as part of the wgc-download flow.
#
# Regenerate manually only if you're iterating on the script itself; the
# ingest loop will call it for each new patch automatically.
#
# This file is python2 (wows_shell embeds a patched Python 2.7); do not add
# unicode-escape literals or other py3-only constructs.
import sys, json

# --- six static enum classes (int/str scalars) ---
PICKS = [
    ("battle_result",    "BATTLE_RESULT"),
    ("game_mode",        "GameMode"),
    ("event_scenario",   "EVENTS"),
    ("achievement_type", "ACHIEVEMENT_TYPE"),
]

found = {}
for mod_name, mod in sorted(sys.modules.items()):
    if mod is None: continue
    for key, cls_name in PICKS:
        if key in found: continue
        v = getattr(mod, cls_name, None)
        if isinstance(v, type):
            found[key] = (mod_name, v)

out = {}
for key, cls_name in PICKS:
    if key not in found:
        raise RuntimeError("class %s not found - was the renamed in this patch?" % cls_name)
    mod_name, cls = found[key]
    rows = []
    for an in dir(cls):
        if an.startswith("_"): continue
        try: av = getattr(cls, an)
        except: continue
        if callable(av): continue
        if isinstance(av, (int, str, bool)):
            rows.append({"name": an, "value": av})
    rows.sort(key=lambda r: (str(type(r["value"]).__name__), r["value"], r["name"]))
    out[key] = {"source_module": mod_name, "source_class": cls_name, "entries": rows}

# --- BattleDefinitions: TeamBuildType + BATTLE_TYPES + BATTLE_TYPE_TO_MATCH ---
import BattleDefinitions as BD
tbt_entries = []
for an in dir(BD.TeamBuildType):
    if an.startswith("_"): continue
    av = getattr(BD.TeamBuildType, an)
    if isinstance(av, int) and not isinstance(av, bool):
        tbt_entries.append({"name": an, "value": av})
tbt_entries.sort(key=lambda r: r["value"])

bt_list = None
for mod in sys.modules.values():
    if mod is None: continue
    bt_cls = getattr(mod, "BATTLE_TYPES", None)
    if bt_cls is not None and hasattr(bt_cls, "MAP_TEAMBUILDTYPE_TO_BATTLETYPE"):
        bt_list = list(bt_cls.MAP_TEAMBUILDTYPE_TO_BATTLETYPE)
        break
if bt_list is None:
    raise RuntimeError("MAP_TEAMBUILDTYPE_TO_BATTLETYPE not found in any module")

out["battle_type"] = {
    "source_module": "BattleDefinitions",
    "team_build_type": tbt_entries,
    "tbt_to_battle_type": bt_list,
    "battle_type_to_match_group": dict(BD.MatchGroup.BATTLE_TYPE_TO_MATCH),
}

# --- Ribbon / SubRibbon: instance catalogs ---
# Each class exposes its members as class-level attributes (Ribbon.MAIN_CALIBER,
# etc.) where every member is itself an instance of the class carrying
# id/iconName/ids/subRibbons. The home modules are obfuscated and rename every
# patch - find by class name, never by module path.
def _instance_rows(cls):
    rows = []
    for an in dir(cls):
        if an.startswith("_"): continue
        try: av = getattr(cls, an)
        except: continue
        if not isinstance(av, cls): continue
        row = {"const_name": an}
        for attr in ("id", "iconName", "ids"):
            if hasattr(av, attr):
                row[attr] = getattr(av, attr)
        sub = getattr(av, "subRibbons", None)
        if sub is not None:
            # subRibbons may be a list of SubRibbon instances or already a
            # list of int ids depending on the patch - normalise to ints.
            row["subRibbons"] = [
                s.id if hasattr(s, "id") else int(s) for s in sub
            ]
        rows.append(row)
    rows.sort(key=lambda r: r.get("id", 0))
    return rows

def _find_populated_class(class_name):
    """Locate the class definition that actually carries instance members.

    There can be multiple classes named e.g. `Ribbon` across loaded modules
    (a base/proxy plus the real one in an obfuscated module). Pick the one
    whose class-level attributes include actual instances of itself - i.e.
    the one with non-empty `_instance_rows`. If none has instance-level
    attributes, raise so we don't silently ship an empty catalog."""
    candidates = []
    for mod_name, mod in sorted(sys.modules.items()):
        if mod is None: continue
        v = getattr(mod, class_name, None)
        if not isinstance(v, type): continue
        if v in [c[1] for c in candidates]: continue  # dedupe re-exports
        rows = _instance_rows(v)
        candidates.append((mod_name, v, rows))
    if not candidates:
        raise RuntimeError("class %s not found in any loaded module" % class_name)
    populated = [c for c in candidates if c[2]]
    if not populated:
        raise RuntimeError(
            "class %s found in %d module(s) but none expose instance members "
            "as class-level attributes - WG may have changed the access "
            "pattern. Candidates: %s" % (
                class_name, len(candidates),
                [c[0] for c in candidates],
            ))
    populated.sort(key=lambda c: -len(c[2]))
    return populated[0]

ribbon_mod, RibbonCls, ribbon_rows = _find_populated_class("Ribbon")
out["ribbon"] = {
    "source_module": ribbon_mod,
    "source_class": "Ribbon",
    "entries": ribbon_rows,
}

subribbon_mod, SubRibbonCls, subribbon_rows = _find_populated_class("SubRibbon")
out["subribbon"] = {
    "source_module": subribbon_mod,
    "source_class": "SubRibbon",
    "entries": subribbon_rows,
}

with open("/tmp/scripts_enums.json", "w") as f:
    json.dump(out, f, indent=2, sort_keys=True)
print "wrote /tmp/scripts_enums.json"
for k, v in out.items():
    if k == "battle_type":
        print "  %-20s = %d tbt / %d list / %d match" % (
            k, len(v["team_build_type"]), len(v["tbt_to_battle_type"]),
            len(v["battle_type_to_match_group"]))
    elif k in ("ribbon", "subribbon"):
        print "  %-20s = %d entries (from %s)" % (k, len(v["entries"]), v["source_module"])
    else:
        print "  %-20s = %d entries" % (k, len(v["entries"]))
