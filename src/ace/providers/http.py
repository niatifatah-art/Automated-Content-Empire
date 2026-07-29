from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ace.errors import ProviderRequestError, ProviderUnavailable


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 120,
) -> dict[str, Any]:
    body = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = Request(url, data=body, headers=request_headers, method=method.upper())

    try:
        with urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise ProviderRequestError(
            f"HTTP {exc.code} from {url}: {detail or exc.reason}"
        ) from exc
    except URLError as exc:
        raise ProviderUnavailable(f"Cannot reach {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ProviderUnavailable(f"Timed out connecting to {url}") from exc

    if not text.strip():
        return {}

    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderRequestError(f"Provider returned invalid JSON from {url}") from exc

    if not isinstance(decoded, dict):
        raise ProviderRequestError(f"Provider returned a non-object JSON response from {url}")
    return decoded
