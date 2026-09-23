"""
Unit tests for app/retriever.py — search result shaping and answer generation.
All externals mocked.
"""

from unittest.mock import MagicMock

import app.retriever as retriever


def _mock_query_results():
    return {
        "ids": [["c1", "c2"]],
        "documents": [["text one", "text two"]],
        "metadatas": [
            [
                {"topic_title": "T1", "section_title": "S1"},
                {"topic_title": "T2", "section_title": "S2"},
            ]
        ],
        "distances": [[0.1, 0.4]],
    }


class TestSearch:
    def _patch(self, monkeypatch):
        collection = MagicMock()
        collection.query.return_value = _mock_query_results()
        monkeypatch.setattr(retriever, "get_chroma_client", lambda persist_dir=None: MagicMock())
        monkeypatch.setattr(retriever, "get_or_create_collection", lambda c: collection)
        monkeypatch.setattr(retriever, "embed_texts", lambda texts: [[0.0, 0.1]])
        return collection

    def test_returns_one_dict_per_hit(self, monkeypatch):
        self._patch(monkeypatch)
        assert len(retriever.search("query")) == 2

    def test_result_shape(self, monkeypatch):
        self._patch(monkeypatch)
        result = retriever.search("query")[0]
        assert set(result) == {"chunk_id", "text", "metadata", "score"}

    def test_score_is_one_minus_distance(self, monkeypatch):
        self._patch(monkeypatch)
        results = retriever.search("query")
        assert results[0]["score"] == 0.9
        assert results[1]["score"] == 0.6

    def test_n_results_passed_to_collection(self, monkeypatch):
        collection = self._patch(monkeypatch)
        retriever.search("query", n_results=7)
        assert collection.query.call_args.kwargs["n_results"] == 7


class TestGenerateAnswer:
    def test_empty_chunks_short_circuits_without_llm(self, monkeypatch):
        client = MagicMock()
        monkeypatch.setattr(retriever, "get_openai_client", lambda: client)
        answer = retriever.generate_answer("q", [])
        assert "No relevant documentation" in answer
        client.chat.completions.create.assert_not_called()

    def test_context_includes_chunk_text_and_titles(self, monkeypatch, retrieved_chunk):
        client = MagicMock()
        client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="answer"))]
        )
        monkeypatch.setattr(retriever, "get_openai_client", lambda: client)

        assert retriever.generate_answer("q", [retrieved_chunk]) == "answer"

        messages = client.chat.completions.create.call_args.kwargs["messages"]
        user_msg = messages[1]["content"]
        assert retrieved_chunk["text"] in user_msg
        assert retrieved_chunk["metadata"]["topic_title"] in user_msg
