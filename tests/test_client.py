from __future__ import annotations

import asyncio
from typing import Any

import httpx

from confluence_dc_mcp.client import ConfluenceDataCenterClient
from confluence_dc_mcp.config import ConfluenceConfig


def test_get_page_storage_sends_bearer_auth_and_maps_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "123",
                "type": "page",
                "title": "Roadmap",
                "space": {"key": "ENG"},
                "version": {"number": 7},
                "body": {
                    "storage": {
                        "value": "<p>Hello</p>",
                        "representation": "storage",
                    }
                },
            },
        )

    async def run() -> None:
        client = ConfluenceDataCenterClient(_config(), transport=httpx.MockTransport(handler))
        try:
            page = await client.get_page("123")
        finally:
            await client.close()

        assert page.id == "123"
        assert page.title == "Roadmap"
        assert page.space_key == "ENG"
        assert page.version == 7
        assert page.storage == "<p>Hello</p>"

    asyncio.run(run())

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/rest/api/content/123"
    assert requests[0].headers["authorization"] == "Bearer token"
    assert "body.storage" in str(requests[0].url)


def test_search_maps_page_summaries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/rest/api/content/search"
        assert "type+%3D+page" in str(request.url)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "123",
                        "type": "page",
                        "title": "Roadmap",
                        "space": {"key": "ENG"},
                        "version": {"number": 7},
                    }
                ],
                "size": 1,
                "limit": 10,
                "start": 0,
            },
        )

    async def run() -> None:
        client = ConfluenceDataCenterClient(_config(), transport=httpx.MockTransport(handler))
        try:
            pages = await client.search("type = page")
        finally:
            await client.close()

        assert len(pages) == 1
        assert pages[0].id == "123"
        assert pages[0].title == "Roadmap"
        assert pages[0].space_key == "ENG"
        assert pages[0].version == 7

    asyncio.run(run())


def test_update_storage_increments_version_and_preserves_space() -> None:
    seen_payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "123",
                    "type": "page",
                    "title": "Roadmap",
                    "space": {"key": "ENG"},
                    "version": {"number": 7},
                    "body": {
                        "storage": {
                            "value": "<p>Old</p>",
                            "representation": "storage",
                        }
                    },
                },
            )

        payload = _json_body(request)
        seen_payloads.append(payload)
        return httpx.Response(
            200,
            json={
                "id": "123",
                "type": "page",
                "title": payload["title"],
                "version": {"number": payload["version"]["number"]},
            },
        )

    async def run() -> None:
        client = ConfluenceDataCenterClient(_config(), transport=httpx.MockTransport(handler))
        try:
            result = await client.update_storage(
                "123",
                "<p>New</p>",
                version_comment="Update raw storage",
                minor_edit=True,
            )
        finally:
            await client.close()

        assert result.version == 8

    asyncio.run(run())

    assert len(seen_payloads) == 1
    assert seen_payloads[0]["space"] == {"key": "ENG"}
    assert seen_payloads[0]["version"] == {
        "number": 8,
        "minorEdit": True,
        "message": "Update raw storage",
    }
    assert seen_payloads[0]["body"]["storage"] == {
        "value": "<p>New</p>",
        "representation": "storage",
    }


def _config() -> ConfluenceConfig:
    return ConfluenceConfig(
        base_url="https://confluence.example.com",
        pat="token",
        username=None,
        password=None,
        verify_ssl=True,
        timeout_seconds=30,
    )


def _json_body(request: httpx.Request) -> dict[str, Any]:
    body = request.read()
    parsed = httpx.Response(200, content=body).json()
    assert isinstance(parsed, dict)
    return parsed

