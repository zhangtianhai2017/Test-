# 剩余共享 procedural shortcuts 审计 (2026-05-25)

Phase 2 #5 完成后,渲染管线里还残留的 "永久同质性" 来源清单。
按优先级(对最终视觉变化的杠杆)排序。下次攻它们应该按这个顺序。

每条注明:位置 / 共享什么 / 影响 / 拆解所需的工作量。

---

## P1 — 必拆(下一轮)

### P1.1 — Halter / shoulder strap **routing 公式共享**
- 位置:`tools/render3d_uv.py:1191-1212` (legacy) + `:2422-2452` (garment-driven)
- 共享什么:所有 halter / shoulder strap 都走同一组弯曲 anchor 序列
  `[P0, P_clav, P_ridge, P_scap, P_back_anchor]`,且 ridge 偏移用同一公式
  `[P_clav*0.65, min(y_acromion+1.5, y_neck_base-1.0), P_clav*0.4]`
- 视觉:**所有 halter / shoulder strap 看起来一样的弧线** — 只是粗细
  随 `g.top_neck_strap` 缩放
- 现实里的多样性:
  - X-back(双 strap 在背后交叉)
  - Racerback(两 strap 收成一根中央 strap)
  - Tied-bow shoulder(肩膀位置打蝴蝶结)
  - Twisted strap(strap 绕一圈再走)
  - Drape neck(strap 不绕脖,直接斜挂)
- 工作量:**3-4 commit** —
  - 新模块 `tools/strap_routings.py` 类似 hardware_placements.py
  - LibraryEntry 加 `strap_routing: str = ""`(strap kind 用)
  - render3d_uv 两个调用点接 placement_key
  - 5-8 个新 STRAPS 库条目

### P1.2 — Underbust band / top back band **几何共享**
- 位置:`tools/render3d_uv.py:1078-1100`(`_build_strap_meshes_legacy`)
- 共享什么:背带高度 `band_h=1.5+2.0*g.top_back_coverage` 是连续函数,
  没有 per-template 风格(平直 vs 扭转 vs 镂空)
- 视觉:所有 bandeau 背带都是一条均匀矩形条带
- 现实:扭转 bandeau、镂空 bandeau、绑带 bandeau 都不同
- 工作量:**2-3 commit** — 类似 cup_polygons 的拆法,band geometry 拆到
  `tools/band_recipes.py`

### P1.3 — O-ring 几何在两条路径不一致
- 位置 1:`tools/render3d_uv.py:798-836`(legacy `_build_oring_meshes`)
  → 一个 O-ring 在 sternum(front_gore)
- 位置 2:`tools/render3d_uv.py:2404-2419`(garment dispatcher)
  → 两个 O-ring 在 cup-top corners(R + L)
- 问题:legacy 路径 promises "Future per-hardware refactor will let
  specific hardware items opt back in to multi-anchor placement via
  library entry's anchor_specs" — 没兑现
- 工作量:**1 commit** — legacy `_build_oring_meshes` 加 `anchor_specs`
  consumption(LibraryEntry 已经有这个字段);garment 路径同样,以
  `c.id` 查 anchor_specs

---

## P2 — 该拆(中期)

### P2.1 — Body-jewelry 几何 hardcoded
- 位置:`tools/render3d_uv.py:2724-2782`
- 共享:
  - earring drop:stud r=0.25,drop r=0.15,height=length_cm
  - body chain waist:`waist_circumference_cm=75.0`(硬编码!)
  - body chain belly:drop length=4.5cm(硬编码)
- 影响:body jewelry 在远景不太显眼,所以视觉收益小,但 75cm 腰围不该
  hardcoded
- 工作量:**1 commit** — 从 LibraryEntry 读 size / 用 g.waist
  proxy

### P2.2 — Fringe length / radius 一公式
- 位置:`tools/render3d_uv.py:_build_fringe_meshes` 内
  `length=max(2.0, min(6.0, 1.0+4.0*g.fringe_length))` +
  `_tube_between(..., radius=0.10, sides=5)`
- Phase 2 #5d 已经支持 length_scale per-placement,但 strand 数(默认 9)
  和 tube radius(0.10)仍然 hardcoded
- 工作量:**0.5 commit** — placement 元组扩展加 `strand_radius` field
  可选

### P2.3 — Beads size hardcoded
- 位置:`_build_beads_meshes` 内 `create_sphere(0.28 * scale)`
- 不同 beads 类型(小米珠 vs 大水晶)应该有 size 差异
- Phase 2 #5d 已经支持 per-anchor scale,但基线 0.28cm 是 hardcoded
- 工作量:**0.5 commit** — LibraryEntry 加 `bead_diameter_cm`

### P2.4 — Cup foam thickness 几乎不使用
- 位置:`tools/library.py` 的 `foam_thickness_mm` 字段存在,但 render
  那边没用(用了 cup_dome_depth_cm 一个 IterParams)
- 影响:不同 padding 的 cup(triangle 无 foam vs molded 厚 foam)
  视觉上没法区分
- 工作量:**1 commit** — render path 把 foam_thickness_mm 注入 cup 几何

---

## P3 — 不急(长期)

### P3.1 — 内裤 inseam tube radius=0.30
- `tools/render3d_uv.py:1235, 2473` `_arc_tube(..., radius=0.30)`
- 所有底裤的 inseam(裆部缝合管)都同一粗细
- 影响:微弱

### P3.2 — Bar-tack 加固点尺寸 hardcoded
- `tools/render3d_uv.py:1226-1247` 围绕 strap 接 cup 的小 ellipsoid
- 工艺细节,远景看不见

### P3.3 — Wrinkle 振幅 / 频率
- `apply_wrinkles(shell, amplitude=wr_amp)` 用 `0.04+0.10*(1-g.fabric_weight)`
- 所有面料是同一种皱纹模式,只是振幅不同
- 影响:细微纹理

### P3.4 — Seam tube width hardcoded
- 各种 seam line 走 `_arc_tube(..., radius=X)`,X 是 const 不是 per-seam
- 影响:细微

---

## 修复优先级建议

| 顺序 | 拆什么 | 价值 | 工作量 |
|------|--------|------|--------|
| 1 | P1.1 strap routing | 高 | 3-4 commit |
| 2 | P1.2 band geometry | 中-高 | 2-3 commit |
| 3 | P1.3 O-ring anchor_specs | 中 | 1 commit |
| 4 | P2.4 cup foam | 中 | 1 commit |
| 5 | P2.1-3 body jewelry / fringe / beads tweaks | 低-中 | 各 0.5-1 commit |

**关键观察**:把 P1.1(strap routing)做了,加上目前的 cup/bottom/back/
hardware-placement,**前端能看到的"形状空间"会再翻一倍**。后面的
band/O-ring/foam 都是细节调整,P1.1 是下一个真正的视觉 axis。

---

## 已完成的拆解(参考,别再重做)

- ✅ Phase 2 #1 — back polygons per-geometry (`back_polygons.py`)
- ✅ Phase 2 #2 — O-ring 三点固定改为 sternum-only(P1.3 是补完
  per-anchor 配置)
- ✅ Phase 2 #4 — side_tie per-bottom(coverage_class gate)
- ✅ Phase 2 #5 — bow/fringe/beads/shell placement(`hardware_placements.py`)
- ✅ Phase 2 #6a — bottom polygons per-geometry(`bottom_polygons.py`)
- ✅ Phase 2 #6b — cup polygons per-geometry(`cup_polygons.py`)
