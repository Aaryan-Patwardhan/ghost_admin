"""Tests for Stage 1: DETECT — rolling window and cascade correlation logic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "daemon"))

from unittest.mock import patch, MagicMock
import detect


def _make_proc(pid: int, mem: float):
    """Helper: mock psutil process_iter entry."""
    p = MagicMock()
    p.info = {"pid": pid, "memory_percent": mem}
    return p


def _fill_history(pid: int, values: list[float]):
    detect._ram_history[pid] = [(i * 5.0, v) for i, v in enumerate(values)]


def test_no_trigger_on_flat_memory():
    """A process with stable RAM below threshold should never trigger."""
    detect._ram_history.clear()
    flat = [20.0] * detect.WINDOW_TICKS

    with patch("detect.psutil.process_iter", return_value=[_make_proc(1001, 20.0)]):
        _fill_history(1001, flat)
        triggered, cascade = detect.detect_anomalies()

    assert 1001 not in triggered and 1001 not in cascade


def test_trigger_on_steep_slope():
    """A process whose RAM climbs steeply should appear in triggered list."""
    detect._ram_history.clear()
    # Simulate climbing memory: 20% → 44% over WINDOW_TICKS ticks (slope = 2% / tick)
    rising = [20.0 + i * 2.1 for i in range(detect.WINDOW_TICKS)]

    with patch("detect.psutil.process_iter", return_value=[_make_proc(2001, rising[-1])]):
        _fill_history(2001, rising)
        triggered, cascade = detect.detect_anomalies()

    assert 2001 in triggered


def test_trigger_on_critical_threshold():
    """A process above CRITICAL_THRESHOLD should always trigger."""
    detect._ram_history.clear()
    above = [detect.CRITICAL_THRESHOLD + 1.0] * detect.WINDOW_TICKS

    with patch("detect.psutil.process_iter", return_value=[_make_proc(3001, above[-1])]):
        _fill_history(3001, above)
        triggered, cascade = detect.detect_anomalies()

    assert 3001 in triggered


def test_stale_pid_cleanup():
    """PIDs no longer in process list should be pruned from _ram_history."""
    detect._ram_history.clear()
    detect._ram_history[9999] = [(0.0, 30.0)]

    with patch("detect.psutil.process_iter", return_value=[]):
        detect.detect_anomalies()

    assert 9999 not in detect._ram_history, "Stale PID should have been cleaned up"


def test_cascade_detection():
    """Two distinct PIDs spiking within the window should produce cascade entries."""
    detect._ram_history.clear()
    detect._recent_triggers.clear()

    rising = [20.0 + i * 2.5 for i in range(detect.WINDOW_TICKS)]
    procs = [_make_proc(4001, rising[-1]), _make_proc(4002, rising[-1])]

    with patch("detect.psutil.process_iter", return_value=procs):
        _fill_history(4001, rising)
        _fill_history(4002, rising)
        triggered, cascade = detect.detect_anomalies()

    # At least one of them should hit cascade (both spiked together)
    total = len(triggered) + len(cascade)
    assert total >= 2, f"Expected 2 triggers (triggered + cascade), got {total}"
