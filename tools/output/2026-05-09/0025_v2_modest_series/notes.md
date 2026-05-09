# Modest series re-render — 髋部侧带桥接前后裤片

## 用户反馈

> "之前生成的那个布片都没有东西挂着他，我说的范围是裤子相关的"

之前的 modest series（1135、1602）虽然 cup + bottom_front + bottom_back
都有，但前后裤片之间在髋部**视觉上断开** — 渲染管线没有画连接它们的
结构件，看起来像两片漂浮的布。

## 渲染管线问题

`_build_strap_meshes_garment` 里的 `_build_tie_mesh` 调用只在
`tie_string` connector 存在时触发 — 即只有 `triangle_string_halter`
archetype（带 side_tie slot）才会画髋部带。其他 3 个 archetype（bandeau、
bralette、one_piece）渲染 0 个髋部连接元素 → 前后片完全脱节。

## 修复

`tools/render3d_uv.py::_build_strap_meshes_garment` 加了一段 3a），
**无论 archetype 如何**，只要 garment 同时有 `bottom_front` 和
`bottom_back_*` 这些 PatternPiece，就在每个髋部画一条 fabric band：

```python
if has_front_bot and has_back_bot:
    y_hip_lo = min(y_front, y_back) - 1.5
    y_hip_hi = max(y_front, y_back) + 1.5
    band_half_w = max(1.0, 12.0 * float(g.bot_back_half_u))
    for u_side, name in [(0.5, "hip_band_R"), (-0.5, "hip_band_L")]:
        band = _build_tie_mesh(V, y_hip_lo, y_hip_hi, u_side,
                                band_offset=0.4,
                                half_width_cm=band_half_w)
        straps.append((name, band))
```

`_build_tie_mesh` 之前的 `half_w` 是固定 0.6 cm，加了 `half_width_cm`
参数让我可以按 `bot_back_half_u` 缩放（覆盖度高 → 侧带宽，最低 1cm）。

## 视觉对比

`tools/output/2026-05-08/1602_v2_modest_series/` (修复前) vs.
`tools/output/2026-05-09/0025_v2_modest_series/` (修复后)：

- **front view**：能看到髋部两侧的薄带（rectangle 法线朝外，前视看的是其窄边）
- **side view**：完整看到布带，宽 ~3.5 cm（briefs/highwaist 时），跟裤片 fabric color 一致
- **3/4 view**：最清楚 — 布带把前后片串成一件完整的下身

## Strap material 同色

`strap_mat.base_color = _color_from_genome(genome)` — 髋部侧带继承
outfit hue，所以颜色与 cup / bottom 一致（不像之前 1602 的 magenta
mismatch）。

## 16 件结果

`overview.png` — 4 archetype × 4 RNG seed，全部有可见髋部侧带。
- 三角款 (BOT_CHEEKY)：侧带小但存在
- bandeau / bralette / one_piece (BOT_BRIEF/HIGHWAIST)：侧带宽，视觉清晰
- 16/16 outfits validate 通过
