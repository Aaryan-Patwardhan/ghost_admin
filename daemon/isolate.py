import psutil
import logging
import os
import yaml

logger = logging.getLogger(__name__)

_WHITELIST_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "whitelist.yaml")

# Hard minimum — these can NEVER be removed even if whitelist.yaml is empty or missing
_HARDCODED_IMMUNE = {
    'systemd', 'init', 'kthreadd', 'rcu_sched',
    'sshd', 'bash', 'fish', 'zsh',
    'Xorg', 'Xwayland',
    'ghost_admin', 'python3',
    'dbus-daemon', 'dockerd', 'containerd',
}


def _load_whitelist() -> set[str]:
    """Load the operator-configurable whitelist from config/whitelist.yaml."""
    try:
        with open(_WHITELIST_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
            user_list = set(data.get("immune_processes", []))
            return _HARDCODED_IMMUNE | user_list
    except FileNotFoundError:
        logger.warning("whitelist.yaml not found — using hardcoded defaults only.")
        return set(_HARDCODED_IMMUNE)
    except Exception as e:
        logger.error(f"Failed to load whitelist: {e} — using hardcoded defaults.")
        return set(_HARDCODED_IMMUNE)


# Loaded once at import; hot-reloaded on each call via reload_whitelist() if needed
IMMUNE_PROCESSES: set[str] = _load_whitelist()


def reload_whitelist() -> None:
    """Hot-reload the whitelist without restarting the daemon.
    Called by main.py on SIGHUP."""
    global IMMUNE_PROCESSES
    IMMUNE_PROCESSES = _load_whitelist()
    logger.info(f"Whitelist reloaded — {len(IMMUNE_PROCESSES)} immune processes.")


class IsolateException(Exception):
    """Raised when a process is on the whitelist and must be bypassed."""
    pass


def isolate_process(pid: int) -> psutil.Process:
    """
    Stage 2: ISOLATE (Whitelist Guardrail)
    Checks if a given PID is on the whitelist (hardcoded + operator-configurable).
    Raises IsolateException if it is protected.
    Returns the psutil.Process object if safe to proceed.
    """
    try:
        proc = psutil.Process(pid)
        name = proc.name()

        if name in IMMUNE_PROCESSES:
            raise IsolateException(
                f"Process '{name}' (PID {pid}) is immune. Bypassing MAPE-K loop."
            )

        return proc
    except psutil.NoSuchProcess:
        raise IsolateException(f"Process {pid} died before isolation check could complete.")
