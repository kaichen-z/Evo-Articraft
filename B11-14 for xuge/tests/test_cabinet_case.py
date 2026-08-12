"""验收测试: 复现 PRO-12 §08 柜子案例的四个分数 (容差 1e-3)。

这是整个 B11-B14 实现的验收门。四条都过 = 公式实现正确。
"""

from __future__ import annotations

import pytest

from verifier.consts import DEFAULT
from verifier.metrics import b11, b12, b13, b14
from verifier.report import build_report, to_json
from verifier.types import Coverage, Prediction

from .fixtures import (
    cabinet_b11_signals,
    cabinet_b12_signals,
    cabinet_b13_signals,
    cabinet_b14_signals,
    cabinet_contract,
)

TOL = 1e-3


@pytest.fixture
def contract():
    return cabinet_contract()


# ------------------------------------------------------------------ B11
def test_b11_cabinet_score(contract):
    r = b11.score(cabinet_b11_signals(), contract, DEFAULT)
    assert r.score == pytest.approx(0.163, abs=TOL)
    assert r.prediction is Prediction.FAIL


def test_b11_sub_scores(contract):
    s = b11.score(cabinet_b11_signals(), contract, DEFAULT).sub_scores
    assert s["R_geom"] == pytest.approx(0.55, abs=TOL)
    assert s["C"] == pytest.approx(0.54, abs=TOL)
    assert s["T"] == pytest.approx(0.549, abs=TOL)
    assert s["L"] == pytest.approx(1.0, abs=TOL)


def test_b11_evidence_is_traceable(contract):
    """每个失败判定必须能回溯到具体姿态/连杆对 (CLAUDE.md 铁律 6)。"""
    r = b11.score(cabinet_b11_signals(), contract, DEFAULT)
    assert r.evidence["first_blocked_step"] == 18
    assert r.evidence["blocking_pair"] == ["drawer", "side_panel"]
    assert r.failure_reason


# ------------------------------------------------------------------ B12
def test_b12_cabinet_score(contract):
    r = b12.score(cabinet_b12_signals(), contract, DEFAULT)
    assert r.score == pytest.approx(0.000022, abs=1e-6)
    assert r.prediction is Prediction.FAIL


def test_b12_interface_and_gravity_split(contract):
    s = b12.score(cabinet_b12_signals(), contract, DEFAULT).sub_scores
    assert s["S_interface"] == pytest.approx(0.00091, abs=1e-5)
    assert s["S_gravity"] == pytest.approx(0.0247, abs=1e-4)


def test_b12_simulation_cannot_compensate_interface(contract):
    """仿真通过不能补偿 S_interface 失败 —— 乘性门。"""
    sig = cabinet_b12_signals()
    sig.update({"d_gravity": 0.0, "e_constraint": 0.0, "theta_drift_deg": 0.0})
    r = b12.score(sig, contract, DEFAULT)
    assert r.sub_scores["S_gravity"] == pytest.approx(1.0, abs=TOL)
    assert r.score < 0.01
    assert r.prediction is Prediction.FAIL


# ------------------------------------------------------------------ B13
def test_b13_cabinet_score(contract):
    r = b13.score(cabinet_b13_signals(), contract, DEFAULT)
    assert r.score == pytest.approx(0.0117, abs=1e-4)
    assert r.prediction is Prediction.FAIL


def test_b13_sub_scores(contract):
    s = b13.score(cabinet_b13_signals(), contract, DEFAULT).sub_scores
    assert s["S_sweep"] == pytest.approx(0.387, abs=TOL)
    assert s["S_contact"] == pytest.approx(0.247, abs=TOL)
    assert s["S_stall"] == pytest.approx(0.55, abs=TOL)
    assert s["S_dyn"] == pytest.approx(0.223, abs=TOL)


# ------------------------------------------------------------------ B14
def test_b14_not_applicable(contract):
    """无预期耦合/闭环 -> N/A, score=None, 不进聚合分母。"""
    r = b14.score(cabinet_b14_signals(), contract, DEFAULT)
    assert r.score is None
    assert r.coverage is Coverage.NOT_APPLICABLE
    assert not r.counts_in_aggregate


# ------------------------------------------------------------- 端到端报告
def test_full_report(contract):
    results = {
        "B11": b11.score(cabinet_b11_signals(), contract, DEFAULT),
        "B12": b12.score(cabinet_b12_signals(), contract, DEFAULT),
        "B13": b13.score(cabinet_b13_signals(), contract, DEFAULT),
        "B14": b14.score(cabinet_b14_signals(), contract, DEFAULT),
    }
    rep = build_report(results, DEFAULT)

    assert rep["coverage"]["scored_metrics"] == 3      # B14 是 N/A
    assert rep["coverage"]["total_metrics"] == 4
    assert rep["human_metrics"]["B14"]["coverage"] == "not-applicable"
    # 依赖的未定参数必须被报告出来
    assert "QREF_PROFILE" in rep["provisional_params"]
    assert "CONTACT_MODEL" in rep["provisional_params"]
    # repair_queue 去重
    assert len(rep["repair_queue"]) == len(set(rep["repair_queue"]))
    to_json(rep)   # 可序列化
