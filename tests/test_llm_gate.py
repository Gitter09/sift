"""Layer 3 (LLM gate) tests — fully mocked, no network."""

from types import SimpleNamespace

from sift.config import DisambiguatorConfig, LLMConfig
from sift.models import FeedbackItem
from sift.pipeline.llm_gate import LLMGate, _parse_verdicts


def _item(text: str) -> FeedbackItem:
    return FeedbackItem(source="reddit", product="X", text=text)


class _FakeClient:
    """Stands in for the OpenAI client; records prompts, returns canned content."""

    def __init__(self, content="", raise_exc=False):
        self._content = content
        self._raise = raise_exc
        self.calls = 0

        def _create(model, messages, **kwargs):
            self.calls += 1
            if self._raise:
                raise RuntimeError("boom")
            msg = SimpleNamespace(content=self._content)
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))


def _gate(content="", raise_exc=False, **cfg_overrides) -> LLMGate:
    cfg = DisambiguatorConfig(**cfg_overrides)
    gate = LLMGate(cfg, LLMConfig(api_key="test-key"))
    gate.client = _FakeClient(content=content, raise_exc=raise_exc)
    return gate


def test_parse_verdicts_handles_varied_formatting():
    parsed = _parse_verdicts("1: YES\n2. no\n3) Yes\n4 - NO")
    assert parsed == {1: True, 2: False, 3: True, 4: False}


def test_gate_keeps_and_rejects_per_llm_answer():
    gate = _gate(content="1: YES\n2: NO")
    items = [_item("a"), _item("b")]
    verdicts, stats = gate.adjudicate([(items[0], 0.5), (items[1], 0.5)], "Notion")

    assert verdicts[items[0].id] is True
    assert verdicts[items[1].id] is False
    assert stats.gated == 2 and stats.gate_yes == 1 and stats.gate_no == 1


def test_cost_guard_decides_overflow_by_score():
    # Only 1 item may hit the LLM; the rest fall back to combined vs midpoint (0.45).
    gate = _gate(content="1: YES", llm_gate_max_items=1)
    keep_item, overflow_keep, overflow_reject = _item("a"), _item("b"), _item("c")
    verdicts, stats = gate.adjudicate(
        [(keep_item, 0.5), (overflow_keep, 0.5), (overflow_reject, 0.1)], "Notion"
    )

    assert verdicts[keep_item.id] is True          # LLM
    assert verdicts[overflow_keep.id] is True       # 0.5 >= 0.45 midpoint
    assert verdicts[overflow_reject.id] is False    # 0.1 < 0.45 midpoint
    assert stats.gated == 1 and stats.over_cap == 2
    assert gate.client.calls == 1


def test_no_llm_falls_back_to_combined_score():
    gate = LLMGate(DisambiguatorConfig(), LLMConfig(api_key=""))  # no client
    assert gate.is_available is False
    keep, reject = _item("a"), _item("b")
    verdicts, stats = gate.adjudicate([(keep, 0.5), (reject, 0.4)], "Notion")

    assert verdicts[keep.id] is True and verdicts[reject.id] is False
    assert stats.over_cap == 2 and stats.gated == 0


def test_disabled_gate_has_no_client():
    gate = LLMGate(DisambiguatorConfig(llm_gate_enabled=False), LLMConfig(api_key="test-key"))
    assert gate.is_available is False


def test_llm_failure_falls_back_to_combined_score():
    gate = _gate(raise_exc=True)
    keep, reject = _item("a"), _item("b")
    verdicts, _ = gate.adjudicate([(keep, 0.5), (reject, 0.3)], "Notion")

    assert verdicts[keep.id] is True and verdicts[reject.id] is False


def test_empty_candidates_returns_empty():
    gate = _gate(content="")
    verdicts, stats = gate.adjudicate([], "Notion")
    assert verdicts == {} and stats.gated == 0
    assert gate.client.calls == 0
