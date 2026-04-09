import time
import subprocess
import logging
from audit import log_audit, AuditEvent
import psutil

logger = logging.getLogger(__name__)


def execute_action(proc, intent_result: dict, context: dict):
    """
    Stage 6: EXECUTE (Graceful Degradation Ladder)
    Applies the appropriate action based on the LLM's classification.
    """
    pid = context["pid"]
    pname = context["name"]
    intent = intent_result.get("intent", "UNKNOWN")
    confidence = intent_result.get("confidence", 0.0)
    action = intent_result.get("action", "escalate")
    start_at_step = intent_result.get("start_at_step", 1)
    reason = intent_result.get("reason", "No reason provided")

    ancestry = context.get("process_ancestry", "")
    rag_refs = context.get("historical_context", None)

    if confidence < 0.70 or intent == "UNKNOWN" or action == "escalate":
        logger.warning(f"Escalating PID {pid} to human review (confidence: {confidence}, intent: {intent})")
        log_audit(AuditEvent(
            event="ESCALATED",
            pid=pid,
            process_name=pname,
            intent=intent,
            intent_confidence=confidence,
            action_taken="escalated_to_human",
            reasoning=reason,
            trigger_type="THRESHOLD" if confidence < 0.70 else "UNKNOWN_INTENT",
            process_ancestry=ancestry.split(" -> ") if ancestry else [],
            rag_incidents_referenced=rag_refs,
        ))
        return

    if action == "ignore" or intent in ["WORKING_AS_INTENDED", "DEGRADED_BUT_FUNCTIONAL"]:
        logger.info(f"Ignoring PID {pid} as behavior is safe.")
        log_audit(AuditEvent(
            event="IGNORED",
            pid=pid,
            process_name=pname,
            intent=intent,
            intent_confidence=confidence,
            action_taken="none",
            reasoning=reason,
            process_ancestry=ancestry.split(" -> ") if ancestry else [],
        ))
        return

    # Action is kill / remediate under LEAKING or UNDER_ATTACK
    steps_attempted = []
    log_audit(AuditEvent(
        event="EXECUTION_STARTED",
        pid=pid,
        process_name=pname,
        intent=intent,
        intent_confidence=confidence,
        action_taken="degradation_ladder",
        reasoning=reason,
        trigger_type="SLOPE" if intent == "LEAKING" else "ANOMALY",
        process_ancestry=ancestry.split(" -> ") if ancestry else [],
        rag_incidents_referenced=rag_refs,
    ))

    try:
        if start_at_step <= 1:
            # Step 1: SIGTERM
            logger.info(f"Step 1: Sending SIGTERM to {pid}")
            proc.terminate()
            steps_attempted.append("SIGTERM")
            try:
                proc.wait(timeout=10)
                log_audit(AuditEvent(
                    event="SIGTERM_SUCCESS",
                    pid=pid,
                    process_name=pname,
                    intent=intent,
                    intent_confidence=confidence,
                    action_taken="terminated",
                    reasoning="Process closed gracefully after SIGTERM",
                    process_ancestry=ancestry.split(" -> ") if ancestry else [],
                    escalation_steps_attempted=steps_attempted,
                    rag_incidents_referenced=rag_refs,
                ))
                return
            except psutil.TimeoutExpired:
                pass

        if start_at_step <= 2:
            # Step 2: cgroup memory cap (noted as not yet implemented in this scope)
            logger.info(f"Step 2: cgroup memory cap (stub — not yet implemented)")
            steps_attempted.append("cgroup_cap_stub")

        if start_at_step <= 3:
            # Step 3: SIGSTOP — freeze the process, buy time
            logger.info(f"Step 3: Sending SIGSTOP to freeze {pid}")
            proc.suspend()
            steps_attempted.append("SIGSTOP")
            time.sleep(60)  # Documented 60-second freeze window

        # Pre-Kill forensic memory dump
        dump_path_base = f"/var/ghost-admin/dumps/pre_kill_{pid}_{int(time.time())}"
        logger.info(f"Dumping memory core to {dump_path_base}.core")
        dump_path_final = None
        try:
            subprocess.run(['gcore', '-o', dump_path_base, str(pid)], capture_output=True, check=True)
            dump_path_final = f"{dump_path_base}.core"
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.error(f"Failed to dump memory core (is gcore installed and running as root?): {e}")

        # Step 4: SIGKILL
        logger.warning(f"Step 4: Sending SIGKILL to {pid}")
        proc.kill()
        steps_attempted.append("SIGKILL")

        log_audit(AuditEvent(
            event="SIGKILL_EXECUTED",
            pid=pid,
            process_name=pname,
            intent=intent,
            intent_confidence=confidence,
            action_taken="killed",
            reasoning="Process failed to terminate gracefully — SIGKILL applied",
            process_ancestry=ancestry.split(" -> ") if ancestry else [],
            escalation_steps_attempted=steps_attempted,
            pre_kill_dump=dump_path_final,
            rag_incidents_referenced=rag_refs,
        ))

    except Exception as e:
        logger.error(f"Execution failed on {pid}: {e}")
        log_audit(AuditEvent(
            event="EXECUTION_FAILED",
            pid=pid,
            process_name=pname,
            intent=intent,
            intent_confidence=confidence,
            action_taken="error",
            reasoning=str(e),
            escalation_steps_attempted=steps_attempted,
        ))
