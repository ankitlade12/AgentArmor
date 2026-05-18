Framework Integrations
======================

AgentArmor works out-of-the-box with **every major AI framework**. Because it
monkey-patches the underlying ``openai`` and ``anthropic`` clients directly at
the network level, you don't need framework-specific callbacks or middleware.

Just call ``agentarmor.init()`` at the top of your script and it will
automatically protect all LLM calls, regardless of which framework wraps them.

Supported Frameworks
--------------------

- **LangChain / LangGraph**
- **LlamaIndex**
- **CrewAI**
- **Agno / Phidata**
- **AutoGen**
- **SmolAgents**
- Custom raw SDK scripts

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
