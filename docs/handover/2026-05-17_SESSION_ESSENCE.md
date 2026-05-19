# 给后续 Claude session 的对话精华交接

> 这份文件是 Python 端 Claude(沙盒里那个,后续叫"上一个 session")
> 在长对话里**积累但未在代码 / 文档里固化**的东西 —— 用户的偏好、
> 决策过程、讨论过的死胡同、不在仓库里能查到的隐性上下文。
>
> 任何接手的 session(包括 3090 这台机器上的,以及未来的)进项目时
> **必读**。读完 + 读 `CLAUDE.md` + 读 `docs/design/2026-05-17_option_D_architecture.md`,你就和上一个 session 几乎对齐了。

---

## 一、用户是谁,要什么

- **不是研究员**:不接受"做个简化 demo 看一眼就完事"这种思路
- **不是雇主**:不会给你详细需求文档,需要你**自己有判断力**主动推进
- **商业导向**:每一步都要往"真壁垒 + 真商业价值"上靠
- **战略定位**:三角差异化 = **AI 生成 + 真 3D 几何 + 可制造**(市面无人占齐三角)
- **不容忍**:模板痕迹、临时 patch、假装解决根因的"修补式"方案、初级验证

## 二、用户的沟通习惯(直接影响怎么和他互动)

- **中文交流**,你也用中文,不需要解释 archetype / GA / NN / backprop 这种基础概念
- **极其讨厌冗长铺垫**,答案直接给,理由放后面
- **拼写错误不在意**(把 v2 写成 VR,把"巡游"写成"巡游"指演化),按上下文理解
- **判断力锋利**,你含糊带过他会立刻挑出来
- **质疑你的话往往是对的** —— 比如"前面那些可微化是不是不难"被他挑出来,我后来确实承认低估了
- **不喜欢来回传球**,能你做的别让他做,主动减少他的步骤
- **明确拒绝过"渐进路线"**:当他说"做个初级看一看意义不大",**真的听进去**,不要绕回去

## 三、关键决策(已锁,不要回头讨论)

| 决策 | 选了什么 | 不选什么 | 原因 |
|---|---|---|---|
| 最终架构 | **方案 D**(PyTorch 生成器 + 符号梯度 + RL 奖励) | 方案 A(全可微 backprop)、方案 B(纯 RL) | A 要 3 个月,B 信号太弱 |
| 视觉判官 | **Qwen2.5-VL-7B 本地**(3090) | 商用 API、CLIP、自训分类器 | 成本、控制、能区分结构 bug vs 风格非常规 |
| 渲染管线 | **不动**(保持 numpy/Open3D 不可微) | 改 NVDiffRast / PyTorch3D | 工程成本太高,通过 RL 跨过 |
| 历史 600+ 输出 | **不带进新框架** | 当预训练数据 | 含已修 bug,会污染新生成器 |
| 训练起点 | **随机初始化直接 RL** | 预训练 + RL | 用户明确选了"干净开始" |
| 偏好采集 | **二选一比较(Bradley-Terry)**,未来再做 | 0-10 评分 | 比较比评分稳 10 倍 |

## 四、用户在对话中亲自挑出的几个关键问题(以及解决思路)

1. **"渲染前能不能判断"** —— 引出"符号 fitness Stage 1 + 渲染 fitness Stage 2"两段架构;Stage 1 在 build_fabric_shell 之前就能算,省 99% 评估成本

2. **"是不是有悖论:用 AI 训 AI 反而做不到"** —— 当前沙盒出站受限,但**这只是这一个部署位置的限制**;Claude Code 装到本地机器上就完全可以。这就是为什么现在分两个 session 协作

3. **"我没看见最常规的比基尼"** —— 引出对历史输出诊断,发现 `cup_p.get("center_v", 0.74)` 在 100% cup 上 fallback,所有 cup 在同一高度。这是"模板深陷"的具体表现。修复:把 `center_v` 加进每个 cup entry 的 `local_params_schema`(`tools/library_data.py` 底部已有这个 hack)

4. **"腋下/膝间挂布"** —— 用户反复观察到这个,要求**结构性根治不是补丁**。结果是:`tools/body_region_classifier.py` 强制运行,把 arm/leg/head_neck 三角形从 shell 候选集**移出**。这取代了我之前加的 SHELL_UV_MARGIN(那是修补式)

5. **"多样性的真正定义"** —— 视觉感知多样性 > 设计空间多样性;9 维 axes(`tools/visual_diversity_audit.py`),Hamming 距离衡量,目标 ≥5 维差异为"明显不同"。当前 winner 是 82.4% clearly-distinct 配 0 个 perceptually identical

6. **"GA 在项目里没真的用上"** —— 用户直接看穿。承认了:`evolve_from_seed.py` / `v2_ga_demo.py` 只是用 GA 的数据结构,没用搜索能力。所以方案 D 改成"NN 生成器 + 符号梯度 + RL",GA 暂时搁置

## 五、已经走过的死胡同(不要重新提)

| 路线 | 为什么死了 |
|---|---|
| 加 SHELL_UV_MARGIN polygon 缩边 | 修补式,宽 cup 还是漏。结构修复用 anatomy classifier 取代了它 |
| 用大模型分类器做 mechanism 3 | 用户明确拒绝"渐进 NN 验证器" —— 没壁垒、没价值 |
| CLASSIC_TEMPLATES 注入"保证经典款出现" | 用户立刻挑出"这又是模板",撤了。改为让宽采样自然包含 |
| 历史 600+ 当预训练数据 | 用户明确不带历史 bug 污染新框架 |
| 从沙盒直接调 trycloudflare.com 隧道 | 沙盒 host 白名单不允许,403。改为"训练在 3090,代码工程在沙盒,git 同步" |
| 端到端可微管线(方案 A) | 工程量 1-3 个月,数据 ROI 不够 |
| 全链路纯 RL(方案 B) | 信号太弱,需要太多样本 |

## 六、当前执行进度(到 2026-05-17 末)

- ✅ **步 1**(`tools/symbolic_fitness.py`):11 个 fitness 项,autograd 全通,微秒级
- ✅ **步 2**(`tools/design_generator.py`):PyTorch 生成器,18 个连续头 + 9 个离散头(archetype/cup/bottom/strap/fabric/accessory/hardware/pattern/weave),mock 编码器 + sentence-transformer 选项
- ✅ **步 3**(`tools/vision_judge.py`):Mock + vLLM 双后端,JUDGE_PROMPT 已仔细设计(区分结构 bug vs 风格非常规)
- ✅ **步 4**(`tools/train_loop.py`):symbolic + REINFORCE 训练循环,JSONL 日志,checkpoint 保存
- ❌ **步 5 预训练**:做了又**主动撤回**(commit `4c55dc0`)—— 不带历史污染
- ⏳ **步 5'** = 直接进 RL:`tools/rl_runner.py` 已写,mock judge smoke 跑通(commit `4cca845` 之后某次)。现在卡在"沙盒不能调 vllm 隧道" → **移到 3090 上跑**(这就是当前节点)

下一步:**3090 跑 smoke run(8 iter × 4 batch)**,详见 `docs/handover/2026-05-17_rl_training_on_3090.md`。

## 七、容易踩的坑(隐性知识,代码注释不一定够)

1. **`outfit_to_genome` 的 `.get(field, default)` 全部是模板地雷**。新加字段绝对不要 hardcode default。要么进 `local_params_schema` 让每件采样,要么从隐私种子边界采,要么从 `random.uniform` 采。

2. **腋下/膝间挂布的根因不是 polygon 太宽**,是 `body_deployment.classify_xyz` 这个 anatomy filter 之前是"可选项"。现在改成 `body_region_classifier.py` 在 `build_fabric_shell` 里**强制运行**,arm/leg/head_neck 三角形从候选集硬删。任何新代码路径都要保留这个调用。

3. **`polish_shell` 是渲染瓶颈(2.21s,62% 时间)**,不是 GPU 渲染。Stage 1 评分应该跳过它。

4. **多样性已达 82%+ clearly-distinct**(采样侧),进一步提升要从"判断者"侧解决(就是 J 的事),不是再调采样。

5. **`tools/output/2026-05-17/0936_diverse_winner_full_stack/` 是 farthest-point + wide_form 的最佳基线**。用 J 评 RL 输出时,可以拿这一批的 J pass rate 当参照。

6. **REINFORCE loss 比 symbolic loss 大一个量级**(~16 vs ~0.7)。需要 `w_rl ≈ 0.05` 配 `w_sym = 1.0`(在 `rl_runner.py` 默认值)。否则 RL 会盖过 symbolic 信号。

7. **3090 上的 vLLM 服务进程不要被中断**。Cloudflare 隧道可以断,Python 端会直接调 localhost 不依赖隧道。

8. **每件衣服渲染 ~3.5 秒**(2 视图,软件 EGL)。3090 上要看看 EGL 跟 vLLM 抢不抢资源,如果抢可以减视图数或用 CPU 渲染(`OPEN3D_CPU_RENDERING=true`)。

9. **`CLAUDE.md` 在仓库根**,Claude Code 会自动加载到上下文。新增长记忆性的项目级决策要 append 进去,不要散落别处。

## 八、什么时候问用户 vs 自己拍板

**自己拍板**:
- 调参(lr / batch / w_rl 等)看着合理就改
- 命名 / 文件位置 / 代码组织
- 修 bug 当下能立刻看清的
- 用什么 PyTorch API / 算法选型

**问用户**:
- 大方向变更(比如"是不是改用别的视觉模型")
- 推迟 / 砍掉某个原计划做的事
- 涉及"是不是该用历史数据"这种价值判断
- 长跑训练之前(几小时的)
- 写库存这种**不可逆**的代码(扩库、改 schema)

**不要问的废话**:
- "我可以 git push 吗"(可以)
- "我可以装 pip 包吗"(可以)
- "我应该写注释吗"(代码精炼别叠注释)

## 九、不要做的事(明令禁止)

- ❌ 再加 SHELL_UV_MARGIN 或类似 polygon 边界 patch
- ❌ 引入"经典模板"作为兜底
- ❌ 拿历史 600+ 输出当训练 label
- ❌ 写"先做个简化版看看效果"这种 baby step
- ❌ 端到端可微方案 / NVDiffRast 这种"现在阶段值得做"的判断
- ❌ 改 `tools/render3d_uv.py` 渲染管线(这是方案 D 的固定假设)
- ❌ 跨 archetype 突变(GA 那条线已经不用了,但保留代码)
- ❌ 改 `CLAUDE.md` 上面的"已确定决策"那张表

## 十、可以期待的下一阶段(执行人是你)

按方案 D 时间表:
- **W1**(已完成):骨架四件
- **W2**(进行中):smoke run + 长跑训练,看 J reward 是否驱动生成器越来越好
- **W3-4**:加入用户偏好回路(可能用 web UI 让用户从 J pass 的池里挑喜欢的)
- **后续**:看 J + 偏好综合后,生成器有没有真正学到"贴你审美的设计"

成功标准:
- 生成器从 random init 跑 ~500 iter 后,**J pass rate 应该从 40% 涨到 75%+**
- **mean_reward 单调上升**,且没有 mode collapse(每次输出大同小异)
- 用户主观看一批 J pass 的样本,**觉得"这些比随机采样的好"**

如果跑了几百 iter 还不动,**先怀疑 reward signal 弱了**(REINFORCE 方差大),
而不是怀疑架构 —— 架构跑通是事实。可能要加 advantage normalization、
KL 正则、或换 PPO。

---

读完这个文件 + `CLAUDE.md` + `docs/design/2026-05-17_option_D_architecture.md`,
你和上一个 session 应该已经几乎对齐了。
直接按 `docs/handover/2026-05-17_ONBOARDING_3090.md` 开干。
