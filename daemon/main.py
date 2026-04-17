import time
import logging
import signal
import psutil

from detect import detect_anomalies
from isolate import isolate_process, reload_whitelist, IsolateException
from profile import verify_against_profile
from extract import extract_context
from reason import classify_intent
from execute import execute_action
from audit import log_audit, AuditEvent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s ghost_admin[%(process)d] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("main")

TICK_INTERVAL_SECS = 5  # Must match thresholds.yaml tick assumption


def _handle_sigterm(signum, frame):
    """Graceful shutdown on SIGTERM (sent by systemd on `systemctl stop`)."""
    logger.info("SIGTERM received — Ghost-Admin daemon shutting down gracefully.")
    raise SystemExit(0)


def _handle_sighup(signum, frame):
    """Hot-reload config on SIGHUP (sent by `systemctl reload` or `kill -HUP <pid>`)."""
    logger.info("SIGHUP received — reloading whitelist configuration.")
    reload_whitelist()


def mape_k_loop() -> None:
    """Runs a single pass of the full 7-stage MAPE-K closed loop."""

    # Stage 1: DETECT — returns two separate lists
    triggered_pids, cascade_pids = detect_anomalies()

    # Handle cascade-flagged PIDs (multi-process spike) — log + escalate, skip full pipeline
    for pid in cascade_pids:
        try:
            proc = isolate_process(pid)
            context = extract_context(proc)
            intent_result = classify_intent(context)
            # Force cascade=True so execute_action escalates rather than kills
            execute_action(proc, intent_result, context, cascade=True)
        except IsolateException as ie:
            logger.info(str(ie))
        except psutil.NoSuchProcess:
            logger.info(f"[{pid}] Process died before cascade handling.")
        except Exception as e:
            logger.error(f"[{pid}] Cascade handling error: {e}")

    # Handle normally-triggered PIDs through the full MAPE-K pipeline
    for pid in triggered_pids:
        try:
            # Stage 2: ISOLATE
            proc = isolate_process(pid)

            # Stage 3: PROFILE
            if not verify_against_profile(proc):
                logger.debug(f"[{pid}] Within baseline profile — no action.")
                continue

            logger.warning(f"[{pid}] Anomaly confirmed for {proc.name()} — entering EXTRACT.")

            # Stage 4: EXTRACT
            context = extract_context(proc)

            # Stage 5: REASON
            intent_result = classify_intent(context)

            # Stage 6 + 7: EXECUTE (non-blocking thread) + AUDIT (inside execute)
            execute_action(proc, intent_result, context, cascade=False)

        except IsolateException as ie:
            logger.info(str(ie))
        except psutil.NoSuchProcess:
            logger.info(f"[{pid}] Process died during MAPE-K loop — skipping.")
        except Exception as e:
            logger.error(f"[{pid}] Unhandled error in MAPE-K loop: {e}")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGHUP, _handle_sighup)

    logger.info("Ghost-Admin Daemon v1.1.0 started.")
    log_audit(AuditEvent(
        event="DAEMON_STARTED",
        pid=0,
        process_name="ghost_admin",
        intent="N/A",
        intent_confidence=1.0,
        action_taken="startup",
        reasoning="Daemon initialised successfully.",
    ))

    try:
        while True:
            mape_k_loop()
            time.sleep(TICK_INTERVAL_SECS)
    except SystemExit:
        pass
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — Ghost-Admin Daemon shutting down.")
    finally:
        log_audit(AuditEvent(
            event="DAEMON_STOPPED",
            pid=0,
            process_name="ghost_admin",
            intent="N/A",
            intent_confidence=1.0,
            action_taken="shutdown",
            reasoning="Clean daemon exit.",
        ))
