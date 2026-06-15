from app.rag.generation.guardrails import check_output, run_input_guard


def test_input_guard_accepts_insurance_question():
    result = run_input_guard("Is collision damage covered by my auto policy?")
    assert result["blocked"] is False


def test_input_guard_blocks_off_topic_question():
    result = run_input_guard("Write a sorting algorithm")
    assert result["blocked"] is True
    assert result["reason"] == "off_topic"


def test_output_guard_accepts_known_source_citation():
    chunks = [{"chunk_id": "auto_collision_001"}]
    result = check_output(
        "Collision damage may be covered. [Source: auto_collision_001]",
        chunks,
    )
    assert result["flagged"] is False
