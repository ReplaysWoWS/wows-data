"""Decode GameParams.data into a plain Python dict.

GameParams.data is a zlib-compressed pickle stream. Each top-level entry is an
instance of `GPData` (a tiny class WG ships in its scripts) whose `__dict__`
holds the actual parameters. Other classes referenced in pickle metadata
(`GameParams`, `TypeInfo`, etc.) are likewise empty containers — their pickled
state is just attribute dicts.

We register a permissive `Unpickler` that resolves any unknown class name to a
shared `_Bag` type. This avoids needing the full WG class hierarchy on the
PYTHONPATH while still recovering all data.

History: we briefly delegated decoding to `wowsunpack game-params`, but its
v0.8.0 deserializer choked on patch 15.x ("invalid type: map, expected a
hashable value"). Doing the decode ourselves keeps us independent of that
toolchain's release cadence — wowsunpack is now used only to extract the raw
file bytes from WG's .pkg containers.
"""
from __future__ import annotations

import pickle
import zlib
from pathlib import Path
from typing import Any


class _Bag:
    """Stand-in for any class pickled inside GameParams.data."""

    def __setstate__(self, state: Any) -> None:
        if isinstance(state, dict):
            self.__dict__.update(state)
        else:
            self.__dict__["_state"] = state


class _PermissiveUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> type:
        return _Bag


def _to_plain(obj: Any) -> Any:
    """Recursively convert _Bag instances to dicts so the result is JSON-shaped.

    Also coerces non-string dict keys to strings — WG uses numeric keys (often
    floats for dispersion / curve lookup tables) which are valid Python but
    rejected by both BSON and JSON."""
    if isinstance(obj, _Bag):
        return {str(k): _to_plain(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, dict):
        return {str(k): _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    return obj


def decode(path: Path) -> dict[str, Any]:
    """Load GameParams.data and return the canonical {entry_name: data} dict.

    Wargaming stores the file as: pickle.dumps → zlib.compress → BYTE-REVERSE.
    The reversal is a trivial anti-tamper that EdibleBug/WoWS-GameParams
    documents; we undo it before decompressing.

    Modern (15.x) layout: the root is a dict keyed by realm — `""` is the base
    table all realms share, then `RU`/`CN`/`PT`/`NA`/`EU`/`ASIA`/etc. carry
    per-realm overrides for ship names, balance, etc. We return the base
    table; per-realm overlays are a follow-up if/when we expose them.
    Older layouts wrapped a single dict in a list; both shapes are handled.
    """
    raw = path.read_bytes()
    decompressed = zlib.decompress(raw[::-1])
    obj = _PermissiveUnpickler(_BytesReader(decompressed)).load()
    plain = _to_plain(obj)
    if isinstance(plain, list) and plain and isinstance(plain[0], dict):
        plain = plain[0]
    if not isinstance(plain, dict):
        raise RuntimeError(f"unexpected GameParams root type: {type(plain).__name__}")
    if "" in plain and isinstance(plain[""], dict):
        return plain[""]
    return plain


class _BytesReader:
    """pickle.Unpickler wants a file-like object."""

    def __init__(self, buf: bytes) -> None:
        self._buf = buf
        self._pos = 0

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            n = len(self._buf) - self._pos
        chunk = self._buf[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def readline(self) -> bytes:
        nl = self._buf.find(b"\n", self._pos)
        end = len(self._buf) if nl < 0 else nl + 1
        chunk = self._buf[self._pos : end]
        self._pos = end
        return chunk
