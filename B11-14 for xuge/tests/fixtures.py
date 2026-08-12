"""柜子案例 fixture (PRO-12 §08)。

资产缺把手; 抽屉在 55% 行程处被侧板挡住; 门有旋转关节声明但没有可信合页接口,
并在重力下漂移。统一 tau = 0.70。

规范只给了最终分数和部分中间量, 下面的原始测量是从中反推的一组自洽取值。
每个数字后面标了它对应规范里的哪个中间量。反推值在等负责人确认后应替换为
真实测量。

  B11: R_geom=.55, C=.54, T=e^(-.03/.05)=.549, L=1     -> .163
  B12: S_interface=.00091, S_gravity=.0247, S_payload=1 -> .000022
  B13: S_sweep=.387, S_contact=.247, S_stall=.55, S_dyn=.223 -> .0117
  B14: N/A (无预期耦合/闭环)
"""

from __future__ import annotations

from verifier.contracts import new_contract

# 整体包围盒对角线, 归一化基准
D = 1.0
# 抽屉活动连杆对角线
L_J = 0.5


def cabinet_contract() -> dict:
    return new_contract(
        asset_id="cabinet_001",
        category="cabinet",
        expected_range={"drawer_joint": {"min": 0.0, "max": 1.0, "unit": "m"}},
        expected_interfaces={"door_joint": {"type": "hinge", "source": "prompt"}},
        mounting={"base_link": "cabinet_body", "fixed_to_world": True},
        expected_movables=["drawer", "door"],
        expected_contacts=[["drawer", "rail"]],
        coupling=[],
        closed_loop=[],
    )


def cabinet_b11_signals() -> dict:
    """抽屉: 几何行程 55%, 动态完成度 54%, RMSE = .03*dq, 无超调。"""
    dq = 1.0
    return {
        "r_geom": 0.55,          # R_geom = .55
        "q_start": 0.0,
        "q_target": 1.0,
        "q_end": 0.54,           # C = .54
        "delta_q": dq,
        "rmse": 0.03 * dq,       # T = e^(-.6) = .5488
        "overshoot": 0.0,        # L = 1
        "physics_provenance": "default",
        "joint_name": "drawer_joint",
        "first_blocked_step": 18,
        "blocking_pair": ["drawer", "side_panel"],
    }


def cabinet_b12_signals() -> dict:
    """门: 虚拟合页 + 重力漂移。

    S_interface = e^(-3) * e^(-2.4) * e^(-.4) * .30 = .00091
    S_gravity   = e^(-2) * e^(-1.2) * e^(-.5)       = .0247
    """
    return {
        "g0": 0.06 * L_J,            # g0/L = .06  -> e^(-3)
        "g_drift": 0.12 * L_J,       # g_drift/L = .12 -> e^(-2.4)
        "l_j": L_J,
        "d_anchor": 0.02 * D,        # d_anchor/D = .02 -> e^(-.4)
        "d_bbox": D,
        "s_clearance": 0.30,
        "d_gravity": 0.02 * D,       # -> e^(-2)
        "e_constraint": 0.006 * D,   # -> e^(-1.2)
        "theta_drift_deg": 5.5,      # max(0, 5.5-3)/5 = .5 -> e^(-.5)
        "s_payload": None,
        "physics_provenance": "default",
        "joint_name": "door_joint",
        "interface_pair": ["door", "cabinet_body"],
    }


def cabinet_b13_signals() -> dict:
    """抽屉: 穿透 + 非预期冲量 + 停滞。

    S_sweep   = .5*e^(-1.5) + .5*.55 = .3866
    S_contact = e^(-1.4) = .2466
    S_stall   = 1 - 1.35/3 = .55
    S_dyn     = e^(-1.5) = .2231
    """
    total_mass, t_act = 10.0, 3.0
    mgt = total_mass * 9.81 * t_act
    return {
        "penetration_max": 0.003 * D,      # P/(.002D) = 1.5
        "d_bbox": D,
        "r_j": 0.55,
        "impulse_unexpected": 0.14 * mgt,  # I/(.10 mgT) = 1.4
        "total_mass": total_mass,
        "t_act": t_act,
        "t_stall": 1.35,                   # 1 - 1.35/3 = .55
        "p_dyn": 0.003 * D,                # p_dyn/(.002D) = 1.5
        "physics_provenance": "default",
        "link_pair": ["drawer", "side_panel"],
        "first_blocked_step": 18,
        "stall_interval": [1.65, 3.0],
    }


def cabinet_b14_signals() -> dict:
    """柜子没有耦合机构 -> B14 不适用。"""
    return {"physics_provenance": "default"}
