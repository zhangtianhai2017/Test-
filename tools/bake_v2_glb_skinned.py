"""Bake every v2 seed (assets/seeds_v2/*.json) to a skinned .glb that
references the MetaHuman skeleton, plus a manifest.json index.

Pipeline per seed:
  1. Load v2 seed JSON, take its `genome` field.
  2. Reuse export_garment.export_genome_to_glb's mesh-build path (no
     write) → (V, F, UV, N, material, albedo).
  3. transfer_weights(V → body_verts) gives per-vertex (joints[4],
     weights[4]) referencing the MetaHuman skeleton.
  4. Write a skinned glTF via pygltflib that:
       - declares all MetaHuman bones as glTF nodes (one node per joint)
       - declares one Skin with inverseBindMatrices from the body
       - mesh primitive carries POSITION, NORMAL, TEXCOORD_0,
         JOINTS_0, WEIGHTS_0
       - embeds the albedo PNG inline (data URI) so the .glb is
         standalone

Usage:
  # one-time: pickle body skinning data
  python3 tools/bake_body_assets.py /path/to/MetaHuman_Body.glb

  # then bake all seeds:
  python3 tools/bake_v2_glb_skinned.py
  # or one seed:
  python3 tools/bake_v2_glb_skinned.py composite_red
"""
from __future__ import annotations

import argparse
import base64
import glob
import io
import json
import os
import pickle
import struct
import sys
import time

import numpy as np
import open3d as o3d
import trimesh
from PIL import Image
import pygltflib

sys.path.insert(0, os.path.dirname(__file__))
from auto_skin import transfer_weights
from render3d_uv import (
    cylindrical_uvs, torso_anchors, genome_to_texture,
    load_body_mesh, build_fabric_shell, build_binding_mesh,
    build_strap_meshes,
)
from garment_polish import polish_shell
from verify_ga_uv import genome_polygons
from seed_loader import seed_to_genome
from export_garment import (
    _trim_color, _build_albedo, _o3d_to_arrays,
    _shell_uvs_to_atlas, _per_corner_to_per_vertex,
    TEX_W, TEX_H,
)


def _build_outfit_mesh(g, body_mesh) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, Image.Image]:
    """Replays export_genome_to_glb's mesh build, returns (V, F, UV, N, albedo)."""
    body_uvs = cylindrical_uvs(body_mesh)
    body_mesh.triangle_uvs = o3d.utility.Vector2dVector(body_uvs)

    polys_uv = genome_polygons(g)
    yc, yn = torso_anchors(body_mesh)
    shell = build_fabric_shell(body_mesh, body_uvs, polys_uv, offset=0.3)
    if len(np.asarray(shell.triangles)) > 0:
        shell = polish_shell(shell, body_mesh, polys_uv, yc, yn)
    shell_corner_uvs = np.asarray(shell.triangle_uvs)

    bind = build_binding_mesh(shell, offset=0.05, thickness=0.40)
    straps = build_strap_meshes(body_mesh, g, yc, yn)

    sV, sF = _o3d_to_arrays(shell)
    if len(sF) == 0:
        raise RuntimeError("Empty fabric shell.")
    atlas_uvs = _shell_uvs_to_atlas(shell_corner_uvs)
    sV, sF, sUV = _per_corner_to_per_vertex(sV, sF, atlas_uvs)

    extra = [("binding", bind)] + straps
    accumV, accumF, accumUV = [sV], [sF], [sUV]
    voff = sV.shape[0]
    for _name, m in extra:
        V, F = _o3d_to_arrays(m)
        if len(V) == 0:
            continue
        UV = np.full((len(V), 2),
                     [0.5, 1.0 - 16 * 0.5 / TEX_H], dtype=np.float32)
        accumV.append(V); accumF.append(F + voff); accumUV.append(UV)
        voff += len(V)

    V  = np.concatenate(accumV, axis=0).astype(np.float32)
    F  = np.concatenate(accumF, axis=0).astype(np.uint32)
    UV = np.concatenate(accumUV, axis=0).astype(np.float32)

    tri = trimesh.Trimesh(vertices=V, faces=F, process=False)
    tri.fix_normals()
    N = np.asarray(tri.vertex_normals, dtype=np.float32)

    albedo = _build_albedo(g)
    return V, F, UV, N, albedo


def _bone_node_tree(joint_names: list[str], parents: list[int],
                    bind_matrices: np.ndarray) -> list[pygltflib.Node]:
    """Build glTF Node array for each bone. Each node carries its
    bind-pose local transform decomposed into T/R/S."""
    nodes = []
    for ji, name in enumerate(joint_names):
        local = bind_matrices[ji]
        if parents[ji] >= 0:
            parent_inv = np.linalg.inv(bind_matrices[parents[ji]])
            local = parent_inv @ bind_matrices[ji]
        T = local[:3, 3].tolist()
        R = _mat_to_quat(local[:3, :3]).tolist()
        S = _mat_to_scale(local[:3, :3]).tolist()
        nodes.append(pygltflib.Node(name=name, translation=T, rotation=R, scale=S))
    # children
    for ji, p in enumerate(parents):
        if p >= 0:
            kids = nodes[p].children or []
            kids.append(ji)
            nodes[p].children = kids
    return nodes


def _mat_to_quat(M: np.ndarray) -> np.ndarray:
    # decompose rotation; assume no shear
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
        x = 0.25 * S
        y = (R[0, 1] + R[1, 0]) / S
        z = (R[0, 2] + R[2, 0]) / S
    elif R[1, 1] > R[2, 2]:
        S = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w = (R[0, 2] - R[2, 0]) / S
        x = (R[0, 1] + R[1, 0]) / S
        y = 0.25 * S
        z = (R[1, 2] + R[2, 1]) / S
    else:
        S = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w = (R[1, 0] - R[0, 1]) / S
        x = (R[0, 2] + R[2, 0]) / S
        y = (R[1, 2] + R[2, 1]) / S
        z = 0.25 * S
    return np.array([x, y, z, w], dtype=np.float32)


def _mat_to_scale(M: np.ndarray) -> np.ndarray:
    return np.linalg.norm(M, axis=0).astype(np.float32)


def _infer_parents(joint_names: list[str], bind_matrices: np.ndarray) -> list[int]:
    """Best-effort: parent = the joint whose bind translation is the
    nearest predecessor in the spatial tree. For MetaHuman / UE5
    mannequin bone names follow a known parenting; if names don't match
    UE conventions, we fall back to all-roots (parents = -1) which is
    still valid skinning but a flat skeleton."""
    UE5_PARENT = {
        "pelvis": "root",
        "spine_01": "pelvis", "spine_02": "spine_01",
        "spine_03": "spine_02", "spine_04": "spine_03",
        "spine_05": "spine_04",
        "neck_01": "spine_05", "head": "neck_01",
        "clavicle_l": "spine_05", "upperarm_l": "clavicle_l",
        "lowerarm_l": "upperarm_l", "hand_l": "lowerarm_l",
        "clavicle_r": "spine_05", "upperarm_r": "clavicle_r",
        "lowerarm_r": "upperarm_r", "hand_r": "lowerarm_r",
        "thigh_l": "pelvis", "calf_l": "thigh_l", "foot_l": "calf_l",
        "thigh_r": "pelvis", "calf_r": "thigh_r", "foot_r": "calf_r",
    }
    name_to_idx = {n: i for i, n in enumerate(joint_names)}
    parents = [-1] * len(joint_names)
    for n, p in UE5_PARENT.items():
        if n in name_to_idx and p in name_to_idx:
            parents[name_to_idx[n]] = name_to_idx[p]
    return parents


def _pack_bin(*arrays: np.ndarray) -> tuple[bytes, list[tuple[int, int]]]:
    """Concatenate arrays into one buffer with 4-byte alignment.
    Returns (blob, [(byte_offset, byte_length) per array])."""
    parts = []
    offsets = []
    cursor = 0
    for a in arrays:
        b = a.tobytes()
        pad = (4 - (cursor % 4)) % 4
        if pad:
            parts.append(b"\x00" * pad)
            cursor += pad
        offsets.append((cursor, len(b)))
        parts.append(b)
        cursor += len(b)
    # final pad to 4
    pad = (4 - (cursor % 4)) % 4
    if pad:
        parts.append(b"\x00" * pad)
    return b"".join(parts), offsets


def write_skinned_glb(out_path: str,
                      V: np.ndarray, F: np.ndarray, UV: np.ndarray, N: np.ndarray,
                      joints: np.ndarray, weights: np.ndarray,
                      albedo: Image.Image,
                      body_skin: dict,
                      g) -> int:
    """Assemble + save a single .glb with one skinned mesh."""
    joint_names   = body_skin["joint_names"]
    inv_binds     = body_skin["inverse_binds"].astype(np.float32)
    bind_matrices = body_skin["bind_matrices"].astype(np.float32)
    parents       = _infer_parents(joint_names, bind_matrices)

    # ---- buffer (all numeric data) ----
    buf_blob, offs = _pack_bin(
        V.astype(np.float32),
        N.astype(np.float32),
        UV.astype(np.float32),
        joints.astype(np.uint16),
        weights.astype(np.float32),
        F.astype(np.uint32),
        inv_binds.astype(np.float32),
    )
    OFF_V, OFF_N, OFF_UV, OFF_J, OFF_W, OFF_F, OFF_IB = offs

    # ---- albedo PNG inline ----
    png_io = io.BytesIO(); albedo.save(png_io, format="PNG"); png_bytes = png_io.getvalue()
    # pad image to 4
    img_pad = (4 - (len(png_bytes) % 4)) % 4
    img_blob = png_bytes + b"\x00" * img_pad

    # ---- bufferViews ----
    BV = []
    for off, length in [OFF_V, OFF_N, OFF_UV, OFF_J, OFF_W]:
        BV.append(pygltflib.BufferView(buffer=0, byteOffset=off, byteLength=length, target=pygltflib.ARRAY_BUFFER))
    BV.append(pygltflib.BufferView(buffer=0, byteOffset=OFF_F[0], byteLength=OFF_F[1], target=pygltflib.ELEMENT_ARRAY_BUFFER))
    BV.append(pygltflib.BufferView(buffer=0, byteOffset=OFF_IB[0], byteLength=OFF_IB[1]))   # inverse-bind, no target
    BV.append(pygltflib.BufferView(buffer=0, byteOffset=len(buf_blob), byteLength=len(png_bytes)))  # image

    # ---- accessors ----
    acc_pos  = pygltflib.Accessor(bufferView=0, componentType=pygltflib.FLOAT, count=len(V),  type=pygltflib.VEC3,
                                  min=V.min(axis=0).tolist(), max=V.max(axis=0).tolist())
    acc_nrm  = pygltflib.Accessor(bufferView=1, componentType=pygltflib.FLOAT, count=len(N),  type=pygltflib.VEC3)
    acc_uv   = pygltflib.Accessor(bufferView=2, componentType=pygltflib.FLOAT, count=len(UV), type=pygltflib.VEC2)
    acc_jt   = pygltflib.Accessor(bufferView=3, componentType=pygltflib.UNSIGNED_SHORT, count=len(joints),  type=pygltflib.VEC4)
    acc_wt   = pygltflib.Accessor(bufferView=4, componentType=pygltflib.FLOAT, count=len(weights), type=pygltflib.VEC4)
    acc_idx  = pygltflib.Accessor(bufferView=5, componentType=pygltflib.UNSIGNED_INT, count=int(F.size), type=pygltflib.SCALAR)
    acc_ib   = pygltflib.Accessor(bufferView=6, componentType=pygltflib.FLOAT, count=len(inv_binds), type=pygltflib.MAT4)

    # ---- texture / material ----
    image    = pygltflib.Image(bufferView=7, mimeType="image/png")
    sampler  = pygltflib.Sampler(magFilter=9729, minFilter=9987, wrapS=10497, wrapT=10497)
    texture  = pygltflib.Texture(source=0, sampler=0)
    material = pygltflib.Material(
        name="fabric",
        pbrMetallicRoughness=pygltflib.PbrMetallicRoughness(
            baseColorTexture=pygltflib.TextureInfo(index=0),
            baseColorFactor=[1.0, 1.0, 1.0, float(g.fabric_opacity)],
            metallicFactor=float(g.fabric_metallic),
            roughnessFactor=float(np.clip(1.0 - g.fabric_sheen, 0.05, 1.0)),
        ),
        doubleSided=True,
    )

    # ---- skin ----
    skin = pygltflib.Skin(
        name="MetaHumanBodySkin",
        inverseBindMatrices=6,
        joints=list(range(len(joint_names))),     # joint nodes start at index 0
    )

    # ---- nodes: bones first, then mesh node ----
    bone_nodes = _bone_node_tree(joint_names, parents, bind_matrices)
    mesh_node_idx = len(bone_nodes)
    mesh_node = pygltflib.Node(name="OutfitMesh", mesh=0, skin=0)

    nodes = bone_nodes + [mesh_node]
    root_indices = [i for i, p in enumerate(parents) if p < 0] + [mesh_node_idx]

    # ---- mesh primitive ----
    prim = pygltflib.Primitive(
        attributes=pygltflib.Attributes(
            POSITION=0, NORMAL=1, TEXCOORD_0=2, JOINTS_0=3, WEIGHTS_0=4,
        ),
        indices=5,
        material=0,
    )
    mesh = pygltflib.Mesh(name="Outfit", primitives=[prim])

    # ---- assemble ----
    g_obj = pygltflib.GLTF2(
        asset=pygltflib.Asset(version="2.0", generator="bake_v2_glb_skinned"),
        scenes=[pygltflib.Scene(nodes=root_indices)],
        scene=0,
        nodes=nodes,
        meshes=[mesh],
        materials=[material],
        textures=[texture],
        samplers=[sampler],
        images=[image],
        skins=[skin],
        accessors=[acc_pos, acc_nrm, acc_uv, acc_jt, acc_wt, acc_idx, acc_ib],
        bufferViews=BV,
        buffers=[pygltflib.Buffer(byteLength=len(buf_blob) + len(img_blob))],
    )
    g_obj.set_binary_blob(buf_blob + img_blob)
    g_obj.save_binary(out_path)
    return os.path.getsize(out_path)


def bake_one(seed_path: str, body_mesh, body_skin: dict, out_dir: str, verbose: bool = True) -> dict:
    name = os.path.splitext(os.path.basename(seed_path))[0]
    with open(seed_path) as f:
        seed = json.load(f)
    g = seed_to_genome(seed)

    V, F, UV, N, albedo = _build_outfit_mesh(g, body_mesh)
    joints, weights = transfer_weights(
        V, body_skin["body_verts"],
        body_skin["body_joints"], body_skin["body_weights"],
    )
    out_path = os.path.join(out_dir, name + ".glb")
    size = write_skinned_glb(out_path, V, F, UV, N, joints, weights, albedo, body_skin, g)
    entry = {
        "seed": name, "file": name + ".glb",
        "archetype": seed.get("outfit", {}).get("archetype", ""),
        "slots": [{"name": s["slot_name"], "library_id": s["library_id"]}
                  for s in seed.get("outfit", {}).get("slot_assignments", [])],
        "kb": size // 1024,
        "vertex_count": int(V.shape[0]),
    }
    if verbose:
        print(f"  {name:30s}  V={V.shape[0]:5d}  F={F.shape[0]:5d}  {size//1024:4d}KB")
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seeds", nargs="*",
                    help="seed names to bake (default: all under assets/seeds_v2/)")
    ap.add_argument("--seeds-dir", default="assets/seeds_v2")
    ap.add_argument("--out-dir",   default="assets/glb")
    ap.add_argument("--body-skin", default="assets/glb/_body_skin.pkl")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    if not os.path.exists(args.body_skin):
        sys.exit(f"missing body skin pickle {args.body_skin} — run "
                 f"`python3 tools/bake_body_assets.py <body.glb>` first.")
    with open(args.body_skin, "rb") as f:
        body_skin = pickle.load(f)

    print(f"loaded body skin: {body_skin['body_verts'].shape[0]} verts, "
          f"{len(body_skin['joint_names'])} joints")
    body_mesh = load_body_mesh()

    if args.seeds:
        paths = [os.path.join(args.seeds_dir, s + ".json") for s in args.seeds]
    else:
        paths = sorted(glob.glob(os.path.join(args.seeds_dir, "*.json")))

    t0 = time.time()
    entries = []
    for p in paths:
        try:
            entries.append(bake_one(p, body_mesh, body_skin, args.out_dir))
        except Exception as exc:
            print(f"  SKIP {p}: {exc}")

    manifest = {
        "version": 1,
        "branch": os.environ.get("GIT_BRANCH", "claude/bikini-variation-algorithm-Dv5q5"),
        "skeleton": "/Game/MetaHuman/Mannequin/SK_Body",
        "outfits": entries,
    }
    with open(os.path.join(args.out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"baked {len(entries)} outfits in {time.time()-t0:.1f}s -> {args.out_dir}/")


if __name__ == "__main__":
    main()
