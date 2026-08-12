# Yiyun · ArtiCraft Verifier A1–A6

PRO-12 自动验证器中 A1–A6 六项指标的第一版可执行评分头。

这是准备提交到 `kaichen-z/Evo-Articraft` 的独立个人目录。它不复制 Wanglin 的
B7–B10，也不复制 Xuge 的 B11–B14；三部分通过相同的指标编号和
`score / prediction / threshold / confidence / coverage / evidence / repair_hint`
输出语义对齐，最终由总仓库统一汇总。

本目录遵循 `B11-14 for xuge` 的工程约定：

- `metrics/` 中的 `score(signals, contract, consts)` 是纯函数；
- 不在评分时调用 LLM/VLM、读取文件或启动仿真器；
- 工具故障不等于资产失败；
- `not-applicable`、`unsupported` 与 `partial` 不伪装成通过；
- 每个失败返回可定位证据和修复建议；
- 所有阈值集中在 `consts.py`。

## 数据流

```text
Prompt --(独立 contract extractor + 人工审核)--> contract.json
资产  --(parser / geometry / renderer / VLM)----> signals.json
contract + signals --> metrics/a1.py ... a6.py --> MetricResult
```

这一版已经把确定性评分头接到真实资产前端，并保存了修改前的全量人工标注对齐基线；它不假装已经
解决以下研究问题：

1. Prompt 中部件、数量、关系和功能接口的可靠提取；
2. Prompt 名词与 `model.py` part 名称的高精度语义匹配；
3. A4 多视角 VLM 的人工校准；
4. A5 对复杂凹体、功能面和局部接口的通用关系测量；
5. A6 对“预期支撑面”的场景语义建模。

## 指标与输入

| 指标 | contract 决定 | signals 提供 |
|---|---|---|
| A1 零件拆分与活动属性 | `required_movables` | 预期/实际活动件匹配数、多余活动件 |
| A2 零件数量与类型 | `required_parts` | 每类实际数量、类型匹配分 |
| A3 必要结构完整性 | `required_parts`, `required_interfaces` | 匹配部件/接口 ID |
| A4 形状尺寸比例 | `appearance_claims` 或 `category_scale` | VLM 真实感、跨视角一致性、实际尺度 |
| A5 位置朝向装配 | `spatial_relations` | 每条关系的位置/朝向/侧面/邻域分 |
| A6 初始状态完整性 | 默认适用 | q0 穿透、脱离比例、悬空间隙 |

## 运行

```bash
cd yiyun
python -m pytest -q
```

测试状态：运行 `python -m pytest -q` 查看当前结果。

## 当前完成度

- 已完成：A1–A6 评分头、Contract 扩展 schema、结果序列化、边界状态与单元测试；
- 已接入：真实 `model.py` 静态 AST 解析和确定性名称匹配，为 A1–A3 生成信号；
  最新匹配器实行候选独占，避免一个实际零件同时满足多个 Prompt 要求；不能解析的
  joint/part 字段触发 abstain/tool-failure，而不会被当成资产缺失；
- 已接入：Articraft SDK 默认姿态真实 mesh overlap 与 isolated-parts 检查，为 A6 生成信号；
- 已接入：冻结人工标注的批量对齐评测，输出 coverage、precision、recall、F1、AUC、balanced accuracy 和误报/漏报 ID；
- 已实现：A3/A4/A5 离线 LLM Contract extractor。它沿用 Wanglin 的
  `gemini-3.6-flash`、temperature 0、JSON-only 和逐条 Prompt 原文引用协议；LLM
  只生成 `required_interfaces` / `appearance_claims` / `spatial_relations`，不接触资产也不直接评分；
- 已接入：A3 明示实体接口的“命名实体 + 正确 joint 双方”诊断；该信号尚不能证明
  轴承/滑轨几何真实有效，因此覆盖状态为 `partial`；
- 已接入：A5 默认姿态真实几何 AABB 测量，可处理 above/below、between、inside、
  adjacent/attached、centered 等直接关系；无法可靠测量的分量不会补成满分；
- 已接入：A4 八视角离屏渲染与 Codex/VLM 原始视觉测量。示例结果见
  `results/a4-signals/` 和 `results/post_change_pilot_tilting_fan.json`；完成人工标签校准前
  只能输出 `partial/abstain`；
- 已改进：A6 优先用解析几何或 watertight mesh 的实体体积计算脱离比例；无法完整读取
  体积时才退回零件数量代理，并显式标为 `partial`；
- 示例：`examples/contracts/air_fryer_a_contract.json` 展示由 Codex 从 Prompt
  提取并冻结的 A3/A4/A5 要求；
- 尚不完整：A4 缺少校准的多视角 VLM；A5 尚未覆盖所有关系与局部 mesh/SDF；A6 的
  SDK isolated 检查没有为所有案例建立 Prompt 指定的地面/桌面/壁挂支撑面；
- 未校准：当前公式权重和 0.70 阈值仍是 proposal 的第一版参数。

因此，“代码可执行”不表示这些指标已经被证明具有判别力。

## 修改前基线结果（2026-08-12）

线上最新人工标注快照共 616 条，616 条对应资产均已稀疏下载并成功运行，零缺失、
零批处理崩溃。下表在本轮实现修正之前生成，是对照基线而不是新代码的最终效果。详细结果见
`results/alignment.md`，逐资产证据见 `results/a1_a6_reports.jsonl`。

| 指标 | 有分数案例 | AUC | F1 | 结论 |
|---|---:|---:|---:|---|
| A1 | 95 | 0.730 | 0.340 | 有排序信号，但 precision 仅 0.209，误报多 |
| A2 | 97 | 0.539 | 0.259 | 接近随机，当前名称/数量方法判别力不足 |
| A3 | 97 | 0.590 | 0.400 | 只有弱信号，需要接口级 Contract |
| A4 | 0 | — | — | 尚无批量校准 VLM 信号 |
| A5 | 0 | — | — | 尚无批量空间关系信号 |
| A6 | 281 | 0.586 | 0.517 | recall 1.0，但大量误报且 kappa=0，不能作硬 verifier |

A1–A3 当前使用 Wanglin 2026-08-12 版 `contracts-300/` 中实际完成的 98 份 Contract；
其中 95–97 条能对相应指标给出分数，其余为 N/A 或解析工具失败。A6 对全部 616 条
运行真实 SDK mesh，其中两条几何查询失败；只有 282 条拥有新版 A6 人工标签，故可
对齐评分 281 条。A6 在这次基线运行中使用零件数代理。新代码已加入实体体积测量，但
尚未完成 616 条全量重跑，因此不能把旧表当成修正后的效果。

这一轮的结论不是“verifier 已经有效”，而是完成了真实信号前端和人工标签评测，并
定位了下一轮应优化的对象：A1 降低误报，A2/A3 改进语义与结构证据，A6 区分合法
接触/嵌套和真正穿透。当前代码已进一步接入 A4/A5 前端，但需要批量 Contract、测量和
校准后才能生成新的正式结果表。

## 真实批量运行

```bash
python -m verifier.run_batch \
  --data-dir /path/to/articraft-data \
  --annotations data/annotations/annotations-2026-08-12.csv \
  --contracts data/contracts-300 \
  --extensions examples/contracts \
  --a4-signals results/a4-signals \
  --output results/a1_a6_reports.jsonl

python -m verifier.evaluate_reports \
  --annotations data/annotations/annotations-2026-08-12.csv \
  --reports results/a1_a6_reports.jsonl \
  --json results/alignment.json \
  --markdown results/alignment.md
```

静态 A1–A3 快速检查可加入 `--no-a6`；完整 A6 会执行生成的 Python/CAD 代码，
只能用于受信任的本地 Articraft 数据。

## A3/A4/A5 Prompt Contract 提取

默认使用本机已登录的 Codex CLI，结构化输出受 JSON Schema 约束：

```bash
python -m verifier.contracts.extract_a4_a5 \
  --data-dir /path/to/articraft-data \
  --annotations data/annotations/annotations-2026-08-12.csv \
  --output-dir data/contracts-a3-a5
```

也可以显式使用与 Wanglin 相同的 Gemini 路径：加
`--provider gemini --model gemini-3.6-flash --env-file /path/to/.env`。Gemini 密钥只从
`GEMINI_API_KEY` 环境变量或显式 env 文件读取，不进入 URL、输出或仓库。

提取器只接受 Prompt 明示且带逐字引用的硬要求。类别常识进入
`advisory_inferences`，不参与扣分。生成 Contract 后，A4 仍需渲染/VLM 或几何比例
测量，A5 再用实际模型的相对变换和几何测量；LLM 不替代这些真实资产证据。

单案例 A4 测量示例：

```bash
python -m verifier.measure_a4 \
  --data-dir /path/to/articraft-data \
  --extensions data/contracts-a3-a5 \
  --output-dir results/a4-signals \
  --render-dir results/a4-renders \
  --record-id rec_tilting_fan_540930b6847a441892643dedf9b71761
```

## 与现有 SDK 的连接点

- A1–A3：解析 `object_model.parts`、`object_model.articulations` 后，由独立语义匹配器产出匹配 ID/数量；
- A4：离屏八视角渲染器与经过人工 A4 标签校准的 VLM 产出概率；
- A5：FK/相对变换、包围盒和 mesh 距离产出每条契约关系的四个子分数；
- A6：可复用 Articraft 的 `fail_if_parts_overlap_in_current_pose()`、`fail_if_isolated_parts()` 和精确 mesh 查询，但必须把布尔结果扩展为穿透深度、脱离体积比例和悬空间隙。

因此，当前目录已经完成评分头和输出契约；下一步是实现/接入 `signals` 生成前端，并在人工标注开发集上测逐项 precision、recall、F1，而不是直接把公式分数当作有效性证明。

## 当前边界

- A1–A5 依赖经过审核的 Prompt contract。没有明确要求时返回 N/A，而不是让模型补出的常识成为硬 GT。
- A4 在没有校准 VLM 时只能部分覆盖；仅尺度证据不会被报告为完整判断。
- A6 的 `unexpected_penetration_m` 必须已扣除明确允许的接触/嵌套；否则会把合法装配当成失败。
- 公式与 `0.70` 初始阈值来自 PRO-12 草案，仍需在开发集上逐项校准并在留出评测前冻结。
