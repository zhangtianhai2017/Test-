# 双 modesty cap = 1.0

`bottom_coverage_strict=1.0` + `cup_coverage_strict=1.0` 同时打满，
其余 RNG seed 与 `1021_v2_pure_random` 完全相同，做直接对照。

## 对照（同 RNG seed × 同 archetype）

| archetype × rng | strict=0 cup | strict=0 bot | strict=1 cup | strict=1 bot |
|---|---|---|---|---|
| triangle × 0 | CUP_TRIANGLE_M | BOT_THONG_M | CUP_BRAZILIAN_M | **BOT_CHEEKY_M** |
| triangle × 1 | CUP_TRIANGLE_S | BOT_THONG_S | CUP_BRAZILIAN_S | **BOT_CHEEKY_S** |
| bandeau × 0 | CUP_FOAM_MOLDED_S | BOT_THONG_M | **CUP_FOAM_MOLDED_L** | **BOT_HIGHWAIST_M** |
| bralette × 0 | CUP_TRIANGLE_S | BOT_HIGHWAIST_S | **CUP_FOAM_MOLDED_M** | **BOT_BRIEF_M** |
| bralette × 3 | CUP_BRAZILIAN_L | BOT_BRIEF_S | **CUP_FOAM_MOLDED_L** | **BOT_HIGHWAIST_M** |
| one_piece × 0 | CUP_BRAZILIAN_S | BOT_BRIEF_S | **CUP_FOAM_MOLDED_S** | **BOT_HIGHWAIST_M** |

观察：
- **triangle archetype** 升级到 `BRAZILIAN/CHEEKY`（自身 slot tags 不允许 `full` 层；图形上仍是三角款，但 cup 选了 brazilian-tagged，bottom 升到 cheeky）
- **bandeau / bralette / one_piece** 全部升到 `FOAM_MOLDED + HIGHWAIST/BRIEF`，是真正的 full-coverage 工字款

## 聚合分数

| | strict=0 (1021) | strict=1 (1135) |
|---|---|---|
| composite mean | 0.790 ± 0.037 | **0.808** ± 0.033 |
| outfit-native | 0.838 ± 0.058 | **0.864** ± 0.049 |
| range | [0.735, 0.848] | [0.755, 0.870] |

平均反而**略高**（+0.02）— foam 主面料 + 上 lining_fabric 槽位激活后，
compatibility_strength / library_diversity 两个轴都满分；视觉上 16 件都是 0 violation。

## cup / bottom 分布

```
cup:                          bottom_front:
  CUP_FOAM_MOLDED_M: 4          BOT_HIGHWAIST_M: 5
  CUP_FOAM_MOLDED_L: 4          BOT_CHEEKY_M:    3
  CUP_FOAM_MOLDED_S: 4          BOT_HIGHWAIST_S: 3
  CUP_BRAZILIAN_M:   1          BOT_BRIEF_M:     2
  CUP_BRAZILIAN_S:   1          BOT_BRIEF_S:     2
  CUP_TRIANGLE_M:    1          BOT_CHEEKY_S:    1
  CUP_TRIANGLE_L:    1
```

12/16 cup 是 molded foam（其余 4 个全是 triangle archetype，archetype-bound）。
0/16 thong（曾是 strict=0 baseline 的常见落点）。

`overview.png`：4×4 contact sheet。
