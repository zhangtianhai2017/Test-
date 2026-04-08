"""OBJ + MTL file export for garment assemblies."""

import os
import numpy as np
from PIL import Image
from ..garment.assembly import GarmentAssembly
from ..texture.uv_mapping import pack_uv_islands


def export_obj(
    assembly: GarmentAssembly,
    output_dir: str,
    name: str = "bikini",
    texture_image: Image.Image | None = None,
    deformed_vertices: np.ndarray | None = None,
) -> dict[str, str]:
    """Export garment assembly to OBJ + MTL + texture PNG.

    Args:
        assembly: the garment assembly
        output_dir: directory to write files
        name: base filename (without extension)
        texture_image: optional texture to include
        deformed_vertices: optional post-physics vertex positions

    Returns:
        dict with file paths: {"obj": ..., "mtl": ..., "texture": ...}
    """
    os.makedirs(output_dir, exist_ok=True)

    obj_path = os.path.join(output_dir, f"{name}.obj")
    mtl_path = os.path.join(output_dir, f"{name}.mtl")
    tex_path = os.path.join(output_dir, f"{name}.png")

    # Pack UVs from all patches into single UV space
    patch_uvs = [p.uvs for p in assembly.patches]
    packed_uvs = pack_uv_islands(patch_uvs)

    # Save texture
    if texture_image is not None:
        texture_image.save(tex_path)

    # Write MTL
    _write_mtl(mtl_path, name, texture_image is not None)

    # Write OBJ
    _write_obj(obj_path, mtl_path, name, assembly, packed_uvs, deformed_vertices)

    result = {"obj": obj_path, "mtl": mtl_path}
    if texture_image is not None:
        result["texture"] = tex_path
    return result


def _write_mtl(mtl_path: str, name: str, has_texture: bool):
    """Write MTL material file."""
    with open(mtl_path, "w") as f:
        f.write(f"# Material for {name}\n")
        f.write(f"newmtl {name}_material\n")
        f.write("Ka 0.2 0.2 0.2\n")    # ambient
        f.write("Kd 0.8 0.8 0.8\n")    # diffuse
        f.write("Ks 0.3 0.3 0.3\n")    # specular
        f.write("Ns 50.0\n")            # specular exponent
        f.write("d 1.0\n")              # opacity
        f.write("illum 2\n")
        if has_texture:
            f.write(f"map_Kd {name}.png\n")

        # Metal material for decorations
        f.write(f"\nnewmtl metal_material\n")
        f.write("Ka 0.3 0.3 0.3\n")
        f.write("Kd 0.7 0.6 0.3\n")
        f.write("Ks 0.9 0.9 0.9\n")
        f.write("Ns 200.0\n")
        f.write("d 1.0\n")
        f.write("illum 2\n")


def _write_obj(
    obj_path: str,
    mtl_path: str,
    name: str,
    assembly: GarmentAssembly,
    packed_uvs: list[np.ndarray],
    deformed_vertices: np.ndarray | None = None,
):
    """Write OBJ geometry file."""
    mtl_filename = os.path.basename(mtl_path)

    with open(obj_path, "w") as f:
        f.write(f"# 3D Bikini Generator - {name}\n")
        f.write(f"# Patches: {len(assembly.patches)}\n")
        f.write(f"# Total vertices: {assembly.total_vertices()}\n")
        f.write(f"# Total faces: {assembly.total_faces()}\n\n")
        f.write(f"mtllib {mtl_filename}\n\n")

        vertex_offset = 0
        uv_offset = 0

        for patch_idx, patch in enumerate(assembly.patches):
            f.write(f"# Patch: {patch.name}\n")
            f.write(f"o {patch.name}\n")

            # Choose material
            if patch.material_name == "metal":
                f.write("usemtl metal_material\n")
            else:
                f.write(f"usemtl {name}_material\n")

            # Vertices
            if deformed_vertices is not None:
                # Use deformed positions
                start = vertex_offset
                end = start + patch.vertex_count()
                verts = deformed_vertices[start:end]
            else:
                verts = patch.vertices

            for v in verts:
                f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")

            # Normals
            if patch.normals is None:
                patch.compute_normals()
            for n in patch.normals:
                f.write(f"vn {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n")

            # UVs (packed)
            if patch_idx < len(packed_uvs):
                uvs = packed_uvs[patch_idx]
            else:
                uvs = patch.uvs
            for uv in uvs:
                f.write(f"vt {uv[0]:.6f} {uv[1]:.6f}\n")

            # Faces (OBJ is 1-indexed)
            for face in patch.faces:
                # f v/vt/vn for each vertex
                parts = []
                for vi in face:
                    v_idx = vi + vertex_offset + 1
                    vt_idx = vi + uv_offset + 1
                    vn_idx = vi + vertex_offset + 1
                    parts.append(f"{v_idx}/{vt_idx}/{vn_idx}")
                f.write(f"f {' '.join(parts)}\n")

            f.write("\n")
            vertex_offset += patch.vertex_count()
            uv_offset += len(uvs)


def export_body_obj(
    vertices: np.ndarray,
    faces: np.ndarray,
    output_dir: str,
    name: str = "mannequin",
) -> str:
    """Export the body mesh as a separate OBJ for reference."""
    os.makedirs(output_dir, exist_ok=True)
    obj_path = os.path.join(output_dir, f"{name}.obj")

    with open(obj_path, "w") as f:
        f.write(f"# Mannequin body - {name}\n")
        f.write(f"o {name}\n\n")

        for v in vertices:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")

        for face in faces:
            f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")

    return obj_path
