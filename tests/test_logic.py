"""
Unit tests that run with no Redis and no network — they cover the pure logic
(model routing, cost math, response parsing, schema validation). Run: pytest -q
"""

from app.core.cost import estimate_cost
from app.providers.minimax import MiniMaxProvider, resolve_model
from app.schemas import ChatRequest, Message


def test_resolve_logical_models():
    assert resolve_model("fast", "MiniMax-M2.5") == "MiniMax-M2.5"
    assert resolve_model("smart", "MiniMax-M2.5") == "MiniMax-M3"


def test_resolve_passthrough_concrete_model():
    # A concrete id should pass through untouched.
    assert resolve_model("MiniMax-M2.7", "MiniMax-M2.5") == "MiniMax-M2.7"


def test_resolve_empty_falls_back_to_default():
    assert resolve_model("", "MiniMax-M2.5") == "MiniMax-M2.5"


def test_estimate_cost_known_model():
    # 1M input + 1M output of M3 at 0.70 / 2.80.
    cost = estimate_cost("MiniMax-M3", 1_000_000, 1_000_000)
    assert abs(cost - (0.70 + 2.80)) < 1e-6


def test_estimate_cost_unknown_model_uses_default_rate():
    cost = estimate_cost("some-future-model", 1_000_000, 0)
    assert cost == 0.30


def test_parse_handles_string_content():
    data = {
        "model": "MiniMax-M2.5",
        "choices": [{"message": {"role": "assistant", "content": "hello"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3},
    }
    result = MiniMaxProvider._parse(data, "MiniMax-M2.5")
    assert result.content == "hello"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 3


def test_parse_handles_list_content_blocks():
    data = {
        "model": "MiniMax-M3",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "text": "ignore me"},
                        {"type": "text", "text": "visible answer"},
                    ],
                }
            }
        ],
        "usage": {},
    }
    result = MiniMaxProvider._parse(data, "MiniMax-M3")
    assert result.content == "visible answer"


def test_chat_request_defaults():
    req = ChatRequest(messages=[Message(role="user", content="hi")])
    assert req.model == "smart"
    assert req.tenant == "default"
    assert req.no_cache is False
