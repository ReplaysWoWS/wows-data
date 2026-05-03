"""Read WoWS gettext catalogs and look up translations for IDS_* keys.

GameParams ship/module entries reference user-facing strings by `IDS_*` key
(e.g. `IDS_PJSB918_YAMATO_1944`, plus `_DESCR` variants for long descriptions).
The actual strings live in `res/texts/<lang>/LC_MESSAGES/global.mo` — standard
gettext .mo binary files.

We use a hand-rolled parser instead of stdlib `gettext.GNUTranslations`: WG's
.mo headers don't always declare a charset, so the stdlib falls back to ASCII
and chokes on the UTF-8 strings. The .mo binary format itself is simple
(documented at https://www.gnu.org/software/gettext/manual/html_node/MO-Files.html)
and a 30-line struct.unpack reader is more reliable here than monkey-patching
gettext.

We bundle every available locale into each ship document; query-time
projection in the API turns that into the WG-style single-language response
when the caller specifies `language=`.
"""
from __future__ import annotations

import struct
from pathlib import Path

# Map .mo directory name → WG-style language code as exposed in the encyclopedia.
# Dirs not in this table are passed through unchanged (covers `en`, `ru`, etc.
# and also surfaces non-WG-supported locales like `ko`, `nl`, `uk` for callers
# who want them).
_DIR_TO_LANG = {
    "zh": "zh-cn",
    "zh_tw": "zh-tw",
    "zh_sg": "zh-sg",
    "pt_br": "pt-br",
    "es_mx": "es-mx",
}

_MO_MAGIC_LE = 0x950412DE
_MO_MAGIC_BE = 0xDE120495


def _parse_mo(path: Path) -> dict[str, str]:
    """Parse a gettext .mo file → {original: translation}.

    Charset is read from the catalog metadata entry (empty-string original);
    most WoWS catalogs use UTF-8 but some declare cp1251/iso-8859-* and would
    crash a hardcoded UTF-8 decode."""
    data = path.read_bytes()
    magic = struct.unpack("<I", data[:4])[0]
    if magic == _MO_MAGIC_LE:
        endian = "<"
    elif magic == _MO_MAGIC_BE:
        endian = ">"
    else:
        raise RuntimeError(f"{path}: not a .mo file (magic {magic:#x})")

    # Header layout after magic: version, num_strings, orig_table_off,
    # trans_table_off, hash_size, hash_off (we only need the middle three).
    _version, num, orig_off, trans_off, _hash_size = struct.unpack(
        endian + "IIIII", data[4:24]
    )

    # Pass 1: find the metadata entry to determine charset.
    charset = "utf-8"
    for i in range(num):
        olen, ooff = struct.unpack(endian + "II", data[orig_off + i * 8 : orig_off + i * 8 + 8])
        if olen != 0:
            continue
        tlen, toff = struct.unpack(endian + "II", data[trans_off + i * 8 : trans_off + i * 8 + 8])
        header = data[toff : toff + tlen].decode("ascii", errors="replace")
        for line in header.splitlines():
            if line.lower().startswith("content-type:"):
                _, _, params = line.partition(":")
                for chunk in params.split(";"):
                    chunk = chunk.strip()
                    if chunk.lower().startswith("charset="):
                        charset = chunk.split("=", 1)[1].strip().lower()
        break

    catalog: dict[str, str] = {}
    for i in range(num):
        olen, ooff = struct.unpack(endian + "II", data[orig_off + i * 8 : orig_off + i * 8 + 8])
        tlen, toff = struct.unpack(endian + "II", data[trans_off + i * 8 : trans_off + i * 8 + 8])
        if olen == 0:
            continue
        original = data[ooff : ooff + olen].decode(charset, errors="replace")
        translation = data[toff : toff + tlen].decode(charset, errors="replace")
        catalog[original] = translation
    return catalog


def load_all(texts_dir: Path) -> dict[str, dict[str, str]]:
    """Walk the texts/ tree and return {lang_code: {key: translation}}."""
    result: dict[str, dict[str, str]] = {}
    for mo_path in sorted(texts_dir.glob("*/LC_MESSAGES/global.mo")):
        dir_name = mo_path.parent.parent.name
        lang = _DIR_TO_LANG.get(dir_name, dir_name)
        result[lang] = _parse_mo(mo_path)
    return result


def translate(translations: dict[str, dict[str, str]], key: str) -> dict[str, str]:
    """Look up `key` in every locale; return {lang: text} for hits.

    Empty dict means the key wasn't found in any catalog (common for content
    too new for the localisation pass to have caught up)."""
    out: dict[str, str] = {}
    for lang, catalog in translations.items():
        text = catalog.get(key)
        if text is not None:
            out[lang] = text
    return out
