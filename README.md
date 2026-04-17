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

### Stage 1 — DETECT (Trend-Based Pre-Detection & Cascade Correlation)

Ghost-Admin does **not** wait for a crisis. It monitors a 60-second rolling RAM window and triggers at sustained growth rates before hard thresholds are breached.

```python
# Trigger on growth trajectory, not just absolute value
ram_history.append(proc.memory_percent())
if len(ram_history) >= WINDOW_TICKS:
    slope = (ram_history[-1] - ram_history[0]) / WINDOW_TICKS
    if slope > 2.0 or ram_history[-1] > CRITICAL_THRESHOLD:
        trigger_pipeline(proc)
```

**Cascade Correlation Engine (v1.1.0):** If 2+ distinct processes spike within a 60-second window, Ghost-Admin detects an OOM storm or coordinated attack. It suppresses automatic SIGKILLs and escalates the entire cluster to human review. 

---

### Stage 2 — ISOLATE (Whitelist Guardrail)

Before any action, the PID is cross-referenced against your operator whitelist (`config/whitelist.yaml`) and a hardcoded minimum floor (`systemd`, `sshd`, `init`, etc.). If a critical process is targeted, it is bypassed, preventing OS self-destruction.

*The whitelist can be hot-reloaded without daemon restarts via `kill -HUP <pid>`.*

---

### Stage 3 — PROFILE (Behavioral Fingerprinting)

Over 24 hours, background analysis builds a **per-process behavioral baseline** using rolling statistics. Thresholds become dynamic per process signature.

```python
# A nightly ML training job hitting 78% RAM is normal.
# An HTTP server hitting 55% for the first time is not.
if proc_ram > baselines[process_signature].p95 * 1.5:
    trigger_pipeline(proc)
```

Ghost-Admin hot-reloads these baselines every 30 seconds automatically. No two processes are treated the same. 

---

### Stage 4 — EXTRACT (Multi-Signal Context Fusion)

Before querying the AI, Ghost-Admin builds a rich `ProcessContext` object from multiple system signals simultaneously:

```python
context = {
    "ram_percent":        proc.memory_percent(),
    "rss_mb":             mem_info.rss / 1024 / 1024,
    "cpu_percent":        proc.cpu_percent(interval=0.05),
    "open_file_handles":  proc.num_fds(),
    "thread_count":       proc.num_threads(),
    "network_connections":len(proc.connections()),
    "runtime_seconds":    time.time() - proc.create_time(),
    "process_ancestry":   get_process_ancestry(proc.pid),
    "journalctl_tail":    extract_journalctl(proc.pid), # Extracted securely via subprocess
    "historical_context": rag_retrieve(proc.name, context)  # RAG layer
}
```

**Process Lineage Awareness:** If `python3` is the target but its parent is `gunicorn` → `systemd`, the AI calculates intent over the full ancestry tree.
**RAG Memory Layer:** Every past post-mortem is embedded into a FAISS vector index. The daemon retrieves strongly correlated past incidents before querying the SLM.

---

### Stage 5 — REASON (Intent Classification)

Logs and context are piped into a local `llama3.2:3b` model via Ollama (CUDA-accelerated). The AI classifies the situation into 5 intents:

```
WORKING_AS_INTENDED  — behavior consistent with process function
DEGRADED_BUT_FUNCTIONAL — suboptimal but not dangerous
LEAKING              — clear unbounded memory growth pattern
UNDER_ATTACK         — anomalous file/network activity (potential injection)
UNKNOWN              — insufficient data for safe classification
```

The `UNDER_ATTACK` classification makes Ghost-Admin the **first self-healing daemon with rudimentary intrusion detection built in**.

```json
{
  "intent": "LEAKING",
  "confidence": 0.91,
  "action": "kill",
  "start_at_step": 1,
  "reason": "Unbounded heap growth over 8 minutes. No legitimate load spike indicators in logs. Process ancestry is safe to terminate."
}
```

---

### Stage 6 — EXECUTE (Graceful Degradation Ladder)

Ghost-Admin does **not** shoot first. A 4-step escalation ladder executes sequentially inside a **non-blocking daemon thread**, ensuring the core detection loop continues scanning the rest of the OS uninterrupted.

```
Step 1: SIGTERM  ──────── "Please close gracefully"          [wait 10s]
           │
           ▼ (if still running)
Step 2: cgroup memory max ─ Artificial ceiling forces internal OOM
           │
           ▼ (if still running)
Step 3: SIGSTOP  ──────── Freeze, buy time, alert humans     [wait 60s]
           │
           ▼ (if still running)
Step 4: SIGKILL  ──────── Nuclear option, full audit logged
```

**Pre-Kill Forensic Checkpoint:** Before SIGKILL, Ghost-Admin dumps the process memory map to disk via `gcore`. Engineers can dissect the exact memory structure post-mortem.

---

### Stage 7 — AUDIT (SIEM-Ready Splunk/Elastic Logging)

Every daemon action uses Python's `RotatingFileHandler` to push JSONL payloads to `/var/ghost-admin/logs/audit.jsonl` safely.

```json
{
  "timestamp": "2026-04-12T14:23:11Z",
  "daemon_version": "1.1.0",
  "event": "CGROUP_CAP_SUCCESS",
  "pid": 4821,
  "process_name": "data_ingester",
  "process_ancestry": ["python3", "gunicorn", "systemd"],
  "ai_intent": "LEAKING",
  "trigger_type": "SLOPE",
  "escalation_steps_attempted": ["SIGTERM", "cgroup_cap"]
}
```

Ingestible by Splunk, Datadog, Elastic, and satisfies high audit requirements out of the box.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Inference/AI** | Ollama · llama3.2:3b · CUDA (local GPU) |
| **RAG / Memory** | FAISS · sentence-transformers (local) |
| **System Telemetry** | psutil · journalctl |
| **Process Control** | os.kill · subprocess · cgroups v2 |
| **Forensics / SIEM** | gcore · `logging.handlers.RotatingFileHandler` |
| **Environment** | Linux · Python 3.10+ |

---

## Project Structure

```
ghost-admin/
├── daemon/
│   ├── main.py                  # Entry point & daemon loop
│   ├── detect.py                # Pre-detection & Cascade Correlation
│   ├── profile.py               # Hot-reloaded behavioural baselines
│   ├── extract.py               # Telemetry / journalctl fusion
│   ├── reason.py                # Ollama SLM inference interface
│   ├── execute.py               # Threaded graceful degradation ladder
│   └── audit.py                 # SIEM JSONL rotating logger
├── memory/                      # RAG FAISS index embeddings
├── config/
│   ├── whitelist.yaml           # Operator process immune exceptions
│   ├── thresholds.yaml          # Detection math parameters
│   └── daemon.yaml.example      # General service configuration
├── systemd/
│   └── ghost-admin.service      # Hardened systemd unit file
├── tests/                       # Unit tests (Mocked, no root required)
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

# Install dependencies (psutil, pyyaml, requests)
pip install -r requirements.txt

# Configure settings
cp config/daemon.yaml.example config/daemon.yaml
nano config/whitelist.yaml
nano config/thresholds.yaml

# Run tests
pytest tests/

# Start as standard user (test mode)
python daemon/main.py

# Install to systemd for production (requires root/sudo)
sudo cp systemd/ghost-admin.service /etc/systemd/system/
sudo systemctl enable --now ghost-admin
```

---

## Why Local-Only Inference Matters

In Industry 4.0 environments, factory telemetry, process names, and log contents are **proprietary operational data**. Sending them to cloud AI APIs (OpenAI, Gemini, Claude) is a non-starter for:
- Zero-trust security architectures
- Air-gapped production networks with no internet access
- Supply chain security requirements

Ghost-Admin runs 100% on bare metal hardware. **Zero bytes of operational data leave your machine.**

---

## Author

**Aaryan Patwardhan** · [GitHub](https://github.com/Aaryan-Patwardhan) · [LinkedIn](https://linkedin.com/in/aaryan-patwardhan)

Pursuing a B.E. in Information Technology · Savitribai Phule Pune University

> *Ghost-Admin is an architecture-first research project demonstrating production-grade autonomous systems design.*
