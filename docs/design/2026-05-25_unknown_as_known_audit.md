# 「未知当已知」反模式审计 (2026-05-25)

## 原则

**未知 ≠ 0,未知 ≠ 默认值,未知 ≠ 任何具体值。**

把"我没观测到"静默改成"我观测到了某个具体值",喂给训练就是噪声梯度
—— 数学上可以推出任意结论(包括 180° 反向),完全偏离真实。

## 已知历史踩坑

| 时间 | 现象 | 根因 | 修法 |
|------|------|------|------|
| 早期 swimsuit_2 模板泄漏 | 240 个 batch variant cup 全在同一垂直位置 | `cup_p.get("center_v", 0.74)` 默认值传染 100% 输出 | `_center_v_range_for` 给每个 cup 加 schema |
| 2026-05-25 RL reward=0 | 35 iter 训练全 reward=0,4 小时白训 | render 子进程 cleanup 阶段 SIGSEGV → 当真 fail → reward=0 → NN 学到假信号 | known_mask + unknown 排除 |

## 当前代码 audit(grep 命中)

### A. `.get(field, default)` — **118 处**(全代码库)

最危险的集中地:
- **`outfit.py`: 39 处** ← 高危,直接喂 genome / 灌 RL
- `pretrain_generator.py`: 15
- `iter/outfit_ga.py`: 8
- `batch_from_diverse_seeds.py`: 7
- `rl_runner.py`: 6
- `render3d_uv.py`: 4

#### A1. `outfit.py` 已知未修透的传染源

```python
# L786-791  outfit_to_genome 里 cup_p.get(field, default)
top_center_v=cup_p.get("center_v", 0.74),
top_half_v=cup_p.get("half_v", 0.07),
top_half_u=cup_p.get("half_u", 0.16),
top_inner_u=cup_p.get("inner_u", 0.10),
top_apex_lift=cup_p.get("apex_lift", 0.15),
top_underband_dip=cup_p.get("underband_dip", 0.05),

# L798-800  bot 同理
bot_front_top_v=bot_p.get("front_top_v", 0.25),
bot_front_half_u=bot_p.get("front_half_u", 0.18),
bot_front_leg_curve=bot_p.get("front_leg_curve", 0.65),

# L547-554  center_gore 里 cup_params.get(...)
"center_v": cup_params.get("center_v", 0.74),
"half_v": cup_params.get("half_v", 0.07),
...
```

**风险等级:CRITICAL**(影响 NN 训练梯度方向)

**情景**:NN 随机选了一个 cup 库条目,但那个条目的 local_params_schema 没声明 center_v。NN 的 continuous head 输出的 top_center_v 应该被使用,但被 `.get("center_v", 0.74)` 替成 0.74。**NN 的输出被静默丢弃,梯度方向是基于"NN 出 0.74"算的反向传播,而 NN 实际上想出别的值。** NN 永远学不会用 center_v 这一维。

CLAUDE.md 里写过的"swimsuit_2 模板泄漏"就是这一行。`_center_v_range_for` 修了 center_v 一条,但 half_v / half_u / inner_u / apex_lift / underband_dip / front_top_v / front_half_u / front_leg_curve / back_top_v / back_half_u 这 10 条**仍然在用 `.get(..., 硬编码默认)`**。

**修法**:
- 要么:每个 library entry 的 local_params_schema **必须** declare 所有 used field(运行时校验,缺一报错而不是默认)
- 要么:`outfit_to_genome` 改成失败时**抛错**,不要 silently fill default

#### A2. `outfit.py` global_design.get(...)

```python
hue=outfit.global_design.get("hue", 0.5),
saturation=outfit.global_design.get("saturation", 0.6),
lightness=outfit.global_design.get("lightness", 0.5),
...
pattern_overlay=outfit.global_design.get("pattern_overlay", "solid"),
```

**风险:HIGH**。若 ConfigToOutfit 漏填某个颜色字段,outfit 看起来正常但
NN 实际控制不到那一维 — NN 学到 "color = 0.5" 是无意义的安全中位。

### B. `except: pass / continue` 静默吞 — **22 处 across 8 files**

#### B1. `render3d_uv.py`: **10 处**(高危集中地)

最严重的 3 个:

```python
# L2415-2419  legacy halter strap 构建
straps.append(("halter_R", halter_R))
straps.append(("halter_L", halter_L))
except Exception:
    pass
```
**halter 整个 silent fail** → 渲染图里没有 halter strap,但 NN 的 has_neck=1 → NN 收到的 reward 是按"有 halter"算的,实际渲出来的图判官看到的是"无 halter"。**信号反向**。

```python
# L2505-2509  shoulder strap 构建
straps.append((name, strap))
except Exception:
    pass
```
同上,shoulder strap silent fail。

```python
# L2418  (今天刚改对)O-ring 构建在改之前
ring = _build_torus(anc, radius_cm, tube_radius=0.08)  # TypeError 永久被吞
except Exception:
    pass
```
**修了,但其他 silent except 全是同一个 pattern**。下次某个 mesh builder
有 typo,bug 会再次被吞,NN 还是错信号训练。

#### B2. `iter/capture.py`: 4 处

- L201-207: seam_mesh build 失败 → 没缝线,NN 不知道
- L312-315: weave normal texture 失败 → 缩到无 normal map
- L329-332: bind_mat 颜色读取失败 → 用默认白色 binding

中等风险,主要影响视觉细节。

#### B3. `vision_judge.py`: 1 处

```python
try:
    return json.loads(text)
except json.JSONDecodeError:
    pass
```
判官返回的 JSON 解析失败 → 返回 None / 落到下一个 fallback。需要确认下
一步是怎么处理 None 的(可能也走 zero-reward path)。

### C. 空 dict / 空字段当"已观测到默认值"

#### C1. `train_loop.py` (老代码,部分修了)

```python
results = [JudgeResult.from_dict({}, backend="error") for _ in briefs]
```
判官整体失败 → 用空 dict 构造的 JudgeResult,所有 sub-score = 0,
is_valid_swimsuit=False。如果在 RL loss 里被当真 reward 用 → fake-zero
污染。

**状态**:今天的 known_mask 修法**部分覆盖**了这条 —— 我把整 batch 失
败也标 unknown,但单条记录里如果哪个 sub-score 来自空 dict 默认值,
还是有传染风险。需要 JudgeResult 区分"真观测到 0"和"未观测,缺省 0"。

#### C2. JudgeResult.from_dict({}) 自身

```python
@dataclass
class JudgeResult:
    is_valid_swimsuit: bool = False  ← 默认 False!
    pelvic_coverage: int = 0          ← 默认 0!
    chest_coverage: int = 0           ← 默认 0!
    ...
```

**任何**没设置的字段都默认 False / 0。一个真实的判官输出"该 dim 我没
打分"跟"该 dim 我打了 0 分"区分不出来。下游 `_reward` 计算时把两者
都当 0 处理。

**修法**:用 `Optional[int] = None` 而不是 `= 0`。`_reward` 看到 None
要跳过那一维而不是算成 0。

### D. anatomy / classifier fallback

#### D1. `body_region_classifier.classify_vertices` 失败时

需要检查:如果 anatomy.detect 抛错,会不会退到"所有顶点都是 torso"
(=允许所有 polygon 落)?这是 silent permissive — 比 silent restrictive
更危险,因为渲染会"看起来正常",但 polygon 实际上覆盖了不该覆盖的区域。

**TODO**:跑一遍代码确认。

### E. subprocess returncode 判定(今天修了一处)

```python
# 原 RenderRunner 老代码:
if rc.returncode != 0:
    raise RuntimeError(...)   # → except → paths.append("") → fake zero
```

**状态**:今天改成"看 PNG 在不在"。但同模式还存在于:
- `library_regression_render.py`:今天的脚本里其实也走了同一条路,改对了
- 任何其他 subprocess 调用?需要 grep 一遍

## 优先级修法清单

| 优先级 | 位置 | 风险 | 工作量 |
|--------|------|------|--------|
| P0 | `outfit.py` L786-803 cup_p.get / bot_p.get 默认值传染 | NN 训练梯度方向假 | 2-3h(改 schema 校验 + 测试) |
| P0 | `render3d_uv.py` L2415, L2505 halter/shoulder silent except | 渲染缺件,reward 反向 | 1h(改 except 加 log + 暴露) |
| P1 | `JudgeResult` 默认 False/0 不能区分"未打分"vs"打 0 分" | 子分错算 | 1.5h(改 Optional[] + _reward) |
| P1 | `render3d_uv.py` 剩余 8 处 silent except | mesh 静默缺件 | 1h(全部改成 log 替代 pass) |
| P2 | `outfit.py` global_design.get(color, 0.5) | 颜色维 NN 学不动 | 1h |
| P2 | `iter/capture.py` 4 处 silent except | 视觉细节 | 30m |
| P3 | `vision_judge.py` json parse fallback | 判官输出降级 | 30m |
| P3 | anatomy classifier fallback 行为确认 | 可能允许过度 polygon | 1h 调查 |

总计:**~12 小时** authoring + 测试。

## 推荐做法 (engineering norm)

加到 CLAUDE.md 「工程惯例提示」一栏:

```markdown
- **未知 ≠ 0 / 默认值**(底层逻辑红线)。任何 silent fallback ——
  `.get(k, default)`、`except: pass`、`if x is None: x = 0`、
  subprocess rc != 0 当 fail、judge 空 dict 当 0 reward —— 都是把
  "我没观测到" 静默改成"我观测到了某个具体值"。喂给训练 = 噪声梯度,
  能推出任意结论(包括反向)。规则:
    * 未知就显式标 None / NaN / sentinel,不要用 0 或 hardcoded default
    * 含 unknown 的 sample 从 loss / mean / 评分里**整体剔除**
    * silent fallback 改成 explicit print + 计数,让"未知"可见可计
  历史踩坑:swimsuit_2 模板泄漏(`.get`,早期);RL reward=0 假信号
  (2026-05-25)。
```

## 这次 audit 学到的

- 单个 bug 修了是事后救火;**反模式 audit 才是预防**
- 这种 bug **不会让代码崩** —— 它默默把训练带歪。比崩溃更隐蔽更危险
- 找这种 bug 不能靠 NN 训练表现来反推(NN 收到假信号也会"看起来在
  学"),要靠**代码 audit + 显式 unknown 标记**
- 修一个 silent except 比修十个具体几何 bug 收益高
