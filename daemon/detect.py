import psutil
import logging

logger = logging.getLogger(__name__)

# rolling memory history: pid -> list of memory percents
ram_history = {}
CRITICAL_THRESHOLD = 85.0

def detect_anomalies() -> list[int]:
    """
    Stage 1: DETECT
    Monitors 60-second rolling RAM windows (assumes 5s polling interval = 12 ticks).
    Triggers on steep growth trajectory before a hard crash.
    """
    triggered_pids = []
    
    for proc in psutil.process_iter(['pid', 'memory_percent']):
        try:
            pid = proc.info['pid']
            mem = proc.info['memory_percent']
            if mem is None:
                continue
                
            if pid not in ram_history:
                ram_history[pid] = []
            
            ram_history[pid].append(mem)
            
            # Keep last 12 data points (60 seconds at 5s tick)
            if len(ram_history[pid]) > 12:
                ram_history[pid].pop(0)
                
            # If we have a full 60 seconds of history
            if len(ram_history[pid]) == 12:
                # Calculate slope from 60 seconds ago compared to now
                slope = (ram_history[pid][-1] - ram_history[pid][0]) / 12
                
                # If memory is climbing at >2% per interval OR we hit the critical absolute threshold
                if slope > 2.0 or ram_history[pid][-1] > CRITICAL_THRESHOLD:
                    triggered_pids.append(pid)
                    # Clear history so we don't trigger again immediately in the same cycle
                    ram_history[pid].clear()
                    
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            if pid in ram_history:
                del ram_history[pid]
                
    return triggered_pids
