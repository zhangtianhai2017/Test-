# AI 接手指令 — 泳装自动设计生成器(GPU 端,A6000)

> 这一份是接手该项目 GPU 工作的 Claude session 的**单一入口文档**。
> 读完它 + 项目里的 `CLAUDE.md`,就和上一个 session 几乎对齐。
> Python 端 Claude(沙盒里那个)负责代码工程 + 仓库管理 + 数据分析,
> 你(本地 A6000)负责跑训练 + 调本地 vLLM。git 是双方纽带。

---

## 一、项目本质(30 秒读懂)

- 做一个 **真的能用的泳装自动设计生成器**
- 不是研究练习,不是别人安排的工作,是**探索性 + 商业导向**项目
- 三角差异化:**AI 生成 + 真 3D 几何 + 可制造**(市面无人占齐三角)
- 当前架构方案锁定:**方案 D**(详见 `docs/design/2026-05-17_option_D_architecture.md`)

## 二、方案 D 一句话

**生成器是一个 PyTorch NN(文本 → outfit 配置)**:
- 能用真梯度的部分(隐私覆盖/比例/颜色调和)用 **autograd**
- 过不去渲染那一段(图像质量判断)用 **REINFORCE/RL 奖励**
- 现有 numpy/Open3D 渲染管线**不动**
- 判官 J 是本地 **Qwen2.5-VL-7B-Instruct**(你这台 A6000 上的 vLLM)

## 三、你的角色

| 谁 | 干什么 |
|---|---|
| **你(A6000 上的 Claude session)** | `git pull` → 跑训练 → `git push` → 报告 |
| **Python 端 Claude(沙盒)** | 看你 push 的 log + 渲染图 → 改代码 → push 新版 → 给你下一轮指令 |
| **用户** | 看双方报告,拍方向决策,转发跨 session 的信息 |

git 是**唯一**协作通道(沙盒那边出站受限,不能直连你的端口)。

---

## 四、立即执行(顺序固定,不要跳)

### Step 1:同步代码

```bash
# 假设仓库在 ~/Test-,不在请自己调整
cd ~/Test-
git fetch origin
git checkout claude/add-diverse-seeds-handover-sBSs3
git pull origin claude/add-diverse-seeds-handover-sBSs3
```

### Step 2:环境前置

```bash
# A6000 验证
nvidia-smi
# 应看到 NVIDIA RTX A6000,显存 49140 MiB

# CUDA
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# Python 3.10+,如果不是,装一个新版
```

### Step 3:启动 vLLM(如果还没跑)

如果用户之前帮你起了 vLLM,跳过这步;否则:

```bash
# 用独立 venv
python3 -m venv ~/venvs/vllm
source ~/venvs/vllm/bin/activate

pip install --upgrade pip vllm

# 启动 — A6000 48GB 显存,可以宽松配置
nohup vllm serve Qwen/Qwen2.5-VL-7B-Instruct \
    --port 8000 \
    --host 0.0.0.0 \
    --gpu-memory-utilization 0.85 \
    --max-model-len 8192 \
    --max-num-batched-tokens 4096 \
    --trust-remote-code \
    > ~/vllm.log 2>&1 &

# 等 ~1-2 分钟加载模型
sleep 90
curl -s http://localhost:8000/v1/models | python3 -m json.tool
# 应该看到 Qwen/Qwen2.5-VL-7B-Instruct
```

**A6000 显存预期**:Qwen2.5-VL-7B fp16 + KV cache ≈ **19-22 GB**,还有 ~26 GB 余量,完全不用担心 OOM。

### Step 4:装训练相关依赖

```bash
# 复用 vllm 那个 venv 即可
pip install --upgrade \
    torch numpy Pillow scipy matplotlib \
    open3d pygltflib trimesh openai

# 渲染需要(可能要 sudo)
sudo apt-get install -y libegl1 libegl-mesa0 xvfb \
    fonts-dejavu fonts-dejavu-core 2>/dev/null || true
```

### Step 5:跑 smoke run(预期 5-7 分钟)

```bash
cd ~/Test-
export VISION_JUDGE_URL=http://localhost:8000/v1
export VISION_JUDGE_MODEL=Qwen/Qwen2.5-VL-7B-Instruct
export OPEN3D_CPU_RENDERING=true        # 渲染走 CPU,GPU 专心跑 vLLM

mkdir -p /tmp/runtime-root && chmod 700 /tmp/runtime-root
XDG_RUNTIME_DIR=/tmp/runtime-root xvfb-run -a \
    python3 tools/rl_runner.py \
        --iters 8 \
        --batch 4 \
        --judge vllm \
        --lr 5e-4 \
    2>&1 | tee /tmp/rl_smoke.log
```

### Step 6:push 结果回仓库

```bash
cd ~/Test-
ls -dt tools/output/*/*_rl_run | head -1     # 找输出目录
git add tools/output/2026-*/
git commit -m "rl smoke: 8 iters x 4 batch, real vllm judge"
git push origin claude/add-diverse-seeds-handover-sBSs3
```

### Step 7:报告给用户

把下面这个模板填好,**贴回给用户**(他会转给 Python 端 Claude):

```text
=== RL smoke run 报告 ===

输出目录:     tools/output/2026-XX-XX/HHMM_rl_run
commit hash:  <git log -1 --format=%h>

iter 0 mean reward:    X.XXX
iter 0 pass rate:      X/4
iter 7 mean reward:    X.XXX
iter 7 pass rate:      X/4
mean fitness 变化:     X.XXX → X.XXX

总耗时:               XXX 秒
渲染成功率:           XX/32
vLLM 调用是否有超时:  是 / 否
显存峰值(nvidia-smi): XX GB / 48 GB

异常 / 警告(如果有):
<具体信息或 N/A>
```

---

## 五、关键决策(已锁,**不要重新讨论**)

| 决策 | 选了什么 | 不选什么 | 为什么 |
|---|---|---|---|
| 整体架构 | 方案 D | 方案 A(全可微 backprop)、方案 B(纯 RL) | A 要 1-3 个月,B 信号太弱 |
| 视觉判官 | Qwen2.5-VL-7B 本地 | 商用 API、CLIP、自训分类器 | 成本、控制、能区分结构 bug vs 风格非常规 |
| 渲染管线 | 不动 | 改 NVDiffRast / PyTorch3D | 工程成本太高 |
| 历史 600+ 输出 | **不带进新框架** | 当预训练数据 | 含已修 bug,会污染新生成器 |
| 训练起点 | **随机初始化直接 RL** | 预训练 + RL | 用户明确选了"干净开始" |

## 六、走过的死胡同(**不要重新提**)

- `SHELL_UV_MARGIN` polygon 缩边 → 修补式,被 anatomy classifier 取代
- 加 `CLASSIC_TEMPLATES` 注入"经典款" → 是模板,用户拒绝
- 拿历史 600+ 当预训练 → 含已修 bug,用户明确不带
- 沙盒直连 Cloudflare 隧道 → host 白名单不允许(为什么训练在你这边跑的原因)
- 端到端可微管线 → 工程成本与现阶段 ROI 不匹配

## 七、用户的沟通习惯

- **中文交流**,你也用中文
- **不要冗长铺垫**,先答案后理由
- **不要解释 archetype / GA / NN / backprop 这种基础概念**(他熟)
- **拼写错误不在意**(按上下文理解就好)
- **挑出你的含糊话**很快,所以**回答要精确**,不要装懂
- **明确拒绝"渐进路线"**:"做个简化版看看"这种思路不要提
- **能你做的别让他做**,主动减少他的步骤

## 八、可能踩的坑(代码注释里没有)

1. **`outfit_to_genome` 的 `.get(field, default)` 都是模板地雷**。新加字段绝不要 hardcoded default,要么进 `local_params_schema` 让每件采样,要么从隐私种子边界 + 随机偏移采。

2. **腋下/膝间挂布的根因**是 `body_deployment.classify_xyz` 之前是可选的。现在 `tools/body_region_classifier.py` 在 `build_fabric_shell` 里**强制运行**,arm/leg/head_neck 三角形从候选集硬删。任何新代码路径都要保留这个调用。

3. **`polish_shell` 是渲染瓶颈**(2.21s,占 62%),不是 GPU 渲染本身(0.93s)。Stage 1 评分应该跳过它。

4. **REINFORCE loss 比 symbolic loss 大一个量级**(~16 vs ~0.7)。`rl_runner.py` 已经设了 `w_rl=0.05 / w_sym=1.0`,不要随便改。

5. **多样性已经达到 82%+ clearly-distinct**(采样侧已饱和),进一步提升要从 J 那一侧解决。

## 九、什么时候自己拍板 vs 问用户

**自己拍板**:
- 调超参(lr / batch / w_rl)看着合理就改
- 命名 / 文件位置 / 代码组织
- 修当下立刻能看清的 bug
- PyTorch API / 算法细节选型

**问用户**:
- 大方向变更(换视觉模型 / 改架构)
- 推迟 / 砍掉原计划的事
- 涉及"该不该用历史数据"这种价值判断
- 启动长跑(几小时的训练)之前
- 改库 schema 这种**不可逆**改动

**不用问的废话**:`pip install`、`git push`、装包路径之类。

## 十、不要做的事

- ❌ 再加 `SHELL_UV_MARGIN` 之类 polygon 边界 patch
- ❌ 引入"经典款"作为兜底
- ❌ 拿 `tools/output/*/` 历史输出当训练标签
- ❌ 写"先做简化版看效果"这种 baby step
- ❌ 启动 NVDiffRast / 端到端可微方案
- ❌ 改 `tools/render3d_uv.py` 渲染管线核心
- ❌ 改 `CLAUDE.md` 上面的"已确定决策"那张表
- ❌ 中途 `Ctrl+C` 训练再重启(会丢 baseline)

## 十一、出错怎么办

| 症状 | 处理 |
|---|---|
| 渲染失败比例 > 20% | 检查 EGL / Xvfb 装好没,贴 traceback 给用户 |
| vLLM 超时 / 502 | `tail -50 ~/vllm.log`,贴回来 |
| OOM(A6000 不应该,但万一) | 把 batch 降到 2,`--gpu-memory-utilization 0.80` 重启 vllm |
| J 通过率 0/N | prompt 解析失败或图片格式问题,把 `tools/output/.../iter_0000/v00/01_front.png` 给用户看 |
| 训练 loss 出 NaN | reward 方差太大,降 `--w-rl 0.01` 重跑 |
| `KeyError: Qwen2_5_VLForConditionalGeneration` | vllm 太旧,`pip install -U vllm` |

## 十二、下一阶段预期

smoke 成功后 Python 端会:
1. 看 log 决定参数是否需调
2. 让你跑 `--iters 50 --batch 8`(约 30-40 分钟)
3. 再之后是 `--iters 200`(约 2 小时)长跑

每一轮你的工作模式都是**固定的**:
**`git pull` → 跑命令 → `git push` → 报告**。

成功标准:
- 生成器 random init 跑 ~500 iter 后,**J pass rate 从 40% → 75%+**
- mean_reward 单调上升,**没有 mode collapse**
- 用户主观看一批 J pass 样本,**觉得"这些比随机采样的好"**

如果跑了几百 iter 还不动:**先怀疑 reward signal 弱**(REINFORCE 方差大),
而不是怀疑架构。可能要加 advantage normalization / KL 正则 / 换 PPO。
但**这是后话**,先把第一轮 smoke 跑出来。

---

## 十三、参考文件(都在仓库里,需要细节再展开看)

- `CLAUDE.md`(仓库根) — 项目永久记忆,Claude Code 自动加载
- `docs/design/2026-05-17_option_D_architecture.md` — 完整架构
- `docs/handover/2026-05-17_SESSION_ESSENCE.md` — 详细决策过程 + 死胡同记录
- `tools/symbolic_fitness.py` — 步 1 输出
- `tools/design_generator.py` — 步 2 输出
- `tools/vision_judge.py` — 步 3 输出(其中 `JUDGE_PROMPT` 很关键)
- `tools/train_loop.py` — 步 4 输出
- `tools/rl_runner.py` — 步 5,你要跑的脚本

---

读完这个 + `CLAUDE.md`,从上面 **Step 1** 开始执行。
