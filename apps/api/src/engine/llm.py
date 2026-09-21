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
from typing import Type, TypeVar

import openai
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

    Normalising these matters because the caller's response differs by kind: a
    schema failure is retried once here (the same input rarely parses on the
    third try), while a provider failure is somebody else's outage and belongs
    to the Celery task's existing backoff. Leaking
    ``openai.RateLimitError`` / ``google.genai.errors.ClientError`` would make
    #543 import both SDKs just to tell those two cases apart.
    """


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
        # HttpOptions.timeout is MILLISECONDS; GEMINI_API_TIMEOUT is seconds.
        # Passing the seconds value through would time out after 120ms.
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
        raise ProviderError(f"Gemini call failed: {exc}") from exc

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
        timeout=settings.OPENAI_API_TIMEOUT,
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
        raise ProviderError(f"OpenAI call failed: {exc}") from exc

    message = completion.choices[0].message
    if message.parsed is None:
        raise ScriptSchemaError(
            f"OpenAI did not return the requested schema: {message.refusal!r}"
        )
    return message.parsed
