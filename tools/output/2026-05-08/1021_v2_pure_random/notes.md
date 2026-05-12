# 纯随机生成 — 不依赖任何 seed 或 Genome 先验

## 想验证什么

v2 系统的 chromosome 层（Outfit）由 3 个手写资源构成：
1. `tools/library.py::ARCHETYPE_SLOTS` — 4 个 archetype 的 slot 模板
2. `tools/library_data.py::LIBRARY` — 86 个 LibraryEntry 目录
3. 每个 LibraryEntry 的 `local_params_schema` — 取值范围

`random_outfit(archetype, rng)` 只读这三个。**它不读** `assets/seeds/`，**不调** `genome_to_outfit`，**不查** v1 默认 Genome。

如果纯 RNG 驱动也能产生连贯的服装，说明 v2 layer 有自己的 intrinsic structure，
不是靠 seed 先验"撑场子"。

## 结果

16 个 outfit（4 archetype × 4 RNG seed），全部走 v2 cascade 渲染：

| 指标 | 值 |
|---|---|
| composite | mean **0.790** ± 0.037, range [0.735, 0.848] |
| outfit-native | mean **0.838** ± 0.058, range [0.708, 0.917] |

对比之前 GA 跑出来的最优 outfit：composite max ≈ 0.939。所以**纯随机的 baseline ≈ 0.79**，
GA 之后 ≈ 0.94 — GA 大约能把分数推高 0.15，但 baseline 已经"够穿"了。

观察 `overview.png`：

- 每个 archetype 的 4 个 RNG seed 之间**外形差异显著**（cup 形状、底片大小、配色都不同）
- 每件衣服都有完整的 cup + bottom + 至少一条 strap + 主面料
- 没有 archetype 错配（triangle 没分到 high_waist，等等）
- 没有 outfit_validation 警告

## 唯一的 pre-trained 依赖

只剩 body mesh `assets/NPC_swim_G_2_CombinedSkelMesh*.obj` — 那是渲染画布，
v2 chromosome 本身完全可以脱离它独立存在（用其他人体网格直接 deploy）。

## 结论

v2 layer 不依赖 v1 seed 数据或任何 trained distribution。`random.Random(seed)`
直接驱动 ARCHETYPE_SLOTS + LIBRARY 就能产出连贯的服装。
