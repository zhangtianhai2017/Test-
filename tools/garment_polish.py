"""
Garment-polish post-processing for the fabric shell.

Why this exists
---------------
`build_fabric_shell` extracts the body's triangles inside the Genome UV
polygons and offsets them along the body normals. Two consequences:

  (a) Nipple bumps come through. The shell inherits every body curvature
      detail. Real swimwear cups are *molded foam* that bridges over the
      breast topology instead of conforming to it (typical foam thickness
      3-5 mm, UV/chlorine resistant EVA — see Cloth Habit's "Making a
      Foam Cup Bra" tutorial and Helen's Closet "Adding Foam Cups"). For
      cups too small for foam, the lining is a **powermesh** layer that
      smooths over body detail (Spandex By Yard buyer's guide). Our fix:
      relax high-frequency curvature with Taubin smoothing, then push
      the cup surface to a minimum offset so the cup forms a dome that
      stands off the body.

  (b) The shell boundary is jagged because it follows body triangle
      edges. Real garment edges are smooth curves, finished with
      **fold-over elastic** (FOE), industry standard 1" or 5/8" wide
      (Brother USA / Janome FOE technique guides; Yarnspirations
      "Guide to Sewing Swimwear"). FOE is sewn at ~90% of the fabric
      edge length so the elastic pulls the fabric edge in slightly —
      we approximate by snapping shell boundary vertices onto the
      smooth Genome polygon and re-building the binding rim around that
      curve.

Industry constants used below (all in cm)
-----------------------------------------
    SKIN_OFFSET_CM      = 0.30   # CLO3D / Marvelous Designer default
                                 # avatar surface offset is 3 mm.
    FOAM_CUP_EXTRA_CM   = 0.45   # average swim foam thickness 3-5 mm;
                                 # we add 4.5 mm above SKIN_OFFSET in
                                 # the cup region so the cup sits as a
                                 # molded dome over the breast.
    FABRIC_THICKNESS_CM = 0.05   # 0.5 mm typical for nylon/spandex
                                 # swim fabric (CLO fabric preset).
    FOE_BINDING_HEIGHT  = 0.40   # 1" FOE folded encloses ~4 mm on the
                                 # garment face.
    SEAM_ALLOWANCE_CM   = 0.64   # 1/4" standard swimwear seam allowance.

Pipeline
--------
    raw_shell  -> taubin_smooth_interior   -> nipple bumps gone
               -> boundary_project_to_uv   -> jagged edge -> smooth curve
               -> safe_offset_from_body    -> guaranteed cup dome stand-off
               -> (binding rebuilt by export_garment with FOE geometry)

Each stage is independent so the exporter can opt out.

References
----------
    - Cloth Habit. "Making a Foam Cup Bra: Part 1."
      https://clothhabit.com/making-a-foam-cup-bra-part-1/
    - Helen's Closet. "How to Add Foam Cups to the Sandpiper Swimsuit."
      https://helensclosetpatterns.com/blogs/helens-closet/how-to-add-foam-cups-to-the-sandpiper-swimsuit
    - Yarnspirations. "Guide to Sewing Swimwear Part 1."
      https://www.yarnspirations.com/blogs/how-to/mic-20180413-guide-to-sewing-swimwear-part-1
    - Brother USA. "How To Use Fold-Over Elastic to Finish Knits."
      https://www.brother-usa.com/blogs/stitching-sewcial/using-fold-over-elastic-to-finish-knits
    - Janome. "Finish Your FOE Like a Pro."
      https://www.janome.com/finish-your-foe-fold-over-elastic-like-a-pro/
    - Marvelous Designer Manual. "Set Skin Offset."
      http://manual.marvelousdesigner.com/display/MD4M/Set+Skin+Offset
    - uDraper. "Preparing garments in MD/CLO."
      https://udraper.com/blogs/tutorials/preparing-garments-in-md-clo
    - Spandex By Yard. "Spandex That Doesn't Go Sheer." (powermesh lining)
      https://spandexbyyard.com/blogs/.../how-to-avoid-see-through-spandex
"""

from __future__ import annotations

import numpy as np
import open3d as o3d
from collections import defaultdict


# Industry-derived constants (all centimeters).
SKIN_OFFSET_CM = 0.30
FOAM_CUP_EXTRA_CM = 0.45
FABRIC_THICKNESS_CM = 0.05
FOE_BINDING_HEIGHT = 0.40
SEAM_ALLOWANCE_CM = 0.64


# ---------------------------------------------------------------------------
# Mesh topology helpers
# ---------------------------------------------------------------------------

def _edge_face_count(faces: np.ndarray) -> dict[tuple[int, int], int]:
    """edge (a<b) -> how many faces use it. Boundary edges get 1."""
    cnt: dict[tuple[int, int], int] = defaultdict(int)
    for a, b, c in faces:
        for u, v in ((a, b), (b, c), (c, a)):
            e = (int(min(u, v)), int(max(u, v)))
            cnt[e] += 1
    return cnt


def _boundary_loops(faces: np.ndarray, n_verts: int
                    ) -> tuple[np.ndarray, list[list[int]]]:
    """Returns (is_boundary_vertex, boundary_loops).

    A boundary loop is an ordered list of vertex indices forming a closed
    boundary of the manifold. We build it by walking boundary half-edges.
    """
    ef = _edge_face_count(faces)
    boundary_edges = [e for e, c in ef.items() if c == 1]
    is_bd = np.zeros(n_verts, dtype=bool)
    nbr: dict[int, list[int]] = defaultdict(list)
    for u, v in boundary_edges:
        is_bd[u] = True
        is_bd[v] = True
        nbr[u].append(v)
        nbr[v].append(u)

    visited: set[int] = set()
    loops: list[list[int]] = []
    for start in nbr.keys():
        if start in visited:
            continue
        loop = [start]
        visited.add(start)
        prev = -1
        cur = start
        while True:
            nexts = [n for n in nbr[cur] if n != prev]
            if not nexts:
                break
            nxt = nexts[0]
            if nxt == start:
                break
            if nxt in visited:
                break
            visited.add(nxt)
            loop.append(nxt)
            prev = cur
            cur = nxt
        if len(loop) >= 3:
            loops.append(loop)
    return is_bd, loops


# ---------------------------------------------------------------------------
# Interior smoothing — flattens nipple bumps without moving the boundary
# ---------------------------------------------------------------------------

def taubin_smooth_interior(shell: o3d.geometry.TriangleMesh,
                            iterations: int = 12,
                            lam: float = 0.5,
                            mu: float = -0.53,
                            ) -> o3d.geometry.TriangleMesh:
    """Apply Taubin smoothing (Laplacian with shrink-cancelling step).

    Taubin alternates two Laplacian steps with opposite signs (lambda/mu);
    the result is low-pass filtered without volumetric shrinkage that
    plain Laplacian causes. We pin the boundary so the silhouette doesn't
    creep inward — interior bumps (the nipple) get flattened, the cut
    edge stays where it is.
    """
    V = np.asarray(shell.vertices, dtype=np.float64).copy()
    F = np.asarray(shell.triangles, dtype=np.int64)
    is_bd, _ = _boundary_loops(F, len(V))

    # Build vertex adjacency once
    nbrs: list[list[int]] = [[] for _ in range(len(V))]
    seen: set[tuple[int, int]] = set()
    for a, b, c in F:
        for u, v in ((a, b), (b, c), (c, a)):
            e = (min(u, v), max(u, v))
            if e in seen:
                continue
            seen.add(e)
            nbrs[u].append(v)
            nbrs[v].append(u)

    def step(V_in: np.ndarray, factor: float) -> np.ndarray:
        out = V_in.copy()
        for i, ns in enumerate(nbrs):
            if is_bd[i] or not ns:
                continue
            avg = V_in[ns].mean(axis=0)
            out[i] = V_in[i] + factor * (avg - V_in[i])
        return out

    for _ in range(iterations):
        V = step(V, lam)
        V = step(V, mu)

    out = o3d.geometry.TriangleMesh()
    out.vertices = o3d.utility.Vector3dVector(V)
    out.triangles = o3d.utility.Vector3iVector(F.astype(np.int32))
    if shell.has_triangle_uvs():
        out.triangle_uvs = o3d.utility.Vector2dVector(np.asarray(shell.triangle_uvs))
    out.compute_vertex_normals()
    return out


# ---------------------------------------------------------------------------
# Boundary projection — snaps jagged edge onto smooth Genome polygon
# ---------------------------------------------------------------------------

def _per_vertex_uv(shell: o3d.geometry.TriangleMesh) -> np.ndarray:
    """Recover one UV per vertex from the per-corner triangle_uvs layout.

    o3d shells carry UVs as (3*Ntri, 2). For verts that appear in multiple
    triangles we take the average — for the cylindrical UV layout this is
    a near-zero error since the same vertex lands at the same body U,V
    no matter which face uses it (except across the back seam, which we
    ignore for boundary projection because the front-side bikini never
    crosses there).
    """
    F = np.asarray(shell.triangles)
    UV = np.asarray(shell.triangle_uvs)
    n = int(F.max()) + 1
    acc = np.zeros((n, 2), dtype=np.float64)
    cnt = np.zeros(n, dtype=np.int64)
    for ti, (a, b, c) in enumerate(F):
        for k, vi in enumerate((a, b, c)):
            acc[vi] += UV[3*ti + k]
            cnt[vi] += 1
    cnt[cnt == 0] = 1
    return acc / cnt[:, None]


def _project_uv_to_polygons(uv: np.ndarray,
                             polys_uv_genome: list[list[tuple[float, float]]],
                             ) -> np.ndarray:
    """For each (u,v) in atlas-space [0,1]x[0,1], return the closest point
    on any Genome polygon. Genome polygons live in [-1,1]x[0,1]; we rescale.
    """
    atlas_u = uv[:, 0] * 2.0 - 1.0      # [-1, 1] like Genome
    atlas_v = uv[:, 1].copy()
    pts = np.stack([atlas_u, atlas_v], axis=-1)

    # gather all polygon edges
    edges: list[tuple[np.ndarray, np.ndarray]] = []
    for poly in polys_uv_genome:
        if len(poly) < 3:
            continue
        arr = np.asarray(poly, dtype=np.float64)
        for i in range(len(arr)):
            edges.append((arr[i], arr[(i + 1) % len(arr)]))
    if not edges:
        return uv.copy()

    out = np.empty_like(uv)
    for i, p in enumerate(pts):
        best_d = np.inf
        best_pt = p
        for a, b in edges:
            ab = b - a
            t = float(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-12))
            t = float(np.clip(t, 0.0, 1.0))
            q = a + t * ab
            d = float(np.dot(p - q, p - q))
            if d < best_d:
                best_d = d
                best_pt = q
        # back to atlas u in [0,1]
        out[i] = [(best_pt[0] + 1.0) * 0.5, best_pt[1]]
    return out


def _uv_to_xyz_cylindrical(uvs: np.ndarray, body_mesh: o3d.geometry.TriangleMesh,
                           y_crotch: float, y_neck: float,
                           max_torso_radius: float = 20.0,
                           ) -> np.ndarray:
    """Inverse of cylindrical_uvs: (u_atlas, v) -> 3D point on the body's
    cylinder at that azimuth/height. Uses the body's actual radial profile
    via nearest-neighbor on (theta, y) so points snap to the surface.

    BUG FIX: filter to torso-only body verts (XZ radius < max_torso_radius).
    Without this, boundary verts at u=+/-0.5 (left/right side of body) get
    projected onto the arms — the arms stretch laterally to ~45 cm at the
    same theta as the torso side and the (theta, y)-nearest body vert is
    on the arm, not the torso. That dragged the polished shell boundary
    out as visible "wings" past the body silhouette in the front view.
    """
    V = np.asarray(body_mesh.vertices)
    r_xz = np.sqrt(V[:, 0] ** 2 + V[:, 2] ** 2)
    keep = r_xz < max_torso_radius
    V = V[keep]
    theta = np.arctan2(V[:, 0], V[:, 2])      # [-pi, pi]
    y = V[:, 1]
    target_theta = (uvs[:, 0] * 2.0 - 1.0) * np.pi
    target_y = y_crotch + uvs[:, 1] * (y_neck - y_crotch)

    # Normalize theta and y for nearest neighbor search
    yh = max(y_neck - y_crotch, 1e-3)
    bv = np.stack([np.sin(theta), np.cos(theta), y / yh], axis=-1)
    tv = np.stack([np.sin(target_theta), np.cos(target_theta), target_y / yh], axis=-1)

    out = np.empty((len(uvs), 3), dtype=np.float64)
    for i in range(len(uvs)):
        d2 = ((bv - tv[i]) ** 2).sum(axis=-1)
        out[i] = V[int(np.argmin(d2))]
    return out


def project_boundary_to_polygons(shell: o3d.geometry.TriangleMesh,
                                  polys_uv_genome: list[list[tuple[float, float]]],
                                  body_mesh: o3d.geometry.TriangleMesh,
                                  y_crotch: float, y_neck: float,
                                  blend: float = 0.85,
                                  ) -> o3d.geometry.TriangleMesh:
    """Move every boundary vertex toward the closest point on the Genome
    polygon, in cylindrical UV space, then back-project to 3D.

    blend: 0.0 = keep raw boundary, 1.0 = fully snap to polygon.
    """
    V = np.asarray(shell.vertices, dtype=np.float64).copy()
    F = np.asarray(shell.triangles, dtype=np.int64)
    is_bd, _ = _boundary_loops(F, len(V))
    bd_idx = np.where(is_bd)[0]
    if len(bd_idx) == 0:
        return shell

    uv_per_vertex = _per_vertex_uv(shell)
    target_uv = _project_uv_to_polygons(uv_per_vertex[bd_idx], polys_uv_genome)
    target_xyz = _uv_to_xyz_cylindrical(target_uv, body_mesh, y_crotch, y_neck)

    V[bd_idx] = (1.0 - blend) * V[bd_idx] + blend * target_xyz

    out = o3d.geometry.TriangleMesh()
    out.vertices = o3d.utility.Vector3dVector(V)
    out.triangles = o3d.utility.Vector3iVector(F.astype(np.int32))
    if shell.has_triangle_uvs():
        out.triangle_uvs = o3d.utility.Vector2dVector(np.asarray(shell.triangle_uvs))
    out.compute_vertex_normals()
    return out


# ---------------------------------------------------------------------------
# Safe offset — ensure no body penetration after smoothing
# ---------------------------------------------------------------------------

def safe_offset_from_body(shell: o3d.geometry.TriangleMesh,
                           body_mesh: o3d.geometry.TriangleMesh,
                           min_offset: float = 0.4,
                           cup_extra: float = 0.6,
                           cup_v_range: tuple[float, float] = (0.66, 0.92),
                           polys_uv_genome: list[list[tuple[float, float]]] | None = None,
                           y_crotch: float = 0.0, y_neck: float = 100.0,
                           max_torso_radius: float = 20.0,
                           ) -> o3d.geometry.TriangleMesh:
    """Push every shell vertex outward along the body normal until it's
    at least `min_offset` cm away from the nearest body vertex.

    In the cup area (mid-chest stripe of v ~ 0.66..0.92) we add `cup_extra`
    to the floor offset so the cup forms a molded dome that visibly stands
    off the body. This is what real foam-cup or structured bikini tops do
    — the cup keeps its convex shape regardless of the breast topology
    underneath.

    BUG FIX: when looking up the nearest body vertex, we restrict the
    search to TORSO vertices only (XZ radius < max_torso_radius). On the
    T-pose mesh the arms run out at the same Y as the chest, and a shell
    vertex on the side of the torso has its nearest body vertex on the
    arm — pushing along the arm's normal then drags the shell laterally
    onto the arm, producing visible "wings" on the chest.
    """
    V = np.asarray(shell.vertices, dtype=np.float64).copy()
    BV = np.asarray(body_mesh.vertices)
    if not body_mesh.has_vertex_normals():
        body_mesh.compute_vertex_normals()
    BN = np.asarray(body_mesh.vertex_normals)

    # Restrict body verts used for nearest-neighbor lookup to the torso
    # (XZ radius < max_torso_radius). Arms in T-pose stretch laterally
    # to ~45 cm and would otherwise capture nearby shell verts.
    body_r_xz = np.sqrt(BV[:, 0] ** 2 + BV[:, 2] ** 2)
    torso_mask = body_r_xz < max_torso_radius
    BV_t = BV[torso_mask]
    BN_t = BN[torso_mask]

    # Approximate per-shell-vertex v in cylindrical UV
    shell_y = V[:, 1]
    shell_v = (shell_y - y_crotch) / max(y_neck - y_crotch, 1e-3)

    new_V = V.copy()
    for i, p in enumerate(V):
        # Nearest TORSO vertex (skip arms)
        d2 = ((BV_t - p) ** 2).sum(axis=-1)
        j = int(np.argmin(d2))
        n = BN_t[j]
        # signed distance along body normal (positive = outside body)
        signed = float(np.dot(p - BV_t[j], n))
        target = min_offset
        if cup_v_range[0] <= shell_v[i] <= cup_v_range[1]:
            target += cup_extra
        if signed < target:
            new_V[i] = p + n * (target - signed)

    out = o3d.geometry.TriangleMesh()
    out.vertices = o3d.utility.Vector3dVector(new_V)
    out.triangles = o3d.utility.Vector3iVector(np.asarray(shell.triangles).astype(np.int32))
    if shell.has_triangle_uvs():
        out.triangle_uvs = o3d.utility.Vector2dVector(np.asarray(shell.triangle_uvs))
    out.compute_vertex_normals()
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def polish_shell(shell: o3d.geometry.TriangleMesh,
                  body_mesh: o3d.geometry.TriangleMesh,
                  polys_uv_genome: list[list[tuple[float, float]]],
                  y_crotch: float, y_neck: float,
                  smooth_iters: int = 12,
                  boundary_snap: float = 0.85,
                  min_offset: float = SKIN_OFFSET_CM,
                  cup_extra_offset: float = FOAM_CUP_EXTRA_CM,
                  ) -> o3d.geometry.TriangleMesh:
    """Run the full polish pipeline. See module docstring for stage list.

    Defaults match industry constants:
      - min_offset = 3 mm  (CLO3D / Marvelous Designer default)
      - cup_extra  = 4.5 mm (typical swim foam cup thickness)
    """
    if len(np.asarray(shell.triangles)) == 0:
        return shell
    s = taubin_smooth_interior(shell, iterations=smooth_iters)
    s = project_boundary_to_polygons(s, polys_uv_genome, body_mesh,
                                       y_crotch, y_neck, blend=boundary_snap)
    s = safe_offset_from_body(s, body_mesh,
                                min_offset=min_offset,
                                cup_extra=cup_extra_offset,
                                polys_uv_genome=polys_uv_genome,
                                y_crotch=y_crotch, y_neck=y_neck)
    return s
