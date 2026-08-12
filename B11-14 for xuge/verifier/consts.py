"""所有魔法数字的唯一来源。公式里禁止硬编码。

两类:
  FROZEN     - PRO-12 §06 已冻结, 不得修改
  PROVISIONAL- 规范未闭合, 占位值。负责人答复后改这里, 公式一行不动。

每个 PROVISIONAL 参数被用到时会写进 MetricResult.provisional_params,
使任何一份结果都能看出它依赖哪些未定参数。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------- FROZEN
DT = 1.0 / 240.0
SETTLE_S = 2.0
ACTUATE_S = 3.0
HOLD_S = 1.0
SWEEP_STEPS = 32
TRIALS = (1.0, 0.8, 1.2)
TRIAL_AGGREGATION = "min"
GRAVITY = 9.81

# 输出契约 §09 里 TRIAL_AGGREGATION 的写法。改上面那个时同步改这里。
TRIAL_AGGREGATION_LABEL = "minimum_trial_score"

# 家族权重 (PRO-12 §07): semantic, static, motion, physics
FAMILY_WEIGHTS = {"semantic": 0.20, "static": 0.25, "motion": 0.30, "physics": 0.25}

# 物理参数来源 -> q_physics (PRO-12 §04)。铁律 2: 魔法数字只在 consts.py。
PHYSICS_QUALITY = {
    "asset": 1.0,
    "inferred": 0.8,
    "default": 0.6,
}


# ------------------------------------------------------- PROVISIONAL 清单
# 名字 -> 一句话说明。用于在结果里报告依赖了哪些未定参数。
PROVISIONAL_NOTES = {
    "QREF_PROFILE": "q_ref(t) 轨迹形状未冻结; 直接决定 B11 的 T 与 L",
    "QREF_ACCEL_FRAC": "梯形加减速段占比未冻结",
    "QREF_DURATION_S": "目标行程走完的时间未冻结",
    "ACTUATOR_MODE": "执行器控制模式未冻结",
    "ACTUATOR_MAX_FORCE": "执行器力/力矩上限未冻结",
    "ACTUATOR_KP": "位置增益未冻结; 换增益可让 B11 的 T 从 0.55 变 0.95",
    "ACTUATOR_KD": "速度增益未冻结",
    "SWEEP_SUBDIV": "32 步之间是否自适应细分未规定; 关系到薄板隧穿漏检",
    "R_J_DEF": "B13 的 R_j 规范未定义; 暂取无阻塞步数比例",
    "T_ACT_DEF": "B13 停滞归一化基准未定义; 暂取驱动段时长",
    "Q_TOOL": "置信度乘子 q_tool 规范未定义",
    "Q_CONTRACT": "置信度乘子 q_contract 规范未定义",
    "CONTACT_MODEL": "接触模型参数未冻结; B13 的 S_dyn 尺度是 0.002D, 对接触刚度极敏感",
    "G0_SIGN_CONVENTION": (
        "规范把 g0 定义成'间隙', 没定义负值。getClosestPoints 对穿透返回负距离, "
        "而 exp(-max(0,g0)/s) 会给互相嵌进去的零件满分。暂按深度同等计罚"
    ),
    "MJ_SOLREF": (
        "MuJoCo 软接触参数未冻结。实测默认值下一个完好方块静置也有 0.1078mm 穿透, "
        "对 B13 的 0.002D 尺度即 S_dyn=0.9475 —— 一个恒定的引擎底噪"
    ),
    "MJ_SOLIMP": "同 MJ_SOLREF; solimp 的 width 直接决定稳态穿透深度",
    "MJ_ACTUATOR_GAINS": (
        "MuJoCo <position> 执行器的 kp/kv 是真实刚度量纲, 与 consts 里 PyBullet "
        "语义的 ACTUATOR_KP/KD 不可通约。暂取一组能跟住梯形轨迹的值"
    ),
    "MJ_GEOM_DISTMAX": "mj_geomDistance 的量程上限未规定; 超出时它返回 distmax 本身",
    "MJ_DEFAULT_DENSITY": "无 <inertial> 时 MuJoCo 从 collision 几何推质量所用的密度",
    "SWEEP_BLOCK_THRESHOLD": (
        "扫掠中'算作阻塞'的新增穿透阈值未规定。取 D 的一个比例, 与 B13 的 "
        "0.002D 同量级但更严"
    ),
    "S_CLEARANCE_DEF": (
        "S_clearance 规范只出现在 B12 公式里, 从未定义。暂取: 活动连杆到第三方"
        "几何的最小净空, 按 clearance_scale*L_j 归一后截到 [0,1]"
    ),
    "MJ_DEFAULT_DAMPING": "资产未声明关节阻尼时的默认值; 三次试验扰动的就是它",
    "STALL_DEF": "t_stall 的判据未定义。暂取: 驱动段内关节速度低于额定速度的一个比例",
    "E_CONSTRAINT_DEF": (
        "e_c 出现在 B12 的 S_gravity 里但符号表未定义。暂取: 静置+保持阶段"
        "MuJoCo 约束违反量 efc_pos 的最大绝对值"
    ),
    "D_GRAVITY_DEF": (
        "d_g 同样未定义。暂取: 静置阶段所有非世界 body 的最大位置漂移"
    ),
    "OTHER_JOINTS_POLICY": (
        "协议只说驱动'目标关节', 没说其余关节怎么处理。放任自由会让多关节资产"
        "(如 42 键的键盘)在重力下整体崩塌, 测到的是自由摆动不是该关节。暂取: "
        "用同一套 PD 把其余关节保持在初始位姿"
    ),
    "EXPECTED_CONTACT_BASELINE": (
        "I_unexpected 的'非预期'只由契约白名单定义, 但静置后本就存在的自重支撑"
        "接触显然也是预期的 —— 不排除的话 36kg 资产静置 6s 的支撑冲量就有 "
        "2119 N·s, 而基准 0.10*mgT 只有 106, S_contact 恒为 0。暂取: 静置结束时"
        "已存在的 body 对并入白名单"
    ),
}


@dataclass(frozen=True)
class Consts:
    """一次评测使用的全部常量。metrics 只从这里取值。"""

    # --- 阈值 (PRO-12 §04, 默认 0.70, 校准集调整后冻结) ---
    tau_b11: float = 0.70
    tau_b12: float = 0.70
    tau_b13: float = 0.70
    tau_b14: float = 0.70

    # --- B11 尺度 ---
    b11_rmse_scale: float = 0.05       # RMSE / (scale * dq)
    b11_overshoot_scale: float = 0.02  # overshoot / (scale * dq)

    # --- B12 尺度 ---
    b12_g0_scale: float = 0.02         # g0 / (scale * L_j)
    b12_gdrift_scale: float = 0.05     # g_drift / (scale * L_j)
    b12_anchor_scale: float = 0.05     # d_anchor / (scale * D)
    b12_gravity_drift_scale: float = 0.01   # d_gravity / (scale * D)
    b12_constraint_scale: float = 0.005     # e_constraint / (scale * D)
    b12_theta_allow_deg: float = 3.0        # 免罚朝向漂移
    b12_theta_scale_deg: float = 5.0        # 超出部分的衰减尺度
    # g0 < 0 (零件互相嵌入) 怎么算。PROVISIONAL, 见 G0_SIGN_CONVENTION。
    #   "abs"  穿透深度按同等大小的间隙计罚
    #   "clip" 截到 0 不计罚 (规范字面行为, 会给穿透满分)
    b12_g0_penetration_mode: str = "abs"    # PROVISIONAL

    # --- B13 尺度 ---
    b13_penetration_scale: float = 0.002   # P_j / (scale * D)
    b13_impulse_scale: float = 0.10        # I / (scale * mgT)
    b13_dyn_penetration_scale: float = 0.002
    # S_sweep = w_pen * exp(-P_j/(scale*D)) + w_reach * R_j。
    # 规范写的是两个独立的 0.5, 这里不假定它们相加为 1, 各自可调。
    b13_sweep_penetration_weight: float = 0.5
    b13_sweep_reach_weight: float = 0.5

    # --- B14 尺度 ---
    b14_sync_scale: float = 0.05
    b14_ratio_scale: float = 0.10
    b14_loop_scale: float = 0.005          # (e_loop / D) / scale

    # --- 置信度 (PRO-12 §04) ---
    confidence_band: float = 0.20
    abstain_below: float = 0.50

    # --- PROVISIONAL: 轨迹 ---
    qref_profile: str = "trapezoid"        # PROVISIONAL
    qref_accel_frac: float = 0.2           # PROVISIONAL
    qref_duration_s: float = 3.0           # PROVISIONAL

    # --- PROVISIONAL: 执行器 ---
    # 注意: 下面这两个增益是 PyBullet positionGain/velocityGain 的语义(无量纲
    # 混合系数), 在 MuJoCo 里不可通约 —— MuJoCo 的 kp 是真实刚度。仿真器改用
    # MuJoCo 后它们已失效, 但按 CLAUDE.md 的规矩不擅自改 PROVISIONAL 值,
    # 实际生效的是下面 mujoco_actuator_* 那组。见 QUESTIONS.md。
    actuator_mode: str = "position"        # PROVISIONAL
    actuator_max_force: float = 200.0      # PROVISIONAL
    actuator_kp: float = 0.1               # PROVISIONAL (PyBullet 语义, 已失效)
    actuator_kd: float = 1.0               # PROVISIONAL (PyBullet 语义, 已失效)

    # --- PROVISIONAL: MuJoCo 后端 ---
    # 接触参数。冻结在 MuJoCo 默认值上: 换机器/换模型都不该改变判定。
    # 实测这组参数下, 一个完好方块静置在地面的稳态穿透是 0.1078 mm,
    # 与质量、timestep 均无关 -> B13 的 S_dyn 有约 0.9475 的恒定上限。
    mj_solref: tuple[float, float] = (0.02, 1.0)                    # PROVISIONAL
    mj_solimp: tuple[float, float, float, float, float] = (
        0.9, 0.95, 0.001, 0.5, 2.0)                                 # PROVISIONAL
    # 执行器按"关节有效惯量 + 无量纲带宽"定增益, 不用绝对 kp/kv:
    #   kp = M_jj * omega^2      kv = 2 * zeta * omega * M_jj
    # 绝对增益在跨尺度资产上会炸 —— 一个 0.043 kg 的琴键配 kv=50 时
    # m/kv = 0.86ms << dt = 4.17ms, 显式积分必然发散。
    # 稳定性要求 omega*dt << 1: 20 rad/s 时 omega*dt = 0.083。
    mj_actuator_omega: float = 20.0        # PROVISIONAL, rad/s
    mj_actuator_zeta: float = 1.0          # PROVISIONAL, 1.0 = 临界阻尼
    # mj_geomDistance 的量程。超出时它返回 distmax 本身而非哨兵值, 必须判断
    # dist >= distmax 并当作"量程内无测量", 否则会把远距离误当成小间隙。
    mj_geom_distmax: float = 1.0           # PROVISIONAL
    # 无 <inertial> 时 MuJoCo 从 collision 几何推质量所用的密度 (kg/m^3)
    mj_default_density: float = 1000.0     # PROVISIONAL
    # 资产未声明 <dynamics damping> 时的默认关节阻尼。三次试验扰动的就是它。
    mj_default_joint_damping: float = 0.1  # PROVISIONAL
    # 驱动段内关节速度低于 额定速度*该比例 即计入 t_stall
    stall_velocity_frac: float = 0.05      # PROVISIONAL
    # 非目标关节的处理: "hold" 用同一套 PD 保持初始位姿, "free" 放任
    other_joints_policy: str = "hold"      # PROVISIONAL
    # 静置结束时已存在的接触是否并入预期白名单 (自重支撑不算"非预期接触")
    baseline_contacts_expected: bool = True  # PROVISIONAL
    # 关节有效惯量 / 模型最大有效惯量, 低于此比例判退化自由度 -> tool-failure
    min_joint_inertia_ratio: float = 1e-4    # PROVISIONAL

    # --- PROVISIONAL: 扫掠与定义 ---
    sweep_subdivide: bool = True           # PROVISIONAL
    r_j_definition: str = "reachable_fraction"  # PROVISIONAL
    t_act_definition: float = ACTUATE_S    # PROVISIONAL
    # 扫掠中新增穿透超过 frac*D 即判该步阻塞
    sweep_block_penetration_frac: float = 0.001   # PROVISIONAL
    # S_clearance 的归一化尺度: 净空 / (clearance_scale * L_j)
    clearance_scale: float = 0.02          # PROVISIONAL

    # --- PROVISIONAL: 置信度乘子 ---
    q_tool: float = 1.0                    # PROVISIONAL
    q_contract: float = 1.0                # PROVISIONAL

    def tau(self, metric: str) -> float:
        return getattr(self, f"tau_{metric.lower()}")


DEFAULT = Consts()
