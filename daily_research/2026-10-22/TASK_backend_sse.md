# TASK (Backend / TDD): SSE-tolerant LLMIdeaProvider._call + strict (no silent mock) mode

Target file: creative_agent/providers.py (class LLMIdeaProvider). Test runner: .venv/bin/pytest

## Problem (measured)
9Router (http://127.0.0.1:20128/v1/chat/completions) answers with `text/event-stream`
(`data: {"choices":[{"delta":{"content":"..."}}]}` ... `data: [DONE]`) regardless of `"stream": false`.
`LLMIdeaProvider._call` does `json.loads(resp.read())` -> JSONDecodeError -> every public method
(normalize/mine_baselines/generate/canonicalize/assess/describe_niche) swallows it with `except Exception`
and silently falls back to MockIdeaProvider. That contaminates "LLM" runs with mock data.

## Required (contract)
1. Add a pure module-level helper `decode_chat_response(raw: bytes, content_type: str | None = None) -> str`
   in providers.py returning the assistant text. Must support BOTH:
   (a) normal JSON `{"choices":[{"message":{"content":...}}]}`,
   (b) SSE stream (accumulate `choices[0].delta.content` of every `data:` line; ignore `[DONE]` and malformed chunks).
   Detect by content (stripped body starts with `data:` or contains "\ndata: "), not only by header.
   Raise ValueError if no content could be extracted.
2. `LLMIdeaProvider._call` must use it and send `"stream": True`; keep the markdown-fence stripping.
   Add constructor kwarg `timeout: float = 90.0` (was hardcoded 45) and use it in urlopen.
3. Add constructor kwarg `strict: bool = False`. When strict=True, any exception inside
   normalize/mine_baselines/generate/canonicalize/assess/describe_niche MUST propagate (no mock fallback).
   Default False keeps legacy behaviour. In non-strict mode, increment `self.fallbacks: int` (init 0) on every fallback to Mock.
4. Do NOT change Protocol signatures, and do NOT edit any file other than providers.py and the new test file.
5. Tests: create tests/test_llm_provider_sse.py (zero network; monkeypatch `urllib.request.urlopen` with a fake
   response object that is iterable/readable and has `.headers`), covering: JSON body, SSE body,
   SSE with fenced ```json block, malformed chunk skipped, empty -> ValueError, strict=True propagates,
   strict=False falls back and increments `fallbacks`.
6. Done only when `.venv/bin/pytest -q` in the project root exits 0 (currently 89 pass). Print the final pytest tail.
   No network calls, no background loops, no tuning. If something fails twice, STOP and report the failure evidence (Report-First).
