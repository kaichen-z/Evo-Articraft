from verifier.contracts.schema import applicable_metrics, new_contract, validate


def test_only_prompt_sourced_hard_requirements_validate():
    contract = new_contract(required_parts=[{
        "id": "lid",
        "source": "prompt",
        "evidence_text": "a hinged top lid",
    }])
    assert validate(contract) == []
    assert applicable_metrics(contract)["A2"] is True
    assert applicable_metrics(contract)["A6"] is True


def test_inferred_requirement_is_rejected_as_hard_gt():
    contract = new_contract(required_parts=[{
        "id": "motor",
        "source": "llm_prior",
        "evidence_text": "inferred from product category",
    }])
    problems = validate(contract)
    assert any("source=prompt" in problem for problem in problems)
