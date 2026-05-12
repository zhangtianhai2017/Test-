# 阶段性报告 — 2026-04-29

> 项目当前 commit：`2346653`
> 分支：`claude/bikini-variation-algorithm-Dv5q5`

## 方案：三层级联潜空间

```
Genome (44 dim, 设计意图)
    ↓ genome_to_garment
Garment (制造层：pieces / connectors / seams / fabrics，body-agnostic)
    ↓ deploy_to_body(body_mesh)
BodyDeployment (body-specific：piece→region 映射 + 解析 3D 锚点)
    ↓ render
3D mesh / .glb (游戏资产)
```

**核心思想**：游戏资产真实感不是渲染出来的，是被"能不能真做出来 + 能不能挂在身上"这条隐式约束逼出来的。把这条约束编码成中间潜空间，渲染层只是结果投影。每个三角面 / strap / accessory 必须能追溯到 latent state 的某条声明，否则不渲染。

## 已实现能力

### 算法层
- GA 遗传算法（pop=60、gens=12+、tournament-3 + 2-elitism、BLX-α 交叉、σ=0.08 高斯变异）
- 4 个支持的 archetype：`triangle_string_halter` / `bandeau_back_band` / `bralette_shoulder_strap` / `one_piece_maillot`
- 7 大设计原则 fitness（balance / proportion / harmony / emphasis / rhythm / unity / contrast）+ 4 个制造维度（manufacturability / sustainability / sku_consistency / construction_simplicity）

### 潜空间
- 44 维 Genome + Privacy seeds 硬约束（隐私部位必覆盖）
- 44 SKU 工业目录（12 fabric + 18 connector + 8 accessory + 6 seam type，每条都有行业引用）
- 10 个解剖命名 region + 拓扑推导锚点（acromion / scapula / clavicle / pelvis 自动检测）
- BodyMapping 每 piece 声明 covers + must_clear

### 渲染
- Open3D headless 渲染、cylindrical UV 展平、Taubin 平滑、闭合三次样条边界、解析半椭球模杯、4 mm FOE 包边、PatternPiece 自动缝合线、anatomy 锚点路由的 strap

### 自迭代闭环
- 8 机位渲染 → 多模态读图 → 结构化 critique JSON → 映射表翻译成参数 delta → 自动应用回退

## 量化效果

- **自迭代**：`composite_floral` 跑 10 轮，感知质量 **0.55 → 0.82**，high-severity issues **2 → 0**
- **种子规模**：3 真实 + 12 手工 + 20 自动合成 + 2 GA 派生 = **37 个种子**全部跑通管线
- **fitness 分布**：overall 0.616..0.891；with_garment 0.657..0.876
- **几何缺陷消除**：
  - 边缘锯齿 → 闭合三次样条曲线替换
  - 乳头透出 → Taubin 平滑 + 解析模杯
  - 手臂飞布 → torso 半径 + arm region 分类
  - 腿部覆盖 → pelvis 拓扑检测 + must_clear
  - 悬空件 → attachment 解析失败即丢弃

## 工业可解释性

每件衣服可以回答："多少片"、"什么布料 SKU"、"哪些五金"、"怎么缝合"、"哪条带挂在身体哪个解剖位"。`.glb` 文件 `extras["manufacturing_state"]` 字段直接携带 SKU JSON 供游戏引擎或人工审计。

## 关键文件

| 文件 | 内容 |
|------|------|
| `tools/verify_ga_uv.py` | Genome 定义 + 多边形生成 + GA 算子 |
| `tools/garment_state.py` | Garment / BodyDeployment 数据结构 + 级联函数 |
| `tools/anatomy.py` | 身体解剖检测 + 命名 region |
| `tools/catalogs.py` | 44 SKU 工业目录 |
| `tools/render3d_uv.py` | 渲染管线（cascade-aware） |
| `tools/garment_polish.py` | 几何后处理（平滑 / 模杯 / 边界曲线） |
| `tools/iter/` | 自迭代闭环（capture / params / diagnose） |
| `tools/fitness.py` | 7 设计 + 4 制造维度评分 |
| `tools/export_garment.py` | glTF 导出（带 manufacturing_state extras） |
| `docs/bikini-ga-algorithm.md` | GA 算法设计 |
| `docs/manufacturing-latent-state.md` | 中间层架构文档 |
| `docs/auto-iteration-loop-proposal.md` | 自迭代闭环方案 |
| `docs/anatomy-and-garment-construction.md` | 解剖 + 服装构造知识汇总 |

## 局限（v2 backlog）

- 圆柱 UV 在身体侧缝有图案拉伸 → v2 用 xatlas atlas 重打包
- 单一 NPC 网格 → v2 跨 avatar 验证（同一 Garment 部署到不同 BodyDeployment）
- Gusset 路径不沿身体表面（直管 + 中点下沉）
- BodyDeployment 只查 must_clear 交集（保守 = `{legs, arms, head, neck}`）→ 更细粒度的 piece-level 拒绝是 v2 工作
- 真实 2D flat-pattern unwrap（pattern_uv 仍是 body-cylinder UV）
- skinning weights / cloth simulation 参数 / LOD 链 / FBX 导出 — 端到端到 UE 还差这一段

## 视觉里程碑

- `tools/output/2026-04-29/0820_diverse_seeds/overview.png` — 20 自动合成种子
- `tools/output/2026-04-29/0918_bodymapping_legs_fixed/headline.png` — leg fabric bug before/after
- `tools/output/2026-04-29/1431_full_seed_batch/overview.png` — 37 seed 总览
- 历史 round_* 在 `tools/output/iter_composite_floral/` 系列里
