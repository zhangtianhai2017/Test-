# hip_strap as a first-class library element

## 用户反馈链

1. "之前的下身布片没有东西挂着" → 我加了硬编码 `hip_band` 渲染（错的层）
2. "比基尼侧面是布条/绳子/缎带，不是布片" → schema 层缺这个建模
3. "这是不是是在最初的描述成的这个潜空间和标签上少了的这个东西？" → **是的**
4. "把这部分补上，但不强制，元素而已" → 这次实现
5. "C 裤无侧带也合法，只是少见" → schema 允许（optional slot 留空）
6. "wearability 是唯一强制" → 加了 O7 rule

## Schema 改动

### 库扩展（`tools/library_data.py`）

3 条新的 STR_HIP_* 条目（hip-side 专用）：

```
STR_HIP_ELASTIC_8MM    width=0.8cm  tags=("hip_side", "elastic", "thin")
STR_HIP_ELASTIC_15MM   width=1.5cm  tags=("hip_side", "elastic")
STR_HIP_BAND_SPORT_25MM width=2.5cm  tags=("hip_side", "elastic", "wide", "sport")
```

现存 3 条 STR_TIE_* 加 `hip_side` tag → 也能填 hip_strap slot：
```
STR_TIE_CORD_3MM, STR_TIE_CORD_5MM, STR_TIE_RIBBON_15MM
```

合计 6 条候选，width 0.3 — 2.5 cm 全谱。

### Slot 模板（`tools/library.py::ARCHETYPE_SLOTS`）

`bandeau_back_band` / `bralette_shoulder_strap` / `one_piece_maillot` 三个
archetype 都加：

```python
SlotSpec("hip_strap", "strap_piece", required=False,
          allowed_tags=("hip_side",))
```

`triangle_string_halter` 已经有 `side_tie` slot（功能等价），不重复加。

### 渲染（`tools/render3d_uv.py`）

撤掉 commit 20ea30b 加的硬编码 `hip_band_R/L`。改为：
- 任何 connector 锚点为 hip_R/hip_L 都触发渲染
- 宽度由 `connector.width_cm` 决定（之前固定 1.2cm）
- C 裤（slot 留空）→ 不渲染任何 hip 几何，wearability 通过前后片 polygon 在 u=±0.5 相邻保证

### Wearability 硬规则（`validate_outfit::O7`）

```
O7  cup 已填且 archetype 提供 anchor slot 时，至少有一条 anchor strap
    （halter / shoulder / back_band / underbust）必须填充。否则 cup 会掉。
```

不检查 hip_strap — 裤子的 wearability 由 polygon 几何隐含。

## Demo 输出

- `overview.png` — 正视图 5×3
- `overview_side.png` — 侧视图 5×3（hip_strap 几何最清晰）

| 列 | hip_strap | width |
|---|---|---|
| 1 | `(none)` C 款 | — |
| 2 | `STR_TIE_CORD_3MM` | 0.3 cm 细绳 |
| 3 | `STR_TIE_RIBBON_15MM` | 1.5 cm 缎带 |
| 4 | `STR_HIP_ELASTIC_15MM` | 1.5 cm 平松紧 |
| 5 | `STR_HIP_BAND_SPORT_25MM` | 2.5 cm 运动宽带 |

侧视图清晰看到宽度梯度（细绳 → 缎带 → 松紧 → 运动带）。column 1 (C 款)
完全没有 hip 处几何，对应"少见但合法"的真实款式。

## 副作用：迁移修复

`genome_to_outfit` 给 `one_piece_maillot` 加 fallback：当
`top_shoulder_strap < 0.15` 时自动加 `STR_FOE_15MM` 到 `underbust` slot。
之前 2 个 v1 seed (`diverse_one_17`, `gallery_onepiece_halter_terracotta`)
迁移后会触发 O7（cup 无锚点）；现在 37/37 全部通过。
