import os
import json
import tempfile
from agentarmor.modules.recorder import RecorderModule
from agentarmor.hooks import RequestContext, ResponseContext

def test_recorder_logging():
    with tempfile.TemporaryDirectory() as temp_dir:
        module = RecorderModule(path=temp_dir)
        
        req = RequestContext(messages=[{"role": "user", "content": "Hi"}], model="gpt-4o")
        res = ResponseContext(text="Hello there!", model="gpt-4o", provider="openai", request=req, latency_ms=150.5)
        
        module.post_record(res)
        
        filepath = os.path.join(temp_dir, f"session_{module.session_id}.jsonl")
        assert os.path.exists(filepath)
        
        with open(filepath, "r") as f:
            lines = f.readlines()
            assert len(lines) == 1
            
            data = json.loads(lines[0])
            assert data["provider"] == "openai"
            assert data["model"] == "gpt-4o"
            assert data["output"] == "Hello there!"
            assert data["latency_ms"] == 150.5
            
        report = module.report()
        assert report["events"] == 1
        assert report["session_id"] == module.session_id
