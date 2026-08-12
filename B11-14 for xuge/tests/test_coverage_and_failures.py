"""覆盖程度、工具故障、N/A 与阈值诊断的行为测试。

这些是 CLAUDE.md 铁律 3-6 的可执行版本。
"""

from __future__ import annotations

import pytest

from verifier.consts import DEFAULT
from verifier.metrics import REGISTRY, b11, b12, b13, b14
from verifier.metrics._common import equivalent_factor_threshold
from verifier.report import aggregate_trials
from verifier.types import Coverage, Prediction

from .fixtures import (
    cabinet_b11_signals,
    cabinet_b12_signals,
    cabinet_b13_signals,
    cabinet_contract,
)


@pytest.fixture
def contract():
    return cabinet_contract()


# --------------------------------------------- 铁律 3: 工具故障 != 资产失败
@pytest.mark.parametrize("metric", ["B11", "B12", "B13", "B14"])
def test_solver_failure_is_not_zero(metric, contract):
    contract["coupling"] = [{"joints": ["l", "r"], "ratio": 1.0}]
    r = REGISTRY[metric]({"solver_failed": True, "solver_status": "NaN"}, contract, DEFAULT)
    assert r.coverage is Coverage.TOOL_FAILURE
    assert r.score is None, "工具故障绝不能伪装成资产 0 分"
    assert not r.counts_in_aggregate


def test_missing_geometry_is_tool_failure(contract):
    r = b11.score({}, contract, DEFAULT)
    assert r.coverage is Coverage.TOOL_FAILURE
    assert r.score is None


def test_invalid_scale_is_tool_failure(contract):
    sig = cabinet_b12_signals()
    sig["l_j"] = 0.0
    r = b12.score(sig, contract, DEFAULT)
    assert r.coverage is Coverage.TOOL_FAILURE


# ------------------------------------------------- 铁律 4/5: 覆盖程度与 N/A
def test_geometry_only_is_partial(contract):
    """仅几何证据 -> partial, 且不用 1.0 补齐缺失因子。"""
    sig = {"r_geom": 0.55}
    r = b11.score(sig, contract, DEFAULT)
    assert r.coverage is Coverage.PARTIAL
    assert r.score == pytest.approx(0.55)
    assert "missing_signals" in r.evidence


def test_static_interface_only_is_partial(contract):
    sig = cabinet_b12_signals()
    for k in ("d_gravity", "e_constraint", "theta_drift_deg"):
        sig[k] = None
    r = b12.score(sig, contract, DEFAULT)
    assert r.coverage is Coverage.PARTIAL
    assert r.score == pytest.approx(r.sub_scores["S_interface"])


def test_sweep_only_is_partial(contract):
    sig = cabinet_b13_signals()
    for k in ("impulse_unexpected", "total_mass", "t_stall", "p_dyn"):
        sig[k] = None
    r = b13.score(sig, contract, DEFAULT)
    assert r.coverage is Coverage.PARTIAL
    assert r.score == pytest.approx(r.sub_scores["S_sweep"])


def test_asset_physics_is_full_coverage(contract):
    sig = cabinet_b11_signals()
    sig["physics_provenance"] = "asset"
    r = b11.score(sig, contract, DEFAULT)
    assert r.coverage is Coverage.FULL


def test_default_physics_is_estimated(contract):
    r = b11.score(cabinet_b11_signals(), contract, DEFAULT)
    assert r.coverage is Coverage.ESTIMATED_PHYSICS


def test_no_expected_range_is_na():
    from verifier.contracts import new_contract

    c = new_contract(expected_range={})
    r = b11.score(cabinet_b11_signals(), c, DEFAULT)
    assert r.coverage is Coverage.NOT_APPLICABLE
    assert r.score is None


# --------------------------------------------------------------- B14 适用项
def test_b14_only_multiplies_applicable_terms():
    from verifier.contracts import new_contract

    c = new_contract(coupling=[{"joints": ["l", "r"], "ratio": 1.0}])
    sig = {"sync_rmse_norm": 0.0, "r_obs": 1.0, "r_exp": 1.0,
           "t_violation": 0.0, "t_total": 6.0, "s_task": 1.0}
    r = b14.score(sig, c, DEFAULT)
    assert "S_loop" not in r.sub_scores, "没声明闭环就不该有 S_loop 项"
    assert r.score == pytest.approx(1.0)


def test_b14_ratio_deviation_penalised():
    from verifier.contracts import new_contract

    c = new_contract(coupling=[{"joints": ["l", "r"], "ratio": 1.0}])
    sig = {"r_obs": 1.2, "r_exp": 1.0, "t_violation": 0.0, "t_total": 6.0}
    r = b14.score(sig, c, DEFAULT)
    assert r.sub_scores["S_ratio"] == pytest.approx(0.1353, abs=1e-3)


def test_b14_declared_but_no_evidence_is_partial():
    from verifier.contracts import new_contract

    c = new_contract(closed_loop=[{"name": "four_bar"}])
    r = b14.score({}, c, DEFAULT)
    assert r.coverage is Coverage.PARTIAL
    assert r.score is None


# ------------------------------------------------------- 阈值严格度诊断
def test_equivalent_factor_threshold_values():
    """把 tau=0.70 的实际严格度暴露出来。"""
    assert equivalent_factor_threshold(0.70, 4) == pytest.approx(0.9147, abs=1e-4)
    assert equivalent_factor_threshold(0.70, 8) == pytest.approx(0.9564, abs=1e-4)


def test_diagnostics_report_equivalent_threshold(contract):
    r = b13.score(cabinet_b13_signals(), contract, DEFAULT)
    assert r.diagnostics["n_multiplicative_factors"] == 4
    assert r.diagnostics["equivalent_factor_threshold"] == pytest.approx(0.9147, abs=1e-3)


# --------------------------------------------------- 三次试验取最低分 (§06)
def test_aggregate_trials_takes_minimum(contract):
    trials = []
    for r_geom in (0.55, 0.80, 0.40):
        sig = cabinet_b11_signals()
        sig["r_geom"] = r_geom
        trials.append(b11.score(sig, contract, DEFAULT))
    agg = aggregate_trials(trials)
    assert agg.score == pytest.approx(min(t.score for t in trials))
    assert agg.diagnostics["trial_aggregation"] == "minimum_trial_score"


def test_aggregate_trials_propagates_tool_failure(contract):
    ok = b11.score(cabinet_b11_signals(), contract, DEFAULT)
    bad = b11.score({"solver_failed": True}, contract, DEFAULT)
    assert aggregate_trials([ok, bad, ok]).coverage is Coverage.TOOL_FAILURE


# ------------------------------------------------------------- 置信度/弃权
def test_low_confidence_abstains(contract):
    """分数贴近阈值 -> 置信度低 -> 弃权, 不硬判通过/失败。"""
    sig = cabinet_b11_signals()
    sig.update({"r_geom": 1.0, "q_end": 0.71, "q_target": 1.0,
                "rmse": 0.0, "overshoot": 0.0, "physics_provenance": "asset"})
    r = b11.score(sig, contract, DEFAULT)
    assert abs(r.score - DEFAULT.tau_b11) < 0.05
    assert r.prediction is Prediction.ABSTAIN


# ----------------------------------------------------- 纯函数: 不修改入参
@pytest.mark.parametrize("metric,sig_fn", [
    ("B11", cabinet_b11_signals), ("B12", cabinet_b12_signals), ("B13", cabinet_b13_signals),
])
def test_scoring_does_not_mutate_inputs(metric, sig_fn, contract):
    sig = sig_fn()
    before_sig, before_con = dict(sig), dict(contract)
    REGISTRY[metric](sig, contract, DEFAULT)
    assert sig == before_sig
    assert contract == before_con
