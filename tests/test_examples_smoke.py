import runpy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import agentarmor
from agentarmor.exceptions import InjectionDetected, MCPViolation, ToolCallBlocked


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def _run_example(script_name: str) -> None:
    runpy.run_path(str(EXAMPLES_DIR / script_name), run_name="__main__")


def _install_modules(monkeypatch, modules: dict[str, ModuleType]) -> None:
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def _stub_agentarmor(monkeypatch, *, report=None, last_trace=None) -> None:
    monkeypatch.setattr(
        agentarmor,
        "init",
        lambda *args, **kwargs: SimpleNamespace(config=kwargs),
    )
    monkeypatch.setattr(agentarmor, "teardown", lambda: None)
    monkeypatch.setattr(agentarmor, "report", lambda: report or {"status": "ok"})
    if last_trace is not None:
        monkeypatch.setattr(agentarmor, "last_trace", lambda: last_trace)


def _fake_pydantic_ai_modules() -> dict[str, ModuleType]:
    pydantic_ai = ModuleType("pydantic_ai")

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def run_sync(self, prompt):
            if "Ignore all previous instructions" in prompt:
                raise InjectionDetected("prompt injection blocked")
            return SimpleNamespace(output="Runtime safety keeps tools in bounds.")

    pydantic_ai.Agent = FakeAgent
    return {"pydantic_ai": pydantic_ai}


def _fake_agno_modules() -> dict[str, ModuleType]:
    agno = ModuleType("agno")
    agno_agent = ModuleType("agno.agent")
    agno_models = ModuleType("agno.models")
    agno_models_openai = ModuleType("agno.models.openai")

    class FakeOpenAIResponses:
        def __init__(self, id):
            self.id = id

    class FakeAgent:
        def __init__(self, model, instructions=None, tools=None, markdown=False):
            self.model = model
            self.instructions = instructions or []
            self.tools = {tool.__name__: tool for tool in tools or []}
            self.markdown = markdown

        def run(self, prompt):
            if "execute_shell" in prompt:
                raise ToolCallBlocked("execute_shell is not allowed")
            if "Ignore all previous instructions" in prompt:
                raise InjectionDetected("prompt injection blocked")
            if "get_service_status" in prompt:
                return SimpleNamespace(
                    content=self.tools["get_service_status"]("billing-api")
                )
            return SimpleNamespace(content="Runtime safety keeps tool calls bounded.")

    agno_agent.Agent = FakeAgent
    agno_models_openai.OpenAIResponses = FakeOpenAIResponses

    agno.agent = agno_agent
    agno.models = agno_models
    agno_models.openai = agno_models_openai

    return {
        "agno": agno,
        "agno.agent": agno_agent,
        "agno.models": agno_models,
        "agno.models.openai": agno_models_openai,
    }


def _fake_google_adk_modules() -> dict[str, ModuleType]:
    google = ModuleType("google")
    google_adk = ModuleType("google.adk")
    google_adk_agents = ModuleType("google.adk.agents")
    google_adk_agents_llm_agent = ModuleType("google.adk.agents.llm_agent")

    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    google_adk_agents_llm_agent.Agent = FakeAgent
    google.adk = google_adk
    google_adk.agents = google_adk_agents
    google_adk_agents.llm_agent = google_adk_agents_llm_agent

    return {
        "google": google,
        "google.adk": google_adk,
        "google.adk.agents": google_adk_agents,
        "google.adk.agents.llm_agent": google_adk_agents_llm_agent,
    }


def _fake_langgraph_modules() -> dict[str, ModuleType]:
    langchain_openai = ModuleType("langchain_openai")
    langgraph = ModuleType("langgraph")
    langgraph_graph = ModuleType("langgraph.graph")

    class FakeChatOpenAI:
        def __init__(self, model, temperature=0):
            self.model = model
            self.temperature = temperature

        def invoke(self, prompt):
            if "Ignore all previous instructions" in prompt:
                raise InjectionDetected("prompt injection blocked")
            if prompt.startswith("Create a two-bullet answer plan"):
                return SimpleNamespace(
                    content="- Explain tool risk\n- Show the runtime block"
                )
            return SimpleNamespace(
                content="Runtime safeguards keep multi-step agents on policy."
            )

    class FakeCompiledGraph:
        def __init__(self, nodes, edges):
            self.nodes = nodes
            self.edges = edges

        def invoke(self, state):
            current = self.edges["__start__"][0]
            data = dict(state)
            while current != "__end__":
                update = self.nodes[current](data)
                if update:
                    data.update(update)
                current = self.edges.get(current, ["__end__"])[0]
            return data

    class FakeStateGraph:
        def __init__(self, _state_type):
            self.nodes = {}
            self.edges = {}

        def add_node(self, name, func):
            self.nodes[name] = func

        def add_edge(self, source, destination):
            self.edges.setdefault(source, []).append(destination)

        def compile(self):
            return FakeCompiledGraph(self.nodes, self.edges)

    langchain_openai.ChatOpenAI = FakeChatOpenAI
    langgraph_graph.StateGraph = FakeStateGraph
    langgraph_graph.START = "__start__"
    langgraph_graph.END = "__end__"
    langgraph.graph = langgraph_graph

    return {
        "langchain_openai": langchain_openai,
        "langgraph": langgraph,
        "langgraph.graph": langgraph_graph,
    }


def _fake_trace_export_modules() -> dict[str, ModuleType]:
    openai = ModuleType("openai")
    opentelemetry = ModuleType("opentelemetry")
    opentelemetry_trace = ModuleType("opentelemetry.trace")

    class FakeCompletions:
        def create(self, **kwargs):
            return {"id": "resp_123", "kwargs": kwargs}

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self):
            self.chat = FakeChat()

    class FakeSpan:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def set_attributes(self, attributes):
            self.attributes = attributes

    class FakeTracer:
        def start_as_current_span(self, name):
            self.name = name
            return FakeSpan()

    def get_tracer(name):
        return FakeTracer()

    openai.OpenAI = FakeOpenAI
    opentelemetry.trace = opentelemetry_trace
    opentelemetry_trace.get_tracer = get_tracer

    return {
        "openai": openai,
        "opentelemetry": opentelemetry,
        "opentelemetry.trace": opentelemetry_trace,
    }


class _FakeTrace:
    def to_dict(self):
        return {
            "blocked_by": None,
            "events": [{"module": "shield", "decision": "allow"}],
        }

    def to_otel_attributes(self):
        return {
            "agentarmor.blocked": False,
            "agentarmor.event_count": 1,
        }


def test_pydantic_ai_example_runs_with_stubbed_framework(monkeypatch, capsys):
    _stub_agentarmor(monkeypatch, report={"status": "ok", "blocked": 1})
    _install_modules(monkeypatch, _fake_pydantic_ai_modules())

    _run_example("pydantic_ai_example.py")

    output = capsys.readouterr().out
    assert "=== Safe request ===" in output
    assert "Runtime safety keeps tools in bounds." in output
    assert "Injection pattern matched (heuristic, bypassable)" in output


def test_agno_tool_policy_example_runs_with_stubbed_framework(monkeypatch, capsys):
    _stub_agentarmor(monkeypatch, report={"status": "ok", "blocked": 1})
    _install_modules(monkeypatch, _fake_agno_modules())

    _run_example("agno_tool_policy_example.py")

    output = capsys.readouterr().out
    assert "=== Allowed tool path ===" in output
    assert "billing-api: green" in output
    assert "Blocked by AgentArmor" in output


def test_google_adk_example_runs_with_stubbed_framework(monkeypatch, capsys):
    _stub_agentarmor(monkeypatch)
    _install_modules(monkeypatch, _fake_google_adk_modules())

    _run_example("google_adk_example.py")

    output = capsys.readouterr().out
    assert "Google ADK example scaffold created." in output
    assert "AgentArmor will protect the underlying model calls once the agent runs." in output


def test_langgraph_example_runs_with_stubbed_framework(monkeypatch, capsys):
    _stub_agentarmor(monkeypatch, report={"status": "ok", "blocked": 1})
    _install_modules(monkeypatch, _fake_langgraph_modules())

    _run_example("langgraph_multistep_example.py")

    output = capsys.readouterr().out
    assert "=== Safe graph run ===" in output
    assert "Runtime safeguards keep multi-step agents on policy." in output
    assert "Injection pattern matched (heuristic, bypassable)" in output


def test_mcp_policy_example_runs_with_stubbed_firewall(monkeypatch, capsys):
    _stub_agentarmor(monkeypatch)

    def fake_validate_server(name, server_uri=None):
        if name == "remote-exec":
            raise MCPViolation("Blocked MCP server: remote-exec")
        return True

    def fake_validate_tool(tool_name, arguments, server_name=None):
        if arguments.get("path") == "/etc/passwd":
            raise MCPViolation("Tool policy violation: file_read with args {'path': '/etc/passwd'}")
        return True

    monkeypatch.setattr(agentarmor, "validate_mcp_server", fake_validate_server)
    monkeypatch.setattr(agentarmor, "validate_mcp_tool", fake_validate_tool)
    monkeypatch.setattr(
        agentarmor,
        "authenticate_mcp_server",
        lambda server_name, token: server_name == "private-server" and token == "Bearer dev-token",
    )

    _run_example("mcp_policy_example.py")

    output = capsys.readouterr().out
    assert "=== Trusted filesystem server ===" in output
    assert "=== Allowed filesystem read ===" in output
    assert "=== Blocked filesystem read ===" in output
    assert "Blocked MCP server: remote-exec" in output


def test_trace_export_example_runs_with_stubbed_dependencies(monkeypatch, capsys):
    fake_trace = _FakeTrace()
    _stub_agentarmor(monkeypatch, last_trace=fake_trace)
    _install_modules(monkeypatch, _fake_trace_export_modules())

    _run_example("trace_export_example.py")

    output = capsys.readouterr().out
    assert "=== JSON export ===" in output
    assert '"blocked_by": null' in output
    assert "'agentarmor.event_count': 1" in output
    assert "=== OpenTelemetry attributes ===" in output
