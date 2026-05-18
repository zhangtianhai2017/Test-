# 项目永久记忆 — 给后续 Claude session 的硬指针

本文件是项目的**永久记忆入口**。任何新进来的 Claude session 都应当**先读这个**,再做事。

---

## 项目本质

- 这是一个 **探索性 + 商业导向** 的项目,目标:**做一个真正能用的泳装自动设计生成器**
- 不是研究、不是学习练习、不是别人安排好给钱的工作
- 要追求**真壁垒 + 真商业价值**,**不接受"做个初级 demo 看一眼"这种没意义的做法**
- 三角差异化定位:**AI 生成 + 真 3D 几何 + 可制造**(市面无人同时占住这三个角)

## 当前正式架构方案:**方案 D**

**所有工程动作必须对照下列文件**:

→ **`docs/design/2026-05-17_option_D_architecture.md`** ← 当前阶段权威设计文档

简要:
- 生成器 = PyTorch 神经网络(文本 → outfit 配置)
- 信号 1:符号 fitness(覆盖/比例/颜色调和等)用真梯度
- 信号 2:J 视觉判官(本地 Qwen2.5-VL-7B)用 REINFORCE/RL 奖励
- 现有 numpy/Open3D 渲染管线**不动**,通过 RL 信号跨过它
- 时间表:W1 骨架 → W2 在线学习 → W3-4 用户偏好回路

## 已确定的关键决策(不要再讨论 / 反复)

| 决策 | 选了什么 | 不选什么 |
|---|---|---|
| 视觉判官 | Qwen2.5-VL-7B 本地(3090 跑) | API(成本)、CLIP(太粗)、专门训分类器(慢) |
| 闭环机制 | 符号梯度 + RL 奖励混合(方案 D) | 全可微 backprop(A,3 个月)、纯 RL(B,信号弱) |
| 渲染管线 | 保持现状,不可微 | 改 NVDiffRast / PyTorch3D(成本高,延后) |
| 优先级 | 文本 → 设计 → 制造 三角占住 | 不做"初级验证 demo" |

## 用户沟通风格(承接 iPad Claude 早期备注 + 后续观察)

- 用户用中文交流,保持中文回复
- 用户偏好简洁、直接、可操作的回答,不喜欢冗长铺垫
- 用户对项目细节熟悉,不需要给他重新解释 archetype / GA / NN / backprop 等基础概念
- 用户多次表达"不要来回传球",**主动减少他要做的步骤**,能你做的别让他做
- 用户对自己拼写错误不在意(把"v2"打成"VR"、把"巡游"打成"巡游"指代演化等),按上下文理解
- 用户思维清晰、问的问题非常精准,**遇到模糊回答会立刻挑出来**,所以回答要精确、不要含糊带过
- 用户判断力强,当他说"做一个初级的看一看意义不大"——**真的听进去,不要再回到渐进路线**

## 工程交付惯例

- 主分支:`claude/add-diverse-seeds-handover-sBSs3`
- 输出走 `tools/output/YYYY-MM-DD/HHMM_<task>/`(`dated_dir` 自动)
- 每批 batch 必须配:overview.png + README.md + index.html(有现成生成器 `tools/build_html_index.py`)
- 每次大改动 commit + push(分支上)
- 涉及多文件的功能,在 `tools/` 里加新模块,不要塞进现有大模块
- 渲染 / 渲染对照图通过 SendUserFile 发用户预览

## 关键技术档案(进项目时必读)

- `docs/design/2026-05-17_option_D_architecture.md` — **当前阶段的正式架构,权威**
- `docs/handover/2026-05-13_HANDOVER.md` — UE 端交接备忘(给 UE-side AI 的)
- `docs/handover/2026-05-13_MESSAGE_TO_UE_AI.md` — 给 UE-AI 的简报
- `MILESTONES.md` — 项目里程碑
- `tools/library_data.py` — 组件库(cup/bottom/strap/fabric/hardware/accessory)
- `tools/visual_diversity_audit.py` — 9 维感知多样性审计工具
- `tools/body_region_classifier.py` — 解剖学过滤器(根治腋下/膝间挂布)

## 工程惯例提示(避免重蹈覆辙)

- **`outfit_to_genome` 里的 `.get(field, default)` 是模板泄漏的元凶**;swimsuit_2 的参数(center_v=0.74 等)曾从这里 100% 传染所有输出。任何新字段都不要用 hardcoded default,要么进 `local_params_schema` 让每件采样,要么从随机 / 隐私种子边界采。
- **腋下/膝间"挂布"问题**已由 `body_region_classifier.py` 强制过滤根治。如果再出现类似身体凹陷处的布料 bug,**第一反应是 anatomy 分类器没接入新代码路径**,而不是再加 polygon 收边补丁。
- **渲染瓶颈不是 GPU,是 `polish_shell`**(2.21s,占 62%)。Stage 1 符号 fitness 跳过它,GA 评分快 350x。
- **多样性已稳定 80%+ clearly-distinct**(strategy 10:全栈 stratified + farthest-point);进一步收益要从"判断者"侧解决,不是采样侧。

---

**新 session 进项目第一动作**:
1. 读本文件
2. 读 `docs/design/2026-05-17_option_D_architecture.md`
3. 看 git log 了解最近 3-5 个 commit
4. 再回答用户问题 / 开始工作
