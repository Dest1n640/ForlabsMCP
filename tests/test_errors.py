from forlabs_mcp.errors import (
    AuthError,
    ConfigError,
    ConnectivityError,
    ForlabsError,
    InvalidArgumentError,
    ProgrammingError,
    RateLimitError,
    TimeoutError,
    UpstreamError,
    to_tool_error,
)


def test_config_error_maps_to_classified_message() -> None:
    exc = ConfigError("username is missing", key="username")
    message = to_tool_error(exc)
    assert message == "Configuration error: username is missing"


def test_invalid_argument_error_maps_to_classified_message() -> None:
    exc = InvalidArgumentError("date and start/end are mutually exclusive", argument="date")
    message = to_tool_error(exc)
    assert message == "Invalid argument: date and start/end are mutually exclusive"


def test_auth_error_maps_to_classified_message() -> None:
    exc = AuthError("Forlabs rejected the configured username/password.")
    message = to_tool_error(exc)
    assert message.startswith("Authentication failed:")


def test_connectivity_error_maps_to_classified_message() -> None:
    exc = ConnectivityError("Could not connect to Forlabs.")
    message = to_tool_error(exc)
    assert message.startswith("Could not connect to Forlabs:")


def test_timeout_error_maps_to_classified_message() -> None:
    exc = TimeoutError("Request to Forlabs timed out.")
    message = to_tool_error(exc)
    assert message.startswith("Request to Forlabs timed out:")


def test_rate_limit_error_includes_retry_after_when_present() -> None:
    exc = RateLimitError("Rate limited.", retry_after=30)
    message = to_tool_error(exc)
    assert "Retry after 30s." in message


def test_rate_limit_error_without_retry_after() -> None:
    exc = RateLimitError("Rate limited.")
    message = to_tool_error(exc)
    assert "Retry after" not in message


def test_upstream_error_includes_module_and_action() -> None:
    exc = UpstreamError("backend blew up", module="sched", action="get_grid")
    message = to_tool_error(exc)
    assert "sched/get_grid" in message


def test_programming_error_maps_to_classified_message() -> None:
    exc = ProgrammingError("action not on the allow-list")
    message = to_tool_error(exc)
    assert message.startswith("Internal error:")


def test_unrecognized_exception_collapses_to_generic_message() -> None:
    exc = ValueError("some raw internal detail that must never leak")
    message = to_tool_error(exc)
    assert message == "Unexpected error while talking to Forlabs."
    assert "some raw internal detail" not in message


def test_all_subclasses_derive_from_forlabs_error() -> None:
    for cls in (
        ConfigError,
        InvalidArgumentError,
        AuthError,
        ConnectivityError,
        TimeoutError,
        RateLimitError,
        UpstreamError,
        ProgrammingError,
    ):
        assert issubclass(cls, ForlabsError)
