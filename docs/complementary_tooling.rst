Complementary Tooling
=====================

AgentArmor is easiest to position correctly when it is described as one layer
in a broader stack, not as a total replacement for every other tool category.

How It Compares
---------------

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - Category
     - Primary job
     - How it fits with AgentArmor
   * - AgentArmor
     - In-process runtime controls around model and tool traffic
     - Budget, prompt-injection, output filtering, MCP policy, and audit hooks
       happen close to the application code path
   * - Hosted proxy guardrails
     - Centralized traffic routing, org-wide enforcement, shared policy
     - Can add fleet-wide governance, but often with more operational
       overhead and a different deployment model
   * - Tracing / observability tools
     - Dashboards, replay, search, and cross-service visibility
     - Good complement for Explain Mode exports, cost events, and blocked-call
       investigations
   * - Evaluation / red-team tools
     - Offline benchmarking and systematic safety testing
     - Useful to validate policies and track improvements over time
   * - Agent orchestration frameworks
     - Graph composition, routing, tool loops, memory, and workflows
     - AgentArmor does not replace orchestration; it wraps the runtime
       surfaces those frameworks eventually use

When To Combine Layers
----------------------

Use AgentArmor plus other tooling when you need:

- runtime controls in the application process
- dashboards or fleet-wide observability elsewhere
- offline evaluation separate from the production execution path
- orchestration without rewriting your safety layer for every framework

Recommended Positioning
-----------------------

Good framing:

- AgentArmor is the local-first runtime safety layer
- observability tools remain the system of record for traces and analytics
- hosted proxies are optional complements for teams that want centralized
  policy or routing

Risky framing:

- claiming AgentArmor replaces every tracing, evaluation, or governance tool
- implying a framework-specific orchestration story where the repo really
  provides provider-surface interception

