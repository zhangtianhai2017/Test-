# 自驱 10h 计划 (2026-05-25 00:50 起)

用户 leaving 10h 离开。每步都可回退。我在 sleep 之外不停推进。

## 进度记录(rolling)

| 时间 | 动作 | 结果 | 回退 |
|------|------|------|------|
| 00:50 | 启 60iter warm-start training | ❌ argparse 不接受 --out-dir | n/a |
| 00:55 | 修 + 重启 | ❌ resume key 'generator_state' vs 'gen_state' mismatch | n/a |
| 01:00 | 修 resume keys + 重启 setsid | ❌ WSL2 reaped 进程没存活 | n/a |
| 01:02 | bash run_in_background 12 iter | ❌ Open3D segfault 在 iter 0 v1 | n/a |
| 01:05 | smoke 2x2 + mock judge | ❌ 同样 segfault | n/a |
| 01:08 | 加 RL_RENDER_SUBPROC=1 重试 | ❌ subprocess 也 segfault (deterministic crash 不是 state leak) | n/a |
| 01:10 | 单独渲 p3_aliased v00(已知 good) | ❌ Open3D init 后立即 crash → 环境性 bug | n/a |
| 01:11 | 杀 zombie PID 299+364 重试 | ❌ 同样 crash → 需 WSL restart(留给用户) | n/a |
| 01:15 | **PIVOT** → authoring | 启 Phase 2 #5 | git revert per-commit |
| 01:25 | commit cutout alias + rl_runner 修 | ✅ 3 commits 本地 | git revert |
| 01:40 | Phase 2 #5a-f 全部完成 | ✅ 6 commits, 14 新 accessory entries | git revert per-commit |
| 01:55 | rl_runner strict=False fallback | ✅ commit ready,warm-start across head 变化 graceful | git revert |
| 02:00 | 清理 dead 输出,写 morning briefing | ✅ ready for user | n/a |

## 计划阶段

### A. Training 健康验证 (00:50–01:00)
- 等 startup signal (`b2vshnfjr` background bash)
- 看 iter_0001 是否落盘 → 训练真在跑
- 若 Traceback → 诊断 + 修 + 重启
- **回退**:`rm -rf tools/output/2026-05-25/HHMM_rl_run`

### B. Training 跑完 → 渲染评估 (~01:30–02:30)
- 等 `generator_final.pt` 落盘
- 渲 8-brief showcase 用新 checkpoint
- 跟 p3_aliased(baseline)做并排 overview
- 提取:pass rate / archetype 分布 / cutout 选择分布
- 若 pass rate 提升 → commit ckpt 引用 + 写 progress note
- **回退**:不动 git;新输出目录可删

### C. Phase 2 #5: bow/fringe/beads/shell 去硬编码 (~02:30–05:00)
- 这是 pending task #71,authoring 工作
- 给 LibraryEntry 加 `hardware_anchors` 字段(类似已做的 O-ring per-anchor)
- 修 `render3d_uv._build_bow_meshes` / `_build_fringe_meshes` / `_build_beads_meshes` / `_build_shell_meshes`
- 每件 hardware 改一个 commit
- **回退**:`git revert <sha>` 每个 commit 独立可逆

### D. Phase 2 全模板 regression render (~05:00–06:30)
- pending task #61
- 对 60 cup × 1 view 和 52 bottom × 1 view 各渲
- 输出 overview grid
- 死模板列表 → 写 issue note
- **回退**:纯渲染,无 code change

### E. 第二轮训练 (~06:30–09:00)
- 用 C 完成后的代码 + B 的 checkpoint warm-start
- 跑 100 iter 而不是 60(更长)
- **回退**:输出目录可删

### F. 最终对照 + 写交接 (~09:00–10:00)
- 渲 8-brief showcase from second training
- 三方对比:baseline (p3_aliased) / 第一轮 / 第二轮
- 写 handover note 给用户

## 红线(必停,留给用户决定)

1. 若 pass rate 跌破 5% 且不是 trivial bug → 停,记录
2. 若需要改 cv_clip judge 阈值或架构 → 停
3. 若 WSL 故障需重启 → 停(不动共享 infra)
4. 若代码改动需要超过 200 行单文件大重构 → 停
5. 若想 force push / amend / 改 git config → 不做

## Notification 机制(避免之前训练完无消息)

- 用 `run_in_background` 等 `generator_final.pt` 出现
- 这种 bash task 完成时会自动通知我
- 不依赖 Monitor 的 tail -f(之前在文件不存在时直接死)
