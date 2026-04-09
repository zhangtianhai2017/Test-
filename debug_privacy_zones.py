"""Generate debug image marking privacy zones using proper 3D rendering.

Approach: extract body mesh faces at privacy zones, extrude outward 2mm.
Fabric = body skin surface + offset along vertex normals.
Guarantees perfect body conformity — fabric literally IS the skin, pushed out.

Uses pyrender (OpenGL) with OSMesa for offscreen rendering.
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
# Extract body surface faces within a zone and extrude outward
# ---------------------------------------------------------------------------

def vertex_cylindrical(verts):
    """Convert vertices to cylindrical coords: (Y, theta).
    theta: 0=front(+Z), pi/2=left(-X), pi=back(-Z).
    """
    y = verts[:, 1]
    theta = np.arctan2(-verts[:, 0], verts[:, 2])
    theta[theta < 0] += 2 * np.pi
    return y, theta


def select_faces_in_zone(verts, faces, zone_path):
    """Select body mesh faces whose centroid falls inside a (Y, theta) zone.

    zone_path: MplPath in (Y, theta) space defining the zone boundary.
    Handles theta wrapping at the 0/2pi boundary (front of body).
    Returns face indices.
    """
    y, theta = vertex_cylindrical(verts)

    # Check if zone crosses the theta=0/2pi boundary
    zone_verts = zone_path.vertices
    has_negative_theta = np.any(zone_verts[:, 1] < 0)
    has_large_theta = np.any(zone_verts[:, 1] > 2 * np.pi - 0.1)

    # Face centroids in (Y, theta)
    fy = (y[faces[:, 0]] + y[faces[:, 1]] + y[faces[:, 2]]) / 3

    # For theta, handle wrapping carefully
    th0 = theta[faces[:, 0]].copy()
    th1 = theta[faces[:, 1]].copy()
    th2 = theta[faces[:, 2]].copy()

    if has_negative_theta:
        # Front zone: shift theta > pi to negative range
        th0[th0 > np.pi] -= 2 * np.pi
        th1[th1 > np.pi] -= 2 * np.pi
        th2[th2 > np.pi] -= 2 * np.pi

    fth = (th0 + th1 + th2) / 3

    points = np.column_stack([fy, fth])
    inside = zone_path.contains_points(points, radius=0.002)
    return np.where(inside)[0]


def extract_and_extrude(verts, faces, face_indices, thickness=0.002):
    """Extract faces from body mesh and extrude outward.

    Returns a trimesh with:
    - Outer surface (body surface + thickness along vertex normals)
    - Inner surface (original body surface)
    - Side faces connecting the edges
    """
    from collections import Counter

    if len(face_indices) == 0:
        return None

    # Collect unique vertices used by selected faces
    selected_faces = faces[face_indices]
    unique_vids = np.unique(selected_faces)
    vid_map = {old: new for new, old in enumerate(unique_vids)}

    # Remap faces
    new_faces = np.array([[vid_map[v] for v in f] for f in selected_faces])
    new_verts = verts[unique_vids].copy()
    n = len(new_verts)

    # Compute vertex normals (area-weighted from face normals)
    normals = np.zeros_like(new_verts)
    for f in new_faces:
        v0, v1, v2 = new_verts[f[0]], new_verts[f[1]], new_verts[f[2]]
        fn = np.cross(v1 - v0, v2 - v0)
        normals[f[0]] += fn
        normals[f[1]] += fn
        normals[f[2]] += fn
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals /= np.maximum(lengths, 1e-8)

    # Ensure normals point outward (away from Y-axis)
    radial = new_verts.copy()
    radial[:, 1] = 0
    dots = np.sum(normals * radial, axis=1)
    normals[dots < 0] *= -1

    # Outer surface = body surface + normal * thickness
    outer_verts = new_verts + normals * thickness
    all_verts = np.vstack([new_verts, outer_verts])

    # Inner faces (body surface, reversed winding so normals face inward)
    # Outer faces (extruded surface, original winding so normals face outward)
    inner_faces = new_faces[:, ::-1]  # reversed → normals face inward
    outer_faces = new_faces + n       # offset → outer surface

    all_faces_list = [inner_faces, outer_faces]

    # Side faces: connect boundary edges
    edge_count = Counter()
    for f in new_faces:
        for i in range(3):
            e = tuple(sorted([f[i], f[(i + 1) % 3]]))
            edge_count[e] += 1

    side_faces = []
    for (a, b), c in edge_count.items():
        if c == 1:  # boundary edge
            side_faces.append([a, b, b + n])
            side_faces.append([a, b + n, a + n])

    if side_faces:
        all_faces_list.append(np.array(side_faces, dtype=np.int32))

    all_faces = np.vstack(all_faces_list)
    mesh = trimesh.Trimesh(vertices=all_verts, faces=all_faces, process=False)
    color = [255, 80, 80, 255]
    mesh.visual.vertex_colors = np.tile(color, (len(all_verts), 1))
    return mesh


# ---------------------------------------------------------------------------
# Zone outline definitions in (Y, theta) space
# ---------------------------------------------------------------------------

def make_front_panel_zone(lm):
    """Front panel: inverted triangle zone in (Y, theta) space."""
    hip_side_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2
    pubic_top_y = lm["pubic_top"][1]

    top_y = hip_side_y - 0.03
    bottom_y = pubic_top_y + 0.015
    hw_top = 0.065      # half-width at top in meters
    hw_bottom = 0.018   # half-width at bottom

    # Convert to theta using approximate body radius
    r_top = 0.10   # front body radius at hip level
    r_bot = 0.085  # front body radius at pubic level
    thf = hw_top / r_top
    thc = hw_bottom / r_bot

    # Inverted triangle with concave leg scoops
    outline = []

    # Top edge (slight bow)
    for i in range(20):
        f = i / 19
        theta = thf * (1 - 2 * f)
        bow = 0.004 * np.sin(np.pi * f)
        outline.append((top_y + bow, theta))

    # Right leg scoop (bezier)
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

    # Bottom edge
    for i in range(6):
        f = i / 5
        outline.append((bottom_y, -thc + 2 * thc * f))

    # Left leg scoop (bezier)
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
    """Back panel: inverted triangle zone on the back."""
    hip_side_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2
    pubic_top_y = lm["pubic_top"][1]

    top_y = hip_side_y - 0.03
    bottom_y = pubic_top_y + 0.015
    hw_top = 0.060
    hw_bottom = 0.018

    r_top = 0.10
    r_bot = 0.085
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


def select_crotch_strip_faces(verts, faces, lm, hw=0.018):
    """Select body mesh faces for the crotch strip by 3D position.

    The crotch strip goes BETWEEN the legs (sagittal plane, |X| < hw),
    from front panel bottom to back panel bottom.
    Can't use cylindrical theta — theta sweep goes around the side, not between legs.

    Selection: |X| < hw AND Y < panel_bottom AND Y > crotch_bottom
    """
    pubic_top_y = lm["pubic_top"][1]
    crotch_y = lm["crotch_center"][1]

    panel_bottom = pubic_top_y + 0.015  # 0.88
    y_bottom = crotch_y - 0.02          # ~0.76

    # Face centroids in 3D
    cx = (verts[faces[:, 0], 0] + verts[faces[:, 1], 0] + verts[faces[:, 2], 0]) / 3
    cy = (verts[faces[:, 0], 1] + verts[faces[:, 1], 1] + verts[faces[:, 2], 1]) / 3

    # Select faces: narrow X band, below panels, above bottom
    mask = (np.abs(cx) < hw) & (cy < panel_bottom) & (cy > y_bottom)
    return np.where(mask)[0]


def make_breast_zone(lm, side='left'):
    """Elliptical breast zone around the apex."""
    if side == 'left':
        apex = lm["left_breast_apex"]
    else:
        apex = lm["right_breast_apex"]

    center_y = apex[1]
    center_theta = np.arctan2(-apex[0], apex[2])
    if center_theta < 0:
        center_theta += 2 * np.pi

    radius_y = 0.04
    radius_theta = 0.5

    # Ellipse in (Y, theta) space
    n = 60
    outline = []
    for i in range(n):
        t = 2 * np.pi * i / n
        y = center_y + radius_y * np.sin(t)
        theta = center_theta + radius_theta * np.cos(t)
        outline.append((y, theta))
    outline.append(outline[0])  # close

    return MplPath(np.array(outline))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def create_body_mesh():
    """Load body mesh and create trimesh object."""
    verts, faces = generate_full_body()
    skin_color = [220, 185, 160, 255]
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    mesh.visual.vertex_colors = np.tile(skin_color, (len(verts), 1))
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
    body_mesh = create_body_mesh()
    lm = get_landmarks()

    # --- Define privacy zones ---
    print("Defining privacy zones...")
    yt_zones = {
        "front_panel": make_front_panel_zone(lm),
        "back_panel": make_back_panel_zone(lm),
        "left_breast": make_breast_zone(lm, 'left'),
        "right_breast": make_breast_zone(lm, 'right'),
    }

    # --- Extract body faces in each zone and extrude ---
    print("Extracting body surface and extruding fabric...")
    fabric_meshes = []

    # Zones defined in (Y, theta) space
    for name, zone_path in yt_zones.items():
        face_ids = select_faces_in_zone(body_verts, body_faces, zone_path)
        mesh = extract_and_extrude(body_verts, body_faces, face_ids,
                                    thickness=0.002)
        if mesh is not None:
            print(f"  {name}: {len(face_ids)} faces extracted")
            fabric_meshes.append(mesh)
        else:
            print(f"  {name}: WARNING - no faces found!")

    # Crotch strip: selected by 3D position (between legs, not around side)
    crotch_face_ids = select_crotch_strip_faces(body_verts, body_faces, lm)
    crotch_mesh = extract_and_extrude(body_verts, body_faces, crotch_face_ids,
                                       thickness=0.002)
    if crotch_mesh is not None:
        print(f"  crotch_strip: {len(crotch_face_ids)} faces extracted")
        fabric_meshes.append(crotch_mesh)
    else:
        print("  crotch_strip: WARNING - no faces found!")

    # --- Export OBJ ---
    print("Exporting OBJ file...")
    export_parts = [body_mesh] + fabric_meshes
    combined = trimesh.util.concatenate(export_parts)
    obj_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "privacy_zones_debug.obj")
    combined.export(obj_path, file_type='obj')
    print(f"Saved OBJ to {obj_path}")

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
              "Privacy Zones: Body Surface Extrusion (2mm)",
              fill=(255, 255, 255), font=font_big)

    for i, (img, title) in enumerate(images):
        pil_img = Image.fromarray(img)
        x_offset = i * (W + gap)
        combined_img.paste(pil_img, (x_offset, 50))
        draw.text((x_offset + W // 2 - 30, 34), title,
                  fill=(255, 255, 255), font=font_small)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "privacy_zones_debug.png")
    combined_img.save(out_path)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
