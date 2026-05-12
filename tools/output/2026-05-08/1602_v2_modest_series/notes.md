# Modest series — strict=1+1，侧边实体布片 panel

用户更正：上一次理解成了"飘带"（dangling ribbon）。其实想要的是
**三角裤侧边连接前后的实体布片**——侧 panel 不是细绳/飘带，是平面布料。

## 这次怎么实现的

`bottom_coverage_strict=1.0` + `cup_coverage_strict=1.0` 同时打开，
`_pin_to_max_coverage` 把 `front_half_u / back_half_u / front_top_v /
back_top_v` 全部钉到 schema **MAX**：

| bottom 库条目 | front_half_u 钉值 | back_half_u 钉值 |
|---|---|---|
| BOT_CHEEKY_S | 0.187 | 0.16 |
| BOT_CHEEKY_M | 0.220 | 0.16 |
| BOT_BRIEF_S  | 0.221 | 0.24 |
| BOT_BRIEF_M  | 0.260 | 0.24 |
| BOT_HIGHWAIST_S | 0.221 | 0.26 |
| BOT_HIGHWAIST_M | 0.260 | 0.26 |

front_half_u / back_half_u 控制**侧边布片宽度**（cup width 在底片几何）。
钉到最大 → 侧边布片明显，连接前后裤片。

## 落点

- triangle archetype × 4: 全部 BOT_CHEEKY (archetype slot 不允许 brief/highwaist)
- bandeau × 4 / bralette × 4 / one_piece × 4: 全部 BOT_BRIEF 或 BOT_HIGHWAIST
- cup: triangle 12/16 是 FOAM_MOLDED + BRAZILIAN（trianlge 内部最大），其余 archetype 全是 FOAM_MOLDED

composite mean **0.812** ± 0.023，比 strict=0 baseline (0.790) 略高。
16/16 全部 validate 通过。

## 视觉确认

特别看：
- `modest_bandeau_back_band__rng2/01_front.png` — 粉色款，BRIEF 底片，
  髋部两侧粉色布片明显连接前后
- `modest_one_piece_maillot__rng2/01_front.png` — 绿松石色，HIGHWAIST 底片，
  从腰下面的实体布片连成 V 形侧面
- `modest_bralette_shoulder_strap__rng3/01_front.png` — 绿松石色 BRIEF，
  侧 panel 为实体布

triangle archetype 那一行（最上）因为 archetype slot 只允许 thong/brazilian/cheeky，
没法升到 BRIEF/HIGHWAIST，所以仍然是相对薄的布片——这是 archetype 设计本身决定的，
不是 strict 没生效。如果想要"加宽侧 panel 的 triangle 系列"，需要改 archetype slot
的 allowed_tags 来允许 cheeky+。
