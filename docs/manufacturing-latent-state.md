# Manufacturing Latent State 中间层（v1：仅比基尼）

## Context

前 36 轮 polish 迭代之后发现：游戏资产的真实感不能靠继续调 polish 参数 / 几何加细节硬挤出来 ——
看着像贴在身上的胶布，不是衣服。**根因**：算法不知道这件衣服怎么裁、怎么缝、怎么挂上去的。

最终交付物**仍是游戏资产 .glb**（不做 Tech Pack / DXF）。但 pipeline 中间插一层 latent state，
把 pattern pieces / fabrics / connectors / seams / accessories / attachments 编码成可校验
的数据结构。这层 state 不直接交付，但同时承担两个角色：

1. **约束反传** — Genome 通不过 manufacturability 检查时回退 / projection
2. **真实感的来源** — mesh 上的缝合线、五金位置、配件挂载点都从这层 state 推导，不再是
   albedo 烤的假线、不再是 `g.has_oring` 这种 ad-hoc bool

## 架构

```
Genome (44 dims, 设计意图)
    ↓ genome_to_garment(genome, anatomy)               ← 物化 latent state
    ↓
Garment {
  archetype, pieces, fabrics, connectors,
  accessories, seams, attachments, metadata
}
    ↓ validate_garment(g)                              ← 硬约束 + projection + warnings
    ↓
build_strap_meshes(body, g) -> 公共 dispatcher          ← 构建几何
   ├ 三种 v1 archetype 走 garment-driven 路径
   └ 不支持 (one-piece) 透明 fallback 到 legacy
    ↓
.glb (extras["manufacturing_state"] 嵌入 SKU JSON)
```

中间层是 **in-memory dataclass**。.glb 导出时只在 `extras` 里写 SKU id（不写完整字典），
避开某些引擎 importer 64 KB 限制。引擎侧可读可不读，配套 LUT 解析。

## v1 范围

**仅比基尼两件式（two-piece）**。one-piece / monokini 由 `_detect_archetype` 显式 raise
`UnsupportedArchetypeV1`，dispatcher 透明回落到 legacy `_build_strap_meshes_legacy`。

三个 archetype（覆盖结构拓扑差异）：

| Archetype | 触发条件 | 例子 seeds |
|---|---|---|
| `triangle_string_halter` | `top_neck_strap > 0.4 and top_inner_u > 0.05` | `composite_red`, `swimsuit_2` |
| `bandeau_back_band` | 无肩带、halter 弱、cup_inner 接近 0 | `make_parents()` Parent B |
| `bralette_shoulder_strap` | `top_shoulder_strap > 0.5` | （目前无 seed） |

dispatch 优先级见 `tools/garment_state.py::_detect_archetype`：
```
if 一片式条件: raise UnsupportedArchetypeV1
if top_shoulder_strap > 0.5: bralette
if top_neck_strap > 0.4 and top_inner_u > 0.05: triangle
else: bandeau
```

## 数据结构（`tools/garment_state.py`）

- **EdgeRef** `(piece_id, edge_index, edge_name, side)` — 双键：integer index 给几何用，
  semantic name (`neckline / armhole / underbust / side_seam / leg_opening / waistband /
  inseam / center_front / back_seam / cup_inner / cup_outer`) 给 catalog matching 和 validator
- **PatternPiece** `id, role, polygon_uv, count, mirror_axis, fabric_id, layer_role
  ("shell"/"lining"/"padding"/"trim"), parent_id, grain_dir_deg, seam_allowance_cm,
  edge_names`
- **FabricRef / ConnectorRef / AccessoryRef** — value-copied from catalog SKU 当 Garment
  自包含（避免 catalog 重 import 才能解 .glb）
- **Connector.path_policy** ⭐ 关键字段，8 种枚举决定 strap 怎么走（halter_behind_neck,
  shoulder_acromion_scapula, side_tie_hip_vertical, back_band_horizontal,
  underbust_horizontal, waist_band_horizontal, center_gore_static, free_anchored）
- **Seam** `id, edge_a, edge_b (optional), seam_type_id, elastic_id, finish, visible`
- **Attachment** 把 connector / accessory 钉在 (a) seam 上参数 t∈[0,1] 或 (b) anatomy_anchor
- **Garment** 顶层；`flatten_polygons()` back-compat 给 build_fabric_shell / polish_shell

**对称性** 用 `count=2, mirror_axis="u"`（不展两个 piece，符合工业 cut-list "Cup × 2 (mirror)"）。

**分层** foam cup → `parent_id=cup, layer_role="padding"`；powermesh 内衬 →
`parent_id=cup, layer_role="lining"`。当 `g.fabric_opacity < 0.92` 自动加内衬。

## Discrete Catalogs（`tools/catalogs.py`）

总共 **44 个 SKU**，手工 author + 引用注释：

| Catalog | size | 关键覆盖 |
|---|---|---|
| **FABRICS** | 12 | 7 weave × 重量/source 变体（ECONYL light/heavy, Q-NOVA ribbed, Velvet, Hunza crinkle, Missoni shiny knit, mesh, powermesh, EVA foam 3 mm, crochet cotton, biopolymer, Amni Soul ribbed） |
| **CONNECTORS** | 18 | 3 O-ring × metal、3 sliders、3 FOE 弹性宽度（10/15/25 mm）、3 tie strings、3 straps、3 specialty（halter cord, underbust elastic, waist elastic） |
| **ACCESSORIES** | 8 | bow/shell/pendant/fringe/2 beads/tassel/ring_charm |
| **SEAM_TYPES** | 6 | 4-thread overlock、3-needle coverstitch、FOE 1"、FOE 5/8"、bartack、flatlock |

**Snapping 是确定的**（argmin distance、不用 RNG）。`snap_oring(0.75, "gold") → OR_8MM_GOLD`，
同一个 Genome 永远 snap 到同一个 SKU。

## 约束（`validate_garment`）

**硬规则**（违反 → 删片 / 删 seam + warning 记录到 `garment.metadata.validation_warnings`）：

- **H1** PatternPiece 体面积 > 8 cm²（Bra-Makers Supply 工业最小可缝杯片）
- **H2** 多边形非自交（射线-段相交检查）
- **H3** 配对 seam 两边 edge 的 body-cm 长度差 ≤ ±8%（针织弹性面料工业容差；非弹机织用 2%）
- **H4** 每个 fabric_id / connector_id / accessory_id / seam_type_id / elastic_id 都在 catalog 里

**软规则**（warning，不阻断）：

- **S1** 高张力 piece（cup / underband / back_band_panel）的 grain_dir 应对齐到身体环向 stretch 轴
- **S2** seam_type_id 与 fabric.weave 兼容（每个 SeamType.fabric_compat 元组列出兼容 weave）

## 渲染端集成

`tools/render3d_uv.py::build_strap_meshes`（cutover 后的公共名字）：

```python
def build_strap_meshes(body_mesh, g, y_crotch, y_neck):
    try:
        garment = validate_garment(genome_to_garment(g))
        return _build_strap_meshes_garment(body_mesh, garment, g, ...)
    except UnsupportedArchetypeV1:
        return _build_strap_meshes_legacy(body_mesh, g, ...)
```

`_build_strap_meshes_garment` 不再扫 `g.has_oring / g.has_bow / g.top_shoulder_strap`，
而是 iterate `garment.connectors / .accessories / .attachments`，按 Connector.path_policy
和 Attachment.anatomy_anchor 路由。复用 `_arc_tube / _build_band_mesh / _build_tie_mesh /
_body_ring / _body_point_at` 等 primitive。

## glTF extras

`tools/export_garment.py` 在 `out.metadata["extras"]["manufacturing_state"]` 写
`garment.sku_summary()` —— 只包含 SKU id（fabric_id / connector_id / accessory_id /
seam_type_id），不嵌完整字典。引擎侧（UE / Unity / Three.js）按需 LUT 解析。

UnsupportedArchetypeV1 的 Genome 写 `extras["manufacturing_state_error"]`，便于追踪。

## 验证

| 检查 | 状态 |
|---|---|
| catalog 大小 12+18+8+6 | ✅ pinned by assert |
| 3 seeds round-trip Genome → Garment → validate | ✅ composite_red/swimsuit_2 → triangle_string_halter；composite_floral → 显式 raise |
| validate_garment 在真实 seeds 上不删 piece | ✅（仅 warnings：seam_inseam_R 32% 不匹配是真实几何偏差） |
| v1 vs v2 render-diff | ✅ overall L1 = 0.16% (target < 2%) |
| 故意 oring_size=0.42→snap to 8 mm SKU | ✅ `snap_oring(0.75, "gold") → OR_8MM_GOLD` |
| .glb extras carries manufacturing_state SKU JSON | ✅ trimesh.load 后 `m.metadata["extras"]["manufacturing_state"]` 可取 |

## 文件清单

**新增**：
- `tools/catalogs.py` — 4 个 dict + snap_* 辅助
- `tools/garment_state.py` — dataclasses + `genome_to_garment` + `validate_garment` + sku_summary
- `docs/manufacturing-latent-state.md` — 本文档

**修改**：
- `tools/render3d_uv.py` — 加 `_build_strap_meshes_garment` (原 v2)、保留 `_build_strap_meshes_legacy`
  (原 v1)、新公共 dispatcher `build_strap_meshes`
- `tools/iter/capture.py` — 删 USE_GARMENT_V2 env-var 分支，直接调公共 dispatcher
- `tools/export_garment.py` — 在 .glb metadata.extras 嵌入 manufacturing_state SKU JSON

**保持兼容**：
- `tools/anatomy.py` 全部
- `tools/garment_polish.py` 全部
- `tools/verify_ga_uv.py` 仅 import private polygon helpers，不改源
- 所有 GA / fitness / iter loop / seed_loader 不动

## v2 规划（不在 v1 范围）

- 一片式 / monokini archetype（`one_piece_maillot` / `one_piece_lace_back`）
- 真实 2D flat-pattern unwrap（当前 `polygon_uv` 仍是 body-cylinder UV）
- Garment-aware fitness（fitness.py 加 SKU 多样性 / 可持续性维度）
- 把 `extras["manufacturing_state"]` 引擎侧脚本（UE Python / Unity C#）做 import-time LUT 解析
- shoulder ridge / gusset 控制点从 anatomy 局部曲率推导（去除 mesh-tuned 常量）
