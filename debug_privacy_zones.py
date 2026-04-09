"""Generate debug image marking privacy zones using proper 3D rendering.

Uses pyrender (OpenGL) with OSMesa for offscreen rendering.
Provides correct z-buffering, camera projection, and lighting.
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
    skin_color = [220, 185, 160, 255]  # RGBA skin tone
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    mesh.visual.vertex_colors = np.tile(skin_color, (len(verts), 1))
    return mesh


def cubic_bezier(p0, p1, p2, p3, n=20):
    """Sample cubic bezier curve, returns list of (y, theta) points."""
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        y = (mt**3 * p0[0] + 3 * mt**2 * t * p1[0] +
             3 * mt * t**2 * p2[0] + t**3 * p3[0])
        th = (mt**3 * p0[1] + 3 * mt**2 * t * p1[1] +
              3 * mt * t**2 * p2[1] + t**3 * p3[1])
        pts.append((y, th))
    return pts


def make_bikini_bottom_outline(lm, body_surface):
    """Create bikini bottom outline in (Y, theta) space.

    Returns list of (y, theta) tuples forming a closed curve.
    """
    hip_side_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2
    crotch_front_y = lm["crotch_front"][1]
    crotch_back_y = lm["crotch_back"][1]
    crotch_center_y = lm["crotch_center"][1]

    top_y = hip_side_y - 0.03
    front_bottom_y = crotch_front_y - 0.01
    back_bottom_y = crotch_back_y - 0.01

    hw_front = 0.055
    hw_back = 0.050
    hw_crotch = 0.015

    def theta_hw(hw, y, tc):
        r = body_surface.get_surface_radius(y, tc)
        return hw / max(r, 0.01)

    thf = theta_hw(hw_front, top_y, 0.0)
    thb = theta_hw(hw_back, top_y, np.pi)
    thc_f = theta_hw(hw_crotch, front_bottom_y, 0.0)
    thc_b = theta_hw(hw_crotch, back_bottom_y, np.pi)

    outline = []

    # 1. Front top edge
    for i in range(16):
        f = i / 15
        theta = thf * (1 - 2 * f)
        bow = 0.004 * np.sin(np.pi * f)
        outline.append((top_y + bow, theta))

    # 2. Right leg scoop
    sy = top_y - (top_y - front_bottom_y) * 0.4
    sd = thf * 0.55
    outline.extend(cubic_bezier(
        (top_y, -thf), (sy, -thf + sd),
        (front_bottom_y + 0.02, -thc_f * 1.5), (front_bottom_y, -thc_f),
        n=25)[1:])

    # 3. Right crotch strip (front→back, dipping to crotch_center)
    n_crotch = 30
    for i in range(n_crotch + 1):
        f = i / n_crotch
        tc = np.pi * f
        y_start = front_bottom_y
        y_end = back_bottom_y
        y_baseline = y_start + (y_end - y_start) * f
        dip_depth = y_baseline - crotch_center_y
        dip = -dip_depth * np.sin(np.pi * f)
        y_here = y_baseline + dip
        off = theta_hw(hw_crotch, max(y_here, crotch_center_y), tc)
        outline.append((y_here, tc - off))

    # 4. Back right leg scoop (up)
    sy_b = top_y - (top_y - back_bottom_y) * 0.4
    sd_b = thb * 0.55
    outline.extend(cubic_bezier(
        (back_bottom_y, np.pi - thc_b), (back_bottom_y + 0.02, np.pi - thc_b * 1.5),
        (sy_b, np.pi - thb + sd_b), (top_y, np.pi - thb),
        n=25)[1:])

    # 5. Back top edge
    for i in range(16):
        f = i / 15
        theta = np.pi - thb + 2 * thb * f
        bow = 0.004 * np.sin(np.pi * f)
        outline.append((top_y + bow, theta))

    # 6. Back left leg scoop (down)
    outline.extend(cubic_bezier(
        (top_y, np.pi + thb), (sy_b, np.pi + thb - sd_b),
        (back_bottom_y + 0.02, np.pi + thc_b * 1.5), (back_bottom_y, np.pi + thc_b),
        n=25)[1:])

    # 7. Left crotch strip (back→front)
    for i in range(n_crotch + 1):
        f = i / n_crotch
        tc = np.pi * (1 - f)
        y_start = back_bottom_y
        y_end = front_bottom_y
        y_baseline = y_start + (y_end - y_start) * f
        dip_depth = y_baseline - crotch_center_y
        dip = -dip_depth * np.sin(np.pi * f)
        y_here = y_baseline + dip
        off = theta_hw(hw_crotch, max(y_here, crotch_center_y), tc)
        outline.append((y_here, tc + off))

    # 8. Front left leg scoop (up)
    outline.extend(cubic_bezier(
        (front_bottom_y, thc_f), (front_bottom_y + 0.02, thc_f * 1.5),
        (sy, thf - sd), (top_y, thf),
        n=25)[1:])

    return outline


def create_panel_mesh(body_surface, outline_yt, n_grid=40, offset=0.003):
    """Create a triangulated mesh for a panel on the body surface.

    Fills the interior of the outline with a grid, projects onto body surface,
    and triangulates.
    """
    # Convert outline to (Y, theta) path for containment test
    outline_arr = np.array(outline_yt)
    path = MplPath(outline_arr)

    # Bounding box in (Y, theta) space
    y_min, y_max = outline_arr[:, 0].min(), outline_arr[:, 0].max()
    th_min, th_max = outline_arr[:, 1].min(), outline_arr[:, 1].max()

    # Create grid
    y_vals = np.linspace(y_min - 0.005, y_max + 0.005, n_grid)
    th_vals = np.linspace(th_min - 0.05, th_max + 0.05, n_grid * 2)

    # Find interior grid points
    vertices = []
    grid_idx = {}  # (iy, it) -> vertex index

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

    # Create triangles from adjacent grid points
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

    vertices = np.array(vertices)
    faces = np.array(faces)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

    # Color: semi-transparent red
    color = [255, 80, 80, 180]
    mesh.visual.vertex_colors = np.tile(color, (len(vertices), 1))
    return mesh


def create_breast_zone_mesh(body_surface, center_y, center_theta,
                            radius_y, radius_theta, offset=0.003, n=30):
    """Create elliptical breast zone mesh on body surface."""
    vertices = []
    # Center point
    r = body_surface.get_surface_radius(center_y, center_theta) + offset
    cx = -np.sin(center_theta) * r
    cz = np.cos(center_theta) * r
    center_idx = 0
    vertices.append([cx, center_y, cz])

    # Boundary points
    for i in range(n):
        t = 2 * np.pi * i / n
        y = center_y + radius_y * np.sin(t)
        theta = center_theta + radius_theta * np.cos(t)
        r = body_surface.get_surface_radius(y, theta) + offset
        x = -np.sin(theta) * r
        z = np.cos(theta) * r
        vertices.append([x, y, z])

    # Fan triangulation from center
    faces = []
    for i in range(n):
        i1 = 1 + i
        i2 = 1 + (i + 1) % n
        faces.append([center_idx, i1, i2])

    mesh = trimesh.Trimesh(vertices=np.array(vertices),
                           faces=np.array(faces), process=False)
    color = [255, 80, 80, 180]
    mesh.visual.vertex_colors = np.tile(color, (len(vertices), 1))
    return mesh


def create_landmark_markers(lm, body_surface, radius=0.004):
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
    """Create camera pose looking at the body from given angle."""
    # Camera looks at (0, target_y, 0) from (distance * sin(az), target_y, distance * cos(az))
    eye = np.array([
        distance * np.sin(azimuth),
        target_y + distance * np.sin(elevation),
        distance * np.cos(azimuth),
    ])
    target = np.array([0, target_y, 0])
    up = np.array([0, 1, 0])

    # Look-at matrix
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

    print("Creating bikini bottom mesh...")
    bottom_outline = make_bikini_bottom_outline(lm, body_surface)
    bottom_mesh = create_panel_mesh(body_surface, bottom_outline, n_grid=50)

    print("Creating breast zone meshes...")
    left_breast = create_breast_zone_mesh(
        body_surface, lm["left_breast_apex"][1],
        np.arctan2(-lm["left_breast_apex"][0], lm["left_breast_apex"][2]),
        0.04, 0.5)
    right_breast = create_breast_zone_mesh(
        body_surface, lm["right_breast_apex"][1],
        np.arctan2(-lm["right_breast_apex"][0], lm["right_breast_apex"][2]),
        0.04, 0.5)

    print("Creating landmark markers...")
    markers = create_landmark_markers(lm, body_surface)

    # Build pyrender scene
    scene = pyrender.Scene(bg_color=[10, 10, 30, 255],
                           ambient_light=[0.3, 0.3, 0.3])

    # Add body
    body_pr = pyrender.Mesh.from_trimesh(body_mesh, smooth=True)
    scene.add(body_pr)

    # Add bikini panels
    if bottom_mesh is not None:
        bottom_pr = pyrender.Mesh.from_trimesh(bottom_mesh, smooth=False)
        scene.add(bottom_pr)

    for bm in [left_breast, right_breast]:
        if bm is not None:
            scene.add(pyrender.Mesh.from_trimesh(bm, smooth=False))

    for m in markers:
        scene.add(pyrender.Mesh.from_trimesh(m, smooth=False))

    # Camera setup: orthographic for consistent scale across views
    camera = pyrender.OrthographicCamera(xmag=0.35, ymag=0.55)
    cam_node = scene.add(camera, pose=np.eye(4))

    # Lighting
    light = pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=4.0)
    light_pose = make_camera_pose(azimuth=0.3, elevation=0.3, distance=2.0)
    scene.add(light, pose=light_pose)

    # Add fill light from opposite side
    fill_light = pyrender.DirectionalLight(color=[0.7, 0.7, 0.8], intensity=2.0)
    fill_pose = make_camera_pose(azimuth=np.pi + 0.5, elevation=0.2, distance=2.0)
    scene.add(fill_light, pose=fill_pose)

    # Render views
    W, H = 600, 900
    renderer = pyrender.OffscreenRenderer(W, H)

    views = [
        (0, "Front View"),
        (np.pi / 3, "Side View (60\u00b0)"),
        (np.pi, "Back View"),
    ]

    images = []
    for azimuth, title in views:
        cam_pose = make_camera_pose(azimuth=azimuth, distance=1.8, target_y=1.05)
        img = render_view(scene, cam_node, cam_pose, renderer)
        images.append((img, title))
        print(f"  Rendered {title}")

    renderer.delete()

    # Combine views into one image with titles
    from PIL import ImageDraw, ImageFont
    combined_w = W * 3 + 20
    combined_h = H + 60
    combined = Image.new('RGBA', (combined_w, combined_h), (10, 10, 30, 255))
    draw = ImageDraw.Draw(combined)

    # Title
    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except IOError:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((combined_w // 2 - 150, 5), "Privacy Zones & Key Landmarks",
              fill=(255, 255, 255), font=font_big)

    for i, (img, title) in enumerate(images):
        pil_img = Image.fromarray(img)
        x_offset = i * (W + 10)
        combined.paste(pil_img, (x_offset, 50))
        draw.text((x_offset + W // 2 - 40, 32), title,
                  fill=(255, 255, 255), font=font_small)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "privacy_zones_debug.png")
    combined.save(out_path)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
