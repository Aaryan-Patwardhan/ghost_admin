import psutil
import subprocess
import logging
import time
import threading
from audit import log_audit, AuditEvent

logger = logging.getLogger(__name__)

# Prevent duplicate executions on the same PID while a thread is already working on it
_active_executions: set[int] = set()
_lock = threading.Lock()


def _run_ladder(proc: psutil.Process, intent_result: dict, context: dict) -> None:
    """
    Internal: Runs the full graceful degradation ladder in a background daemon thread.
    This keeps the detection loop spinning freely while slow operations
    (SIGTERM wait, SIGSTOP freeze, gcore dump) are handled asynchronously.
    """
    pid    = context["pid"]
    pname  = context["name"]
    intent = intent_result.get("intent", "UNKNOWN")
    conf   = intent_result.get("confidence", 0.0)
    action = intent_result.get("action", "escalate")
    start  = intent_result.get("start_at_step", 1)
    reason = intent_result.get("reason", "No reason provided")

    ancestry  = context.get("process_ancestry", "")
    rag_refs  = context.get("historical_context", None)
    anc_list  = ancestry.split(" -> ") if ancestry else []

    steps_attempted: list[str] = []

    log_audit(AuditEvent(
        event="EXECUTION_STARTED",
        pid=pid, process_name=pname,
        intent=intent, intent_confidence=conf,
        action_taken="degradation_ladder", reasoning=reason,
        trigger_type="SLOPE" if intent == "LEAKING" else "ANOMALY",
        process_ancestry=anc_list,
        rag_incidents_referenced=rag_refs,
    ))

    try:
        if start <= 1:
            logger.info(f"[{pid}] Step 1 — SIGTERM")
            proc.terminate()
            steps_attempted.append("SIGTERM")
            try:
                proc.wait(timeout=10)
                log_audit(AuditEvent(
                    event="SIGTERM_SUCCESS",
                    pid=pid, process_name=pname,
                    intent=intent, intent_confidence=conf,
                    action_taken="terminated",
                    reasoning="Process closed gracefully after SIGTERM",
                    process_ancestry=anc_list,
                    escalation_steps_attempted=steps_attempted,
                    rag_incidents_referenced=rag_refs,
                ))
                return
            except psutil.TimeoutExpired:
                logger.warning(f"[{pid}] SIGTERM did not close process within 10s — escalating.")

        if start <= 2:
            # Step 2: cgroup v2 memory hard limit — cap to current RSS to force OOM kill
            logger.info(f"[{pid}] Step 2 — cgroup memory cap")
            steps_attempted.append("cgroup_cap")
            cgroup_path = f"/sys/fs/cgroup/ghost_admin.slice/cgroup.{pid}"
            try:
                rss = proc.memory_info().rss
                # Write memory.max = current RSS so any new allocation triggers OOM within cgroup
                with open(f"{cgroup_path}/memory.max", "w") as f:
                    f.write(str(rss))
                logger.info(f"[{pid}] cgroup memory cap set to {rss} bytes.")
                time.sleep(5)
                # If still running after cap, proceed to SIGSTOP
                if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
                    log_audit(AuditEvent(
                        event="CGROUP_CAP_SUCCESS",
                        pid=pid, process_name=pname,
                        intent=intent, intent_confidence=conf,
                        action_taken="cgroup_oom",
                        reasoning="Process terminated after cgroup memory cap",
                        process_ancestry=anc_list,
                        escalation_steps_attempted=steps_attempted,
                    ))
                    return
            except Exception as e:
                logger.warning(f"[{pid}] cgroup cap failed (running as root?): {e}")

        if start <= 3:
            # Step 3: SIGSTOP — freeze in place, preserve forensic state
            logger.info(f"[{pid}] Step 3 — SIGSTOP (60s freeze)")
            proc.suspend()
            steps_attempted.append("SIGSTOP")
            time.sleep(60)  # 60-second documented freeze window for operator intervention

        # Pre-kill forensic dump (gcore)
        dump_base = f"/var/ghost-admin/dumps/pre_kill_{pid}_{int(time.time())}"
        dump_final = None
        logger.info(f"[{pid}] Pre-kill gcore dump → {dump_base}.core")
        try:
            subprocess.run(
                ["gcore", "-o", dump_base, str(pid)],
                capture_output=True, check=True, timeout=30
            )
            dump_final = f"{dump_base}.core"
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error(f"[{pid}] gcore failed (root + gcore required): {e}")

        # Step 4: SIGKILL — no mercy
        logger.warning(f"[{pid}] Step 4 — SIGKILL")
        proc.kill()
        steps_attempted.append("SIGKILL")

        log_audit(AuditEvent(
            event="SIGKILL_EXECUTED",
            pid=pid, process_name=pname,
            intent=intent, intent_confidence=conf,
            action_taken="killed",
            reasoning="Process failed to terminate gracefully — SIGKILL applied",
            process_ancestry=anc_list,
            escalation_steps_attempted=steps_attempted,
            pre_kill_dump=dump_final,
            rag_incidents_referenced=rag_refs,
        ))

    except psutil.NoSuchProcess:
        logger.info(f"[{pid}] Process self-terminated during degradation ladder.")
        log_audit(AuditEvent(
            event="SELF_TERMINATED",
            pid=pid, process_name=pname,
            intent=intent, intent_confidence=conf,
            action_taken="self_terminated",
            reasoning="Process exited on its own before SIGKILL was reached",
            escalation_steps_attempted=steps_attempted,
        ))
    except Exception as e:
        logger.error(f"[{pid}] Execution thread error: {e}")
        log_audit(AuditEvent(
            event="EXECUTION_FAILED",
            pid=pid, process_name=pname,
            intent=intent, intent_confidence=conf,
            action_taken="error", reasoning=str(e),
            escalation_steps_attempted=steps_attempted,
        ))
    finally:
        with _lock:
            _active_executions.discard(pid)


def execute_action(proc: psutil.Process, intent_result: dict, context: dict,
                   cascade: bool = False) -> None:
    """
    Stage 6: EXECUTE (Graceful Degradation Ladder)
    Non-blocking: launches a daemon thread so the MAPE-K loop keeps scanning
    while slow ladder operations (timeouts, gcore dumps) run in the background.

    The cascade flag (from detect.py cascade correlation) forces escalation
    regardless of the LLM's action recommendation.
    """
    pid      = context["pid"]
    pname    = context["name"]
    intent   = intent_result.get("intent", "UNKNOWN")
    conf     = intent_result.get("confidence", 0.0)
    action   = intent_result.get("action", "escalate")
    reason   = intent_result.get("reason", "No reason provided")
    ancestry = context.get("process_ancestry", "")
    rag_refs = context.get("historical_context", None)
    anc_list = ancestry.split(" -> ") if ancestry else []

    # Guard: skip if already handling this PID
    with _lock:
        if pid in _active_executions:
            logger.info(f"[{pid}] Already under active remediation — skipping duplicate trigger.")
            return
        _active_executions.add(pid)

    # Cascade override — multi-process spike → always escalate to human
    if cascade:
        logger.warning(f"[{pid}] Cascade correlation detected — escalating to human review.")
        log_audit(AuditEvent(
            event="CASCADE_ESCALATED",
            pid=pid, process_name=pname,
            intent=intent, intent_confidence=conf,
            action_taken="escalated_cascade",
            reasoning="Multi-process spike within cascade window — suppressing auto-kill",
            process_ancestry=anc_list,
            cascade_event=True,
        ))
        with _lock:
            _active_executions.discard(pid)
        return

    # Confidence gate / unknown intent → escalate
    if conf < 0.70 or intent == "UNKNOWN" or action == "escalate":
        logger.warning(f"[{pid}] Low-confidence result — escalating (conf={conf:.2f}, intent={intent})")
        log_audit(AuditEvent(
            event="ESCALATED",
            pid=pid, process_name=pname,
            intent=intent, intent_confidence=conf,
            action_taken="escalated_to_human",
            reasoning=reason,
            trigger_type="THRESHOLD" if conf < 0.70 else "UNKNOWN_INTENT",
            process_ancestry=anc_list,
            rag_incidents_referenced=rag_refs,
        ))
        with _lock:
            _active_executions.discard(pid)
        return

    # Safe to ignore
    if action == "ignore" or intent in ["WORKING_AS_INTENDED", "DEGRADED_BUT_FUNCTIONAL"]:
        logger.info(f"[{pid}] Intent classified as safe — no action.")
        log_audit(AuditEvent(
            event="IGNORED",
            pid=pid, process_name=pname,
            intent=intent, intent_confidence=conf,
            action_taken="none", reasoning=reason,
            process_ancestry=anc_list,
        ))
        with _lock:
            _active_executions.discard(pid)
        return

    # Launch degradation ladder in a daemon thread — non-blocking
    t = threading.Thread(
        target=_run_ladder,
        args=(proc, intent_result, context),
        daemon=True,
        name=f"ghost-exec-{pid}",
    )
    t.start()
    logger.info(f"[{pid}] Degradation ladder started in thread '{t.name}'.")
