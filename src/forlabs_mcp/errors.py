"""Credential-free, classified error taxonomy for the Forlabs client.

See PROJECT-REFERENCE.md §8. `to_tool_error()` is the one boundary every
tool call goes through: no raw exception, stack trace, or credential value
is ever allowed to reach tool output.
"""

from __future__ import annotations


class ForlabsError(Exception):
    """Base class for every error this client can raise."""


class ConfigError(ForlabsError):
    """A required setting is missing or malformed at startup."""

    def __init__(self, message: str, *, key: str | None = None) -> None:
        super().__init__(message)
        self.key = key


class InvalidArgumentError(ForlabsError):
    """A tool argument is invalid, checked before any backend call."""

    def __init__(self, message: str, *, argument: str | None = None) -> None:
        super().__init__(message)
        self.argument = argument


class AuthError(ForlabsError):
    """Login was rejected, or re-auth-once also failed."""


class ConnectivityError(ForlabsError):
    """The host is unreachable (DNS failure, connection reset, ...)."""


class TimeoutError(ForlabsError):  # noqa: A001 - name matches reference §8 exactly
    """A request exceeded the configured timeout."""


class RateLimitError(ForlabsError):
    """The backend is rate-limiting requests."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class UpstreamError(ForlabsError):
    """The backend returned an application-level error."""

    def __init__(
        self, message: str, *, module: str | None = None, action: str | None = None
    ) -> None:
        super().__init__(message)
        self.module = module
        self.action = action


class ProgrammingError(ForlabsError):
    """A call was made outside the read-only allow-list, or the client was misused."""


def to_tool_error(exc: Exception) -> str:
    """Map any exception to a single-line, credential-free, classified message.

    An exception type this function does not recognize collapses to a
    generic message rather than leaking its own text.
    """
    if isinstance(exc, ConfigError):
        return f"Configuration error: {exc}"
    if isinstance(exc, InvalidArgumentError):
        return f"Invalid argument: {exc}"
    if isinstance(exc, AuthError):
        return f"Authentication failed: {exc}"
    if isinstance(exc, ConnectivityError):
        return f"Could not connect to Forlabs: {exc}"
    if isinstance(exc, TimeoutError):
        return f"Request to Forlabs timed out: {exc}"
    if isinstance(exc, RateLimitError):
        suffix = f" Retry after {exc.retry_after}s." if exc.retry_after else ""
        return f"Forlabs is rate-limiting requests.{suffix}"
    if isinstance(exc, UpstreamError):
        return f"Forlabs returned an error for {exc.module}/{exc.action}: {exc}"
    if isinstance(exc, ProgrammingError):
        return f"Internal error: {exc}"
    return "Unexpected error while talking to Forlabs."
