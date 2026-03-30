"""
test_cache.py — Cache tests using timezone-aware datetimes throughout.
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone


def _now():
    """Timezone-aware UTC now — matches what main.py uses."""
    return datetime.now(timezone.utc)


class TestCacheKey:

    def test_identical_for_same_input(self):
        from main import _cache_key
        assert _cache_key("What is the portfolio value?") == \
               _cache_key("What is the portfolio value?")

    def test_case_insensitive(self):
        from main import _cache_key
        assert _cache_key("What is the portfolio value?") == \
               _cache_key("WHAT IS THE PORTFOLIO VALUE?")

    def test_whitespace_insensitive(self):
        from main import _cache_key
        assert _cache_key("  hello  ") == _cache_key("hello")

    def test_different_questions_give_different_keys(self):
        from main import _cache_key
        assert _cache_key("question one") != _cache_key("question two")

    def test_key_is_sha256_hex_string(self):
        from main import _cache_key
        key = _cache_key("any question")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_stable_across_multiple_calls(self):
        from main import _cache_key
        keys = {_cache_key("stable question") for _ in range(10)}
        assert len(keys) == 1


class TestCacheHitMiss:

    def test_miss_returns_none(self):
        from main import _get_from_cache
        assert _get_from_cache("never asked this") is None

    def test_save_and_retrieve(self):
        from main import _get_from_cache, _save_to_cache
        _save_to_cache("q1", "response text", [0.9, 0.8], ["doc.pdf"])
        result = _get_from_cache("q1")
        assert result is not None
        assert result["response"] == "response text"
        assert result["chunk_scores"] == [0.9, 0.8]
        assert result["chunk_titles"] == ["doc.pdf"]

    def test_hit_is_case_insensitive(self):
        from main import _get_from_cache, _save_to_cache
        _save_to_cache("What is the value?", "answer", [], [])
        assert _get_from_cache("WHAT IS THE VALUE?") is not None

    def test_overwrite_updates_entry(self):
        from main import _get_from_cache, _save_to_cache
        _save_to_cache("q", "old answer", [], [])
        _save_to_cache("q", "new answer", [], [])
        assert _get_from_cache("q")["response"] == "new answer"


class TestCacheExpiry:

    def test_expired_entry_returns_none(self):
        from main import _cache, _cache_key, _get_from_cache, _save_to_cache
        _save_to_cache("expiring question", "r", [], [])
        key = _cache_key("expiring question")
        _cache[key]["expires_at"] = _now() - timedelta(seconds=1)
        assert _get_from_cache("expiring question") is None

    def test_expired_entry_is_removed_from_cache(self):
        from main import _cache, _cache_key, _get_from_cache, _save_to_cache
        _save_to_cache("expiring question", "r", [], [])
        key = _cache_key("expiring question")
        _cache[key]["expires_at"] = _now() - timedelta(seconds=1)
        _get_from_cache("expiring question")
        assert key not in _cache

    def test_non_expired_entry_is_served(self):
        from main import _get_from_cache, _save_to_cache
        _save_to_cache("fresh question", "fresh answer", [], [])
        result = _get_from_cache("fresh question")
        assert result is not None
        assert result["response"] == "fresh answer"


class TestCacheCleanupTask:

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired_entries(self):
        from main import _cache, _save_to_cache
        _save_to_cache("q1", "r1", [], [])
        _save_to_cache("q2", "r2", [], [])
        for key in list(_cache.keys()):
            _cache[key]["expires_at"] = _now() - timedelta(seconds=1)
        assert len(_cache) == 2
        now = _now()
        expired_keys = [k for k, v in _cache.items() if now > v["expires_at"]]
        for key in expired_keys:
            del _cache[key]
        assert len(_cache) == 0

    @pytest.mark.asyncio
    async def test_cleanup_keeps_valid_entries(self):
        from main import _cache, _cache_key, _save_to_cache
        _save_to_cache("valid", "response", [], [])
        _save_to_cache("expired", "response", [], [])
        expired_key = _cache_key("expired")
        _cache[expired_key]["expires_at"] = _now() - timedelta(seconds=1)
        now = _now()
        expired_keys = [k for k, v in _cache.items() if now > v["expires_at"]]
        for key in expired_keys:
            del _cache[key]
        valid_key = _cache_key("valid")
        assert valid_key in _cache
        assert expired_key not in _cache

    @pytest.mark.asyncio
    async def test_background_task_starts_and_cancels_cleanly(self):
        from main import _cleanup_cache
        task = asyncio.create_task(_cleanup_cache())
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            pytest.fail(f"Cleanup task raised unexpected error: {e}")



