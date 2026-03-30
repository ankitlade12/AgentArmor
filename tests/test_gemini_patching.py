import sys
import types
import pytest


import agentarmor
from agentarmor.core import ArmorCore
from agentarmor.hooks import ResponseContext


def _create_mock_genai_module():
    """Create a fake google.genai module hierarchy for testing."""
    google_mod = types.ModuleType("google")
    genai_mod = types.ModuleType("google.genai")
    models_mod = types.ModuleType("google.genai.models")

    google_mod.genai = genai_mod
    genai_mod.models = models_mod

    class FakePart:
        def __init__(self, text=""):
            self.text = text

    class FakeContent:
        def __init__(self, text=""):
            self.parts = [FakePart(text)]

    class FakeCandidate:
        def __init__(self, text=""):
            self.content = FakeContent(text)

    class FakeUsageMetadata:
        def __init__(self, prompt_token_count=0, candidates_token_count=0):
            self.prompt_token_count = prompt_token_count
            self.candidates_token_count = candidates_token_count

    class FakeResponse:
        def __init__(self, text="hello", prompt_tokens=10, output_tokens=5):
            self.text = text
            self.candidates = [FakeCandidate(text)]
            self.usage_metadata = FakeUsageMetadata(prompt_tokens, output_tokens)

    class Models:
        def generate_content(self, model, contents, config=None, **kwargs):
            return FakeResponse("mocked gemini reply")

        def generate_content_stream(self, model, contents, config=None, **kwargs):
            return [FakeResponse("mocked "), FakeResponse("stream")]

    class AsyncModels:
        async def generate_content(self, model, contents, config=None, **kwargs):
            return FakeResponse("async mocked gemini reply")

        async def generate_content_stream(self, model, contents, config=None, **kwargs):
            yield FakeResponse("async mocked ")
            yield FakeResponse("stream")

    models_mod.Models = Models
    models_mod.AsyncModels = AsyncModels

    return google_mod, genai_mod, models_mod, Models, AsyncModels, FakeResponse


def _install_mock_genai():
    """Install mock google.genai into sys.modules."""
    google_mod, genai_mod, models_mod, Models, AsyncModels, FakeResponse = _create_mock_genai_module()
    sys.modules["google"] = google_mod
    sys.modules["google.genai"] = genai_mod
    sys.modules["google.genai.models"] = models_mod
    return google_mod, genai_mod, models_mod, Models, AsyncModels, FakeResponse


def _uninstall_mock_genai():
    """Remove mock google modules from sys.modules."""
    for key in ["google.genai.models", "google.genai", "google", "google.generativeai"]:
        sys.modules.pop(key, None)


class TestGeminiPatchUnpatch:
    def setup_method(self):
        self.google_mod, self.genai_mod, self.models_mod, self.Models, self.AsyncModels, self.FakeResponse = _install_mock_genai()

    def teardown_method(self):
        agentarmor.teardown()
        _uninstall_mock_genai()

    def test_patch_replaces_methods(self):
        original_sync = self.Models.generate_content
        original_async = self.AsyncModels.generate_content

        agentarmor.init()  # sets up the patch

        assert self.Models.generate_content is not original_sync
        assert self.AsyncModels.generate_content is not original_async

    def test_unpatch_restores_methods(self):
        original_sync = self.Models.generate_content
        original_async = self.AsyncModels.generate_content

        core = agentarmor.init()
        core.unpatch()

        assert self.Models.generate_content is original_sync
        assert self.AsyncModels.generate_content is original_async

    def test_sync_call_runs_hooks(self):
        core = agentarmor.init()

        hook_ran = False

        @core.registry.register_after_response
        def cb(ctx: ResponseContext):
            nonlocal hook_ran
            hook_ran = True
            assert ctx.text == "mocked gemini reply"
            assert ctx.provider == "gemini"
            assert ctx.model == "gemini-2.0-flash"
            return ctx

        model_api = self.Models()
        response = model_api.generate_content("gemini-2.0-flash", "Hello")

        assert hook_ran is True
        assert response.text == "mocked gemini reply"

    @pytest.mark.asyncio
    async def test_async_call_runs_hooks(self):
        core = agentarmor.init()

        hook_ran = False

        @core.registry.register_after_response
        def cb(ctx: ResponseContext):
            nonlocal hook_ran
            hook_ran = True
            assert ctx.text == "async mocked gemini reply"
            assert ctx.provider == "gemini"
            return ctx

        model_api = self.AsyncModels()
        response = await model_api.generate_content("gemini-2.0-flash", "Hello")

        assert hook_ran is True
        assert response.text == "async mocked gemini reply"


class TestGeminiRequestContext:
    def setup_method(self):
        self.google_mod, self.genai_mod, self.models_mod, self.Models, self.AsyncModels, self.FakeResponse = _install_mock_genai()

    def teardown_method(self):
        agentarmor.teardown()
        _uninstall_mock_genai()

    def test_string_contents_converted_to_messages(self):
        core = agentarmor.init()

        captured_ctx = None

        @core.registry.register_before_request
        def capture(ctx):
            nonlocal captured_ctx
            captured_ctx = ctx
            return ctx

        model_api = self.Models()
        model_api.generate_content("gemini-2.0-flash", "What is 2+2?")

        assert captured_ctx is not None
        assert len(captured_ctx.messages) == 1
        assert captured_ctx.messages[0]["role"] == "user"
        assert captured_ctx.messages[0]["parts"][0]["text"] == "What is 2+2?"
        assert captured_ctx.model == "gemini-2.0-flash"

    def test_list_contents_converted_to_messages(self):
        core = agentarmor.init()

        captured_ctx = None

        @core.registry.register_before_request
        def capture(ctx):
            nonlocal captured_ctx
            captured_ctx = ctx
            return ctx

        model_api = self.Models()
        model_api.generate_content("gemini-2.0-flash", [
            {"role": "user", "parts": [{"text": "Hello"}]},
            {"role": "model", "parts": [{"text": "Hi there"}]},
        ])

        assert len(captured_ctx.messages) == 2


class TestGeminiOutputExtraction:
    def setup_method(self):
        self.google_mod, self.genai_mod, self.models_mod, self.Models, self.AsyncModels, self.FakeResponse = _install_mock_genai()

    def teardown_method(self):
        _uninstall_mock_genai()

    def test_extract_output(self):
        core = ArmorCore()
        response = self.FakeResponse("test output")
        assert core._extract_output(response, "gemini") == "test output"

    def test_inject_output(self):
        core = ArmorCore()
        response = self.FakeResponse("original")
        core._inject_output(response, "gemini", "modified")
        assert response.candidates[0].content.parts[0].text == "modified"

    def test_extract_output_empty_candidates_returns_empty_string(self):
        core = ArmorCore()
        response = self.FakeResponse("blocked")
        response.candidates = []  
        assert core._extract_output(response, "gemini") == ""

    def test_inject_output_empty_candidates_is_noop(self):
        core = ArmorCore()
        response = self.FakeResponse("blocked")
        response.candidates = []
        core._inject_output(response, "gemini", "should not appear")  


class TestGeminiUsageExtraction:
    def setup_method(self):
        self.google_mod, self.genai_mod, self.models_mod, self.Models, self.AsyncModels, self.FakeResponse = _install_mock_genai()

    def teardown_method(self):
        agentarmor.teardown()
        _uninstall_mock_genai()

    def test_non_stream_usage(self):
        core = ArmorCore()
        response = self.FakeResponse("hello", prompt_tokens=100, output_tokens=50)
        usage = core._extract_non_stream_usage(response, provider="gemini")
        assert usage is not None
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 50

    def test_usage_recorded_in_hook(self):
        core = agentarmor.init()

        captured_usage = None

        @core.registry.register_after_response
        def cb(ctx: ResponseContext):
            nonlocal captured_usage
            captured_usage = ctx.usage
            return ctx

        model_api = self.Models()
        model_api.generate_content("gemini-2.0-flash", "Hello")

        assert captured_usage is not None
        assert captured_usage["input_tokens"] == 10
        assert captured_usage["output_tokens"] == 5


class TestGeminiGracefulSkip:
    def test_patch_skips_when_not_installed(self):
        """Patching should not raise when google-genai is not installed."""
        saved = {}
        keys_to_remove = [k for k in sys.modules if k.startswith("google")]
        for key in keys_to_remove:
            saved[key] = sys.modules.pop(key)

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name.startswith("google"):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = mock_import
        try:
            core = ArmorCore()
            core.patch()
            assert "genai_sync" not in core._originals
            assert "genai_async" not in core._originals

            core.unpatch()
        finally:
            builtins.__import__ = original_import
            sys.modules.update(saved)


class TestGeminiContentsConversion:
    def test_string_contents(self):
        result = ArmorCore._gemini_contents_to_messages("hello")
        assert result == [{"role": "user", "parts": [{"text": "hello"}]}]

    def test_none_contents(self):
        result = ArmorCore._gemini_contents_to_messages(None)
        assert result == []

    def test_dict_contents(self):
        d = {"role": "user", "parts": [{"text": "hi"}]}
        result = ArmorCore._gemini_contents_to_messages(d)
        assert result == [d]

    def test_list_of_strings(self):
        result = ArmorCore._gemini_contents_to_messages(["hello", "world"])
        assert len(result) == 2
        assert result[0]["parts"][0]["text"] == "hello"
        assert result[1]["parts"][0]["text"] == "world"

    def test_list_of_dicts(self):
        msgs = [
            {"role": "user", "parts": [{"text": "a"}]},
            {"role": "model", "parts": [{"text": "b"}]},
        ]
        result = ArmorCore._gemini_contents_to_messages(msgs)
        assert result == msgs
