import contextvars
import threading
import time
import uuid
from typing import Dict, List, Optional

from ..exceptions import AgentDepthExceeded, AgentLimitExceeded, AgentBudgetExhausted
from ..hooks import RequestContext, ResponseContext


# Async-safe active agent tracking via contextvars.
# Each asyncio task / thread gets its own active agent.
_ctx_active_agent: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_agentarmor_active_agent", default=None,
)


class AgentNode:
    """Represents a single agent in the execution graph."""

    def __init__(self, agent_id: str, parent: Optional['AgentNode'] = None,
                 budget_limit: Optional[float] = None,
                 trace_id: Optional[str] = None,
                 policies: Optional[Dict] = None):
        self.agent_id = agent_id
        self.parent = parent
        self.children: List['AgentNode'] = []
        self.budget_spent = 0.0
        self.budget_limit = budget_limit
        self.calls = 0
        self.blocked_calls = 0
        self.created_at = time.time()
        self.ended = False
        self.trace_id = trace_id or str(uuid.uuid4())[:12]
        self.policies = policies or {}

    @property
    def depth(self) -> int:
        """How deep in the agent tree this node is."""
        d = 0
        node = self.parent
        while node is not None:
            d += 1
            node = node.parent
        return d

    @property
    def total_spent(self) -> float:
        """Total spent by this agent and all descendants."""
        total = self.budget_spent
        for child in self.children:
            total += child.total_spent
        return total

    @property
    def budget_remaining(self) -> Optional[float]:
        """Remaining budget for this agent, or None if unlimited."""
        if self.budget_limit is None:
            return None
        return max(0.0, self.budget_limit - self.total_spent)


class AgentGraphModule:
    """Manages parent-child agent relationships and propagates safety state.

    v2 improvements:
    - Uses contextvars for async-safe active agent tracking (safe across
      concurrent asyncio tasks and threads)
    - Per-agent trace IDs for distributed tracing
    - Parallel execution: multiple agents can be active simultaneously
      in different async tasks / threads
    - Policy inheritance: child agents inherit parent policies by default
    """

    def __init__(self, max_depth: int = 5, inherit_budget: bool = True,
                 inherit_firewall: bool = True, inherit_shield: bool = True,
                 max_total_agents: int = 50,
                 default_policies: Optional[Dict] = None):
        self.max_depth = max_depth
        self.inherit_budget = inherit_budget
        self.inherit_firewall = inherit_firewall
        self.inherit_shield = inherit_shield
        self.max_total_agents = max_total_agents
        self.default_policies = default_policies or {}
        self._agents: Dict[str, AgentNode] = {}
        self._lock = threading.Lock()

    def spawn_agent(self, agent_id: str, parent_id: Optional[str] = None,
                    budget_limit: Optional[float] = None,
                    policies: Optional[Dict] = None) -> AgentNode:
        """Register a new child agent.

        Inherits parent's remaining budget and policies if configured.
        Sets the new agent as active in the current async context.
        """
        with self._lock:
            if len(self._agents) >= self.max_total_agents:
                raise AgentLimitExceeded(
                    f"Maximum number of agents ({self.max_total_agents}) exceeded."
                )

            parent = None
            if parent_id is not None:
                parent = self._agents.get(parent_id)
                if parent is None:
                    raise ValueError(f"Parent agent '{parent_id}' not found.")

            # Build inherited policies
            effective_policies = dict(self.default_policies)
            if parent is not None:
                # Inherit parent policies, child overrides take precedence
                effective_policies.update(parent.policies)
            if policies:
                effective_policies.update(policies)

            # Derive trace_id from parent if available
            trace_id = None
            if parent is not None:
                trace_id = f"{parent.trace_id}/{agent_id}"

            node = AgentNode(
                agent_id=agent_id,
                parent=parent,
                budget_limit=budget_limit,
                trace_id=trace_id,
                policies=effective_policies,
            )

            # Enforce depth limit
            if node.depth >= self.max_depth:
                raise AgentDepthExceeded(
                    f"Agent depth {node.depth} exceeds maximum of {self.max_depth - 1}. "
                    f"Agent '{agent_id}' cannot be spawned."
                )

            # Inherit budget from parent if enabled
            if self.inherit_budget and parent is not None and parent.budget_limit is not None:
                parent_remaining = parent.budget_remaining
                if parent_remaining is not None:
                    if budget_limit is not None:
                        node.budget_limit = min(budget_limit, parent_remaining)
                    else:
                        node.budget_limit = parent_remaining

            if parent is not None:
                parent.children.append(node)

            self._agents[agent_id] = node

        # Set active agent in current async/thread context
        _ctx_active_agent.set(agent_id)
        return node

    def end_agent(self, agent_id: str) -> None:
        """Mark an agent as completed and restore parent as active."""
        with self._lock:
            node = self._agents.get(agent_id)
            if node is None:
                raise ValueError(f"Agent '{agent_id}' not found.")
            node.ended = True

        # Restore parent as active in current context
        if node.parent:
            _ctx_active_agent.set(node.parent.agent_id)
        else:
            _ctx_active_agent.set(None)

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Check agent-level budget limits before each call."""
        agent_id = _ctx_active_agent.get()
        if agent_id is None:
            return ctx

        with self._lock:
            node = self._agents.get(agent_id)
            if node is None:
                return ctx

            # Check budget
            if node.budget_limit is not None:
                remaining = node.budget_remaining
                if remaining is not None and remaining <= 0:
                    node.blocked_calls += 1
                    raise AgentBudgetExhausted(
                        f"Agent '{node.agent_id}' budget exhausted. "
                        f"Limit: ${node.budget_limit:.4f}, Spent: ${node.total_spent:.4f}"
                    )

        return ctx

    def post_record(self, ctx: ResponseContext) -> ResponseContext:
        """Record cost against the active agent node."""
        agent_id = _ctx_active_agent.get()
        if agent_id is None:
            return ctx

        with self._lock:
            node = self._agents.get(agent_id)
            if node is None:
                return ctx

            cost = ctx.cost or 0.0
            node.budget_spent += cost
            node.calls += 1

        return ctx

    def get_agent(self, agent_id: str) -> Optional[AgentNode]:
        """Return the AgentNode for the given agent_id, or None."""
        return self._agents.get(agent_id)

    @property
    def active_agent_id(self) -> Optional[str]:
        """Return the currently active agent ID (context-local)."""
        return _ctx_active_agent.get()

    @active_agent_id.setter
    def active_agent_id(self, value: Optional[str]) -> None:
        _ctx_active_agent.set(value)

    def _node_to_dict(self, node: AgentNode) -> dict:
        """Convert an AgentNode to a dictionary representation."""
        result = {
            "agent_id": node.agent_id,
            "depth": node.depth,
            "calls": node.calls,
            "blocked_calls": node.blocked_calls,
            "budget_spent": f"${node.budget_spent:.4f}",
            "total_spent": f"${node.total_spent:.4f}",
            "ended": node.ended,
            "trace_id": node.trace_id,
        }
        if node.budget_limit is not None:
            result["budget_limit"] = f"${node.budget_limit:.4f}"
            remaining = node.budget_remaining
            result["budget_remaining"] = f"${remaining:.4f}" if remaining is not None else None
        if node.policies:
            result["policies"] = node.policies
        if node.children:
            result["children"] = [self._node_to_dict(c) for c in node.children]
        return result

    def report(self) -> dict:
        """Return tree structure with per-agent stats."""
        roots = [n for n in self._agents.values() if n.parent is None]
        total_spent = sum(r.total_spent for r in roots)
        return {
            "total_agents": len(self._agents),
            "max_depth": self.max_depth,
            "max_total_agents": self.max_total_agents,
            "total_spent": f"${total_spent:.4f}",
            "active_agent": _ctx_active_agent.get(),
            "agents": [self._node_to_dict(r) for r in roots],
        }
