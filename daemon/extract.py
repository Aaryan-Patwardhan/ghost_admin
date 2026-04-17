import psutil
import subprocess
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


def get_process_ancestry(pid: int) -> list[str]:
    """Walks the process tree backwards to collect the full ancestry chain."""
    ancestry: list[str] = []
    try:
        proc = psutil.Process(pid)
        while True:
            parent = proc.parent()
            if parent is None:
                break
            ancestry.append(parent.name())
            proc = parent
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return ancestry


def extract_journalctl(pid: int, lines: int = 50) -> str:
    """
    Pull the last `lines` log entries for the given PID from journald.
    Falls back to a warning string if journalctl is unavailable (e.g. non-systemd systems).
    """
    try:
        result = subprocess.check_output(
            ["journalctl", f"_PID={pid}", "-n", str(lines), "--no-pager", "-o", "short"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return result.decode("utf-8", errors="replace").strip() or "(no journal entries)"
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "(journalctl unavailable — not a systemd system or insufficient privileges)"


def rag_retrieve(proc_name: str, _context: Optional[dict] = None) -> str:
    """
    Retrieves historically similar incidents from local FAISS memory.
    TODO: wire up actual sentence-transformers + FAISS index stored in memory/rag_index/.
    Currently returns heuristic stubs so call sites always get a non-empty string.
    """
    name = proc_name.lower()
    if "python" in name:
        return "Past incident: Python process memory leak from un-chunked SQLite queries (2w ago)."
    if "java" in name or "jvm" in name:
        return "Past incident: JVM heap growth from unclosed JDBC connections (3w ago)."
    if "node" in name:
        return "Past incident: Node.js event-loop stall from unresolved promise chain (1w ago)."
    return "No strongly correlated past incidents in RAG memory."


def extract_context(proc: psutil.Process) -> dict:
    """
    Stage 4: EXTRACT (Multi-Signal Context Fusion)
    Assembles a fully-fused context object that represents the exact state of the process.
    The LLM receives this dict — it never touches raw metrics directly.
    """
    pid = proc.pid

    try:
        num_threads = proc.num_threads()
    except Exception:
        num_threads = 0

    try:
        num_fds = proc.num_fds()
    except Exception:
        num_fds = 0

    try:
        conns = len(proc.connections(kind="all"))
    except Exception:
        conns = 0

    try:
        runtime = time.time() - proc.create_time()
    except Exception:
        runtime = 0.0

    try:
        ram_percent = round(proc.memory_percent(), 2)
    except Exception:
        ram_percent = 0.0

    try:
        # Non-blocking: sample CPU over a very short window to avoid stalling extract stage
        cpu_percent = round(proc.cpu_percent(interval=0.05), 2)
    except Exception:
        cpu_percent = 0.0

    try:
        mem_info = proc.memory_info()
        rss_mb   = round(mem_info.rss / 1024 / 1024, 2)
        vms_mb   = round(mem_info.vms / 1024 / 1024, 2)
    except Exception:
        rss_mb = vms_mb = 0.0

    ancestry = get_process_ancestry(pid)

    context = {
        "pid":                pid,
        "name":               proc.name(),
        "ram_percent":        ram_percent,
        "rss_mb":             rss_mb,
        "vms_mb":             vms_mb,
        "cpu_percent":        cpu_percent,
        "open_file_handles":  num_fds,
        "thread_count":       num_threads,
        "network_connections": conns,
        "runtime_seconds":    round(runtime, 2),
        "process_ancestry":   " -> ".join(ancestry),
        "journalctl_tail":    extract_journalctl(pid),
    }

    context["historical_context"] = rag_retrieve(context["name"], context)
    return context
