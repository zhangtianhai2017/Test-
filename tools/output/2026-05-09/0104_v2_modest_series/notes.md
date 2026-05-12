# Schema fix — bottom_piece front_half_u was too small (rendering invisible bottoms)

## 用户反馈
> "有可能有一半都下身都没有衣服 然后我也没有看到三角裤的样子"

## 根因（潜空间层的真正 bug）

之前的 `bottom_piece.local_params_schema` 把 `front_half_u` 设得太窄：

| entry | 原 max front_half_u | 实际可见三角形 |
|---|---|---|
| BOT_THONG_M | 0.20 | 0 |
| BOT_BRAZILIAN_M | 0.22 | 0 |
| BOT_CHEEKY_M | 0.22 | 0 |
| BOT_BRIEF_M | 0.26 | **0** |
| BOT_HIGHWAIST_M | 0.26 | 0 |

`front_half_u` 是 polygon 在 cylindrical body UV 空间的方位角半宽。
身体在 hip 处实际曲面分布需要 polygon u 至少覆盖 ±0.40 才能命中前面板的 body 三角形。
之前的 0.22-0.26 范围导致 polygon 落在身体几何之外的"空气"里，渲染管线挑不出任何三角形包含其中——bottom_front 完全 invisible。

之前 1135/1602/0025 系列里"看起来有"是因为我加了 commit 20ea30b 的硬编码 `hip_band` mesh（已撤）。底裤 polygon **从来就没真的渲染过**。

## 修复

`tools/library_data.py` 把所有 5 个 bottom_piece 几何的 `front_half_u` 和 `back_half_u` 推到现实范围：

| entry | 新 front_half_u (M) | 新 back_half_u (M) | 真正可见 |
|---|---|---|---|
| BOT_THONG_M | 0.22-0.32 | 0.06-0.14 | ≈ 70 三角形 (small panel) |
| BOT_BRAZILIAN_M | 0.28-0.36 | 0.10-0.18 | ≈ 200 |
| BOT_CHEEKY_M | 0.34-0.42 | 0.18-0.26 | ≈ 400 |
| BOT_BRIEF_M | 0.42-0.52 | 0.30-0.42 | ≈ 750 |
| BOT_HIGHWAIST_M | 0.46-0.58 | 0.34-0.46 | ≈ 1000 |

## 视觉确认

`overview.png` — 16 件全部显示**真实可见的下裤片**：
- 三角款（行 1）：能看到的三角裤（侧边窄）
- bandeau / bralette / one_piece (行 2-4)：briefs / highwaist 的宽底覆盖

## 副作用

- 37/37 v2 seed 重新迁移通过
- `front_half_u` 改大不影响其他几何，bottom polygon 现在 wraps 从前到侧
- 其它 schema 字段（`back_half_u`, `front_top_v`）也连带调整保持几何比例
