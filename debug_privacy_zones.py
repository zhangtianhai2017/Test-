"""Generate debug image marking privacy zone positions on the body."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.patches import Ellipse

from bikini_generator.body.mannequin import generate_full_body
from bikini_generator.body.landmarks import get_landmarks


def render_body(ax, body_verts, body_faces, azimuth=0, title=""):
    """Render body with painter's algorithm."""
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


def main():
    body_verts, body_faces = generate_full_body()
    lm = get_landmarks()

    fig, axes = plt.subplots(1, 3, figsize=(18, 10))
    fig.patch.set_facecolor('#0a0a1a')
    fig.suptitle('Privacy Zones & Key Landmarks', color='white', fontsize=16, y=0.96)

    views = [
        (axes[0], 0, "Front View"),
        (axes[1], np.pi/3, "Side View (60°)"),
        (axes[2], np.pi, "Back View"),
    ]

    # Define privacy zones and landmarks to mark
    privacy_zones = [
        ("LEFT BREAST", lm["left_breast_apex"], 'red', 0.08, 0.08),
        ("RIGHT BREAST", lm["right_breast_apex"], 'red', 0.08, 0.08),
        ("CROTCH CENTER", lm["crotch_center"], 'red', 0.07, 0.10),
    ]

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

        # Draw privacy zone ellipses
        for name, center, color, rx, ry in privacy_zones:
            pt3d = np.array([center])
            rpt = rotate(pt3d)[0]

            # Only draw if facing this view
            if rpt[2] > -0.05:  # not behind
                ellipse = Ellipse(
                    (rpt[0], rpt[1]), rx * 2, ry * 2,
                    fill=False, edgecolor=color, linewidth=2.5,
                    linestyle='--', zorder=50, alpha=0.9,
                )
                ax.add_patch(ellipse)
                ax.annotate(name, (rpt[0], rpt[1] + ry + 0.01),
                            color=color, fontsize=7, ha='center',
                            fontweight='bold', zorder=51,
                            bbox=dict(boxstyle='round,pad=0.2',
                                      facecolor='black', alpha=0.7))

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
