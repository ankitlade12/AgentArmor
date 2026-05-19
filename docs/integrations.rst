Framework Integrations
======================

AgentArmor works well with many major Python AI frameworks whose LLM traffic
flows through supported SDK surfaces. Because it monkey-patches the underlying
provider clients directly, you often don't need framework-specific callbacks or
middleware.

Just call ``agentarmor.init()`` at the top of your script and it will
automatically protect all LLM calls, regardless of which framework wraps them.

See ``SUPPORT_MATRIX.md`` in the repository root for the tested provider
surfaces and the evidence level behind compatibility claims.

Supported Frameworks
--------------------

- **LangChain / LangGraph**
- **LiteLLM**
- **LlamaIndex**
- **CrewAI**
- **Pydantic AI**
- **Google ADK**
- **Agno / Phidata**
- **AutoGen**
- **SmolAgents**
- Custom raw SDK scripts

LiteLLM
-------

.. code-block:: python

   import agentarmor
   from litellm import completion

   agentarmor.init(budget="$2.00", shield=True, record=True)

   response = completion(
       model="gpt-4o-mini",
       messages=[{"role": "user", "content": "Summarize runtime safety"}],
   )

   print(agentarmor.report())
   agentarmor.teardown()

LangChain
---------

.. code-block:: python

   import agentarmor
   from langchain_openai import ChatOpenAI

   agentarmor.init(budget="$2.00", shield=True, filter=["pii"])

   llm = ChatOpenAI(model="gpt-4o")
   response = llm.invoke("Summarize this document...")
   # AgentArmor is silently protecting every call

   print(agentarmor.report())
   agentarmor.teardown()

LangGraph
---------

See ``examples/langgraph_multistep_example.py`` for a small two-node graph that
shows AgentArmor covering more than one model hop inside the same flow.

LlamaIndex
----------

.. code-block:: python

   import agentarmor
   from llama_index.llms.openai import OpenAI

   agentarmor.init(budget="$3.00", record=True)

   llm = OpenAI(model="gpt-4o")
   response = llm.complete("Explain quantum computing...")

   print(agentarmor.spent())
   agentarmor.teardown()

CrewAI
------

.. code-block:: python

   import agentarmor
   from crewai import Agent, Task, Crew

   agentarmor.init(budget="$5.00", shield=True, filter=["secrets"])

   researcher = Agent(
       role="Researcher",
       goal="Find the latest AI trends",
       llm="gpt-4o",
   )

   task = Task(
       description="Research the latest AI trends",
       agent=researcher,
   )

   crew = Crew(agents=[researcher], tasks=[task])
   result = crew.kickoff()

   print(agentarmor.report())
   agentarmor.teardown()

Pydantic AI
-----------

.. code-block:: python

   import agentarmor
   from pydantic_ai import Agent

   agentarmor.init(budget="$2.00", shield=True, filter=["secrets"])

   agent = Agent(
       "openai-responses:gpt-5.2",
       instructions="Give concise, practical answers for engineers.",
   )
   result = agent.run_sync("Explain why runtime safety matters for agents.")

   print(result.output)
   print(agentarmor.report())
   agentarmor.teardown()

Google ADK
----------

.. code-block:: python

   import agentarmor
   from google.adk.agents.llm_agent import Agent

   agentarmor.init(budget="$2.00", shield=True, record=True)

   def get_status(service: str) -> dict:
       return {"service": service, "status": "green"}

   root_agent = Agent(
       model="gemini-2.5-flash",
       name="root_agent",
       description="Answers operational questions with a small toolset.",
       instruction=(
           "You are a helpful ops assistant. Use the get_status tool when a "
           "service-health question appears."
       ),
       tools=[get_status],
   )

Agno / Phidata
--------------

.. code-block:: python

   import agentarmor
   from agno.agent import Agent
   from agno.models.openai import OpenAIResponses

   agentarmor.init(budget="$2.00", shield=True, record=True)

   agent = Agent(
       model=OpenAIResponses(id="gpt-5.2"),
       instructions=["Keep answers practical and concise."],
       markdown=True,
   )
   response = agent.run("Summarize the purpose of runtime tool guardrails.")

   print(response.content)
   print(agentarmor.report())
   agentarmor.teardown()

For a tool-policy-focused Agno example, see
``examples/agno_tool_policy_example.py``.

AutoGen
-------

.. code-block:: python

   import agentarmor
   from autogen import AssistantAgent, UserProxyAgent

   agentarmor.init(budget="$5.00", shield=True, record=True)

   assistant = AssistantAgent("assistant", llm_config={"model": "gpt-4o"})
   user_proxy = UserProxyAgent("user_proxy", code_execution_config=False)

   user_proxy.initiate_chat(assistant, message="Write a Python function...")

   print(agentarmor.report())
   agentarmor.teardown()
