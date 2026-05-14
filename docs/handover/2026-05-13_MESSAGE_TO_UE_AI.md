# 给 UE 端 AI 的交接消息(2026-05-13)

> 复制这个文件全文,贴给对面 AI 即可。

---

你好,Python 端这边已经把 `zhangtianhai2017/Test-` 仓库里 `assets/glb/` 下的 37 个 skinned GLB 全部 refit 到了 UE 5.6 MetaHuman Body 的交付规范,这个 message 告诉你怎么取、怎么用。

## 1. 取文件

- 仓库:`zhangtianhai2017/Test-`
- 分支:`claude/add-diverse-seeds-handover-sBSs3`
- 最新 commit:`f0017a1`
- 路径:`assets/glb/*.glb` + `assets/glb/manifest.json`
- 工具源码(便于你审):
  - `tools/refit_metahuman_glb.py`
  - `tools/metahuman_skeleton.py`
  - `tools/bake_v2_glb_skinned.py`

## 2. 这 37 个 GLB 已满足的硬性条件

1. joint 名:UE 5.6 MetaHuman Body 命名,**无 FACIAL_***
2. parent/child 层级:严格匹配 `MetaHumanSkeletonDefinitions.inl` 的 body 部分
3. 不含 corrective/helper/dyn(`*_correctiveRoot_*`、`*_fwd_/_bck_/_in_/_out_/_knee*`、`*_twistCor_*`、`*_dyn`、`bicep`/`tricep`、`wrist_inner/outer`、`ankle_fwd/bck`、`clavicle_out/scap/pec`、`spine_04_latissimus_*`)
4. skin.joints = **70 根**(42 核心 deform + 18 手部一级 + 10 脚趾一级);所有 GLB 完全相同的骨骼数组
5. 每顶点 ≤4 影响,weights 已归一,sum=1.0(已逐文件校验)
6. 总骨骼 70,远低于 128 软上限
7. **单位 = cm,Forward = +Y**,标注在 `asset.extras` 里
8. 每个文件是 skinned mesh(POSITION / NORMAL / TEXCOORD_0 / JOINTS_0 / WEIGHTS_0 全在)
9. inverseBindMatrices 已按 70 根重新计算,与 bind pose 对齐
10. 新 manifest schema:
    ```json
    { "version": 2, "skeleton": "MetaHuman UE5.6 Body",
      "unitScale": "cm", "forwardAxis": "+Y",
      "ueImportSettings": {"SceneScale": 1.0, "ForwardAxis": "Y", "note": "..."},
      "outfits": [
        {"file": "...", "displayName": "...", "slots": [...],
         "skeleton": "MetaHuman UE5.6 Body", "archetype": "...",
         "unitScale": "cm", "forwardAxis": "+Y",
         "boneCount": 70, "vertexCount": ..., "sizeKb": ...}
      ]}
    ```

## 3. UE 端唯一需要做的配置变更

把 `unreal/BikiniValidator/Plugins/glTFRuntime/`(或你工程里实际配置 glTFRuntime 的位置)的 import 设置:

| 字段 | 旧值 | 新值 |
|---|---|---|
| `SceneScale` | `0.1` | **`1.0`** |
| `ForwardAxis` | `Y` | `Y`(保持) |

**理由**:这次 GLB 直接以 UE 的 cm 单位输出(verts X 跨 ±23 cm,Y 84→144 cm,Z ±13 cm,真人尺寸物理正确),不再需要 0.1 缩放。如果忘了改,资产会比正确尺寸小 10 倍。

## 4. 烟测建议(从小到大)

1. 先 import `composite_red.glb`(397 KB,顶点最少)。bind pose 应贴合标准 MetaHuman Body 的胸/腰/胯位置。
2. import 后在 Skeletal Mesh 编辑器里 Verify:Skeleton 资产引用应能直接关联到 `/Game/MetaHuman/Mannequin/SK_Body`(或你工程里同源的 MetaHuman body skeleton)。如果 UE 报"missing bones",这意味着 70 根白名单和你目标 SK 实际 bone 名有出入,贴 missing 列表给我们,我们调白名单。
3. 拉一个 idle 动画(任意 MetaHuman body anim)play 一下,看 cup/strap 是否随胸廓和锁骨自然变形。如果手臂动起来 cup/strap 跟手臂一起飘 → 说明权重 fold 把上臂权重错路由到了手臂;告诉我们具体 outfit 名 + 截图,我们查 fold 表。
4. 通过后再 batch import 剩余 36 个。

## 5. 如果你发现问题想反馈

- **bind pose 偏移**:发 1) UE 工程的 SK_Body 资产路径,2) UE 那边能 dump 出来的 reference pose 的几个关键 bone(`pelvis`、`spine_03`、`upperarm_l`、`thigh_l`)的 world position
- **bone 名缺失**:贴 UE 报的 missing bone 列表
- **缩放不对**:确认 SceneScale 改没改;如果改了仍然不对,说明 source body 单位假设(我们假设 cm)和你工程的 SK_Body 不一致

## 6. 后续可能问到的

- **将来还会增加新 outfit**:Python 端只要再跑一次 `python3 tools/bake_v2_glb_skinned.py <seed_name>`,新 GLB **自动**符合上述全部规范(refit 已串进 baker)。manifest 也自动更新。你这边不用做任何额外配置。
- **240 件 batch 输出**(`tools/output/2026-05-13/.../*/outfit.json`):**这些不在 GLB 范围内**,只是 outfit 定义 + 渲染图,不是给 UE 用的。如果将来需要把这批也 bake,告诉我们,我们扩 loader。
- **昨天修了一个 cup 在腋下黏布料的 bug**(commit `4ea21d6`,A/B 对照在 `tools/output/2026-05-13/1039_seed_batch_random_M080_20x6/_compare_pre_post.png`)。这个 fix 影响的是几何生成阶段,在 GLB bake 之前;现有 37 个 GLB **是修复前**几何 bake 出来的,如果你看到 cup 区域有奇怪布片连到上臂内侧,告诉我们,我们重新 bake。

有问题随时贴 commit hash + 文件路径,这边接得住。
