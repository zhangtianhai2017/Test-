"""Bake every AccessoryEntry to an individual GLB + write a manifest.
Spec parity with the outfit GLBs: cm scale, +Y forward, asset.extras
tagged so UE glTFRuntime can import without per-asset config.

Accessories are STATIC meshes for now (rigid hardware doesn't deform).
A future revision can attach them to the MetaHuman skeleton at their
anchor_anatomy for skinned-by-bone follow."""
from __future__ import annotations

import io
import json
import os
import sys
import time

import numpy as np
from PIL import Image
import pygltflib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from accessory_pipeline.catalog import ACCESSORY_CATALOG
from accessory_pipeline.schema import AccessoryEntry
from accessory_pipeline.builders import build as build_mesh


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "assets", "accessories_v2", "glb")


def _pack(*arrays: np.ndarray):
    parts = []
    offs = []
    cur = 0
    for a in arrays:
        pad = (4 - (cur % 4)) % 4
        if pad:
            parts.append(b"\x00" * pad); cur += pad
        b = a.tobytes()
        offs.append((cur, len(b)))
        parts.append(b); cur += len(b)
    pad = (4 - (cur % 4)) % 4
    if pad:
        parts.append(b"\x00" * pad)
    return b"".join(parts), offs


def _hex_to_rgba(h: str) -> list[float]:
    h = (h or "#bfbfbf").lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return [r, g, b, 1.0]


def write_static_glb(out_path: str, V: np.ndarray, F: np.ndarray,
                     N: np.ndarray, entry: AccessoryEntry) -> int:
    blob, offs = _pack(V.astype(np.float32),
                       N.astype(np.float32),
                       F.astype(np.uint32))
    OFF_V, OFF_N, OFF_F = offs

    BV = [
        pygltflib.BufferView(buffer=0, byteOffset=OFF_V[0], byteLength=OFF_V[1],
                              target=pygltflib.ARRAY_BUFFER),
        pygltflib.BufferView(buffer=0, byteOffset=OFF_N[0], byteLength=OFF_N[1],
                              target=pygltflib.ARRAY_BUFFER),
        pygltflib.BufferView(buffer=0, byteOffset=OFF_F[0], byteLength=OFF_F[1],
                              target=pygltflib.ELEMENT_ARRAY_BUFFER),
    ]
    acc_pos = pygltflib.Accessor(bufferView=0, componentType=pygltflib.FLOAT,
                                  count=len(V), type=pygltflib.VEC3,
                                  min=V.min(axis=0).tolist(),
                                  max=V.max(axis=0).tolist())
    acc_nrm = pygltflib.Accessor(bufferView=1, componentType=pygltflib.FLOAT,
                                  count=len(N), type=pygltflib.VEC3)
    acc_idx = pygltflib.Accessor(bufferView=2, componentType=pygltflib.UNSIGNED_INT,
                                  count=int(F.size), type=pygltflib.SCALAR)

    material = pygltflib.Material(
        name=f"{entry.metal or 'metal'}",
        pbrMetallicRoughness=pygltflib.PbrMetallicRoughness(
            baseColorFactor=_hex_to_rgba(entry.base_color_hex),
            metallicFactor=float(entry.metallic),
            roughnessFactor=float(entry.roughness),
        ),
        doubleSided=False,
    )

    prim = pygltflib.Primitive(
        attributes=pygltflib.Attributes(POSITION=0, NORMAL=1),
        indices=2,
        material=0,
    )
    mesh = pygltflib.Mesh(name=entry.id, primitives=[prim])
    node = pygltflib.Node(name=entry.id, mesh=0)

    asset = pygltflib.Asset(
        version="2.0",
        generator="accessory_pipeline/bake",
        extras={
            "unitScale": "cm",
            "forwardAxis": "+Y",
            "accessoryFamily": entry.family,
            "anchorAnatomy": list(entry.anchor_anatomy),
            "mount": entry.mount,
            "bboxMm": list(entry.bbox_mm),
            "swingMode": entry.swing_mode,
            "metal": entry.metal,
            "ueImportSettings": {"SceneScale": 1.0, "ForwardAxis": "Y"},
        },
    )

    g = pygltflib.GLTF2(
        asset=asset,
        scenes=[pygltflib.Scene(nodes=[0])],
        scene=0,
        nodes=[node],
        meshes=[mesh],
        materials=[material],
        accessors=[acc_pos, acc_nrm, acc_idx],
        bufferViews=BV,
        buffers=[pygltflib.Buffer(byteLength=len(blob))],
    )
    g.set_binary_blob(blob)
    g.save_binary(out_path)
    return os.path.getsize(out_path)


def bake_one(entry: AccessoryEntry, out_dir: str = OUT_DIR,
              verbose: bool = True) -> dict:
    V, F, N = build_mesh(entry)
    out_path = os.path.join(out_dir, entry.id + ".glb")
    size = write_static_glb(out_path, V, F, N, entry)
    if verbose:
        print(f"  {entry.id:32s} {entry.family:18s} "
              f"V={len(V):4d} F={len(F):4d}  {size//1024} KB")
    return {
        "id": entry.id,
        "file": entry.id + ".glb",
        "family": entry.family,
        "displayName": entry.name,
        "tags": list(entry.tags),
        "metal": entry.metal,
        "baseColorHex": entry.base_color_hex,
        "metallic": entry.metallic,
        "roughness": entry.roughness,
        "mount": entry.mount,
        "anchorAnatomy": list(entry.anchor_anatomy),
        "bboxMm": list(entry.bbox_mm),
        "weightG": entry.weight_g,
        "swingMode": entry.swing_mode,
        "vertexCount": int(len(V)),
        "faceCount": int(len(F)),
        "sizeKb": size // 1024,
        "unitScale": "cm",
        "forwardAxis": "+Y",
    }


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    entries = list(ACCESSORY_CATALOG.values())
    t0 = time.time()
    out = []
    for e in entries:
        try:
            out.append(bake_one(e))
        except Exception as exc:
            print(f"  FAIL {e.id}: {exc}")
    manifest = {
        "version": 1,
        "type": "accessory_catalog",
        "skeleton": "MetaHuman UE5.6 Body",   # for skinned accessories later
        "unitScale": "cm",
        "forwardAxis": "+Y",
        "ueImportSettings": {"SceneScale": 1.0, "ForwardAxis": "Y"},
        "accessories": out,
    }
    with open(os.path.join(OUT_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nbaked {len(out)} accessories in {time.time()-t0:.1f}s -> {OUT_DIR}")


if __name__ == "__main__":
    main()
