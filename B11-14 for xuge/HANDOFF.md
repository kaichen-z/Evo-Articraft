# ArtiCraft Verifier — B11–B14 交付与校准报告

> 一份文件包含:交付状态、机制说明、核心代码、在 219 条人工标注上的校准结果、
> 待决策事项。最后附一段可直接在群里发的总结。

---

## 0. 一页纸摘要

**做完了什么** — PRO-12 中 B11–B14 四条指标的完整实现,加 MuJoCo 后端。
113 项测试通过,柜子案例四个验收数字精确复现。在 219 个真实 ArtiCraft 资产上
跑通,零失败。

**验证结果是负面的** — 对照 219 条人工标注,四条指标的判别力约等于随机
(AUC 0.49–0.57)。已逐层排除阈值、公式、估计量、标注质量四种解释。

**根因** — 不在公式,在测量对象。`g₀` 取最小距离,分不开"真合页"和"两块板
硬凑在一起";`S_clearance` 在装配体里必然归零,而它是乘性因子,一个人清零了
三分之二的 B12 分数。

**唯一有信号的方向** — "关节邻域有没有专门的连接硬件"(轴筒/销/支架)。
被判失败的资产,关节轴附近小几何中位数 2 个;判满足的 5.25 个。这个量不在规范
的七个乘性因子里。

**要负责人定三件事** — ①`S_clearance` 重定义或删除;②指标覆盖与真实失败分布
错配(B11+B14 只对应 15 条失败却占一半指标,第二大失败模式零覆盖);
③"连接硬件"算 B12 的新因子还是新指标。

---

## 1. 交付状态

按 CLAUDE.md 的开发顺序:

| 步骤 | 状态 |
|---|---|
| 1. `types.py` + `consts.py` + 契约 schema | 完成 |
| 2. `metrics/b11–b14.py` + 全部单测 | 完成(**这是可交付线**) |
| 3. `primitives/sweep.py` 几何扫掠 | 完成(改用 MuJoCo `mj_geomDistance`) |
| 4. `sim/runner.py` 按冻结协议展开 2s/3s/1s | 完成 |
| 5. 端到端接柜子案例 | 改为在 219 个真实资产上跑,见第 5 节 |

### 文件清单

```
verifier/
  consts.py            所有常量的唯一来源, FROZEN 与 PROVISIONAL 分区
  types.py             MetricResult / Coverage / Prediction / ToolFailure
  contracts/schema.py  需求契约 schema 与校验
  metrics/
    _common.py         数值守卫、结果组装、置信度与判定
    b11.py b12.py      ← 四条打分函数, 纯函数
    b13.py b14.py
  primitives/sweep.py  32 步几何扫掠
  sim/
    loader.py          URDF → MjModel, provenance 判定, 协议参数冻结
    protocol.py        2s/3s/1s 相位与 q_ref(t)
    runner.py          动态试验, 三次鲁棒性试验
    signals.py         扫掠 + 动态 → 一份 signals dict
  report/serialize.py  输出契约序列化与试验聚合
tests/                 113 项
calibration/           本次校准的脚本、结果与说明
```

### 测试

```
113 passed
```

其中柜子案例(PRO-12 §08)四个数字容差 1e-3 内复现:

```
S_B11 = 0.1629970559    规范 0.163
S_B12 = 2.2455548966e-5 规范 0.000022
S_B13 = 0.0116985305    规范 0.0117
S_B14 = None, coverage = not-applicable
```

---

## 2. 架构与数据流

```
model.urdf
  │
  ├─1─ sim/loader.py        判 provenance · 冻结 timestep/solref/solimp · 算 D
  ├─2─ primitives/sweep.py  32 步几何扫掠 → 静态量(不跑物理)
  ├─3─ sim/runner.py        2s静置 / 3s驱动 / 1s保持 → 动态量
  ├─4─ sim/signals.py       合成一份 signals dict
  └─5─ metrics/b11-b14.py   纯函数打分
```

关键设计:**`metrics/` 只吃一个 dict,不 import mujoco**。换仿真器只影响 1–4 步,
四条打分函数一行不改。没装 mujoco 时前 88 项单测照跑。

### provenance 三档

由 URDF 内容直接决定,对应 PRO-12 §04 的 `q_physics`:

| URDF 内容 | provenance | q |
|---|---|---|
| 有 `<inertial>` | `asset` | 1.0 |
| 只有 `<collision>`,质量由 MuJoCo 按密度推 | `inferred` | 0.8 |
| 都没有(视觉级模型) | 加载即 tool-failure,**不为它伪造物理参数** | — |

219 条实测:83 条 `asset`,136 条 `inferred`。

### 打分前的两道闸门

1. **不适用闸门** — 契约没声明就返回 `not-applicable`,`score=None`,不进聚合分母
2. **工具故障闸门** — `solver_failed`、信号含 NaN/inf、归一化尺度 ≤0 →
   `coverage="tool-failure"`,`score=None`。**绝不返回 0.0**

---

## 3. 四条指标怎么算

下面用真实资产 `rec_air_purifier_with_filter_door_0008` 走一遍,所有数字都是实测。

```
provenance=asset   D=2.2705m   总质量=12.600kg   njnt=1   ngeom=67
关节 'housing_to_filter_door'  行程=1.8500 rad

扫掠: r_geom=1.0000  P_j=0  L_j=1.6767  g0=-0.005000
      g_drift=0.006413  d_anchor=0.68440  s_clear=1.0000
动态: q_end=1.85024  rmse=0.09802  overshoot=0.00112
      p_dyn=0.001075  t_stall=0.0542  impulse=0  d_gravity=0
```

### B11 可用关节运动范围

```
S_B11 = R_geom · C · T · L = 1.0 × 1.0 × 0.3466 × 0.9701 = 0.336
```

| 因子 | 量什么 | 怎么量 | 本例 |
|---|---|---|---|
| `R_geom` | 几何上能走通多少行程 | 32 步扫掠,新增穿透超 `0.001·D` 判该步阻塞;`R_geom = 首个阻塞步/31` | 1.0 |
| `C` | 动态上实际走到哪 | `\|q_end−q_start\| / \|q_target−q_start\|` | 1.0 |
| `T` | 轨迹跟得准不准 | `exp(−RMSE/(0.05·Δq))` | 0.347 |
| `L` | 有没有冲过头 | `exp(−overshoot/(0.02·Δq))` | 0.970 |

**注意**:本例 B11 掉到 0.336 全由 T 造成,而 T 由 PROVISIONAL 的 PD 增益和梯形
轨迹决定。**这个分数说的是执行器参数选择,不是资产质量**(见 QUESTIONS.md 第 1 条)。

### B12 实体接口与物理支撑

```
S_interface = 0.8615 × 0.9264 × 0.00240 × 1.0 = 0.001915
S_gravity   = 1.0    × 0.6438 × 0.0469        = 0.0302
S_B12 = 0.001915 × 0.0302 × 1.0 = 0.000058
```

静态部分(全部来自扫掠):

| 因子 | 怎么量 | 本例 |
|---|---|---|
| `f_g0` | `g₀` = q₀ 处活动连杆几何 × 父连杆几何的**最小**距离(负=穿透),`exp(−\|g₀\|/(0.02·L_j))` | 0.862 |
| `f_g_drift` | 该最小间隙在 32 步中的最大变化量,`exp(−g_drift/(0.05·L_j))` | 0.926 |
| `f_anchor` | `mj_geomDistance` 的 `fromto` 给出最近接近线段,取中点作"接口几何中心",算到关节世界锚点距离 | **0.0024** |
| `s_clearance` | 活动连杆到**第三方**几何的最小净空 / `(0.02·L_j)`,截到 [0,1] | 1.0 |

动态部分(2 秒静置段):

| 因子 | 怎么量 | 本例 |
|---|---|---|
| `f_d_gravity` | 静置段所有非世界 body 的最大位移,`exp(−d/(0.01·D))` | 1.0 |
| `f_e_constraint` | 静置+保持段 MuJoCo `efc_pos` 绝对值最大值,`exp(−e/(0.005·D))` | 0.644 |
| `f_theta` | 各 body 相对初始朝向的最大转角,3° 免罚,`exp(−max(0,θ−3)/5)` | 0.047 |

**硬规则**:`S_interface` 与 `S_gravity` 相乘,所以**仿真跑得再好也补不回接口失败**。

### B13 运动干涉与动态阻塞

```
S_B13 = S_sweep · S_contact · S_stall · S_dyn = 1.0 × 1.0 × 0.9819 × 0.7892 = 0.775
```

| 因子 | 怎么量 | 本例 |
|---|---|---|
| `S_sweep` | `0.5·exp(−P_j/(0.002·D)) + 0.5·R_j`,`P_j` 是**新增**穿透(相对 q₀ 基线) | 1.0 |
| `S_contact` | 驱动+保持段对每个接触调 `mj_contactForce` 取法向力×dt 累加,排除契约白名单**和静置末已存在的接触**(自重支撑不算非预期) | 1.0 |
| `S_stall` | 驱动段速度低于额定 5% 的累计时长,`1 − t_stall/t_act` | 0.982 |
| `S_dyn` | 驱动+保持段接触穿透深度最大值,`exp(−p_dyn/(0.002·D))` | 0.789 |

B13=0.775 判 `abstain` 而非 `pass`:离阈值 0.70 只有 0.075,置信度 0.375 < 0.5。
**证据不够强时宁可弃权。**

### B14 多部件机构耦合

契约里 `coupling=[]` 且 `closed_loop=[]` → `not-applicable`,不进聚合分母。

---

## 4. 实现中做的关键判断

规范未闭合处,一律"取一个可辩护的默认 + 标 PROVISIONAL + 写进
`provisional_params` + 记入 QUESTIONS.md",不擅自放宽阈值。以下几条影响较大:

**① 工具故障绝不伪装成 0 分(铁律 3)。** `max(0.0, nan) == 0.0` 会让
`exp_decay(nan)` 算出 **1.0**(假通过),`exp(−inf)` 算出 **0.0**(假失败)。
四条指标进公式前统一拦 NaN/inf,`exp_decay`/`clip01` 改为抛 `ToolFailure`,
由 `@guards` 装饰器兜底。

**② 部分覆盖不得判 PASS。** 缺失因子实际被当成 1.0,所以 partial 下的分数是
完整分数的**上界**:上界 < τ 时 FAIL 可证,上界 ≥ τ 时改判 ABSTAIN。
此前"只跑几何扫掠、没碰仿真器"的资产能拿到 PASS。

**③ 执行器增益按关节有效惯量定,不给绝对值。**

```
kp = M_jj · ω²      kv = 2ζω · M_jj      ω = 20 rad/s
```

绝对增益会在跨尺度资产上发散——实测 0.043 kg 的琴键配 `kv=50` 时
`m/kv = 0.86 ms << dt = 4.17 ms`,显式积分必然炸(第一版 `impulse = 4.6e12 N·s`)。

**④ 总质量从 URDF 原文取。** MuJoCo 丢弃焊到世界的 body 质量,对固定底座资产
那几乎是全部质量。实测 air_purifier 会从 12.6 kg 缩到 2.4 kg,`mgT` 基准差 5 倍。

**⑤ 证据用 geom 名而非 body 名。** 焊到世界的零件 body 名全变成 `world`,
只报 body 名会让"撞上侧板"变成"撞上 world",违反铁律 6。

**⑥ 非目标关节全程 PD 保持。** 放任自由时 42 键的键盘在重力下整体崩塌,
测到的是自由摆动(rmse 2.64 rad)而非目标关节。

**⑦ `distmax` 陷阱。** `mj_geomDistance` 超量程时返回 `distmax` 本身而非哨兵值,
当测量值用会把"隔了 2 米"记成"隔了 1 米"、静默高估分数。每处查询都判
`dist >= distmax` 并标记截断。

---

## 5. 校准:219 条人工标注对照

### 数据集

人工标注 569 条,最后四个维度与 B11–B14 一一对应。按来源分层后取
**219 条**(新版原始标注 且 不需人工复核):

```
B12   不满足=92   满足=126      42% 正例, 类别均衡, 主要分析对象
B13   不满足=41   满足=177
B11   不满足=12   满足=206      正例太少
B14   不满足= 3   满足=86       无法评估
```

### 流水线执行

| | |
|---|---|
| 重编(`articraft compile --target full`) | **219/219 成功**,7.8 分钟 |
| 跑验证器 | **219/219 成功**,905 个关节 |
| 确定性验证 | 重编一条已有产物的记录,`model.urdf` 与两个 `.obj` **字节完全一致** |

### 结果

| | 不满足 | 满足 | AUC(0.5=随机) | τ=0.70 平衡准确率 | 最优 τ |
|---|---|---|---|---|---|
| B11 | 11 | 186 | 0.566 | 0.503 | 0.624 |
| B12 | 92 | 126 | **0.490** | 0.508 | 0.527 |
| B13 | 41 | 177 | 0.552 | 0.575 | 0.607 |
| B14 | 3 | 86 | 未评估 | — | — |

资产级分数分布:

| | 有分数 | 中位数 | ≥0.70 | 恰好=0 |
|---|---|---|---|---|
| B11 | 198 | 1.96e-06 | 1 | 1 |
| B12 | 219 | **0** | 2 | **142** |
| B13 | 219 | 0.00106 | 37 | 3 |
| B14 | 0 | — | — | — |

905 个关节的失败原因排序:

```
B11   轨迹跟踪误差过大 ×361   几何可达行程不足 ×191   delta_q<=0 ×75
B12   接口几何不成立 ×333     接口局部净空不足 ×309   重力漂移 ×122
B13   动态穿透超限 ×208       扫掠穿透或受阻 ×196     停滞 ×91
```

### 逐层排除

| 假设 | 检验 | 结论 |
|---|---|---|
| 阈值没校准 | 扫描全部候选 τ | 否,B12 最优只到 0.527 |
| 公式毁掉信号 | 直接看原始测量 | 否,`g0`/`g_drift`/`d_anchor`/`r_geom` 全部 AUC 0.44–0.52 |
| 估计量不敏感 | 保留每个几何到最近邻的完整分布,试 max/中位/超阈比例 | 否,最强仅 \|信号\| 0.089 **且方向相反** |
| 人在判"悬浮/脱离" | 同上 | 否,失败组几何**贴得更紧** |
| 标签只是质量代理 | 对照 5 星评分 | 否,AUC 0.506;92 个失败案例里 88 个仍是 5 星 |

### 一个容易被埋没的正面发现

不是"完全没信号",而是**高分端可信、中段分不开**:

- B13 分数前十名,**10/10 人工都判满足**
- B12 前五名,**5/5 人工都判满足**
- 但 B12 有 142/219 分数**精确等于 0**,三分之二是平局,AUC 自然退化

验证器"说好"的时候是对的,问题是它几乎给不出高分(B12 只有 2/219 过线)。

### 人的 B12 判断实际绑定在什么上

B12=不满足 与其他标注维度的共现:

| 维度 | B12不满足组 | B12满足组 | 提升 |
|---|---|---|---|
| **初始状态是否不存在非预期穿插、悬浮或脱离** | 42.4% | 11.1% | **+31.3pp** |
| 运动过程中是否不存在非预期穿模或几何干涉 | 27.2% | 12.7% | +14.5pp |
| 必要结构是否完整 | 19.6% | 6.3% | +13.2pp |

### 唯一有信号的方向

假设:人看的是**关节处有没有专门的连接硬件**(轴筒、销、支架),不是间隙大小。

| 特征 | AUC | \|信号\| | 不满足中位 | 满足中位 |
|---|---|---|---|---|
| `small_near_50`(关节轴 0.5·L_j 邻域内的小几何数) | 0.356 | **0.144** | **2** | **5.25** |
| `near_total_10` | 0.365 | 0.135 | 6 | 8 |
| `ngeom`(全资产几何数) | 0.398 | 0.102 | 25.5 | 32 |

前 18 名全是同一族(关节邻域几何计数),方向一致——不是单个特征碰巧。
但 0.144 仍太弱,单独做不了分类器。

---

## 6. 需要负责人决策的三件事

### ① `S_clearance` 必须重定义或删除

规范只在 B12 公式里出现过这个符号,**从未定义**。当前任何"到第三方几何的净空"
式定义在装配体里都会归零,而它是乘性因子——905 个关节里 **309 次**失败原因就是
它,它一个人清零了三分之二的 B12 分数。

**倾向**:改成非乘性的诊断项,或直接删除。

### ② 指标覆盖与真实失败分布严重错配

219 条里的失败计数:

```
活动零件是否具有可信的实体连接或支撑结构    92   ← B12
初始状态是否不存在非预期穿插、悬浮或脱离    53   ← 无任何指标覆盖
运动过程中是否不存在非预期穿模或几何干涉    41   ← B13
必要结构是否完整                        26   ← 无指标覆盖
运动学关节的运动范围是否合理              12   ← B11
多部件机构的连接与运动关系是否合理          3   ← B14
```

B11 + B14 合计只对应 15 条失败,却占这四条指标的一半;第二大失败模式零覆盖。

**倾向**:把 B14 的资源转到"初始状态装配正确性"。

### ③ "连接硬件"算 B12 的新因子还是新指标

唯一有信号的方向不在规范的七个乘性因子里。

**倾向**:先做成 B12 的一个新因子试水,而不是新指标。

---

## 7. 已知局限

不说出来会显得结论比实际更硬:

1. **契约是从资产自身合成的**(关节限位 → `expected_range`,每个已声明关节 →
   一个 `expected_interface`),不是从 prompt 解析的。所以"该有的关节根本没声明"
   这类失败,验证器**结构上看不见**。这可能压低了全部四条指标——但它解释不了
   B12 在**已声明关节**上也毫无判别力。**这是最重的一条。**
2. **B14 一条都没真正评估** — 合成契约没有 `coupling`/`closed_loop`,89 条全部
   返回 N/A。表里 B14 的空白是方法学缺口,不是关于 B14 的结论。
3. **48% 的关节只拿到几何证据** — 动态试验每资产上限 3 个,392 个关节被截断。
4. **B11 的头号失败原因"轨迹跟踪误差过大"出现 361 次,是 PROVISIONAL 的 PD 增益
   和梯形轨迹造成的**,不是资产问题。这正是 QUESTIONS.md 第 1 条的直接后果。
5. **MuJoCo 对 mesh 碰撞体做凸包化**,空心资产穿透量系统性失真(实测面包机
   `p_dyn=0.138m`)。影响 `P_j` 与 `p_dyn`。
6. **75 个关节因 `delta_q<=0` 判 tool-failure** — 那是 `jnt_limited=False` 的连续
   关节,B11 应该用 2π 而非 0,是个待补的口子。
7. 219 条基本一类目一条,无法评估类目效应;人工标注未做双标注一致性检验。

---

## 8. 复现

```bash
pip install -e .[sim]     # mujoco>=3.2, mj_geomDistance 在 3.1.5 里还没有
pytest -q                 # 113 passed
```

校准流程见 `calibration/README.md`,脚本按 `00a → 08` 顺序编号,保持了当时的原样
(含硬编码绝对路径,换机器需改每个文件顶部的常量)。

产物:

```
calibration/results/compile_results.jsonl        219 条编译状态
calibration/results/verifier_results.jsonl       逐关节打分与 sub_scores
calibration/results/attach_probe.jsonl           静止姿态的距离分布
calibration/results/per_asset_comparison.csv     219 行逐资产人机对照
```

**注意**:重编会覆盖 `articraft-data/cache/record_materialization/` 下的条目
(本次把 112 条 `visual` 缓存改成了 `full`)。运行前请先备份该目录(56 MB)。

---

## 9. 核心代码

以下是四条打分函数的全文,以及支撑它们的数值守卫。完整代码见仓库。

### 9.1 常量:唯一可调处

`consts.py` 分两区。FROZEN 是 PRO-12 §06 已冻结、不得修改的:

```python
DT = 1.0 / 240.0
SETTLE_S = 2.0
ACTUATE_S = 3.0
HOLD_S = 1.0
SWEEP_STEPS = 32
TRIALS = (1.0, 0.8, 1.2)
TRIAL_AGGREGATION = "min"
GRAVITY = 9.81
PHYSICS_QUALITY = {"asset": 1.0, "inferred": 0.8, "default": 0.6}
```

PROVISIONAL 是规范未闭合、取了占位值的。每个被用到时会写进
`MetricResult.provisional_params`,使任何一份结果都能看出它依赖哪些未定参数。
当前共 23 项,其中与本次结论直接相关的:

```python
b12_g0_scale: float = 0.02              # g0 / (scale * L_j)
b12_anchor_scale: float = 0.05          # d_anchor / (scale * D)
clearance_scale: float = 0.02           # S_clearance 的归一化尺度  ← 决策点 ①
b12_g0_penetration_mode: str = "abs"    # g0<0 按深度同等计罚
mj_actuator_omega: float = 20.0         # kp = M_jj*omega^2         ← 局限 4
mj_solref = (0.02, 1.0)                 # MuJoCo 软接触, 恒定 0.1078mm 引擎底噪
sweep_block_penetration_frac = 0.001    # 新增穿透超 frac*D 判阻塞
other_joints_policy: str = "hold"       # 非目标关节保持初始位姿
```

### 9.2 数值守卫(`metrics/_common.py` 节选)

```python
def exp_decay(value: float, scale: float) -> float:
    """exp(-value/scale), 对负 value 截断到 0 (不奖励"超好")。

    value 非有限时抛 ToolFailure。直接算的话:
      max(0.0, nan) == 0.0 -> exp(0) == 1.0  假通过
      exp(-inf/scale)      == 0.0            假失败
    两者都违反铁律 3 "工具故障 != 资产失败"。
    """
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("scale must be a positive finite number")
    if not math.isfinite(value):
        raise ToolFailure(f"exp_decay 收到非有限值 {value!r}")
    return math.exp(-max(0.0, value) / scale)


def non_finite(signals: dict, keys: Iterable[str]) -> list[str]:
    """返回存在但不是有限实数的键 (NaN / ±inf / 非数值)。

    仿真器发散往往不设 solver_failed, 而是直接吐 NaN/inf。缺失 (None) 不算,
    由 require() 分开处理 —— 缺证据是覆盖不全, 不是故障。
    """
    bad = []
    for k in keys:
        v = signals.get(k)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            bad.append(k)
            continue
        if not math.isfinite(f):
            bad.append(k)
    return bad
```

判定逻辑(部分覆盖不得判 PASS):

```python
    # 部分覆盖下缺失的因子实际被当成 1.0, 所以分数只是完整分数的上界:
    #   上界 <  tau -> 完整分数必然 < tau, FAIL 可证
    #   上界 >= tau -> 完整分数未知, 不能凭不完整证据判 PASS
    upper_bound_only = coverage is Coverage.PARTIAL

    if confidence < consts.abstain_below:
        prediction = Prediction.ABSTAIN
    elif score >= tau:
        prediction = Prediction.ABSTAIN if upper_bound_only else Prediction.PASS
    else:
        prediction = Prediction.FAIL
```

### 9.3 B11 可用关节运动范围

```python
METRIC = "B11"
_STATIC_KEYS = ("r_geom",)
_DYNAMIC_KEYS = ("q_start", "q_target", "q_end", "delta_q", "rmse", "overshoot")
_NUMERIC_KEYS = _STATIC_KEYS + _DYNAMIC_KEYS


@C.guards(METRIC)
def score(signals: dict, contract: dict, consts: Consts) -> MetricResult:
    if not contract.get("expected_range"):
        return C.not_applicable(METRIC, consts, "契约中没有预期活动范围")

    if signals.get("solver_failed"):
        return C.tool_failure(METRIC, consts, "仿真器求解失败",
                              solver_status=signals.get("solver_status"))

    bad = C.non_finite(signals, _NUMERIC_KEYS)
    if bad:
        return C.tool_failure(METRIC, consts, "信号含 NaN/inf, 疑似仿真发散",
                              non_finite=bad)

    missing_static = C.require(signals, _STATIC_KEYS)
    if missing_static:
        return C.tool_failure(METRIC, consts, "缺少几何扫掠证据", missing=missing_static)

    r_geom = C.clip01(float(signals["r_geom"]))
    provenance = signals.get("physics_provenance", "default")
    missing_dyn = C.require(signals, _DYNAMIC_KEYS)
    has_dynamic = not missing_dyn
    provisional = ["QREF_PROFILE", "SWEEP_SUBDIV"]

    if not has_dynamic:
        # 仅几何 -> 部分覆盖。分数只保留 R_geom, 不用 1.0 补齐缺失因子。
        return C.build_result(
            METRIC, r_geom, Coverage.PARTIAL, consts,
            physics_provenance=provenance, tools=["sweep"],
            raw_measurements={"r_geom": r_geom}, sub_scores={"R_geom": r_geom},
            evidence=_evidence(signals, missing=missing_dyn),
            failure_reason=None if r_geom >= consts.tau_b11 else "几何可达行程不足",
            repair_hint="清理运动走廊、调整合理范围或补充足够执行器",
            provisional_params=provisional, n_factors=1,
        )

    dq = float(signals["delta_q"])
    if dq <= 0:
        return C.tool_failure(METRIC, consts, "delta_q <= 0, 关节行程无效", delta_q=dq)

    q_start = float(signals["q_start"])
    q_target = float(signals["q_target"])
    q_end = float(signals["q_end"])
    target_travel = abs(q_target - q_start)
    if target_travel <= 0:
        return C.tool_failure(METRIC, consts, "目标行程为 0",
                              q_start=q_start, q_target=q_target)

    completion = C.clip01(abs(q_end - q_start) / target_travel)
    rmse = float(signals["rmse"])
    overshoot = float(signals["overshoot"])
    tracking = C.exp_decay(rmse, consts.b11_rmse_scale * dq)
    limit = C.exp_decay(overshoot, consts.b11_overshoot_scale * dq)

    s = r_geom * completion * tracking * limit

    provisional += ["QREF_ACCEL_FRAC", "QREF_DURATION_S", "ACTUATOR_MODE",
                    "ACTUATOR_MAX_FORCE", "ACTUATOR_KP", "ACTUATOR_KD"]

    return C.build_result(
        METRIC, s, C.coverage_for_physics(provenance, True), consts,
        physics_provenance=provenance, tools=["sweep", "simulator"],
        raw_measurements={
            "r_geom": r_geom, "q_start": q_start, "q_target": q_target,
            "q_end": q_end, "delta_q": dq, "rmse": rmse, "overshoot": overshoot,
            "rmse_norm": rmse / dq, "overshoot_norm": overshoot / dq,
        },
        sub_scores={"R_geom": r_geom, "C": completion, "T": tracking, "L": limit},
        evidence=_evidence(signals),
        failure_reason=_reason(r_geom, completion, tracking, limit, consts),
        repair_hint="清理运动走廊、调整合理范围或补充足够执行器",
        provisional_params=provisional, n_factors=4,
    )
```

### 9.4 B12 实体接口与物理支撑

```python
METRIC = "B12"
_INTERFACE_KEYS = ("g0", "g_drift", "l_j", "d_anchor", "d_bbox", "s_clearance")
_GRAVITY_KEYS = ("d_gravity", "e_constraint", "theta_drift_deg")
_NUMERIC_KEYS = _INTERFACE_KEYS + _GRAVITY_KEYS + ("s_payload",)


@C.guards(METRIC)
def score(signals: dict, contract: dict, consts: Consts) -> MetricResult:
    if not contract.get("expected_interfaces") and not contract.get("mounting"):
        return C.not_applicable(METRIC, consts, "契约中没有接口或安装要求")

    if signals.get("solver_failed"):
        return C.tool_failure(METRIC, consts, "仿真器求解失败",
                              solver_status=signals.get("solver_status"))

    bad = C.non_finite(signals, _NUMERIC_KEYS)
    if bad:
        return C.tool_failure(METRIC, consts, "信号含 NaN/inf, 疑似仿真发散",
                              non_finite=bad)

    missing_if = C.require(signals, _INTERFACE_KEYS)
    if missing_if:
        return C.tool_failure(METRIC, consts, "缺少接口几何证据", missing=missing_if)

    l_j = float(signals["l_j"])
    d_bbox = float(signals["d_bbox"])
    if l_j <= 0 or d_bbox <= 0:
        return C.tool_failure(METRIC, consts, "归一化尺度无效", l_j=l_j, d_bbox=d_bbox)

    g0_raw = float(signals["g0"])
    g0 = _effective_gap(g0_raw, consts)          # g0<0 是穿透, 按深度同等计罚
    g_drift = float(signals["g_drift"])
    d_anchor = float(signals["d_anchor"])
    s_clear = C.clip01(float(signals["s_clearance"]))

    f_g0 = C.exp_decay(g0, consts.b12_g0_scale * l_j)
    f_gd = C.exp_decay(g_drift, consts.b12_gdrift_scale * l_j)
    f_anchor = C.exp_decay(d_anchor, consts.b12_anchor_scale * d_bbox)
    s_interface = f_g0 * f_gd * f_anchor * s_clear

    provenance = signals.get("physics_provenance", "default")
    missing_grav = C.require(signals, _GRAVITY_KEYS)

    if missing_grav:
        # 只有静态接口证据 -> 部分覆盖。不用 1.0 补齐重力项。
        return C.build_result(METRIC, s_interface, Coverage.PARTIAL, consts, ...)

    d_g = float(signals["d_gravity"])
    e_c = float(signals["e_constraint"])
    theta = float(signals["theta_drift_deg"])

    f_dg = C.exp_decay(d_g, consts.b12_gravity_drift_scale * d_bbox)
    f_ec = C.exp_decay(e_c, consts.b12_constraint_scale * d_bbox)
    f_theta = C.exp_decay(max(0.0, theta - consts.b12_theta_allow_deg),
                          consts.b12_theta_scale_deg)
    s_gravity = f_dg * f_ec * f_theta

    raw_payload = signals.get("s_payload")
    has_payload = bool(contract.get("payload"))
    payload_missing = has_payload and raw_payload is None
    # 契约没声明载荷 -> 该因子不适用, 取 1.0。
    # 声明了却没证据 -> 也只能取 1.0, 但那是把缺失因子当满分, 分数因此只是
    # 上界: 降级 partial 并记进 evidence, 由 build_result 禁掉 PASS。
    s_payload = 1.0 if payload_missing or not has_payload else C.clip01(float(raw_payload))

    s = s_interface * s_gravity * s_payload

    n_factors = 8 if (has_payload and not payload_missing) else 7
    coverage = (Coverage.PARTIAL if payload_missing
                else C.coverage_for_physics(provenance, True))
    return C.build_result(METRIC, s, coverage, consts, ...)


def _effective_gap(g0: float, consts: Consts) -> float:
    """g0 < 0 表示接口处零件互相嵌入 (距离查询对穿透返回负距离)。

    规范只把 g0 定义成"间隙", 而 exp_decay 又把负值截到 0, 于是穿透
    (比缝隙过大更严重的装配缺陷) 会拿到满分因子。默认按深度同等计罚。
    """
    mode = consts.b12_g0_penetration_mode
    if mode == "abs":
        return abs(g0)
    if mode == "clip":
        return g0
    raise ValueError(f"未知的 b12_g0_penetration_mode: {mode!r}")
```

### 9.5 B13 运动干涉与动态阻塞

```python
    p_j = float(signals["penetration_max"])
    r_j = C.clip01(float(signals["r_j"]))
    f_pen = C.exp_decay(p_j, consts.b13_penetration_scale * d_bbox)
    s_sweep = (consts.b13_sweep_penetration_weight * f_pen
               + consts.b13_sweep_reach_weight * r_j)

    total_mass = float(signals["total_mass"])
    # 归一化基准只认 consts (铁律 2)。ACTUATE_S 是 §06 冻结量, 让 signals
    # 覆盖它等于把 S_stall 和 mgT 的分母交给信号生产方 —— 实测把 t_act
    # 从 3.0 改成 100 能让 B13 从 0.0117 变 0.0816。
    t_act = float(consts.t_act_definition)
    if total_mass <= 0 or t_act <= 0:
        return C.tool_failure(METRIC, consts, "冲量归一化基准无效",
                              total_mass=total_mass, t_act=t_act)

    # 仿真器报了不一样的驱动段时长 = 没按 §06 协议跑, 结果不可比。
    # 不静默采用, 也不静默丢弃, 写进 diagnostics 让问题可见。
    reported_t_act = signals.get("t_act")
    protocol_deviation = (
        None if reported_t_act is None or abs(float(reported_t_act) - t_act) < 1e-9
        else {"t_act_reported": float(reported_t_act), "t_act_used": t_act})

    mgt = total_mass * GRAVITY * t_act
    s_contact = C.exp_decay(float(signals["impulse_unexpected"]),
                            consts.b13_impulse_scale * mgt)
    s_stall = C.clip01(1.0 - float(signals["t_stall"]) / t_act)
    s_dyn = C.exp_decay(float(signals["p_dyn"]),
                        consts.b13_dyn_penetration_scale * d_bbox)

    s = s_sweep * s_contact * s_stall * s_dyn
```

### 9.6 B14 多部件机构耦合

"适用项"是关键:只有契约里声明了的耦合/比例/闭环才进乘积。

```python
    factors: dict[str, float] = {}
    dropped: list[str] = []       # 契约声明了、却没有证据可算的项

    if has_coupling:
        if signals.get("sync_rmse_norm") is not None:
            factors["S_sync"] = C.exp_decay(float(signals["sync_rmse_norm"]),
                                            consts.b14_sync_scale)
        else:
            dropped.append("S_sync")

    if has_coupling:
        if signals.get("r_obs") is not None and signals.get("r_exp") is not None:
            r_obs, r_exp = float(signals["r_obs"]), float(signals["r_exp"])
            factors["S_ratio"] = C.exp_decay(abs(r_obs - r_exp), consts.b14_ratio_scale)
        else:
            dropped.append("S_ratio")

    # 这里必须用 is not None: d_bbox = 0.0 是假值, 用真值判断会短路掉下面的
    # 合法性检查, 让 S_loop 被静默丢弃 —— 实测那条路径下 score 变成 1.0。
    if has_loop:
        e_loop_raw, d_bbox_raw = signals.get("e_loop"), signals.get("d_bbox")
        if e_loop_raw is not None and d_bbox_raw is not None:
            e_loop, d_bbox = float(e_loop_raw), float(d_bbox_raw)
            if d_bbox <= 0:
                return C.tool_failure(METRIC, consts, "包围盒对角线无效", d_bbox=d_bbox)
            factors["S_loop"] = C.exp_decay(e_loop / d_bbox, consts.b14_loop_scale)
        else:
            dropped.append("S_loop")

    s = 1.0
    for v in factors.values():
        s *= v

    # 声明了却算不出的项等于被当成 1.0, 分数只是上界 -> partial。
    coverage = (Coverage.PARTIAL if dropped
                else C.coverage_for_physics(provenance, has_dynamic))
```

### 9.7 扫掠核心(`primitives/sweep.py` 节选)

用 `mj_geomDistance` 而非接触列表:纯几何查询,不受 contype 与父子过滤影响,
同一姿态给同一个数,满足 §06 的可复现要求。

```python
def _distance(model, data, g1: int, g2: int, distmax: float):
    """返回 (距离, fromto) 或 (_TRUNCATED, None)。截断绝不当测量值。"""
    fromto = np.zeros(6, dtype=np.float64)
    dist = mujoco.mj_geomDistance(model, data, int(g1), int(g2), float(distmax), fromto)
    if dist >= distmax:
        return _TRUNCATED, None
    return float(dist), fromto
```

### 9.8 动态试验核心(`sim/runner.py` 节选)

```python
def _pd_gains(m, d, dof: int, consts) -> tuple[float, float, float]:
    """按关节有效惯量定 PD 增益, 使闭环带宽与阻尼比在所有资产上一致。

        kp = M_jj * omega^2      kv = 2 * zeta * omega * M_jj

    M_jj 取质量矩阵对角元 —— 一个 0.043kg 的琴键和一个 21kg 的靠背拿到的是
    同一个 omega, 而不是同一个 kp。绝对增益会让前者数值发散。
    """
    dense = _full_mass_matrix(m, d)
    m_jj = float(dense[dof, dof])
    if not np.isfinite(m_jj) or m_jj <= 0.0:
        raise ToolFailure(f"关节有效惯量无效: M[{dof},{dof}]={m_jj!r}")
    # 退化自由度: 有效惯量比模型里最大的小若干量级时, 任何接触力都能主导它,
    # 结果测的是数值噪声而非资产。实测键盘旋钮 M_jj=3.8e-07 就是这种。
    biggest = float(np.max(np.diag(dense)))
    if biggest > 0 and m_jj / biggest < consts.min_joint_inertia_ratio:
        raise ToolFailure(f"关节有效惯量退化: M_jj={m_jj:.3g}, 动力学结果不可信")
    w, z = consts.mj_actuator_omega, consts.mj_actuator_zeta
    return m_jj * w * w, 2.0 * z * w * m_jj, m_jj
```

三次鲁棒性试验只扰动推断/默认参数(§06 原文):

```python
def _perturb(loaded: LoadedModel, scale: float, consts: Consts) -> dict:
    """按试验缩放推断/默认参数。返回这次实际动了什么, 供 evidence 追溯。"""
    m = loaded.model
    touched = {"scale": scale}

    if loaded.provenance != "asset":
        m.body_mass[:] = m.body_mass * scale
        m.body_inertia[:] = m.body_inertia * scale
        touched["mass"] = True
    else:
        touched["mass"] = False        # 资产自带惯量, 不篡改

    m.geom_friction[:] = m.geom_friction * scale
    touched["friction"] = True

    if float(np.max(np.abs(m.dof_damping))) <= 0.0:
        m.dof_damping[:] = consts.mj_default_joint_damping * scale
        touched["damping"] = "default"
    else:
        touched["damping"] = "asset"   # 资产声明了 <dynamics damping>, 不动
    return touched
```

---

## 10. 群里可以直接发的一段

> **B11–B14 验证器进展 + 一个需要大家拍板的结果**
>
> 四条指标的实现完成了,MuJoCo 后端也接通了。113 项单测通过,PRO-12 §08 的柜子
> 案例四个数字精确复现。在 219 个真实 ArtiCraft 资产上跑通,零失败。
>
> 但我们把它拿去和 219 条人工标注对照,**结果是负面的**:四条指标的判别力约等于
> 随机(AUC 0.49–0.57),B12 在 τ=0.70 下把 218 个资产判了 216 个"不满足",
> 基本是常数输出。
>
> 我们逐层排除了四种解释:不是阈值没校准(最优 τ 也只到 0.527);不是公式写错
> (绕开公式看原始测量,AUC 还是 0.44–0.52);不是估计量不够敏感(换了一整族
> 更贴"悬浮/脱离"的估计量,最强信号 0.089 而且方向相反);也不是标注本身没意义
> (B12 标签和 5 星评分 AUC 0.506,92 个失败案例里 88 个仍是 5 星)。
>
> 一个容易被埋没的正面发现:**高分端是可信的**——B13 分数前十名 10/10 人工都判
> 满足,B12 前五名 5/5 都判满足。问题是它几乎给不出高分,B12 有 142/219 分数精确
> 等于 0,三分之二是平局,AUC 自然就退化了。
>
> 三件事需要拍板:
> 1. **`S_clearance` 要重定义或删掉**。规范只在 B12 公式里出现过这个符号从未定义,
>    而任何"到第三方几何净空"式的定义在装配体里都会归零,它又是乘性因子——
>    905 个关节里 309 次失败原因就是它,一个人清零了 2/3 的 B12 分数。
> 2. **指标覆盖和真实失败分布对不上**。219 条里失败最多的是 B12(92)和"初始状态
>    穿插/悬浮/脱离"(53),而后者没有任何指标覆盖;B11+B14 合计只对应 15 条失败,
>    却占了四条指标的一半。
> 3. **人判的"可信实体连接"可能不是几何间隙能表达的**。唯一有信号的方向是
>    "关节附近有没有专门的连接硬件"——失败资产关节轴附近小几何中位数 2 个,
>    通过的 5.25 个。这个量不在规范的七个乘性因子里。
>
> 需要说明的局限:契约目前是从资产自身合成的、不是从 prompt 解析的,所以"该有的
> 关节根本没声明"这类失败验证器结构上看不见;B14 因为合成契约没有 coupling/
> closed_loop,89 条全部 N/A,等于没评估;另外 B11 最主要的失败原因"轨迹跟踪
> 误差过大"(361 次)是我们自己选的 PD 增益造成的,不是资产问题。
>
> 我的建议是先别调参——AUC 0.49 不是调参能救的,而且现在这批数据的说服力正好
> 用来推动规范层面的讨论。完整证据链和复现材料在 `calibration/README.md`,
> 逐资产人机对照表在 `calibration/results/per_asset_comparison.csv`(219 行)。
