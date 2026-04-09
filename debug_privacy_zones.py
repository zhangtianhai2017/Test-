"""Generate debug image marking privacy zones using proper 3D rendering.

Uses pyrender (OpenGL) with OSMesa for offscreen rendering.
Provides correct z-buffering, camera projection, and lighting.

Bikini bottom = front panel + crotch strip (sagittal plane) + back panel.
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


def cubic_bezier_3d(p0, p1, p2, p3, n=20):
    """Sample cubic bezier in 3D space. Returns (n+1, 3) array."""
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        pt = mt**3*p0 + 3*mt**2*t*p1 + 3*mt*t**2*p2 + t**3*p3
        pts.append(pt)
    return np.array(pts)


def make_front_panel_outline(lm, body_surface):
    """Front panel: inverted triangle on the FRONT of the body.

    Bottom edge raised to pubic area level - tight swimwear pulls up.
    """
    hip_side_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2
    pubic_top_y = lm["pubic_top"][1]  # 0.865

    top_y = hip_side_y - 0.03   # 0.946
    # Tight bikini: bottom at pubic area, not at crotch fold
    bottom_y = pubic_top_y + 0.015  # ~0.88, elastic pulls fabric up
    hw_front = 0.055
    hw_crotch = 0.015

    def theta_hw(hw, y, tc):
        r = body_surface.get_surface_radius(y, tc)
        return hw / max(r, 0.01)

    thf = theta_hw(hw_front, top_y, 0.0)
    thc = theta_hw(hw_crotch, bottom_y, 0.0)

    outline = []

    # Top edge
    for i in range(16):
        f = i / 15
        theta = thf * (1 - 2 * f)
        bow = 0.004 * np.sin(np.pi * f)
        outline.append((top_y + bow, theta))

    # Right leg scoop
    sy = top_y - (top_y - bottom_y) * 0.4
    sd = thf * 0.55
    outline.extend(cubic_bezier_yt(
        (top_y, -thf), (sy, -thf + sd),
        (bottom_y + 0.02, -thc * 1.5), (bottom_y, -thc),
        n=25)[1:])

    # Bottom edge
    for i in range(6):
        f = i / 5
        outline.append((bottom_y, -thc + 2 * thc * f))

    # Left leg scoop
    outline.extend(cubic_bezier_yt(
        (bottom_y, thc), (bottom_y + 0.02, thc * 1.5),
        (sy, thf - sd), (top_y, thf),
        n=25)[1:])

    return outline


def make_back_panel_outline(lm, body_surface):
    """Back panel: inverted triangle on the BACK of the body.

    Bottom edge raised - tight swimwear pulls up.
    """
    hip_side_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2
    pubic_top_y = lm["pubic_top"][1]

    top_y = hip_side_y - 0.03
    # Same height as front bottom - fabric pulled tight
    bottom_y = pubic_top_y + 0.015  # ~0.88
    hw_back = 0.050
    hw_crotch = 0.015

    def theta_hw(hw, y, tc):
        r = body_surface.get_surface_radius(y, tc)
        return hw / max(r, 0.01)

    thb = theta_hw(hw_back, top_y, np.pi)
    thc = theta_hw(hw_crotch, bottom_y, np.pi)

    outline = []

    # Top edge
    for i in range(16):
        f = i / 15
        theta = np.pi + thb * (1 - 2 * f)
        bow = 0.004 * np.sin(np.pi * f)
        outline.append((top_y + bow, theta))

    # Right scoop (as seen from back)
    sy = top_y - (top_y - bottom_y) * 0.4
    sd = thb * 0.55
    outline.extend(cubic_bezier_yt(
        (top_y, np.pi - thb), (sy, np.pi - thb + sd),
        (bottom_y + 0.02, np.pi - thc * 1.5), (bottom_y, np.pi - thc),
        n=25)[1:])

    # Bottom edge
    for i in range(6):
        f = i / 5
        outline.append((bottom_y, np.pi - thc + 2 * thc * f))

    # Left scoop
    outline.extend(cubic_bezier_yt(
        (bottom_y, np.pi + thc), (bottom_y + 0.02, np.pi + thc * 1.5),
        (sy, np.pi + thb - sd), (top_y, np.pi + thb),
        n=25)[1:])

    return outline


def create_panel_mesh(body_surface, outline_yt, n_grid=40, offset=0.003):
    """Create a triangulated mesh for a panel on the body surface."""
    outline_arr = np.array(outline_yt)
    path = MplPath(outline_arr)

    y_min, y_max = outline_arr[:, 0].min(), outline_arr[:, 0].max()
    th_min, th_max = outline_arr[:, 1].min(), outline_arr[:, 1].max()

    y_vals = np.linspace(y_min - 0.005, y_max + 0.005, n_grid)
    th_vals = np.linspace(th_min - 0.05, th_max + 0.05, n_grid * 2)

    vertices = []
    grid_idx = {}

    for iy, y in enumerate(y_vals):
        for it, th in enumerate(th_vals):
            if path.contains_point((y, th)):
                idx = len(vertices)
                grid_idx[(iy, it)] = idx
                r = body_surface.get_surface_radius(y, th) + offset
                x = -np.sin(th) * r
                z = np.cos(th) * r
                vertices.append([x, y, z])

    if len(vertices) < 3:
        return None

    faces = []
    for iy in range(n_grid - 1):
        for it in range(len(th_vals) - 1):
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
    color = [255, 80, 80, 180]
    mesh.visual.vertex_colors = np.tile(color, (len(vertices), 1))
    return mesh


def create_crotch_strip_mesh(lm, body_surface, hw=0.015, offset=0.003,
                             n_along=40, n_across=6):
    """Create crotch strip mesh that follows the body surface from front to back.

    Three segments, ALL on the body surface:
    1. Front descent: theta=0 (front surface), Y drops from front_bottom to crotch_center
    2. Perineum wrap: at Y=crotch_center, semicircle from theta=0 to theta=pi
       using the small perineum radius (~3cm), staying on the body surface
    3. Back ascent: theta=pi (back surface), Y rises from crotch_center to back_bottom

    Width: ±hw in X direction (perpendicular to strip direction).
    """
    pubic_top_y = lm["pubic_top"][1]  # 0.865

    # Tight swimwear: fabric pulled up to pubic area, barely dips below
    panel_bottom_y = pubic_top_y + 0.015  # 0.88 (matches panel bottoms)
    # Strip lowest point: only 1-2cm below panel bottom (elastic pulls tight)
    strip_lowest_y = panel_bottom_y - 0.015  # ~0.865

    # Build center line in 3 segments
    center_line = []

    # Segment 1: front descent, theta=0, Y from panel_bottom to strip_lowest
    # Very short descent - fabric barely dips
    n_descent = n_along // 4
    for i in range(n_descent + 1):
        f = i / n_descent
        y = panel_bottom_y + (strip_lowest_y - panel_bottom_y) * f
        r = body_surface.get_surface_radius(y, 0.0) + offset
        center_line.append([0, y, r])  # X=0, Z=+r (front surface)

    # Segment 2: wrap from front to back at strip_lowest_y
    # Very tight: small radius, fabric pressed into body crease by elastic
    r_wrap = 0.010 + offset  # 1cm - extremely tight against perineum
    n_wrap = n_along // 2
    for i in range(1, n_wrap + 1):
        f = i / n_wrap
        theta = np.pi * f
        x = -np.sin(theta) * r_wrap
        z = np.cos(theta) * r_wrap
        center_line.append([x, strip_lowest_y, z])

    # Segment 3: back ascent, theta=pi, Y from strip_lowest to panel_bottom
    n_ascent = n_along // 4
    for i in range(1, n_ascent + 1):
        f = i / n_ascent
        y = strip_lowest_y + (panel_bottom_y - strip_lowest_y) * f
        r = body_surface.get_surface_radius(y, np.pi) + offset
        center_line.append([0, y, -r])  # X=0, Z=-r (back surface)

    center_line = np.array(center_line)

    # Build strip mesh: at each center point, add width perpendicular to strip direction
    n_pts = len(center_line)
    vertices = []
    for i in range(n_pts):
        cx, cy, cz = center_line[i]
        for j in range(n_across + 1):
            f = j / n_across
            x = cx + hw * (2 * f - 1)  # ±hw in X
            vertices.append([x, cy, cz])

    vertices = np.array(vertices)

    # Triangulate
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

    mesh = trimesh.Trimesh(vertices=vertices, faces=np.array(faces), process=False)
    color = [255, 80, 80, 180]
    mesh.visual.vertex_colors = np.tile(color, (len(vertices), 1))
    return mesh


def _project_to_mesh(body_verts, point, direction=None):
    """Project a point onto the actual body mesh surface.

    Finds the nearest mesh vertex and returns its radial distance.
    More accurate than BodySurface ellipsoidal model, especially at breasts.
    """
    # Find nearest vertex
    dists = np.linalg.norm(body_verts - point, axis=1)
    nearest = body_verts[np.argmin(dists)]
    return np.sqrt(nearest[0]**2 + nearest[2]**2)


def create_breast_zone_mesh(body_surface, center_y, center_theta,
                            radius_y, radius_theta, offset=0.004, n=30,
                            body_verts=None):
    """Create elliptical breast zone mesh on body surface.

    Uses actual mesh vertices for projection (not BodySurface model)
    to prevent clipping at the breast area where the model is inaccurate.
    """
    vertices = []

    def get_radius(y, theta):
        """Get body radius using actual mesh if available."""
        if body_verts is not None:
            # Approximate target point
            r_est = body_surface.get_surface_radius(y, theta)
            target = np.array([-np.sin(theta) * r_est, y, np.cos(theta) * r_est])
            # Find nearest mesh vertex in a cone around this direction
            direction = np.array([-np.sin(theta), 0, np.cos(theta)])
            # Filter vertices near this Y and direction
            y_mask = np.abs(body_verts[:, 1] - y) < 0.02
            if y_mask.sum() > 0:
                candidates = body_verts[y_mask]
                # Project onto radial direction
                radii = candidates[:, 0] * (-np.sin(theta)) + candidates[:, 2] * np.cos(theta)
                # Use the maximum radius in this direction (outermost surface)
                lateral = np.abs(candidates[:, 0] * np.cos(theta) + candidates[:, 2] * np.sin(theta))
                close_mask = lateral < 0.03  # within 3cm of this theta line
                if close_mask.sum() > 0:
                    return np.max(radii[close_mask])
            return r_est
        return body_surface.get_surface_radius(y, theta)

    r = get_radius(center_y, center_theta) + offset
    cx = -np.sin(center_theta) * r
    cz = np.cos(center_theta) * r
    vertices.append([cx, center_y, cz])

    for i in range(n):
        t = 2 * np.pi * i / n
        y = center_y + radius_y * np.sin(t)
        theta = center_theta + radius_theta * np.cos(t)
        r = get_radius(y, theta) + offset
        x = -np.sin(theta) * r
        z = np.cos(theta) * r
        vertices.append([x, y, z])

    faces = []
    for i in range(n):
        faces.append([0, 1 + i, 1 + (i + 1) % n])

    mesh = trimesh.Trimesh(vertices=np.array(vertices),
                           faces=np.array(faces), process=False)
    color = [255, 80, 80, 180]
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


def main():
    print("Loading body mesh...")
    body_mesh = create_body_mesh()
    lm = get_landmarks()
    body_surface = BodySurface()

    print("Creating front panel mesh...")
    front_outline = make_front_panel_outline(lm, body_surface)
    front_mesh = create_panel_mesh(body_surface, front_outline, n_grid=50)

    print("Creating back panel mesh...")
    back_outline = make_back_panel_outline(lm, body_surface)
    back_mesh = create_panel_mesh(body_surface, back_outline, n_grid=50)

    print("Creating crotch strip mesh (sagittal plane)...")
    crotch_mesh = create_crotch_strip_mesh(lm, body_surface)

    print("Creating breast zone meshes (using actual mesh projection)...")
    body_verts, _ = generate_full_body()
    left_breast = create_breast_zone_mesh(
        body_surface, lm["left_breast_apex"][1],
        np.arctan2(-lm["left_breast_apex"][0], lm["left_breast_apex"][2]),
        0.04, 0.5, body_verts=body_verts)
    right_breast = create_breast_zone_mesh(
        body_surface, lm["right_breast_apex"][1],
        np.arctan2(-lm["right_breast_apex"][0], lm["right_breast_apex"][2]),
        0.04, 0.5, body_verts=body_verts)

    print("Creating landmark markers...")
    markers = create_landmark_markers(lm)

    # Build pyrender scene
    scene = pyrender.Scene(bg_color=[10, 10, 30, 255],
                           ambient_light=[0.3, 0.3, 0.3])

    # Add body
    scene.add(pyrender.Mesh.from_trimesh(body_mesh, smooth=True))

    # Add bikini panels (3 separate pieces)
    for mesh in [front_mesh, back_mesh, crotch_mesh]:
        if mesh is not None:
            scene.add(pyrender.Mesh.from_trimesh(mesh, smooth=False))

    for bm in [left_breast, right_breast]:
        if bm is not None:
            scene.add(pyrender.Mesh.from_trimesh(bm, smooth=False))

    for m in markers:
        scene.add(pyrender.Mesh.from_trimesh(m, smooth=False))

    # Camera
    camera = pyrender.OrthographicCamera(xmag=0.35, ymag=0.55)
    cam_node = scene.add(camera, pose=np.eye(4))

    # Lighting
    light = pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=4.0)
    scene.add(light, pose=make_camera_pose(azimuth=0.3, elevation=0.3, distance=2.0))
    fill_light = pyrender.DirectionalLight(color=[0.7, 0.7, 0.8], intensity=2.0)
    scene.add(fill_light, pose=make_camera_pose(azimuth=np.pi + 0.5, elevation=0.2, distance=2.0))

    # Render 4 views: front, right side (90°), left side (270°/close), back
    W, H = 500, 800
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

    # Combine views into one image
    from PIL import ImageDraw, ImageFont
    n_views = len(views)
    gap = 10
    combined_w = W * n_views + gap * (n_views - 1)
    combined_h = H + 60
    combined = Image.new('RGBA', (combined_w, combined_h), (10, 10, 30, 255))
    draw = ImageDraw.Draw(combined)

    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except IOError:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((combined_w // 2 - 180, 5),
              "Privacy Zones: Front + Back Panels + Crotch Strip",
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
