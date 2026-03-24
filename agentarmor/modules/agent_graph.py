import threading
import time
from typing import Dict, List, Optional

from ..exceptions import AgentDepthExceeded, AgentLimitExceeded, AgentBudgetExhausted
from ..hooks import RequestContext, ResponseContext


class AgentNode:
    """Represents a single agent in the execution graph."""

    def __init__(self, agent_id: str, parent: Optional['AgentNode'] = None,
                 budget_limit: Optional[float] = None):
        self.agent_id = agent_id
        self.parent = parent
        self.children: List['AgentNode'] = []
        self.budget_spent = 0.0
        self.budget_limit = budget_limit
        self.calls = 0
        self.blocked_calls = 0
        self.created_at = time.time()
        self.ended = False

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

    Thread safety: all mutating methods (spawn_agent, end_agent, pre_check,
    post_record) are protected by an internal Lock. Cost attribution assumes
    sequential agent execution; concurrent agents on separate threads will
    attribute costs to whichever agent is ``active_agent_id`` at call time.
    """

    def __init__(self, max_depth: int = 5, inherit_budget: bool = True,
                 inherit_firewall: bool = True, inherit_shield: bool = True,
                 max_total_agents: int = 50):
        self.max_depth = max_depth
        self.inherit_budget = inherit_budget
        self.inherit_firewall = inherit_firewall
        self.inherit_shield = inherit_shield
        self.max_total_agents = max_total_agents
        self._agents: Dict[str, AgentNode] = {}
        self._active_agent_id: Optional[str] = None
        self._lock = threading.Lock()

    def spawn_agent(self, agent_id: str, parent_id: Optional[str] = None,
                    budget_limit: Optional[float] = None) -> AgentNode:
        """Register a new child agent. Inherits parent's remaining budget if inherit_budget=True."""
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

            node = AgentNode(agent_id=agent_id, parent=parent, budget_limit=budget_limit)

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
            self._active_agent_id = agent_id
            return node

    def end_agent(self, agent_id: str) -> None:
        """Mark an agent as completed and roll up its stats to parent."""
        with self._lock:
            node = self._agents.get(agent_id)
            if node is None:
                raise ValueError(f"Agent '{agent_id}' not found.")
            node.ended = True

            # Restore parent as active
            if node.parent:
                self._active_agent_id = node.parent.agent_id
            else:
                self._active_agent_id = None

    def pre_check(self, ctx: RequestContext) -> RequestContext:
        """Check agent-level budget and depth limits before each call."""
        with self._lock:
            if self._active_agent_id is None:
                return ctx

            node = self._agents.get(self._active_agent_id)
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
        with self._lock:
            if self._active_agent_id is None:
                return ctx

            node = self._agents.get(self._active_agent_id)
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
        """Return the currently active agent ID."""
        return self._active_agent_id

    @active_agent_id.setter
    def active_agent_id(self, value: Optional[str]) -> None:
        self._active_agent_id = value

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
        }
        if node.budget_limit is not None:
            result["budget_limit"] = f"${node.budget_limit:.4f}"
            remaining = node.budget_remaining
            result["budget_remaining"] = f"${remaining:.4f}" if remaining is not None else None
        if node.children:
            result["children"] = [self._node_to_dict(c) for c in node.children]
        return result

    def report(self) -> dict:
        """Return tree structure with per-agent stats."""
        # Find root nodes (agents without parents)
        roots = [n for n in self._agents.values() if n.parent is None]
        total_spent = sum(r.total_spent for r in roots)
        return {
            "total_agents": len(self._agents),
            "max_depth": self.max_depth,
            "max_total_agents": self.max_total_agents,
            "total_spent": f"${total_spent:.4f}",
            "active_agent": self._active_agent_id,
            "agents": [self._node_to_dict(r) for r in roots],
        }
