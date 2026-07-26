"""HTTP client for the internal assist.org API.

The API requires no key, but every request must carry the XSRF cookies set by
the SPA shell plus an ``X-XSRF-TOKEN`` header echoing the readable cookie.
Stdlib only, so the MCP server's sole dependency is the ``mcp`` package.
"""

from __future__ import annotations

import http.cookiejar
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://assist.org"
USER_AGENT = "assist-mcp/0.1 (MCP server for ASSIST articulation data)"
CACHE_TTL_SECONDS = 24 * 3600


class AssistError(RuntimeError):
    """A request to assist.org failed after retrying the handshake."""


class AssistClient:
    def __init__(self):
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar)
        )
        self._opener.addheaders = [("User-Agent", USER_AGENT)]
        self._token: str | None = None
        self._cache: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def _handshake(self) -> None:
        """GET the SPA shell; the response sets the XSRF cookie pair."""
        self._opener.open(BASE + "/", timeout=30).read()
        self._token = None
        for cookie in self._jar:
            if cookie.name == "X-XSRF-TOKEN":
                self._token = cookie.value
        if not self._token:
            raise AssistError("XSRF handshake with assist.org failed: no token cookie")

    def get(self, path: str, **params) -> object:
        """GET /api/{path}, with a 24h in-memory cache per full URL."""
        url = f"{BASE}/api/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        with self._lock:
            hit = self._cache.get(url)
            if hit and time.time() < hit[0]:
                return hit[1]
            data = self._request(url)
            self._cache[url] = (time.time() + CACHE_TTL_SECONDS, data)
            return data

    def _request(self, url: str, _retried: bool = False) -> object:
        if self._token is None:
            self._handshake()
        req = urllib.request.Request(url, headers={"X-XSRF-TOKEN": self._token})
        try:
            with self._opener.open(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            # A 400 usually means the antiforgery session expired; redo the
            # handshake once before giving up.
            if e.code == 400 and not _retried:
                self._token = None
                return self._request(url, _retried=True)
            raise AssistError(f"assist.org returned HTTP {e.code} for {url}") from e
        except urllib.error.URLError as e:
            raise AssistError(f"could not reach assist.org: {e.reason}") from e
