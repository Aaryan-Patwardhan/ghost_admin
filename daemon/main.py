import time
import logging
import psutil
import sys
import os

# Ensure the daemon directory is in sys.path so systemd execution works
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from detect import detect_anomalies
from cascade import detect_cascade
from isolate import isolate_process, IsolateException
from profile import verify_against_profile
from extract import extract_context
from reason import classify_intent
from execute import execute_action

logging.basicConfig(level=logging.INFO, format='ghost_admin[%(process)d]: %(message)s')
logger = logging.getLogger("main")

def mape_k_loop():
    """Runs a single pass of the 7-stage closed loop."""
    # Stage 1: DETECT
    anomalous_pids = detect_anomalies()

    # Cascade Correlation — halt individual kills if cluster failure detected
    anomalous_pids = detect_cascade(anomalous_pids)

    for pid in anomalous_pids:
        try:
            # Stage 2: ISOLATE
            proc = isolate_process(pid)
            
            # Stage 3: PROFILE
            if not verify_against_profile(proc):
                continue
                
            logger.warning(f"Anomaly verified for {proc.name()} (PID: {pid}). Extracting context...")
            
            # Stage 4: EXTRACT
            context = extract_context(proc)
            
            # Stage 5: REASON
            intent_result = classify_intent(context)
            
            # Stage 6 & 7: EXECUTE & AUDIT
            execute_action(proc, intent_result, context)
            
        except IsolateException as ie:
            logger.info(str(ie))
        except psutil.NoSuchProcess:
            logger.info(f"PID {pid} died during MAPE-K loop.")
        except Exception as e:
            logger.error(f"Error handling PID {pid}: {e}")

if __name__ == "__main__":
    logger.info("Ghost-Admin Daemon started.")
    try:
        while True:
            mape_k_loop()
            time.sleep(5) # Tick every 5 seconds
    except KeyboardInterrupt:
        logger.info("Ghost-Admin Daemon shutting down.")
