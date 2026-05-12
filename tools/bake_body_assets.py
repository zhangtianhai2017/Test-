"""Cache the MetaHuman body skinning data for later use by the
.glb baker.

Input: a skinned **glTF / glb** of the MetaHuman body (export from UE
via Asset Actions → Export → glTF, or via fbx2gltf if you have a
Maya/Blender source).

We chose glTF over FBX because:
  - pygltflib is pure-Python and trivial to install
  - FBX parsing on Linux requires either Autodesk's closed-source SDK
    (license-restricted) or assimp/pyassimp (frequently broken).

Output: assets/glb/_body_skin.pkl  — a dict with:
    body_verts      (M, 3) float32           bind-pose vertex positions
    body_joints     (M, 4) uint16            joint indices per vertex
    body_weights    (M, 4) float32           joint weights per vertex
    joint_names     list[str]                bone names (length J)
    inverse_binds   (J, 4, 4) float32        inverse-bind matrices
    bind_matrices   (J, 4, 4) float32        bind-pose joint matrices

The baker (bake_v2_glb_skinned.py) reads this once and reuses across
all 37+ outfits.
"""
from __future__ import annotations

import argparse
import os
import pickle
import struct

import numpy as np
import pygltflib


def _accessor_to_np(g: pygltflib.GLTF2, accessor_idx: int) -> np.ndarray:
    acc = g.accessors[accessor_idx]
    bv = g.bufferViews[acc.bufferView]
    buf = g.binary_blob() if g.binary_blob() else None
    if buf is None:
        # external .bin
        with open(os.path.join(os.path.dirname(g._path), g.buffers[bv.buffer].uri), "rb") as f:
            buf = f.read()

    offset = (bv.byteOffset or 0) + (acc.byteOffset or 0)
    count = acc.count

    type_map = {
        pygltflib.SCALAR: 1, pygltflib.VEC2: 2, pygltflib.VEC3: 3,
        pygltflib.VEC4: 4, pygltflib.MAT4: 16,
    }
    components = type_map[acc.type]

    dtype_map = {
        pygltflib.BYTE:           np.int8,
        pygltflib.UNSIGNED_BYTE:  np.uint8,
        pygltflib.SHORT:          np.int16,
        pygltflib.UNSIGNED_SHORT: np.uint16,
        pygltflib.UNSIGNED_INT:   np.uint32,
        pygltflib.FLOAT:          np.float32,
    }
    dtype = dtype_map[acc.componentType]
    nbytes = count * components * dtype().nbytes

    arr = np.frombuffer(buf[offset:offset + nbytes], dtype=dtype)
    if components > 1:
        arr = arr.reshape((count, components))
    return arr.copy()


def extract_body_skin(glb_path: str) -> dict:
    g = pygltflib.GLTF2().load(glb_path)
    g._path = glb_path  # for external .bin lookup

    if not g.skins:
        raise RuntimeError(f"{glb_path} has no skin — body must be skinned glTF")
    skin = g.skins[0]

    # Joint nodes → bone names
    joint_names = [g.nodes[ni].name or f"bone_{ni}" for ni in skin.joints]
    inverse_binds = _accessor_to_np(g, skin.inverseBindMatrices).reshape((-1, 4, 4)).astype(np.float32)

    # Find first mesh primitive that has skinning attributes
    body_mesh_idx = None
    for ni in skin.joints:  # walk meshes that share this skin
        pass
    # actually look for a node referencing this skin
    body_node = None
    for n in g.nodes:
        if n.skin == 0 and n.mesh is not None:
            body_node = n
            break
    if body_node is None:
        raise RuntimeError("no node references skin 0")
    prim = g.meshes[body_node.mesh].primitives[0]

    body_verts   = _accessor_to_np(g, prim.attributes.POSITION).astype(np.float32)
    body_joints  = _accessor_to_np(g, prim.attributes.JOINTS_0).astype(np.uint16)
    body_weights = _accessor_to_np(g, prim.attributes.WEIGHTS_0).astype(np.float32)

    if body_joints.ndim == 1:    # scalar joint? shouldn't happen
        body_joints = body_joints[:, None]
    if body_weights.ndim == 1:
        body_weights = body_weights[:, None]

    # bind_matrices = inv(inverse_binds)
    bind_matrices = np.linalg.inv(inverse_binds).astype(np.float32)

    out = dict(
        body_verts=body_verts,
        body_joints=body_joints,
        body_weights=body_weights,
        joint_names=joint_names,
        inverse_binds=inverse_binds,
        bind_matrices=bind_matrices,
    )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("body_glb",
                    help="path to a skinned MetaHuman body .glb / .gltf")
    ap.add_argument("--out", default="assets/glb/_body_skin.pkl")
    args = ap.parse_args()

    print(f"loading {args.body_glb}…")
    data = extract_body_skin(args.body_glb)
    print(f"  body_verts:   {data['body_verts'].shape}")
    print(f"  joint_names:  {len(data['joint_names'])}  "
          f"({data['joint_names'][:6]}…)")
    print(f"  inverse_binds:{data['inverse_binds'].shape}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "wb") as f:
        pickle.dump(data, f)
    print(f"wrote {args.out}  ({os.path.getsize(args.out)//1024} KB)")


if __name__ == "__main__":
    main()
