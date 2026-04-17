import json
import logging
import logging.handlers
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
import os

DAEMON_VERSION = "1.1.0"

# Prefer the system path; fallback to repo-local logs/ during dev/test
_SYSTEM_LOG = "/var/ghost-admin/logs/audit.jsonl"
try:
    os.makedirs(os.path.dirname(_SYSTEM_LOG), exist_ok=True)
    AUDIT_LOG_FILE = _SYSTEM_LOG
except PermissionError:
    AUDIT_LOG_FILE = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "logs", "audit.jsonl")
    )
    os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)


@dataclass
class AuditEvent:
    """
    Structured audit log entry matching the README JSONL schema.
    All fields beyond the core set are Optional — call sites only populate
    what is available for that specific event type.
    """
    # Core (always required)
    event: str
    pid: int
    process_name: str
    intent: str
    intent_confidence: float
    action_taken: str
    reasoning: str

    # Rich context (optional — populated by execute.py when available)
    trigger_type: Optional[str]              = None
    process_ancestry: Optional[list]         = field(default=None)
    escalation_steps_attempted: Optional[list] = field(default=None)
    pre_kill_dump: Optional[str]             = None
    rag_incidents_referenced: Optional[str]  = None
    post_mortem: Optional[str]               = None
    cascade_event: Optional[bool]            = None  # NEW: marks cascade-flagged escalations

    # Injected at log time
    timestamp: str        = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    daemon_version: str   = DAEMON_VERSION

    def to_jsonl(self) -> str:
        """Serialises the event, dropping None fields for clean SIEM-ingestible output."""
        d = asdict(self)
        d = {k: v for k, v in d.items() if v is not None}
        return json.dumps(d)


class GhostAuditLogger:
    """
    Thread-safe, rotating audit logger.
    Writes SIEM-ready JSONL lines.  Rolls over at 10 MB, keeping 5 backups.
    Backups: audit.jsonl.1 … audit.jsonl.5
    """
    def __init__(self):
        self.logger = logging.getLogger("ghost_admin_audit")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False  # Don't bubble up to root logger

        if not self.logger.handlers:
            handler = logging.handlers.RotatingFileHandler(
                AUDIT_LOG_FILE,
                maxBytes=10 * 1024 * 1024,   # 10 MB per file
                backupCount=5,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)

    def write(self, event: AuditEvent) -> None:
        self.logger.info(event.to_jsonl())


# Module-level singleton — safe across threads because RotatingFileHandler uses a lock
_audit_logger = GhostAuditLogger()


def log_audit(event: AuditEvent) -> None:
    """
    Stage 7: Writes a SIEM-compliant JSONL log entry.
    Accepts a fully-formed AuditEvent dataclass.
    Thread-safe: can be called from execute threads concurrently.
    """
    _audit_logger.write(event)
