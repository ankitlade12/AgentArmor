import sys
import types
import pytest
from unittest.mock import MagicMock, patch

import agentarmor
from agentarmor.core import ArmorCore
from agentarmor.hooks import ResponseContext


def _create_mock_genai_module():
    """Create a fake google.generativeai module hierarchy for testing."""
    # Build the module tree: google -> google.generativeai
    google_mod = types.ModuleType("google")
    genai_mod = types.ModuleType("google.generativeai")
    google_mod.generativeai = genai_mod

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
            self._text = text
            self.candidates = [FakeCandidate(text)]
            self.usage_metadata = FakeUsageMetadata(prompt_tokens, output_tokens)

        @property
        def text(self):
            return self.candidates[0].content.parts[0].text

    class GenerativeModel:
        def __init__(self, model_name="gemini-2.0-flash"):
            self.model_name = model_name
            self._model_name = model_name

        def generate_content(self, contents, **kwargs):
            return FakeResponse("mocked gemini reply")

        async def generate_content_async(self, contents, **kwargs):
            return FakeResponse("async mocked gemini reply")

    genai_mod.GenerativeModel = GenerativeModel
    genai_mod.FakeResponse = FakeResponse
    genai_mod.FakePart = FakePart
    genai_mod.FakeContent = FakeContent
    genai_mod.FakeCandidate = FakeCandidate
    genai_mod.FakeUsageMetadata = FakeUsageMetadata

    return google_mod, genai_mod, GenerativeModel, FakeResponse


def _install_mock_genai():
    """Install mock google.generativeai into sys.modules."""
    google_mod, genai_mod, GenerativeModel, FakeResponse = _create_mock_genai_module()
    sys.modules["google"] = google_mod
    sys.modules["google.generativeai"] = genai_mod
    return google_mod, genai_mod, GenerativeModel, FakeResponse


def _uninstall_mock_genai():
    """Remove mock google modules from sys.modules."""
    for key in ["google.generativeai", "google"]:
        sys.modules.pop(key, None)


class TestGeminiPatchUnpatch:
    def setup_method(self):
        self.google_mod, self.genai_mod, self.GenerativeModel, self.FakeResponse = _install_mock_genai()

    def teardown_method(self):
        agentarmor.teardown()
        _uninstall_mock_genai()

    def test_patch_replaces_methods(self):
        original_sync = self.GenerativeModel.generate_content
        original_async = self.GenerativeModel.generate_content_async

        core = agentarmor.init()

        assert self.GenerativeModel.generate_content is not original_sync
        assert self.GenerativeModel.generate_content_async is not original_async

    def test_unpatch_restores_methods(self):
        original_sync = self.GenerativeModel.generate_content
        original_async = self.GenerativeModel.generate_content_async

        core = agentarmor.init()
        core.unpatch()

        assert self.GenerativeModel.generate_content is original_sync
        assert self.GenerativeModel.generate_content_async is original_async

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

        model = self.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content("Hello")

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

        model = self.GenerativeModel("gemini-2.0-flash")
        response = await model.generate_content_async("Hello")

        assert hook_ran is True
        assert response.text == "async mocked gemini reply"


class TestGeminiRequestContext:
    def setup_method(self):
        self.google_mod, self.genai_mod, self.GenerativeModel, self.FakeResponse = _install_mock_genai()

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

        model = self.GenerativeModel("gemini-2.0-flash")
        model.generate_content("What is 2+2?")

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

        model = self.GenerativeModel("gemini-2.0-flash")
        model.generate_content([
            {"role": "user", "parts": [{"text": "Hello"}]},
            {"role": "model", "parts": [{"text": "Hi there"}]},
        ])

        assert len(captured_ctx.messages) == 2


class TestGeminiOutputExtraction:
    def setup_method(self):
        self.google_mod, self.genai_mod, self.GenerativeModel, self.FakeResponse = _install_mock_genai()

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


class TestGeminiUsageExtraction:
    def setup_method(self):
        self.google_mod, self.genai_mod, self.GenerativeModel, self.FakeResponse = _install_mock_genai()

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

        model = self.GenerativeModel("gemini-2.0-flash")
        model.generate_content("Hello")

        assert captured_usage is not None
        assert captured_usage["input_tokens"] == 10
        assert captured_usage["output_tokens"] == 5


class TestGeminiGracefulSkip:
    def test_patch_skips_when_not_installed(self):
        """Patching should not raise when google-generativeai is not installed."""
        # Save and remove all google-related modules so the import fails
        saved = {}
        keys_to_remove = [k for k in sys.modules if k == "google" or k.startswith("google.")]
        for key in keys_to_remove:
            saved[key] = sys.modules.pop(key)

        # Also block fresh imports by temporarily making import raise ImportError
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "google.generativeai" or name == "google":
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = mock_import
        try:
            core = ArmorCore()
            # Should not raise
            core.patch()
            assert "gemini_sync" not in core._originals
            assert "gemini_async" not in core._originals

            # unpatch should also not raise
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
