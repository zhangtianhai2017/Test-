"""Generate debug image marking privacy zones using proper 3D rendering.

Approach: parametric mesh + body surface projection.
- Creates clean fabric meshes with smooth parametric boundaries
- Projects all vertices onto body surface using trimesh closest-point query
- Offsets along surface normals for 2mm solid shell thickness
- Bikini bottom = one continuous mesh (front + crotch + back)
- Breast zones = elliptical disc meshes

Advantages over body-face-selection approach:
- Smooth edges (defined by parametric curves, not body mesh topology)
- No gaps between segments (continuous grid connectivity)
- Resolution independent of body mesh density
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


# ---------------------------------------------------------------------------
# Helpers: projection and solid shell
# ---------------------------------------------------------------------------

def project_and_offset(verts_3d, body_trimesh, thickness=0.002):
    """Project points onto body surface and offset outward along normals."""
    closest, dist, fids = body_trimesh.nearest.on_surface(verts_3d)
    normals = body_trimesh.face_normals[fids].copy()

    # Ensure normals point outward from body
    radial = closest.copy()
    radial[:, 1] = 0  # XZ plane radial direction
    radial_len = np.linalg.norm(radial, axis=1)

    # For vertices near body center axis (crotch/perineum), use direction
    # from body center-of-mass instead of radial
    near_axis = radial_len < 0.03
    body_com = np.array([0.0, 1.0, 0.0])
    com_dir = closest - body_com

    ref = radial.copy()
    ref[near_axis] = com_dir[near_axis]
    ref_len = np.linalg.norm(ref, axis=1, keepdims=True)
    ref /= np.maximum(ref_len, 1e-8)

    dots = np.sum(normals * ref, axis=1)
    normals[dots < 0] *= -1

    outer = closest + normals * thickness
    return outer, closest, normals


def make_solid_shell(outer, inner, faces, color):
    """Build extruded solid: inner surface + outer surface + side walls."""
    from collections import Counter

    n = len(outer)
    all_verts = np.vstack([inner, outer])
    inner_faces = faces[:, ::-1]  # reversed winding
    outer_faces = faces + n

    # Find boundary edges (appear in exactly 1 triangle)
    ec = Counter()
    for f in faces:
        for i in range(3):
            a, b = int(f[i]), int(f[(i + 1) % 3])
            ec[(min(a, b), max(a, b))] += 1

    sides = []
    for (a, b), c in ec.items():
        if c == 1:
            sides.append([a, b, b + n])
            sides.append([a, b + n, a + n])

    parts = [inner_faces, outer_faces]
    if sides:
        parts.append(np.array(sides, dtype=np.int32))
    all_faces = np.vstack(parts)

    mesh = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=False)
    mesh.visual.vertex_colors = np.tile(list(color) + [255], (len(all_verts), 1))
    return mesh


# ---------------------------------------------------------------------------
# Zone outline definitions in (Y, theta) space
# ---------------------------------------------------------------------------

def make_front_panel_zone(lm):
    """Front panel: inverted triangle with bezier leg scoops in (Y, theta)."""
    hip_side_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2
    pubic_top_y = lm["pubic_top"][1]
    top_y = hip_side_y - 0.03
    bottom_y = pubic_top_y + 0.015
    hw_top, hw_bottom = 0.065, 0.018
    r_top, r_bot = 0.10, 0.085
    thf = hw_top / r_top
    thc = hw_bottom / r_bot

    outline = []
    for i in range(20):
        f = i / 19
        theta = thf * (1 - 2 * f)
        bow = 0.004 * np.sin(np.pi * f)
        outline.append((top_y + bow, theta))

    sy = top_y - (top_y - bottom_y) * 0.4
    sd = thf * 0.55
    n_bez = 30
    for i in range(1, n_bez + 1):
        t = i / n_bez
        mt = 1 - t
        p0, p1 = (top_y, -thf), (sy, -thf + sd)
        p2, p3 = (bottom_y + 0.02, -thc * 1.5), (bottom_y, -thc)
        y = mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0]
        th = mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1]
        outline.append((y, th))

    for i in range(6):
        f = i / 5
        outline.append((bottom_y, -thc + 2 * thc * f))

    for i in range(1, n_bez + 1):
        t = i / n_bez
        mt = 1 - t
        p0, p1 = (bottom_y, thc), (bottom_y + 0.02, thc * 1.5)
        p2, p3 = (sy, thf - sd), (top_y, thf)
        y = mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0]
        th = mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1]
        outline.append((y, th))

    outline_arr = np.array(outline)
    if not np.allclose(outline_arr[0], outline_arr[-1], atol=0.01):
        outline_arr = np.vstack([outline_arr, outline_arr[0:1]])
    return MplPath(outline_arr)


def make_back_panel_zone(lm):
    """Back panel: inverted triangle on the back in (Y, theta)."""
    hip_side_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2
    pubic_top_y = lm["pubic_top"][1]
    top_y = hip_side_y - 0.03
    bottom_y = pubic_top_y + 0.015
    hw_top, hw_bottom = 0.060, 0.018
    r_top, r_bot = 0.10, 0.085
    thb = hw_top / r_top
    thc = hw_bottom / r_bot

    outline = []
    for i in range(20):
        f = i / 19
        theta = np.pi + thb * (1 - 2 * f)
        bow = 0.004 * np.sin(np.pi * f)
        outline.append((top_y + bow, theta))

    sy = top_y - (top_y - bottom_y) * 0.4
    sd = thb * 0.55
    n_bez = 30
    for i in range(1, n_bez + 1):
        t = i / n_bez
        mt = 1 - t
        p0, p1 = (top_y, np.pi - thb), (sy, np.pi - thb + sd)
        p2, p3 = (bottom_y + 0.02, np.pi - thc * 1.5), (bottom_y, np.pi - thc)
        y = mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0]
        th = mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1]
        outline.append((y, th))

    for i in range(6):
        f = i / 5
        outline.append((bottom_y, np.pi - thc + 2 * thc * f))

    for i in range(1, n_bez + 1):
        t = i / n_bez
        mt = 1 - t
        p0, p1 = (bottom_y, np.pi + thc), (bottom_y + 0.02, np.pi + thc * 1.5)
        p2, p3 = (sy, np.pi + thb - sd), (top_y, np.pi + thb)
        y = mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0]
        th = mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1]
        outline.append((y, th))

    outline_arr = np.array(outline)
    if not np.allclose(outline_arr[0], outline_arr[-1], atol=0.01):
        outline_arr = np.vstack([outline_arr, outline_arr[0:1]])
    return MplPath(outline_arr)


def scan_hw_at_y(path, y, center_theta, r_body):
    """Find half-width in meters at given Y by scanning the outline path."""
    verts = path.vertices
    th_lo, th_hi = verts[:, 1].min() - 0.05, verts[:, 1].max() + 0.05
    test = np.linspace(th_lo, th_hi, 500)
    pts = np.column_stack([np.full(500, y), test])
    inside = path.contains_points(pts)
    if not inside.any():
        return 0.005  # fallback minimum
    th_in = test[inside]
    max_angle = max(abs(th_in.min() - center_theta), abs(th_in.max() - center_theta))
    return r_body * np.sin(min(max_angle, np.pi / 2))


# ---------------------------------------------------------------------------
# Parametric fabric generators
# ---------------------------------------------------------------------------

def create_bottom_mesh(lm, body_trimesh, thickness=0.002, color=(255, 80, 100)):
    """Create entire bikini bottom as one continuous parametric mesh.

    All rows share the same column count (n_cols), connected as a single grid:
    1. Front panel: rows at different Y, width from outline (leg scoops)
    2. Crotch strip: arc from front-bottom through perineum to back-bottom
    3. Back panel: rows at different Y, width from outline

    Each vertex is then projected onto the body surface for perfect conformity.
    """
    pubic_top_y = lm["pubic_top"][1]
    crotch_y = lm["crotch_center"][1]
    hip_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2

    top_y = hip_y - 0.03
    bot_y = pubic_top_y + 0.015
    crotch_bot_y = crotch_y - 0.02
    hw_crotch = 0.018
    r_body = 0.11  # approximate body radius (corrected by projection)

    n_cols = 24
    n_front = 20
    n_crotch = 25
    n_back = 20

    front_path = make_front_panel_zone(lm)
    back_path = make_back_panel_zone(lm)

    all_verts = []

    # ---- Front panel rows: top_y → bot_y ----
    front_ys = np.linspace(top_y, bot_y, n_front)
    for y in front_ys:
        hw = scan_hw_at_y(front_path, y, 0.0, r_body)
        xs = np.linspace(-hw, hw, n_cols)
        for x in xs:
            z = np.sqrt(max(r_body**2 - x**2, 0.001))
            all_verts.append([x, y, z])

    # ---- Crotch strip rows: arc from front-bottom to back-bottom ----
    # Interior rows only (endpoints are adjacent to panel rows)
    front_hw = scan_hw_at_y(front_path, bot_y, 0.0, r_body)
    back_hw = scan_hw_at_y(back_path, bot_y, np.pi, r_body)

    phis = np.linspace(0, np.pi, n_crotch + 2)[1:-1]  # skip endpoints
    for phi in phis:
        # Y: U-shape (high at front/back, low in middle)
        y = crotch_bot_y + (bot_y - crotch_bot_y) * np.cos(phi)**2
        # Z: front(+) through 0 to back(-)
        z_center = r_body * np.cos(phi)
        # Width: smooth transition panel_hw ↔ crotch_hw
        t = np.sin(phi)  # 0 at endpoints, 1 in middle
        endpoint_hw = front_hw if phi < np.pi / 2 else back_hw
        hw = endpoint_hw * (1 - t) + hw_crotch * t

        xs = np.linspace(-hw, hw, n_cols)
        for x in xs:
            all_verts.append([x, y, z_center])

    # ---- Back panel rows: bot_y → top_y ----
    back_ys = np.linspace(bot_y, top_y, n_back)
    for y in back_ys:
        hw = scan_hw_at_y(back_path, y, np.pi, r_body)
        xs = np.linspace(-hw, hw, n_cols)
        for x in xs:
            z = -np.sqrt(max(r_body**2 - x**2, 0.001))
            all_verts.append([x, y, z])

    all_verts = np.array(all_verts, dtype=np.float64)
    total_rows = n_front + n_crotch + n_back

    # Build faces: uniform grid connectivity
    faces = []
    for ri in range(total_rows - 1):
        for ci in range(n_cols - 1):
            a = ri * n_cols + ci
            b = a + 1
            c = (ri + 1) * n_cols + ci
            d = c + 1
            faces.append([a, c, b])
            faces.append([b, c, d])
    faces = np.array(faces, dtype=np.int32)

    # Project onto body surface and offset
    print(f"    Projecting {len(all_verts)} vertices onto body surface...")
    outer, inner, normals = project_and_offset(all_verts, body_trimesh, thickness)
    return make_solid_shell(outer, inner, faces, color)


def create_breast_mesh(lm, body_trimesh, side='left', thickness=0.002,
                       color=(255, 160, 40)):
    """Create elliptical breast zone as parametric disc, projected onto body."""
    apex = lm[f"{side}_breast_apex"]
    cy = apex[1]
    cth = np.arctan2(-apex[0], apex[2])
    if cth < 0:
        cth += 2 * np.pi

    ry = 0.04    # Y radius (meters)
    rth = 0.5    # theta radius (radians)
    r_body = 0.11
    n_rings = 12
    n_radial = 24

    # Center vertex
    verts_3d = [[-r_body * np.sin(cth), cy, r_body * np.cos(cth)]]

    # Concentric rings
    for ring in range(1, n_rings + 1):
        frac = ring / n_rings
        for j in range(n_radial):
            angle = 2 * np.pi * j / n_radial
            y = cy + ry * frac * np.sin(angle)
            th = cth + rth * frac * np.cos(angle)
            verts_3d.append([-r_body * np.sin(th), y, r_body * np.cos(th)])

    verts_3d = np.array(verts_3d, dtype=np.float64)

    # Faces: center fan + ring-to-ring quads
    faces = []
    for j in range(n_radial):
        faces.append([0, 1 + j, 1 + (j + 1) % n_radial])

    for ring in range(1, n_rings):
        ib = 1 + (ring - 1) * n_radial
        ob = 1 + ring * n_radial
        for j in range(n_radial):
            jn = (j + 1) % n_radial
            faces.append([ib + j, ob + j, ib + jn])
            faces.append([ib + jn, ob + j, ob + jn])

    faces = np.array(faces, dtype=np.int32)

    outer, inner, normals = project_and_offset(verts_3d, body_trimesh, thickness)
    return make_solid_shell(outer, inner, faces, color)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def create_body_mesh():
    """Load body mesh and create trimesh with skin color."""
    verts, faces = generate_full_body()
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    mesh.visual.vertex_colors = np.tile([220, 185, 160, 255], (len(verts), 1))
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
    body_verts, body_faces = generate_full_body()
    body_trimesh = trimesh.Trimesh(vertices=body_verts, faces=body_faces,
                                    process=False)
    body_mesh = create_body_mesh()
    lm = get_landmarks()

    fabric_meshes = []

    # --- Bikini bottom: one continuous parametric mesh ---
    print("Creating bikini bottom (parametric + projection)...")
    bottom = create_bottom_mesh(lm, body_trimesh)
    fabric_meshes.append(bottom)
    print(f"  Bottom: {len(bottom.vertices)} verts, {len(bottom.faces)} faces")

    # --- Breast zones: elliptical discs ---
    for side in ['left', 'right']:
        print(f"Creating {side} breast zone...")
        breast = create_breast_mesh(lm, body_trimesh, side)
        fabric_meshes.append(breast)
        print(f"  {side}: {len(breast.vertices)} verts, {len(breast.faces)} faces")

    # --- Export 3D files ---
    print("Exporting 3D files...")
    export_parts = [body_mesh] + fabric_meshes
    combined = trimesh.util.concatenate(export_parts)
    base = os.path.dirname(os.path.abspath(__file__))

    obj_path = os.path.join(base, "privacy_zones_debug.obj")
    combined.export(obj_path, file_type='obj')
    print(f"  OBJ: {obj_path}")

    glb_path = os.path.join(base, "privacy_zones_debug.glb")
    combined.export(glb_path, file_type='glb')
    print(f"  GLB: {glb_path}")

    # --- Build pyrender scene ---
    print("Creating landmark markers...")
    markers = create_landmark_markers(lm)

    scene = pyrender.Scene(bg_color=[10, 10, 30, 255],
                           ambient_light=[0.3, 0.3, 0.3])
    scene.add(pyrender.Mesh.from_trimesh(body_mesh, smooth=True))
    for fm in fabric_meshes:
        scene.add(pyrender.Mesh.from_trimesh(fm, smooth=False))
    for m in markers:
        scene.add(pyrender.Mesh.from_trimesh(m, smooth=False))

    camera = pyrender.OrthographicCamera(xmag=0.35, ymag=0.55)
    cam_node = scene.add(camera, pose=np.eye(4))

    light = pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=4.0)
    scene.add(light, pose=make_camera_pose(azimuth=0.3, elevation=0.3,
                                            distance=2.0))
    fill_light = pyrender.DirectionalLight(color=[0.7, 0.7, 0.8], intensity=2.0)
    scene.add(fill_light, pose=make_camera_pose(azimuth=np.pi + 0.5,
                                                 elevation=0.2, distance=2.0))

    # --- Render 4 views ---
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
        cam_pose = make_camera_pose(azimuth=azimuth, distance=1.8, target_y=1.05)
        img = render_view(scene, cam_node, cam_pose, renderer)
        images.append((img, title))
        print(f"  Rendered {title}")

    renderer.delete()

    # --- Combine views into one image ---
    from PIL import ImageDraw, ImageFont
    n_views = len(views)
    gap = 10
    combined_w = W * n_views + gap * (n_views - 1)
    combined_h = H + 60
    combined_img = Image.new('RGBA', (combined_w, combined_h),
                             (10, 10, 30, 255))
    draw = ImageDraw.Draw(combined_img)

    try:
        font_big = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except IOError:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((combined_w // 2 - 200, 5),
              "Privacy Zones: Parametric Mesh + Projection (2mm)",
              fill=(255, 255, 255), font=font_big)

    for i, (img, title) in enumerate(images):
        pil_img = Image.fromarray(img)
        x_offset = i * (W + gap)
        combined_img.paste(pil_img, (x_offset, 50))
        draw.text((x_offset + W // 2 - 30, 34), title,
                  fill=(255, 255, 255), font=font_small)

    out_path = os.path.join(base, "privacy_zones_debug.png")
    combined_img.save(out_path)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
