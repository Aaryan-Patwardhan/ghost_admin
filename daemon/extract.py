import psutil
import time
import logging

logger = logging.getLogger(__name__)

def get_process_ancestry(pid: int) -> list:
    """Walks the process tree backwards to get ancestry."""
    ancestry = []
    try:
        proc = psutil.Process(pid)
        while proc.parent():
            proc = proc.parent()
            ancestry.append(proc.name())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return ancestry

def extract_logs(pid: int) -> str:
    """
    Mocks extracting journalctl logs related to the PID.
    In production: subprocess.check_output(['journalctl', f'_PID={pid}', '-n', '50'])
    """
    return "[INFO] Connection established\n[WARN] High memory allocation block requested\n[WARN] Failed to garbage collect..."

def rag_retrieve(proc_name: str, current_context: dict) -> str:
    """
    Mocks looking up via local FAISS against historical incident post-mortems.
    """
    if "python" in proc_name.lower():
        return "Past incident (2 weeks ago): Python process memory leak caused by un-chunked SQLite queries."
    return "No strongly correlated past incidents."

def extract_context(proc) -> dict:
    """
    Stage 4: EXTRACT (Multi-Signal Context Fusion)
    Assembles a JSON context object representing the exact state of the process.
    """
    try:
        num_threads = proc.num_threads()
    except Exception:
        num_threads = 0
        
    try:
        num_fds = proc.num_fds()
    except Exception:
        num_fds = 0

    try:
        conns = len(proc.connections())
    except Exception:
        conns = 0

    try:
        runtime = time.time() - proc.create_time()
    except Exception:
        runtime = 0

    context = {
        "pid": proc.pid,
        "name": proc.name(),
        "ram_percent": round(proc.memory_percent(), 2) if hasattr(proc, 'memory_percent') else 0.0,
        "cpu_percent": round(proc.cpu_percent(interval=0.1), 2) if hasattr(proc, 'cpu_percent') else 0.0,
        "open_file_handles": num_fds,
        "thread_count": num_threads,
        "network_connections": conns,
        "runtime_seconds": round(runtime, 2),
        "process_ancestry": " -> ".join(get_process_ancestry(proc.pid)),
        "journalctl_tail": extract_logs(proc.pid)
    }
    
    # Inject RAG context based on what we extracted
    context["historical_context"] = rag_retrieve(context["name"], context)
    
    return context
