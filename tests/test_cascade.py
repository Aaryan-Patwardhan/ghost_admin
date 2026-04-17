"""Tests for execute.py cascade path and confidence gate."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "daemon"))

from unittest.mock import patch, MagicMock
import execute


def _make_context(pid=5001, name="test_proc"):
    return {
        "pid": pid, "name": name,
        "ram_percent": 70.0, "rss_mb": 512.0, "vms_mb": 1024.0,
        "cpu_percent": 40.0, "open_file_handles": 100,
        "thread_count": 8, "network_connections": 12,
        "runtime_seconds": 3600.0,
        "process_ancestry": "systemd -> init",
        "journalctl_tail": "no journal",
        "historical_context": "no past incidents",
    }


def test_cascade_flag_prevents_kill():
    """cascade=True must emit CASCADE_ESCALATED and never start a thread."""
    execute._active_executions.clear()
    logged = []

    with patch("execute.log_audit", side_effect=lambda e: logged.append(e)), \
         patch("execute.threading.Thread") as mock_thread:

        proc = MagicMock()
        proc.pid = 5001
        intent = {"intent": "LEAKING", "confidence": 0.95, "action": "kill",
                   "reason": "extreme leak"}

        execute.execute_action(proc, intent, _make_context(), cascade=True)

    assert mock_thread.call_count == 0, "No thread should start on cascade event"
    assert any(e.event == "CASCADE_ESCALATED" for e in logged), \
        "CASCADE_ESCALATED audit event must be emitted"


def test_low_confidence_escalates():
    """Confidence below 0.70 must always escalate — never kill."""
    execute._active_executions.clear()
    logged = []

    with patch("execute.log_audit", side_effect=lambda e: logged.append(e)), \
         patch("execute.threading.Thread") as mock_thread:

        proc = MagicMock()
        proc.pid = 5002
        intent = {"intent": "LEAKING", "confidence": 0.55, "action": "kill",
                   "reason": "uncertain"}

        execute.execute_action(proc, intent, _make_context(pid=5002), cascade=False)

    assert mock_thread.call_count == 0
    assert any(e.event == "ESCALATED" for e in logged)


def test_kill_intent_launches_thread():
    """High-confidence LEAKING intent should launch exactly one execution thread."""
    execute._active_executions.clear()
    logged = []
    threads_started = []

    class FakeThread:
        def __init__(self, *a, **kw):
            self.name = kw.get("name", "fake-thread")
        def start(self):
            threads_started.append(self)

    with patch("execute.log_audit", side_effect=lambda e: logged.append(e)), \
         patch("execute.threading.Thread", side_effect=FakeThread):

        proc = MagicMock()
        proc.pid = 5003
        intent = {"intent": "LEAKING", "confidence": 0.92, "action": "kill",
                   "reason": "confirmed leak", "start_at_step": 1}

        execute.execute_action(proc, intent, _make_context(pid=5003), cascade=False)

    assert len(threads_started) == 1, "Exactly one execution thread must be launched"


def test_duplicate_pid_guard():
    """Triggering execute_action on an already-active PID must silently drop."""
    execute._active_executions.clear()
    execute._active_executions.add(6001)
    threads_started = []

    class FakeThread:
        def start(self): threads_started.append(self)

    with patch("execute.log_audit"), \
         patch("execute.threading.Thread", side_effect=FakeThread):

        proc = MagicMock()
        proc.pid = 6001
        intent = {"intent": "LEAKING", "confidence": 0.92, "action": "kill",
                   "reason": "duplicate", "start_at_step": 1}

        execute.execute_action(proc, intent, _make_context(pid=6001), cascade=False)

    assert len(threads_started) == 0, "Second execution on same PID must be dropped"
    execute._active_executions.clear()
