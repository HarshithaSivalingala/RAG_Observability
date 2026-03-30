"""
test_adapter.py — Tests for VerbaMessageAdapter.

The adapter is the single place that knows how to read/write
Verba WebSocket messages. These tests verify it handles all
known message formats and edge cases correctly.
"""

import json
import pytest


class TestExtractQuestion:

    def test_from_query_field(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_question(
            {"query": "What is the value?"}
        ) == "What is the value?"

    def test_from_message_field(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_question(
            {"message": "What is the value?"}
        ) == "What is the value?"

    def test_from_question_field(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_question(
            {"question": "What is the value?"}
        ) == "What is the value?"

    def test_from_input_field(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_question(
            {"input": "What is the value?"}
        ) == "What is the value?"

    def test_strips_whitespace(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_question(
            {"query": "  hello world  "}
        ) == "hello world"

    def test_returns_none_if_no_question_key(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_question({"type": "ping"}) is None

    def test_returns_none_for_empty_string(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_question({"query": ""}) is None

    def test_returns_none_for_whitespace_only(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_question({"query": "   "}) is None

    def test_returns_none_for_non_string_value(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_question({"query": 123}) is None


class TestExtractChunks:

    def test_from_chunks_key(self):
        from main import VerbaMessageAdapter
        msg = {"chunks": [{"doc_name": "report.pdf", "score": 0.92}]}
        chunks = VerbaMessageAdapter.extract_chunks(msg)
        assert len(chunks) == 1
        assert chunks[0]["title"] == "report.pdf"
        assert chunks[0]["score"] == 0.92

    def test_from_documents_key(self):
        from main import VerbaMessageAdapter
        msg = {"documents": [{"title": "memo.pdf", "score": 0.85}]}
        chunks = VerbaMessageAdapter.extract_chunks(msg)
        assert chunks[0]["title"] == "memo.pdf"

    def test_title_fallback_order(self):
        """doc_name → title → document → name → Unknown"""
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_chunks(
            {"chunks": [{"doc_name": "a.pdf", "score": 0.9}]}
        )[0]["title"] == "a.pdf"

        assert VerbaMessageAdapter.extract_chunks(
            {"chunks": [{"title": "b.pdf", "score": 0.9}]}
        )[0]["title"] == "b.pdf"

        assert VerbaMessageAdapter.extract_chunks(
            {"chunks": [{"document": "c.pdf", "score": 0.9}]}
        )[0]["title"] == "c.pdf"

        assert VerbaMessageAdapter.extract_chunks(
            {"chunks": [{"score": 0.9}]}
        )[0]["title"] == "Unknown"

    def test_invalid_score_defaults_to_zero(self):
        from main import VerbaMessageAdapter
        chunks = VerbaMessageAdapter.extract_chunks(
            {"chunks": [{"title": "doc.pdf", "score": "not-a-number"}]}
        )
        assert chunks[0]["score"] == 0.0

    def test_missing_score_defaults_to_zero(self):
        from main import VerbaMessageAdapter
        chunks = VerbaMessageAdapter.extract_chunks(
            {"chunks": [{"title": "doc.pdf"}]}
        )
        assert chunks[0]["score"] == 0.0

    def test_returns_empty_for_no_chunk_key(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_chunks({"message": "answer"}) == []

    def test_returns_empty_for_empty_list(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_chunks({"chunks": []}) == []

    def test_skips_non_dict_chunk_entries(self):
        from main import VerbaMessageAdapter
        chunks = VerbaMessageAdapter.extract_chunks(
            {"chunks": [{"title": "valid.pdf", "score": 0.9}, "invalid", None]}
        )
        assert len(chunks) == 1
        assert chunks[0]["title"] == "valid.pdf"


class TestExtractResponseToken:

    def test_from_message_key(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_response_token(
            {"message": "The answer is 42."}
        ) == "The answer is 42."

    def test_from_text_key(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_response_token(
            {"text": "The answer is 42."}
        ) == "The answer is 42."

    def test_from_content_key(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_response_token(
            {"content": "The answer is 42."}
        ) == "The answer is 42."

    def test_returns_none_if_no_token_key(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_response_token({"chunks": []}) is None

    def test_returns_none_for_empty_string(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_response_token({"message": ""}) is None

    def test_returns_none_for_whitespace(self):
        from main import VerbaMessageAdapter
        assert VerbaMessageAdapter.extract_response_token({"message": "   "}) is None


class TestFormatCachedResponse:
    """
    Cached response must use the same JSON format as Verba's live responses
    so the frontend handles them identically.
    """

    def test_uses_message_key(self):
        from main import VerbaMessageAdapter
        data = json.loads(VerbaMessageAdapter.format_cached_response("The answer."))
        assert "message" in data
        assert data["message"] == "The answer."

    def test_sets_cached_flag(self):
        from main import VerbaMessageAdapter
        data = json.loads(VerbaMessageAdapter.format_cached_response("answer"))
        assert data.get("cached") is True

    def test_returns_valid_json_string(self):
        from main import VerbaMessageAdapter
        result = VerbaMessageAdapter.format_cached_response("answer")
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_roundtrip_extraction(self):
        """format_cached_response output must be readable by extract_response_token."""
        from main import VerbaMessageAdapter
        formatted = VerbaMessageAdapter.format_cached_response("The answer is 42.")
        data = json.loads(formatted)
        token = VerbaMessageAdapter.extract_response_token(data)
        assert token == "The answer is 42."
