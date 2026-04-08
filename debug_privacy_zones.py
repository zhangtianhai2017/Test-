"""Generate debug image marking privacy zone positions on the body.

Privacy zones are drawn as 3D curves on the body surface, not flat 2D ellipses.
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


def sample_surface_ellipse(body_surface, center_y, center_theta,
                           radius_y, radius_theta, n_pts=80, offset=0.002):
    """Sample a closed curve on the body surface around a center point.

    The ellipse is defined in (Y, theta) parameter space, then each point
    is placed on the body surface at the correct 3D radius.

    Returns: (n_pts, 3) array of 3D points on the body surface.
    """
    pts = np.zeros((n_pts, 3))
    for i in range(n_pts):
        t = 2 * np.pi * i / n_pts
        # Parametric ellipse in (Y, theta) space
        dy = radius_y * np.sin(t)
        dtheta = radius_theta * np.cos(t)

        y = center_y + dy
        theta = center_theta + dtheta

        # Get body surface radius at this (y, theta)
        r = body_surface.get_surface_radius(y, theta) + offset

        # Convert cylindrical to cartesian
        # theta: 0=+Z (front), pi/2=-X (left), pi=-Z (back)
        x = -np.sin(theta) * r
        z = np.cos(theta) * r

        pts[i] = [x, y, z]
    return pts


def draw_surface_zone(ax, rotate_fn, pts3d, color, label, label_offset_y=0.02):
    """Draw a 3D surface curve projected to 2D view."""
    rpts = rotate_fn(pts3d)

    # Use the average z to determine visibility
    avg_z = rpts[:, 2].mean()
    if avg_z < -0.05:
        return  # behind body in this view

    # Close the loop
    xs = np.append(rpts[:, 0], rpts[0, 0])
    ys = np.append(rpts[:, 1], rpts[0, 1])

    # Only draw segments that face the camera (z > threshold)
    # Split into visible segments
    z_vals = np.append(rpts[:, 2], rpts[0, 2])
    visible = z_vals > -0.02

    # Draw visible segments
    i = 0
    while i < len(xs) - 1:
        if visible[i] and visible[i + 1]:
            # Find contiguous visible segment
            seg_x = [xs[i]]
            seg_y = [ys[i]]
            while i < len(xs) - 1 and visible[i] and visible[i + 1]:
                seg_x.append(xs[i + 1])
                seg_y.append(ys[i + 1])
                i += 1
            ax.plot(seg_x, seg_y, color=color, linewidth=2.5,
                    linestyle='--', zorder=50, alpha=0.9)
        else:
            i += 1

    # Label at top of zone
    center_2d = rpts[:, :2].mean(axis=0)
    top_y = rpts[:, 1].max()
    ax.annotate(label, (center_2d[0], top_y + label_offset_y),
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

    # Privacy zone definitions:
    # center_y, center_theta, radius_y, radius_theta
    # theta: 0=front(+Z), pi=back(-Z)
    #
    # The actual pubic privacy center is around pubic_top/crotch_front,
    # NOT at crotch_center (which is the very bottom between legs).
    pubic_center_y = (lm["pubic_top"][1] + lm["crotch_front"][1]) / 2  # ~0.855
    privacy_zones = [
        {
            "name": "LEFT BREAST",
            "center_y": lm["left_breast_apex"][1],  # 1.298
            "center_theta": np.arctan2(-lm["left_breast_apex"][0],
                                        lm["left_breast_apex"][2]),
            "radius_y": 0.04,
            "radius_theta": 0.5,  # ~30 degrees
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
        {
            "name": "PUBIC AREA",
            "center_y": pubic_center_y,
            "center_theta": 0.0,  # front center
            "radius_y": 0.04,  # ~4cm up/down from center
            "radius_theta": 0.35,  # ~20 degrees left/right
            "color": "#ff4444",
        },
        {
            "name": "BUTTOCK CREASE",
            "center_y": (lm["buttock_crease_left"][1] + lm["buttock_crease_right"][1]) / 2,
            "center_theta": np.pi,  # back center
            "radius_y": 0.04,
            "radius_theta": 0.5,
            "color": "#ff6666",
        },
    ]

    # Pre-sample all zone curves in 3D
    zone_curves = []
    for zone in privacy_zones:
        pts = sample_surface_ellipse(
            body_surface,
            zone["center_y"], zone["center_theta"],
            zone["radius_y"], zone["radius_theta"],
        )
        zone_curves.append(pts)

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

        # Draw privacy zones as 3D curves on body surface
        for zone, pts3d in zip(privacy_zones, zone_curves):
            draw_surface_zone(ax, rotate, pts3d, zone["color"], zone["name"])

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
