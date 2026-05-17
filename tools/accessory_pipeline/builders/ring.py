"""Parametric ring builder — produces a closed torus mesh for round
profile, a rounded-square loop for square profile, and a flat-top D
shape for d profile.

Output units: cm (matches outfit pipeline + UE 5.6 import config).
"""
from __future__ import annotations

import numpy as np

from ..schema import AccessoryEntry


# Tessellation density.  Rings are tiny (≤2 cm) so 24×12 is plenty
# without bloating the GLB.
N_MAJOR = 32
N_MINOR = 12


def _torus_round(R_cm: float, r_cm: float):
    """Standard torus around the +Z axis, major radius R, minor r (cm)."""
    u = np.linspace(0, 2 * np.pi, N_MAJOR, endpoint=False)
    v = np.linspace(0, 2 * np.pi, N_MINOR, endpoint=False)
    U, V = np.meshgrid(u, v, indexing="ij")
    # parametric torus
    X = (R_cm + r_cm * np.cos(V)) * np.cos(U)
    Y = (R_cm + r_cm * np.cos(V)) * np.sin(U)
    Z = r_cm * np.sin(V)
    V_xyz = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1).astype(np.float32)
    # normals point outward from the centre tube
    Nx = np.cos(V) * np.cos(U)
    Ny = np.cos(V) * np.sin(U)
    Nz = np.sin(V)
    N_xyz = np.stack([Nx.ravel(), Ny.ravel(), Nz.ravel()], axis=1).astype(np.float32)
    # tri indices
    faces = []
    for i in range(N_MAJOR):
        i2 = (i + 1) % N_MAJOR
        for j in range(N_MINOR):
            j2 = (j + 1) % N_MINOR
            a = i  * N_MINOR + j
            b = i2 * N_MINOR + j
            c = i2 * N_MINOR + j2
            d = i  * N_MINOR + j2
            faces.append([a, b, c])
            faces.append([a, c, d])
    F = np.asarray(faces, dtype=np.uint32)
    return V_xyz, F, N_xyz


def _square_loop(R_cm: float, r_cm: float):
    """Square-cornered ring: 4 straight edges joined by 4 quarter
    rounds. Same minor-radius tube cross-section as the round ring.
    We bias U by snapping to the nearest of {0, π/2, π, 3π/2} during
    parameter sweep — implemented by sampling a square path then
    sweeping the circular cross-section along it."""
    n_edge = 8           # samples per straight edge
    n_corner = 6         # samples per rounded corner
    total = (n_edge + n_corner) * 4
    # build centreline points on square + rounded corners
    side = R_cm * 0.85   # straight side half-length
    corner_r = R_cm * 0.15
    pts = []
    # 4 edges in CCW order
    for ei, (sx, sy, ex, ey) in enumerate([
        (-side, -corner_r,  side, -corner_r),  # bottom
        ( side + corner_r * 0, -side * 0 - corner_r, side + corner_r * 0, side * 0 + corner_r),  # right (placeholder)
    ]):
        pass
    # simpler: parametric on a rounded square
    u = np.linspace(0, 2 * np.pi, total, endpoint=False)
    cu, su = np.cos(u), np.sin(u)
    # superellipse approximation: |x|^n + |y|^n = R^n
    n_pow = 6.0
    denom = np.maximum(np.power(np.abs(cu), n_pow) + np.power(np.abs(su), n_pow),
                       1e-9) ** (1.0 / n_pow)
    cx = R_cm * cu / denom
    cy = R_cm * su / denom
    # tangents = numerical derivative
    tx = np.gradient(cx); ty = np.gradient(cy)
    tlen = np.sqrt(tx * tx + ty * ty)
    tx /= tlen; ty /= tlen
    # in-plane normal = perpendicular to tangent
    nx_p = -ty; ny_p = tx
    # cross-section circle
    v = np.linspace(0, 2 * np.pi, N_MINOR, endpoint=False)
    cv, sv = np.cos(v), np.sin(v)
    V_xyz = []
    N_xyz = []
    for i in range(len(u)):
        for j in range(N_MINOR):
            ox = nx_p[i] * r_cm * cv[j]
            oy = ny_p[i] * r_cm * cv[j]
            oz = r_cm * sv[j]
            V_xyz.append([cx[i] + ox, cy[i] + oy, oz])
            # outward normal (radial through the cross-section)
            N_xyz.append([nx_p[i] * cv[j], ny_p[i] * cv[j], sv[j]])
    V_xyz = np.asarray(V_xyz, dtype=np.float32)
    N_xyz = np.asarray(N_xyz, dtype=np.float32)
    # faces
    faces = []
    N_LOOP = len(u)
    for i in range(N_LOOP):
        i2 = (i + 1) % N_LOOP
        for j in range(N_MINOR):
            j2 = (j + 1) % N_MINOR
            a = i  * N_MINOR + j
            b = i2 * N_MINOR + j
            c = i2 * N_MINOR + j2
            d = i  * N_MINOR + j2
            faces.append([a, b, c])
            faces.append([a, c, d])
    return V_xyz, np.asarray(faces, dtype=np.uint32), N_xyz


def _d_loop(R_cm: float, r_cm: float):
    """D-ring: semicircle + straight bar across the diameter."""
    n_arc = N_MAJOR - 8         # arc points
    n_bar = 8                    # bar points
    u_arc = np.linspace(np.pi, 2 * np.pi, n_arc, endpoint=False)
    # arc: upper half (semicircle), x = R cos, y = R sin
    cx_arc = R_cm * np.cos(u_arc)
    cy_arc = R_cm * np.sin(u_arc)
    # bar along the diameter from (-R, 0) to (R, 0)
    cx_bar = np.linspace(-R_cm, R_cm, n_bar, endpoint=False)
    cy_bar = np.zeros_like(cx_bar)
    cx = np.concatenate([cx_arc, cx_bar])
    cy = np.concatenate([cy_arc, cy_bar])
    # tangent + normal in-plane
    tx = np.gradient(cx); ty = np.gradient(cy)
    tlen = np.sqrt(tx * tx + ty * ty); tx /= tlen; ty /= tlen
    nx_p = -ty; ny_p = tx
    v = np.linspace(0, 2 * np.pi, N_MINOR, endpoint=False)
    cv, sv = np.cos(v), np.sin(v)
    V_xyz, N_xyz = [], []
    for i in range(len(cx)):
        for j in range(N_MINOR):
            V_xyz.append([
                cx[i] + nx_p[i] * r_cm * cv[j],
                cy[i] + ny_p[i] * r_cm * cv[j],
                r_cm * sv[j],
            ])
            N_xyz.append([nx_p[i] * cv[j], ny_p[i] * cv[j], sv[j]])
    V_xyz = np.asarray(V_xyz, dtype=np.float32)
    N_xyz = np.asarray(N_xyz, dtype=np.float32)
    faces = []
    N_LOOP = len(cx)
    for i in range(N_LOOP):
        i2 = (i + 1) % N_LOOP
        for j in range(N_MINOR):
            j2 = (j + 1) % N_MINOR
            a = i  * N_MINOR + j
            b = i2 * N_MINOR + j
            c = i2 * N_MINOR + j2
            d = i  * N_MINOR + j2
            faces.append([a, b, c])
            faces.append([a, c, d])
    return V_xyz, np.asarray(faces, dtype=np.uint32), N_xyz


def build(entry: AccessoryEntry):
    """Build a ring mesh in cm. Returns (V, F, N) where V is float32 cm."""
    g = entry.geom
    od_mm = float(g.get("outer_diameter_mm", 12.0))
    th_mm = float(g.get("ring_thickness_mm", 2.0))
    profile = g.get("profile", "round")
    # major radius = (outer - thickness) / 2, in cm
    R_cm = (od_mm - th_mm) / 20.0
    r_cm = th_mm / 20.0
    if profile == "round":
        return _torus_round(R_cm, r_cm)
    if profile == "square":
        return _square_loop(R_cm, r_cm)
    if profile == "d":
        return _d_loop(R_cm, r_cm)
    raise ValueError(f"unknown ring profile: {profile!r}")
