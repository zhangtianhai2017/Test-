# 从 GA 输出到 UE 可用资产的中间环节（Bake / Export Pipeline）

GA 跑完之后，我们手里只是一组**参数 + 一张纹理**。距离一件能直接拖进 Unreal Engine、跟着 MetaHuman 骨骼走、还能让 Chaos Cloth 模拟摆动的"可游戏资产"，中间还隔了**九个 stage 的工程化烘焙过程**。本文把这些 stage 全部拆开说明，并给出最小可运行的原型 `tools/export_garment.py`。

---

## 0. 现在我们手里有什么 vs. 引擎需要什么

| 维度 | GA 当前输出 | UE Chaos Cloth 需要的 |
|------|------------|---------------------|
| 几何 | UV 上的多边形（参数化） | **独立的服装三角网格** OBJ/FBX/glTF |
| 网格拓扑 | 借用人体三角面（offset 3 mm） | 不依赖人体网格的 standalone garment mesh |
| UV | 圆柱展开（共用 body 的 UV） | **服装专属 atlas UV**（高密度区给胸 / 腰带） |
| 纹理 | 一张 albedo（程序化烘焙） | **PBR 纹理组**：albedo + normal + roughness + metallic + AO + opacity |
| 材质 | 程序生成的 PIL 图像 | glTF/FBX 中的 PBRMetallicRoughness 材质，参数可在 UE Material Editor 调节 |
| 蒙皮 | 无 | **顶点权重**绑到 MetaHuman 骨骼（Spine_03、Clavicle 等约 8 根骨骼） |
| 物理 | 无 | Chaos Cloth 顶点画：`MaxDistance` / `BackstopRadius` / `Stiffness` |
| 碰撞 | 无 | 简化的 Capsule / Tapered Capsule，约 4 个碰撞体覆盖躯干 |
| LOD | 无 | LOD0（满）/ LOD1（½）/ LOD2（¼）三级 |
| 元数据 | Genome 字典 | 属性表（archetype / fabric_source / sustainability tags） |

中间环节就是要把左列变成右列。下面九步逐一说明，**带 ⭐ 是 `tools/export_garment.py` 已经实现的，⛏ 是当前留作 TODO 的**。

---

## Stage 1 ⭐ 服装网格抽取（Garment Mesh Extraction）

GA 把比基尼描述为 UV 平面上的若干闭合多边形（top 杯片 / bottom 前后片）。要变成真正的服装网格，做法是：

1. 对人体网格做圆柱展开 `cylindrical_uvs`，每个三角面拿到三个 UV。
2. 对每个 Genome 多边形，用 `matplotlib.path.Path.contains_points` 标记**三个 UV 全部落在多边形内部**的三角面。
3. 这些三角面沿顶点法线**外推 0.3 cm** 得到一层薄壳（fabric shell），就是服装的主体。
4. 在 shell 的边界边检测出**开口环（boundary loops）**，在每条 boundary edge 上长出一圈 0.05 cm 厚 / 0.15 cm 高的 **rim 几何**（binding）—— 模拟弹性包边。
5. 单独建立 **strap 几何**：
   - 颈带 / 肩带 / 后背带 / 侧腰带 / 流苏 / 蝴蝶结 / 串珠 / 贝壳挂件
   - 都是若干段 `_arc_tube`（六棱柱）从胸口或腰部 anchor 点延伸出来。
6. 全部合并成**一个 trimesh.Trimesh**。

> 已经实现，复用 `render3d_uv.build_fabric_shell / build_binding_mesh / build_strap_meshes`。<br>
> 在 `composite_red.glb` 上跑出 ~3 k 三角面，`composite_floral.glb` 上 ~32 k 三角面 —— 后者大是因为是连体泳衣覆盖范围广。

**已知问题**（v0.1 留作下一版处理）：
- 当前 shell 顶点数等于参与的 body 顶点数；引擎里建议先做一遍 `mesh decimation`（QEM 算法）压到 1 k–2 k 三角面再用。
- shell 顶点位置完全继承自人体网格，所以 garment 不会和人体有空气层，物理模拟会黏住。下一步要把 shell 从 body 单独剥离（不共享顶点），然后整体 backstop 0.5 cm。

---

## Stage 2 ⭐ Atlas UV 重绘（Atlas Repacking）

shell 的 UV 是从人体圆柱展开继承的。这有个问题：圆柱展开下**胸部和侧腰的纹理密度差 3–4 倍**，肩带这种细长几何在 atlas 上会变成一根针，烘焙时分辨率不够。

**v0.1（已实现）**：
- 直接复用圆柱 UV 喂给 shell。
- straps / binding 的 UV 全部固定指向纹理底部一条 16 像素高的 trim color 条带 → 这些部分就是纯色，不需要 UV 精度。

**v1（TODO ⛏）**：
- 用 [`xatlas`](https://github.com/jpcy/xatlas) 对合并后的 garment 网格做 **conformal atlas packing**：保持角度，像素密度均匀，自动找接缝。
- 输出 4096 × 4096 atlas，比胸 / 侧腰 / 后腰之间分配均匀。

---

## Stage 3 ⭐ Albedo 纹理烘焙

`render3d_uv.genome_to_texture()` 已经把 Genome 的 12 种 pattern（solid / stripes / dots / gingham / floral / chevron / ombre / tiedye / leopard / camo / mesh_grid / abstract）烘成 1024 × 512 圆柱图。我们：

- 顶部 1024 × 512 = 上述烘焙结果。
- 底部 1024 × 16 = 实色 trim（根据 `trim_color_mode` 决定与主色一致还是反差强烈）。
- 整体导出为 glTF `baseColorTexture`。

---

## Stage 4 ⛏ 法线 / 粗糙度 / 金属度 / AO 纹理

引擎里布料质感主要靠 **normal map** 表现织纹。`render3d_uv` 里已经有 `_fabric_normal_map / _crinkle_normal_map / _ribbed_normal_map / _mesh_normal_map / _velvet_normal_map`，但当前只用于离线渲染。要烘进 glTF 还差三步：

1. 在 atlas 空间生成 1024 × 528 normal map（reuse 上面五种之一，由 `fabric_weave` 决定）。
2. 在皱褶位置（皮肤张力高的胸下围、腰侧）叠一层低频 noise normal —— 复用 `apply_wrinkles` 的 trig pseudo-noise，但烘成纹理而不是几何位移。
3. metallic / roughness 我们已经写到了 PBR 材质的标量字段（`metallicFactor` / `roughnessFactor`），如果想做有变化的（例如金属丝刺绣区域），需要再烘一张 metallic-roughness 双通道 PNG。

> 这一阶段是 v0.1 → v1 之间**最重要的视觉提升**。

---

## Stage 5 ⛏ 蒙皮权重传递（Skin Weight Transfer）

UE 期望 garment 的每个顶点附带 4 根骨骼 + 4 个权重。从 MetaHuman 默认骨骼里挑约 8 根相关：

```
spine_03 / spine_04 / spine_05 / clavicle_l/r / upperarm_l/r / pelvis
```

最简单的策略是 **closest-bone-on-skeleton**：对每个 garment 顶点找到最近的人体顶点，复制人体顶点的权重数组。
精细做法：**bind-pose smooth voxel transfer**（参考 Unreal 的 `Cloth Painting` 工具或 Blender 的 *Data Transfer modifier*）。

**输出格式**：glTF 2.0 支持 `JOINTS_0` + `WEIGHTS_0` accessor，FBX 直接走 `Skin` 节点。

---

## Stage 6 ⛏ Chaos Cloth 顶点画（Vertex Paint）

这是 UE 物理布料的核心。每个顶点画三个值：

| 通道 | 含义 | 取值范围 | Genome 驱动 |
|------|------|---------|------------|
| `MaxDistance` | 顶点最多能离 reference pose 多远 | 0–5 cm | 边缘 / 流苏 → 大；胸口 / 腰带 → 小 |
| `BackstopRadius` | 反向穿透屏障（防止穿入身体） | 0.5–1 cm | 取决于 `fabric_opacity` |
| `Stiffness` | 抗拉刚度 | 0–1 | 由 `fabric_weight` × `single_material` 推 |

写法：自动给 garment 顶点加 vertex color 通道，R/G/B 各编码一个值。UE 导入后在 `Cloth Painting` 面板 `Convert Vertex Color → Cloth Param`。

---

## Stage 7 ⛏ 简化碰撞体（Physics Asset）

Chaos Cloth 不直接用人体网格做碰撞 —— 太贵。要给每个 MetaHuman 配一个 **简化碰撞体**：4–6 个 capsule 覆盖躯干。我们的 NPC 网格上：

- 胸部：tapered capsule，沿 `spine_05`，r=14 cm → 12 cm，长 35 cm
- 腰：capsule，r=11 cm，长 18 cm
- 髋：capsule，r=12 cm，长 14 cm
- 左 / 右大腿上半段：capsule，r=8 cm

这些写在 `*.uasset` Physics Asset 里。导出时我们在 .glb 的 `extras` 字段塞一个 JSON，UE 端用 Python 脚本读出来生成 `PhysicsAsset`。

---

## Stage 8 ⛏ LOD 链生成

Unreal 期望每件衣服带 3 级 LOD。用 `pyMesh` 或 `pymeshlab` 的 **Quadric Edge Collapse Decimation** 自动生成：

```
LOD0 = 100% triangles  (game distance < 5 m)
LOD1 = 50%             (5–15 m)
LOD2 = 25%             (15+ m, cloth simulation off)
```

UV 连续性 / 蒙皮权重要在 decimation 中保持，否则 LOD 切换会有瞬移。

---

## Stage 9 ⭐ 导出格式 & 元数据

**glTF 2.0（推荐做交换格式）**：

- 单文件 `.glb`：网格 + UV + 纹理 + 材质 + （TODO）骨骼 + （TODO）顶点权重，全部嵌入。
- 我们用 `trimesh.Trimesh.export(.glb)`，PBR 材质字段：`baseColorTexture` / `metallicFactor` / `roughnessFactor` / `doubleSided=True` / `alphaMode`。
- 文件大小：纯 albedo + 材质大约 200 KB（小比基尼）到 1.7 MB（连体）。

**FBX（UE 原生路径）**：

- 用 [`Blender headless`](https://docs.blender.org/manual/en/latest/advanced/command_line/render.html) 把 glTF 转成 FBX 并补 skinning + collision metadata，或者用 Autodesk FBX SDK 直接写。
- UE 导入时 `Skeletal Mesh` 可以直接用 MetaHuman 的骨骼，材质会自动转成 `M_Bikini` 实例。

**glTF extras**（我们额外塞的元数据）：

```json
{
  "ga_genome": { ...44 fields... },
  "fitness": { "overall": 0.984, "harmony": 0.91, ... },
  "seed_provenance": { "seed_a": "composite_red", "seed_b": "composite_floral" },
  "physics_hint": { "capsules": [...], "max_distance_max": 4.0 }
}
```

---

## 端到端最小可运行原型：`tools/export_garment.py`

实现了 Stage 1–3（mesh 抽取 + atlas 复用 + albedo 烘焙 + PBR 材质常量），**不带骨骼 / 不带物理 / 不带 LOD**，但产出一个**能在 Blender / Three.js / glTF Viewer / Unreal 4.27+ 直接打开的 .glb**。

```bash
python3 tools/export_garment.py composite_floral
# -> tools/output/glb/composite_floral.glb (1.7 MB)
```

输出统计（带回示例）：

| Seed | Vertices | Triangles | shell tris | strap+rim tris | .glb size |
|------|----------|-----------|-----------|----------------|-----------|
| `composite_red`    | 5 872  | 3 014  | 1 388  | 1 626  | 224 KB |
| `composite_floral` | 42 695 | 32 457 | 10 001 | 22 456 | 1.73 MB |

---

## TODO 路线图（下一步要补的功能）

1. **mesh decimation**（pymeshlab）—— LOD0 控制在 < 2 k 三角面
2. **xatlas atlas 重打包** —— 像素密度均匀
3. **normal / roughness / metallic 三纹理烘焙** —— 把 `_fabric_normal_map` 系列搬进 atlas
4. **MetaHuman 骨骼蒙皮传递** —— `JOINTS_0` + `WEIGHTS_0` accessor
5. **Chaos Cloth vertex paint** —— 顶点色通道编码 MaxDistance / Backstop / Stiffness
6. **简化碰撞体导出** —— glTF extras + UE 端 Python 解析脚本
7. **LOD 链** —— LOD0 / 1 / 2，配套 UV / 权重保留
8. **FBX 转换** —— 更好的 UE 原生兼容性

按工程排期：每一项 1–2 天，整套从 v0.1 → v1.0 大约两周。
