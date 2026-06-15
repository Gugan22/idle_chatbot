from app.rag.retrieval import searcher


def test_point_to_dict_supports_legacy_content_payload():
    point = type(
        "Point",
        (),
        {"payload": {"chunk_id": "legacy_1", "content": "Legacy text"}, "score": 0.9},
    )()

    result = searcher._point_to_dict(point)

    assert result["text"] == "Legacy text"


def test_search_multi_type_includes_all_supported_types(monkeypatch):
    searched_types = []

    def fake_search(**kwargs):
        searched_types.append(kwargs["doc_type"])
        return [{
            "chunk_id": kwargs["doc_type"],
            "doc_type": kwargs["doc_type"],
            "qdrant_score": 0.8,
        }]

    monkeypatch.setattr(searcher, "search", fake_search)

    results = searcher.search_multi_type([0.1, 0.2])

    assert searched_types == ["policy", "faq", "coverage", "exclusion", "endorsement"]
    assert len(results) == 5
