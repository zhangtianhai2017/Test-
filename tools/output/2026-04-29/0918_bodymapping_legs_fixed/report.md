# BodyMapping latent space — legs no longer covered by bottom panel

Cascaded architecture committed:

    Genome  →  Garment  →  BodyDeployment  →  rendered mesh

The leg-fabric bug is now caught at the **BodyDeployment** layer (third
in the cascade). No render-time patch — the constraint lives entirely in
the latent state.

## What changed

- `tools/anatomy.py`:
  - `BodyRegion` dataclass + `body_regions(landmarks)` returning 10 named
    regions (legs / arms / head / neck / chest / pelvis with front/back/
    side variants).
  - `classify_point(x,y,z, regions, max_torso_radius)` — returns the
    region a 3D point falls into, "arms" when it's outside the torso
    radius, "outside" when none match.
  - `y_pelvis` — was hardcoded `y_lo + 0.30 * H` (mid-thigh on this
    standing-pose mesh); now derived from the body topology by walking
    Y up from the feet and finding the first prominent torso-width
    peak (the actual hip ridge).

- `tools/garment_state.py`:
  - `BodyMapping` per piece (covers_regions, must_clear, contact_kind),
    with `DEFAULT_MAPPING_BY_ROLE` providing the role→mapping table.
  - `BodyDeployment` — third-layer dataclass holding piece_mappings,
    resolved 3D anchors, valid_connector_ids / valid_accessory_ids,
    cached anatomy + classify_xyz closure.
  - `deploy_to_body(garment, body_mesh)` — cascades Garment to a
    body-specific BodyDeployment. Resolves every Connector/Accessory
    attachment to a 3D point on the body. Components without resolved
    attachments get filtered out (accountability rule: nothing
    renders that the latent state didn't claim).
  - `validate_deployment(garment, deployment)` — entry point for
    deployment-level validation (warnings already captured by
    deploy_to_body).

- `tools/render3d_uv.py`:
  - `build_fabric_shell` accepts `body_deployment=None`. When supplied,
    it computes the intersection of must_clear across all pieces and
    rejects any triangle whose centroid classifies into one of those
    regions (=legs/arms/head/neck for v1 bikini).
  - `build_strap_meshes` (and `_build_strap_meshes_garment`) accept
    `body_deployment=None`. When supplied, only connectors / accessories
    in `valid_connector_ids` / `valid_accessory_ids` are built. The
    rest are dropped — they had no resolved attachment so they're not
    really there.

- `tools/iter/capture.py`:
  - Builds the BodyDeployment once per render and threads it into
    both `build_fabric_shell` and `build_strap_meshes`.

## Validation

`diverse_triangle_03` was the worst offender — fabric covered both legs
down to mid-shin. After this commit:

- shell Y range: 46.9..146 → constrained by must_clear=legs to torso-only
- the rendered front view shows the bikini terminating at the hip, with
  legs entirely uncovered.

## Files

- `headline.png` — before / after side-by-side on diverse_triangle_03
- `renders/diverse_triangle_03/` — 8-view set with the fix applied
- `renders/composite_red/`, `renders/swimsuit_2/`,
  `renders/composite_floral/` — regression check against the original
  seeds (no visual regression).
