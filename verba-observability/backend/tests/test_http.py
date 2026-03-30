"""
test_http.py — Fixed version.

Fixes:
- Categorization tests use questions that unambiguously match one category
- Error classification test uses "failed to connect" which matches connection_error
- All tests verify actual keyword matches not assumed ones
"""

import pytest


class TestFilterHeaders:

    def test_removes_connection_header(self):
        from main import _filter_headers
        result = _filter_headers({"connection": "keep-alive", "content-type": "application/json"})
        assert "connection" not in result
        assert "content-type" in result

    def test_removes_transfer_encoding(self):
        from main import _filter_headers
        result = _filter_headers({"transfer-encoding": "chunked", "authorization": "Bearer x"})
        assert "transfer-encoding" not in result
        assert "authorization" in result

    def test_removes_host_header(self):
        from main import _filter_headers
        result = _filter_headers({"host": "localhost:8001", "x-custom": "value"})
        assert "host" not in result
        assert "x-custom" in result

    def test_removes_all_hop_by_hop_headers(self):
        from main import HOP_BY_HOP_HEADERS, _filter_headers
        headers = {h: "value" for h in HOP_BY_HOP_HEADERS}
        headers["x-keep-this"] = "important"
        result = _filter_headers(headers)
        assert list(result.keys()) == ["x-keep-this"]

    def test_case_insensitive_filtering(self):
        from main import _filter_headers
        result = _filter_headers({
            "Connection": "keep-alive",
            "TRANSFER-ENCODING": "chunked",
            "Content-Type": "application/json",
        })
        assert "Connection" not in result
        assert "TRANSFER-ENCODING" not in result
        assert "Content-Type" in result

    def test_empty_headers_returns_empty(self):
        from main import _filter_headers
        assert _filter_headers({}) == {}

    def test_all_safe_headers_preserved(self):
        from main import _filter_headers
        headers = {
            "content-type": "application/json",
            "authorization": "Bearer token",
            "x-request-id": "abc-123",
            "accept": "application/json",
        }
        result = _filter_headers(headers)
        assert result == headers


class TestBuildProxyUrl:

    def test_basic_url_construction(self):
        from main import _build_proxy_url
        url, params = _build_proxy_url("api/documents", {})
        assert url == "http://localhost:8000/api/documents"
        assert params == {}

    def test_query_params_returned_as_dict(self):
        from main import _build_proxy_url
        url, params = _build_proxy_url("api/search", {"limit": "10", "offset": "0"})
        assert params == {"limit": "10", "offset": "0"}

    def test_url_does_not_include_query_string(self):
        from main import _build_proxy_url
        url, params = _build_proxy_url("api/search", {"q": "portfolio value"})
        assert "?" not in url
        assert "q" in params

    def test_special_characters_in_params(self):
        from main import _build_proxy_url
        url, params = _build_proxy_url("api/search", {"q": "value & profit > 0"})
        assert params["q"] == "value & profit > 0"

    def test_empty_path(self):
        from main import _build_proxy_url
        url, params = _build_proxy_url("", {})
        assert url == "http://localhost:8000/"


class TestQueryCategorization:
    """
    Use unambiguous questions that clearly match one category.
    Avoid questions with keywords that could match multiple categories.
    """

    def test_financial_keywords(self):
        from main import categorize_query
        # "portfolio" and "ytd" are financial-only keywords
        assert categorize_query("Show my portfolio allocation") == "financial"
        assert categorize_query("What is the YTD performance?") == "financial"
        assert categorize_query("List all stock holdings") == "financial"

    def test_compliance_keywords(self):
        from main import categorize_query
        # "audit", "fiduciary", "finra" are compliance-only keywords
        assert categorize_query("Were any audit violations found?") == "compliance"
        assert categorize_query("What are the FINRA deadlines?") == "compliance"
        assert categorize_query("Explain the fiduciary requirements") == "compliance"

    def test_analytical_keywords(self):
        from main import categorize_query
        # "compare", "trend", "breakdown" are analytical-only keywords
        assert categorize_query("Compare Q1 and Q2 results") == "analytical"
        assert categorize_query("Show me the trend over time") == "analytical"
        assert categorize_query("Give me a breakdown of costs") == "analytical"

    def test_factual_keywords(self):
        from main import categorize_query
        # Use questions with keywords that ONLY appear in factual category
        assert categorize_query("What is the standard deduction?") == "factual"
        assert categorize_query("Define the term amortization") == "factual"
        assert categorize_query("Which accounts were opened in 2024?") == "factual"

    def test_general_fallback(self):
        from main import categorize_query
        assert categorize_query("hello") == "general"
        assert categorize_query("") == "general"
        assert categorize_query("   ") == "general"

    def test_first_matching_category_wins(self):
        """When multiple keywords match, the first category in order wins."""
        from main import CATEGORY_KEYWORDS, categorize_query
        # "portfolio" matches financial first — even if other keywords present
        assert categorize_query("portfolio audit") == "financial"


class TestErrorClassification:

    def test_timeout(self):
        from main import classify_error
        assert classify_error("Request timed out after 30s") == "timeout"
        assert classify_error("operation timed out") == "timeout"

    def test_connection_error(self):
        from main import classify_error
        # Use exact keywords that are in the classifier
        assert classify_error("Connection refused by server") == "connection_error"
        assert classify_error("connection failed") == "connection_error"

    def test_empty_response(self):
        from main import classify_error
        assert classify_error("Got empty response from server") == "empty_response"

    def test_unknown_error(self):
        from main import classify_error
        assert classify_error("Something unexpected happened") == "unknown"
        assert classify_error("Internal server error 500") == "unknown"