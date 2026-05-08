# Component Library v2 — 真实特征保留型潜空间

**Status:** implemented (Phase A + B + C complete)
**Commits:** 427b360 (Phase A) · 9d180a6 (Phase B) · 2d0d1fe (Phase C / Step 6) · this commit (Step 7)
**Last updated:** 2026-05-08

---

## 1. 为什么改 v1

v1 的级联是 **Genome (44-dim float) → Garment → BodyDeployment → mesh**。
Genome 的核心字段（`top_half_u`、`top_inner_u`、`bot_front_top_v` …）是**连续浮点 + 数学公式**，
`_cup_polygon(g)` 直接根据这些浮点切多边形。
问题：**浮点之间的中间值会产生现实里不存在的款型**——既不是 Brazilian 也不是 Balconette
的"四不像"，制造端无法解释，GA 把分数推上去也只是数学上的最优而非工艺上的最优。

v2 的解法：**最前端先有"组件库" latent space**。
每个组件（杯片 / 底片 / 带子 / 五金 / 装饰 / 上身配饰 / 面料）都有自己的潜空间，
**但这个潜空间是真实特征保留型**——同一条目内的 `local_params`（颜色、尺寸、深浅）允许连续变化，
**跨条目（A 款 → B 款）必须显式切换 library_id，不允许数学插值**。

---

## 2. 架构

```
[Component Library]            (NEW — primary latent space)
  cup_pieces / bottom_pieces / strap_pieces /
  hardware / accessories / fabrics / body_jewelry / seam_types
        │
        │  archetype slot template
        ▼
[Outfit]                       (NEW — chromosome layer)
  archetype + slot_assignments + global_design
        │
        │  outfit_to_garment(anatomy_landmarks)
        ▼
[Garment]                      (existing — geometric data classes)
        │
        │  deploy_to_body(body_mapping)
        ▼
[BodyDeployment]               (existing)
        │
        │  build_strap_meshes / fabric_shell / body_jewelry
        ▼
3D mesh / .glb
```

每层职责清楚分离：

| 层 | 责任 | 不做什么 |
|---|---|---|
| Library | 离散目录 + 真实款 + 兼容性 | 不做几何变换 |
| Outfit | "这件衣服由哪些库条目装配" + 全局设计 | 不切多边形 |
| Garment | 多边形 / 接缝 / 连接器的纯几何描述 | 不知道身体 |
| BodyDeployment | 把 Garment attach 到具体 body anatomy | 不渲染 |
| mesh | 实际 3D 几何 | 不知道库 |

---

## 3. Library Schema (`tools/library.py` + `tools/library_data.py`)

### LibraryEntry

每个条目是 **kitchen-sink 形 dataclass**——8 种 kind 共享字段，每 kind 用到自己的子集：

```python
@dataclass(frozen=True)
class LibraryEntry:
    id: str              # e.g. "CUP_TRI_M"
    kind: str            # 见下表 LIBRARY_KINDS
    name: str
    tags: tuple[str, ...]                  # 用于 SlotSpec.allowed_tags 匹配
    compatible_with: tuple[str, ...]       # 必须共存的其他 library_id
    incompatible_with: tuple[str, ...]
    anatomy_hints: dict                    # → Attachment.anatomy_anchor
    local_params_schema: dict              # param_name → (lo, hi, default)
    base_polygon_recipe: str               # geometry_kind → polygon_recipes registry key
    # kind-specific: jewelry_form / size_class / hardware_form / accessory_form
    # / fabric_props (E_warp/E_weft/density)…
```

### LIBRARY_KINDS

| kind | 数量 | 说明 |
|---|---|---|
| `cup_piece` | 15 | 5 geometry_kind × 3 size_class — triangle / balconette / bandeau / molded_foam / softcup_squareneck |
| `bottom_piece` | 10 | 5 geometry_kind × 2 size_class — thong / brazilian / cheeky / brief / high_waisted |
| `strap_piece` | 13 | halter / shoulder / side_tie / FOE / padded_strap / **back_band**（bandeau 必需） |
| `hardware` | 10 | o_ring / d_ring / sliders / clasps |
| `accessory` | 10 | charm_*, ruffle, hem_lace, side_bow … |
| `fabric` | 12 | 12 真实面料（jersey / mesh / velvet / lycra / foam_cup / …）+ E_warp/E_weft/density |
| `body_jewelry` | 10 | bracelet / anklet / necklace_choker / necklace_pendant / earring_drop/stud / body_chain_waist/belly **(NEW v2)** |
| `seam_type` | 6 | flatlock / lockstitch / bound / overlock |
| **总计** | **86** | 手写离散条目 |

### local_params 的"真实特征保留"语义

举例：`CUP_TRI_M`（triangle 杯，M 号）的 local_params_schema：

```python
local_params_schema = {
    "wing_extension": (0.85, 1.15, 1.00),   # 翼宽 ±15%
    "depth": (0.92, 1.08, 1.00),            # 深度 ±8%
    "tip_height": (-0.05, 0.05, 0.00),      # 尖端 ±5%
}
```

这个空间内任意取值都还是一只 **可识别的 triangle 杯**。
要变成 balconette，必须 **library_id 切换到 CUP_BAL_M**——不允许浮点插值越界。
GA 在跨款时只能做 `library_id` 离散重采样，款内做 BLX-α 连续交叉。

---

## 4. Archetype Slot Template (`tools/library.py::ARCHETYPE_SLOTS`)

4 个 archetype，每个一份 SlotSpec list：

```python
ARCHETYPE_SLOTS = {
    "triangle_string_halter": [
        SlotSpec("cup",            "cup_piece",    allowed_tags=("triangle","brazilian")),
        SlotSpec("bottom_front",   "bottom_piece", allowed_tags=("thong","brazilian","cheeky")),
        SlotSpec("bottom_back",    "bottom_piece", required=False),
        SlotSpec("halter_strap",   "strap_piece",  allowed_tags=("halter",)),
        SlotSpec("side_tie",       "strap_piece",  allowed_tags=("tie",)),
        SlotSpec("oring",          "hardware",     required=False, allowed_tags=("o_ring",)),
        SlotSpec("primary_fabric", "fabric"),
        SlotSpec("accessory",      "accessory",    required=False, max_count=2),
        SlotSpec("body_jewelry",   "body_jewelry", required=False, max_count=3),
    ],
    "bandeau_back_band":       [...],   # 包含 back_band slot
    "bralette_shoulder_strap": [...],
    "one_piece_maillot":       [...],
}
```

**多样性下限**：每个 SlotSpec 的 `(kind, allowed_tags)` 至少能匹配 ≥2 个库条目
（验证脚本 `entries_matching_slot()` 全部通过）。

---

## 5. Outfit dataclass (`tools/outfit.py`)

```python
@dataclass(frozen=True)
class SlotAssignment:
    slot_name: str
    library_id: str
    local_params: dict[str, float]

@dataclass(frozen=True)
class Outfit:
    archetype: str
    slot_assignments: tuple[SlotAssignment, ...]
    global_design: dict   # hue / pattern_overlay / palette_preset
```

### 关键函数

| 函数 | 作用 |
|---|---|
| `random_outfit(archetype, rng)` | 按 archetype slot 模板采样合法 Outfit；自动解决 `compatible_with`（如 foam cup 必带 foam fabric） |
| `outfit_to_garment(outfit, anatomy=None) -> Garment` | 遍历 slot_assignment → 查 library entry → 调 `polygon_recipes.<base_polygon_recipe>(local_params)` → 拼 Garment |
| `outfit_to_genome(outfit) -> Genome` | 有损投影回 v1 Genome（fitness 老代码 / 老 seeds 用） |
| `genome_to_outfit(genome) -> Outfit` | v1 老种子上行——把 Genome 字段 snap 到最近 library entry，archetype-aware bottom 选择（不会把 high_waisted 配到 triangle_string_halter） |
| `validate_outfit(outfit) -> list[str]` | O1–O6 hard rules：archetype 已知 / required slot 满足 / library_id 在 catalog / kind 匹配 / tags 命中 / compatible_with 不冲突 |

---

## 6. Polygon Recipes (`tools/polygon_recipes.py`)

把 v1 `verify_ga_uv.py` 里的 `_cup_polygon`/`_back_top_polygons`/`_bottom_front_polygon` 等
**几何函数从 Genome 解耦**——现在每个 recipe 接 `local_params` dict（不接 Genome），
通过 `RECIPES` 注册表按 `geometry_kind` 派发：

```python
RECIPES = {
    "cup_triangle":     cup_triangle,
    "cup_balconette":   cup_balconette,
    "cup_bandeau":      cup_bandeau,
    "bottom_thong":     bottom_thong,
    "bottom_brief":     bottom_brief,
    "back_bottom_strips": back_bottom_strips,
    "side_tie":         side_tie,
    "back_top_band":    back_top_band,    # bandeau 用
    "center_gore":      center_gore,
}
```

验证：v2 `cup_triangle(local_params)` 在与 Parent A 默认 local_params 同时
能 bit-exact 复现 v1 `_cup_polygon(g)` 的 polygon。

---

## 7. GA Operators (`tools/iter/outfit_ga.py`)

GA chromosome 从 **44-dim Genome 浮点向量** 升级为 **Outfit**。

| op | 行为 |
|---|---|
| `crossover(a, b, rng)` | 必须同 archetype（异 archetype crossover = 整片复制父亲，沿用 v1）；逐 slot 二选一：相同 library_id 的 slot 做 BLX-α (alpha=0.25) 交叉 local_params；不同 library_id 的 slot 50/50 整片继承 |
| `mutate(outfit, rng, p_id=0.05, sigma=0.10)` | 每 slot p_id 概率 library_id 重采样到 allowed subset；local_params 高斯扰动 σ=0.10 clamp 到 schema range；global_design HSL 高斯 |
| `_heal_invalid(child, parent)` | 任何子代如果 `validate_outfit` 不通过，回滚 offending slot 到 parent 值 |
| `evolve(parent_a, parent_b, pop_size, gens, rng)` | tournament-3 + 2-elitism；测试结果 mean 0.772→0.857，max 0.844→0.895 |

---

## 8. 上身配饰渲染（Step 6 / Phase C）

新加的 anatomy 锚点（`tools/anatomy.py`）：
- `wrist_R/L`, `forearm_R/L`, `bicep_R/L` （从肩 acromion 沿手臂沿 fraction 0.85/0.65/0.30）
- `earlobe_R/L` （head sphere 上沿）
- `ankle_R/L` （脚跟 + 脚踝 offset）
- `belly_button` / `navel`（hip ridge 中点）
- `neck_front`（neck base + offset）

`tools/garment_state.py::_resolve_anchor` 扩展 11 个新 case 路由到上面的 anatomy 函数。

`tools/render3d_uv.py::_build_body_jewelry_meshes` 按 `jewelry_form` 派发：
- `bracelet/anklet/choker` → torus
- `necklace_pendant` → arc tube + pendant sphere
- `earring_drop` → stem + drop sphere（自动 mirror L/R）
- `body_chain_waist/belly` → 闭合 / 开放链条带

走 `valid_jewelry_ids` 过滤，与 strap meshes 同样的 accountability 模式。

---

## 9. 迁移 + v1 兼容性（Step 7）

### v1 → v2 自动迁移：`tools/seed_to_outfit.py`

```bash
python3 tools/seed_to_outfit.py            # 全部 37 seeds
python3 tools/seed_to_outfit.py composite_red   # 单 seed
```

每个 `assets/seeds/*.json` 通过 `seed_to_genome → genome_to_outfit` 反向工程到 Outfit，
连同原 Genome 一起写到 `assets/seeds_v2/<name>.json`：

```json
{
  "meta": { "migrated_to_v2": "2026-04-29", ... },
  "genome": { /* 原 v1 Genome 完整保留 */ },
  "outfit": {
    "archetype": "triangle_string_halter",
    "slot_assignments": [...],
    "global_design": {...}
  },
  "outfit_validation": { "valid": true, "warnings": [] }
}
```

**结果：37/37 全部 valid**，archetype-aware bottom 选择修复了 `diverse_triangle_*`
之前会被分配 high_waisted 的 bug。

### Render pipeline v2 优先（`tools/iter/capture.py`）

```python
if params.outfit is not None:
    garment = outfit_to_garment(params.outfit, anatomy=landmarks)
    polys_uv = garment.flatten_polygons()
else:
    garment = genome_to_garment(g)         # v1 fallback
    polys_uv = build_uv_pieces(g, ...)
```

`tools/iter/params.py::IterParams` 新增 `outfit: object = None` 字段——任何老 caller 不动，
只要 caller 显式 set `params.outfit = my_outfit`，pipeline 立刻走 v2。

---

## 10. 验证

| 测试 | 结果 |
|---|---|
| 库 smoke：86 条目 + 8 kinds + ARCHETYPE_SLOTS 4 archetype | ✓ |
| Slot 多样性下限：每个 SlotSpec ≥2 库条目可匹配 | ✓（修复 bandeau back_band 后） |
| Outfit round-trip：5 个随机 Outfit → garment → validate 无硬错 | ✓ |
| v1 兼容：37 seeds → outfit_to_garment 渲染（296 PNG） | ✓ — 见 `tools/output/2026-05-08/0337_v2_full_batch/` |
| 上身配饰渲染：bracelet+necklace 在 wrist/neck 命中、不渲到非法位置 | ✓ |
| GA 兼容：outfit_ga.evolve 8 代 max fitness 0.844→0.895，无退化 | ✓ |

---

## 11. 关键文件

**新增（v2 主体）：**
- `tools/library.py`          — LibraryEntry / SlotSpec / ARCHETYPE_SLOTS / validate_outfit
- `tools/library_data.py`     — 86 个手写库条目
- `tools/polygon_recipes.py`  — 9 个 polygon recipe（从 verify_ga_uv 抽出）
- `tools/outfit.py`           — Outfit + outfit_to_garment + 双向 Genome 投影
- `tools/iter/outfit_ga.py`   — Outfit-level GA
- `tools/seed_to_outfit.py`   — v1→v2 迁移
- `assets/seeds_v2/*.json`    — 37 个迁移过来的 v2 seed

**重构：**
- `tools/anatomy.py`          — 加 wrist/earlobe/ankle/bicep/forearm/belly_button/neck_front
- `tools/garment_state.py::_resolve_anchor` — 11 个新 anchor case
- `tools/render3d_uv.py`      — `_build_body_jewelry_meshes` + 8 jewelry primitive
- `tools/iter/capture.py`     — v2 优先，v1 fallback
- `tools/iter/params.py`      — 加 `outfit` 字段

**复用不动：**
- `tools/garment_polish.py` / `build_fabric_shell` / `polish_shell`
- `tools/iter/{params,diagnose,loop,build_trajectory}.py`（除 params 加一个字段）
- `tools/output_paths.py` / `tools/build_html_index.py`
- `tools/fitness.py`（Genome-based，通过 outfit_to_genome 回兼容）

---

## 12. 下一步

完整 v2 7 步已经完成。后续改进方向：
1. **库扩展**：当前 86 条目，可继续加 (a) 高端泳装的 cutout / mesh paneling 杯款，
   (b) 更多 body jewelry 形态（waist beads / arm chain / nipple chain），
   (c) 季节性面料（terry / corduroy / metallic）。
2. **前端编辑器**：现在 Outfit 是 dataclass + JSON，可以做一个纯 Web 的可视化
   slot picker（archetype 下拉 → 每个 slot 一个 thumbnail grid）。
3. **fitness 函数 v2**：当前 `tools/fitness.py` 还是 Genome-based。
   可以加一个 `outfit_fitness(outfit)` 直接用 library 元数据评估
   （兼容性 / anatomy_hints 完整度 / 制造工序复杂度等），把 GA loop 完全脱离 Genome。
