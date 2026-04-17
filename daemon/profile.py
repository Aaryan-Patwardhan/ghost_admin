import json
import os
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PROFILE_DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "memory", "baselines.json")
)
os.makedirs(os.path.dirname(PROFILE_DB_PATH), exist_ok=True)

# Multiplier: process RAM must exceed (p95_baseline * VIOLATION_MULTIPLIER) to be flagged
VIOLATION_MULTIPLIER = 1.5

# How many seconds between re-checking whether the baselines file has changed on disk
RELOAD_INTERVAL_SECS = 30.0


@dataclass
class ProcessBaseline:
    p95_ram: float
    avg_threads: int
    avg_fds: int


# --- Module-level state for hot-reload ---
_baselines: dict          = {}
_last_mtime: float        = 0.0
_last_reload_check: float = 0.0


def _load_baselines() -> dict:
    """Read and parse the baselines JSON file from disk."""
    if not os.path.exists(PROFILE_DB_PATH):
        return {}
    try:
        with open(PROFILE_DB_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to load baselines: {e}")
        return {}


def _maybe_reload() -> None:
    """
    Hot-reload baselines if the file has changed since we last read it.
    Uses mtime polling rather than inotify to stay dependency-free.
    Only stat()s the file every RELOAD_INTERVAL_SECS to avoid hammering disk.
    """
    global _baselines, _last_mtime, _last_reload_check
    now = time.monotonic()
    if now - _last_reload_check < RELOAD_INTERVAL_SECS:
        return
    _last_reload_check = now
    try:
        mtime = os.path.getmtime(PROFILE_DB_PATH)
        if mtime != _last_mtime:
            _baselines = _load_baselines()
            _last_mtime = mtime
            logger.info(f"Baselines reloaded from disk ({len(_baselines)} entries).")
    except FileNotFoundError:
        pass  # File doesn't exist yet — will be created by the background profiler


# Initial load at import time
_baselines = _load_baselines()
try:
    _last_mtime = os.path.getmtime(PROFILE_DB_PATH)
except FileNotFoundError:
    _last_mtime = 0.0


class ProfileViolation(Exception):
    pass


def verify_against_profile(proc) -> bool:
    """
    Stage 3: PROFILE
    Compares current process RAM against its 24-hour behavioural baseline.
    Hot-reloads baseline data from disk if the file has been updated since last check.

    Returns True  → process violates its baseline and must proceed to EXTRACT/REASON.
    Returns False → process is within normal bounds; skip the rest of the pipeline.
    """
    _maybe_reload()  # Non-blocking: only hits disk every RELOAD_INTERVAL_SECS

    try:
        proc_name = proc.name()
        proc_ram  = proc.memory_percent()

        if proc_name not in _baselines:
            # No baseline on record → anomalous by definition (already passed DETECT)
            return True

        baseline = _baselines[proc_name]
        p95_ram  = float(baseline.get("p95_ram", 0.0))

        if proc_ram > (p95_ram * VIOLATION_MULTIPLIER):
            logger.debug(
                f"Profile violation: {proc_name} at {proc_ram:.1f}% RAM "
                f"(p95={p95_ram:.1f}%, threshold={p95_ram * VIOLATION_MULTIPLIER:.1f}%)"
            )
            return True

        return False

    except Exception as e:
        logger.error(f"Profile check error: {e}")
        return True  # Fail open — treat unknown state as suspicious
