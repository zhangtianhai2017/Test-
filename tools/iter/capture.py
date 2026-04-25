"""
Stage 1 — render N standard views of a Genome+Params combo.

Same lighting, distance and background every round so the loop never
confuses "we changed angle" with "we improved". The 8 views target
specific failure modes (cup shape, edge cleanliness, strap placement).
"""
from __future__ import annotations

import os, sys, math
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")

import numpy as np
from dataclasses import dataclass
from PIL import Image
import open3d as o3d

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from verify_ga_uv import Genome, genome_polygons, _DISCRETE_ENUMS, CONT_FIELDS
from render3d_uv import (
    cylindrical_uvs, torso_anchors, genome_to_texture,
    load_body_mesh, build_fabric_shell, build_binding_mesh,
    build_strap_meshes, _apply_weave_shade_to_texture, _get_fabric_normal,
    apply_wrinkles, _skin_only_texture,
)
from garment_polish import polish_shell


@dataclass
class CamSpec:
    name: str
    azimuth_deg: float    # 0 = front, 90 = side_left, 180 = back
    elevation_deg: float  # 0 = horizontal, +up
    target_height_frac: float  # 0..1, fraction up the body
    zoom: float          # smaller = tighter
    fov_deg: float = 35.0


# 8 fixed views. Numbers are tuned for our NPC mesh (~150 cm tall).
VIEWS = [
    CamSpec("01_front",          azimuth_deg=0,    elevation_deg=0,   target_height_frac=0.55, zoom=1.00),
    CamSpec("02_three_quarter",  azimuth_deg=45,   elevation_deg=0,   target_height_frac=0.55, zoom=1.00),
    CamSpec("03_side_left",      azimuth_deg=90,   elevation_deg=0,   target_height_frac=0.55, zoom=1.00),
    CamSpec("04_back",           azimuth_deg=180,  elevation_deg=0,   target_height_frac=0.55, zoom=1.00),
    CamSpec("05_chest_close",    azimuth_deg=0,    elevation_deg=0,   target_height_frac=0.78, zoom=0.32),
    CamSpec("06_hip_close",      azimuth_deg=0,    elevation_deg=0,   target_height_frac=0.32, zoom=0.32),
    CamSpec("07_neck_top",       azimuth_deg=0,    elevation_deg=55,  target_height_frac=0.85, zoom=0.40),
    CamSpec("08_shoulder_top",   azimuth_deg=25,   elevation_deg=40,  target_height_frac=0.82, zoom=0.45),
]


def _setup_renderer(W: int, H: int):
    R = o3d.visualization.rendering.OffscreenRenderer(W, H)
    R.scene.set_background([0.92, 0.92, 0.94, 1.0])
    R.scene.scene.set_sun_light(
        direction=[-0.4, -0.6, -0.7], color=[1.0, 1.0, 1.0], intensity=80_000)
    R.scene.scene.enable_sun_light(True)
    R.scene.scene.enable_indirect_light(True)
    R.scene.scene.set_indirect_light_intensity(28_000)
    return R


def _frame(renderer, mesh: o3d.geometry.TriangleMesh, view: CamSpec):
    V = np.asarray(mesh.vertices)
    y_lo, y_hi = float(np.percentile(V[:, 1], 2)), float(np.percentile(V[:, 1], 98))
    body_h = y_hi - y_lo
    target_y = y_lo + view.target_height_frac * body_h
    center = np.array([0.0, target_y, 0.0], dtype=np.float32)

    radius = body_h * 0.55 * view.zoom / math.tan(math.radians(view.fov_deg / 2.0))
    az = math.radians(view.azimuth_deg)
    el = math.radians(view.elevation_deg)
    eye = center + np.array([
        math.sin(az) * math.cos(el) * radius,
        math.sin(el) * radius,
        math.cos(az) * math.cos(el) * radius,
    ], dtype=np.float32)
    up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    renderer.setup_camera(view.fov_deg, center.tolist(), eye.tolist(), up.tolist())


def apply_genome_patch(g: Genome, patch: dict) -> Genome:
    """Return a new Genome with continuous fields nudged by `patch` and
    discrete fields replaced (if a valid enum value is given).
    """
    if not patch:
        return g
    from dataclasses import asdict
    d = asdict(g)
    for k, v in patch.items():
        if k in CONT_FIELDS:
            d[k] = float(d[k]) + float(v)
        elif k in _DISCRETE_ENUMS:
            if v in _DISCRETE_ENUMS[k]:
                d[k] = v
        # ignore unknown keys
    return Genome(**d).clipped()


def render_views(genome: Genome, params, out_dir: str,
                  W: int = 480, H: int = 720,
                  body_mesh: o3d.geometry.TriangleMesh | None = None,
                  ) -> list[str]:
    """Render all 8 standard views into out_dir/<name>.png. Returns paths."""
    os.makedirs(out_dir, exist_ok=True)

    # Apply Genome patch
    g = apply_genome_patch(genome, params.genome_patch)

    if body_mesh is None:
        body_mesh = load_body_mesh()
    body_uvs = cylindrical_uvs(body_mesh)
    body_mesh.triangle_uvs = o3d.utility.Vector2dVector(body_uvs)
    yc, yn = torso_anchors(body_mesh)

    polys_uv = genome_polygons(g)
    shell = build_fabric_shell(body_mesh, body_uvs, polys_uv,
                                offset=params.shell_offset_cm)
    if len(shell.vertices) > 0:
        shell = polish_shell(
            shell, body_mesh, polys_uv, yc, yn,
            smooth_iters=params.smooth_iters,
            boundary_snap=params.boundary_snap,
            min_offset=params.min_offset_cm,
            cup_extra_offset=params.cup_extra_cm,
        )
        wr_amp = (0.04 + 0.10 * (1.0 - g.fabric_weight)) * params.wrinkle_amp_scale
        if wr_amp > 0.001:
            apply_wrinkles(shell, amplitude=wr_amp)

    binding = (build_binding_mesh(shell, offset=params.binding_offset_cm,
                                    thickness=params.binding_thickness_cm)
                if len(shell.vertices) > 0 else o3d.geometry.TriangleMesh())

    # Strap radius scale: temporarily monkey-patch by scaling strap meshes.
    straps = build_strap_meshes(body_mesh, g, yc, yn)
    if params.strap_radius_scale != 1.0 and straps:
        scaled = []
        for name, m in straps:
            verts = np.asarray(m.vertices, dtype=np.float64)
            # Each strap is a tube around a centerline. Scaling
            # per-vertex around its center isn't straightforward; instead
            # we approximate by scaling distance to the strap's mean axis
            # in the XZ plane, which is the dominant cross-section.
            if len(verts) >= 6:
                ctr = verts.mean(axis=0)
                offset = verts - ctr
                # only scale XZ (radial); leave Y (along-strap) alone
                offset[:, [0, 2]] *= params.strap_radius_scale
                m.vertices = o3d.utility.Vector3dVector(ctr + offset)
                m.compute_vertex_normals()
            scaled.append((name, m))
        straps = scaled

    R = _setup_renderer(W, H)

    body_tex = np.array(_skin_only_texture().convert("RGB"))
    body_mat = o3d.visualization.rendering.MaterialRecord()
    body_mat.shader = "defaultLit"
    body_mat.albedo_img = o3d.geometry.Image(body_tex)
    body_mat.base_roughness = 0.65

    if len(shell.vertices) > 0:
        # Apply weave shading at `weave_intensity`. 0.0 = unshaded albedo
        # (pure pattern), 1.0 = original effect, >1 = exaggerated.
        base_tex = genome_to_texture(g)
        if params.weave_intensity > 0.001:
            shaded = _apply_weave_shade_to_texture(base_tex)
            base_arr = np.array(base_tex.convert("RGB"), dtype=np.float32)
            shaded_arr = np.array(shaded.convert("RGB"), dtype=np.float32)
            mix = base_arr + (shaded_arr - base_arr) * float(params.weave_intensity)
            tex_np = np.clip(mix, 0, 255).astype(np.uint8)
        else:
            tex_np = np.array(base_tex.convert("RGB"))
        shell_mat = o3d.visualization.rendering.MaterialRecord()
        shell_mat.shader = "defaultLit"
        shell_mat.albedo_img = o3d.geometry.Image(tex_np)
        shell_mat.base_roughness = float(np.clip(0.95 - 0.65 * g.fabric_sheen, 0.05, 1.0))
        shell_mat.base_metallic = float(g.fabric_metallic)
        if params.weave_intensity > 0.05:
            try:
                nm = _get_fabric_normal(g.fabric_weave)
                # Soften normal map by blending toward flat (128, 128, 255)
                if params.weave_intensity < 1.0:
                    flat = np.full_like(nm, [128, 128, 255], dtype=np.uint8)
                    nm = (nm * params.weave_intensity + flat * (1.0 - params.weave_intensity)).astype(np.uint8)
                shell_mat.normal_img = o3d.geometry.Image(nm)
            except Exception:
                pass

    bind_mat = o3d.visualization.rendering.MaterialRecord()
    bind_mat.shader = "defaultLit"
    bind_mat.base_roughness = 0.6

    out_paths = []
    for view in VIEWS:
        R.scene.clear_geometry()
        R.scene.add_geometry("body", body_mesh, body_mat)
        if len(shell.vertices) > 0:
            R.scene.add_geometry("shell", shell, shell_mat)
        if len(binding.vertices) > 0:
            R.scene.add_geometry("binding", binding, bind_mat)
        for name, m in straps:
            if len(m.vertices) > 0:
                R.scene.add_geometry(f"strap_{name}", m, bind_mat)
        _frame(R, body_mesh, view)
        img = R.render_to_image()
        path = os.path.join(out_dir, f"{view.name}.png")
        o3d.io.write_image(path, img, 9)
        out_paths.append(path)
    return out_paths


def make_contact_sheet(view_paths: list[str], out_path: str,
                        thumb_w: int = 360, cols: int = 4) -> str:
    """Stack all views into one PNG so the critic can read 1 image not 8."""
    imgs = [Image.open(p).convert("RGB") for p in view_paths]
    if not imgs:
        return ""
    aspect = imgs[0].size[1] / imgs[0].size[0]
    thumb_h = int(thumb_w * aspect)
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + 24)), (24, 24, 24))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(sheet)
    for i, (im, p) in enumerate(zip(imgs, view_paths)):
        r, c = divmod(i, cols)
        x0, y0 = c * thumb_w, r * (thumb_h + 24)
        draw.text((x0 + 6, y0 + 4), os.path.basename(p).replace(".png", ""),
                  fill=(255, 220, 100))
        sheet.paste(im.resize((thumb_w, thumb_h)), (x0, y0 + 22))
    sheet.save(out_path)
    return out_path
