"""MuJoCo 后端的行为测试: loader / sweep / protocol / runner。

用内联合成的最小 URDF, 不依赖任何外部资产库 —— 换台机器 clone 下来就能跑。
没装 mujoco 时整个模块跳过, metrics/ 的 88 项单测不受影响。
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

mujoco = pytest.importorskip("mujoco", reason="sim 后端需要 mujoco (pip install -e .[sim])")

from verifier.consts import DT, SWEEP_STEPS, DEFAULT
from verifier.types import ToolFailure

_INERTIA = '<inertia ixx="0.01" ixy="0" ixz="0" iyy="0.01" iyz="0" izz="0.01"/>'


def _urdf(*, wall_x: float | None = None, inertial: bool = True,
          collision: bool = True, light_joint: bool = False) -> str:
    """底座 + 滑块。wall_x 给定时在该处加一堵挡住滑块的墙。

    几何都带 name —— MuJoCo 会把焊到世界的 body 融进 world, 只有 geom 名
    能保住"撞的是哪块板"这条证据 (铁律 6)。
    """
    def link(name, size, xyz="0 0 0", mass=1.0):
        parts = [f'<link name="{name}">']
        if inertial:
            parts.append(f'<inertial><mass value="{mass}"/>{_INERTIA}</inertial>')
        parts.append(f'<visual name="{name}_vis"><origin xyz="{xyz}"/><geometry>'
                     f'<box size="{size}"/></geometry></visual>')
        if collision:
            parts.append(f'<collision name="{name}"><origin xyz="{xyz}"/><geometry>'
                         f'<box size="{size}"/></geometry></collision>')
        parts.append("</link>")
        return "".join(parts)

    body = [link("base", "0.6 0.4 0.05", mass=10.0),
            link("slider", "0.1 0.1 0.1", mass=1.0)]
    joints = ['<joint name="slide" type="prismatic">'
              '<origin xyz="0 0 0.08"/><parent link="base"/><child link="slider"/>'
              '<axis xyz="1 0 0"/>'
              '<limit effort="100" velocity="1" lower="0" upper="0.3"/></joint>']
    if wall_x is not None:
        body.append(link("wall", "0.02 0.2 0.2", mass=5.0))
        joints.append(f'<joint name="wall_fix" type="fixed">'
                      f'<origin xyz="{wall_x} 0 0.1"/>'
                      f'<parent link="base"/><child link="wall"/></joint>')
    if light_joint:
        # 一个近乎无质量的自由度, 用来触发退化守卫
        body.append(link("speck", "0.004 0.004 0.004", mass=1e-6))
        joints.append('<joint name="speck_slide" type="prismatic">'
                      '<origin xyz="0 0.3 0.1"/><parent link="base"/>'
                      '<child link="speck"/><axis xyz="0 1 0"/>'
                      '<limit effort="1" velocity="1" lower="0" upper="0.05"/></joint>')
    return f'<robot name="t">{"".join(body)}{"".join(joints)}</robot>'


def _write(tmp_path, name="model.urdf", **kw):
    p = tmp_path / name
    p.write_text(_urdf(**kw), encoding="utf-8")
    return p


# ============================================================== loader
def test_inertial_urdf_is_asset_provenance(tmp_path):
    from verifier.sim.loader import load_urdf

    loaded = load_urdf(_write(tmp_path), DEFAULT)
    assert loaded.provenance == "asset"
    assert loaded.d_bbox > 0
    # 底座焊在世界上, MuJoCo 会丢掉它的 10kg —— 总质量必须回到 URDF 原文取,
    # 否则固定底座资产的 mgT 基准会小一个量级。
    assert loaded.model.body_mass.sum() == pytest.approx(1.0)
    assert loaded.mass_is_declared
    assert loaded.total_mass == pytest.approx(11.0, abs=1e-6)


def test_collision_only_urdf_is_inferred(tmp_path):
    """无 <inertial> 但有 <collision> -> MuJoCo 按密度推质量 -> inferred。"""
    from verifier.sim.loader import load_urdf

    loaded = load_urdf(_write(tmp_path, inertial=False), DEFAULT)
    assert loaded.provenance == "inferred"
    assert loaded.total_mass > 0


def test_visual_only_urdf_is_tool_failure(tmp_path):
    """ArtiCraft 的 compile_level=visual 缓存就是这种。不给它伪造物理参数。"""
    from verifier.sim.loader import load_urdf

    p = _write(tmp_path, inertial=False, collision=False)
    with pytest.raises(ToolFailure, match="视觉级模型"):
        load_urdf(p, DEFAULT)


def test_missing_file_is_tool_failure(tmp_path):
    from verifier.sim.loader import load_urdf

    with pytest.raises(ToolFailure):
        load_urdf(tmp_path / "nope.urdf", DEFAULT)


def test_protocol_constants_are_frozen_into_model(tmp_path):
    """不覆盖的话 timestep 会是 MuJoCo 默认的 0.002 而不是冻结的 1/240。"""
    from verifier.sim.loader import load_urdf

    loaded = load_urdf(_write(tmp_path), DEFAULT)
    assert loaded.model.opt.timestep == pytest.approx(DT)
    assert loaded.model.geom_solref[0][0] == pytest.approx(DEFAULT.mj_solref[0])
    assert loaded.model.geom_solimp[0][2] == pytest.approx(DEFAULT.mj_solimp[2])


def test_bbox_diagonal_includes_geom_extent(tmp_path):
    """只用 geom_xpos 会把一个大立方体算成一个点。"""
    from verifier.sim.loader import bbox_diagonal, load_urdf

    loaded = load_urdf(_write(tmp_path), DEFAULT)
    assert bbox_diagonal(loaded.model, loaded.data) > 0.6


def test_movable_joints_skips_fixed(tmp_path):
    from verifier.sim.loader import joint_name, load_urdf, movable_joints

    loaded = load_urdf(_write(tmp_path, wall_x=0.5), DEFAULT)
    mj = movable_joints(loaded.model)
    assert [joint_name(loaded.model, j) for j in mj] == ["slide"]


# =============================================================== sweep
def test_sweep_unblocked_travel_is_full(tmp_path):
    from verifier.primitives.sweep import sweep_joint
    from verifier.sim.loader import load_urdf

    loaded = load_urdf(_write(tmp_path), DEFAULT)
    sw = sweep_joint(loaded, 0, DEFAULT)
    assert sw.r_geom == pytest.approx(1.0)
    assert sw.first_blocked_step is None
    assert sw.penetration_max == pytest.approx(0.0, abs=1e-9)
    assert sw.gap_curve_summary["steps"] == SWEEP_STEPS


def test_sweep_detects_blocking_wall(tmp_path):
    """滑块行程 0..0.3, 墙在 0.15 -> 应在中途阻塞并记下阻塞对。"""
    from verifier.primitives.sweep import sweep_joint
    from verifier.sim.loader import load_urdf

    loaded = load_urdf(_write(tmp_path, wall_x=0.15), DEFAULT)
    sw = sweep_joint(loaded, 0, DEFAULT)
    assert sw.first_blocked_step is not None
    assert 0.0 < sw.r_geom < 1.0
    assert sw.penetration_max > 0.0
    assert "wall" in (sw.blocking_pair or []), sw.blocking_pair
    assert sw.gap_curve_summary["penetration_argmax_step"] is not None


def test_sweep_restores_joint_position(tmp_path):
    """扫掠是只读操作, 不能把模型停在扫到一半的姿态。"""
    from verifier.primitives.sweep import sweep_joint
    from verifier.sim.loader import load_urdf

    loaded = load_urdf(_write(tmp_path), DEFAULT)
    before = float(loaded.data.qpos[0])
    sweep_joint(loaded, 0, DEFAULT)
    assert float(loaded.data.qpos[0]) == pytest.approx(before)


def test_distmax_truncation_is_flagged_not_measured(tmp_path):
    """mj_geomDistance 超量程时返回 distmax 本身 —— 不能当测量值。"""
    from verifier.primitives.sweep import sweep_joint
    from verifier.sim.loader import load_urdf

    loaded = load_urdf(_write(tmp_path), DEFAULT)
    tiny = replace(DEFAULT, mj_geom_distmax=1e-6)
    sw = sweep_joint(loaded, 0, tiny)
    assert sw.truncated, "全部超量程时必须标记, 否则会把远距离记成 1e-6 的小间隙"


def test_sweep_signals_cover_metric_keys(tmp_path):
    from verifier.primitives.sweep import sweep_joint
    from verifier.sim.loader import load_urdf

    loaded = load_urdf(_write(tmp_path, wall_x=0.15), DEFAULT)
    sig = sweep_joint(loaded, 0, DEFAULT).as_signals()
    for k in ("r_geom", "penetration_max", "r_j", "l_j", "d_bbox",
              "g0", "g_drift", "d_anchor", "s_clearance"):
        assert k in sig, k
        assert isinstance(sig[k], float)


# ============================================================ protocol
def test_phase_step_counts_match_frozen_durations():
    from verifier.sim.protocol import phases

    ph = phases(DT)
    assert (ph.settle, ph.actuate, ph.hold) == (480, 720, 240)
    assert ph.total == 1440
    assert ph.phase_at(0) == "settle"
    assert ph.phase_at(480) == "actuate"
    assert ph.phase_at(1200) == "hold"


def test_trapezoid_endpoints_and_monotonicity():
    from verifier.sim.protocol import trapezoid_fraction

    assert trapezoid_fraction(0.0, 0.2) == pytest.approx(0.0)
    assert trapezoid_fraction(1.0, 0.2) == pytest.approx(1.0)
    assert trapezoid_fraction(0.5, 0.2) == pytest.approx(0.5, abs=1e-9)
    xs = [trapezoid_fraction(i / 50, 0.2) for i in range(51)]
    assert all(b >= a - 1e-12 for a, b in zip(xs, xs[1:]))


def test_trapezoid_zero_accel_is_linear_ramp():
    from verifier.sim.protocol import trapezoid_fraction

    for u in (0.1, 0.4, 0.9):
        assert trapezoid_fraction(u, 0.0) == pytest.approx(u)


def test_qref_holds_start_during_settle_and_target_after():
    from verifier.sim.protocol import phases, q_ref

    ph = phases(DT)
    assert q_ref(0, ph, 0.0, 1.0, DEFAULT, DT) == pytest.approx(0.0)
    assert q_ref(ph.settle - 1, ph, 0.0, 1.0, DEFAULT, DT) == pytest.approx(0.0)
    assert q_ref(ph.total - 1, ph, 0.0, 1.0, DEFAULT, DT) == pytest.approx(1.0)


def test_unknown_qref_profile_is_loud():
    from verifier.sim.protocol import phases, q_ref

    bad = replace(DEFAULT, qref_profile="whatever")
    with pytest.raises(ValueError, match="QREF_PROFILE"):
        q_ref(phases(DT).settle + 1, phases(DT), 0.0, 1.0, bad, DT)


# ============================================================== runner
def test_run_trial_tracks_target(tmp_path):
    from verifier.sim.runner import run_trial

    p = _write(tmp_path)
    sig = run_trial(p, 0, DEFAULT)
    assert sig["q_target"] == pytest.approx(0.3)
    assert sig["q_end"] == pytest.approx(0.3, abs=0.02), "自由滑块应能跟到位"
    assert sig["rmse"] < 0.1
    assert math.isfinite(sig["impulse_unexpected"])
    assert sig["physics_provenance"] == "asset"


def test_run_trials_perturbs_only_inferred_params(tmp_path):
    """§06: 只扰动推断/默认的质量、摩擦、阻尼。资产自带惯量不得篡改。"""
    from verifier.sim.runner import run_trials

    asset = run_trials(_write(tmp_path), 0, DEFAULT)
    assert [t["trial"]["scale"] for t in asset] == [1.0, 0.8, 1.2]
    assert all(t["trial"]["mass"] is False for t in asset), "asset 级质量不该被缩放"
    assert all(t["total_mass"] == pytest.approx(11.0) for t in asset)

    inferred = run_trials(_write(tmp_path, "inf.urdf", inertial=False), 0, DEFAULT)
    assert all(t["trial"]["mass"] is True for t in inferred)
    masses = [t["total_mass"] for t in inferred]
    assert masses[1] < masses[0] < masses[2], "inferred 级质量应随试验缩放"


def test_degenerate_joint_inertia_is_tool_failure(tmp_path):
    """有效惯量比模型最大值低若干量级时, 测的是数值噪声不是资产。

    实测键盘的旋钮关节 M_jj=3.8e-07, PD 推不动它, 任何接触力都能主导。
    """
    from verifier.sim.loader import joint_name, load_urdf, movable_joints
    from verifier.sim.runner import run_trial

    p = _write(tmp_path, light_joint=True)
    loaded = load_urdf(p, DEFAULT)
    names = {joint_name(loaded.model, j): j for j in movable_joints(loaded.model)}
    speck = names["speck_slide"]

    with pytest.raises(ToolFailure, match="退化"):
        run_trial(p, speck, DEFAULT)
    # 同一个模型上正常的那个关节照常能跑
    assert run_trial(p, names["slide"], DEFAULT)["q_end"] == pytest.approx(0.3, abs=0.02)


def test_unknown_other_joints_policy_is_loud(tmp_path):
    from verifier.sim.runner import run_trial

    bad = replace(DEFAULT, other_joints_policy="whatever")
    with pytest.raises(ValueError, match="other_joints_policy"):
        run_trial(_write(tmp_path), 0, bad)


def test_baseline_contacts_are_not_counted_unexpected(tmp_path):
    """自重支撑接触不该算'非预期'。关掉基线后冲量必然更大。"""
    from verifier.sim.runner import run_trial

    p = _write(tmp_path, wall_x=0.15)
    with_baseline = run_trial(p, 0, DEFAULT)["impulse_unexpected"]
    without = run_trial(p, 0, replace(DEFAULT, baseline_contacts_expected=False))
    assert without["impulse_unexpected"] >= with_baseline


# ============================================================= signals
def test_merge_prefers_sweep_normalisation(tmp_path):
    from verifier.primitives.sweep import sweep_joint
    from verifier.sim.loader import load_urdf
    from verifier.sim.runner import run_trial
    from verifier.sim.signals import merge, provisional_from_signals

    p = _write(tmp_path)
    loaded = load_urdf(p, DEFAULT)
    sw = sweep_joint(loaded, 0, DEFAULT)
    dyn = run_trial(p, 0, DEFAULT)
    sig = merge(sw, dyn, DEFAULT)

    assert sig["d_bbox"] == pytest.approx(sw.d_bbox), "归一化基准以扫掠侧为准"
    assert sig["joint_name"] == sw.joint_name
    assert sig["t_act"] == pytest.approx(DEFAULT.t_act_definition)
    assert "MJ_SOLREF" in provisional_from_signals(sig)
    assert "STALL_DEF" in provisional_from_signals(sig)


def test_merge_without_dynamics_is_geometry_only(tmp_path):
    from verifier.primitives.sweep import sweep_joint
    from verifier.sim.loader import load_urdf
    from verifier.sim.signals import merge, provisional_from_signals

    loaded = load_urdf(_write(tmp_path), DEFAULT)
    sig = merge(sweep_joint(loaded, 0, DEFAULT), None, DEFAULT)
    assert "p_dyn" not in sig
    assert "STALL_DEF" not in provisional_from_signals(sig)


def test_end_to_end_scores_are_finite(tmp_path):
    """跑通全链: URDF -> 扫掠+动态 -> 四条打分, 分数要么 None 要么有限。"""
    from verifier.contracts import new_contract
    from verifier.metrics import b11, b12, b13, b14
    from verifier.primitives.sweep import sweep_joint
    from verifier.sim.loader import load_urdf
    from verifier.sim.runner import run_trial
    from verifier.sim.signals import merge

    p = _write(tmp_path, wall_x=0.15)
    loaded = load_urdf(p, DEFAULT)
    sig = merge(sweep_joint(loaded, 0, DEFAULT), run_trial(p, 0, DEFAULT), DEFAULT)
    contract = new_contract(
        expected_range={"slide": {"min": 0.0, "max": 0.3}},
        expected_interfaces={"slide": {"type": "prismatic"}},
        mounting={"base_link": "base"},
        expected_movables=["slide"])
    for mod in (b11, b12, b13, b14):
        r = mod.score(sig, contract, DEFAULT)
        assert r.score is None or math.isfinite(r.score)
        assert r.coverage is not None
