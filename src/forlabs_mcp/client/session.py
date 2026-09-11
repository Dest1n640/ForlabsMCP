"""Session/auth layer: one httpx.Client, the Laravel+AngularJS login flow,
and XSRF header derivation for every subsequent request.

See PROJECT-REFERENCE.md §2.1-2.2 for the captured login flow this mirrors.
"""

from __future__ import annotations

import json
from urllib.parse import unquote

import httpx

from ..config import ForlabsConfig
from ..errors import AuthError, ConnectivityError
from ..errors import TimeoutError as ForlabsTimeoutError

_LOGIN_PATH = "/app/login"


class ForlabsSession:
    """Holds one httpx.Client and the Forlabs login/session lifecycle."""

    def __init__(self, config: ForlabsConfig) -> None:
        self._config = config
        self._client = httpx.Client(base_url=config.base_url, timeout=config.timeout_seconds)
        self._authenticated = False
        self._load_persisted_session()

    def close(self) -> None:
        self._client.close()

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    def ensure_authenticated(self) -> None:
        if not self._authenticated:
            self.login()

    def login(self) -> None:
        """Prime the XSRF cookie, then log in with the configured credentials.

        Raises AuthError on rejected credentials or any other login failure,
        without ever including the password in the error message.
        """
        self._send("GET", _LOGIN_PATH)
        token = self._xsrf_token()

        response = self._send(
            "POST",
            _LOGIN_PATH,
            json_body={
                "username": self._config.username,
                "password": self._config.password,
                "remember": True,
            },
            extra_headers={
                "Accept": "application/json, text/plain, */*",
                "Origin": self._config.base_url,
                "Referer": f"{self._config.base_url}{_LOGIN_PATH}",
                "X-XSRF-TOKEN": token or "",
            },
        )

        if response.status_code == 422:
            raise AuthError("Forlabs rejected the configured username/password.")
        if response.status_code >= 400:
            raise AuthError(f"Forlabs login failed with status {response.status_code}.")

        self._authenticated = True
        self._persist_session()

    def request(self, method: str, path: str, json_body: dict | None = None) -> httpx.Response:
        """Make an authenticated request, logging in first if necessary."""
        self.ensure_authenticated()
        token = self._xsrf_token()
        return self._send(
            method,
            path,
            json_body=json_body,
            extra_headers={"Accept": "application/json", "X-XSRF-TOKEN": token or ""},
        )

    def _xsrf_token(self) -> str | None:
        raw = self._client.cookies.get("XSRF-TOKEN")
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
        payload = {"cookies": dict(self._client.cookies)}
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
        cookies = payload.get("cookies", {})
        for name, value in cookies.items():
            self._client.cookies.set(name, value)
        if "forlabs_session" in cookies:
            self._authenticated = True
