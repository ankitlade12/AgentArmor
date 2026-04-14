import contextvars
import pytest
from agentarmor.modules.agent_graph import AgentGraphModule, AgentNode
from agentarmor.exceptions import (
    AgentDepthExceeded, AgentLimitExceeded, AgentBudgetExhausted,
)
from agentarmor.hooks import RequestContext, ResponseContext


def _make_req_ctx():
    return RequestContext(messages=[], model="gpt-4o")


def _make_res_ctx(cost=0.0):
    req = _make_req_ctx()
    ctx = ResponseContext(
        text="test", model="gpt-4o", provider="openai", request=req,
    )
    ctx.cost = cost
    return ctx


# --- AgentNode basics ---

def test_agent_node_depth_root():
    node = AgentNode(agent_id="root")
    assert node.depth == 0


def test_agent_node_depth_nested():
    root = AgentNode(agent_id="root")
    child = AgentNode(agent_id="child", parent=root)
    grandchild = AgentNode(agent_id="grandchild", parent=child)
    assert child.depth == 1
    assert grandchild.depth == 2


def test_agent_node_total_spent():
    root = AgentNode(agent_id="root")
    child = AgentNode(agent_id="child", parent=root)
    root.children.append(child)
    root.budget_spent = 1.0
    child.budget_spent = 0.5
    assert root.total_spent == 1.5
    assert child.total_spent == 0.5


# --- Spawning ---

def test_spawn_root_agent():
    module = AgentGraphModule()
    node = module.spawn_agent("root")
    assert node.agent_id == "root"
    assert node.depth == 0
    assert node.parent is None


def test_spawn_child_agent():
    module = AgentGraphModule()
    module.spawn_agent("root")
    child = module.spawn_agent("child", parent_id="root")
    assert child.parent.agent_id == "root"
    assert child.depth == 1


def test_spawn_child_inherits_budget():
    module = AgentGraphModule(inherit_budget=True)
    root = module.spawn_agent("root", budget_limit=10.0)
    child = module.spawn_agent("child", parent_id="root")
    # Child inherits parent's remaining budget
    assert child.budget_limit == 10.0


def test_spawn_child_inherits_min_budget():
    module = AgentGraphModule(inherit_budget=True)
    root = module.spawn_agent("root", budget_limit=10.0)
    # Explicit limit less than parent remaining -> use explicit
    child = module.spawn_agent("child", parent_id="root", budget_limit=5.0)
    assert child.budget_limit == 5.0


def test_spawn_child_inherits_parent_remaining_when_less():
    module = AgentGraphModule(inherit_budget=True)
    root = module.spawn_agent("root", budget_limit=10.0)
    # Simulate root spending 8.0
    root.budget_spent = 8.0
    # Explicit limit 5.0 > parent remaining 2.0 -> use parent remaining
    child = module.spawn_agent("child", parent_id="root", budget_limit=5.0)
    assert child.budget_limit == 2.0


def test_spawn_no_inherit_budget():
    module = AgentGraphModule(inherit_budget=False)
    module.spawn_agent("root", budget_limit=10.0)
    child = module.spawn_agent("child", parent_id="root", budget_limit=50.0)
    assert child.budget_limit == 50.0


def test_spawn_unknown_parent():
    module = AgentGraphModule()
    with pytest.raises(ValueError, match="Parent agent"):
        module.spawn_agent("child", parent_id="nonexistent")


# --- Depth enforcement ---

def test_max_depth_enforcement():
    module = AgentGraphModule(max_depth=3)
    module.spawn_agent("a0")
    module.spawn_agent("a1", parent_id="a0")
    module.spawn_agent("a2", parent_id="a1")
    # depth=3 would equal max_depth, so it should be blocked
    with pytest.raises(AgentDepthExceeded):
        module.spawn_agent("a3", parent_id="a2")


# --- Total agents enforcement ---

def test_max_total_agents_enforcement():
    module = AgentGraphModule(max_total_agents=3)
    module.spawn_agent("a")
    module.spawn_agent("b")
    module.spawn_agent("c")
    with pytest.raises(AgentLimitExceeded):
        module.spawn_agent("d")


# --- Budget pre_check ---

def test_pre_check_allows_within_budget():
    module = AgentGraphModule()
    module.spawn_agent("root", budget_limit=10.0)
    ctx = _make_req_ctx()
    result = module.pre_check(ctx)
    assert result is ctx


def test_pre_check_blocks_exhausted_budget():
    module = AgentGraphModule()
    node = module.spawn_agent("root", budget_limit=1.0)
    node.budget_spent = 1.0
    ctx = _make_req_ctx()
    with pytest.raises(AgentBudgetExhausted):
        module.pre_check(ctx)


def test_pre_check_no_active_agent():
    module = AgentGraphModule()
    ctx = _make_req_ctx()
    # No agents spawned, should pass through
    result = module.pre_check(ctx)
    assert result is ctx


# --- post_record ---

def test_post_record_tracks_cost():
    module = AgentGraphModule()
    module.spawn_agent("root")
    res_ctx = _make_res_ctx(cost=0.25)
    module.post_record(res_ctx)
    node = module.get_agent("root")
    assert node.budget_spent == 0.25
    assert node.calls == 1


def test_post_record_no_active_agent():
    module = AgentGraphModule()
    res_ctx = _make_res_ctx(cost=0.1)
    # Should not raise
    result = module.post_record(res_ctx)
    assert result is res_ctx


# --- Budget propagation ---

def test_budget_propagation_child_spend_reduces_parent_remaining():
    module = AgentGraphModule(inherit_budget=True)
    root = module.spawn_agent("root", budget_limit=10.0)
    child = module.spawn_agent("child", parent_id="root", budget_limit=5.0)
    child.budget_spent = 3.0
    # root's total_spent includes child's spend
    assert root.total_spent == 3.0
    # root's remaining = 10.0 - 3.0 = 7.0
    assert root.budget_remaining == 7.0


# --- end_agent ---

def test_end_agent_marks_ended():
    module = AgentGraphModule()
    module.spawn_agent("root")
    module.spawn_agent("child", parent_id="root")
    module.end_agent("child")
    node = module.get_agent("child")
    assert node.ended is True
    assert module.active_agent_id == "root"


def test_end_root_agent():
    module = AgentGraphModule()
    module.spawn_agent("root")
    module.end_agent("root")
    assert module.active_agent_id is None


def test_end_unknown_agent():
    module = AgentGraphModule()
    with pytest.raises(ValueError, match="not found"):
        module.end_agent("nonexistent")


# --- Report ---

def test_report_structure():
    module = AgentGraphModule(max_depth=5, max_total_agents=50)
    root = module.spawn_agent("root", budget_limit=10.0)
    child = module.spawn_agent("child", parent_id="root", budget_limit=5.0)
    child.budget_spent = 1.5
    child.calls = 2

    report = module.report()
    assert report["total_agents"] == 2
    assert report["max_depth"] == 5
    assert report["max_total_agents"] == 50
    assert report["active_agent"] == "child"
    assert len(report["agents"]) == 1  # one root

    root_report = report["agents"][0]
    assert root_report["agent_id"] == "root"
    assert root_report["total_spent"] == "$1.5000"
    assert "children" in root_report
    assert root_report["children"][0]["agent_id"] == "child"
    assert root_report["children"][0]["budget_spent"] == "$1.5000"


def test_report_total_spent():
    module = AgentGraphModule()
    root = module.spawn_agent("root")
    root.budget_spent = 2.0
    child = module.spawn_agent("child", parent_id="root")
    child.budget_spent = 1.0
    report = module.report()
    assert report["total_spent"] == "$3.0000"


# --- get_agent ---

def test_get_agent_found():
    module = AgentGraphModule()
    module.spawn_agent("root")
    assert module.get_agent("root") is not None


def test_get_agent_not_found():
    module = AgentGraphModule()
    assert module.get_agent("nope") is None


# --- Graceful no-op without graph module ---

def test_no_graph_module_spawn_returns_none():
    """spawn_agent via __init__.py returns None when no graph module."""
    import agentarmor
    # init without agent_graph
    core = agentarmor.init(budget="$10.00")
    try:
        result = agentarmor.spawn_agent("test")
        assert result is None
    finally:
        agentarmor.teardown()


def test_no_graph_module_end_no_error():
    """end_agent via __init__.py does nothing when no graph module."""
    import agentarmor
    core = agentarmor.init(budget="$10.00")
    try:
        # Should not raise
        agentarmor.end_agent("test")
    finally:
        agentarmor.teardown()


# --- v2: Trace IDs ---

def test_trace_id_auto_generated():
    module = AgentGraphModule()
    node = module.spawn_agent("root")
    assert node.trace_id is not None
    assert len(node.trace_id) == 12


def test_trace_id_inherited_from_parent():
    module = AgentGraphModule()
    root = module.spawn_agent("root")
    child = module.spawn_agent("child", parent_id="root")
    assert child.trace_id == f"{root.trace_id}/child"


def test_trace_id_in_report():
    module = AgentGraphModule()
    module.spawn_agent("root")
    report = module.report()
    assert "trace_id" in report["agents"][0]


# --- v2: Policy inheritance ---

def test_child_inherits_parent_policies():
    module = AgentGraphModule()
    module.spawn_agent("root", policies={"shield": True, "filter": ["pii"]})
    child = module.spawn_agent("child", parent_id="root")
    assert child.policies["shield"] is True
    assert child.policies["filter"] == ["pii"]


def test_child_overrides_parent_policies():
    module = AgentGraphModule()
    module.spawn_agent("root", policies={"shield": True, "filter": ["pii"]})
    child = module.spawn_agent(
        "child", parent_id="root", policies={"shield": False},
    )
    assert child.policies["shield"] is False
    assert child.policies["filter"] == ["pii"]


def test_default_policies_applied():
    module = AgentGraphModule(default_policies={"budget": 10.0})
    node = module.spawn_agent("root")
    assert node.policies["budget"] == 10.0


def test_parent_policies_override_defaults():
    module = AgentGraphModule(default_policies={"budget": 10.0})
    module.spawn_agent("root", policies={"budget": 5.0})
    child = module.spawn_agent("child", parent_id="root")
    assert child.policies["budget"] == 5.0


# --- v2: Async-safe contextvars ---

def test_contextvars_active_agent():
    """Active agent uses contextvars, not shared state."""
    module = AgentGraphModule()
    module.spawn_agent("root")
    assert module.active_agent_id == "root"
    module.spawn_agent("child", parent_id="root")
    assert module.active_agent_id == "child"
    module.end_agent("child")
    assert module.active_agent_id == "root"


@pytest.mark.asyncio
async def test_parallel_agents_in_async_tasks():
    """Two concurrent async tasks get independent active agents."""
    import asyncio

    module = AgentGraphModule()
    module.spawn_agent("root")

    results = {}

    async def task_a():
        module.spawn_agent("agent_a", parent_id="root")
        await asyncio.sleep(0.01)
        results["a"] = module.active_agent_id

    async def task_b():
        module.spawn_agent("agent_b", parent_id="root")
        await asyncio.sleep(0.01)
        results["b"] = module.active_agent_id

    # Copy context so each task gets its own contextvars
    ctx_a = contextvars.copy_context()
    ctx_b = contextvars.copy_context()

    await asyncio.gather(
        asyncio.ensure_future(ctx_a.run(task_a)),
        asyncio.ensure_future(ctx_b.run(task_b)),
    )

    assert results["a"] == "agent_a"
    assert results["b"] == "agent_b"


# --- v2: Backwards-compat for removed constructor kwargs ---

def test_deprecated_inherit_firewall_emits_warning_and_maps_to_policies():
    with pytest.warns(DeprecationWarning, match="inherit_firewall"):
        module = AgentGraphModule(inherit_firewall=True)
    assert module.default_policies.get("firewall") is True


def test_deprecated_inherit_shield_emits_warning_and_maps_to_policies():
    with pytest.warns(DeprecationWarning, match="inherit_shield"):
        module = AgentGraphModule(inherit_shield=False)
    assert module.default_policies.get("shield") is False


def test_deprecated_flags_do_not_clobber_explicit_default_policies():
    """Explicit default_policies value wins over legacy flag."""
    with pytest.warns(DeprecationWarning):
        module = AgentGraphModule(
            default_policies={"shield": True},
            inherit_shield=False,
        )
    # setdefault() keeps the explicit value set by default_policies
    assert module.default_policies["shield"] is True


def test_unknown_kwargs_still_raise_type_error():
    """Accepting deprecated flags must not mask typos in other kwargs."""
    with pytest.raises(TypeError, match="totally_made_up_param"):
        AgentGraphModule(totally_made_up_param=True)
