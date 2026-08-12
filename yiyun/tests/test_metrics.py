from __future__ import annotations

import math

import pytest

from verifier.consts import DEFAULT
from verifier.contracts.schema import new_contract
from verifier.metrics import a1, a2, a3, a4, a5, a6
from verifier.types import Coverage, Prediction


def item(identifier: str, *, category: str | None = None, count: int = 1) -> dict:
    value = {
        "id": identifier,
        "source": "prompt",
        "evidence_text": f"Prompt explicitly requires {identifier}",
    }
    if category is not None:
        value["category"] = category
    if count != 1:
        value["count"] = count
    return value


def test_a1_perfect_activity_split_passes():
    contract = new_contract(required_movables=[item("lid"), item("button")])
    result = a1.score({
        "matched_required_movables": ["lid", "button"],
        "actual_movable_ids": ["lid_link", "button_link"],
        "spurious_movable_ids": [],
    }, contract, DEFAULT)
    assert result.score == pytest.approx(1.0)
    assert result.prediction is Prediction.PASS


def test_a1_missing_and_spurious_are_traceable():
    contract = new_contract(required_movables=[item("lid"), item("button")])
    result = a1.score({
        "matched_required_movables": ["lid"],
        "actual_movable_ids": ["lid_link", "ornament"],
        "spurious_movable_ids": ["ornament"],
    }, contract, DEFAULT)
    assert result.score == pytest.approx(0.5 * math.exp(-0.5))
    assert result.evidence["missing_required_movables"] == ["button"]
    assert result.prediction is Prediction.FAIL


def test_a1_expands_explicit_repeated_movable_count():
    contract = new_contract(required_movables=[item("outlet_flap", count=4)])
    result = a1.score({
        "matched_required_movables": [],
        "matched_required_movable_counts": {"outlet_flap": 3},
        "actual_movable_ids": ["flap_0", "flap_1", "flap_2"],
        "spurious_movable_ids": [],
    }, contract, DEFAULT)
    assert result.raw_measurements["expected_count"] == 4
    assert result.raw_measurements["matched_count"] == 3
    assert result.sub_scores["recall"] == pytest.approx(0.75)
    assert result.evidence["missing_required_movables"] == ["outlet_flap[4]"]


def test_a2_counts_only_prompt_required_categories():
    contract = new_contract(required_parts=[item("links", category="link", count=3),
                                            item("pad", category="pad")])
    result = a2.score({
        "actual_part_counts": {"link": 2, "pad": 1, "decorative_bolt": 20},
        "type_match_score": 1.0,
    }, contract, DEFAULT)
    assert result.sub_scores["S_count"] == pytest.approx(0.75)
    assert result.score == pytest.approx(0.875)
    assert result.evidence["unrequested_categories"] == ["decorative_bolt"]


def test_a2_null_count_checks_presence_without_assuming_exactly_one():
    requirement = item("controls", category="button")
    requirement["count"] = None
    contract = new_contract(required_parts=[requirement])
    result = a2.score({
        "actual_part_counts": {"button": 4},
        "type_match_score": 1.0,
    }, contract, DEFAULT)
    assert "S_count" not in result.sub_scores
    assert result.sub_scores["S_type"] == 1.0
    assert result.score == 1.0
    assert result.evidence["count_unspecified_categories"] == ["button"]


def test_a3_matches_prompt_parts_and_interfaces():
    contract = new_contract(
        required_parts=[item("body"), item("lid")],
        required_interfaces=[item("lid_opening")],
    )
    result = a3.score({
        "matched_required_parts": ["body", "lid"],
        "matched_required_interfaces": [],
    }, contract, DEFAULT)
    assert result.score == pytest.approx(0.7)
    assert result.evidence["missing_interfaces"] == ["lid_opening"]
    # 正好落在阈值上，但置信度为 0，所以应弃权而非假装高置信通过。
    assert result.prediction is Prediction.ABSTAIN


def test_a4_without_calibrated_vlm_is_partial_and_cannot_pass():
    contract = new_contract(
        appearance_claims=[item("compact_proportions")],
        category_scale={"median_m": 0.2, "source": "dataset"},
    )
    result = a4.score({
        "vlm_realism_probability": 0.95,
        "cross_view_consistency": 0.95,
        "actual_scale_m": 0.2,
        "vlm_calibrated": False,
    }, contract, DEFAULT)
    assert result.coverage is Coverage.PARTIAL
    assert result.prediction is Prediction.ABSTAIN


def test_a5_weighted_relation_score():
    contract = new_contract(spatial_relations=[item("wheel_front_below_tray")])
    result = a5.score({"relation_results": [{
        "id": "wheel_front_below_tray",
        "position": 0.2,
        "orientation": 1.0,
        "side": 0.0,
        "neighborhood": 0.5,
    }]}, contract, DEFAULT)
    assert result.score == pytest.approx(0.42)
    assert result.prediction is Prediction.FAIL
    assert result.evidence["violated_relations"]


def test_a6_clean_initial_pose_passes():
    result = a6.score({
        "object_diagonal_m": 1.0,
        "unexpected_penetration_m": 0.0,
        "detached_volume_ratio": 0.0,
        "unsupported_gap_m": 0.0,
    }, new_contract(), DEFAULT)
    assert result.score == pytest.approx(1.0)
    assert result.prediction is Prediction.PASS


def test_a6_proxy_measurement_is_partial_and_cannot_claim_pass():
    result = a6.score({
        "object_diagonal_m": 1.0,
        "unexpected_penetration_m": 0.0,
        "detached_volume_ratio": 0.0,
        "unsupported_gap_m": 0.0,
        "a6_measurement_notes": {"detached_ratio_is_part_count_proxy": True},
    }, new_contract(), DEFAULT)
    assert result.coverage is Coverage.PARTIAL
    assert result.prediction is Prediction.ABSTAIN


def test_a6_penetration_fails_with_pair_evidence():
    result = a6.score({
        "object_diagonal_m": 1.0,
        "unexpected_penetration_m": 0.01,
        "detached_volume_ratio": 0.0,
        "unsupported_gap_m": 0.0,
        "penetrating_pairs": [{"a": "drawer", "b": "cabinet", "depth_m": 0.01}],
    }, new_contract(), DEFAULT)
    assert result.score == pytest.approx(math.exp(-5.0))
    assert result.prediction is Prediction.FAIL
    assert result.evidence["penetrating_pairs"][0]["a"] == "drawer"


@pytest.mark.parametrize("module,contract", [
    (a1, new_contract()),
    (a2, new_contract()),
    (a3, new_contract()),
    (a4, new_contract()),
    (a5, new_contract()),
])
def test_prompt_dependent_metrics_are_na_without_explicit_contract(module, contract):
    result = module.score({}, contract, DEFAULT)
    assert result.coverage is Coverage.NOT_APPLICABLE
    assert result.score is None


def test_a6_nan_is_tool_failure_not_asset_failure():
    result = a6.score({
        "object_diagonal_m": 1.0,
        "unexpected_penetration_m": float("nan"),
        "detached_volume_ratio": 0.0,
        "unsupported_gap_m": 0.0,
    }, new_contract(), DEFAULT)
    assert result.coverage is Coverage.TOOL_FAILURE
    assert result.score is None
