import json
import os
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PROFILE_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "baselines.json")
os.makedirs(os.path.dirname(PROFILE_DB_PATH), exist_ok=True)

@dataclass
class ProcessBaseline:
    p95_ram: float
    avg_threads: int
    avg_fds: int

def load_baselines() -> dict:
    if not os.path.exists(PROFILE_DB_PATH):
        return {}
    with open(PROFILE_DB_PATH, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

# In a real system, a background thread builds this via numpy/rolling stats over 24h.
baselines = load_baselines()

class ProfileViolation(Exception):
    pass

def verify_against_profile(proc) -> bool:
    """
    Stage 3: PROFILE
    Compares the current process stats against its 24-hour behavioral baseline.
    Returns True if it violates the baseline and requires extraction.
    """
    try:
        proc_name = proc.name()
        proc_ram = proc.memory_percent()
        
        if proc_name not in baselines:
            # If we have no baseline, it's anomalous by definition if it breached DETECT
            return True
            
        baseline = baselines[proc_name]
        p95_ram = float(baseline.get("p95_ram", 0.0))
        
        # If RAM exceeds 150% of the normal P95, it's a violation
        if proc_ram > (p95_ram * 1.5):
            return True
            
        return False
    except Exception as e:
        logger.error(f"Profile check error: {e}")
        return True
