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


def _fit_closed_spline(poly_xy: np.ndarray, n_samples: int = 400,
                        smoothing: float = 0.0) -> np.ndarray:
    """Fit a closed parametric cubic B-spline through the polygon vertices
    and return `n_samples` densely-sampled points along the curve.

    The Genome polygons are themselves analytic but stored as a finite
    point list. Fitting a closed B-spline gives us a C2-continuous curve
    that we can use as the *target* boundary, completely replacing the
    piecewise-linear polygon — that's the geometric-curve replacement
    we want for the jagged shell boundary, not a tiny local smoothing.
    """
    from scipy.interpolate import splprep, splev
    pts = np.asarray(poly_xy, dtype=np.float64)
    if len(pts) < 4:
        return pts.copy()
    # splprep with per=1 fits a periodic spline (closed curve)
    tck, _u = splprep([pts[:, 0], pts[:, 1]], s=smoothing, k=3, per=True)
    u = np.linspace(0.0, 1.0, n_samples, endpoint=False)
    out = splev(u, tck)
    return np.stack([out[0], out[1]], axis=-1)


def _build_polygon_curves(polys_uv_genome: list[list[tuple[float, float]]],
                            n_samples: int = 400
                            ) -> list[np.ndarray]:
    """Fit a closed cubic B-spline through each Genome polygon. Returns
    a list of dense (n_samples, 2) arrays in Genome-UV [-1,1] x [0,1].
    """
    out = []
    for poly in polys_uv_genome:
        if len(poly) < 4:
            continue
        try:
            curve = _fit_closed_spline(np.asarray(poly), n_samples=n_samples)
            out.append(curve)
        except Exception:
            # Fall back to raw polygon if the fit fails (degenerate)
            out.append(np.asarray(poly))
    return out


def _project_uv_to_curves(uv_atlas: np.ndarray,
                            curves_genome: list[np.ndarray]
                            ) -> np.ndarray:
    """For each (u,v) in atlas-space [0,1] x [0,1], snap to the closest
    point on any of the dense Genome-UV curves. Curves are in [-1,1] Genome u.
    """
    if not curves_genome:
        return uv_atlas.copy()
    pts = np.stack([uv_atlas[:, 0] * 2.0 - 1.0, uv_atlas[:, 1]], axis=-1)
    all_curve = np.concatenate(curves_genome, axis=0)  # (sum_n, 2)
    out = np.empty_like(uv_atlas)
    for i, p in enumerate(pts):
        d2 = ((all_curve - p) ** 2).sum(axis=-1)
        q = all_curve[int(np.argmin(d2))]
        out[i] = [(q[0] + 1.0) * 0.5, q[1]]
    return out


def project_boundary_to_polygons(shell: o3d.geometry.TriangleMesh,
                                  polys_uv_genome: list[list[tuple[float, float]]],
                                  body_mesh: o3d.geometry.TriangleMesh,
                                  y_crotch: float, y_neck: float,
                                  blend: float = 0.85,
                                  use_spline: bool = True,
                                  ) -> o3d.geometry.TriangleMesh:
    """Move every boundary vertex onto a smooth target curve.

    Two-stage geometric-curve replacement:
      1. Fit a closed cubic B-spline through each Genome polygon (200+
         dense samples) — gives a C2-continuous target curve, not the
         piecewise-linear polygon.
      2. For every shell boundary vertex, find its UV, snap UV to the
         densely-sampled spline, back-project to 3D via cylindrical map.

    The result is an aggressive boundary replacement — entire jagged
    boundary is overwritten with curve-sampled positions, not nudged
    toward polygon edges. blend=1.0 gives full replacement.
    """
    V = np.asarray(shell.vertices, dtype=np.float64).copy()
    F = np.asarray(shell.triangles, dtype=np.int64)
    is_bd, loops = _boundary_loops(F, len(V))
    bd_idx = np.where(is_bd)[0]
    if len(bd_idx) == 0:
        return shell

    uv_per_vertex = _per_vertex_uv(shell)
    if use_spline:
        curves = _build_polygon_curves(polys_uv_genome, n_samples=400)
        target_uv = _project_uv_to_curves(uv_per_vertex[bd_idx], curves)
    else:
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

def cup_dome_replace(shell: o3d.geometry.TriangleMesh,
                      body_mesh: o3d.geometry.TriangleMesh,
                      genome,
                      y_crotch: float, y_neck: float,
                      cup_depth_cm: float = 1.8,
                      ) -> o3d.geometry.TriangleMesh:
    """Replace cup-region vertex positions with an analytic half-ellipsoid
    surface whose shape DOES NOT depend on breast topology.

    A real molded swim cup is a *foam cup* — a structured surface that
    bridges over the breast keeping its own convex shape. We replicate
    by computing each cup-region vertex's offset *along the body normal*
    as the dome height of an axis-aligned ellipsoid centered on the cup,
    keyed to the vertex's local (u, v) inside the cup polygon (NOT to
    the body's local breast curvature).

    cup_depth_cm: dome height at apex (4-5 mm for thin-shell padded; up
    to 1.5-2 cm for full molded foam cup).

    The mapping for each cup, c in {left, right}:
        u_local = (vertex_u - cup_center_u) / cup_half_u  ∈ [-1, 1]
        v_local = (vertex_v - cup_center_v) / cup_half_v
        r2 = u_local^2 + v_local^2
        if r2 < 1: dome = cup_depth * sqrt(1 - r2)   (half-ellipsoid)
                  else dome = 0
    Then set vertex = body_surface_pt + body_normal * dome.

    Result: cup is a smooth dome regardless of breast shape — solves
    the cup body-coupling that all of round 0..9 could not fix with
    parameter tuning.
    """
    if genome is None:
        return shell

    half_u = float(getattr(genome, "top_half_u", 0.16))
    half_v = float(getattr(genome, "top_half_v", 0.07))
    inner_u = float(getattr(genome, "top_inner_u", 0.12))
    center_v = float(getattr(genome, "top_center_v", 0.76))
    if half_u <= 0.0 or half_v <= 0.0:
        return shell

    V = np.asarray(shell.vertices, dtype=np.float64).copy()
    if not body_mesh.has_vertex_normals():
        body_mesh.compute_vertex_normals()
    BV = np.asarray(body_mesh.vertices)
    BN = np.asarray(body_mesh.vertex_normals)
    body_r_xz = np.sqrt(BV[:, 0] ** 2 + BV[:, 2] ** 2)
    torso = body_r_xz < 20.0
    BV_t, BN_t = BV[torso], BN[torso]

    yh = max(y_neck - y_crotch, 1e-3)
    cup_center_y = y_crotch + center_v * yh
    cup_half_y = half_v * yh

    # Cup u-centers in Genome [-1,1]: each cup centered at +/-(inner_u + half_u)
    cup_center_u_R = inner_u + half_u
    cup_center_u_L = -(inner_u + half_u)

    new_V = V.copy()
    for i, p in enumerate(V):
        # Find cylindrical (u, y) for this vertex
        theta = np.arctan2(p[0], p[2])
        u_genome = theta / np.pi      # [-1, 1]
        y = p[1]

        # In which cup? (Or neither.)
        for cu in (cup_center_u_R, cup_center_u_L):
            u_local = (u_genome - cu) / max(half_u, 1e-3)
            v_local = (y - cup_center_y) / max(cup_half_y, 1e-3)
            r2 = u_local * u_local + v_local * v_local
            if r2 >= 1.0:
                continue
            # Smooth blend at the cup edge so the dome doesn't transition
            # sharply into the surrounding shell. Use a Hermite-like
            # falloff (smoothstep) keyed to r2 so dome contribution fades
            # to zero at r2 = 1.0.
            blend = 1.0 - r2
            blend = blend * blend * (3.0 - 2.0 * blend)   # smoothstep
            # Find body surface at this (theta, y) (torso only)
            tv_y = y / yh
            bv_normalized = np.stack([
                np.sin(np.arctan2(BV_t[:, 0], BV_t[:, 2])),
                np.cos(np.arctan2(BV_t[:, 0], BV_t[:, 2])),
                BV_t[:, 1] / yh
            ], axis=-1)
            target = np.array([np.sin(theta), np.cos(theta), tv_y])
            d2 = ((bv_normalized - target) ** 2).sum(axis=-1)
            j = int(np.argmin(d2))
            base_pt = BV_t[j]
            normal = BN_t[j]
            dome_h = cup_depth_cm * float(np.sqrt(1.0 - r2)) * blend
            # The dome height is added on top of a small base offset
            # so the cup never touches the body even at its rim.
            # Blend keeps the existing vertex position when far from
            # cup center, dome-target when close.
            base_offset = 0.30
            target = base_pt + normal * (base_offset + dome_h)
            new_V[i] = (1.0 - blend) * p + blend * target
            break

    out = o3d.geometry.TriangleMesh()
    out.vertices = o3d.utility.Vector3dVector(new_V)
    out.triangles = o3d.utility.Vector3iVector(np.asarray(shell.triangles).astype(np.int32))
    if shell.has_triangle_uvs():
        out.triangle_uvs = o3d.utility.Vector2dVector(np.asarray(shell.triangle_uvs))
    out.compute_vertex_normals()
    return out


def smooth_boundary_loops_3d(shell: o3d.geometry.TriangleMesh,
                              n_harmonics: int = 8,
                              ) -> o3d.geometry.TriangleMesh:
    """Aggressive arc-length low-pass of every closed boundary loop in 3D.

    For each boundary loop we treat the (X,Y,Z) coordinates as three
    periodic 1-D signals indexed by loop position, take the FFT, keep
    only the lowest `n_harmonics` frequencies (zero everything else),
    and inverse-FFT. This is the global-scale smoothing the user asked
    for — it kills high-frequency wiggle along the boundary regardless
    of where the verts came from. n_harmonics ~6-10 keeps the overall
    shape (the polygon's 'roundness') but flattens triangle-edge zigzags.
    """
    V = np.asarray(shell.vertices, dtype=np.float64).copy()
    F = np.asarray(shell.triangles, dtype=np.int64)
    _is_bd, loops = _boundary_loops(F, len(V))
    if not loops:
        return shell

    for loop in loops:
        n = len(loop)
        if n < max(8, 2 * n_harmonics + 1):
            continue
        idx = np.array(loop, dtype=np.int64)
        coords = V[idx]                        # (n, 3)
        smoothed = np.empty_like(coords)
        for axis in range(3):
            sig = coords[:, axis]
            spec = np.fft.fft(sig)
            mask = np.zeros(n, dtype=complex)
            mask[: n_harmonics + 1] = 1
            mask[-n_harmonics:] = 1
            smoothed[:, axis] = np.real(np.fft.ifft(spec * mask))
        V[idx] = smoothed

    out = o3d.geometry.TriangleMesh()
    out.vertices = o3d.utility.Vector3dVector(V)
    out.triangles = o3d.utility.Vector3iVector(F.astype(np.int32))
    if shell.has_triangle_uvs():
        out.triangle_uvs = o3d.utility.Vector2dVector(np.asarray(shell.triangle_uvs))
    out.compute_vertex_normals()
    return out


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
                  genome=None,
                  cup_dome_depth_cm: float = 0.0,
                  ) -> o3d.geometry.TriangleMesh:
    """Run the full polish pipeline. See module docstring for stage list.

    Defaults match industry constants:
      - min_offset = 3 mm  (CLO3D / Marvelous Designer default)
      - cup_extra  = 4.5 mm (typical swim foam cup thickness)
    """
    if len(np.asarray(shell.triangles)) == 0:
        return shell
    s = taubin_smooth_interior(shell, iterations=smooth_iters)
    # Geometric-curve replacement of boundary: fit closed cubic B-spline
    # through each Genome polygon, snap boundary verts onto the dense
    # spline samples in UV, back-project to 3D.
    s = project_boundary_to_polygons(s, polys_uv_genome, body_mesh,
                                       y_crotch, y_neck, blend=boundary_snap,
                                       use_spline=True)
    # Then a global arc-length low-pass on each boundary loop in 3D —
    # kills any residual zigzag that the cylindrical back-projection
    # introduced (body surface is locally non-smooth).
    s = smooth_boundary_loops_3d(s, n_harmonics=8)
    # Optional analytic cup dome — replaces breast-following cup geometry
    # with a half-ellipsoid (round 12). cup_dome_depth_cm > 0 enables.
    if cup_dome_depth_cm > 0.001 and genome is not None:
        s = cup_dome_replace(s, body_mesh, genome, y_crotch, y_neck,
                              cup_depth_cm=cup_dome_depth_cm)
    s = safe_offset_from_body(s, body_mesh,
                                min_offset=min_offset,
                                cup_extra=cup_extra_offset,
                                polys_uv_genome=polys_uv_genome,
                                y_crotch=y_crotch, y_neck=y_neck)
    return s
