import json
import urllib.request

import pytest

from creative_agent.providers import LLMIdeaProvider, MockIdeaProvider, decode_chat_response


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/json"):
        self.body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self.body.splitlines(keepends=True))

    def read(self):
        return self.body


def fake_urlopen(monkeypatch, body, content_type="application/json"):
    calls = []

    def urlopen(request, timeout):
        calls.append((json.loads(request.data), timeout))
        return FakeResponse(body, content_type)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return calls


def test_json_chat_body(monkeypatch):
    body = json.dumps({"choices": [{"message": {"content": '{"objective": "play"}'}}]}).encode()
    calls = fake_urlopen(monkeypatch, body)
    provider = LLMIdeaProvider(api_key="test", timeout=12.5)

    assert decode_chat_response(body, "application/json") == '{"objective": "play"}'
    assert provider._call("prompt") == {"objective": "play"}
    assert calls == [({"model": "hermes-main", "messages": [
        {"role": "system", "content": "You are a creative systems architect and game designer. Always output strict, valid JSON without extra chat or conversational filler."},
        {"role": "user", "content": "prompt"},
    ], "temperature": 0.85, "stream": True}, 12.5)]


def test_sse_chat_body_detected_without_stream_header(monkeypatch):
    body = (b'data: {"choices":[{"delta":{"content":"{\\"objective\\": "}}]}\n'
            b'data: {"choices":[{"delta":{"content":"\\"play\\"}"}}]}\n'
            b'data: [DONE]\n')
    fake_urlopen(monkeypatch, body)

    assert decode_chat_response(body, "application/json") == '{"objective": "play"}'
    assert LLMIdeaProvider(api_key="test")._call("prompt") == {"objective": "play"}


def test_sse_fenced_json(monkeypatch):
    body = (b'data: {"choices":[{"delta":{"content":"```json\\n{\\"count\\": 1}"}}]}\n'
            b'data: {"choices":[{"delta":{"content":"\\n```"}}]}\n'
            b'data: [DONE]\n')
    fake_urlopen(monkeypatch, body, "text/event-stream")

    assert LLMIdeaProvider(api_key="test")._call("prompt") == {"count": 1}


def test_malformed_sse_chunk_is_skipped():
    body = (b'data: {bad json}\n'
            b'data: {"choices":[{"delta":{"content":"hello"}}]}\n'
            b'data: {"choices":[]}\n'
            b'data: [DONE]\n')

    assert decode_chat_response(body, "text/event-stream") == "hello"


@pytest.mark.parametrize("body", [b"", b"data: [DONE]\n", b'{"choices":[]}'])
def test_empty_chat_content_raises_value_error(body):
    with pytest.raises(ValueError):
        decode_chat_response(body)


def test_strict_mode_propagates_from_every_public_method(monkeypatch):
    provider = LLMIdeaProvider(api_key="test", strict=True)
    mock = MockIdeaProvider()
    problem = mock.normalize("Improve a game")
    candidate = mock.mine_baselines(problem, 1)[0]

    def fail(*args, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(provider, "_call", fail)
    calls = [
        lambda: provider.normalize("Improve a game"),
        lambda: provider.mine_baselines(problem, 1),
        lambda: provider.generate(problem, "Inversion", (), 1),
        lambda: provider.canonicalize(problem, candidate),
        lambda: provider.assess(problem, candidate),
        lambda: provider.describe_niche(problem, candidate),
    ]
    for call in calls:
        with pytest.raises(RuntimeError, match="model unavailable"):
            call()
    assert provider.fallbacks == 0


def test_non_strict_mode_counts_each_mock_fallback(monkeypatch):
    provider = LLMIdeaProvider(api_key="test")
    mock = MockIdeaProvider()
    problem = mock.normalize("Improve a game")
    candidate = mock.mine_baselines(problem, 1)[0]

    def fail(*args, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(provider, "_call", fail)
    assert provider.normalize("Improve a game") == problem
    assert provider.mine_baselines(problem, 1) == mock.mine_baselines(problem, 1)
    assert provider.generate(problem, "Inversion", (), 1) == mock.generate(problem, "Inversion", (), 1)
    assert provider.canonicalize(problem, candidate) == mock.canonicalize(problem, candidate)
    assert provider.assess(problem, candidate) == mock.assess(problem, candidate)
    assert provider.describe_niche(problem, candidate) == mock.describe_niche(problem, candidate)
    assert provider.fallbacks == 6
