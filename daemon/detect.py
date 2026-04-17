import psutil
import logging
import os
import yaml
import time

logger = logging.getLogger(__name__)

# --- Config loading ---
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "thresholds.yaml")

def _load_thresholds() -> dict:
    try:
        with open(_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

_thresholds = _load_thresholds()
CRITICAL_THRESHOLD: float = float(_thresholds.get("ram_critical_pct", 85.0))
SLOPE_TRIGGER: float      = float(_thresholds.get("ram_slope_pct_per_tick", 2.0))
WINDOW_TICKS: int         = int(_thresholds.get("rolling_window_ticks", 12))  # 60s @ 5s tick

# --- State ---
# pid -> deque of (timestamp, memory_percent) tuples
_ram_history: dict[int, list[tuple[float, float]]] = {}

# Cascade correlation: track recent trigger timestamps to detect multi-process spikes
_recent_triggers: list[tuple[float, int]] = []  # (timestamp, pid)
CASCADE_WINDOW_SECS: int = int(_thresholds.get("cascade_window_secs", 60))
CASCADE_THRESHOLD: int   = int(_thresholds.get("cascade_trigger_count", 2))


def _cleanup_stale_pids(seen_pids: set[int]) -> None:
    """Remove PIDs from history that are no longer running. Prevents ghost-history memory leak."""
    dead = [pid for pid in _ram_history if pid not in seen_pids]
    for pid in dead:
        del _ram_history[pid]


def is_cascade_event(pid: int) -> bool:
    """
    Returns True if multiple distinct processes have spiked within CASCADE_WINDOW_SECS.
    This signals a system-wide event (e.g., OOM storm, coordinated attack) rather than
    an isolated process fault — and suppresses the kill ladder in favour of escalation.
    """
    now = time.time()
    # Prune old entries
    cutoff = now - CASCADE_WINDOW_SECS
    still_active = [(ts, p) for ts, p in _recent_triggers if ts > cutoff]
    still_active.append((now, pid))
    _recent_triggers.clear()
    _recent_triggers.extend(still_active)

    unique_pids = {p for _, p in _recent_triggers}
    return len(unique_pids) >= CASCADE_THRESHOLD


def detect_anomalies() -> tuple[list[int], list[int]]:
    """
    Stage 1: DETECT
    Monitors a rolling RAM window of WINDOW_TICKS ticks (default 60s at 5s intervals).
    Triggers on steep growth trajectory before a hard crash, not just on an absolute limit.

    Returns:
        (triggered_pids, cascade_pids) — cascade_pids are those caught inside a multi-process
        spike window and should be escalated rather than auto-killed.
    """
    triggered: list[int] = []
    cascade:   list[int] = []
    seen_pids: set[int]  = set()

    for proc in psutil.process_iter(['pid', 'memory_percent']):
        try:
            pid = proc.info['pid']
            mem = proc.info['memory_percent']
            if mem is None:
                continue

            seen_pids.add(pid)

            history = _ram_history.setdefault(pid, [])
            history.append((time.time(), mem))

            # Trim to window size
            if len(history) > WINDOW_TICKS:
                history.pop(0)

            if len(history) < WINDOW_TICKS:
                continue  # Not enough data yet

            oldest_mem = history[0][1]
            newest_mem = history[-1][1]
            slope = (newest_mem - oldest_mem) / WINDOW_TICKS

            triggered_now = (slope > SLOPE_TRIGGER) or (newest_mem > CRITICAL_THRESHOLD)
            if triggered_now:
                history.clear()  # Reset so we don't re-fire immediately
                if is_cascade_event(pid):
                    cascade.append(pid)
                else:
                    triggered.append(pid)

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass  # Process may have died; cleanup sweep below will handle history

    # Fix: actively clean up departed PIDs to prevent unbounded memory growth
    _cleanup_stale_pids(seen_pids)

    return triggered, cascade
