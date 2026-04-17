"""Tests for Stage 5: REASON — LLM intent classification and fail-safe behaviour."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "daemon"))

import json
from unittest.mock import patch, MagicMock
import reason


def _fake_ollama_response(payload: dict):
    """Builds a mock requests.Response that returns the given payload as Ollama would."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"response": json.dumps(payload)}
    return mock_resp


_SAMPLE_CONTEXT = {
    "pid": 7001, "name": "python3",
    "ram_percent": 78.0, "rss_mb": 600.0, "vms_mb": 1200.0,
    "cpu_percent": 30.0, "open_file_handles": 50, "thread_count": 4,
    "network_connections": 3, "runtime_seconds": 7200.0,
    "process_ancestry": "systemd -> gunicorn",
    "journalctl_tail": "WARN: memory allocation failed",
    "historical_context": "Past incident: Python memory leak (2w ago)",
}


def test_valid_llm_response_is_returned():
    """A well-formed LLM response must be passed through unchanged."""
    expected = {
        "intent": "LEAKING",
        "confidence": 0.88,
        "action": "kill",
        "start_at_step": 1,
        "reason": "Sustained unbounded RAM growth without CPU activity is a classic leak.",
    }

    with patch("reason.requests.post", return_value=_fake_ollama_response(expected)):
        result = reason.classify_intent(_SAMPLE_CONTEXT)

    assert result["intent"] == "LEAKING"
    assert result["confidence"] == 0.88
    assert result["action"] == "kill"


def test_missing_schema_fields_trigger_failsafe():
    """An LLM response missing required fields must return the UNKNOWN fail-safe dict."""
    bad_payload = {"some_random_key": "garbage"}

    with patch("reason.requests.post", return_value=_fake_ollama_response(bad_payload)):
        result = reason.classify_intent(_SAMPLE_CONTEXT)

    assert result["intent"] == "UNKNOWN"
    assert result["confidence"] == 0.0
    assert result["action"] == "escalate"


def test_network_error_returns_failsafe():
    """A network failure to Ollama must return the UNKNOWN fail-safe dict."""
    with patch("reason.requests.post", side_effect=ConnectionError("Ollama unreachable")):
        result = reason.classify_intent(_SAMPLE_CONTEXT)

    assert result["intent"] == "UNKNOWN"
    assert result["action"] == "escalate"
    assert "Inference failed" in result["reason"]


def test_timeout_returns_failsafe():
    """An Ollama timeout must return the UNKNOWN fail-safe dict."""
    import requests as req
    with patch("reason.requests.post", side_effect=req.exceptions.Timeout):
        result = reason.classify_intent(_SAMPLE_CONTEXT)

    assert result["intent"] == "UNKNOWN"
    assert result["action"] == "escalate"
