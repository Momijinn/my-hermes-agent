"""FastAPI gateway for secure OpenAI-compatible access to Hermes Agent."""

import hmac
import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

GATEWAY_TOKENS = {
    token.strip()
    for token in os.environ.get("GATEWAY_TOKENS", "").split(",")
    if token.strip()
}
HERMES_URL = os.environ.get("HERMES_URL", "http://hermes:9119")
HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "")
MAX_BODY_BYTES = int(os.environ.get("GATEWAY_MAX_BODY_BYTES", "1048576"))
MAX_CONTEXT_LINES = int(os.environ.get("GATEWAY_MAX_CONTEXT_LINES", os.environ.get("MAX_CONTEXT_LINES", "2000")))
MAX_CONTEXT_CHARS = int(os.environ.get("GATEWAY_MAX_CONTEXT_CHARS", os.environ.get("MAX_CONTEXT_CHARS", "200000")))
PUBLIC_DIR = Path("/opt/data/public").resolve()
MAX_PUBLIC_FILE_BYTES = 10 * 1024 * 1024

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gateway")
app = FastAPI(title="Hermes Review Gateway")


@app.middleware("http")
async def enforce_body_limit(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/v1/chat/completions":
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                too_large = int(content_length) > MAX_BODY_BYTES
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(
                    status_code=413,
                    content=openai_error("Request body is too large", "invalid_request_error"),
                )
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content=openai_error("Request body is too large", "invalid_request_error"),
            )
    return await call_next(request)


def openai_error(message: str, error_type: str, *, param=None, code=None) -> dict:
    return {
        "error": {
            "message": message,
            "type": error_type,
            "param": param,
            "code": code,
        }
    }


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=openai_error("Invalid request", "invalid_request_error"),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    content = exc.detail if isinstance(exc.detail, dict) and "error" in exc.detail else openai_error(
        str(exc.detail), "invalid_request_error"
    )
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


async def verify_token(request: Request, authorization: str | None = Header(default=None)) -> str:
    """Verify the Bearer token from the Authorization header."""
    if not HERMES_API_KEY or not GATEWAY_TOKENS:
        logger.error("Gateway authentication configuration is incomplete")
        raise HTTPException(
            status_code=500,
            detail=openai_error("Gateway authentication is not configured", "configuration_error"),
        )
    if authorization is None or not authorization.startswith("Bearer "):
        logger.warning("Invalid auth header format")
        raise HTTPException(
            status_code=401,
            detail=openai_error("Invalid authorization header", "authentication_error"),
        )

    token = authorization[7:]
    if not any(hmac.compare_digest(token, allowed) for allowed in GATEWAY_TOKENS):
        client_host = request.client.host if request.client else "unknown"
        logger.warning("Invalid token attempt from %s", client_host)
        raise HTTPException(
            status_code=401,
            detail=openai_error("Invalid token", "authentication_error"),
        )

    return token


class ContentPart(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    type: Literal["text", "image_url", "input_audio"]
    text: StrictStr | None = None
    image_url: dict[str, Any] | None = None
    input_audio: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_part(self):
        required = {
            "text": self.text is not None,
            "image_url": self.image_url is not None,
            "input_audio": self.input_audio is not None,
        }
        if not required[self.type]:
            raise ValueError(f"content part type {self.type!r} has no matching content")
        return self


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    role: Literal["developer", "system", "user", "assistant", "tool"]
    content: StrictStr | list[ContentPart] | None = None


StrictNumber = StrictFloat | StrictInt


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: StrictStr
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: Annotated[StrictNumber, Field(ge=0, le=2)] | None = None
    top_p: Annotated[StrictNumber, Field(ge=0, le=1)] | None = None
    frequency_penalty: Annotated[StrictNumber, Field(ge=-2, le=2)] | None = None
    presence_penalty: Annotated[StrictNumber, Field(ge=-2, le=2)] | None = None
    max_tokens: Annotated[StrictInt, Field(ge=1)] | None = None
    max_completion_tokens: Annotated[StrictInt, Field(ge=1)] | None = None
    n: Annotated[StrictInt, Field(ge=1, le=128)] | None = None
    stream: StrictBool = False


def validate_message_limits(messages: list[ChatMessage]) -> None:
    text_parts = []
    for message in messages:
        content = message.content if isinstance(message, ChatMessage) else message.get("content")
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            text_parts.extend(part.text for part in content if part.type == "text" and part.text is not None)
    total_text = "\n".join(text_parts)
    line_count = len(total_text.splitlines())
    if len(total_text) > MAX_CONTEXT_CHARS or line_count > MAX_CONTEXT_LINES:
        logger.warning("Request content too large: %s chars, %s lines", len(total_text), line_count)
        raise HTTPException(
            status_code=413,
            detail=openai_error("Request content is too large", "invalid_request_error"),
        )


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest, token: str = Depends(verify_token)
):
    """Forward an OpenAI Chat Completions request to Hermes without rewriting it."""
    if request.stream:
        raise HTTPException(
            status_code=400,
            detail=openai_error(
                "Streaming responses are not supported by this gateway",
                "invalid_request_error",
                param="stream",
            ),
        )

    validate_message_limits(request.messages)
    payload = request.model_dump(exclude_unset=True)
    logger.info("Chat completion request: messages=%s", len(request.messages))

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            response = await client.post(
                f"{HERMES_URL}/v1/chat/completions",
                headers={"Authorization": f"Bearer {HERMES_API_KEY}"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.error("Hermes API timeout: %s", exc)
            raise HTTPException(
                status_code=504,
                detail=openai_error("Hermes API timed out", "upstream_timeout"),
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("Hermes API error: %s", exc)
            raise HTTPException(
                status_code=502,
                detail=openai_error("Hermes API error", "upstream_error"),
            ) from exc

    try:
        json.loads(response.content)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        logger.error("Hermes API returned invalid JSON: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=openai_error("Hermes API returned invalid JSON", "upstream_error"),
        ) from exc

    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/public/{path:path}")
async def public_file(path: str):
    """Serve a public file without gateway authentication."""
    file_path = (PUBLIC_DIR / path).resolve()
    if not file_path.is_relative_to(PUBLIC_DIR) or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if file_path.stat().st_size > MAX_PUBLIC_FILE_BYTES:
        raise HTTPException(status_code=404, detail="File not found")

    media_type, _ = mimetypes.guess_type(file_path.name)
    return FileResponse(file_path, media_type=media_type or "application/octet-stream")
