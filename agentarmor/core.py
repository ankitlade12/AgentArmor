import time
import openai

from .modules.budget import BudgetModule
from .modules.shield import ShieldModule
from .modules.filter import FilterModule
from .modules.recorder import RecorderModule

class ArmorCore:
    def __init__(self, budget, shield, filter, record):
        self.modules = {}
        self._original_openai = None
        self._original_anthropic = None

        if budget:
            self.modules["budget"] = BudgetModule(limit=budget)
        if shield:
            self.modules["shield"] = ShieldModule()
        if filter:
            self.modules["filter"] = FilterModule(rules=filter)
        if record:
            self.modules["recorder"] = RecorderModule()

    def patch(self):
        # Patch OpenAI
        self._original_openai = openai.chat.completions.create
        openai.chat.completions.create = self._wrap(self._original_openai, provider="openai")

        # Patch Anthropic
        try:
            import anthropic as ant
            self._original_anthropic = ant.Anthropic.messages.create
            ant.Anthropic.messages.create = self._wrap(self._original_anthropic, provider="anthropic")
        except ImportError:
            pass # Anthropic optional

    def _wrap(self, original_fn, provider):
        def wrapped(*args, **kwargs):
            messages = kwargs.get("messages", [])
            model = kwargs.get("model", "unknown")
            user_input = messages[-1]["content"] if messages else ""

            # PRE-CALL PHASE
            if "shield" in self.modules:
                self.modules["shield"].scan(user_input)  # raises InjectionDetected if found

            if "budget" in self.modules:
                self.modules["budget"].pre_check(model, messages)  # raises BudgetExhausted if over

            # CALL
            t0 = time.perf_counter()
            response = original_fn(*args, **kwargs)
            latency_ms = (time.perf_counter() - t0) * 1000

            # POST-CALL PHASE
            output_text = self._extract_output(response, provider)

            if "filter" in self.modules:
                output_text = self.modules["filter"].scan(output_text)  # redacts or raises
                
                # We need to inject the filtered text back into the response object
                self._inject_output(response, provider, output_text)

            if "budget" in self.modules:
                self.modules["budget"].post_record(model, response)

            if "recorder" in self.modules:
                self.modules["recorder"].log(
                    provider=provider,
                    model=model,
                    input_messages=messages,
                    output=output_text,
                    latency_ms=latency_ms
                )

            return response
        return wrapped

    def _extract_output(self, response, provider):
        try:
            if provider == "openai":
                return response.choices[0].message.content
            elif provider == "anthropic":
                return response.content[0].text
        except Exception:
            return ""

    def _inject_output(self, response, provider, output_text):
        try:
            if provider == "openai":
                response.choices[0].message.content = output_text
            elif provider == "anthropic":
                response.content[0].text = output_text
        except Exception:
            pass

    def unpatch(self):
        if self._original_openai:
            openai.chat.completions.create = self._original_openai
        
        if self._original_anthropic:
            import anthropic as ant
            ant.Anthropic.messages.create = self._original_anthropic

    def report(self):
        r = {}
        for name, module in self.modules.items():
            if hasattr(module, "report"):
                r[name] = module.report()
        return r
