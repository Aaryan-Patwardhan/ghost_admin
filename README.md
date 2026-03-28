# Ghost-Admin

> **An autonomous, air-gapped Linux daemon that heals servers through semantic reasoning — not blind thresholds.**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square)](https://python.org)
[![CUDA](https://img.shields.io/badge/CUDA-Enabled-green?style=flat-square)](https://developer.nvidia.com/cuda-toolkit)
[![Ollama](https://img.shields.io/badge/Inference-Ollama-orange?style=flat-square)](https://ollama.ai)
[![License](https://img.shields.io/badge/License-MIT-purple?style=flat-square)](LICENSE)
[![Zero Cloud](https://img.shields.io/badge/Cloud%20API%20Calls-Zero-red?style=flat-square)]()

---

## The Problem

Every serious production environment runs some version of the same lie: "our monitoring will catch it."

Kubernetes liveness probes kill processes when RAM hits a threshold. Nagios fires alerts into Slack channels that engineers silence at 3AM. Static bash scripts restart services regardless of whether they were in the middle of a critical database transaction.

These tools are **syntactic**. They read numbers. They do not reason.

The result:
- **$1.4 trillion** in unplanned downtime losses annually across Fortune 500 companies
- **$2.3 million per hour** in idle automotive production lines
- **$9,000 per minute** average cost for large enterprise outages
- **25 unplanned incidents per month** in the average industrial plant

The problem isn't that servers crash. It's that the tools watching them are blind to *why*.

---

## What Ghost-Admin Does Differently

Ghost-Admin is the **first air-gapped, semantically-aware server healing daemon** that classifies process *intent* — not just resource state.

| Capability | Ghost-Admin | Kubernetes Probes | Nagios/Zabbix |
|---|:---:|:---:|:---:|
| Semantic log reasoning | ✅ | ❌ | ❌ |
| Pre-kill forensic memory dump | ✅ | ❌ | ❌ |
| RAG over incident history | ✅ | ❌ | ❌ |
| Process lineage awareness | ✅ | ❌ | ❌ |
| Trend-based pre-detection | ✅ | ❌ | Partial |
| Graceful degradation ladder (4-step) | ✅ | Partial | ❌ |
| Per-process behavioral fingerprinting | ✅ | ❌ | ❌ |
| Cascade correlation engine | ✅ | ❌ | ❌ |
| Intent classification (LEAKING / UNDER_ATTACK) | ✅ | ❌ | ❌ |
| JSONL compliance audit log (SIEM-ready) | ✅ | ❌ | Partial |
| Air-gapped / zero cloud inference | ✅ | ❌ | ✅ |

---

## Architecture

Ghost-Admin operates on a strict **7-stage MAPE-K closed-loop**:

```
┌─────────────────────────────────────────────────────────────────┐
│                        GHOST-ADMIN DAEMON                       │
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────────┐  │
│  │  DETECT  │──▶│ ISOLATE  │──▶│ PROFILE  │──▶│  EXTRACT   │  │
│  │ (Trend)  │   │(Whitelist│   │(Baseline)│   │   (Logs)   │  │
│  └──────────┘   └──────────┘   └──────────┘   └────────────┘  │
│                                                        │        │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐           │        │
│  │  AUDIT   │◀──│ EXECUTE  │◀──│  REASON  │◀──────────┘        │
│  │ (JSONL)  │   │(Ladder)  │   │(Local AI)│                    │
│  └──────────┘   └──────────┘   └──────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

### Stage 1 — DETECT (Trend-Based Pre-Detection)

Ghost-Admin does **not** wait for a crisis. It monitors a 60-second rolling RAM window and triggers at sustained growth rates before hard thresholds are breached.

```python
# Trigger on growth trajectory, not just absolute value
ram_history.append(psutil.virtual_memory().percent)
if len(ram_history) >= 12:  # 60s at 5s polling
    slope = (ram_history[-1] - ram_history[-12]) / 12
    if slope > 2.0 or ram_history[-1] > CRITICAL_THRESHOLD:
        trigger_pipeline(proc)
```

This fires at **60% RAM climbing fast** — not 85% RAM already in crisis.

---

### Stage 2 — ISOLATE (Whitelist Guardrail)

Before any action, the PID is cross-referenced against a hardcoded system whitelist. `systemd`, `fish`, `Xorg`, `sshd`, and other critical processes are entirely immune. This prevents OS self-destruction.

---

### Stage 3 — PROFILE (Behavioral Fingerprinting)

Over 24 hours, Ghost-Admin builds a **per-process behavioral baseline** using rolling P95 RAM statistics. Thresholds become dynamic per process signature:

```python
# A nightly ML training job hitting 78% RAM is normal.
# An HTTP server hitting 55% for the first time is not.
if proc_ram > baselines[process_signature].p95 * 1.5:
    trigger_pipeline(proc)
```

No two processes are treated the same. Ghost-Admin learns your environment's *normal*.

---

### Stage 4 — EXTRACT (Multi-Signal Context Fusion)

Before querying the AI, Ghost-Admin builds a rich `ProcessContext` object from multiple system signals simultaneously:

```python
context = {
    "ram_percent":        proc.memory_percent(),
    "cpu_percent":        proc.cpu_percent(interval=1),
    "open_file_handles":  len(proc.open_files()),
    "thread_count":       proc.num_threads(),
    "network_connections":len(proc.connections()),
    "runtime_seconds":    time.time() - proc.create_time(),
    "process_ancestry":   get_process_ancestry(proc.pid),
    "journalctl_tail":    extract_logs(proc.pid),
    "historical_context": rag_retrieve(proc.name, context)  # RAG layer
}
```

**Process Lineage Awareness:** Ghost-Admin walks the full process tree before any kill decision. If `python3` is the target but its parent is `gunicorn` → `systemd`, the AI is informed of the full ancestry — and can choose to terminate the orchestrator instead of triggering an infinite respawn loop.

**RAG Memory Layer:** Every past incident post-mortem is embedded into a local FAISS vector index. Before querying the SLM, Ghost-Admin retrieves the 2 most semantically similar past incidents and injects them as context. The daemon gets smarter with every event it handles.

---

### Stage 5 — REASON (Intent Classification)

Logs and context are piped into a local `llama3.2:3b` model running via Ollama (CUDA-accelerated). The AI classifies the situation across **5 intent categories**:

```
WORKING_AS_INTENDED  — behavior consistent with process function
DEGRADED_BUT_FUNCTIONAL — suboptimal but not dangerous
LEAKING              — clear unbounded memory growth pattern
UNDER_ATTACK         — anomalous file/network activity (potential injection)
UNKNOWN              — insufficient data for safe classification
```

The `UNDER_ATTACK` classification makes Ghost-Admin the **first self-healing daemon with rudimentary intrusion detection built in** — because a process suddenly opening 200 file handles it has never accessed before is not a RAM problem, it's a security problem.

The AI returns a strict JSON response:

```json
{
  "intent": "LEAKING",
  "confidence": 0.91,
  "action": "kill",
  "start_at_step": 1,
  "reason": "Unbounded heap growth over 8 minutes. No legitimate load spike indicators in logs. Process ancestry is safe to terminate."
}
```

If `confidence < 0.70` or `intent == "UNKNOWN"`, the action is automatically escalated rather than executed.

---

### Stage 6 — EXECUTE (Graceful Degradation Ladder)

Ghost-Admin does **not** shoot first. A 4-step escalation ladder with configurable wait windows ensures the minimum necessary force is used:

```
Step 1: SIGTERM  ──────── "Please close gracefully"          [wait 10s]
           │
           ▼ (if still running)
Step 2: cgroup memory cap ─ Artificially ceiling the process  [wait 30s]
           │
           ▼ (if still running)
Step 3: SIGSTOP  ──────── Freeze, buy time, alert humans     [wait 60s]
           │
           ▼ (if still running)
Step 4: SIGKILL  ──────── Nuclear option, full audit logged
```

**Pre-Kill Forensic Checkpoint:** Before any SIGKILL, Ghost-Admin dumps the process memory map to disk via `gcore`. Engineers can perform post-mortem analysis on *why* the leak occurred — not just *that* it did.

```bash
gcore -o /var/ghost-admin/dumps/pre_kill_{pid}_{timestamp} {pid}
```

**Cascade Correlation:** If 2+ processes spike within a 60-second window, Ghost-Admin detects a potential cascade failure, halts individual kill decisions, and escalates the entire event cluster to human review. A cascade is handled as a single incident, not multiple unrelated ones.

---

### Stage 7 — AUDIT (Compliance-Ready JSONL Log)

Every single daemon action — including non-events — is written to an append-only JSONL audit log:

```json
{
  "timestamp": "2025-03-29T14:23:11Z",
  "daemon_version": "1.0.0",
  "event": "SIGKILL_EXECUTED",
  "pid": 4821,
  "process_name": "data_ingester",
  "process_ancestry": ["python3", "gunicorn", "systemd"],
  "ram_at_trigger": 91.2,
  "trigger_type": "THRESHOLD",
  "ai_intent": "LEAKING",
  "ai_confidence": 0.91,
  "escalation_steps_attempted": ["SIGTERM", "cgroup_cap", "SIGSTOP"],
  "pre_kill_dump": "/var/ghost-admin/dumps/4821_1743259391.core",
  "rag_incidents_referenced": ["incident_2025-03-12_nginx", "incident_2025-02-28_python3"],
  "post_mortem": "/var/ghost-admin/reports/2025-03-29_4821.md"
}
```

This output is directly ingestible by SIEM systems (Splunk, Elastic, Wazuh) and satisfies audit requirements in manufacturing, healthcare, and financial environments.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Inference** | Ollama · llama3.2:3b · CUDA (local GPU) |
| **RAG / Memory** | FAISS · sentence-transformers (local) |
| **System Telemetry** | psutil · journalctl · /proc |
| **Process Control** | os.kill · subprocess · cgroups v2 |
| **Forensics** | gcore (GNU Core Utilities) |
| **Audit** | JSONL append-only log · Markdown post-mortems |
| **Environment** | Garuda Linux (Arch-based) · Python 3.10+ |
| **Hardware Target** | NVIDIA RTX 3050 Ti (4GB VRAM) · 16GB RAM |

---

## Project Structure

```
ghost-admin/
├── daemon/
│   ├── main.py                  # Entry point & daemon loop
│   ├── detect.py                # Trend-based pre-detection
│   ├── profile.py               # Behavioral fingerprinting & baselines
│   ├── extract.py               # Multi-signal context fusion & log extraction
│   ├── reason.py                # Ollama AI interface & intent classification
│   ├── execute.py               # Graceful degradation ladder & SIGKILL
│   └── audit.py                 # JSONL logger & post-mortem writer
├── memory/
│   ├── rag.py                   # FAISS vector index & retrieval
│   ├── embedder.py              # sentence-transformers local embeddings
│   └── index/                   # Persisted FAISS index (gitignored)
├── config/
│   ├── whitelist.yaml           # Critical process whitelist
│   ├── thresholds.yaml          # Per-process baseline overrides
│   └── daemon.yaml              # Global daemon configuration
├── reports/                     # Markdown post-mortem output directory
├── dumps/                       # Pre-kill gcore memory dumps (gitignored)
├── logs/
│   └── audit.jsonl              # Append-only SIEM-ready audit log
├── tests/
│   ├── test_detect.py
│   ├── test_reason.py
│   └── test_cascade.py
├── systemd/
│   └── ghost-admin.service      # systemd unit file for daemon install
└── README.md
```

---

## Installation

```bash
# Clone
git clone https://github.com/Aaryan-Patwardhan/ghost-admin
cd ghost-admin

# Create virtualenv
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install psutil requests faiss-cpu sentence-transformers pyyaml

# Ensure Ollama is running with llama3.2:3b
ollama pull llama3.2:3b

# Configure
cp config/daemon.yaml.example config/daemon.yaml
# Edit whitelist.yaml with your critical process names

# Run
python daemon/main.py

# Or install as systemd service
sudo cp systemd/ghost-admin.service /etc/systemd/system/
sudo systemctl enable --now ghost-admin
```

---

## Configuration

```yaml
# config/daemon.yaml
inference:
  endpoint: "http://localhost:11434/api/generate"
  model: "llama3.2:3b"
  confidence_threshold: 0.70     # Below this → escalate, never kill

monitoring:
  poll_interval_seconds: 5
  ram_hard_threshold: 85.0        # Absolute ceiling fallback
  trend_window_seconds: 60        # Rolling window for slope detection
  trend_slope_threshold: 2.0      # % per poll = early trigger
  cascade_window_seconds: 60      # Multi-process correlation window

execution:
  sigterm_wait_seconds: 10
  cgroup_cap_wait_seconds: 30
  sigstop_wait_seconds: 60
  forensic_dump_enabled: true
  dump_directory: "/var/ghost-admin/dumps"

audit:
  log_path: "/var/ghost-admin/logs/audit.jsonl"
  report_directory: "/var/ghost-admin/reports"
```

---

## Results (Design Targets)

| Metric | Baseline (Manual) | Ghost-Admin Target |
|---|---|---|
| Mean time to detection | ~15 minutes (on-call) | < 30 seconds |
| False positive kill rate | N/A | < 5% (confidence gate) |
| Cloud API calls per incident | 0 (air-gapped) | 0 |
| Audit trail completeness | Manual notes | 100% automated JSONL |
| Post-mortem forensic data | None | Full gcore dump + Markdown |

---

## Roadmap

- [ ] Web dashboard (FastAPI + HTMX) for audit log visualization
- [ ] Telegram/Slack escalation webhook for human-in-the-loop alerts  
- [ ] Prometheus metrics exporter (Grafana-compatible)
- [ ] Multi-node support (SSH-based remote healing)
- [ ] Model hot-swap (qwen2.5:3b as fallback when llama3.2 is busy)
- [ ] Docker container process healing support

---

## Why Local-Only Inference Matters

In Industry 4.0 environments, factory telemetry, process names, and log contents are **proprietary operational data**. Sending them to cloud AI APIs (OpenAI, Gemini, Claude) is a non-starter for:
- Zero-trust security architectures
- GDPR / data residency compliance  
- Air-gapped production networks with no internet access
- Supply chain security requirements

Ghost-Admin's entire inference stack runs on your hardware. **Zero bytes of operational data leave your machine.**

---

## Author

**Aaryan Patwardhan** · [GitHub](https://github.com/Aaryan-Patwardhan) · [LinkedIn](https://linkedin.com/in/aaryan-patwardhan)

B.E. Information Technology · Savitribai Phule Pune University · 2027

> *Ghost-Admin is an architecture-first research project demonstrating production-grade autonomous systems design.*

---

*Built on Garuda Linux. Runs on bare metal. Costs $0 to operate.*
