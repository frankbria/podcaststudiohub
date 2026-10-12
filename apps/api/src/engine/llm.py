"""Direct provider SDK access for the generation engine (issue #541).

Deliberately none of the LangChain / model-router tree podcastfy pulled in.
That tree is the entire 31-entry pip-audit suppression list and the
``openai<2`` ceiling (#518), plus a prompt fetch from a third-party account on
the paid generation path (#446). ``google-genai`` and ``openai`` are called
directly instead; ``tests/test_dependency_reachability.py`` fails the build if
any of it creeps back into this package.

Both providers are asked for structured JSON against a Pydantic schema, so a
malformed response is a caught exception rather than a silently mangled
transcript.
"""
import logging
from typing import Optional, Type, TypeVar

import openai
import requests
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from src.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class EngineError(RuntimeError):
    """The engine could not be used at all (bad configuration, no API key)."""


class ScriptSchemaError(EngineError):
    """The provider replied, but not with the schema it was asked for."""


class ProviderError(EngineError):
    """The provider call itself failed — auth, rate limit, timeout, 5xx.

    ``retryable`` marks a failure the engine retries in place with a short
    backoff (#574), so one 503 on chunk 7 does not throw away chunks 1-6. It is
    set only for failures that come back fast: a rate limit, a 5xx, a refused or
    dropped connection. Those almost always generated nothing; the exception is
    a response body cut off mid-read, which may follow a finished (billed)
    generation — retried anyway, because it is rare and costs no timeout to
    detect. A failure that will recur on
    every attempt (bad key, unknown model, rejected request) is not retryable,
    and neither is a timeout: each one costs the full provider timeout, and the
    provider may have finished — and billed — the generation anyway. Those
    reach the Celery task, whose backoff is the right tool for a slow outage.
    Leaking ``openai.RateLimitError`` / ``google.genai.errors.ClientError``
    would make every caller import both SDKs just to tell these cases apart.
    """

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


# 408/409/429 are the only 4xx a retry can fix (409 is a conflict both
# providers document as retryable); every 5xx is the provider's side.
def _is_retryable_status(code: Optional[int]) -> bool:
    return code is not None and (code in (408, 409, 429) or code >= 500)


def generate_json(
    *,
    system: str,
    user: str,
    schema: Type[T],
    creativity: float,
) -> T:
    """Ask the configured provider for a single JSON object matching ``schema``.

    Raises ``EngineError`` if the engine is misconfigured, ``ProviderError`` if
    the provider call fails, and ``ScriptSchemaError`` if the reply cannot be
    validated. No provider-specific exception escapes this module.
    """
    provider = settings.ENGINE_LLM_PROVIDER
    if provider == "gemini":
        return _generate_gemini(
            system=system, user=user, schema=schema, creativity=creativity
        )
    if provider == "openai":
        return _generate_openai(
            system=system, user=user, schema=schema, creativity=creativity
        )
    raise EngineError(
        f"Unsupported ENGINE_LLM_PROVIDER {provider!r}; expected 'gemini' or 'openai'"
    )


def _generate_gemini(
    *, system: str, user: str, schema: Type[T], creativity: float
) -> T:
    if not settings.GEMINI_API_KEY:
        raise EngineError("GEMINI_API_KEY is not set; cannot generate a script")

    # Built per call rather than cached at module scope. Construction opens no
    # connection, and a module-global client captures the API key at import
    # time — exactly the defect #542 is fixing in podcastfy's OpenAI provider.
    client = genai.Client(
        api_key=settings.GEMINI_API_KEY,
        # MILLISECONDS, while GEMINI_API_TIMEOUT is seconds — passing the
        # seconds value straight through would time out after 120ms. Verified
        # against the pinned google-genai: `_api_client.py` divides this by
        # 1000.0 before handing it to the transport. The field's own docstring
        # says "in milliseconds" too. Re-check both if the pin ever moves.
        http_options=types.HttpOptions(timeout=settings.GEMINI_API_TIMEOUT * 1000),
    )
    try:
        response = client.models.generate_content(
            model=settings.ENGINE_GEMINI_MODEL,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=creativity,
                max_output_tokens=settings.ENGINE_MAX_OUTPUT_TOKENS,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
    except genai_errors.APIError as exc:
        raise ProviderError(
            f"Gemini call failed: {exc}", retryable=_is_retryable_status(exc.code)
        ) from exc
    except requests.RequestException as exc:
        # The locked google-genai (1.2.0) sends over `requests` and wraps only
        # HTTP status errors in APIError, so transport failures arrive here raw.
        # pyproject only floors the SDK, so a bump could move it to httpx;
        # test_a_dropped_gemini_connection_... drives the real SDK and fails
        # first if this clause stops seeing its transport errors.
        raise ProviderError(
            f"Gemini call failed: {exc}", retryable=_gemini_transport_retryable(exc)
        ) from exc
    return _parse_gemini_reply(response, schema)


def _gemini_transport_retryable(exc: requests.RequestException) -> bool:
    # Timeout is checked first: ConnectTimeout is also a ConnectionError.
    # A body cut off mid-read is ChunkedEncodingError, which is neither.
    return not isinstance(exc, requests.Timeout) and isinstance(
        exc, (requests.ConnectionError, requests.exceptions.ChunkedEncodingError)
    )


def _parse_gemini_reply(response: types.GenerateContentResponse, schema: Type[T]) -> T:
    try:
        text = response.text
    except ValueError as exc:
        # `.text` raises when any part carries a non-text field — a safety
        # block, a function call, inline data. It sits outside the APIError
        # handler above because it is a property access, not the call, so
        # without this the one contentless shape Gemini actually produces
        # escapes as a raw ValueError past the empty-response branch below.
        raise ScriptSchemaError(f"Gemini returned a non-text response: {exc}") from exc
    if not text:
        raise ScriptSchemaError("Gemini returned an empty response")
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        raise ScriptSchemaError(f"Gemini response did not match the schema: {exc}")


def _generate_openai(
    *, system: str, user: str, schema: Type[T], creativity: float
) -> T:
    if not settings.OPENAI_API_KEY:
        raise EngineError("OPENAI_API_KEY is not set; cannot generate a script")

    client = openai.OpenAI(
        api_key=settings.OPENAI_API_KEY,
        # SECONDS here, unlike the Gemini client above. openai-python hands this
        # to httpx, whose timeouts are seconds (`_constants.py` defaults to
        # `httpx.Timeout(timeout=600, connect=5.0)` — ten minutes, not 600ms).
        # Do not "fix" this to match the * 1000 above: that would be a
        # 120,000-second timeout, i.e. no timeout at all.
        timeout=settings.OPENAI_API_TIMEOUT,
        # The SDK retries 429/5xx twice by default. The engine owns that policy
        # for both providers (#574); leaving this on would stack two retry
        # loops and multiply the worst-case time per chunk.
        max_retries=0,
    )
    # `creativity` is deliberately not forwarded: GPT-5-family models reject any
    # non-default `temperature` with `unsupported_value`, so sending it would
    # fail every call. It still applies on the Gemini path.
    try:
        completion = client.chat.completions.parse(
            model=settings.ENGINE_OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_completion_tokens=settings.ENGINE_MAX_OUTPUT_TOKENS,
            response_format=schema,
        )
    except openai.OpenAIError as exc:
        raise ProviderError(
            f"OpenAI call failed: {exc}", retryable=_openai_retryable(exc)
        ) from exc

    message = completion.choices[0].message
    if message.parsed is None:
        raise ScriptSchemaError(
            f"OpenAI did not return the requested schema: {message.refusal!r}"
        )
    return message.parsed


def _openai_retryable(exc: openai.OpenAIError) -> bool:
    # APITimeoutError subclasses APIConnectionError, so it is excluded
    # explicitly: a timeout is not retried here (see ProviderError).
    if isinstance(exc, openai.APIStatusError):
        return _is_retryable_status(exc.status_code)
    return isinstance(exc, openai.APIConnectionError) and not isinstance(
        exc, openai.APITimeoutError
    )
