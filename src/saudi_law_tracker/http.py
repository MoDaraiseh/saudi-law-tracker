"""Polite, retrying HTTP client wrapper."""

from __future__ import annotations

import asyncio
import ssl
import time
from functools import lru_cache
from pathlib import Path

import certifi
import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .logging import get_logger

log = get_logger(__name__)

_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)

_EXTRA_CA_BUNDLE = Path(__file__).with_name("certs") / "extra_intermediates.pem"


@lru_cache(maxsize=1)
def default_ssl_context() -> ssl.SSLContext:
    """certifi's trust store plus intermediates some gov hosts fail to serve.

    Several tracked portals (e.g. laws.boe.gov.sa) send only their leaf
    certificate, so OpenSSL can't build a path to an already-trusted root and
    verification fails with "unable to get local issuer certificate". Bundling
    the public intermediates fixes that without weakening verification.
    """

    ctx = ssl.create_default_context(cafile=certifi.where())
    if _EXTRA_CA_BUNDLE.exists():
        ctx.load_verify_locations(cafile=str(_EXTRA_CA_BUNDLE))
    return ctx


class HttpClient:
    """Async client that rate-limits per host and retries transient failures."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float = 30.0,
        max_retries: int = 4,
        request_delay: float = 2.0,
    ) -> None:
        self._delay = request_delay
        self._max_retries = max_retries
        self._last_request_at: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=default_ssl_context(),
            headers={"User-Agent": user_agent, "Accept-Language": "ar,en;q=0.8"},
        )

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _throttle(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            last = self._last_request_at.get(host, 0.0)
            wait = self._delay - (time.monotonic() - last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at[host] = time.monotonic()

    async def get(self, url: str, **kwargs: object) -> httpx.Response:
        host = httpx.URL(url).host or ""
        await self._throttle(host)

        @retry(
            reraise=True,
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type(_RETRYABLE),
        )
        async def _do() -> httpx.Response:
            resp = await self._client.get(url, **kwargs)  # type: ignore[arg-type]
            if resp.status_code >= 500:
                resp.raise_for_status()
            return resp

        log.debug("http.get", url=url)
        return await _do()
