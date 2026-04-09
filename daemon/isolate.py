import psutil
import logging

logger = logging.getLogger(__name__)

# Hardcoded whitelist of critical OS components that MUST NEVER be touched
IMMUNE_PROCESSES = {
    'systemd', 'init', 'kthreadd', 'rcu_sched', 'sshd', 
    'bash', 'fish', 'Xorg', 'ghost_admin', 
    'dbus-daemon', 'dockerd', 'containerd'
}

class IsolateException(Exception):
    """Raised when a process is protected by the guardrails and should be bypassed."""
    pass

def isolate_process(pid: int) -> psutil.Process:
    """
    Stage 2: ISOLATE (Whitelist Guardrail)
    Checks if a given PID is on the whitelist.
    Raises IsolateException if it is protected.
    Returns the psutil.Process object if safe to proceed.
    """
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        
        if name in IMMUNE_PROCESSES:
            raise IsolateException(f"Process {name} (PID {pid}) is immune. Bypassing MAPE-K loop.")
            
        return proc
    except psutil.NoSuchProcess:
        raise IsolateException(f"Process {pid} died before isolation check could complete.")
