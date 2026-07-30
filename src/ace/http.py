from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

from ace import __version__
from ace.cache import Cache


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class HTTPError(RuntimeError):
    def __init__(self, status: int, message: str, *, headers: Mapping[str, str] | None = None):
        super().__init__(message)
        self.status = status
        self.headers = dict(headers or {})


def request(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    json_body: Any | None = None,
    timeout: int = 30,
    retries: int = 1,
    cache: Cache | None = None,
    cache_ttl: int = 0,
) -> HTTPResponse:
    normalized_headers = {"User-Agent": f"ACE/{__version__} (+https://github.com/niatifatah-art/Automated-Content-Empire)"}
    normalized_headers.update(headers or {})
    payload = None
    if json_body is not None:
        payload = json.dumps(json_body).encode("utf-8")
        normalized_headers.setdefault("Content-Type", "application/json")
    cache_key = None
    if method.upper() == "GET" and cache and cache_ttl > 0:
        cache_key = cache.key("http", url)
        cached = cache.get(cache_key)
        if isinstance(cached, dict) and "body" in cached:
            return HTTPResponse(int(cached["status"]), dict(cached.get("headers", {})), bytes.fromhex(cached["body"]))
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=payload, headers=normalized_headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = HTTPResponse(response.status, dict(response.headers.items()), response.read())
                if cache_key and cache:
                    cache.set(cache_key, {"status": result.status, "headers": result.headers, "body": result.body.hex()}, cache_ttl)
                return result
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = HTTPError(exc.code, body or str(exc), headers=dict(exc.headers.items()))
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= retries:
                raise last_error
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else min(8.0, 1.5 * (2**attempt))
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt >= retries:
                raise RuntimeError(f"network request failed: {exc}") from exc
            time.sleep(min(8.0, 1.5 * (2**attempt)))
    raise RuntimeError(str(last_error or "network request failed"))
