"""The flight recorder writes full, unredacted prompts/outputs to local disk,
so the session file must not be world-readable. (It is a local debug log, not
a tamper-evident audit trail — but it should at least be owner-only.)
"""
import os
import stat
import sys

import pytest

from agentarmor.modules.recorder import RecorderModule
from agentarmor.hooks import RequestContext, ResponseContext

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")


def _record_once(path):
    rec = RecorderModule(path=str(path))
    req = RequestContext(messages=[{"role": "user", "content": "my SSN is 123-45-6789"}], model="gpt-4o")
    res = ResponseContext(text="ok", model="gpt-4o", provider="openai", request=req, latency_ms=1.0)
    rec.post_record(res)
    return rec


def test_session_file_is_owner_only(tmp_path):
    rec = _record_once(tmp_path / "sessions")
    mode = stat.S_IMODE(os.stat(rec.filepath).st_mode)
    assert mode == 0o600, f"session file is {oct(mode)}, expected 0o600 (owner-only)"


def test_session_dir_is_owner_only(tmp_path):
    rec = _record_once(tmp_path / "sessions")
    mode = stat.S_IMODE(os.stat(rec.path).st_mode)
    assert mode == 0o700, f"session dir is {oct(mode)}, expected 0o700 (owner-only)"
