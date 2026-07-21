"""Normalize provider SDK exceptions into safe, structured error info.

LLM provider SDKs (openai, anthropic) attach the full upstream error body to
their exceptions. ``str(exc)`` on those exceptions embeds that raw body
verbatim, which can carry fields the provider never intended us to forward
downstream (account identifiers, internal ticket IDs, etc). The normalizers
here copy only an explicit allowlist of known-safe fields out of the typed
exception so callers have a structured, leak-safe alternative to ``str(exc)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = [
    "ProviderErrorInfo",
    "normalize_openai_error",
    "normalize_anthropic_error",
    "normalize_provider_error",
]


@dataclass
class ProviderErrorInfo:
    http_status: Optional[int] = None
    provider_error_code: Optional[str] = None
    retry_after_seconds: Optional[float] = None
    provider_name: Optional[str] = None
    safe_summary: str = ""


def _safe_summary(
    http_status: Optional[int],
    provider_error_code: Optional[str],
    retry_after_seconds: Optional[float],
) -> str:
    """Build a human-readable summary using only the already-allowlisted fields."""
    if http_status is None and provider_error_code is None:
        return (
            "Provider returned an error."
            if retry_after_seconds is None
            else (f"Provider returned an error. Retry after {retry_after_seconds}s.")
        )

    if provider_error_code is None and retry_after_seconds is None:
        return f"Provider returned HTTP {http_status}."

    if http_status is not None and provider_error_code is not None:
        summary = f"Provider error {http_status} ({provider_error_code})."
    elif http_status is not None:
        summary = f"Provider error {http_status}."
    else:
        summary = f"Provider error ({provider_error_code})."

    if retry_after_seconds is not None:
        summary += f" Retry after {retry_after_seconds}s."
    return summary


def normalize_openai_error(exc: Exception) -> ProviderErrorInfo:
    """Extract safe fields from an openai SDK exception (e.g. APIStatusError).

    Only ever reads these known-safe paths out of the (already-parsed) error
    body:

    - ``body["error"]["code"]`` (fallback for http_status)
    - ``body["error"]["metadata"]["provider_error_code"]``
    - ``body["error"]["metadata"]["retry_after_seconds"]``
    - ``body["error"]["metadata"]["provider_name"]``

    Deliberately never reads ``body["error"]["metadata"]["raw"]``,
    ``body["user_id"]``, ``body["error"]["metadata"]["headers"]``, or any
    other key — this is an allowlist, not a denylist.
    """
    http_status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)

    provider_error_code: Optional[str] = None
    retry_after_seconds: Optional[float] = None
    provider_name: Optional[str] = None

    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            if http_status is None:
                code = error.get("code")
                if isinstance(code, int):
                    http_status = code

            metadata = error.get("metadata")
            if isinstance(metadata, dict):
                meta_code = metadata.get("provider_error_code")
                if isinstance(meta_code, str):
                    provider_error_code = meta_code

                retry_after = metadata.get("retry_after_seconds")
                if isinstance(retry_after, (int, float)):
                    retry_after_seconds = float(retry_after)

                name = metadata.get("provider_name")
                if isinstance(name, str):
                    provider_name = name

    return ProviderErrorInfo(
        http_status=http_status,
        provider_error_code=provider_error_code,
        retry_after_seconds=retry_after_seconds,
        provider_name=provider_name,
        safe_summary=_safe_summary(
            http_status, provider_error_code, retry_after_seconds
        ),
    )


def normalize_anthropic_error(exc: Exception) -> ProviderErrorInfo:
    """Extract safe fields from an anthropic SDK exception (e.g. APIStatusError).

    Only ever reads ``body["error"]["type"]`` out of the error body, mirroring
    the allowlist approach of :func:`normalize_openai_error`.
    """
    http_status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)

    provider_error_code: Optional[str] = None
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            error_type = error.get("type")
            if isinstance(error_type, str):
                provider_error_code = error_type

    return ProviderErrorInfo(
        http_status=http_status,
        provider_error_code=provider_error_code,
        safe_summary=_safe_summary(http_status, provider_error_code, None),
    )


def normalize_provider_error(exc: Exception) -> ProviderErrorInfo:
    """Dispatch to the right normalizer by type; fall back to a status-code-only summary."""
    try:
        import openai

        if isinstance(exc, openai.APIStatusError):
            return normalize_openai_error(exc)
    except ImportError:
        pass

    try:
        import anthropic

        if isinstance(exc, anthropic.APIStatusError):
            return normalize_anthropic_error(exc)
    except ImportError:
        pass

    http_status = getattr(exc, "status_code", None)
    return ProviderErrorInfo(
        http_status=http_status,
        safe_summary=_safe_summary(http_status, None, None),
    )
