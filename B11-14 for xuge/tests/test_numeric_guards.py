"""数值守卫与"缺证据不得判通过"的行为测试。

覆盖六类此前会给出**错误结论**的路径:
  1. NaN 被算成满分因子 / inf 被算成 0.0  (违反铁律 3)
  2. 声明了却没证据的因子被静默补 1.0, 部分覆盖还能判 PASS
  3. B14 用真值判断, d_bbox=0.0 / t_total=0.0 静默丢因子
  4. 公式里硬编码、绕过 consts.py 的常量  (违反铁律 2)
  5. aggregate_trials 就地修改入参, 聚合结果与试验记录共用同一个对象
  6. g0 < 0 (零件互相嵌入) 被截到 0, 穿透拿满分因子
"""

from __future__ import annotations

import copy
import math
from dataclasses import replace

import pytest

from verifier.consts import DEFAULT, PHYSICS_QUALITY
from verifier.contracts import new_contract
from verifier.metrics import REGISTRY, b11, b12, b13, b14
from verifier.metrics._common import clip01, exp_decay
from verifier.report import aggregate_trials
from verifier.types import Coverage, Prediction, ToolFailure

from .fixtures import (
    cabinet_b11_signals,
    cabinet_b12_signals,
    cabinet_b13_signals,
    cabinet_contract,
)

NAN, INF = float("nan"), float("inf")


@pytest.fixture
def contract():
    return cabinet_contract()


# ============================================================ 1. NaN / inf
@pytest.mark.parametrize("bad", [NAN, INF, -INF, "not-a-number"])
@pytest.mark.parametrize("metric,sig_fn,key", [
    ("B11", cabinet_b11_signals, "r_geom"),
    ("B11", cabinet_b11_signals, "rmse"),
    ("B12", cabinet_b12_signals, "g0"),
    ("B12", cabinet_b12_signals, "theta_drift_deg"),
    ("B13", cabinet_b13_signals, "p_dyn"),
    ("B13", cabinet_b13_signals, "t_act"),
])
def test_non_finite_signal_is_tool_failure(metric, sig_fn, key, bad, contract):
    """铁律 3: NaN/发散是工具故障, 既不能变满分也不能变 0 分。"""
    sig = sig_fn()
    sig[key] = bad
    r = REGISTRY[metric](sig, contract, DEFAULT)
    assert r.coverage is Coverage.TOOL_FAILURE
    assert r.score is None
    assert not r.counts_in_aggregate
    assert key in r.evidence["non_finite"]


def test_b14_non_finite_is_tool_failure():
    c = new_contract(coupling=[{"joints": ["l", "r"], "ratio": 1.0}])
    r = b14.score({"sync_rmse_norm": NAN, "r_obs": 1.0, "r_exp": 1.0}, c, DEFAULT)
    assert r.coverage is Coverage.TOOL_FAILURE
    assert r.score is None


def test_nan_would_have_scored_full_marks(contract):
    """回归钉子: max(0.0, nan) == 0.0, 曾让 exp_decay(nan) 算出 1.0。"""
    assert max(0.0, NAN) == 0.0          # 这就是当初的坑
    with pytest.raises(ToolFailure):
        exp_decay(NAN, 0.01)
    with pytest.raises(ToolFailure):
        clip01(NAN)

    sig = cabinet_b12_signals()
    sig["g0"] = NAN
    r = b12.score(sig, contract, DEFAULT)
    assert r.sub_scores.get("f_g0") != 1.0, "NaN 不得变成满分因子"
    assert r.score is None


def test_inf_would_have_scored_zero(contract):
    """回归钉子: exp(-inf) == 0.0, 曾让发散的仿真被记成资产失败。"""
    assert math.exp(-INF) == 0.0
    with pytest.raises(ToolFailure):
        exp_decay(INF, 0.01)

    sig = cabinet_b13_signals()
    sig["p_dyn"] = INF
    r = b13.score(sig, contract, DEFAULT)
    assert r.score is None, "工具故障绝不能伪装成 0.0 分"
    assert r.prediction is not Prediction.FAIL


def test_guards_decorator_converts_tool_failure(contract):
    """兜底层: 万一某个键漏进了 _NUMERIC_KEYS, exp_decay/clip01 抛出的
    ToolFailure 要变成 tool-failure 结果, 而不是冒出异常或算出 1.0/0.0。"""
    from verifier.metrics import _common as C

    @C.guards("B11")
    def broken(signals, contract, consts):
        return C.exp_decay(signals["oops"], 0.01)   # 未被守卫覆盖的键

    r = broken({"oops": NAN}, contract, DEFAULT)
    assert r.coverage is Coverage.TOOL_FAILURE
    assert r.score is None
    assert "非有限值" in r.failure_reason


# =================================================== 2. 部分覆盖不得判 PASS
def test_partial_coverage_cannot_pass(contract):
    """只有几何证据时分数是上界, 上界过线只能弃权, 不能判通过。"""
    r = b11.score({"r_geom": 0.95, "physics_provenance": "asset"}, contract, DEFAULT)
    assert r.coverage is Coverage.PARTIAL
    assert r.score == pytest.approx(0.95)
    assert r.prediction is Prediction.ABSTAIN, "不完整证据不得判 PASS"
    assert r.diagnostics["score_is_upper_bound"] is True


def test_partial_coverage_can_still_fail(contract):
    """上界都低于 tau -> 完整分数必然低于 tau, FAIL 可证。"""
    r = b11.score({"r_geom": 0.30}, contract, DEFAULT)
    assert r.coverage is Coverage.PARTIAL
    assert r.prediction is Prediction.FAIL


def test_b12_interface_only_cannot_pass(contract):
    sig = cabinet_b12_signals()
    for k in ("d_gravity", "e_constraint", "theta_drift_deg"):
        sig[k] = None
    sig.update({"g0": 0.0, "g_drift": 0.0, "d_anchor": 0.0, "s_clearance": 1.0})
    r = b12.score(sig, contract, DEFAULT)
    assert r.score == pytest.approx(1.0)
    assert r.coverage is Coverage.PARTIAL
    assert r.prediction is Prediction.ABSTAIN


def test_full_coverage_still_passes(contract):
    """守卫不能误伤: 证据齐全且分数过线时照常判 PASS。"""
    sig = cabinet_b11_signals()
    sig.update({"r_geom": 1.0, "q_end": 1.0, "rmse": 0.0, "overshoot": 0.0,
                "physics_provenance": "asset"})
    r = b11.score(sig, contract, DEFAULT)
    assert r.coverage is Coverage.FULL
    assert r.score == pytest.approx(1.0)
    assert r.prediction is Prediction.PASS


# ------------------------------------------------------- B12 载荷项
def _payload_contract():
    return new_contract(
        expected_interfaces={"door_joint": {"type": "hinge"}},
        mounting={"base_link": "cabinet_body"},
        payload={"link": "shelf", "mass_kg": 2.0},
    )


def _perfect_b12_signals():
    sig = cabinet_b12_signals()
    sig.update({"g0": 0.0, "g_drift": 0.0, "d_anchor": 0.0, "s_clearance": 1.0,
                "d_gravity": 0.0, "e_constraint": 0.0, "theta_drift_deg": 0.0})
    return sig


def test_declared_payload_without_evidence_is_partial():
    """契约声明了载荷但没测 -> 不能拿 1.0 满分再判 PASS。"""
    sig = _perfect_b12_signals()
    sig["s_payload"] = None
    r = b12.score(sig, _payload_contract(), DEFAULT)
    assert r.coverage is Coverage.PARTIAL
    assert r.prediction is Prediction.ABSTAIN
    assert "s_payload" in r.evidence["missing_signals"]
    assert r.diagnostics["n_multiplicative_factors"] == 7, "没进乘积的项不算因子数"


def test_declared_payload_with_evidence_counts_eight_factors():
    sig = _perfect_b12_signals()
    sig["s_payload"] = 0.9
    r = b12.score(sig, _payload_contract(), DEFAULT)
    assert r.coverage is not Coverage.PARTIAL
    assert r.sub_scores["S_payload"] == pytest.approx(0.9)
    assert r.score == pytest.approx(0.9)
    assert r.diagnostics["n_multiplicative_factors"] == 8


def test_undeclared_payload_is_not_partial(contract):
    """契约没声明载荷 -> 该因子不适用, 取 1.0 是对的, 不该降级。"""
    r = b12.score(cabinet_b12_signals(), contract, DEFAULT)
    assert r.coverage is Coverage.ESTIMATED_PHYSICS
    assert r.diagnostics["n_multiplicative_factors"] == 7


# ====================================== 3. B14 真值短路吞掉无效/缺失尺度
def _loop_contract():
    return new_contract(closed_loop=[{"name": "four_bar"}])


def test_b14_zero_d_bbox_is_tool_failure():
    """0.0 是假值; 用真值判断会短路掉合法性检查, 让 S_loop 静默消失。"""
    r = b14.score({"e_loop": 0.5, "d_bbox": 0.0}, _loop_contract(), DEFAULT)
    assert r.coverage is Coverage.TOOL_FAILURE
    assert r.score is None


def test_b14_zero_t_total_is_tool_failure():
    r = b14.score({"e_loop": 0.001, "d_bbox": 1.0,
                   "t_violation": 5.0, "t_total": 0.0}, _loop_contract(), DEFAULT)
    assert r.coverage is Coverage.TOOL_FAILURE
    assert r.score is None


def test_b14_declared_term_without_evidence_is_partial():
    """声明了闭环却没有 d_bbox -> 该项算不出, 属覆盖不全而非满分。"""
    r = b14.score({"e_loop": 0.5, "t_violation": 0.0, "t_total": 6.0},
                  _loop_contract(), DEFAULT)
    assert r.coverage is Coverage.PARTIAL
    assert "S_loop" in r.evidence["declared_but_unmeasured"]
    assert r.prediction is Prediction.ABSTAIN


def test_b14_missing_sync_evidence_is_partial():
    c = new_contract(coupling=[{"joints": ["l", "r"], "ratio": 1.0}])
    r = b14.score({"r_obs": 1.0, "r_exp": 1.0, "t_violation": 0.0, "t_total": 6.0},
                  c, DEFAULT)
    assert r.coverage is Coverage.PARTIAL
    assert r.evidence["declared_but_unmeasured"] == ["S_sync"]


def test_b14_complete_evidence_is_not_partial():
    c = new_contract(coupling=[{"joints": ["l", "r"], "ratio": 1.0}])
    r = b14.score({"sync_rmse_norm": 0.0, "r_obs": 1.0, "r_exp": 1.0,
                   "t_violation": 0.0, "t_total": 6.0}, c, DEFAULT)
    assert r.coverage is not Coverage.PARTIAL
    assert "declared_but_unmeasured" not in r.evidence
    assert r.prediction is Prediction.PASS


# ================================================ 4. 常量只能来自 consts.py
def test_b13_sweep_weights_come_from_consts(contract):
    """S_sweep 的两个 0.5 曾硬编码在公式里。"""
    sig = cabinet_b13_signals()
    base = b13.score(sig, contract, DEFAULT).sub_scores["S_sweep"]
    tweaked = replace(DEFAULT, b13_sweep_penetration_weight=1.0,
                      b13_sweep_reach_weight=0.0)
    only_pen = b13.score(sig, contract, tweaked).sub_scores["S_sweep"]
    assert base == pytest.approx(0.386565, abs=1e-5)
    assert only_pen == pytest.approx(math.exp(-1.5), abs=1e-6)


def test_b13_t_act_is_not_overridable_by_signals(contract):
    """t_act 是 §06 冻结量, 信号不得改写 S_stall / mgT 的分母。"""
    sig = cabinet_b13_signals()
    sig["t_act"] = 100.0
    r = b13.score(sig, contract, DEFAULT)
    assert r.score == pytest.approx(0.0117, abs=1e-4), "分数不该被信号里的 t_act 改动"
    assert r.raw_measurements["t_act"] == pytest.approx(DEFAULT.t_act_definition)
    dev = r.diagnostics["protocol_deviation"]
    assert dev["t_act_reported"] == 100.0 and dev["t_act_used"] == 3.0


def test_matching_t_act_records_no_deviation(contract):
    r = b13.score(cabinet_b13_signals(), contract, DEFAULT)
    assert "protocol_deviation" not in r.diagnostics


def test_physics_quality_lives_in_consts():
    """铁律 2: 魔法数字的唯一来源是 consts.py。"""
    assert PHYSICS_QUALITY == {"asset": 1.0, "inferred": 0.8, "default": 0.6}
    import verifier.types as t
    assert not hasattr(t, "PHYSICS_QUALITY"), "不该再有第二份"


def test_report_trial_labels_derive_from_trials():
    """报告里的试验标签曾是写死的字符串, 改 TRIALS 会说谎。"""
    from verifier.consts import TRIAL_AGGREGATION_LABEL, TRIALS
    from verifier.report.serialize import simulator_block

    block = simulator_block(DEFAULT)
    assert block["trials"] == ["nominal", "0.8x", "1.2x"]
    assert len(block["trials"]) == len(TRIALS)
    assert block["aggregation"] == TRIAL_AGGREGATION_LABEL


# =================================== 5. aggregate_trials 不得就地改入参
def _three_trials(contract):
    out = []
    for r_geom in (0.55, 0.80, 0.40):
        sig = cabinet_b11_signals()
        sig["r_geom"] = r_geom
        out.append(b11.score(sig, contract, DEFAULT))
    return out


def test_aggregate_trials_does_not_mutate_inputs(contract):
    """以前返回的就是入参里那个最低分对象, 还就地往它的 diagnostics 里写。"""
    trials = _three_trials(contract)
    snapshot = [copy.deepcopy(t.diagnostics) for t in trials]

    agg = aggregate_trials(trials)

    assert all(t is not agg for t in trials), "聚合结果必须是新对象"
    assert [t.diagnostics for t in trials] == snapshot, "入参不得被就地修改"
    assert agg.diagnostics["trial_scores"] == [t.score for t in trials]


def test_aggregate_result_is_detached_from_trials(contract):
    """改聚合结果不该回流到试验记录。"""
    trials = _three_trials(contract)
    agg = aggregate_trials(trials)
    agg.diagnostics["touched"] = True
    agg.evidence["touched"] = True
    agg.sub_scores["touched"] = 1.0
    assert all("touched" not in t.diagnostics for t in trials)
    assert all("touched" not in t.evidence for t in trials)
    assert all("touched" not in t.sub_scores for t in trials)


def test_aggregate_trials_tool_failure_path_also_copies(contract):
    ok = b11.score(cabinet_b11_signals(), contract, DEFAULT)
    bad = b11.score({"solver_failed": True}, contract, DEFAULT)
    agg = aggregate_trials([ok, bad, ok])
    assert agg.coverage is Coverage.TOOL_FAILURE
    assert agg is not bad


# ============================================ 6. g0 < 0 是穿透, 不得给满分
def _b12_with_g0(g0: float) -> dict:
    sig = cabinet_b12_signals()
    sig["g0"] = g0
    return sig


def test_penetrating_interface_is_not_full_marks(contract):
    """getClosestPoints 对穿透返回负距离, exp_decay 截负到 0 -> 因子 1.0。"""
    r = b12.score(_b12_with_g0(-0.03), contract, DEFAULT)
    assert r.sub_scores["f_g0"] < 1.0
    assert r.sub_scores["f_g0"] == pytest.approx(math.exp(-3), abs=1e-6)


def test_penetration_scores_same_as_equal_gap(contract):
    """默认约定: 嵌入 d 米与缝隙 d 米同等计罚。"""
    deep = b12.score(_b12_with_g0(-0.03), contract, DEFAULT)
    gap = b12.score(_b12_with_g0(0.03), contract, DEFAULT)
    assert deep.score == pytest.approx(gap.score)


def test_penetration_is_traceable(contract):
    """铁律 6: 失败判定要回溯到具体量, 且换算过程可见。"""
    r = b12.score(_b12_with_g0(-0.03), contract, DEFAULT)
    assert r.evidence["interface_penetration_m"] == pytest.approx(0.03)
    assert r.raw_measurements["g0_measured"] == pytest.approx(-0.03)
    assert r.raw_measurements["g0"] == pytest.approx(0.03)
    assert "G0_SIGN_CONVENTION" in r.provisional_params


def test_penetration_failure_reason_names_penetration(contract):
    sig = _b12_with_g0(-0.03)
    for k in ("d_gravity", "e_constraint", "theta_drift_deg"):
        sig[k] = None
    r = b12.score(sig, contract, DEFAULT)
    assert "嵌入" in r.failure_reason


def test_clip_mode_restores_literal_spec_behaviour(contract):
    """切回 clip 就是规范字面行为 —— 穿透拿满分。留作对照, 也是回退开关。"""
    clip = replace(DEFAULT, b12_g0_penetration_mode="clip")
    r = b12.score(_b12_with_g0(-0.03), contract, clip)
    assert r.sub_scores["f_g0"] == pytest.approx(1.0)


def test_unknown_g0_mode_is_loud(contract):
    """配置写错要炸, 不能静默退回不计罚。"""
    bad = replace(DEFAULT, b12_g0_penetration_mode="whatever")
    with pytest.raises(ValueError, match="b12_g0_penetration_mode"):
        b12.score(cabinet_b12_signals(), contract, bad)


def test_positive_gap_is_unaffected(contract):
    """柜子案例 g0 > 0, 结果必须一位不变。"""
    r = b12.score(cabinet_b12_signals(), contract, DEFAULT)
    assert r.score == pytest.approx(0.000022, abs=1e-6)
    assert "g0_penetration_depth" not in r.raw_measurements
    assert "interface_penetration_m" not in r.evidence
