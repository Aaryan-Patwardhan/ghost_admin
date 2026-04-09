import time
import logging
from audit import log_audit, AuditEvent

logger = logging.getLogger(__name__)

# Sliding window: {pid: timestamp_of_trigger}
_cascade_window: dict[int, float] = {}
CASCADE_WINDOW_SECONDS = 60
CASCADE_THRESHOLD = 2  # Distinct PIDs needed to declare a cascade


def detect_cascade(anomalous_pids: list[int]) -> list[int]:
    """
    Cascade Correlation Engine.

    Maintains a 60-second sliding window of triggered PIDs.
    If 2+ *distinct* processes are seen within the window, the entire cluster
    is escalated to human review and NO individual kill decisions are made.

    Returns:
        list[int]: A filtered list of PIDs that are safe to process individually.
                   Returns [] if a cascade is detected — individual action is halted.
    """
    now = time.time()

    # Expire stale entries outside the rolling window
    expired = [pid for pid, ts in _cascade_window.items() if now - ts > CASCADE_WINDOW_SECONDS]
    for pid in expired:
        del _cascade_window[pid]

    # Register newly triggered PIDs into the window
    for pid in anomalous_pids:
        _cascade_window[pid] = now

    active_pids = list(_cascade_window.keys())

    if len(active_pids) >= CASCADE_THRESHOLD:
        logger.critical(
            f"CASCADE DETECTED: {len(active_pids)} distinct processes spiked within "
            f"{CASCADE_WINDOW_SECONDS}s window. PIDs: {active_pids}. "
            "Halting individual kill decisions. Escalating to human review."
        )

        # Emit one structured audit event for the entire cluster
        log_audit(AuditEvent(
            event="CASCADE_DETECTED",
            pid=-1,  # -1 signals a multi-process cluster event
            process_name="[CLUSTER]",
            intent="CASCADE",
            intent_confidence=1.0,
            action_taken="escalated_to_human",
            reasoning=(
                f"{len(active_pids)} distinct processes triggered anomaly detection "
                f"within a {CASCADE_WINDOW_SECONDS}s window. PIDs: {active_pids}. "
                "Individual remediation halted to prevent cascaded process kills."
            ),
            trigger_type="CASCADE",
            escalation_steps_attempted=["none — cascade halt"],
        ))

        # Clear the window after escalation to avoid repeat firing
        _cascade_window.clear()

        # Halt all individual processing for this cycle
        return []

    # No cascade — return incoming PIDs unchanged for normal processing
    return anomalous_pids
