import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
import os

AUDIT_LOG_FILE = "/var/ghost-admin/logs/audit.jsonl"
DAEMON_VERSION = "1.0.0"

# Create log directory if it doesn't exist (assuming /var/ghost-admin is writable by daemon)
try:
    os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)
except PermissionError:
    # Fallback to local logs directory during dev/testing
    AUDIT_LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "audit.jsonl")
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
    trigger_type: Optional[str] = None
    process_ancestry: Optional[list] = field(default=None)
    escalation_steps_attempted: Optional[list] = field(default=None)
    pre_kill_dump: Optional[str] = None
    rag_incidents_referenced: Optional[str] = None
    post_mortem: Optional[str] = None

    # Injected at log time
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    daemon_version: str = DAEMON_VERSION

    def to_jsonl(self) -> str:
        """Serialises the event, dropping None fields for clean output."""
        d = asdict(self)
        d = {k: v for k, v in d.items() if v is not None}
        return json.dumps(d)


class GhostAuditLogger:
    def __init__(self):
        self.logger = logging.getLogger("ghost_admin_audit")
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            handler = logging.FileHandler(AUDIT_LOG_FILE)
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)

    def write(self, event: AuditEvent):
        self.logger.info(event.to_jsonl())


# Global instance
_audit_logger = GhostAuditLogger()


def log_audit(event: AuditEvent):
    """
    Stage 7: Writes a SIEM-compliant JSONL log entry.
    Accepts a fully-formed AuditEvent dataclass.
    """
    _audit_logger.write(event)
