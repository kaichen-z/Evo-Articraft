import json

import pytest

from verifier.contracts.extract_a4_a5 import ExtractionError, extension_from_answer


PROMPT = (
    "A desk fan with a guarded fan head between two side brackets. "
    "Emphasize a long vertical proportion with a small head at the top."
)


def answer():
    return {
        "required_interfaces": [],
        "appearance_claims": [
            {
                "id": "long_vertical_proportion",
                "subject": "whole object",
                "claim_type": "proportion",
                "description": "long vertical proportion",
                "comparison_target": "width",
                "check_mode": "geometry",
                "source": "prompt",
                "confidence": 1.0,
                "evidence_text": "long vertical proportion",
            }
        ],
        "spatial_relations": [
            {
                "id": "head_between_brackets",
                "subject": "fan head",
                "relation": "between",
                "objects": ["left bracket", "right bracket"],
                "frame": "object",
                "check_mode": "geometry",
                "source": "prompt",
                "confidence": 1.0,
                "evidence_text": "fan head between two side brackets",
            }
        ],
        "advisory_inferences": [],
    }


def test_validates_and_freezes_prompt_requirements():
    result = extension_from_answer(
        json.dumps(answer()), record_id="rec_fan", prompt=PROMPT, extractor="test-model"
    )
    assert result["appearance_claims"][0]["claim_type"] == "proportion"
    assert result["required_interfaces"] == []
    assert result["spatial_relations"][0]["objects"] == ["left bracket", "right bracket"]
    assert result["extractor"] == "test-model"


def test_rejects_invented_quote():
    payload = answer()
    payload["appearance_claims"][0]["evidence_text"] = "five metal blades"
    with pytest.raises(ExtractionError, match="exact prompt substring"):
        extension_from_answer(payload, record_id="rec_fan", prompt=PROMPT, extractor="test")


def test_rejects_unknown_relation():
    payload = answer()
    payload["spatial_relations"][0]["relation"] = "looks_good_next_to"
    with pytest.raises(ExtractionError, match="invalid relation"):
        extension_from_answer(payload, record_id="rec_fan", prompt=PROMPT, extractor="test")
