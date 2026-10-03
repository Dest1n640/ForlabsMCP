"""Session/auth layer: one httpx.Client seeded from a long-lived Laravel
remember-me cookie, plus XSRF header derivation for every request.

See PROJECT-REFERENCE.md §2.1-2.2 for the captured cookie shapes, and
openspec/changes/session-token-auth/design.md for why this seeds
`remember_lm_<hash>` (~5 year lifetime, confirmed live) instead of
logging in with a username/password.

A 401/419 is first treated as a stale short-lived session, not a dead
token: the jar is reset to the remember cookie alone and the call retried
once. See openspec/changes/self-heal-stale-session/design.md.
"""

from __future__ import annotations

import json
from urllib.parse import unquote, urlparse

import httpx

from ..config import ForlabsConfig
from ..errors import AuthError, ConnectivityError
from ..errors import TimeoutError as ForlabsTimeoutError

_XSRF_PRIME_PATH = "/app/login"

# The Laravel remember-me cookie name observed live for this deployment.
# The <hash> suffix is a fixed guard identifier baked into this app's own
# auth configuration - the same for every account on this Forlabs
# deployment, not something derived per user.
REMEMBER_COOKIE_NAME = "remember_lm_59ba36addc2b2f9401580f014c7f58ea4e30989d"

# 401/419 are what Laravel returns once the short-lived session or its
# CSRF token has expired (419 "CSRF token mismatch." confirmed live for a
# stale cached session). Either one triggers a single reset-and-retry; only
# a repeat on the retry is reported. A truly dead remember cookie's
# response was never captured, so 401 on the retry is best-effort.
_SESSION_EXPIRED_STATUSES = frozenset({401, 419})
_CSRF_MISMATCH_STATUS = 419


class ForlabsSession:
    """Holds one httpx.Client seeded from a long-lived remember cookie."""

    def __init__(self, config: ForlabsConfig) -> None:
        self._config = config
        self._client = httpx.Client(base_url=config.base_url, timeout=config.timeout_seconds)
        self._authenticated = False
        self._load_persisted_session()
        self._seed_remember_cookie()

    def close(self) -> None:
        self._client.close()

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    def _seed_remember_cookie(self) -> None:
        """Seed the configured remember cookie unless one was already
        restored from the session cache."""
        if REMEMBER_COOKIE_NAME not in self._client.cookies:
            domain = urlparse(self._config.base_url).hostname or ""
            self._client.cookies.set(
                REMEMBER_COOKIE_NAME, self._config.session_token, domain=domain
            )
        self._authenticated = True

    def _reset_session(self) -> None:
        """Drop every cookie and re-seed only the configured remember
        cookie, so the next send primes a fresh XSRF-TOKEN and Laravel
        mints a fresh short-lived session from the remember cookie."""
        self._client.cookies.clear()
        self._seed_remember_cookie()

    def request(self, method: str, path: str, json_body: dict | None = None) -> httpx.Response:
        """Make an authenticated request.

        The configured remember cookie lets Laravel establish or renew the
        short-lived session cookies as a side effect of an ordinary
        request - confirmed live, no separate keep-alive call is
        made. A 401/419 usually means those short-lived cookies (cached or
        in memory) went stale, so the session is reset to the remember
        cookie and the call retried exactly once. Only if the retry fails
        the same way is AuthError raised - there is no credential to fall
        back to.
        """
        response = self._authenticated_send(method, path, json_body)
        if response.status_code in _SESSION_EXPIRED_STATUSES:
            self._reset_session()
            response = self._authenticated_send(method, path, json_body)
        if response.status_code == _CSRF_MISMATCH_STATUS:
            raise AuthError(
                "Forlabs rejected the request's CSRF token even with a newly "
                "established session. Replacing session_token will not "
                "fix this; try again later."
            )
        if response.status_code in _SESSION_EXPIRED_STATUSES:
            raise AuthError(
                "Forlabs rejected the configured session_token. Obtain a fresh "
                f"{REMEMBER_COOKIE_NAME!r} cookie value from your browser and "
                "update your configuration."
            )
        self._persist_session()
        return response

    def _authenticated_send(self, method: str, path: str, json_body: dict | None) -> httpx.Response:
        token = self._xsrf_token()
        if token is None:
            # No XSRF-TOKEN cookie yet this process (cold start) - prime it.
            self._send("GET", _XSRF_PRIME_PATH)
            token = self._xsrf_token()
        return self._send(
            method,
            path,
            json_body=json_body,
            extra_headers={"Accept": "application/json", "X-XSRF-TOKEN": token or ""},
        )

    def _xsrf_token(self) -> str | None:
        try:
            raw = self._client.cookies.get("XSRF-TOKEN")
        except httpx.CookieConflict:
            # A domain-less cookie restored from the session cache can
            # coexist with a domain-qualified one the server just set.
            # Prefer the most recently set match rather than failing.
            matches = [c for c in self._client.cookies.jar if c.name == "XSRF-TOKEN"]
            raw = matches[-1].value if matches else None
        return unquote(raw) if raw else None

    def _send(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        extra_headers: dict | None = None,
    ) -> httpx.Response:
        kwargs: dict = {"headers": extra_headers or {}}
        if json_body is not None:
            kwargs["json"] = json_body
        try:
            return self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ForlabsTimeoutError("Request to Forlabs timed out.") from exc
        except httpx.TransportError as exc:
            raise ConnectivityError("Could not connect to Forlabs.") from exc

    def _persist_session(self) -> None:
        path = self._config.session_path
        path.parent.mkdir(parents=True, exist_ok=True)
        # A list of {name, value, domain} records - not a flat name->value
        # dict - so two cookies that share a name but differ by domain (the
        # same conflict _xsrf_token() defends against) both survive a
        # persist/restore round trip instead of one silently overwriting
        # the other.
        cookies = [
            {"name": cookie.name, "value": cookie.value, "domain": cookie.domain}
            for cookie in self._client.cookies.jar
        ]
        payload = {"cookies": cookies}
        path.write_text(json.dumps(payload))
        path.chmod(0o600)

    def _load_persisted_session(self) -> None:
        path = self._config.session_path
        if not path.is_file():
            return
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        cookies = payload.get("cookies", [])
        if not isinstance(cookies, list):
            return
        for entry in cookies:
            if not isinstance(entry, dict):
                continue
            name, value, domain = entry.get("name"), entry.get("value"), entry.get("domain")
            if (
                not isinstance(name, str)
                or not isinstance(value, str)
                or not isinstance(domain, str)
            ):
                # Skip just this record - one bad entry shouldn't cost the
                # rest of an otherwise-valid persisted session.
                continue
            self._client.cookies.set(name, value, domain=domain)
