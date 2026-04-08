"""Generate debug image marking privacy zone positions on the body.

Privacy zones are drawn as 3D curves on the body surface.
The bikini bottom is one continuous piece: front panel + crotch strip + back panel.
Fabric is clipped to the body silhouette so it never shows over background.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

from bikini_generator.body.mannequin import generate_full_body
from bikini_generator.body.landmarks import get_landmarks
from bikini_generator.garment.loop_generator import BodySurface


def render_body(ax, body_verts, body_faces, azimuth=0, title=""):
    """Render body with painter's algorithm. Returns (rotate_fn, silhouette)."""
    cos_a, sin_a = np.cos(azimuth), np.sin(azimuth)

    def rotate(v):
        x = v[:, 0] * cos_a - v[:, 2] * sin_a
        z = v[:, 0] * sin_a + v[:, 2] * cos_a
        return np.column_stack([x, v[:, 1], z])

    ax.set_xlim(-0.30, 0.30)
    ax.set_ylim(0.55, 1.60)
    ax.set_aspect('equal')
    ax.set_facecolor('#1a1a2e')
    ax.set_title(title, fontsize=10, color='white', pad=4)
    ax.tick_params(labelsize=6, colors='#555')

    light_dir = np.array([0.3, 0.5, 0.8])
    light_dir /= np.linalg.norm(light_dir)

    rv = rotate(body_verts)
    tris = rv[body_faces]
    centroids_z = tris[:, :, 2].mean(axis=1)

    e1 = tris[:, 1] - tris[:, 0]
    e2 = tris[:, 2] - tris[:, 0]
    normals = np.cross(e1, e2)
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    norms[norms < 1e-10] = 1e-10
    normals /= norms

    dots = np.einsum('ij,j->i', normals, light_dir)
    intensity = np.clip(dots * 0.6 + 0.4, 0.15, 1.0)

    body_xy = tris[:, :, :2]
    body_colors = np.zeros((len(tris), 4))
    body_colors[:, 0] = 0.85 * intensity
    body_colors[:, 1] = 0.72 * intensity
    body_colors[:, 2] = 0.62 * intensity
    body_colors[:, 3] = 1.0

    order = np.argsort(centroids_z)
    pc = PolyCollection(body_xy[order], facecolors=body_colors[order],
                        edgecolors='none', zorder=1)
    ax.add_collection(pc)

    # Build body silhouette: for each Y bin, find min/max X of front-facing verts
    front_mask = rv[:, 2] > -0.01
    front_verts = rv[front_mask]
    silhouette = build_silhouette(front_verts[:, 0], front_verts[:, 1],
                                  y_min=0.55, y_max=1.60, n_bins=500)

    return rotate, silhouette


def build_silhouette(xs, ys, y_min, y_max, n_bins=500):
    """Build body silhouette as (y_bin -> (min_x, max_x)).

    Returns a function: is_inside(x, y) -> bool
    """
    bin_edges = np.linspace(y_min, y_max, n_bins + 1)
    bin_min_x = np.full(n_bins, np.inf)
    bin_max_x = np.full(n_bins, -np.inf)

    bin_idx = np.clip(((ys - y_min) / (y_max - y_min) * n_bins).astype(int),
                      0, n_bins - 1)
    for i in range(len(xs)):
        bi = bin_idx[i]
        if xs[i] < bin_min_x[bi]:
            bin_min_x[bi] = xs[i]
        if xs[i] > bin_max_x[bi]:
            bin_max_x[bi] = xs[i]

    # Expand bins slightly for margin
    margin = 0.003
    valid = bin_min_x < np.inf
    bin_min_x[valid] -= margin
    bin_max_x[valid] += margin

    def is_inside(x, y):
        bi = int((y - y_min) / (y_max - y_min) * n_bins)
        if bi < 0 or bi >= n_bins:
            return False
        if bin_min_x[bi] == np.inf:
            return False
        return bin_min_x[bi] <= x <= bin_max_x[bi]

    return is_inside


def sample_surface_points(body_surface, yt_points, offset=0.002):
    """Convert (Y, theta) points to 3D body surface positions."""
    pts = np.zeros((len(yt_points), 3))
    for i, (y, theta) in enumerate(yt_points):
        r = body_surface.get_surface_radius(y, theta) + offset
        x = -np.sin(theta) * r
        z = np.cos(theta) * r
        pts[i] = [x, y, z]
    return pts


def sample_surface_ellipse(body_surface, center_y, center_theta,
                           radius_y, radius_theta, n_pts=80, offset=0.002):
    """Sample elliptical curve on body surface (for breast zones)."""
    yt = []
    for i in range(n_pts):
        t = 2 * np.pi * i / n_pts
        dy = radius_y * np.sin(t)
        dtheta = radius_theta * np.cos(t)
        yt.append((center_y + dy, center_theta + dtheta))
    return sample_surface_points(body_surface, yt, offset)


def cubic_bezier(p0, p1, p2, p3, n=20):
    """Sample cubic bezier curve, returns list of (y, theta) points."""
    pts = []
    for i in range(n + 1):
        t = i / n
        t2 = t * t
        t3 = t2 * t
        mt = 1 - t
        mt2 = mt * mt
        mt3 = mt2 * mt
        y = mt3 * p0[0] + 3 * mt2 * t * p1[0] + 3 * mt * t2 * p2[0] + t3 * p3[0]
        th = mt3 * p0[1] + 3 * mt2 * t * p1[1] + 3 * mt * t2 * p2[1] + t3 * p3[1]
        pts.append((y, th))
    return pts


def make_bikini_bottom(lm, body_surface):
    """Create one continuous bikini bottom: front + crotch strip + back.

    Front panel covers the pubic area on the FRONT of the body.
    Its bottom edge is at crotch_front level (~Y=0.84), NOT at crotch_center.
    Only the narrow crotch strip goes down between the legs.

    Outline traversal (clockwise from front top-left):
    1. Front top edge
    2. Right leg scoop (down to front panel bottom)
    3. Right crotch strip edge (front panel bottom → crotch_center → back panel bottom)
    4. Back right leg scoop (up)
    5. Back top edge
    6. Back left leg scoop (down)
    7. Left crotch strip edge (back → crotch_center → front)
    8. Front left leg scoop (up)
    """
    hip_side_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2
    crotch_front_y = lm["crotch_front"][1]  # 0.846 — where front meets crotch
    crotch_back_y = lm["crotch_back"][1]    # 0.849
    crotch_center_y = lm["crotch_center"][1]  # 0.781 — lowest point between legs

    top_y = hip_side_y - 0.03  # 0.946
    # Front panel bottom: at crotch fold, not between legs
    front_bottom_y = crotch_front_y - 0.01  # 0.836
    back_bottom_y = crotch_back_y - 0.01    # 0.839

    hw_front = 0.055
    hw_back = 0.050
    hw_crotch = 0.015

    def theta_hw(hw, y, tc):
        r = body_surface.get_surface_radius(y, tc)
        return hw / max(r, 0.01)

    thf = theta_hw(hw_front, top_y, 0.0)
    thb = theta_hw(hw_back, top_y, np.pi)
    # Crotch strip width at front/back panel bottoms (on body surface)
    thc_f = theta_hw(hw_crotch, front_bottom_y, 0.0)
    thc_b = theta_hw(hw_crotch, back_bottom_y, np.pi)
    # Crotch strip width at the lowest point (between legs)
    thc_mid = theta_hw(hw_crotch, crotch_center_y, np.pi / 2)

    outline = []

    # 1. Front top edge
    for i in range(16):
        f = i / 15
        theta = thf * (1 - 2 * f)
        bow = 0.004 * np.sin(np.pi * f)
        outline.append((top_y + bow, theta))

    # 2. Right leg scoop (top-right → front panel bottom-right)
    sy = top_y - (top_y - front_bottom_y) * 0.4
    sd = thf * 0.55
    outline.extend(cubic_bezier(
        (top_y, -thf), (sy, -thf + sd),
        (front_bottom_y + 0.02, -thc_f * 1.5), (front_bottom_y, -thc_f),
        n=25)[1:])

    # 3. Right crotch strip edge (front bottom → dip to crotch_center → back bottom)
    # The strip dips from front_bottom_y down to crotch_center_y and back up to back_bottom_y
    n_crotch = 30
    for i in range(n_crotch + 1):
        f = i / n_crotch
        # theta goes from 0 (front) to pi (back)
        tc = np.pi * f
        # Y: smooth dip from front_bottom_y → crotch_center_y → back_bottom_y
        # Use a sine curve to dip at the midpoint
        y_start = front_bottom_y
        y_end = back_bottom_y
        y_baseline = y_start + (y_end - y_start) * f
        dip_depth = y_baseline - crotch_center_y
        dip = -dip_depth * np.sin(np.pi * f)
        y_here = y_baseline + dip
        off = theta_hw(hw_crotch, max(y_here, crotch_center_y), tc)
        outline.append((y_here, tc - off))

    # 4. Back right leg scoop (back bottom → back top-right)
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

    # 7. Left crotch strip edge (back → crotch_center → front)
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


def draw_surface_zone_clipped(ax, rotate_fn, silhouette, pts3d, color, label,
                              label_offset_y=0.02):
    """Draw 3D surface curve clipped to body silhouette.

    Only segments where BOTH endpoints project inside the body silhouette
    are drawn. This prevents fabric from appearing over background.
    """
    rpts = rotate_fn(pts3d)

    # Close the loop
    n = len(rpts)
    xs = np.append(rpts[:, 0], rpts[0, 0])
    ys = np.append(rpts[:, 1], rpts[0, 1])
    zs = np.append(rpts[:, 2], rpts[0, 2])

    # Check each point: must face camera AND be inside body silhouette
    inside = np.zeros(n + 1, dtype=bool)
    for i in range(n + 1):
        if zs[i] > -0.02 and silhouette(xs[i], ys[i]):
            inside[i] = True

    # Draw visible+inside segments
    drawn_any = False
    i = 0
    while i < n:
        if inside[i] and inside[i + 1]:
            seg_x = [xs[i]]
            seg_y = [ys[i]]
            while i < n and inside[i] and inside[i + 1]:
                seg_x.append(xs[i + 1])
                seg_y.append(ys[i + 1])
                i += 1
            ax.plot(seg_x, seg_y, color=color, linewidth=2.5,
                    linestyle='--', zorder=50, alpha=0.9)
            drawn_any = True
        else:
            i += 1

    if not drawn_any:
        return

    # Fill only inside-silhouette points
    inside_pts = rpts[[silhouette(rpts[j, 0], rpts[j, 1]) and rpts[j, 2] > -0.02
                        for j in range(n)]]
    if len(inside_pts) > 2:
        ax.fill(inside_pts[:, 0], inside_pts[:, 1], color=color,
                alpha=0.2, zorder=45)

    # Label
    if len(inside_pts) > 0:
        cx = inside_pts[:, 0].mean()
        ty = inside_pts[:, 1].max()
        ax.annotate(label, (cx, ty + label_offset_y),
                    color=color, fontsize=7, ha='center',
                    fontweight='bold', zorder=51,
                    bbox=dict(boxstyle='round,pad=0.2',
                              facecolor='black', alpha=0.7))


def main():
    body_verts, body_faces = generate_full_body()
    lm = get_landmarks()
    body_surface = BodySurface()

    fig, axes = plt.subplots(1, 3, figsize=(18, 10))
    fig.patch.set_facecolor('#0a0a1a')
    fig.suptitle('Privacy Zones & Key Landmarks', color='white', fontsize=16, y=0.96)

    views = [
        (axes[0], 0, "Front View"),
        (axes[1], np.pi / 3, "Side View (60\u00b0)"),
        (axes[2], np.pi, "Back View"),
    ]

    # Breast zones
    breast_zones = [
        {
            "name": "LEFT BREAST",
            "center_y": lm["left_breast_apex"][1],
            "center_theta": np.arctan2(-lm["left_breast_apex"][0],
                                        lm["left_breast_apex"][2]),
            "radius_y": 0.04,
            "radius_theta": 0.5,
            "color": "red",
        },
        {
            "name": "RIGHT BREAST",
            "center_y": lm["right_breast_apex"][1],
            "center_theta": np.arctan2(-lm["right_breast_apex"][0],
                                        lm["right_breast_apex"][2]),
            "radius_y": 0.04,
            "radius_theta": 0.5,
            "color": "red",
        },
    ]

    breast_curves = []
    for zone in breast_zones:
        pts = sample_surface_ellipse(
            body_surface,
            zone["center_y"], zone["center_theta"],
            zone["radius_y"], zone["radius_theta"],
        )
        breast_curves.append(pts)

    # One continuous bikini bottom
    bottom_yt = make_bikini_bottom(lm, body_surface)
    bottom_3d = sample_surface_points(body_surface, bottom_yt)

    key_landmarks = {
        "neck_front": ('cyan', 'v'),
        "sternum_top": ('cyan', 'v'),
        "left_breast_apex": ('red', '*'),
        "right_breast_apex": ('red', '*'),
        "left_breast_outer": ('orange', 'o'),
        "right_breast_outer": ('orange', 'o'),
        "left_breast_inner": ('orange', 'o'),
        "right_breast_inner": ('orange', 'o'),
        "left_underbust": ('yellow', '^'),
        "right_underbust": ('yellow', '^'),
        "waist_front": ('lime', 's'),
        "hip_front": ('lime', 's'),
        "hip_left": ('lime', 's'),
        "hip_right": ('lime', 's'),
        "hip_back": ('lime', 's'),
        "pubic_top": ('magenta', 'D'),
        "crotch_front": ('magenta', 'D'),
        "crotch_center": ('red', '*'),
        "crotch_back": ('magenta', 'D'),
        "left_buttock_apex": ('orange', 'o'),
        "right_buttock_apex": ('orange', 'o'),
        "buttock_crease_left": ('yellow', '^'),
        "buttock_crease_right": ('yellow', '^'),
    }

    for ax, azimuth, title in views:
        rotate, silhouette = render_body(ax, body_verts, body_faces, azimuth, title)

        # Draw breast zones (clipped to body)
        for zone, pts3d in zip(breast_zones, breast_curves):
            draw_surface_zone_clipped(ax, rotate, silhouette, pts3d,
                                      zone["color"], zone["name"])

        # Draw bikini bottom (clipped to body silhouette)
        draw_surface_zone_clipped(ax, rotate, silhouette, bottom_3d,
                                  '#ff4444', 'BIKINI BOTTOM')

        # Draw landmarks
        for lm_name, (color, marker) in key_landmarks.items():
            pt3d = np.array([lm[lm_name]])
            rpt = rotate(pt3d)[0]
            if rpt[2] > -0.03 and silhouette(rpt[0], rpt[1]):
                ax.scatter(rpt[0], rpt[1], c=color, marker=marker,
                           s=40, zorder=30, edgecolors='white',
                           linewidths=0.5, alpha=0.9)
                ax.annotate(lm_name, (rpt[0] + 0.01, rpt[1]),
                            color=color, fontsize=5, zorder=31,
                            alpha=0.8)

        # Draw Y reference lines
        for label, y_val, color in [
            ("breast apex Y", lm["left_breast_apex"][1], 'red'),
            ("underbust Y", lm["left_underbust"][1], 'yellow'),
            ("waist Y", lm["waist_front"][1], 'lime'),
            ("hip Y", lm["hip_front"][1], 'lime'),
            ("pubic top Y", lm["pubic_top"][1], 'magenta'),
            ("crotch front Y", lm["crotch_front"][1], '#ff4444'),
            ("crotch center Y", lm["crotch_center"][1], 'red'),
        ]:
            ax.axhline(y=y_val, color=color, linewidth=0.5,
                       linestyle=':', alpha=0.4, zorder=5)
            ax.text(0.22, y_val + 0.005, f"{label} ({y_val:.3f})",
                    color=color, fontsize=5, alpha=0.6, zorder=6)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    out_path = os.path.join(os.path.dirname(__file__), "privacy_zones_debug.png")
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
