# Schema Redesign v3 — Game-Character-First Design Generator

**Status:** proposal for user review · supersedes v2 (`docs/component-library-v2.md`) and `docs/design/2026-05-17_option_D_architecture.md` on output/schema side; preserves v2 anchor grammar
**Last updated:** 2026-05-27
**Trigger:** 2026-05-27 conversation — Phase 3 (rigid categorical NN + RL) produces designs indistinguishable from real-world mainstream swimwear; project needs to escape this trap

---

## 1. 三条根本原则(本设计要扛住的)

| # | 原则 | 翻译成 NN 结构要求 |
|---|---|---|
| 1 | **游戏角色服装优先,可制造性后置** | 输出端解锁 v2 "必须命名库条目" 约束;可制造性变成后置分类器,不再是 generation-time hard constraint |
| 2 | **砍掉一般性 / 主流 / 已有库里泛滥的设计,只留 stylized / 想象 / 艺术 / 张力** | 训练分布显式偏向 stylized tag 空间;明文 ban-list 阻止平庸滑回 |
| 3 | **不被现有美术风格的桶锁死;tag = 潜空间维度;模型自发组合新风格;~10% 纯自由度** | tag = embedding 不是 id;style latent 是 d 维连续 manifold;额外 noise channel 占 10% 能量预算;反 "snap-to-nearest-tag" 训练机制 |

附:Phase 1/2 考古结论(详见 §8):**v1 → v2 的"离散库"妥协是为了制造性可解释**,跟新原则 1 直接冲突,所以那条妥协必须撤回;但 v2 的 **anchor-based fabric grammar** 解决了 Phase 1 真正的失败原因(身体锚定),那部分必须保留。

---

## 2. v2 架构为什么必须重做

| v2 现状 | 撞哪条原则 |
|---|---|
| 12 个 categorical head,每个 `argmax(softmax)` 输出 library entry id | **撞原则 3**:输出永远 snap 到命名条目,无法在条目之间出新风格 |
| `cup_piece` / `bottom_piece` / `strap_piece` 三槽固定 | **撞原则 1**:无法表达 monokini / cross-body wrap / harness / 自由 fabric path |
| `local_params` 仅在条目内连续 | **撞原则 3**:连续性只在低层几何参数(尺寸/颜色),style/美学维度完全没有 |
| `_detect_archetype` 显式 raise `UnsupportedArchetypeV1` 回落 legacy | **撞原则 1**:连体式直接进死路 |
| 训练分布按"现实泳装款型"均匀覆盖 | **撞原则 2**:训出来的就是泛滥设计 |
| 没有 noise channel | **撞原则 3**:不存在"10% 自由发挥"的接口 |

**结论**:输出端 + 训练机制必须重写。**保留**:sbert 文本编码、anatomy anchor 系统、Connector.path_policy 8 种枚举、渲染管线 primitive(`_arc_tube` / `_build_band_mesh` / `_body_ring` 等)、symbolic fitness 框架(但权重要重调)。

---

## 3. 新架构总览

```
                  ┌────────────────────────┐
brief 文本 ───────►│  sbert encoder (frozen)│ (384-dim)
                  └───────────┬────────────┘
                              │
                  ┌───────────▼────────────┐
                  │ Brief→Style Bias       │ 把 brief 投到 style manifold
                  │ Linear(384 → 128) + LN │ 上的"用户期望区域"
                  └───────────┬────────────┘
                              │  brief_bias (128 d)
                              ▼
        ┌─────────────────────┐
tag 池  │  Tag Embedding Bank │     280 个 game tags + 375 个 fashion tags
~655    │  E ∈ ℝ^(655 × 128)  │     init from sbert(tag 名字) + 微调
个 ──►  └──────────┬──────────┘
                   │
            训练时:soft mix
            采样:Dirichlet(α) over tags
            推理时:可硬选 / 软混 / 完全随机点
                   │
                   ▼  style_latent (128 d)
                   │
                   │  混入 noise channel (能量 10%)
                   │  z = √0.9 · style_latent + √0.1 · noise
                   │  noise ~ N(0, I), 128 d
                   ▼
                  ┌─────────────────────────┐
                  │ Latent → Anchor Plan    │  决定用哪些身体 anchor、几条 fabric stroke
                  │ MLP (128 → 256 → plan)  │  输出:variable-length anchor sequence
                  └──────────┬──────────────┘
                             │
                  ┌──────────▼──────────────┐
                  │ Stroke Decoder          │  自回归 / transformer
                  │ (style_latent 作 cross- │  逐 stroke 输出:
                  │  attention key/value)   │   - 起始 anchor (8 个枚举之一)
                  │                         │   - 终止 anchor 或自由 UV 点
                  │                         │   - 中间 Bezier 控制点 (4 个 UV 坐标)
                  │                         │   - 宽度 profile (3 段折线)
                  │                         │   - 张力 / drape 系数
                  │                         │   - fabric_color (256 调色板 OR 连续 HSL)
                  │                         │   - fabric_material (40 材质轴 embedding)
                  │                         │   - decoration_tags (多标签 soft mix)
                  │                         │   - <END> token
                  └──────────┬──────────────┘
                             │
                  ┌──────────▼──────────────┐
                  │ Renderer (复用 v2)      │  按 stroke list 在身体网格上画
                  │ + anchor grammar        │  每个 stroke = UV-投影的 ribbon
                  └──────────┬──────────────┘
                             │
                       3D mesh / png
                             │
                             ▼
                  ┌──────────────────────────┐
                  │ Judge (vllm Qwen-VL)    │ → reward (RL signal)
                  │ Symbolic fitness        │ → reward (gradient signal)
                  │ Manufacturability cls   │ → bool tag (后置筛选器,不进 loss)
                  └──────────────────────────┘
```

**核心三件事:**
- **Tag = embedding,style = 连续 manifold** — 原则 3 的硬实现
- **Stroke sequence 输出 = 变长 + anchor-grounded** — 原则 1 + Phase 1 修复
- **Manufacturability 是后置 tag 而不是 loss term** — 原则 1

---

## 4. 关键设计选择(我先做主,你审)

### 4.1 Style Latent 空间

| 项 | 选择 | 理由 |
|---|---|---|
| 维度 d | **128** | 跟现有 sbert post-proj 对齐,跟 trunk hidden 一致;128 维已经足够表达 ~655 tag 的协方差(信息论下限 ≈ log2(655) ≈ 9.4 bits / sample,128 维高斯有足量自由度) |
| 拓扑 | **欧式连续 manifold,不强制单位球** | VAE 风格的 N(μ, σ²) 采样自然支持插值/外推 |
| 采样分布 | 训练时 Dirichlet(α=0.5) over tag mix → ⨁ tag embeddings → style;**鼓励 multi-tag 软混合,不让模型只学单 tag 中心** | 反 "snap-to-nearest-tag" 塌方 |
| 推理时控制 | (a) 硬选 1 tag(brief 强约束),(b) 软混 N tag(brief 提示),(c) 完全随机点(自发新风格) | 给用户 3 档自由度 |

### 4.2 Tag Embedding Bank

| 项 | 选择 | 理由 |
|---|---|---|
| 初始化 | **sbert(tag 中英文名)→ 128 d Linear 投影** | 复用现成 sbert 已经 frozen 的语义先验,免训练冷启动期 |
| 是否可学 | **可学,但 EMA 防漂移**(每 epoch 把 embedding 拉回 sbert 初始位置一点点) | 既能微调到任务专属语义,又不让"cyberpunk"的 embedding 训着训着变成什么乱七八糟的方向 |
| 数量 | ~655(280 game + 375 fashion,去重后)| 全量收录,不预先筛 |
| 多轴并行 | 5 个轴(art_style / cultural / archetype / costume_convention / material_vfx),每轴有自己的 mix 系数 | 5 维 mix 给 brief→tag 检索更结构化 |

### 4.3 Noise Channel(10% 自由度的精确实现)

```python
# 训练时和推理时一样:
noise = torch.randn(batch, 128) * σ        # σ 可调,默认 1.0
style_latent = brief_bias + tag_mix         # 来自 brief + tag pool
z = math.sqrt(0.9) * style_latent + math.sqrt(0.1) * noise
# z 进 decoder
```

**为什么是能量预算而不是采样概率**:
- "10% 的样本完全无 conditioning" 太极端,得不到稳定训练梯度
- "每个样本的 latent 都有 10% 噪声成分" 是软约束,训练更稳,而且 noise 跟 style 同步反向传播,模型会学到怎么"利用 10% 自由度"产生未必命中 tag 但风格连贯的输出
- σ 推理时可调:σ=0 完全 tag 主导(最像 brief),σ=1 默认,σ=2+ 越来越野

### 4.4 输出端:Stroke Sequence 解码器

**为什么是 sequence 不是 fixed-slot**:
- fixed-slot 等于回到 v2 的 cup/bottom/strap 固定槽 — 表达力不够
- variable-length sequence 可以一件衣服只有 2 条 stroke(极简比基尼)或 12 条 stroke(复杂 harness + 多层 wrap)
- 自回归 + <END> token 是成熟模式,有大量参考实现

**Stroke 参数**(每个 token):
| 字段 | 类型 | 备注 |
|---|---|---|
| `start_anchor` | 8-way categorical | shoulder_L/R / sternum / underbust / waist / hip_L/R / pubis(从 v2 继承) |
| `end_anchor` | 8-way categorical OR free UV (2 floats) | 自由端给"垂坠尾"那种 |
| `bezier_controls` | 4 × (u, v) = 8 floats | 控制 stroke 在身体表面的路径形状 |
| `width_profile` | 3 floats | start / mid / end 宽度 (cm),允许 0 表示渐隐 |
| `tension` | 1 float ∈ [0,1] | 0=完全垂坠,1=紧贴 |
| `fabric_color_id` | 256-way categorical | 调色板 |
| `material_mix` | 40-way soft over E axis tags | 软混合材质语言 |
| `decoration_tags` | 70-way soft over decoration axis | 软混合装饰 |
| `is_end` | bool | <END> token |

最多 16 stroke / 件衣服(覆盖 99% 的设计复杂度)。

### 4.5 Anchor Grammar(从 v2 继承不动)

| v2 现有,继承 | 新加 |
|---|---|
| 8 个 anatomy anchor(shoulder_L/R, sternum, underbust, waist_L/R, hip_L/R, pubis,基于 `tools/anatomy.py`) | 加 2 个新 anchor:**collarbone** 和 **neck_back**(支持 halter / choker / 项链/披帛 起点) |
| `Connector.path_policy` 8 种枚举(halter_behind_neck / shoulder_acromion_scapula / …) | 自由 stroke 不强制 path_policy,但 stroke 必须 ≥1 端 anchor-bound(否则不让 sample,防 Phase 1 飘空) |
| `_arc_tube` / `_build_band_mesh` / `_body_ring` 等渲染 primitive | stroke renderer 调用这些 primitive 画 ribbon |

### 4.6 Manufacturability:后置 Tag,不进 loss

```python
# 训练后离线跑(或推理时挂):
def is_manufacturable(garment) -> bool:
    return (
        all_strokes_have_real_fabric(garment) and
        no_floating_only_anchors(garment) and
        seam_lengths_within_8pct(garment) and        # 继承 v2 H3
        piece_areas_above_min(garment) and            # 继承 v2 H1
        all_seams_in_catalog(garment)                 # 继承 v2 H4
    )
# 这个 bool 标在元数据里,不影响生成
# 产品线时:游戏 SaaS 用全集,真实泳装 SKU 只从 is_manufacturable=True 子集挑
```

**好处**:游戏角色那条路 100% 不被制造约束牵制;制造那条路靠后置筛选保证质量。

---

## 5. 训练流程

### Phase A — 重新预训练(从零)

| 阶段 | iter | 数据/采样 | loss |
|---|---|---|---|
| A1: tag embedding warm-up | 1000 | brief = tag 名字本身(自监督) | reconstruct: brief sbert ↔ tag emb cosine |
| A2: stroke decoder 模仿学习 | 5000 | 用 v2 库的现有 86 entries 转成 stroke sequence("教师")教 decoder 学输出语法 | cross-entropy on stroke tokens |
| A3: RL fine-tune(主) | 200-500 | brief 来自精选 brief 池;tag mix 随机 + brief-conditional + 完全 random 三档混合 | REINFORCE on (symbolic fitness + judge reward),加 batch-div 在 style_latent 上 |

### Phase B — 抗 mode collapse 机制

- **style_latent 多样性奖励** β · ‖cov(z_batch) − I‖² (鼓励 batch 覆盖 manifold,反堆中心)
- **entropy bonus on tag mix** — 反过度依赖单 tag
- **noise scaling schedule** — σ 从 1.5 慢慢降到 1.0,前期野探索后期精修
- **judge 多角度 prompt** — 9 维 sub-score 全部启用,brief_match 权重加大(防止 brief→color 信号稀)

### Phase C — Manufacturability 分类器训练(分支)

独立的小 NN(2 层 MLP on garment features),用 v2 现有 validate_garment 的 H1-H4 + S1-S2 规则做监督。完全跟生成器解耦,只在产品分流时跑。

---

## 6. 跟现有 1136 ckpt 的兼容性

| 现有组件 | 新架构里 | 怎么处理 |
|---|---|---|
| sbert encoder | **保留,frozen** | 不变 |
| input_proj (384→128) | **保留作 Brief→Style Bias 的初始权重** | warm-start |
| 18 trunk blocks (12 + 6 新加) | **作 Encoder 的 trunk warm-start** | 前 12 层加载,后 6 层 reinit;structure 变 VAE 后部分有用 |
| 12 个 categorical heads + continuous_head | **全废** | 输出格式整体不一样 |
| anatomy.py / Connector.path_policy / 渲染 primitive | **全保留** | 这是 v2 最有价值的资产 |
| symbolic fitness 框架 | **保留,权重重调** | 一些 cup/bottom 特定权重(top_back_coverage 之类)要弱化 |
| Qwen-VL judge | **保留 + prompt 重写** | 加 stylized 评分维度,加 brief_match 权重 |
| 调色板(还没建) | **新建 256 色 with 30 锚点色名** | 之前讨论的 palette 直接复用 |

**结论**:1136 ckpt 的 trunk 权重还能用作冷启动,但 head 全废。Phase A1+A2 需要从头训(估算 ~6-10h on A6000),A3 是主战场。

---

## 7. 工程里程碑 & 时间估算

| 阶段 | 工作 | 时间 |
|---|---|---|
| W1.1 | 多轴 tag pool 整合 + embedding init pipeline | 1d |
| W1.2 | 新 NN 架构代码(VAE encoder + transformer stroke decoder)| 3-4d |
| W1.3 | stroke → render 桥接(renderer 加 stroke 接口) | 3-4d |
| W1.4 | Phase A1 + A2 预训练 | 1d |
| W2.1 | symbolic fitness 重调 + judge prompt 重写 | 2d |
| W2.2 | Phase A3 RL 训练(首轮 200 iter) | 2d (compute time) |
| W2.3 | 评估 + 跟 1136 对照 | 1d |
| W3 | manufacturability 分类器训 + 接入 | 3d |
| W4 | 第一版稳定 demo + 文档 | 5d |

**合计 ~4 周到第一版可用 demo。** 比"继续在 v2 上微调"长,但出来的东西能彻底打开 Phase 3 平庸陷阱。

---

## 8. Phase 1/2 考古结论(简明版)

| 阶段 | 实际做法 | 真死因 |
|---|---|---|
| 史前 Phase 1(pre-git) | 纯自由多边形,无身体锚定 | **一致性塌方** — 多边形飘空,不挂身体 |
| v1(到 2026-05-08) | 44 维 Genome 浮点 → 公式切多边形,**已经按身体 anchor 切** | **可制造性塌方** — "浮点中间值产生'四不像',制造端不能解释" |
| v2(今天 2026-05-27) | 离散库 86 条目 + 库内 local_params | **表达力锁死** — 显式只支持 two-piece 比基尼,one-piece 走 legacy 死路 |

**新架构对上述的修法:**
- ✅ Phase 1 anchor 失败 → 新 stroke 强制 ≥1 端 anchor-bound
- ⚪ v1 可制造性失败 → **故意不修**(原则 1),改为后置分类器
- ✅ v2 表达力锁死 → 变长 stroke sequence 解锁

---

## 9. 给用户的决策点(请确认或改)

| # | 决策 | 我推 | 备选 |
|---|---|---|---|
| D1 | style latent 维度 | **128** | 64(更紧凑)/ 256(更宽松) |
| D2 | tag embedding 初始化 | **sbert(tag 名)+ 微调 + EMA 拉回** | CLIP / 完全 learned from scratch |
| D3 | 10% 自由度形式 | **能量预算混合** `√0.9 style + √0.1 noise` | 10% 样本 unconditional / KL 正则 |
| D4 | 输出架构 | **VAE encoder + 自回归 transformer stroke decoder** | pure diffusion(更强但 5× 慢)/ 自回归无 latent VAE(更简单但反 collapse 弱) |
| D5 | stroke 数量上限 | **16** | 8(更紧)/ 32(更野) |
| D6 | 新加 anchor | **collarbone + neck_back(共 10 个 anchor)** | 不加(保 8 个) |
| D7 | manufacturability | **后置分类器,不进 loss** | 进 loss 但权重低 |
| D8 | 首轮训练规模 | **Phase A 全部 + 200 iter A3 ≈ 3-4 天** | smoke 4 iter 先验证流程 |

**点头我就开干 W1.1**(tag pool 整合 + embedding 初始化代码)。**或者哪条要改,直接说。**

---

## 10. 这个设计跟项目根本目标的对齐 check

| 项目目标 (CLAUDE.md) | 对齐情况 |
|---|---|
| 真壁垒 + 真商业价值 | ✅ 游戏角色服装 SaaS 是真 H 万亿市场,可制造泳装是 break-out |
| 三角差异化:**AI 生成 + 真 3D 几何 + 可制造** | ✅ 三角全在;可制造从硬约束变软子集 |
| 不接受"做初级 demo 看一眼" | ✅ 这个方案就是冲长期能力做的,不是给 demo 用 |
| 想象力丰富,有张力 | ✅ 原则 3 直接编码到架构里 |
| 不离奇,有美感 | ⚠ 这点靠 judge 评分把关,prompt 要写清楚 "artistic-not-bizarre" |

---

## 11. 已知风险

1. **训练数据冷启动难** — 没有 ground-truth 设计样本教 stroke decoder 怎么"画一条 stroke"。Phase A2 用 v2 库 86 entries 转 stroke teacher 是冷启,质量上限受 v2 限制
2. **judge 评 stylized 维度可能不准** — Qwen-VL 7B 对 "Iris van Herpen 风" 的判断未必比对 "红色比基尼" 准。需要构造更结构化的 multi-dim prompt
3. **训练成本** — 4 周到第一版,比"继续在 v2 微调"长得多。如果中途市场窗口变了,机会成本高
4. **Phase A2 的"教师"如果不够好** — stroke decoder 学不到合理的"画 stroke"语法。备选方案是手工标注 30-50 个高质量 stroke 序列教师样本

---

**End of design doc.** 接下来等用户点头 → 启动 W1.1。
