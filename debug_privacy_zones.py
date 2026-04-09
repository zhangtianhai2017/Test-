"""Generate debug image marking privacy zones using proper 3D rendering.

Uses pyrender (OpenGL) with OSMesa for offscreen rendering.
Uses Taichi PBD cloth simulation to settle fabric onto body surface.

Bikini bottom = front panel + crotch strip (sagittal plane) + back panel.
Breast zones = two elliptical patches.
"""
import os
os.environ['PYOPENGL_PLATFORM'] = 'osmesa'

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import trimesh
import pyrender
from PIL import Image
from matplotlib.path import Path as MplPath

from bikini_generator.body.mannequin import generate_full_body
from bikini_generator.body.landmarks import get_landmarks
from bikini_generator.garment.loop_generator import BodySurface


# ---------------------------------------------------------------------------
# Mesh thickness: extrude thin surface into solid shell
# ---------------------------------------------------------------------------

def thicken_mesh(mesh, thickness=0.002):
    """Extrude a surface mesh into a solid shell with given thickness.

    Extrudes INWARD (toward body), so the original surface stays as the
    visible outer face. This keeps fabric flush against the body surface
    at the collision margin position.
    """
    from collections import Counter

    verts = mesh.vertices.copy()
    faces = mesh.faces.copy()
    n = len(verts)

    # Compute vertex normals from face normals
    normals = np.zeros_like(verts)
    for f in faces:
        v0, v1, v2 = verts[f[0]], verts[f[1]], verts[f[2]]
        fn = np.cross(v1 - v0, v2 - v0)
        normals[f[0]] += fn
        normals[f[1]] += fn
        normals[f[2]] += fn
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals /= np.maximum(lengths, 1e-8)

    # Ensure normals point outward (away from body center axis)
    radial = verts.copy()
    radial[:, 1] = 0
    dots = np.sum(normals * radial, axis=1)
    normals[dots < 0] *= -1

    # Outer surface = original vertices (stays at collision margin)
    # Inner surface = original - normal * thickness (goes toward body)
    inner_verts = verts - normals * thickness
    all_verts = np.vstack([verts, inner_verts])

    # Outer faces (original winding) + inner faces (reversed, offset by n)
    inner_faces = faces[:, ::-1] + n
    all_faces_list = [faces, inner_faces]

    # Side faces: connect boundary edges
    edge_count = Counter()
    for f in faces:
        for i in range(3):
            e = tuple(sorted([f[i], f[(i + 1) % 3]]))
            edge_count[e] += 1

    side_faces = []
    for (a, b), c in edge_count.items():
        if c == 1:
            side_faces.append([a, b, a + n])
            side_faces.append([b, b + n, a + n])

    if side_faces:
        all_faces_list.append(np.array(side_faces, dtype=np.int32))

    all_faces = np.vstack(all_faces_list)
    thick = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=False)

    # Copy vertex colors to both inner and outer surfaces
    if hasattr(mesh.visual, 'vertex_colors') and mesh.visual.vertex_colors is not None:
        colors = mesh.visual.vertex_colors[:n]
        thick.visual.vertex_colors = np.tile(
            colors[0], (len(all_verts), 1))  # uniform color
    return thick


# ---------------------------------------------------------------------------
# Body mesh LUT builder (uses actual mesh, not BodySurface ellipsoidal model)
# ---------------------------------------------------------------------------

def build_mesh_body_lut(body_verts, n_y=256, n_theta=256,
                        y_min=0.75, y_max=1.50):
    """Build body surface radius LUT from actual mesh vertices.

    For each (Y, theta) cell, records the maximum radial distance of any
    mesh vertex in that region.  This captures actual breast protrusion,
    pelvic curvature, etc. that the ellipsoidal BodySurface model misses.

    Cells with no nearby vertices fall back to the BodySurface model.
    Result is smoothed to fill sparse cells.
    """
    lut = np.zeros((n_y, n_theta), dtype=np.float32)
    count = np.zeros((n_y, n_theta), dtype=np.int32)

    dy = (y_max - y_min) / (n_y - 1)
    dtheta = 2 * np.pi / n_theta

    for v in body_verts:
        x, y, z = v
        if y < y_min - dy or y > y_max + dy:
            continue
        r = np.sqrt(x * x + z * z)
        theta = np.arctan2(-x, z)
        if theta < 0:
            theta += 2 * np.pi

        iy = int(round((y - y_min) / dy))
        it = int(theta / dtheta) % n_theta
        iy = max(0, min(iy, n_y - 1))

        # Keep maximum radius in each cell
        if r > lut[iy, it]:
            lut[iy, it] = r
        count[iy, it] += 1

    # Fill empty cells with BodySurface fallback, then smooth
    body = BodySurface()
    y_values = np.linspace(y_min, y_max, n_y)
    theta_values = np.linspace(0, 2 * np.pi, n_theta, endpoint=False)

    for iy in range(n_y):
        for it in range(n_theta):
            if count[iy, it] == 0:
                lut[iy, it] = body.get_surface_radius(
                    y_values[iy], theta_values[it])

    # Light Gaussian blur to smooth out noise from sparse vertex sampling
    from scipy.ndimage import gaussian_filter
    # Wrap theta axis (periodic boundary)
    padded = np.concatenate([lut[:, -3:], lut, lut[:, :3]], axis=1)
    padded = gaussian_filter(padded, sigma=[1.0, 1.5])
    lut_smooth = padded[:, 3:-3]

    # Take max of original and smoothed to avoid shrinking breast peaks
    lut = np.maximum(lut, lut_smooth)

    return lut


# ---------------------------------------------------------------------------
# Cloth physics settling
# ---------------------------------------------------------------------------

def settle_fabric_on_body(fabric_meshes, body_verts, num_steps=300):
    """Run PBD cloth simulation to settle fabric meshes onto body surface.

    Uses ClothSimulator with:
    - Zero gravity (pure settling, not dynamics)
    - Mesh-based body LUT (accurate breast/pelvis collision)
    - Elastic tension (rest lengths at 88% → fabric contracts onto body)
    - Collision + friction (prevents penetration, holds position)

    Returns updated vertex positions for each mesh.
    """
    import taichi as ti
    from bikini_generator.physics.cloth_sim import ClothSimulator
    from bikini_generator.config import PhysicsConfig

    # Initialize Taichi
    try:
        ti.init(arch=ti.gpu, default_fp=ti.f32)
        print("  Taichi: GPU backend")
    except Exception:
        ti.init(arch=ti.cpu, default_fp=ti.f32)
        print("  Taichi: CPU fallback")

    # Track vertex counts for splitting results back
    valid_meshes = [m for m in fabric_meshes if m is not None]
    vertex_counts = [len(m.vertices) for m in valid_meshes]

    # Merge all fabric into single mesh for simulation
    merged = trimesh.util.concatenate(valid_meshes)
    all_verts = merged.vertices.astype(np.float32)
    all_faces = merged.faces.astype(np.int32)

    print(f"  Merged fabric: {len(all_verts)} verts, {len(all_faces)} faces")

    # Custom config: zero gravity settling, high precision
    cfg = PhysicsConfig()
    cfg.gravity = 0.0           # No gravity — pure elastic settling
    cfg.num_steps = num_steps   # More iterations for better convergence
    cfg.num_substeps = 25       # More constraint iterations per step
    cfg.collision_margin = 0.001  # 1mm — very tight against body
    cfg.damping = 0.90          # Strong damping for fast convergence
    cfg.friction_coefficient = 2.0  # High friction to prevent sliding
    cfg.stretch_stiffness = 15000.0  # Stiffer fabric for better shape retention

    # Create simulator
    sim = ClothSimulator(all_verts, all_faces, config=cfg)

    # Replace the BodySurface-based LUT with high-res mesh-based LUT
    # The BodySurface model underestimates breast radius by 6-12mm
    import taichi as ti
    hi_ny, hi_ntheta = 256, 256
    mesh_lut = build_mesh_body_lut(
        body_verts, hi_ny, hi_ntheta, sim.y_min, sim.y_max)
    # Reallocate Taichi LUT field at higher resolution
    sim.body_lut = ti.field(dtype=ti.f32, shape=(hi_ny, hi_ntheta))
    sim.body_lut.from_numpy(mesh_lut)
    sim.lut_ny = hi_ny
    sim.lut_ntheta = hi_ntheta
    print(f"  Replaced body LUT with {hi_ny}x{hi_ntheta} mesh-based version")

    # Run simulation
    print(f"  Running {num_steps} physics steps...")
    final_verts = sim.simulate()
    max_disp = sim.get_max_displacement()
    print(f"  Max displacement: {max_disp*100:.1f} cm")

    # Split results back to individual meshes
    offset = 0
    for i, mesh in enumerate(valid_meshes):
        n = vertex_counts[i]
        mesh.vertices = final_verts[offset:offset + n]
        offset += n

    return valid_meshes


# ---------------------------------------------------------------------------
# Mesh creation (geometric initial placement)
# ---------------------------------------------------------------------------

def create_body_mesh():
    """Load body mesh and create trimesh object."""
    verts, faces = generate_full_body()
    skin_color = [220, 185, 160, 255]
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    mesh.visual.vertex_colors = np.tile(skin_color, (len(verts), 1))
    return mesh


def cubic_bezier_yt(p0, p1, p2, p3, n=20):
    """Sample cubic bezier in (y, theta) space."""
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        y = mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0]
        th = mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1]
        pts.append((y, th))
    return pts


def make_front_panel_outline(lm, body_surface):
    """Front panel: inverted triangle on the FRONT of the body."""
    hip_side_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2
    pubic_top_y = lm["pubic_top"][1]

    top_y = hip_side_y - 0.03
    bottom_y = pubic_top_y + 0.015
    hw_front = 0.055
    hw_crotch = 0.015

    def theta_hw(hw, y, tc):
        r = body_surface.get_surface_radius(y, tc)
        return hw / max(r, 0.01)

    thf = theta_hw(hw_front, top_y, 0.0)
    thc = theta_hw(hw_crotch, bottom_y, 0.0)

    outline = []

    for i in range(16):
        f = i / 15
        theta = thf * (1 - 2 * f)
        bow = 0.004 * np.sin(np.pi * f)
        outline.append((top_y + bow, theta))

    sy = top_y - (top_y - bottom_y) * 0.4
    sd = thf * 0.55
    outline.extend(cubic_bezier_yt(
        (top_y, -thf), (sy, -thf + sd),
        (bottom_y + 0.02, -thc * 1.5), (bottom_y, -thc),
        n=25)[1:])

    for i in range(6):
        f = i / 5
        outline.append((bottom_y, -thc + 2 * thc * f))

    outline.extend(cubic_bezier_yt(
        (bottom_y, thc), (bottom_y + 0.02, thc * 1.5),
        (sy, thf - sd), (top_y, thf),
        n=25)[1:])

    return outline


def make_back_panel_outline(lm, body_surface):
    """Back panel: inverted triangle on the BACK of the body."""
    hip_side_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2
    pubic_top_y = lm["pubic_top"][1]

    top_y = hip_side_y - 0.03
    bottom_y = pubic_top_y + 0.015
    hw_back = 0.050
    hw_crotch = 0.015

    def theta_hw(hw, y, tc):
        r = body_surface.get_surface_radius(y, tc)
        return hw / max(r, 0.01)

    thb = theta_hw(hw_back, top_y, np.pi)
    thc = theta_hw(hw_crotch, bottom_y, np.pi)

    outline = []

    for i in range(16):
        f = i / 15
        theta = np.pi + thb * (1 - 2 * f)
        bow = 0.004 * np.sin(np.pi * f)
        outline.append((top_y + bow, theta))

    sy = top_y - (top_y - bottom_y) * 0.4
    sd = thb * 0.55
    outline.extend(cubic_bezier_yt(
        (top_y, np.pi - thb), (sy, np.pi - thb + sd),
        (bottom_y + 0.02, np.pi - thc * 1.5), (bottom_y, np.pi - thc),
        n=25)[1:])

    for i in range(6):
        f = i / 5
        outline.append((bottom_y, np.pi - thc + 2 * thc * f))

    outline.extend(cubic_bezier_yt(
        (bottom_y, np.pi + thc), (bottom_y + 0.02, np.pi + thc * 1.5),
        (sy, np.pi + thb - sd), (top_y, np.pi + thb),
        n=25)[1:])

    return outline


def create_panel_mesh(body_surface, outline_yt, n_grid=40, offset=0.003):
    """Create a triangulated mesh for a panel on the body surface.

    Uses contains_points (batch) with radius tolerance to avoid
    boundary misses that create clean breaks in the mesh.
    """
    outline_arr = np.array(outline_yt)
    # Ensure path is explicitly closed
    if not np.allclose(outline_arr[0], outline_arr[-1]):
        outline_arr = np.vstack([outline_arr, outline_arr[0:1]])
    path = MplPath(outline_arr)

    y_min, y_max = outline_arr[:, 0].min(), outline_arr[:, 0].max()
    th_min, th_max = outline_arr[:, 1].min(), outline_arr[:, 1].max()

    y_vals = np.linspace(y_min - 0.005, y_max + 0.005, n_grid)
    th_vals = np.linspace(th_min - 0.05, th_max + 0.05, n_grid * 2)

    # Batch contains_points with radius tolerance to avoid boundary gaps
    grid_points = np.array([(y, th) for y in y_vals for th in th_vals])
    # Radius tolerance: half the grid spacing to include boundary points
    tol = max((y_vals[1] - y_vals[0]), (th_vals[1] - th_vals[0])) * 0.6
    inside = path.contains_points(grid_points, radius=tol)

    vertices = []
    grid_idx = {}
    n_th = len(th_vals)

    for idx_flat, is_in in enumerate(inside):
        if is_in:
            iy = idx_flat // n_th
            it = idx_flat % n_th
            y = y_vals[iy]
            th = th_vals[it]
            vidx = len(vertices)
            grid_idx[(iy, it)] = vidx
            r = body_surface.get_surface_radius(y, th) + offset
            x = -np.sin(th) * r
            z = np.cos(th) * r
            vertices.append([x, y, z])

    if len(vertices) < 3:
        return None

    faces = []
    for iy in range(n_grid - 1):
        for it in range(n_th - 1):
            i00 = grid_idx.get((iy, it))
            i10 = grid_idx.get((iy + 1, it))
            i01 = grid_idx.get((iy, it + 1))
            i11 = grid_idx.get((iy + 1, it + 1))
            if i00 is not None and i10 is not None and i01 is not None:
                faces.append([i00, i10, i01])
            if i10 is not None and i11 is not None and i01 is not None:
                faces.append([i10, i11, i01])

    if len(faces) == 0:
        return None

    mesh = trimesh.Trimesh(vertices=np.array(vertices),
                           faces=np.array(faces), process=False)
    color = [255, 80, 80, 255]  # Fully opaque
    mesh.visual.vertex_colors = np.tile(color, (len(vertices), 1))
    return mesh


def create_crotch_strip_mesh(lm, body_surface, hw=0.015, offset=0.003,
                             n_along=80, n_across=12):
    """Create crotch strip mesh in the sagittal plane.

    Not included in physics simulation — the cylindrical body model
    can't represent the concavity between the legs.
    """
    pubic_top_y = lm["pubic_top"][1]

    panel_bottom_y = pubic_top_y + 0.015
    strip_lowest_y = panel_bottom_y - 0.015

    center_line = []

    n_descent = n_along // 4
    for i in range(n_descent + 1):
        f = i / n_descent
        y = panel_bottom_y + (strip_lowest_y - panel_bottom_y) * f
        r = body_surface.get_surface_radius(y, 0.0) + offset
        center_line.append([0, y, r])

    r_wrap = 0.010 + offset
    n_wrap = n_along // 2
    for i in range(1, n_wrap + 1):
        f = i / n_wrap
        theta = np.pi * f
        x = -np.sin(theta) * r_wrap
        z = np.cos(theta) * r_wrap
        center_line.append([x, strip_lowest_y, z])

    n_ascent = n_along // 4
    for i in range(1, n_ascent + 1):
        f = i / n_ascent
        y = strip_lowest_y + (panel_bottom_y - strip_lowest_y) * f
        r = body_surface.get_surface_radius(y, np.pi) + offset
        center_line.append([0, y, -r])

    center_line = np.array(center_line)

    n_pts = len(center_line)
    vertices = []
    for i in range(n_pts):
        cx, cy, cz = center_line[i]
        for j in range(n_across + 1):
            f = j / n_across
            x = cx + hw * (2 * f - 1)
            vertices.append([x, cy, cz])

    vertices = np.array(vertices)

    faces = []
    w = n_across + 1
    for i in range(n_pts - 1):
        for j in range(n_across):
            i00 = i * w + j
            i01 = i * w + j + 1
            i10 = (i + 1) * w + j
            i11 = (i + 1) * w + j + 1
            faces.append([i00, i10, i01])
            faces.append([i10, i11, i01])

    mesh = trimesh.Trimesh(vertices=vertices, faces=np.array(faces),
                           process=False)
    color = [255, 80, 80, 255]
    mesh.visual.vertex_colors = np.tile(color, (len(vertices), 1))
    return mesh


def create_breast_zone_mesh(body_surface, center_y, center_theta,
                            radius_y, radius_theta, offset=0.004, n=60):
    """Create elliptical breast zone mesh with concentric ring grid."""
    n_rings = 12
    vertices = []
    faces = []

    r = body_surface.get_surface_radius(center_y, center_theta) + offset
    cx = -np.sin(center_theta) * r
    cz = np.cos(center_theta) * r
    vertices.append([cx, center_y, cz])

    for ring in range(1, n_rings + 1):
        frac = ring / n_rings
        for i in range(n):
            t = 2 * np.pi * i / n
            y = center_y + radius_y * frac * np.sin(t)
            theta = center_theta + radius_theta * frac * np.cos(t)
            r = body_surface.get_surface_radius(y, theta) + offset
            x = -np.sin(theta) * r
            z = np.cos(theta) * r
            vertices.append([x, y, z])

    for i in range(n):
        faces.append([0, 1 + i, 1 + (i + 1) % n])

    for ring in range(1, n_rings):
        base_inner = 1 + (ring - 1) * n
        base_outer = 1 + ring * n
        for i in range(n):
            i0 = base_inner + i
            i1 = base_inner + (i + 1) % n
            o0 = base_outer + i
            o1 = base_outer + (i + 1) % n
            faces.append([i0, o0, i1])
            faces.append([o0, o1, i1])

    mesh = trimesh.Trimesh(vertices=np.array(vertices),
                           faces=np.array(faces), process=False)
    color = [255, 80, 80, 255]
    mesh.visual.vertex_colors = np.tile(color, (len(vertices), 1))
    return mesh


def create_landmark_markers(lm, radius=0.004):
    """Create small sphere markers at key landmarks."""
    markers = []
    key_points = {
        "left_breast_apex": [255, 0, 0],
        "right_breast_apex": [255, 0, 0],
        "pubic_top": [255, 0, 255],
        "crotch_front": [255, 0, 255],
        "crotch_center": [255, 255, 0],
        "crotch_back": [255, 0, 255],
        "hip_front": [0, 255, 0],
        "hip_left": [0, 255, 0],
        "hip_right": [0, 255, 0],
    }
    for name, color in key_points.items():
        pos = lm[name]
        sphere = trimesh.creation.icosphere(subdivisions=2, radius=radius)
        sphere.apply_translation(pos)
        sphere.visual.vertex_colors = np.tile(color + [255],
                                               (len(sphere.vertices), 1))
        markers.append(sphere)
    return markers


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def make_camera_pose(azimuth, elevation=0.0, distance=1.5, target_y=1.0):
    """Create camera pose (look-at matrix)."""
    eye = np.array([
        distance * np.sin(azimuth),
        target_y + distance * np.sin(elevation),
        distance * np.cos(azimuth),
    ])
    target = np.array([0, target_y, 0])
    up = np.array([0, 1, 0])

    forward = target - eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    true_up = np.cross(right, forward)

    pose = np.eye(4)
    pose[:3, 0] = right
    pose[:3, 1] = true_up
    pose[:3, 2] = -forward
    pose[:3, 3] = eye
    return pose


def render_view(scene, camera_node, cam_pose, renderer):
    """Render scene from a given camera pose."""
    scene.set_pose(camera_node, cam_pose)
    color, _ = renderer.render(scene,
                                flags=pyrender.RenderFlags.RGBA |
                                      pyrender.RenderFlags.SKIP_CULL_FACES)
    return color


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading body mesh...")
    body_mesh = create_body_mesh()
    body_verts, _ = generate_full_body()
    lm = get_landmarks()
    body_surface = BodySurface()

    # --- Create initial fabric meshes (geometric placement) ---
    print("Creating initial fabric meshes (geometric)...")
    front_mesh = create_panel_mesh(body_surface,
                                   make_front_panel_outline(lm, body_surface),
                                   n_grid=100)
    back_mesh = create_panel_mesh(body_surface,
                                  make_back_panel_outline(lm, body_surface),
                                  n_grid=100)
    crotch_mesh = create_crotch_strip_mesh(lm, body_surface)

    left_breast = create_breast_zone_mesh(
        body_surface, lm["left_breast_apex"][1],
        np.arctan2(-lm["left_breast_apex"][0], lm["left_breast_apex"][2]),
        0.04, 0.5)
    right_breast = create_breast_zone_mesh(
        body_surface, lm["right_breast_apex"][1],
        np.arctan2(-lm["right_breast_apex"][0], lm["right_breast_apex"][2]),
        0.04, 0.5)

    # --- Physics: settle panels + breasts onto body ---
    # Crotch strip excluded (cylindrical model can't handle between-legs)
    print("Running cloth physics simulation (panels + breasts)...")
    physics_meshes = [front_mesh, back_mesh, left_breast, right_breast]
    settle_fabric_on_body(physics_meshes, body_verts, num_steps=300)

    # --- Snap crotch strip boundaries to post-physics panel edges ---
    # The crotch strip's first row should connect to front panel bottom,
    # and last row to back panel bottom. After physics moved the panels,
    # we snap the crotch endpoints to match.
    print("Connecting crotch strip to panels...")
    if crotch_mesh is not None and front_mesh is not None and back_mesh is not None:
        from scipy.spatial import cKDTree
        crotch_verts = crotch_mesh.vertices.copy()
        n_across = 13  # n_across(12) + 1
        n_crotch_pts = len(crotch_verts) // n_across

        # Front boundary: first row of crotch strip
        front_tree = cKDTree(front_mesh.vertices)
        for j in range(n_across):
            _, idx = front_tree.query(crotch_verts[j])
            crotch_verts[j] = front_mesh.vertices[idx]

        # Back boundary: last row of crotch strip
        back_tree = cKDTree(back_mesh.vertices)
        last_row_start = (n_crotch_pts - 1) * n_across
        for j in range(n_across):
            _, idx = back_tree.query(crotch_verts[last_row_start + j])
            crotch_verts[last_row_start + j] = back_mesh.vertices[idx]

        crotch_mesh.vertices = crotch_verts
        print(f"  Snapped {n_across} front + {n_across} back boundary verts")

    # --- Concatenate into one bottom mesh ---
    bottom_parts = [m for m in [front_mesh, back_mesh, crotch_mesh]
                    if m is not None]
    bottom_mesh = trimesh.util.concatenate(bottom_parts)
    bottom_mesh.visual.vertex_colors = np.tile(
        [255, 80, 80, 255], (len(bottom_mesh.vertices), 1))

    # --- Shrinkwrap: project onto exact body mesh surface ---
    # Physics gave correct topology; now pin every vertex to the actual
    # body surface for a perfectly flush fit.
    # Skip perineum vertices (radial distance < 3cm from Y-axis) —
    # they're between the legs where the body surface isn't a simple shell.
    print("Shrinkwrapping to body mesh (final pass)...")
    body_trimesh = create_body_mesh()
    skin_offset = 0.0005  # 0.5mm — barely above skin

    for mesh in [bottom_mesh, left_breast, right_breast]:
        if mesh is None:
            continue
        verts = mesh.vertices.copy()
        # Radial distance from Y-axis for each vertex
        radial_dist = np.sqrt(verts[:, 0]**2 + verts[:, 2]**2)
        # Only shrinkwrap vertices on the outer body surface (r > 3cm)
        outer_mask = radial_dist > 0.03

        if outer_mask.sum() > 0:
            outer_verts = verts[outer_mask]
            closest_pts, _, face_ids = body_trimesh.nearest.on_surface(
                outer_verts)
            # Offset along body face normals (outward)
            face_normals = body_trimesh.face_normals[face_ids]
            # Ensure normals point outward
            radial = closest_pts.copy()
            radial[:, 1] = 0
            r_len = np.linalg.norm(radial, axis=1, keepdims=True)
            radial_dir = radial / np.maximum(r_len, 1e-6)
            dots = np.sum(face_normals * radial_dir, axis=1)
            face_normals[dots < 0] *= -1
            fn_len = np.linalg.norm(face_normals, axis=1, keepdims=True)
            face_normals /= np.maximum(fn_len, 1e-6)

            verts[outer_mask] = closest_pts + face_normals * skin_offset
        mesh.vertices = verts

    n_outer = sum(1 for v in bottom_mesh.vertices
                  if np.sqrt(v[0]**2 + v[2]**2) > 0.03)
    print(f"  Projected {n_outer} outer vertices to body surface + 0.5mm")

    # --- Add 2mm thickness (extrude inward toward body) ---
    print("Extruding 2mm thickness...")
    if bottom_mesh is not None:
        bottom_mesh = thicken_mesh(bottom_mesh, thickness=0.002)
    if left_breast is not None:
        left_breast = thicken_mesh(left_breast, thickness=0.002)
    if right_breast is not None:
        right_breast = thicken_mesh(right_breast, thickness=0.002)

    # --- Export combined OBJ file ---
    print("Exporting OBJ file...")
    export_meshes = [body_mesh]
    for m in [bottom_mesh, left_breast, right_breast]:
        if m is not None:
            export_meshes.append(m)
    combined_mesh = trimesh.util.concatenate(export_meshes)
    obj_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "privacy_zones_debug.obj")
    combined_mesh.export(obj_path, file_type='obj')
    print(f"Saved OBJ to {obj_path}")

    # --- Build pyrender scene ---
    print("Creating landmark markers...")
    markers = create_landmark_markers(lm)

    scene = pyrender.Scene(bg_color=[10, 10, 30, 255],
                           ambient_light=[0.3, 0.3, 0.3])

    scene.add(pyrender.Mesh.from_trimesh(body_mesh, smooth=True))

    if bottom_mesh is not None:
        scene.add(pyrender.Mesh.from_trimesh(bottom_mesh, smooth=False))

    for bm in [left_breast, right_breast]:
        if bm is not None:
            scene.add(pyrender.Mesh.from_trimesh(bm, smooth=False))

    for m in markers:
        scene.add(pyrender.Mesh.from_trimesh(m, smooth=False))

    camera = pyrender.OrthographicCamera(xmag=0.35, ymag=0.55)
    cam_node = scene.add(camera, pose=np.eye(4))

    light = pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=4.0)
    scene.add(light, pose=make_camera_pose(azimuth=0.3, elevation=0.3,
                                            distance=2.0))
    fill_light = pyrender.DirectionalLight(color=[0.7, 0.7, 0.8],
                                            intensity=2.0)
    scene.add(fill_light, pose=make_camera_pose(azimuth=np.pi + 0.5,
                                                 elevation=0.2, distance=2.0))

    # --- Render 4 views (high resolution) ---
    W, H = 800, 1280
    renderer = pyrender.OffscreenRenderer(W, H)

    views = [
        (0, "Front"),
        (np.pi / 2, "Right Side (90\u00b0)"),
        (np.pi, "Back"),
        (-np.pi / 2, "Left Side (270\u00b0)"),
    ]

    images = []
    for azimuth, title in views:
        cam_pose = make_camera_pose(azimuth=azimuth, distance=1.8,
                                     target_y=1.05)
        img = render_view(scene, cam_node, cam_pose, renderer)
        images.append((img, title))
        print(f"  Rendered {title}")

    renderer.delete()

    # --- Combine views ---
    from PIL import ImageDraw, ImageFont
    n_views = len(views)
    gap = 10
    combined_w = W * n_views + gap * (n_views - 1)
    combined_h = H + 60
    combined = Image.new('RGBA', (combined_w, combined_h), (10, 10, 30, 255))
    draw = ImageDraw.Draw(combined)

    try:
        font_big = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except IOError:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((combined_w // 2 - 200, 5),
              "Privacy Zones: PBD Cloth Simulation + Mesh Body LUT",
              fill=(255, 255, 255), font=font_big)

    for i, (img, title) in enumerate(images):
        pil_img = Image.fromarray(img)
        x_offset = i * (W + gap)
        combined.paste(pil_img, (x_offset, 50))
        draw.text((x_offset + W // 2 - 30, 34), title,
                  fill=(255, 255, 255), font=font_small)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "privacy_zones_debug.png")
    combined.save(out_path)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
