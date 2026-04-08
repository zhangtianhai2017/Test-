"""Test physics simulation with corrected anchors — no shape_retention.

Generates before/after comparison showing natural cloth drape under gravity.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

def render_view(ax, body_verts, body_faces, patches, patch_colors, title,
                azimuth=0, show_anchors=False):
    """Render a single view with painter's algorithm."""
    # Rotation
    cos_a, sin_a = np.cos(azimuth), np.sin(azimuth)
    def rotate(v):
        x = v[:, 0] * cos_a - v[:, 2] * sin_a
        z = v[:, 0] * sin_a + v[:, 2] * cos_a
        return np.column_stack([x, v[:, 1], z])

    ax.set_xlim(-0.25, 0.25)
    ax.set_ylim(0.6, 1.55)
    ax.set_aspect('equal')
    ax.set_facecolor('#1a1a2e')
    ax.set_title(title, fontsize=7, color='white', pad=2)
    ax.tick_params(labelsize=5, colors='#555')

    # Light direction
    light_dir = np.array([0.3, 0.5, 0.8])
    light_dir /= np.linalg.norm(light_dir)

    # Body
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

    # Garment patches
    for patch, color in zip(patches, patch_colors):
        if len(patch.faces) == 0:
            continue
        pv = rotate(patch.vertices)
        ptris = pv[patch.faces]
        pz = ptris[:, :, 2].mean(axis=1)

        pe1 = ptris[:, 1] - ptris[:, 0]
        pe2 = ptris[:, 2] - ptris[:, 0]
        pn = np.cross(pe1, pe2)
        pnorm = np.linalg.norm(pn, axis=1, keepdims=True)
        pnorm[pnorm < 1e-10] = 1e-10
        pn /= pnorm

        pdots = np.einsum('ij,j->i', pn, light_dir)
        pint = np.clip(pdots * 0.5 + 0.5, 0.2, 1.0)

        pxy = ptris[:, :, :2]
        pc_colors = np.zeros((len(ptris), 4))
        pc_colors[:, 0] = color[0] * pint
        pc_colors[:, 1] = color[1] * pint
        pc_colors[:, 2] = color[2] * pint
        pc_colors[:, 3] = 0.9

        porder = np.argsort(pz)
        pc2 = PolyCollection(pxy[porder], facecolors=pc_colors[porder],
                             edgecolors='none', zorder=2)
        ax.add_collection(pc2)

        # Show anchor points
        if show_anchors and hasattr(patch, 'anchor_vertex_ids') and patch.anchor_vertex_ids:
            anchor_pts = pv[patch.anchor_vertex_ids]
            ax.scatter(anchor_pts[:, 0], anchor_pts[:, 1], c='yellow',
                       s=3, zorder=10, alpha=0.8)


def run_physics(patches, body_verts, body_faces):
    """Run cloth simulation on patches, return modified copies."""
    import taichi as ti
    from bikini_generator.physics.cloth_sim import ClothSimulator
    from bikini_generator.garment.assembly import GarmentAssembly
    from bikini_generator.body.mannequin import get_body_collision_primitives
    from bikini_generator.config import PHYSICS

    try:
        ti.init(arch=ti.gpu, default_fp=ti.f32)
    except:
        ti.init(arch=ti.cpu, default_fp=ti.f32)

    assembly = GarmentAssembly()
    for p in patches:
        assembly.add_patch(p)

    vertices, faces, uvs = assembly.merge_to_single_mesh()
    anchor_ids, anchor_positions = assembly.get_all_anchors()
    collision_prims = get_body_collision_primitives()

    print(f"  Total vertices: {len(vertices)}")
    print(f"  Total anchors: {len(anchor_ids)} ({100*len(anchor_ids)/max(len(vertices),1):.1f}%)")

    # Print per-patch anchor info
    offset = 0
    for p in patches:
        n = p.vertex_count()
        na = len(p.anchor_vertex_ids) if p.anchor_vertex_ids else 0
        print(f"    {p.name}: {n} verts, {na} anchors ({100*na/max(n,1):.1f}%)")
        offset += n

    sim = ClothSimulator(
        vertices=vertices,
        faces=faces,
        anchor_ids=anchor_ids,
        anchor_positions=anchor_positions,
        collision_primitives=collision_prims,
        config=PHYSICS,
    )

    final_pos = sim.simulate()
    max_disp = sim.get_max_displacement()
    print(f"  Max displacement: {max_disp*100:.2f} cm")

    # Check Y drops
    initial = sim.initial_pos.to_numpy()
    anchored = sim.is_anchored.to_numpy()
    y_drops = initial[:, 1] - final_pos[:, 1]
    y_drops[anchored == 1] = 0.0
    max_y_drop = float(np.max(y_drops)) if len(y_drops) > 0 else 0
    print(f"  Max Y drop: {max_y_drop*100:.2f} cm")

    # Count extreme displacements
    disps = np.linalg.norm(final_pos - initial, axis=1)
    disps[anchored == 1] = 0
    n_extreme = np.sum(disps > 0.10)
    print(f"  Vertices displaced > 10cm: {n_extreme}")

    # Distribute back to patches
    import copy
    result_patches = []
    offset = 0
    for p in patches:
        p2 = copy.deepcopy(p)
        n = p.vertex_count()
        p2.vertices = final_pos[offset:offset+n].copy()
        p2.compute_normals()
        result_patches.append(p2)
        offset += n

    return result_patches, max_disp


def main():
    from bikini_generator.garment.loop_generator import generate_loop_bikini
    from bikini_generator.body.mannequin import generate_full_body

    body_verts, body_faces = generate_full_body()

    seeds = [0, 7, 42, 100]
    colors_list = [
        (0.2, 0.8, 0.2),  # green (base patches)
        (0.9, 0.3, 0.1),  # red
        (0.3, 0.3, 0.9),  # blue
        (0.8, 0.2, 0.8),  # purple
        (0.9, 0.6, 0.1),  # orange
        (0.1, 0.8, 0.8),  # cyan
        (0.9, 0.9, 0.2),  # yellow
        (0.5, 0.9, 0.3),  # lime
        (0.9, 0.3, 0.5),  # pink
    ]

    fig, axes = plt.subplots(len(seeds), 4, figsize=(16, 4 * len(seeds)))
    fig.patch.set_facecolor('#0a0a1a')
    fig.suptitle('Physics Simulation: Before vs After\n(NO shape_retention, sparse anchors, soft fabric)',
                 color='white', fontsize=14, y=0.98)

    for row, seed in enumerate(seeds):
        print(f"\n=== Seed {seed} ===")
        patches = generate_loop_bikini(seed=seed)

        # Assign colors
        patch_colors = []
        for i, p in enumerate(patches):
            patch_colors.append(colors_list[i % len(colors_list)])

        # Before physics
        print("  Rendering BEFORE...")
        render_view(axes[row, 0], body_verts, body_faces, patches, patch_colors,
                    f"Seed {seed} BEFORE — Front", azimuth=0, show_anchors=True)
        render_view(axes[row, 1], body_verts, body_faces, patches, patch_colors,
                    "BEFORE — Side", azimuth=np.pi/3, show_anchors=True)

        # Run physics
        print("  Running physics...")
        after_patches, max_d = run_physics(patches, body_verts, body_faces)

        # After physics
        print("  Rendering AFTER...")
        render_view(axes[row, 2], body_verts, body_faces, after_patches, patch_colors,
                    f"AFTER physics — Front (max Δ={max_d*100:.1f}cm)", azimuth=0)
        render_view(axes[row, 3], body_verts, body_faces, after_patches, patch_colors,
                    "AFTER — Side", azimuth=np.pi/3)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out_path = os.path.join(os.path.dirname(__file__), "bikini_output.png")
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
