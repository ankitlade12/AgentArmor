import json
import uuid
import os
import logging
from datetime import datetime, timezone
from ..hooks import ResponseContext

class RecorderModule:
    def __init__(self, storage: str = "local", path: str = ".agentarmor/sessions"):
        """
        Initializes the session recorder.
        
        Args:
            storage: Defines where logs shouldn be saved ('local' or 'logging').
            path: Directory path for local storage.
        """
        self.storage = storage

        self.path = path
        self.session_id = str(uuid.uuid4())[:8]
        self.events = []
        if self.storage == "local":
            os.makedirs(path, exist_ok=True)
            # The log holds full, unredacted prompts/outputs — keep it owner-only.
            try:
                os.chmod(path, 0o700)
            except OSError:
                pass
            self.filepath = os.path.join(self.path, f"session_{self.session_id}.jsonl")
        else:
            self.logger = logging.getLogger("agentarmor.recorder")
            self.logger.setLevel(logging.INFO)

    def post_record(self, ctx: ResponseContext) -> ResponseContext:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": ctx.provider,
            "model": ctx.model,
            "input": ctx.request.messages,
            "output": ctx.text,
            "cost": ctx.cost,
            "latency_ms": round(ctx.latency_ms, 2) if ctx.latency_ms else None,
        }
        self.events.append(event)
        
        if self.storage == "local":
            self._flush_local(event)
        elif self.storage == "logging":
            self.logger.info(json.dumps(event))
            
        return ctx

    def _flush_local(self, event: dict):
        # Create owner-only (0600) — the file contains unredacted prompt data.
        fd = os.open(self.filepath, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(event) + "\n")

    def report(self) -> dict:
        return {
            "session_id": self.session_id,
            "events": len(self.events),
            "storage": self.storage,
            **({"path": self.filepath} if self.storage == "local" else {})
        }
