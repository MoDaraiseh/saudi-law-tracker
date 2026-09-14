from __future__ import annotations

import httpx
import pytest
import structlog

from saudi_law_tracker.http import HttpClient

_UA = "saudi-law-tracker-test/1.0"


def _client() -> HttpClient:
    # request_delay=0 so tests don't actually wait on the per-host throttle.
    return HttpClient(user_agent=_UA, request_delay=0, max_retries=1)


async def test_disallowed_path_is_skipped_with_warning(httpx_mock):
    httpx_mock.add_response(
        url="https://example.gov.sa/robots.txt",
        text="User-agent: *\nDisallow: /private/\n",
    )
    # Deliberately no mock registered for the private page: if the client
    # tried to actually fetch it, httpx_mock would raise for the unmatched
    # request, failing this test.

    async with _client() as client:
        with structlog.testing.capture_logs() as logs:
            resp = await client.get("https://example.gov.sa/private/secret")

    assert resp.status_code == 403
    assert "robots.txt" in resp.text
    disallowed = [e for e in logs if e["event"] == "robots.disallowed"]
    assert disallowed and disallowed[0]["log_level"] == "warning"


async def test_allowed_path_fetches_normally(httpx_mock):
    httpx_mock.add_response(
        url="https://example.gov.sa/robots.txt", text="User-agent: *\nDisallow: /private/\n"
    )
    httpx_mock.add_response(url="https://example.gov.sa/public/page", text="hello world")

    async with _client() as client:
        resp = await client.get("https://example.gov.sa/public/page")

    assert resp.status_code == 200
    assert resp.text == "hello world"


async def test_robots_txt_is_fetched_once_per_host(httpx_mock):
    httpx_mock.add_response(url="https://example.gov.sa/robots.txt", text="")
    httpx_mock.add_response(url="https://example.gov.sa/a", text="a")
    httpx_mock.add_response(url="https://example.gov.sa/b", text="b")

    async with _client() as client:
        await client.get("https://example.gov.sa/a")
        await client.get("https://example.gov.sa/b")

    assert len(httpx_mock.get_requests(url="https://example.gov.sa/robots.txt")) == 1


async def test_missing_robots_txt_allows_everything(httpx_mock):
    httpx_mock.add_response(url="https://example.gov.sa/robots.txt", status_code=404)
    httpx_mock.add_response(url="https://example.gov.sa/anything", text="content")

    async with _client() as client:
        resp = await client.get("https://example.gov.sa/anything")

    assert resp.status_code == 200
    assert resp.text == "content"


@pytest.mark.parametrize("status_code", [401, 403, 500, 503])
async def test_robots_txt_itself_erroring_disallows_everything(httpx_mock, status_code):
    httpx_mock.add_response(url="https://example.gov.sa/robots.txt", status_code=status_code)
    # No mock for the page itself -- it must never be requested.

    async with _client() as client:
        with structlog.testing.capture_logs() as logs:
            resp = await client.get("https://example.gov.sa/some/page")

    assert resp.status_code == 403
    assert any(entry["event"] == "robots.disallowed" for entry in logs)


async def test_robots_txt_network_failure_fails_closed(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("boom"), url="https://example.gov.sa/robots.txt")

    async with _client() as client:
        with structlog.testing.capture_logs() as logs:
            resp = await client.get("https://example.gov.sa/some/page")

    assert resp.status_code == 403
    fetch_failed = [e for e in logs if e["event"] == "robots.fetch_failed"]
    assert fetch_failed and fetch_failed[0]["log_level"] == "warning"
    assert any(entry["event"] == "robots.disallowed" for entry in logs)
