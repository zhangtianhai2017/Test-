# Phase 2 #5: 硬件 mesh 去硬编码 — bow / fringe / beads / shell

## 现状问题

`tools/render3d_uv.py` 中四个硬件 mesh 构造函数全是单点共享公式:

| 函数 | 位置 | 形状变化 |
|------|------|---------|
| `_build_bow_mesh` | u=0, y=top_center_v(胸中心) | 永远 1 个蝴蝶结,2 翼+1 结 |
| `_build_fringe_meshes` | u=[-0.30, 0.30] 9 stripes,y=底裤腿口 -4cm | 永远前面流苏,9 根 |
| `_build_beads_meshes` | u=[cup_outer+0.02, 1.0] 6 串镜像,y=top_center_v | 永远胸围一圈珠 |
| `_build_shell_mesh` | u=0, y=top_center_v -2.5 | 永远 1 个贝壳挂坠在胸下 |

结果:所有"有蝴蝶结"的设计都是胸中心一个 bow,所有"有珠"的设计都是胸围一圈,无变化。
跟之前 O-ring 三点固定一样的"永久同质性"。

## 修复架构(镜像 Phase 2 #2 O-ring 做法)

### 1. 新模块 `tools/hardware_placements.py`

每个 hardware type 一组命名 placement 函数,返回 `[(anchor_name, u, v, scale_mult), ...]`:

```python
BOW_PLACEMENTS = {
    "single_center": lambda g: [("bow_C", 0.0, g.top_center_v, 1.0)],
    "hip_pair":      lambda g: [("bow_LH", -0.45, 0.50, 0.7),
                                  ("bow_RH", +0.45, 0.50, 0.7)],
    "back_neck":     lambda g: [("bow_BN", 1.0, 0.94, 0.9)],  # u=1 = back seam
    "three":         lambda g: [("bow_C",  0.0, g.top_center_v, 0.8),
                                  ("bow_LH", -0.40, 0.50, 0.6),
                                  ("bow_RH", +0.40, 0.50, 0.6)],
    "butt_pair":     lambda g: [("bow_LB", -0.70, 0.40, 0.6),
                                  ("bow_RB", +0.70, 0.40, 0.6)],
}

BEADS_PLACEMENTS = {
    "bust_ring":    "current behavior",
    "vertical_drape": lambda g: u=0 串珠从胸到腰,
    "halter_loop":  lambda g: 从颈后绕一圈,
    "side_chain":   lambda g: 两侧腰处垂吊,
}

SHELLS_PLACEMENTS = {
    "single_charm": lambda g: 当前,
    "collar_row":   lambda g: 胸前一排小贝壳,
    "drop_string":  lambda g: 一串下垂,
}

FRINGE_PLACEMENTS = {
    "front_hem":   lambda g: 当前,
    "full_ring":   lambda g: 360° 环绕,
    "long_drape":  lambda g: 长 12cm 飘穗,
    "side_only":   lambda g: 仅左侧/右侧,
}
```

### 2. LibraryEntry 加字段

`tools/library.py` 的 LibraryEntry 加 4 个 optional:

```python
bow_placement: str = ""       # key in BOW_PLACEMENTS
beads_placement: str = ""     # key in BEADS_PLACEMENTS
shells_placement: str = ""    # key in SHELLS_PLACEMENTS
fringe_placement: str = ""    # key in FRINGE_PLACEMENTS
```

不填 → 走 "current behavior" 保持兼容。

### 3. 现有 build 函数改造

每个 `_build_X_mesh` 改成:
- 接受 placement_key(从 g.hardware_meta 拿,默认 ""空字符串)
- 调用 `hardware_placements.resolve_X(key, g)` 拿 anchors 列表
- 每个 anchor 单独建一个 mesh,name = anchor_name
- 默认 fall back 到 current single-anchor behavior

### 4. 库扩

在 library_data.py 加 ~10 个新 hardware entries:
- "bow_hip_pair" / "bow_three" / "bow_butt_pair"
- "beads_vertical" / "beads_halter"
- "shells_collar"
- "fringe_full_ring" / "fringe_long_drape"

每个新 entry 用对应的 placement key。

### 5. NN 影响

discrete hardware head 当前 size 10,新增条目 → 需要 retrain。但 head expansion 在 retrain 时是已知模式(在 1f 阶段就做过 cutout=15)。warm-start ckpt 的 head 会和新 size 不匹配 → 必须 cold-start 或随机初始化 head。

**取舍**:这一步如果要立即训练,需要 cold-start。建议先把 placement 字段全部默认 "" 保持向后兼容,新 entries 推到下次训练。

---

## 执行步骤(每步独立 commit)

1. `commit A`:新增 `tools/hardware_placements.py` 模块(纯增,无破坏)
2. `commit B`:LibraryEntry 加 4 个新字段(默认空,向后兼容)
3. `commit C`:`_build_bow_mesh` 接 placement,缺省走旧路径
4. `commit D`:`_build_beads_meshes` 同上
5. `commit E`:`_build_shell_mesh` 同上
6. `commit F`:`_build_fringe_meshes` 同上
7. `commit G`:library_data.py 加新 entries(库 size 增加)
8. `commit H`(可选):快速冒烟渲染新 entries 各一张

每个 commit 可独立 `git revert`。
