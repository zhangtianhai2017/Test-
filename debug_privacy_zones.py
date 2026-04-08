"""Generate debug image marking privacy zone positions on the body.

Privacy zones are drawn as 3D curves on the body surface.
The bikini bottom is one continuous piece: front panel + crotch strip + back panel,
all flush against skin.
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
    """Render body with painter's algorithm. Returns rotate function."""
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
    return rotate


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
    """Create one continuous bikini bottom: front panel + crotch strip + back panel.

    The outline is a single closed loop in (Y, theta) space, projected
    onto the body surface. The crotch strip wraps between the legs from
    front to back, flush against skin.

    Outline traversal (clockwise from front top-left):
    1. Front top edge (left to right)
    2. Right leg scoop (down to front crotch)
    3. Right edge of crotch strip (front to back, between legs)
    4. Back right leg scoop (up from crotch to back top)
    5. Back top edge (right to left, viewed from back)
    6. Back left leg scoop (down to back crotch)
    7. Left edge of crotch strip (back to front, between legs)
    8. Front left leg scoop (up to front top-left)
    """
    hip_side_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2  # 0.976
    crotch_y = lm["crotch_center"][1]  # 0.781

    # Slightly smaller overall: top at hip - 3cm
    top_y = hip_side_y - 0.03  # 0.946

    # Front panel half-width at top: 5.5cm (smaller)
    hw_front = 0.055
    # Back panel half-width at top: 5cm
    hw_back = 0.050
    # Crotch strip half-width: 1.5cm
    hw_crotch = 0.015

    def theta_for_hw(hw, y, theta_center):
        """Convert physical half-width (m) to angular half-width."""
        r = body_surface.get_surface_radius(y, theta_center)
        return hw / max(r, 0.01)

    # Angular half-widths at key locations
    thf = theta_for_hw(hw_front, top_y, 0.0)         # front top
    thb = theta_for_hw(hw_back, top_y, np.pi)         # back top
    thc_f = theta_for_hw(hw_crotch, crotch_y, 0.0)    # crotch front
    thc_b = theta_for_hw(hw_crotch, crotch_y, np.pi)  # crotch back

    outline = []

    # --- 1. FRONT TOP EDGE (left to right) ---
    n_top = 15
    for i in range(n_top + 1):
        frac = i / n_top
        theta = thf * (1 - 2 * frac)  # +thf to -thf
        bow = 0.004 * np.sin(np.pi * frac)
        outline.append((top_y + bow, theta))

    # --- 2. RIGHT LEG SCOOP (top-right to front crotch-right) ---
    scoop_frac = 0.35
    scoop_y = top_y - (top_y - crotch_y) * scoop_frac
    scoop_depth = thf * 0.55
    p0 = (top_y, -thf)
    p3 = (crotch_y, -thc_f)
    p1 = (scoop_y, -thf + scoop_depth)
    p2 = (crotch_y + 0.03, -thc_f * 1.5)
    outline.extend(cubic_bezier(p0, p1, p2, p3, n=25)[1:])

    # --- 3. RIGHT CROTCH STRIP EDGE (front to back, between legs) ---
    # theta_center sweeps from 0 (front) to pi (back)
    # right edge = theta_center - offset
    n_crotch = 25
    for i in range(n_crotch + 1):
        frac = i / n_crotch
        theta_center = np.pi * frac  # 0 → pi
        offset = theta_for_hw(hw_crotch, crotch_y, theta_center)
        theta = theta_center - offset  # right edge
        # Slight Y dip at midpoint (between legs, lowest point)
        y_dip = -0.008 * np.sin(np.pi * frac)
        outline.append((crotch_y + y_dip, theta))

    # --- 4. BACK RIGHT LEG SCOOP (crotch up to back top-right) ---
    # From (crotch_y, pi - thc_b) up to (top_y, pi - thb)
    scoop_y_b = top_y - (top_y - crotch_y) * scoop_frac
    scoop_depth_b = thb * 0.55
    p0 = (crotch_y, np.pi - thc_b)
    p3 = (top_y, np.pi - thb)
    p1 = (crotch_y + 0.03, np.pi - thc_b * 1.5)
    p2 = (scoop_y_b, np.pi - thb + scoop_depth_b)
    outline.extend(cubic_bezier(p0, p1, p2, p3, n=25)[1:])

    # --- 5. BACK TOP EDGE (right to left, at theta ~ pi) ---
    for i in range(n_top + 1):
        frac = i / n_top
        theta = np.pi - thb + 2 * thb * frac  # pi-thb to pi+thb
        bow = 0.004 * np.sin(np.pi * frac)
        outline.append((top_y + bow, theta))

    # --- 6. BACK LEFT LEG SCOOP (back top-left down to crotch) ---
    p0 = (top_y, np.pi + thb)
    p3 = (crotch_y, np.pi + thc_b)
    p1 = (scoop_y_b, np.pi + thb - scoop_depth_b)
    p2 = (crotch_y + 0.03, np.pi + thc_b * 1.5)
    outline.extend(cubic_bezier(p0, p1, p2, p3, n=25)[1:])

    # --- 7. LEFT CROTCH STRIP EDGE (back to front, between legs) ---
    # theta_center sweeps from pi (back) to 0 (front)
    # left edge = theta_center + offset
    for i in range(n_crotch + 1):
        frac = i / n_crotch
        theta_center = np.pi * (1 - frac)  # pi → 0
        offset = theta_for_hw(hw_crotch, crotch_y, theta_center)
        theta = theta_center + offset  # left edge
        y_dip = -0.008 * np.sin(np.pi * frac)
        outline.append((crotch_y + y_dip, theta))

    # --- 8. FRONT LEFT LEG SCOOP (crotch up to front top-left) ---
    p0 = (crotch_y, thc_f)
    p3 = (top_y, thf)
    p1 = (crotch_y + 0.03, thc_f * 1.5)
    p2 = (scoop_y, thf - scoop_depth)
    outline.extend(cubic_bezier(p0, p1, p2, p3, n=25)[1:])

    return outline


def draw_surface_zone(ax, rotate_fn, pts3d, color, label, label_offset_y=0.02,
                      fill=False):
    """Draw a 3D surface curve projected to 2D view."""
    rpts = rotate_fn(pts3d)

    # Close the loop
    xs = np.append(rpts[:, 0], rpts[0, 0])
    ys = np.append(rpts[:, 1], rpts[0, 1])
    z_vals = np.append(rpts[:, 2], rpts[0, 2])

    # Draw segments where vertices face the camera
    visible = z_vals > -0.02
    i = 0
    drawn_any = False
    while i < len(xs) - 1:
        if visible[i] and visible[i + 1]:
            seg_x = [xs[i]]
            seg_y = [ys[i]]
            while i < len(xs) - 1 and visible[i] and visible[i + 1]:
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

    # Optional fill
    if fill:
        visible_mask = rpts[:, 2] > -0.02
        if visible_mask.sum() > 2:
            vis_pts = rpts[visible_mask]
            ax.fill(vis_pts[:, 0], vis_pts[:, 1], color=color,
                    alpha=0.15, zorder=45)

    # Label at top of visible area
    visible_mask = rpts[:, 2] > -0.02
    if visible_mask.sum() > 0:
        vis_pts = rpts[visible_mask]
        center_x = vis_pts[:, 0].mean()
        top_y_val = vis_pts[:, 1].max()
        ax.annotate(label, (center_x, top_y_val + label_offset_y),
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

    # Breast zones (elliptical)
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

    # One continuous bikini bottom (front + crotch strip + back)
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
        rotate = render_body(ax, body_verts, body_faces, azimuth, title)

        # Draw breast zones
        for zone, pts3d in zip(breast_zones, breast_curves):
            draw_surface_zone(ax, rotate, pts3d, zone["color"], zone["name"],
                              fill=True)

        # Draw bikini bottom (one continuous piece)
        draw_surface_zone(ax, rotate, bottom_3d, '#ff4444',
                          'BIKINI BOTTOM', fill=True)

        # Draw landmarks
        for lm_name, (color, marker) in key_landmarks.items():
            pt3d = np.array([lm[lm_name]])
            rpt = rotate(pt3d)[0]

            if rpt[2] > -0.03:
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
