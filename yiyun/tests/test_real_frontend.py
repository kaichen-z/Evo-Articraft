from __future__ import annotations

import json

from verifier.evaluation.metrics import auc, evaluate_item
from verifier.frontends.pipeline import load_prompt_contract, static_signals
from verifier.frontends.static_asset import read_model_source


def test_real_static_model_and_frozen_contract_produce_a1_a3_signals(tmp_path):
    prompt = "A base with two buttons and a lid. The lid rotates on the base."
    path = tmp_path / "contract.json"
    path.write_text(
        json.dumps(
            {
                "record_id": "rec_test",
                "prompt": prompt,
                "expected_parts": [
                    {"name": "base", "source": "explicit", "quote": "A base"},
                    {"name": "button", "count": 2, "source": "explicit", "quote": "two buttons"},
                    {"name": "lid", "source": "explicit", "quote": "a lid"},
                ],
                "expected_joints": [
                    {
                        "child": "lid",
                        "parent": "base",
                        "kind": "revolute",
                        "source": "explicit",
                        "quote": "The lid rotates on the base",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    contract, frozen = load_prompt_contract(path)
    asset = read_model_source(
        '''
from sdk import ArticulatedObject, ArticulationType, Box, Origin, MotionLimits
def build_object_model():
    model = ArticulatedObject(name="fixture")
    base = model.part("base")
    base.visual(Box((1, 1, 1)))
    lid = model.part("lid")
    lid.visual(Box((1, 1, .1)))
    button_0 = model.part("button_0")
    button_1 = model.part("button_1")
    model.articulation("hinge", ArticulationType.REVOLUTE, parent=base, child=lid,
        origin=Origin(), axis=(0, 1, 0),
        motion_limits=MotionLimits(lower=0, upper=1.5))
    return model
'''
    )
    signals = static_signals(asset, frozen)
    assert contract["required_movables"][0]["id"] == "lid"
    assert signals["matched_required_movables"] == ["lid"]
    assert signals["actual_part_counts"]["button"] == 2
    assert signals["matched_required_parts"] == ["base", "button", "lid"]


def test_contract_loader_preserves_unspecified_count(tmp_path):
    path = tmp_path / "contract.json"
    path.write_text(json.dumps({
        "record_id": "rec_test",
        "expected_parts": [{
            "name": "button", "count": None, "source": "explicit", "quote": "buttons"
        }],
        "expected_joints": [],
    }), encoding="utf-8")
    contract, _ = load_prompt_contract(path)
    assert contract["required_parts"][0]["count"] is None


def test_alignment_reports_auc_and_abstention_coverage():
    rows = [
        {"record_id": "bad", "human": "不满足", "score": 0.1, "prediction": "fail"},
        {"record_id": "good", "human": "满足", "score": 0.9, "prediction": "pass"},
        {"record_id": "unknown", "human": "不满足", "score": 0.5, "prediction": "abstain"},
    ]
    result = evaluate_item(rows, "A1")
    assert auc([0.1], [0.9]) == 1.0
    assert result["auc"] == 1.0
    assert result["decision_coverage"] == 2 / 3
    assert result["f1"] == 1.0
    assert result["kappa"] == 1.0
