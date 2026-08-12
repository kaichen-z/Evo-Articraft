"""B12 实体接口与物理支撑。

S_interface = exp(-g0/(0.02*L)) * exp(-g_drift/(0.05*L))
              * exp(-d_anchor/(0.05*D)) * S_clearance
S_gravity   = exp(-d_g/(0.01*D)) * exp(-e_c/(0.005*D))
              * exp(-max(0, theta-3)/5)
S_B12 = S_interface * S_gravity * S_payload

关键: 仿真成功不能补偿 S_interface 失败 (乘性门, PRO-12 §05)。

signals:
  g0, g_drift, l_j           接口间隙与活动连杆对角线
  d_anchor, d_bbox           锚点距离与整体包围盒对角线
  s_clearance                局部净空评分 [0,1]
  d_gravity, e_constraint    重力漂移与约束误差
  theta_drift_deg            朝向漂移(度)
  s_payload                  载荷保持评分; 无载荷契约时为 None -> 1.0
  solver_failed              bool
"""

from __future__ import annotations

from ..consts import Consts
from ..types import Coverage, MetricResult
from . import _common as C

METRIC = "B12"
_INTERFACE_KEYS = ("g0", "g_drift", "l_j", "d_anchor", "d_bbox", "s_clearance")
_GRAVITY_KEYS = ("d_gravity", "e_constraint", "theta_drift_deg")
_NUMERIC_KEYS = _INTERFACE_KEYS + _GRAVITY_KEYS + ("s_payload",)


@C.guards(METRIC)
def score(signals: dict, contract: dict, consts: Consts) -> MetricResult:
    if not contract.get("expected_interfaces") and not contract.get("mounting"):
        return C.not_applicable(METRIC, consts, "契约中没有接口或安装要求")

    if signals.get("solver_failed"):
        return C.tool_failure(
            METRIC, consts, "仿真器求解失败",
            solver_status=signals.get("solver_status"),
        )

    bad = C.non_finite(signals, _NUMERIC_KEYS)
    if bad:
        return C.tool_failure(
            METRIC, consts, "信号含 NaN/inf, 疑似仿真发散", non_finite=bad
        )

    missing_if = C.require(signals, _INTERFACE_KEYS)
    if missing_if:
        return C.tool_failure(METRIC, consts, "缺少接口几何证据", missing=missing_if)

    l_j = float(signals["l_j"])
    d_bbox = float(signals["d_bbox"])
    if l_j <= 0 or d_bbox <= 0:
        return C.tool_failure(METRIC, consts, "归一化尺度无效", l_j=l_j, d_bbox=d_bbox)

    g0_raw = float(signals["g0"])
    g0 = _effective_gap(g0_raw, consts)
    g_drift = float(signals["g_drift"])
    d_anchor = float(signals["d_anchor"])
    s_clear = C.clip01(float(signals["s_clearance"]))

    f_g0 = C.exp_decay(g0, consts.b12_g0_scale * l_j)
    f_gd = C.exp_decay(g_drift, consts.b12_gdrift_scale * l_j)
    f_anchor = C.exp_decay(d_anchor, consts.b12_anchor_scale * d_bbox)
    s_interface = f_g0 * f_gd * f_anchor * s_clear

    provenance = signals.get("physics_provenance", "default")
    missing_grav = C.require(signals, _GRAVITY_KEYS)
    provisional = ["CONTACT_MODEL", "G0_SIGN_CONVENTION"]

    raw = {
        "g0": g0, "g0_measured": g0_raw, "g_drift": g_drift, "l_j": l_j,
        "d_anchor": d_anchor, "d_bbox": d_bbox,
        "g0_norm": g0 / l_j, "g_drift_norm": g_drift / l_j,
        "d_anchor_norm": d_anchor / d_bbox,
        "s_clearance": s_clear,
    }
    if g0_raw < 0:
        raw["g0_penetration_depth"] = -g0_raw
    subs = {
        "f_g0": f_g0, "f_g_drift": f_gd, "f_anchor": f_anchor,
        "s_clearance": s_clear, "S_interface": s_interface,
    }

    if missing_grav:
        # 只有静态接口证据 -> 部分覆盖。不用 1.0 补齐重力项。
        return C.build_result(
            METRIC, s_interface, Coverage.PARTIAL, consts,
            physics_provenance=provenance,
            tools=["interface"],
            raw_measurements=raw,
            sub_scores=subs,
            evidence=_evidence(signals, missing=missing_grav,
                               penetration=-g0_raw if g0_raw < 0 else None),
            failure_reason=_interface_reason(f_g0, f_gd, f_anchor, s_clear,
                                             s_interface, consts, g0_raw),
            repair_hint="增加合页支架/滑轨/支撑, 并修正安装或质量分布",
            provisional_params=provisional,
            n_factors=4,
        )

    d_g = float(signals["d_gravity"])
    e_c = float(signals["e_constraint"])
    theta = float(signals["theta_drift_deg"])

    f_dg = C.exp_decay(d_g, consts.b12_gravity_drift_scale * d_bbox)
    f_ec = C.exp_decay(e_c, consts.b12_constraint_scale * d_bbox)
    f_theta = C.exp_decay(
        max(0.0, theta - consts.b12_theta_allow_deg), consts.b12_theta_scale_deg
    )
    s_gravity = f_dg * f_ec * f_theta

    raw_payload = signals.get("s_payload")
    has_payload = bool(contract.get("payload"))
    payload_missing = has_payload and raw_payload is None
    # 契约没声明载荷 -> 该因子不适用, 取 1.0。
    # 声明了却没证据 -> 也只能取 1.0, 但那是把缺失因子当满分, 分数因此只是
    # 上界: 降级 partial 并记进 evidence, 由 build_result 禁掉 PASS。
    s_payload = 1.0 if payload_missing or not has_payload else C.clip01(float(raw_payload))

    s = s_interface * s_gravity * s_payload

    raw.update({
        "d_gravity": d_g, "e_constraint": e_c, "theta_drift_deg": theta,
        "d_gravity_norm": d_g / d_bbox, "e_constraint_norm": e_c / d_bbox,
        "s_payload": s_payload,
    })
    subs.update({
        "f_d_gravity": f_dg, "f_e_constraint": f_ec, "f_theta": f_theta,
        "S_gravity": s_gravity, "S_payload": s_payload,
    })

    # 缺证据的载荷项没进乘积, 不能算进等价阈值的因子数。
    n_factors = 8 if (has_payload and not payload_missing) else 7
    coverage = (Coverage.PARTIAL if payload_missing
                else C.coverage_for_physics(provenance, True))
    return C.build_result(
        METRIC, s, coverage, consts,
        physics_provenance=provenance,
        tools=["interface", "simulator"],
        raw_measurements=raw,
        sub_scores=subs,
        evidence=_evidence(signals, missing=["s_payload"] if payload_missing else None,
                           penetration=-g0_raw if g0_raw < 0 else None),
        failure_reason=_reason(s_interface, s_gravity, s_payload, consts),
        repair_hint="增加合页支架/滑轨/支撑, 并修正安装或质量分布",
        provisional_params=provisional,
        n_factors=n_factors,
    )


def _effective_gap(g0: float, consts: Consts) -> float:
    """把测得的 g0 换算成进公式的值。

    g0 < 0 表示接口处零件互相嵌入 —— getClosestPoints 对穿透返回负距离。
    规范只把 g0 定义成"间隙", 而 exp_decay 又把负值截到 0, 于是穿透
    (比缝隙过大更严重的装配缺陷) 会拿到满分因子。默认按深度同等计罚。
    """
    mode = consts.b12_g0_penetration_mode
    if mode == "abs":
        return abs(g0)
    if mode == "clip":
        return g0
    raise ValueError(f"未知的 b12_g0_penetration_mode: {mode!r}")


def _evidence(signals: dict, missing: list[str] | None = None,
              penetration: float | None = None) -> dict:
    ev = {}
    for k in ("joint_name", "interface_pair", "gap_curve_summary", "payload_slip"):
        if signals.get(k) is not None:
            ev[k] = signals[k]
    if missing:
        ev["missing_signals"] = missing
    if penetration is not None:
        ev["interface_penetration_m"] = penetration
    return ev


def _interface_reason(f_g0, f_gd, f_anchor, s_clear, s_interface, consts,
                      g0_raw: float = 0.0) -> str | None:
    if s_interface >= consts.tau_b12:
        return None
    worst = min(
        [("接口处零件互相嵌入(穿透)" if g0_raw < 0
          else "接口初始间隙过大(疑似虚拟合页)", f_g0),
         ("运动中接口间隙漂移过大", f_gd),
         ("关节原点远离接口邻域", f_anchor),
         ("接口局部净空不足", s_clear)],
        key=lambda p: p[1],
    )
    return worst[0]


def _reason(s_interface, s_gravity, s_payload, consts) -> str | None:
    if s_interface * s_gravity * s_payload >= consts.tau_b12:
        return None
    worst = min(
        [("接口几何不成立", s_interface),
         ("重力下发生漂移/塌陷", s_gravity),
         ("载荷保持失败", s_payload)],
        key=lambda p: p[1],
    )
    return worst[0]
