import json
import uuid
import os
from datetime import datetime, timezone

class RecorderModule:
    def __init__(self, storage="local", path=".agentarmor/sessions"):
        self.storage = storage
        self.path = path
        self.session_id = str(uuid.uuid4())[:8]
        self.events = []
        os.makedirs(path, exist_ok=True)

    def log(self, provider, model, input_messages, output, latency_ms):
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "model": model,
            "input": input_messages,
            "output": output,
            "latency_ms": round(latency_ms, 2),
        }
        self.events.append(event)
        self._flush()

    def _flush(self):
        filepath = os.path.join(self.path, f"session_{self.session_id}.jsonl")
        with open(filepath, "a") as f:
            f.write(json.dumps(self.events[-1]) + "\n")

    def report(self):
        return {
            "session_id": self.session_id,
            "events": len(self.events),
            "path": os.path.join(self.path, f"session_{self.session_id}.jsonl")
        }
