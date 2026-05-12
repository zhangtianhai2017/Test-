# 自动迭代闭环（auto-iteration loop）方案

## 1. 目标

让 GA 的产物能在**没有人工逐次评审**的情况下自我打磨：渲染 → 多模态批评 → 数值修正 → 再渲染，直到看不出毛病或迭代次数用完。

每一轮的副产物都留档，人类可以随时跳进去看任意一轮的"诊断书 + 参数变化"，对整条链路保持审计能力。

---

## 2. 整条链路（5 个阶段）

```
   ┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌────────────┐    ┌───────────┐
   │  Stage 1    │    │  Stage 2     │    │  Stage 3     │    │  Stage 4   │    │ Stage 5   │
   │  CAPTURE    │ →  │  CRITIQUE    │ →  │  DIAGNOSE    │ →  │  APPLY     │ →  │ DECIDE    │
   │ N 张多角度  │    │ 视觉模型读   │    │ critique →   │    │ 改 polish  │    │ 收敛？还  │
   │  渲染图     │    │ 图，输出     │    │ 参数 delta   │    │ / Genome   │    │ 没？回到  │
   │             │    │ JSON 报告    │    │              │    │ / 拓扑     │    │ Stage 1   │
   └─────────────┘    └──────────────┘    └──────────────┘    └────────────┘    └───────────┘
```

每一轮 i 都产出 `tools/output/iter_<seed>/round_i/` 一个目录，包含：

```
round_i/
  views/
    01_front.png         # 6–8 个标准机位
    02_three_quarter.png
    03_side_left.png
    04_back.png
    05_chest_close.png
    06_hip_close.png
    07_strap_neck.png
    08_strap_shoulder.png
  critique.json          # 多模态模型给的诊断书
  diagnosis.json         # critique → 参数 delta 的解析
  params_before.json     # 这一轮开始时的 polish + Genome 参数
  params_after.json      # 应用 delta 后
  changelog.md           # 人类可读的"这一轮改了什么、为什么"
```

---

## 3. Stage 1 — CAPTURE：标准机位

要让多模态模型能稳定给出有用的批评，**机位必须固定**，否则模型把"那一轮换了角度"当成"那一轮变好了"。

固定 6 个主机位 + 2 个特写：

| 机位 | 用途 | 主要看什么 |
|------|------|-----------|
| front | 正面 | 杯型对称 / 乳头是否突出 / 前面边缘 |
| three_quarter (45°) | 侧前 | 杯的 3D 凸度 / 侧腰带过渡 |
| side_left (90°) | 正侧 | 胸的 silhouette / 后背带高度 |
| back | 背面 | 后背带闭合 / 后片完整 |
| chest_close | 胸口特写 | 边缘锯齿 / 杯接缝 / 是否贴皮 |
| hip_close | 髋部特写 | 前片 / 后片 / 侧带 / 高叉 |
| strap_neck (顶视) | 顶部 | 颈带是否过头 / 在脸上 |
| strap_shoulder (顶视斜) | | 肩带落点 / 不打耳朵 |

每张统一光照（左前 45° 主光 + 右后辅光），统一相机距离，统一背景色（中性灰，避免模型把背景当成衣服）。

灯光 + 距离 + 背景**写死在代码里**，不参与迭代变量，让模型每一轮看到的"基准"是一样的。

---

## 4. Stage 2 — CRITIQUE：多模态模型读图

把 8 张 PNG 喂给一个视觉模型，prompt 强制返回**结构化 JSON**：

```jsonc
{
  "iteration": 3,
  "seed": "composite_floral",
  "global_quality": 0.72,
  "issues": [
    {
      "id": "I1",
      "view": "chest_close",
      "region": "left_cup",
      "category": "nipple_show",
      "severity": "high",        // low / med / high
      "evidence": "明显的圆形凸起穿过织物，在乳头位置最高",
      "fix_hint": "increase_cup_dome"
    },
    {
      "id": "I2",
      "view": "front",
      "region": "right_strap",
      "category": "strap_floating",
      "severity": "med",
      "evidence": "肩带在锁骨上方 ~2 cm 悬空，没有贴在身上",
      "fix_hint": "lower_strap_anchor"
    },
    {
      "id": "I3",
      "view": "hip_close",
      "region": "front_panel_top_edge",
      "category": "jagged_edge",
      "severity": "low",
      "evidence": "腰线轻微锯齿，但 polish 后已不明显",
      "fix_hint": "increase_boundary_snap"
    },
    ...
  ]
}
```

**关键约束**：
- `category` 是封闭枚举（见下面映射表），不能自由发挥
- `fix_hint` 也是封闭枚举（确保 Stage 3 能自动翻译）
- `severity` 必须给定，是 Stage 5 决策的依据
- `evidence` 是自由文本，用来给人类审计

封闭枚举设计避免模型给出我们处理不了的批评；如果模型想说一个枚举外的问题，要落到 `category="other"` + 自由文本，由人类决定下一步。

执行模型有两种选择：
- **A. Claude API**（推荐生产用）：claude-opus-4-7 多模态，每轮 8 张图 + JSON schema，prompt cache 锁住系统指令，每轮成本 ~$0.05
- **B. Claude Code 交互模式**：人类敲 `/iterate composite_floral` → Claude 读图、生成 critique、写回 JSON、改参数、重渲染、再读图 → 全部在一个 session 里走

两种模式共用同一份 prompt 模板和同一份 JSON schema，单元测试也能复用。

---

## 5. Stage 3 — DIAGNOSE：critique → 数值 delta

每个 `fix_hint` 都对应一个**确定的、有界的参数修改**。映射表：

| fix_hint | 改哪个参数 | delta 公式（severity 调强度） |
|----------|-----------|---------------------------|
| `increase_cup_dome` | `garment_polish.FOAM_CUP_EXTRA_CM` | `+0.1` (low) / `+0.2` (med) / `+0.3` (high)，上限 1.0 |
| `decrease_cup_dome` | 同上 | 反向，下限 0.1 |
| `increase_boundary_snap` | polish_shell `boundary_snap` 参数 | `+0.05` ... `+0.15`，上限 1.0 |
| `more_smooth_iters` | polish_shell `smooth_iters` | `+2` ... `+8`，上限 30 |
| `increase_min_offset` | `garment_polish.SKIN_OFFSET_CM` | `+0.05` ... `+0.15`，上限 0.6 |
| `lower_strap_anchor` | `build_strap_meshes` y 偏移参数 | `-1` ... `-3` cm |
| `narrow_strap` | strap_r | `-0.05` ... `-0.15`，下限 0.10 |
| `widen_back_panel` | Genome.top_back_coverage | `+0.05` ... `+0.15` |
| `strengthen_binding` | binding `thickness` | `+0.05` ... `+0.15`，上限 0.6 |
| `shrink_front_panel` | Genome.bot_front_top_v | `-0.03` ... `-0.10` |
| `pattern_too_busy` | Genome.pattern_scale | `+0.1` ... `+0.3` (放大单位 → 视觉简洁) |
| `other` | 不动，加进 `unresolved_issues.json` | 0 |

写在 `tools/iter/diagnose.py` 里，纯函数，input critique.json → output `params_delta.json`，可单元测试。

**严格不允许**模型直接返回 raw 数值（"把 cup_extra 改到 0.7"），必须经过这张表 —— 这样所有变化可追溯、可回滚、有界。

---

## 6. Stage 4 — APPLY：合并 delta

`params_after = clamp(params_before + delta, MIN, MAX)` —— 数值参数。

如果命中的是 Genome 字段（不是 polish 参数），写回 `assets/seeds/<seed>.json` 的副本 `assets/seeds/<seed>_iterN.json`，不污染原始种子。

如果命中的是拓扑改造（`fix_hint=lower_strap_anchor` 这类），改 `build_strap_meshes` 的输入参数（不改函数本身）。

每一轮的 `params_after` 喂给下一轮的 `export_garment.py + render`。

---

## 7. Stage 5 — DECIDE：何时停？

四个停止条件，**任一**触发即停：

1. **收敛**：`global_quality ≥ 0.92` 连续两轮
2. **饱和**：连续两轮 `issues == []` 或全是 severity=low
3. **预算**：`iteration ≥ 5`（防止刷屏 + 控制成本）
4. **退化**：`global_quality_i < global_quality_{i-1} - 0.05` —— 这一轮改坏了，回滚到 i-1 并停下，flag 给人类

每一轮的 `global_quality` 也是模型在 critique 里给的（同一调用得到），所以收敛判定不需要额外推理。

---

## 8. 安全栏 / sanity checks

- **隐私底线不可触碰**：Genome `_enforce_constraints` 已经把乳头 / 私处覆盖锁成 lower bound，loop 不能让 critique 把这些边界往外拉
- **fitness 不可降**：每轮算一次 `tools/fitness.py overall`，如果掉 0.05 以上就停
- **diff cap**：单轮所有 delta 的 L∞ 范数有上限（例如 0.3）—— 防止模型一次改太狠
- **rollback**：`round_i_failed/` 留档失败轮，方便回滚

---

## 9. 文件 / 模块设计

```
tools/iter/
  __init__.py
  capture.py         # Stage 1: 多机位渲染
  critique.py        # Stage 2: 调 Claude API（或 stub 给手动模式）
  diagnose.py        # Stage 3: critique → delta（纯函数 + 映射表）
  apply.py           # Stage 4: 合并 delta，写入下一轮的 params
  decide.py          # Stage 5: 停止条件
  loop.py            # 串起来的 main loop
docs/
  auto-iteration-loop-proposal.md   # 这份方案
```

CLI:

```bash
# 一次性跑完一个种子的完整迭代
python3 tools/iter/loop.py composite_floral --max-iters 5

# 单步调试模式
python3 tools/iter/loop.py composite_floral --step 1   # 只跑 capture+critique
python3 tools/iter/loop.py composite_floral --resume   # 从最近一轮接着跑
```

---

## 10. 两种执行模式

**A. 自动模式（Claude API）**：脚本里调 `anthropic.messages.create()`，`messages=[ {role: user, content: [{type: image, ...}, ...8 张, {type: text, text: prompt}]} ]`。系统指令开 prompt cache，每轮命中。
- 优点：完全自动，可半夜跑
- 缺点：花钱、要 API key、批评质量取决于模型那天的状态

**B. 交互模式（Claude Code session）**：在我们当前这个 session 里，你说"`/iterate composite_floral`"，我就走这个 5 阶段。
- 优点：免费、可以中途指导我"这条评论不对，跳过"
- 缺点：手动驱动，每一步要你确认

两种模式共用 Stage 3/4/5 代码，只有 Stage 2 的"图怎么变成 critique JSON"那一步换实现。

---

## 11. 第一版能交付的最小可运行版本

如果你点头我就开干，第一版我会：

1. **`tools/iter/capture.py`** + 一组 8 机位的固定相机参数（已有 `render3d_uv` 的 OffscreenRenderer 做底层）
2. **`tools/iter/diagnose.py`** + 完整映射表 + 单元测试（不依赖任何 LLM，纯参数化逻辑，先确保下游链路能跑）
3. **`tools/iter/critique.py` 的 stub 版**：跑出 capture，但 critique 由你（或我用 Read tool 读图）人工填一份 JSON 进去，然后 diagnose+apply+rerender 自动跑
4. 这一版是闭环的"半自动版"，验证 Stage 1+3+4+5 工作正常
5. 第二版才接 Claude API 把 Stage 2 也自动化

这样的好处：链路本身的可靠性先在不依赖 LLM 的情况下建立起来，后面接 API 只是把 critique 那一步从手工换成自动，不会同时调试两层。

---

## 12. 风险 / 我能想到的雷

| 风险 | 缓解 |
|------|------|
| 多模态模型把"杯太大"看成"乳头突出" | severity 必须 ≥ med 才动手；连续两轮同一 issue 才认 |
| 模型的"global_quality" 漂移没意义 | 用 fitness.py overall 作 ground truth，模型分数仅用于排序 |
| 单轮改太狠把 Genome 改飞了 | L∞ diff cap + rollback |
| 在某些 archetype 上反复修不掉同一个问题 | 三轮还在 → flag 给人类（写进 unresolved_issues.json）|
| 多模态评审"看着差不多"但 fitness 下降 | 用 fitness 作硬约束，掉超过 0.05 立即停 |
| critique 自由文本里夹带提示注入 | JSON schema 校验失败一律丢掉 |
| 视觉评审对小 polygon 边缘不敏感 | chest_close / hip_close 两个特写就是为这个准备的 |

---

## 13. 时间评估

| 工作 | 时间 |
|------|------|
| Stage 1 capture（8 机位渲染脚本） | 2 小时 |
| Stage 3 diagnose 映射表 + 单元测试 | 3 小时 |
| Stage 4 apply + Stage 5 decide | 2 小时 |
| Stage 2 stub（半自动版） + loop 串起来 | 2 小时 |
| 在 composite_red / composite_floral 上跑通 5 轮 | 1 小时 |
| **半自动版总计** | **10 小时** |
| Stage 2 接 Claude API（全自动版） | +4 小时 |

---

## 14. 你需要回答的问题

1. **执行模式**：先做半自动版（手填一次 critique 看链路通不通），还是直接上 Claude API 全自动？
2. **预算**：迭代上限 5 轮够不够？想要 10 轮要重新算每轮成本
3. **范围**：这次只针对 polish 参数 + 部分 Genome 字段，还是要把拓扑（strap 走线、cup 形状参数化）也纳入？拓扑改造工作量翻倍
4. **种子**：先在 composite_red / composite_floral 上跑通，还是要扩展到 GA 输出的 top-N 后代？
