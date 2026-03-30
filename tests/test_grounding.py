import pytest
from agentarmor.modules.grounding import GroundingGuardModule
from agentarmor.exceptions import HallucinationDetected
from agentarmor.hooks import RequestContext, ResponseContext


SOURCE_DOC = (
    "The Eiffel Tower is located in Paris, France. "
    "It was built in 1889 and stands 330 meters tall. "
    "Gustave Eiffel's company designed and built the tower. "
    "The tower was the tallest man-made structure in the world for 41 years."
)


def _make_req_ctx(messages=None, model="gpt-4o"):
    if messages is None:
        messages = [{"role": "user", "content": "Tell me about the Eiffel Tower."}]
    return RequestContext(messages=messages, model=model)


def _make_res_ctx(text, req_ctx=None):
    if req_ctx is None:
        req_ctx = _make_req_ctx()
    return ResponseContext(
        text=text,
        model=req_ctx.model,
        provider="openai",
        request=req_ctx,
    )


# ---------------------------------------------------------------------------
# Well-grounded response passes
# ---------------------------------------------------------------------------

def test_grounded_response_passes():
    module = GroundingGuardModule(
        sources=[SOURCE_DOC],
        threshold=0.3,
        on_detect="block",
        extract_from_messages=False,
    )
    ctx = _make_res_ctx(
        "The Eiffel Tower is located in Paris, France. It was built in 1889."
    )
    result = module.post_filter(ctx)
    assert result is ctx
    assert module.hallucinations_detected == 0
    assert module.checks_run == 1
    assert len(module.scores) == 1
    assert module.scores[0] >= 0.3


# ---------------------------------------------------------------------------
# Hallucinated response fails
# ---------------------------------------------------------------------------

def test_hallucinated_response_detected():
    module = GroundingGuardModule(
        sources=[SOURCE_DOC],
        threshold=0.5,
        on_detect="block",
        extract_from_messages=False,
    )
    ctx = _make_res_ctx(
        "The Colosseum is located in Rome, Italy. "
        "It was built by Emperor Vespasian in 72 AD and seats 50000 spectators."
    )
    with pytest.raises(HallucinationDetected, match="grounding score"):
        module.post_filter(ctx)
    assert module.hallucinations_detected == 1


# ---------------------------------------------------------------------------
# Number verification
# ---------------------------------------------------------------------------

def test_number_verification_matching():
    module = GroundingGuardModule(
        sources=[SOURCE_DOC],
        threshold=0.0,
        on_detect="warn",
        check_claims=False,
        check_names=False,
        check_numbers=True,
        extract_from_messages=False,
    )
    ctx = _make_res_ctx("The tower is 330 meters tall, built in 1889.")
    module.post_filter(ctx)
    # Numbers 330 and 1889 are in the source
    assert module.scores[-1] > 0.5


def test_number_verification_mismatch():
    module = GroundingGuardModule(
        sources=[SOURCE_DOC],
        threshold=0.0,
        on_detect="warn",
        check_claims=False,
        check_names=False,
        check_numbers=True,
        extract_from_messages=False,
    )
    ctx = _make_res_ctx("The tower is 500 meters tall and was built in 1920.")
    module.post_filter(ctx)
    # Numbers 500 and 1920 are NOT in the source
    number_score = module.scores[-1]
    assert number_score < 0.5


# ---------------------------------------------------------------------------
# Name verification
# ---------------------------------------------------------------------------

def test_name_verification_matching():
    module = GroundingGuardModule(
        sources=[SOURCE_DOC],
        threshold=0.0,
        on_detect="warn",
        check_claims=False,
        check_numbers=False,
        check_names=True,
        extract_from_messages=False,
    )
    # "Gustave Eiffel" and "Paris" are in the source
    ctx = _make_res_ctx("Gustave Eiffel designed the tower in Paris.")
    module.post_filter(ctx)
    assert module.scores[-1] >= 0.4


def test_name_verification_mismatch():
    module = GroundingGuardModule(
        sources=[SOURCE_DOC],
        threshold=0.0,
        on_detect="warn",
        check_claims=False,
        check_numbers=False,
        check_names=True,
        extract_from_messages=False,
    )
    ctx = _make_res_ctx("Leonardo Da Vinci designed the tower in Berlin.")
    module.post_filter(ctx)
    name_score = module.scores[-1]
    assert name_score < 0.5


# ---------------------------------------------------------------------------
# Source extraction from system messages
# ---------------------------------------------------------------------------

def test_source_extraction_from_system_messages():
    module = GroundingGuardModule(
        sources=[],
        threshold=0.3,
        on_detect="block",
        extract_from_messages=True,
    )
    messages = [
        {"role": "system", "content": SOURCE_DOC},
        {"role": "user", "content": "Tell me about the Eiffel Tower."},
    ]
    req_ctx = _make_req_ctx(messages=messages)
    module.pre_check(req_ctx)
    assert len(module._session_sources) > 0

    # Now a grounded response should pass
    ctx = _make_res_ctx(
        "The Eiffel Tower was built in 1889 in Paris, France.",
        req_ctx=req_ctx,
    )
    result = module.post_filter(ctx)
    assert result is ctx
    assert module.hallucinations_detected == 0


# ---------------------------------------------------------------------------
# Block vs warn vs flag modes
# ---------------------------------------------------------------------------

def test_block_mode_raises():
    module = GroundingGuardModule(
        sources=[SOURCE_DOC],
        threshold=0.99,  # Nearly impossible to pass
        on_detect="block",
        extract_from_messages=False,
    )
    ctx = _make_res_ctx("Something completely unrelated about quantum physics and black holes.")
    with pytest.raises(HallucinationDetected):
        module.post_filter(ctx)


def test_warn_mode_does_not_raise(capsys):
    module = GroundingGuardModule(
        sources=[SOURCE_DOC],
        threshold=0.99,
        on_detect="warn",
        extract_from_messages=False,
    )
    ctx = _make_res_ctx("Something completely unrelated about quantum physics and black holes.")
    result = module.post_filter(ctx)
    assert result is ctx
    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "grounding score" in captured.out.lower()


def test_flag_mode_prepends_warning():
    module = GroundingGuardModule(
        sources=[SOURCE_DOC],
        threshold=0.99,
        on_detect="flag",
        extract_from_messages=False,
    )
    original_text = "Something completely unrelated about quantum physics and black holes."
    ctx = _make_res_ctx(original_text)
    result = module.post_filter(ctx)
    assert result.text.startswith("[GROUNDING WARNING:")
    assert original_text in result.text


# ---------------------------------------------------------------------------
# Custom threshold
# ---------------------------------------------------------------------------

def test_custom_threshold():
    # With a very low threshold, even a poor match should pass
    module = GroundingGuardModule(
        sources=[SOURCE_DOC],
        threshold=0.01,
        on_detect="block",
        extract_from_messages=False,
    )
    ctx = _make_res_ctx("Random unrelated text about pizza and submarines.")
    result = module.post_filter(ctx)
    assert result is ctx
    assert module.hallucinations_detected == 0


# ---------------------------------------------------------------------------
# Empty sources = no check (passes through)
# ---------------------------------------------------------------------------

def test_empty_sources_passes_through():
    module = GroundingGuardModule(
        sources=[],
        threshold=0.5,
        on_detect="block",
        extract_from_messages=False,
    )
    ctx = _make_res_ctx("Anything at all, even completely fabricated content.")
    result = module.post_filter(ctx)
    assert result is ctx
    assert module.checks_run == 0
    assert module.hallucinations_detected == 0


# ---------------------------------------------------------------------------
# N-gram overlap scoring
# ---------------------------------------------------------------------------

def test_ngram_overlap_identical():
    module = GroundingGuardModule(extract_from_messages=False)
    text = "the quick brown fox jumps over the lazy dog"
    score = module._ngram_overlap(text, text, n=3)
    assert score == 1.0


def test_ngram_overlap_no_match():
    module = GroundingGuardModule(extract_from_messages=False)
    score = module._ngram_overlap(
        "alpha beta gamma delta epsilon", "one two three four five six seven", n=3
    )
    assert score == 0.0


def test_ngram_overlap_partial():
    module = GroundingGuardModule(extract_from_messages=False)
    source = "the quick brown fox jumps over the lazy dog"
    response = "the quick brown fox flies over the happy cat"
    score = module._ngram_overlap(response, source, n=3)
    assert 0.0 < score < 1.0


# ---------------------------------------------------------------------------
# Report accuracy
# ---------------------------------------------------------------------------

def test_report_accuracy():
    module = GroundingGuardModule(
        sources=[SOURCE_DOC],
        threshold=0.3,
        on_detect="warn",
        extract_from_messages=False,
    )
    # Run two checks
    ctx1 = _make_res_ctx("The Eiffel Tower was built in 1889 in Paris, France.")
    module.post_filter(ctx1)

    ctx2 = _make_res_ctx("Random text about volcanoes and deep sea creatures.")
    module.post_filter(ctx2)

    report = module.report()
    assert report["checks_run"] == 2
    assert report["source_count"] == 1
    assert "average_grounding_score" in report
    assert "min_score" in report
    assert isinstance(report["average_grounding_score"], float)
    assert isinstance(report["min_score"], float)
    assert report["min_score"] <= report["average_grounding_score"]


def test_report_empty():
    module = GroundingGuardModule(extract_from_messages=False)
    report = module.report()
    assert report["checks_run"] == 0
    assert report["hallucinations_detected"] == 0
    assert report["average_grounding_score"] == 0.0
    assert report["min_score"] is None
