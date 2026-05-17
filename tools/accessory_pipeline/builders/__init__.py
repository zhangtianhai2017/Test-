"""Builders convert an AccessoryEntry into a (vertices, faces, normals)
mesh tuple. One module per family, registered in BUILDERS."""
from __future__ import annotations

from ..schema import AccessoryEntry
from . import ring as _ring


BUILDERS = {
    "ring": _ring.build,
}


def build(entry: AccessoryEntry):
    fn = BUILDERS.get(entry.family)
    if fn is None:
        raise NotImplementedError(
            f"no builder for family '{entry.family}' (id={entry.id})")
    return fn(entry)
