# Evo-Articraft P2 · Geometry Fidelity（GF1–GF4）

对通过 Initialization Gate 的资产评估几何保真度。本仓库是 P2 的可运行实现，
**接口已对齐 P0 提示词契约与 P1 Gate 绑定的真格式**（规格见 `task-2_08-16-p0/p1/p2.html`），
并在 20 个典型案例上端到端验证。

## 四个指标

| 指标 | 消费的 P0 字段 | 判定方式 |
|---|---|---|
| GF1 | `global_form` {category, geometry, coarse_structure} | 4 视角中性渲染 × 全局文本，冻结 CLIP 余弦 + 20 类干扰项 softmax |
| GF2 | `part_geometry` [{id, geometry}] | 逐部件隔离渲染 × 部件形状描述文本，先聚视角再宏平均 + 兄弟部件辨识概率 |
| GF3 | `part_relations` [{subject, relation, object}] | 确定性 3D 测量：attached_to（符号距离三态）、inside（AABB 体积占比）、above、aligned |
| GF4 | `proportion_claims`（成组或成对，含 measure/target_ratio/tolerance） | `exp(−\|log(r_obs/r_target)\|/σ)`，σ = ln(1+tolerance) |

规则：`overall_description` 只给人读，**不进任何评分**（P0 明文规定）；
GF1/GF2 裸余弦只在同类间可比，读干扰项概率与排名；
不可测（引用解析失败 / link 无几何 / 渲染退化）记 unmeasurable 单列，不折成 0 分。

## 与上游的接缝（无缝切换设计）

- **P0 接缝 = `specs/<rid>.json`**：文件就是 P0 契约本身的形状。今天由
  `p2/spec.py` 自动起草替身（prompt + URDF 命名/拓扑 + 命名对称性，每条 claim 带
  `source`）；P0 就绪后**整文件替换**即可，评分代码不动。
- **P1 接缝 = `p2/binding.py` 的 `PartBinding`**：GF2/GF3/GF4 的所有部件引用都经它
  解析（实例 ID → 抽象 part（展开全部实例，须全满足）→ geom 名兜底（子部件级引用，
  如 `drawer_front`））。今天用 URDF link 起草替身绑定；P1 就绪后换成 Gate 交付的
  part→body/geom 绑定表。`required_parts` 的 count 展开（drawer×3 → drawer_1..3）
  也在这一层处理。
- **资产格式**：正式流水线是 **MJCF 原生**，而 ArtiCraft 存货全部为 URDF
  （缓存中无任何 .xml，代码库亦无 MJCF 导出能力）——MJCF 从哪来是待确认问题。
  URDF 融合导致零件名丢失的问题已解决：`Scene.load` 在内存中向 URDF 注入
  `<mujoco><compiler fusestatic="false" meshdir=.../></mujoco>`，禁止 fixed link
  融合、零件名全量保留；fused-proxy 别名仅作加载失败时的回退保留。

## 运行

```
python select_cases.py        # 从 train.csv 选 20 个典型案例 → cases_20.json
python runner.py              # 全流程；--limit N 只跑前 N 个；--no-clip 跳过编码器
python make_report.py         # 生成 out/p2_smoke_report.html
```

Python 用 `D:\projects\articraft-verifier\.venv`（mujoco 3.11 + torch + open_clip + pillow）。
产物：`out/results.json`（全量证据）、`out/summary.csv`、`out/renders/<rid>/`。

## 冻结协议与暂定参数

- 渲染：448²、方位角 0/90/180/270、仰角 −20°、距离 1.7×AABB 对角线、统一灰材质、
  分割通道抠浅灰背景；渲染 collision 几何。
- 编码器：open_clip ViT-B-32 / laion2b_s34b_b79k。
- GF3 容差（·D 归一化）：attached_to 间隙 ≤0.010、穿透 ≤0.005；inside ≥0.70；
  above z-gap ≥−0.05 且投影重叠 ≥0.30；aligned 偏轴 ≤0.05。
- GF4：σ = ln(1+tolerance)（容差边界处得分 = 1/e）；measure 约定（AABB v0）：
  height=Z 边、length=水平长边、width=水平短边、area=水平投影面积、volume=AABB 体积、
  long=三边最大（替身对称 claims 用）。
- 全部为 PROVISIONAL（`p2/consts.py`），回显在 results.json 的
  `protocol.provisional_params`；重点校准点：ATTACH_MAX_PEN 的 0.005–0.01·D 敏感带。

## 待与团队对齐的接口问题

1. **子部件引用的绑定约定**：P0 示例里 `drawer_front` 比 part 更细——在 MJCF 里
   约定为 geom 名、site 名，还是 Gate 绑定表的一层？当前实现按 geom 名兜底。
2. **tolerance → σ 的换算**：P2 公式用 σ_r，P0 声明 tolerance；当前用 σ=ln(1+tol)
   （边界处 1/e），需和 P2 公式作者确认。
3. **measure 的几何定义**：length/width 在旋转过的部件上有歧义，当前用世界系 AABB
   （v0 约定），正式版可能要 OBB。

## 20 案例运行结论（2026-08-19，fusestatic 注入后）

- 20/20 跑通，0 工具故障，单轮 21 s（含 CLIP 编码）；119 个零件全部可测，
  不可测清零，证据中无 fused-proxy。
- GF3 判负 20/105 条声明，其中 attached_to 的失败（19 条）**全部是 penetration**
  （−0.008·D ~ −0.24·D）、0 条 separated：这批资产的典型缺陷是实心建模互嵌
  （套管、碗架、转盘中轴）。唯一非 attached_to 失败是打印机的 above 声明——
  盖子嵌坐在机身翻边之间（z-gap −0.069·D），换真身测量后依然如此，
  属 above 语义/容差的校准问题而非测量假象。
- 深穿透案例与人工 A6 标注方向一致（3/7 直接对上；4 个分歧案例全在此前 B12 待复核
  假正例名单中，先验偏向标注遗漏）。
- GF1 13/20 在 20 类干扰中排第 1；排名差的是中性灰渲染下无法与"柜子"区分的方盒资产
  （编码器已知局限，佐证"裸余弦不可当绝对分"）。
