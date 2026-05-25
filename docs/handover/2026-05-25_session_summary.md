# 2026-05-25 Session 收尾

## 全天 commits(本地分支 `claude/add-diverse-seeds-handover-sBSs3`)

按时间顺序:

```
0ee039cd  Phase 1f post-mortem: alias 9 of 15 cutout modes to no-op
9809ac74  rl_runner: warm-start fixes + intermediate ckpts + subprocess opt-in
3f05ca83  helpers + autonomous plan + Phase 2 #5 design
e5ce261e  Phase 2 #5a: hardware_placements module
8fe9872d  Phase 2 #5b: LibraryEntry placement fields
be245580  Phase 2 #5c: bow placement_key
b1403c13  Phase 2 #5d: fringe/beads/shell placement_key
c8676f3a  Phase 2 #5e: wire garment dispatcher
a9068a48  Phase 2 #5f: 14 new accessory entries (hip_pair / three / drape / collar_row / ...)
b7f89ac4  rl_runner: graceful warm-start across head-size changes
a46a2112  docs: morning briefing (10h autonomous)
93d29700  docs: audit of remaining shared procedural shortcuts
68a5e321  Phase 2 #5+: wire O-ring anchor_specs
7dd00fd5  Phase 2 #5+: 4 new HW O-ring entries (hip_pair / trio / back_band / navel)
b369be7b  briefing update
<未提交> Fix breast-peak halo artifact (BREAST_TOP_FLOOR=0.79 lift + majority 2/3 polygon test)
<未提交> rl_runner: lazy Open3D + SKIP_RENDER env var
```

## 真正解决的问题

1. **腹部/肚脐圆环 artifact** — cutout 系统里 9/15 mode 是 navel/torso 圆形,NN 几乎不选 "none";aliased to no-op。
2. **乳房/乳头圆环 artifact**(用户称"根深蒂固"的)— shell builder 的严格 3/3 顶点判定 + 低 center_v + 高 apex_lift 复合 → polygon 边压在乳房峰上,密集三角形被丢掉成洞。修法:`_lift_above_breast(poly)` + 严格→多数 2/3 判定。
3. **Phase 2 #5 hardware mesh 去硬编码** — bow/fringe/beads/shell 现在能 per-template 选 placement(hip_pair / three / back_neck / butt_pair / drape / halter_loop / collar_row / hip_pair_shell / full_ring / long_drape / side_only / underbust)。14 个新 accessory entries 用上这套。
4. **Phase 2 #5+ O-ring anchor_specs** — Phase 2 #2 留的 promise 兑现,4 个新 HW O-ring entries 走 sternum+L/R hips trio 等多 anchor。
5. **rl_runner 加固** — resume key 双轨,intermediate ckpts(默认每 5 iter),strict=False 自动 reinit head 不匹配的层,SKIP_RENDER + RL_RENDER_SUBPROC env var,lazy Open3D import。

## 没解决的问题(明早再来)

### 训练管线在本机 WSL 仍不稳

- rl_runner 父进程加载 sbert + CLIP + NN 之后,subprocess 调 `_render_one_outfit.py` 仍然 SIGSEGV(rc=-11)
- `wsl --shutdown` 试过,fresh WSL 启动后依然 segfault
- 单独 `_render_one_outfit.py` 在干净 shell 里渲一张能成
- 推测:GPU 资源 / EGL state 在父进程持有时,子进程 Filament init 抢不到

**结论**:训练目前只能跑符号 fitness(SKIP_RENDER=1),拿不到视觉判官信号。

### Symbolic-only 训练 → mode collapse / 退化

- 200 iter 纯 fitness 训练 → 8 个 brief 全部收敛成绿色 bandeau
- 50 iter 纯 fitness → 大多数设计变成 minimal fabric / 接近裸体
- 符号 fitness gradient 是单调的,没有视觉信号约束 → NN 找到 fitness 数值最优(可能是某个固定姿态)
- 验证了 CLAUDE.md 决策:**必须用视觉判官 RL 才能学到 brief alignment + 多样性**

## 当前最佳 ckpt

仍然是 `tools/output/2026-05-24/2050_rl_run/generator_final.pt`(昨晚训出来的)。今天的 retrain 没有超越它。

## 现存输出目录(2026-05-25)

```
1339_rl_run/    86M   全部 10 个 ckpt (iter 5..50) + train_log.jsonl
                       symbolic-only,无视觉判官信号,iter50 退化
p4_showcase/   2.8M   8 个 brief,2050 baseline + Phase 2 #5 新 accessory,有乳房环
p5_no_breast_ring/ 5M  乳房环修复对比图(_compare_before_after.png)
p6_clean/      2.8M   2050 ckpt + 所有 Phase 2 #5/+#5+ + 乳房环修复
p7_iter30/     3.8M   1032_rl_run iter30 ckpt 渲染 + 跟 baseline 对比图
p8_fitness200/ 2.7M   纯 fitness 200 iter 后的 mode collapse(全绿 bandeau)
p9_iter50/     2.8M   纯 fitness 50 iter 后的退化(大多 minimal fabric)
smoke_check/   276K  单 PNG 渲染冒烟测试
```

清掉了:1031/1032/1308/1314 失败 run、_rl_warm.* stale state、1339 的每 iter PNG(只保留 ckpts + jsonl)。累计释放 ~950MB。

## 明天的下一步

按价值排序:

1. **诊断 subprocess Open3D 死因**(决定能否真训练):
   - 试只装 CV(去 CLIP)的 judge
   - 试父进程不加载 sbert(用 mock encoder)
   - 试更进一步 isolate:把 train_loop 跑在 subprocess,父进程只做 grad collection
2. **若 (1) 不通**:接受退而用 W2 plan 的另一条路 — 离线 batch render → 离线判官打分 → 重训(完全打破父子进程冲突,但牺牲在线学习)
3. **若 (1) 通**:60 iter cv_clip retrain → 应该能看到 brief alignment 进步
4. **不依赖训练的 authoring**:Phase 2 strap routing per-template(audit P1.1,下一个最大视觉 axis)

## 关键文件指针

- 设计 doc: `docs/design/2026-05-25_phase2_5_hardware_placement.md`
- 短板 audit: `docs/design/2026-05-25_remaining_shortcuts_audit.md`
- 早上 briefing(已部分过时): `docs/handover/2026-05-25_morning_briefing.md`
- 10h 自驱日志: `docs/handover/2026-05-25_autonomous_10h_plan.md`
- 本文: `docs/handover/2026-05-25_session_summary.md`
