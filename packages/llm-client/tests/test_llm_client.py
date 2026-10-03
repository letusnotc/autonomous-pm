"""Regression tests for the shared LLM client."""
import httpx
import pytest

import llm_client


class Recorder:
    """Stands in for the network: records the request and returns a canned reply."""

    def __init__(self, reply):
        self.reply = reply
        self.request = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.request = request
        return httpx.Response(200, json=self.reply)


@pytest.fixture
def network(monkeypatch):
    def install(reply):
        recorder = Recorder(reply)
        real_client = httpx.AsyncClient
        monkeypatch.setattr(llm_client.httpx, "AsyncClient",
                            lambda **kw: real_client(transport=httpx.MockTransport(recorder), **kw))
        return recorder
    return install


async def test_gemini_key_is_sent_in_a_header_never_the_url(network, monkeypatch):
    """APM-15: the key leaked into logs because it was part of the request URL."""
    monkeypatch.setattr(llm_client, "GEMINI_API_KEY", "secret-test-key")
    rec = network({"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]})

    out = await llm_client.call_llm("prompt", "system", provider="gemini")

    assert out == '{"ok": true}'
    assert "secret-test-key" not in str(rec.request.url)
    assert "key=" not in str(rec.request.url)
    assert rec.request.headers["x-goog-api-key"] == "secret-test-key"


async def test_gemini_errors_do_not_expose_the_key(monkeypatch):
    monkeypatch.setattr(llm_client, "GEMINI_API_KEY", "secret-test-key")
    real_client = httpx.AsyncClient
    failing = httpx.MockTransport(lambda req: httpx.Response(400, json={"error": "bad"}))
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **kw: real_client(transport=failing, **kw))

    with pytest.raises(httpx.HTTPStatusError) as err:
        await llm_client.call_llm("prompt", "system", provider="gemini")
    assert "secret-test-key" not in str(err.value)


async def test_missing_key_fails_fast(monkeypatch):
    monkeypatch.setattr(llm_client, "GEMINI_API_KEY", "")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY not set"):
        await llm_client.call_llm("prompt", "system", provider="gemini")


@pytest.mark.parametrize("raw", ['{"a": 1}', '```json\n{"a": 1}\n```', '```\n{"a": 1}\n```'])
def test_parse_json_response_strips_markdown_fences(raw):
    assert llm_client.parse_json_response(raw) == {"a": 1}
