import threading
from agentarmor.modules.cost_tags import CostTagsModule, set_tag, clear_tag, get_tag
from agentarmor.hooks import RequestContext, ResponseContext


def _make_res(model="gpt-4o", cost=0.005):
    req = RequestContext(messages=[{"role": "user", "content": "hello"}], model=model)
    return ResponseContext(
        text="response",
        model=model,
        provider="openai",
        request=req,
        cost=cost,
    )


# ---------------------------------------------------------------------------
# Basic tagging
# ---------------------------------------------------------------------------

def test_cost_tags_records_with_tag():
    module = CostTagsModule()
    set_tag("summarization")
    module.post_record(_make_res(cost=0.01))
    clear_tag()

    report = module.report()
    assert "summarization" in report["by_tag"]
    assert report["by_tag"]["summarization"]["calls"] == 1
    assert report["by_tag"]["summarization"]["spent"] == "$0.0100"


def test_cost_tags_default_tag_when_unset():
    module = CostTagsModule(default_tag="untagged")
    clear_tag()
    module.post_record(_make_res(cost=0.005))

    report = module.report()
    assert "untagged" in report["by_tag"]
    assert report["by_tag"]["untagged"]["calls"] == 1


def test_cost_tags_multiple_tags():
    module = CostTagsModule()

    set_tag("code-gen")
    module.post_record(_make_res(cost=0.01))
    module.post_record(_make_res(cost=0.02))

    set_tag("chat")
    module.post_record(_make_res(cost=0.005))

    clear_tag()

    report = module.report()
    assert report["by_tag"]["code-gen"]["calls"] == 2
    assert report["by_tag"]["code-gen"]["spent"] == "$0.0300"
    assert report["by_tag"]["chat"]["calls"] == 1
    assert report["by_tag"]["chat"]["spent"] == "$0.0050"


def test_cost_tags_tracks_models():
    module = CostTagsModule()
    set_tag("analysis")
    module.post_record(_make_res(model="gpt-4o", cost=0.01))
    module.post_record(_make_res(model="gpt-4o-mini", cost=0.001))
    clear_tag()

    report = module.report()
    models = report["by_tag"]["analysis"]["models"]
    assert "gpt-4o" in models
    assert "gpt-4o-mini" in models


# ---------------------------------------------------------------------------
# Tag context variable API
# ---------------------------------------------------------------------------

def test_set_and_get_tag():
    set_tag("my-tag")
    assert get_tag() == "my-tag"
    clear_tag()
    assert get_tag() is None


def test_clear_tag():
    set_tag("temp")
    clear_tag()
    assert get_tag() is None


# ---------------------------------------------------------------------------
# get_by_tag
# ---------------------------------------------------------------------------

def test_get_by_tag():
    module = CostTagsModule()
    set_tag("search")
    module.post_record(_make_res(cost=0.003))
    clear_tag()

    result = module.get_by_tag("search")
    assert result is not None
    assert result["calls"] == 1
    assert result["spent"] == "$0.0030"


def test_get_by_tag_missing():
    module = CostTagsModule()
    assert module.get_by_tag("nonexistent") is None


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

def test_cost_tags_thread_safety():
    module = CostTagsModule()

    def worker(tag_name, count):
        set_tag(tag_name)
        for _ in range(count):
            module.post_record(_make_res(cost=0.001))
        clear_tag()

    threads = [
        threading.Thread(target=worker, args=("thread-a", 10)),
        threading.Thread(target=worker, args=("thread-b", 5)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert module.total_tagged == 15


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def test_cost_tags_report():
    module = CostTagsModule()
    set_tag("test")
    module.post_record(_make_res(cost=0.01))
    clear_tag()

    report = module.report()
    assert report["total_tagged"] == 1
    assert "by_tag" in report
    assert "test" in report["by_tag"]


# ---------------------------------------------------------------------------
# Zero cost handling
# ---------------------------------------------------------------------------

def test_cost_tags_zero_cost():
    module = CostTagsModule()
    set_tag("free")
    module.post_record(_make_res(cost=0.0))
    clear_tag()

    report = module.report()
    assert report["by_tag"]["free"]["spent"] == "$0.0000"
    assert report["by_tag"]["free"]["calls"] == 1
