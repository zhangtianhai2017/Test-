"""Refit existing skinned .glb files to the UE 5.6 MetaHuman Body
deliverable spec:

  1. Joint names == UE 5.6 MetaHuman Body skeleton names (already true).
  2. Parent/child hierarchy matches MetaHumanSkeletonDefinitions.inl
     (uses tools/metahuman_skeleton.BODY_HIERARCHY).
  3. No corrective/helper/dyn bones as weight targets — these are
     folded into their nearest stable ancestor via
     `fold_to_whitelist_ancestor`.
  4. Only stable deform bones present in skin.joints (whitelist of 70).
  5. <= 4 influences per vertex, weights normalised, sum to 1.
  6. Bone count = 70 (well under 128 / 256).
  7. Unit = cm, forward axis = +Y, marked in asset.extras
     so the UE side can disable SceneScale=0.1.
  8. Skinned mesh preserved (POSITION/NORMAL/TEXCOORD_0/JOINTS_0/WEIGHTS_0).
  9. inverseBindMatrices sliced to the 70 kept joints.
 10. manifest.json rewritten with the deliverable schema:
        {file, displayName, slots, skeleton, unitScale,
         forwardAxis, boneCount, vertexCount}

The script edits each .glb in place AND rebuilds
``assets/glb/manifest.json``.  No mesh geometry is touched.

Usage:
    python3 tools/refit_metahuman_glb.py                # all *.glb
    python3 tools/refit_metahuman_glb.py composite_red  # just one
"""
from __future__ import annotations

import argparse
import io
import json
import os
import struct
import sys
import time
from collections import OrderedDict

import numpy as np
import pygltflib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metahuman_skeleton import (
    BODY_HIERARCHY, STABLE_DEFORM_WHITELIST, WHITELIST_SET,
    fold_to_whitelist_ancestor, parent_of,
)


GLB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "assets", "glb")
SEEDS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "assets", "seeds_v2")


# ---------------------------------------------------------------------------
# Binary helpers
# ---------------------------------------------------------------------------

def _bv_bytes(g: pygltflib.GLTF2, bv_idx: int) -> bytes:
    """Slice the right portion of the embedded BIN out of a glb."""
    bv = g.bufferViews[bv_idx]
    blob = g.binary_blob() or b""
    off = bv.byteOffset or 0
    return blob[off : off + bv.byteLength]


_COMP_FMT = {
    pygltflib.UNSIGNED_BYTE:  ("B", 1),
    pygltflib.UNSIGNED_SHORT: ("H", 2),
    pygltflib.UNSIGNED_INT:   ("I", 4),
    pygltflib.FLOAT:          ("f", 4),
    pygltflib.BYTE:           ("b", 1),
    pygltflib.SHORT:          ("h", 2),
}
_TYPE_DIM = {
    pygltflib.SCALAR: 1, pygltflib.VEC2: 2, pygltflib.VEC3: 3,
    pygltflib.VEC4: 4, pygltflib.MAT4: 16,
}


def _read_accessor(g: pygltflib.GLTF2, acc_idx: int) -> np.ndarray:
    acc = g.accessors[acc_idx]
    fmt_char, _ = _COMP_FMT[acc.componentType]
    dim = _TYPE_DIM[acc.type]
    bv = g.bufferViews[acc.bufferView]
    blob = g.binary_blob() or b""
    off = (bv.byteOffset or 0) + (acc.byteOffset or 0)
    n_items = acc.count * dim
    np_dtype = np.dtype(fmt_char).newbyteorder("<")
    arr = np.frombuffer(blob, dtype=np_dtype,
                        count=n_items, offset=off)
    if dim > 1:
        arr = arr.reshape(acc.count, dim)
    return arr.copy()  # detach from blob memory


def _pack_aligned(*arrays: np.ndarray) -> tuple[bytes, list[tuple[int, int]]]:
    parts: list[bytes] = []
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for a in arrays:
        pad = (4 - (cursor % 4)) % 4
        if pad:
            parts.append(b"\x00" * pad)
            cursor += pad
        b = a.tobytes()
        offsets.append((cursor, len(b)))
        parts.append(b)
        cursor += len(b)
    pad = (4 - (cursor % 4)) % 4
    if pad:
        parts.append(b"\x00" * pad)
    return b"".join(parts), offsets


# ---------------------------------------------------------------------------
# Weight folding
# ---------------------------------------------------------------------------

def _fold_weights(joint_names: list[str],
                  joints: np.ndarray,
                  weights: np.ndarray
                  ) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Collapse every non-whitelist joint reference into its nearest
    whitelisted ancestor.  Returns the kept joint name list (preserving
    STABLE_DEFORM_WHITELIST order, only including joints actually
    referenced or required for hierarchy completeness), and new
    (joints, weights) arrays addressed to the kept-list.

    joints  : (V, K)  uint16
    weights : (V, K)  float32
    """
    n_verts, k = joints.shape
    # map each source-index -> destination joint NAME
    source_to_dest_name: dict[int, str] = {}
    for src_idx, src_name in enumerate(joint_names):
        dest = fold_to_whitelist_ancestor(src_name)
        source_to_dest_name[src_idx] = dest

    # build kept list in the canonical whitelist order, only including
    # the joints that actually receive weight
    received: set[str] = set(source_to_dest_name.values())
    kept_names: list[str] = [j for j in STABLE_DEFORM_WHITELIST if j in received]
    # add any whitelist joints that didn't receive weight too, so the
    # output skeleton is identical across all outfits (UE prefers a
    # stable bone list for animation compatibility)
    for j in STABLE_DEFORM_WHITELIST:
        if j not in kept_names:
            kept_names.append(j)

    name_to_dest_idx: dict[str, int] = {n: i for i, n in enumerate(kept_names)}

    # accumulate per-vertex contributions
    new_joints  = np.zeros((n_verts, 4), dtype=np.uint16)
    new_weights = np.zeros((n_verts, 4), dtype=np.float32)

    # vector path: build remap table src_idx -> dest_idx
    remap = np.full(len(joint_names), -1, dtype=np.int32)
    for src_idx, dest_name in source_to_dest_name.items():
        remap[src_idx] = name_to_dest_idx[dest_name]

    # accumulate using dict per vertex (k is small, 4 in our case)
    for vi in range(n_verts):
        accum: dict[int, float] = {}
        for ki in range(k):
            w = float(weights[vi, ki])
            if w <= 0.0:
                continue
            d = int(remap[int(joints[vi, ki])])
            if d < 0:
                continue
            accum[d] = accum.get(d, 0.0) + w
        if not accum:
            # vertex had no weight (shouldn't happen) — pin to root
            new_joints[vi, 0]  = name_to_dest_idx["root"]
            new_weights[vi, 0] = 1.0
            continue
        # top-4 by weight
        items = sorted(accum.items(), key=lambda kv: kv[1], reverse=True)[:4]
        total = sum(w for _, w in items)
        for slot, (dj, dw) in enumerate(items):
            new_joints[vi, slot]  = dj
            new_weights[vi, slot] = dw / total

    return kept_names, new_joints, new_weights


# ---------------------------------------------------------------------------
# Re-emission
# ---------------------------------------------------------------------------

def _mat_to_quat(M: np.ndarray) -> np.ndarray:
    s = np.linalg.norm(M, axis=0)
    R = M / np.where(s > 1e-8, s, 1.0)
    t = R[0, 0] + R[1, 1] + R[2, 2]
    if t > 0:
        S = np.sqrt(t + 1.0) * 2
        w = 0.25 * S
        x = (R[2, 1] - R[1, 2]) / S
        y = (R[0, 2] - R[2, 0]) / S
        z = (R[1, 0] - R[0, 1]) / S
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        S = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w = (R[2, 1] - R[1, 2]) / S
        x = 0.25 * S; y = (R[0, 1] + R[1, 0]) / S; z = (R[0, 2] + R[2, 0]) / S
    elif R[1, 1] > R[2, 2]:
        S = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w = (R[0, 2] - R[2, 0]) / S
        x = (R[0, 1] + R[1, 0]) / S; y = 0.25 * S; z = (R[1, 2] + R[2, 1]) / S
    else:
        S = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w = (R[1, 0] - R[0, 1]) / S
        x = (R[0, 2] + R[2, 0]) / S; y = (R[1, 2] + R[2, 1]) / S; z = 0.25 * S
    return np.array([x, y, z, w], dtype=np.float32)


def _mat_to_scale(M: np.ndarray) -> np.ndarray:
    return np.linalg.norm(M, axis=0).astype(np.float32)


def _world_bind(ibm: np.ndarray) -> np.ndarray:
    """invert inverseBindMatrices to recover world bind transforms."""
    out = np.empty_like(ibm)
    for i in range(ibm.shape[0]):
        out[i] = np.linalg.inv(ibm[i])
    return out


def refit(glb_path: str, verbose: bool = True) -> dict:
    g = pygltflib.GLTF2().load(glb_path)

    if len(g.skins) != 1 or len(g.meshes) != 1:
        raise RuntimeError(f"{glb_path}: expected 1 skin + 1 mesh, "
                            f"got {len(g.skins)} skins / {len(g.meshes)} meshes")

    skin = g.skins[0]
    joint_names_full = [g.nodes[j].name for j in skin.joints]
    ibm_full = _read_accessor(g, skin.inverseBindMatrices).reshape(-1, 4, 4)
    # glTF stores matrices column-major
    ibm_full = ibm_full.transpose(0, 2, 1).astype(np.float32)

    # Read primitive attributes
    mesh = g.meshes[0]
    prim = mesh.primitives[0]
    V  = _read_accessor(g, prim.attributes.POSITION).astype(np.float32)
    N  = _read_accessor(g, prim.attributes.NORMAL).astype(np.float32) \
            if prim.attributes.NORMAL is not None else np.zeros_like(V)
    UV = _read_accessor(g, prim.attributes.TEXCOORD_0).astype(np.float32) \
            if prim.attributes.TEXCOORD_0 is not None else np.zeros((len(V), 2), np.float32)
    J  = _read_accessor(g, prim.attributes.JOINTS_0).astype(np.uint16).reshape(-1, 4)
    W  = _read_accessor(g, prim.attributes.WEIGHTS_0).astype(np.float32).reshape(-1, 4)
    F  = _read_accessor(g, prim.indices).astype(np.uint32).ravel()

    kept_names, new_J, new_W = _fold_weights(joint_names_full, J, W)

    # Build new bind / IBM for kept set
    world_bind_full = _world_bind(ibm_full)
    full_idx = {n: i for i, n in enumerate(joint_names_full)}
    world_bind_kept = np.stack([
        world_bind_full[full_idx[n]] if n in full_idx
        else np.eye(4, dtype=np.float32)
        for n in kept_names
    ])
    new_ibm_kept = np.empty_like(world_bind_kept)
    for i in range(len(kept_names)):
        new_ibm_kept[i] = np.linalg.inv(world_bind_kept[i])

    # parents for kept set (walked via BODY_HIERARCHY through whitelist only)
    kept_name_to_idx = {n: i for i, n in enumerate(kept_names)}
    kept_parents = []
    for n in kept_names:
        p = parent_of(n) if n != "root" else None
        kept_parents.append(kept_name_to_idx[p] if p in kept_name_to_idx else -1)

    # ---- texture / albedo: copy existing image bufferView raw bytes ----
    # The mesh's existing material is preserved by reading from the
    # incoming GLB; we re-emit the texture as its raw PNG bytes via a
    # fresh bufferView at the end of the bin blob.
    img_bv_idx = None
    if g.images:
        img = g.images[0]
        if img.bufferView is not None:
            img_bv_idx = img.bufferView
    png_bytes = b""
    if img_bv_idx is not None:
        png_bytes = _bv_bytes(g, img_bv_idx)

    # ---- Build new buffer with all the numeric arrays (column-major IBM) ----
    ibm_colmajor = new_ibm_kept.transpose(0, 2, 1).astype(np.float32)
    buf_blob, offs = _pack_aligned(
        V.astype(np.float32),
        N.astype(np.float32),
        UV.astype(np.float32),
        new_J.astype(np.uint16),
        new_W.astype(np.float32),
        F.astype(np.uint32),
        ibm_colmajor,
    )
    OFF_V, OFF_N, OFF_UV, OFF_J, OFF_W, OFF_F, OFF_IB = offs

    BV = [
        pygltflib.BufferView(buffer=0, byteOffset=OFF_V[0],  byteLength=OFF_V[1],  target=pygltflib.ARRAY_BUFFER),
        pygltflib.BufferView(buffer=0, byteOffset=OFF_N[0],  byteLength=OFF_N[1],  target=pygltflib.ARRAY_BUFFER),
        pygltflib.BufferView(buffer=0, byteOffset=OFF_UV[0], byteLength=OFF_UV[1], target=pygltflib.ARRAY_BUFFER),
        pygltflib.BufferView(buffer=0, byteOffset=OFF_J[0],  byteLength=OFF_J[1],  target=pygltflib.ARRAY_BUFFER),
        pygltflib.BufferView(buffer=0, byteOffset=OFF_W[0],  byteLength=OFF_W[1],  target=pygltflib.ARRAY_BUFFER),
        pygltflib.BufferView(buffer=0, byteOffset=OFF_F[0],  byteLength=OFF_F[1],  target=pygltflib.ELEMENT_ARRAY_BUFFER),
        pygltflib.BufferView(buffer=0, byteOffset=OFF_IB[0], byteLength=OFF_IB[1]),
    ]
    if png_bytes:
        # pad image to 4-byte alignment and tack onto blob
        bin_pad = (4 - (len(buf_blob) % 4)) % 4
        buf_blob = buf_blob + b"\x00" * bin_pad
        BV.append(pygltflib.BufferView(buffer=0,
                                        byteOffset=len(buf_blob),
                                        byteLength=len(png_bytes)))
        img_bv_new_idx = len(BV) - 1
        # pad PNG
        img_pad = (4 - (len(png_bytes) % 4)) % 4
        full_blob = buf_blob + png_bytes + b"\x00" * img_pad
    else:
        img_bv_new_idx = None
        full_blob = buf_blob

    # Accessors
    acc_pos = pygltflib.Accessor(bufferView=0, componentType=pygltflib.FLOAT,
                                 count=len(V), type=pygltflib.VEC3,
                                 min=V.min(axis=0).tolist(), max=V.max(axis=0).tolist())
    acc_nrm = pygltflib.Accessor(bufferView=1, componentType=pygltflib.FLOAT,
                                 count=len(N), type=pygltflib.VEC3)
    acc_uv  = pygltflib.Accessor(bufferView=2, componentType=pygltflib.FLOAT,
                                 count=len(UV), type=pygltflib.VEC2)
    acc_jt  = pygltflib.Accessor(bufferView=3, componentType=pygltflib.UNSIGNED_SHORT,
                                 count=len(new_J), type=pygltflib.VEC4)
    acc_wt  = pygltflib.Accessor(bufferView=4, componentType=pygltflib.FLOAT,
                                 count=len(new_W), type=pygltflib.VEC4)
    acc_idx = pygltflib.Accessor(bufferView=5, componentType=pygltflib.UNSIGNED_INT,
                                 count=int(F.size), type=pygltflib.SCALAR)
    acc_ibm = pygltflib.Accessor(bufferView=6, componentType=pygltflib.FLOAT,
                                 count=len(kept_names), type=pygltflib.MAT4)

    # Nodes: one per kept joint (in kept order), with parent-relative
    # local T/R/S derived from the kept-only bind chain.
    nodes: list[pygltflib.Node] = []
    for ji, name in enumerate(kept_names):
        wb = world_bind_kept[ji]
        if kept_parents[ji] >= 0:
            parent_wb = world_bind_kept[kept_parents[ji]]
            local = np.linalg.inv(parent_wb) @ wb
        else:
            local = wb
        T = local[:3, 3].tolist()
        R = _mat_to_quat(local[:3, :3]).tolist()
        S = _mat_to_scale(local[:3, :3]).tolist()
        nodes.append(pygltflib.Node(name=name, translation=T, rotation=R, scale=S))
    for ji, pi in enumerate(kept_parents):
        if pi >= 0:
            kids = nodes[pi].children or []
            kids.append(ji)
            nodes[pi].children = kids

    mesh_node_idx = len(nodes)
    nodes.append(pygltflib.Node(name="OutfitMesh", mesh=0, skin=0))
    root_indices = [i for i, p in enumerate(kept_parents) if p < 0] + [mesh_node_idx]

    # Skin: joints = indices into nodes[], which IS the kept order
    new_skin = pygltflib.Skin(
        name="MetaHumanBodySkin",
        inverseBindMatrices=6,
        joints=list(range(len(kept_names))),
    )

    # Mesh + material: re-emit fresh ones referencing the new accessors
    new_prim = pygltflib.Primitive(
        attributes=pygltflib.Attributes(
            POSITION=0, NORMAL=1, TEXCOORD_0=2, JOINTS_0=3, WEIGHTS_0=4),
        indices=5,
        material=0,
    )
    new_mesh = pygltflib.Mesh(name=mesh.name or "Outfit", primitives=[new_prim])

    images, textures, samplers, materials = [], [], [], []
    if img_bv_new_idx is not None:
        images.append(pygltflib.Image(bufferView=img_bv_new_idx, mimeType="image/png"))
        samplers.append(pygltflib.Sampler(magFilter=9729, minFilter=9987,
                                          wrapS=10497, wrapT=10497))
        textures.append(pygltflib.Texture(source=0, sampler=0))
        # carry over PBR factors from incoming material when present
        if g.materials:
            src_mat = g.materials[0]
            pbr = src_mat.pbrMetallicRoughness or pygltflib.PbrMetallicRoughness()
            base = pbr.baseColorFactor or [1.0, 1.0, 1.0, 1.0]
            metallic = pbr.metallicFactor if pbr.metallicFactor is not None else 0.0
            rough = pbr.roughnessFactor if pbr.roughnessFactor is not None else 0.5
        else:
            base, metallic, rough = [1.0, 1.0, 1.0, 1.0], 0.0, 0.5
        materials.append(pygltflib.Material(
            name="fabric",
            pbrMetallicRoughness=pygltflib.PbrMetallicRoughness(
                baseColorTexture=pygltflib.TextureInfo(index=0),
                baseColorFactor=base,
                metallicFactor=metallic,
                roughnessFactor=rough,
            ),
            doubleSided=True,
        ))
    else:
        materials.append(pygltflib.Material(name="fabric", doubleSided=True))
        new_prim.material = 0

    out = pygltflib.GLTF2(
        asset=pygltflib.Asset(
            version="2.0",
            generator="refit_metahuman_glb",
            extras={
                "unitScale": "cm",
                "forwardAxis": "+Y",
                "skeleton": "MetaHuman UE5.6 Body",
                "ueImportSettings": {
                    "SceneScale": 1.0,
                    "ForwardAxis": "Y",
                    "note": "Body output is already in UE cm; the previously "
                            "documented SceneScale=0.1 should be disabled.",
                },
            },
        ),
        scenes=[pygltflib.Scene(nodes=root_indices)],
        scene=0,
        nodes=nodes,
        meshes=[new_mesh],
        materials=materials,
        textures=textures,
        samplers=samplers,
        images=images,
        skins=[new_skin],
        accessors=[acc_pos, acc_nrm, acc_uv, acc_jt, acc_wt, acc_idx, acc_ibm],
        bufferViews=BV,
        buffers=[pygltflib.Buffer(byteLength=len(full_blob))],
    )
    out.set_binary_blob(full_blob)
    out.save_binary(glb_path)

    if verbose:
        print(f"  {os.path.basename(glb_path):40s}  "
              f"V={len(V):5d}  bones {len(joint_names_full)}→{len(kept_names)}  "
              f"{os.path.getsize(glb_path)//1024:5d} KB")
    return {
        "file": os.path.basename(glb_path),
        "bone_count_before": len(joint_names_full),
        "bone_count_after":  len(kept_names),
        "vertex_count":      int(len(V)),
        "size_kb":           os.path.getsize(glb_path) // 1024,
    }


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def _seed_v2_slots(seed_basename: str) -> list[dict]:
    """Pull slot_assignments from assets/seeds_v2/<name>.json so the
    manifest carries human-meaningful slot info."""
    p = os.path.join(SEEDS_DIR, seed_basename + ".json")
    if not os.path.isfile(p):
        return []
    try:
        s = json.load(open(p))
    except Exception:
        return []
    of = s.get("outfit") or {}
    return [{"name": a.get("slot_name"), "library_id": a.get("library_id")}
            for a in of.get("slot_assignments", [])]


def _seed_v2_archetype(seed_basename: str) -> str:
    p = os.path.join(SEEDS_DIR, seed_basename + ".json")
    if not os.path.isfile(p):
        return ""
    try:
        s = json.load(open(p))
    except Exception:
        return ""
    return (s.get("outfit") or {}).get("archetype", "")


def _pretty_display_name(seed_basename: str) -> str:
    return seed_basename.replace("_", " ").title()


def build_manifest(refit_results: dict[str, dict],
                    out_path: str) -> None:
    entries = []
    for seed in sorted(refit_results.keys()):
        r = refit_results[seed]
        entries.append({
            "file":         r["file"],
            "displayName":  _pretty_display_name(seed),
            "slots":        _seed_v2_slots(seed),
            "skeleton":     "MetaHuman UE5.6 Body",
            "archetype":    _seed_v2_archetype(seed),
            "unitScale":    "cm",
            "forwardAxis":  "+Y",
            "boneCount":    r["bone_count_after"],
            "vertexCount":  r["vertex_count"],
            "sizeKb":       r["size_kb"],
        })
    manifest = {
        "version": 2,
        "skeleton": "MetaHuman UE5.6 Body",
        "unitScale": "cm",
        "forwardAxis": "+Y",
        "ueImportSettings": {
            "SceneScale": 1.0,
            "ForwardAxis": "Y",
            "note": "Output already in cm. Disable glTFRuntime SceneScale=0.1.",
        },
        "outfits": entries,
    }
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*",
                    help="seed basenames to refit (default: every .glb under assets/glb/)")
    ap.add_argument("--glb-dir", default=GLB_DIR)
    args = ap.parse_args()

    if args.names:
        paths = [os.path.join(args.glb_dir, n if n.endswith(".glb") else n + ".glb")
                 for n in args.names]
    else:
        paths = sorted(p for p in
                       (os.path.join(args.glb_dir, f)
                        for f in os.listdir(args.glb_dir) if f.endswith(".glb"))
                       if os.path.isfile(p))
    if not paths:
        sys.exit(f"no GLBs under {args.glb_dir}")

    t0 = time.time()
    results: dict[str, dict] = {}
    for p in paths:
        seed = os.path.splitext(os.path.basename(p))[0]
        try:
            results[seed] = refit(p)
        except Exception as exc:
            print(f"  FAIL {p}: {exc}")
    manifest_path = os.path.join(args.glb_dir, "manifest.json")
    build_manifest(results, manifest_path)
    dt = time.time() - t0
    print(f"\nrefit {len(results)} GLBs in {dt:.1f}s; manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
