import pytest
import httpx
from fastapi.testclient import TestClient

from gateway import main


client = TestClient(main.app)
AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def allow_test_token(monkeypatch):
    monkeypatch.setattr(main, "GATEWAY_TOKENS", {"test-token"})
    monkeypatch.setattr(main, "HERMES_API_KEY", "internal-test-key")


def test_chat_completions_forwards_openai_payload_without_rewriting(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        content = b'{"choices":[{"message":{"content":"review"}}]}'
        headers = {"content-type": "application/json"}

        def raise_for_status(self):
            pass

    async def post(self, url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(main.httpx.AsyncClient, "post", post)
    payload = {
        "model": "hermes",
        "messages": [{"role": "user", "content": "caller supplied\nreview context"}],
        "temperature": 0.3,
        "max_tokens": 4096,
        "stream": False,
        "top_p": 0.9,
    }

    response = client.post("/v1/chat/completions", headers=AUTH, json=payload)

    assert response.status_code == 200
    assert captured["json"] == payload
    assert response.content == Response.content


@pytest.mark.parametrize(
    ("headers", "message"),
    [
        ({}, "Invalid authorization header"),
        ({"Authorization": "Basic dGVzdC10b2tlbg=="}, "Invalid authorization header"),
        ({"Authorization": "Bearer wrong-token"}, "Invalid token"),
    ],
)
def test_chat_completions_rejects_missing_or_invalid_authorization(headers, message):
    response = client.post(
        "/v1/chat/completions",
        headers=headers,
        json={"model": "hermes", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "message": message,
            "type": "authentication_error",
            "param": None,
            "code": None,
        }
    }


def test_health_does_not_require_authorization():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_completions_rejects_invalid_upstream_json(monkeypatch):
    class Response:
        status_code = 200
        content = b"not-json"
        headers = {"content-type": "text/plain"}

        def raise_for_status(self):
            pass

    async def post(self, url, **kwargs):
        return Response()

    monkeypatch.setattr(main.httpx.AsyncClient, "post", post)

    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={"model": "hermes", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "message": "Hermes API returned invalid JSON",
            "type": "upstream_error",
            "param": None,
            "code": None,
        }
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "hermes", "messages": []},
        {"model": "hermes"},
    ],
)
def test_chat_completions_rejects_invalid_messages(payload):
    response = client.post("/v1/chat/completions", headers=AUTH, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_chat_completions_rejects_streaming():
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={
            "model": "hermes",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_forwards_internal_key_instead_of_external_token(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        content = b'{"ok":true}'
        headers = {"content-type": "application/json"}

        def raise_for_status(self):
            pass

    async def post(self, url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(main.httpx.AsyncClient, "post", post)
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={"model": "hermes", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert captured["headers"] == {"Authorization": "Bearer internal-test-key"}


@pytest.mark.parametrize("missing", ["HERMES_API_KEY", "GATEWAY_TOKENS"])
def test_required_gateway_configuration_is_rejected(monkeypatch, missing):
    if missing == "HERMES_API_KEY":
        monkeypatch.setattr(main, "HERMES_API_KEY", "")
    else:
        monkeypatch.setattr(main, "GATEWAY_TOKENS", set())

    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={"model": "hermes", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 500
    assert response.json()["error"]["type"] == "configuration_error"


def test_rejects_body_over_byte_limit(monkeypatch):
    monkeypatch.setattr(main, "MAX_BODY_BYTES", 150)
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={"model": "hermes", "messages": [{"role": "user", "content": "x" * 200}]},
    )

    assert response.status_code == 413
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_rejects_giant_unknown_field_before_validation(monkeypatch):
    monkeypatch.setattr(main, "MAX_BODY_BYTES", 256)
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={
            "model": "hermes",
            "messages": [{"role": "user", "content": "hi"}],
            "future_option": "x" * 1000,
        },
    )

    assert response.status_code == 413


def test_accepts_text_content_parts_and_counts_their_text(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        content = b'{"ok":true}'
        headers = {"content-type": "application/json"}

        def raise_for_status(self):
            pass

    async def post(self, url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(main.httpx.AsyncClient, "post", post)
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={
            "model": "hermes",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    assert captured["json"]["messages"][0]["content"][0]["text"] == "hello"


def test_content_limit_accepts_exact_boundary_and_rejects_next_character(monkeypatch):
    monkeypatch.setattr(main, "MAX_CONTEXT_CHARS", 3)
    exact = main.ChatMessage(role="user", content=[{"type": "text", "text": "abc"}])
    main.validate_message_limits([exact])

    over = main.ChatMessage(role="user", content=[{"type": "text", "text": "abcd"}])
    with pytest.raises(main.HTTPException) as error:
        main.validate_message_limits([over])
    assert error.value.status_code == 413


@pytest.mark.parametrize(
    "message",
    [
        {"role": "user", "content": [{"type": "unknown", "text": "x"}]},
        {"role": "user", "content": [{"type": "text", "text": 1}]},
        {"role": "not-a-role", "content": "x"},
    ],
)
def test_rejects_invalid_message_content(message):
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={"model": "hermes", "messages": [message]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "invalid_request_error"


@pytest.mark.parametrize(
    "field_value",
    [("temperature", 2.1), ("top_p", -0.1), ("max_tokens", 0), ("n", 129)],
)
def test_rejects_out_of_range_numeric_parameters(field_value):
    field, value = field_value
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={
            "model": "hermes",
            "messages": [{"role": "user", "content": "hi"}],
            field: value,
        },
    )

    assert response.status_code == 422


def test_allows_unknown_top_level_and_message_fields(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        content = b'{"ok":true}'
        headers = {"content-type": "application/json"}

        def raise_for_status(self):
            pass

    async def post(self, url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(main.httpx.AsyncClient, "post", post)
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={
            "model": "hermes",
            "messages": [{"role": "user", "content": "hi", "vendor_field": "preserve"}],
            "future_option": {"value": "preserve"},
        },
    )

    assert response.status_code == 200
    assert captured["json"]["future_option"] == {"value": "preserve"}
    assert captured["json"]["messages"][0]["vendor_field"] == "preserve"


@pytest.mark.parametrize("status_code", [400, 500])
def test_maps_upstream_http_errors_to_502(monkeypatch, status_code):
    request = httpx.Request("POST", "http://hermes/v1/chat/completions")
    response = httpx.Response(status_code, request=request)

    async def post(self, url, **kwargs):
        return response

    monkeypatch.setattr(main.httpx.AsyncClient, "post", post)
    result = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={"model": "hermes", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert result.status_code == 502
    assert result.json()["error"]["type"] == "upstream_error"


def test_maps_upstream_timeout_to_504(monkeypatch):
    async def post(self, url, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(main.httpx.AsyncClient, "post", post)
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH,
        json={"model": "hermes", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 504
    assert response.json()["error"]["type"] == "upstream_timeout"
