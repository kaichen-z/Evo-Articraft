# ArtiCraft Verifier — B11–B14

## 项目范围

实现 PRO-12 自动验证器中 **B11–B14** 四项指标的精确计算。
A1–A6、B7–B10 由他人负责,**不要实现,不要修改**。

- B11 可用关节运动范围
- B12 实体接口与物理支撑
- B13 运动干涉与动态阻塞
- B14 多部件机构耦合

## 铁律

1. **metrics/ 下的打分函数是纯函数**,签名固定:
   `score(signals: dict, contract: dict, consts: Consts) -> MetricResult`
   不读文件、不启仿真器、不调网络、不用全局状态。
2. **所有魔法数字必须来自 `consts.py`**,禁止硬编码在公式里。
3. **工具故障 ≠ 资产失败**。仿真器 NaN / 发散 / 超时 / 加载失败 →
   `MetricResult(score=None, coverage="tool-failure")`,绝不返回 0.0。
4. **coverage 必须与 score 同时返回**,取值只能是:
   `full` / `estimated-physics` / `partial` / `unsupported` / `not-applicable`
5. **不适用时返回 `not-applicable`,score=None**,不补 0,不进聚合分母。
6. **每个失败判定必须可回溯**到具体连杆对 / 关节 / 姿态索引 / 时间步,
   写进 `MetricResult.evidence`。
7. **不调用任何 LLM API**。契约是输入的 JSON,不在运行时生成。

## 符号表

| 符号 | 含义 |
|---|---|
| `D` | 完整物体包围盒对角线(米)。全局长度量除以它 |
| `L_j` | 关节 j 的活动连杆包围盒对角线。局部间隙除以它 |
| `Δq_j` | `|q_max − q_min|`,关节 j 的行程 |
| `R_geom` | 32 步扫掠中无阻塞可达的行程比例 ∈ [0,1] |
| `P_j` | 扫掠中最大新增穿透深度(米),归一化用 `P_j/D` |
| `p_dyn` | 动态试验中最大穿透深度(米) |
| `I_unexpected` | 非白名单接触的累计冲量(N·s) |
| `t_stall` | 停滞总时长(秒) |
| `t_act` | 驱动阶段时长 = 3.0 s |
| `mgT` | 冲量归一化基准 = 总质量 × 9.81 × `t_act` |
| `g₀` | 关节邻域 q₀ 处的最小接口间隙(米) |
| `g_drift` | 扫掠全程该间隙的最大变化量(米) |
| `d_anchor` | 关节原点到接口几何中心的距离(米) |
| `e_loop` | 闭环约束残差(米) |

## 冻结常量(consts.py)

以下已由 PRO-12 §06 冻结,**不得修改**:

```
DT = 1.0 / 240.0        # s
SETTLE_S = 2.0
ACTUATE_S = 3.0
HOLD_S = 1.0
SWEEP_STEPS = 32
TRIALS = (1.0, 0.8, 1.2)   # 只扰动推断/默认的质量、摩擦、阻尼
TRIAL_AGGREGATION = "min"  # 取三次试验最低分
TAU = 0.70                 # 全部四项
```

## 暂定决策(PROVISIONAL — 等负责人答复后改 consts.py)

规范未闭合,以下为占位值。**每一项在代码里标 `# PROVISIONAL`,
并在 JSON 输出的 `provisional_params` 字段里原样报告**,
这样任何一份结果都能看出它依赖哪些未定参数。

| 参数 | 暂定值 | 待确认 |
|---|---|---|
| `QREF_PROFILE` | `"trapezoid"` | 轨迹形状:斜坡 / 梯形 / min-jerk |
| `QREF_ACCEL_FRAC` | 0.2 | 梯形加减速段各占行程比例 |
| `QREF_DURATION_S` | 3.0 | 目标行程走完的时间 = 整个驱动段 |
| `ACTUATOR_MODE` | `"position"` | 位置控制 vs PD 力矩 |
| `ACTUATOR_MAX_FORCE` | 200.0 | N 或 N·m |
| `ACTUATOR_KP` / `KD` | 0.1 / 1.0 | PyBullet positionGain / velocityGain |
| `SWEEP_SUBDIV` | `True` | 32 步之间检出穿透时自适应细分,防薄板隧穿 |
| `R_J_DEF` | `"reachable_fraction"` | B13 中 R_j 的定义,暂取无阻塞步数比例 |
| `T_ACT_DEF` | 3.0 | 停滞归一化用驱动段时长 |
| `Q_TOOL` / `Q_CONTRACT` | 1.0 / 1.0 | 置信度乘子未定义,暂置 1 |

**已知风险(已上报,未解决)**:τ 统一 0.70 在指数乘积下实际严格度差一个量级。
B13 四因子 → 单项需 ≥ 0.915;B12 约六个指数项 → 单项需 ≈ 0.97,
即 `g₀ ≤ 0.0006·L_j`。叠加三次试验取最低分后 B12 近乎不可通过。
**不要私自放宽阈值**,按规范算,把等价单因子阈值一并输出到
`diagnostics.equivalent_factor_threshold`,让问题可见。

## 公式(照抄规范,不得改写)

```
B11: C = clip(|q_end − q_start| / |q_target − q_start|, 0, 1)
     T = exp(−RMSE / (0.05·Δq))
     L = exp(−overshoot / (0.02·Δq))
     S_B11 = R_geom · C · T · L

B12: S_interface = exp(−g₀/(0.02L)) · exp(−g_drift/(0.05L))
                   · exp(−d_anchor/(0.05D)) · S_clearance
     S_gravity   = exp(−d_g/(0.01D)) · exp(−e_c/(0.005D))
                   · exp(−max(0, θ−3)/5)
     S_B12 = S_interface · S_gravity · S_payload
     ※ 仿真通过不能补偿 S_interface 失败

B13: S_sweep   = 0.5·exp(−P_j/(0.002D)) + 0.5·R_j
     S_contact = exp(−I_unexpected/(0.10·mgT))
     S_stall   = 1 − t_stall/t_act
     S_dyn     = exp(−p_dyn/(0.002D))
     S_B13 = S_sweep · S_contact · S_stall · S_dyn

B14: S_sync  = exp(−RMSE_sync / 0.05)
     S_ratio = exp(−|r_obs − r_exp| / 0.10)
     S_loop  = exp(−(e_loop/D) / 0.005)
     S_time  = 1 − t_violation/t_total
     S_B14 = Π(适用项) · S_task
     ※ 无预期耦合/闭环 → not-applicable
```

## 覆盖程度判定

| 指标 | full | estimated-physics | partial |
|---|---|---|---|
| B11 | 资产自带执行器参数 + 完成动态试验 | 用默认执行器 | 只有几何扫掠 |
| B12 | 资产自带质量/惯量/摩擦 | 推断或默认物理参数 | 只有静态接口证据 |
| B13 | 同上 + 完整接触/停滞记录 | 同上 | 只有扫掠碰撞 |
| B14 | 完整多关节仿真 | 默认物理参数 | 只有静态耦合图 |

物理置信系数:资产参数 1.0 / 推断 0.8 / 默认 0.6。

## 输出契约

```json
{
  "score": 0.163,
  "prediction": "fail",
  "threshold": 0.70,
  "confidence": 0.88,
  "coverage": "estimated-physics",
  "tools": ["sweep", "simulator"],
  "raw_measurements": {"R_geom": 0.55, "C": 0.54, "RMSE_norm": 0.03},
  "sub_scores": {"R_geom": 0.55, "C": 0.54, "T": 0.549, "L": 1.0},
  "evidence": {"first_blocked_step": 18, "link_pair": ["drawer", "side_panel"]},
  "failure_reason": "抽屉在 55% 行程处被侧板阻挡",
  "repair_hint": "清理运动走廊或缩短有效范围",
  "provisional_params": ["QREF_PROFILE", "ACTUATOR_MAX_FORCE"]
}
```

## 目录结构

```
verifier/
  consts.py           # 所有常量,唯一可调处
  types.py            # MetricResult 等数据类
  contracts/          # 契约 schema + 样例 JSON
  primitives/         # fk.py sweep.py collision.py interface.py
  sim/                # protocol.py runner.py signals.py
  metrics/            # b11.py b12.py b13.py b14.py ← 纯函数
  report/             # 输出契约序列化
tests/
  fixtures/           # 极小 URDF + 手写 signals dict
```

## 开发顺序(周三前)

1. `types.py` + `consts.py` + 契约 schema
2. `metrics/b11–b14.py` + 全部单测(**用手写 signals dict,不跑仿真**)
3. `primitives/sweep.py`(PyBullet getClosestPoints)
4. `sim/runner.py` 按冻结协议展开 2s/3s/1s
5. 端到端接柜子案例

**第 2 步做完就已经可交付**:四条公式跑通、有输出、有失败证据。
仿真器接不完也不影响演示。

## 验收标准(用规范里的柜子案例)

抽屉在 55% 行程被侧板挡住:
- `S_B11 = 0.55 × 0.54 × 0.549 × 1.0 ≈ 0.163`
- `S_B12 = 0.00091 × 0.0247 × 1.0 ≈ 0.000022`
- `S_B13 = 0.387 × 0.247 × 0.55 × 0.223 ≈ 0.0117`
- `S_B14 = None, coverage = "not-applicable"`

单测必须复现这四个数(容差 1e-3)。

## 工作方式

- 每个 metric 先写 pytest 用例再写实现。
- 不要 `cat` URDF、不要打印完整轨迹数组。
  脚本读数据,只 print 摘要:极值、首次阻塞步、violation 区间。
- 机械性任务(样板、fixture、批量改测试)开 caveman;
  讨论公式与阈值时关掉。
- 改动 `consts.py` 里任何 PROVISIONAL 值前先问我。
