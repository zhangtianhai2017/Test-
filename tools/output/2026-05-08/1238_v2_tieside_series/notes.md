# Tie-side (挂带) bikini series — 12 outfits

User asked: "目前下身的穿着都倾向于那种叫C裤的。这并不是不允许，但
这只是一种常见的，那种有挂的、边上有挂的，把这种有挂带的随机因子
找出来生成一个系列。"

C裤 = thin string-only minimal bottom, no visible tie-knot at the hip.
挂带 = visible side-tie ribbon/cord with a knot + dangling tail at the hip.

## 找到的随机因子

| # | 层 | 因子 | 取值 |
|---|---|---|---|
| 1 | archetype | 必须是 `triangle_string_halter`（4 个 archetype 里**唯一**有 `side_tie` slot 的） | pinned |
| 2 | bottom_piece | 必须 tag 含 `tie-side` → `BOT_BRAZILIAN_S/M`（库 86 个里**只有这 2 个** tag 含 tie-side） | pinned |
| 3 | strap_piece | `side_tie` slot 必填，从 3 条 tie 里挑：`STR_TIE_CORD_3MM/5MM` 或 `STR_TIE_RIBBON_15MM` | RNG |
| 4 | Genome | `bot_tie_dangle ∈ U(0.65, 0.95)` — 控渲染器 `_build_strap_meshes` 的下垂飘带长度（`dangle_len = 2 + 14·dangle` cm，11–15cm 显眼） | RNG |

`outfit_to_genome` 默认把 `bot_tie_dangle` 硬编码为 0.40（仅 ~7cm，飘带几乎看不出）— 我手动把它推到 0.65–0.95 才让"挂"的效果出来。

## 12 件结果

`overview.png` 一张 4×3 的 contact sheet。每件：
- 100% 用 `triangle_string_halter` 架构
- 100% 用 `BOT_BRAZILIAN_S/M`（tie-side 唯一 2 条）
- 100% 含 `side_tie` slot → 3 种带子 RNG 分配（cord 3mm / cord 5mm / ribbon 15mm）
- `dangle ∈ [0.66, 0.94]`，飘带长度 11.2–15.2 cm

cup / fabric / hue / hardware / accessory **保持 RNG**，所以颜色和 cup 形状仍多样。

composite mean **0.785** ± 0.027（与 baseline 0.790 持平 — 钉死 4 个因子没显著降低多样性评分）。

## 怎么看挂带

正视图（`01_front.png`）因为飘带与相机平行，**看不太到**。
侧视图（`03_side_left.png`）和 3/4 视角（`02_three_quarter.png`）能清楚看到髋两侧的 RIBBON / CORD 飘带向下垂落。

特别推荐看：
- `tieside_04__bot_BRAZILIAN_M__tie_TIE_RIBBON_15MM/02_three_quarter.png` — 蓝色款，髋两侧蓝带最清楚
- `tieside_02__bot_BRAZILIAN_S__tie_TIE_RIBBON_15MM/03_side_left.png` — 绿色款，侧视图飘带条带感最强
