from __future__ import annotations

import asyncio
from pathlib import Path
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


def test_get_page_children_maps_page_summaries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/rest/api/content/123/child/page"
        assert "limit=25" in str(request.url)
        assert "start=0" in str(request.url)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "456",
                        "type": "page",
                        "title": "Child page",
                        "space": {"key": "ENG"},
                        "version": {"number": 3},
                    }
                ],
                "size": 1,
                "limit": 25,
                "start": 0,
            },
        )

    async def run() -> None:
        client = ConfluenceDataCenterClient(_config(), transport=httpx.MockTransport(handler))
        try:
            pages = await client.get_page_children("123")
        finally:
            await client.close()

        assert len(pages) == 1
        assert pages[0].id == "456"
        assert pages[0].title == "Child page"
        assert pages[0].space_key == "ENG"
        assert pages[0].version == 3

    asyncio.run(run())


def test_get_page_history_maps_versions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/rest/api/content/123/version"
        assert "expand=by" in str(request.url)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "number": 7,
                        "by": {"username": "alice", "displayName": "Alice"},
                        "when": "2026-01-01T10:00:00.000Z",
                        "message": "Updated",
                        "minorEdit": True,
                    }
                ],
                "size": 1,
                "limit": 25,
                "start": 0,
            },
        )

    async def run() -> None:
        client = ConfluenceDataCenterClient(_config(), transport=httpx.MockTransport(handler))
        try:
            history = await client.get_page_history("123")
        finally:
            await client.close()

        assert len(history) == 1
        assert history[0].number == 7
        assert history[0].by_username == "alice"
        assert history[0].by_display_name == "Alice"
        assert history[0].minor_edit is True

    asyncio.run(run())


def test_create_page_posts_storage_payload_with_optional_parent() -> None:
    seen_payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/rest/api/content"
        payload = _json_body(request)
        seen_payloads.append(payload)
        return httpx.Response(
            200,
            json={
                "id": "456",
                "type": "page",
                "title": payload["title"],
                "version": {"number": 1},
            },
        )

    async def run() -> None:
        client = ConfluenceDataCenterClient(_config(), transport=httpx.MockTransport(handler))
        try:
            result = await client.create_page("ENG", "New page", "<p>Body</p>", parent_id="123")
        finally:
            await client.close()

        assert result.id == "456"
        assert result.version == 1

    asyncio.run(run())

    assert seen_payloads[0]["space"] == {"key": "ENG"}
    assert seen_payloads[0]["ancestors"] == [{"id": "123"}]
    assert seen_payloads[0]["body"]["storage"]["value"] == "<p>Body</p>"


def test_move_page_uses_relative_move_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/rest/api/content/123/move/append/456"
        return httpx.Response(200)

    async def run() -> None:
        client = ConfluenceDataCenterClient(_config(), transport=httpx.MockTransport(handler))
        try:
            result = await client.move_page("123", "456")
        finally:
            await client.close()

        assert result.moved is True
        assert result.position == "append"

    asyncio.run(run())


def test_comments_can_be_listed_added_and_replied_to() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            assert request.url.path == "/rest/api/content/123/child/comment"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "c1",
                            "type": "comment",
                            "title": "Re: Roadmap",
                            "container": {"id": "123", "type": "page"},
                            "version": {"number": 2},
                            "body": {
                                "storage": {
                                    "value": "<p>Existing</p>",
                                    "representation": "storage",
                                }
                            },
                        }
                    ],
                    "size": 1,
                    "limit": 25,
                    "start": 0,
                },
            )

        payload = _json_body(request)
        return httpx.Response(
            200,
            json={
                "id": "c2",
                "type": "comment",
                "title": "Re: Roadmap",
                "container": payload["container"],
                "version": {"number": 1},
                "body": payload["body"],
            },
        )

    async def run() -> None:
        client = ConfluenceDataCenterClient(_config(), transport=httpx.MockTransport(handler))
        try:
            comments = await client.get_comments("123")
            added = await client.add_comment("123", "<p>Added</p>")
            reply = await client.reply_to_comment("c1", "<p>Reply</p>")
        finally:
            await client.close()

        assert comments[0].storage == "<p>Existing</p>"
        assert added.container_id == "123"
        assert reply.container_id == "c1"

    asyncio.run(run())

    add_payload = _json_body(requests[1])
    reply_payload = _json_body(requests[2])
    assert add_payload["container"] == {"id": "123", "type": "page"}
    assert reply_payload["container"] == {"id": "c1", "type": "comment"}


def test_labels_and_user_search_are_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/rest/api/content/123/label":
            return httpx.Response(
                200,
                json={
                    "results": [{"id": "l1", "name": "roadmap", "prefix": "global"}],
                    "size": 1,
                    "limit": 25,
                    "start": 0,
                },
            )
        if request.method == "POST":
            assert request.url.path == "/rest/api/content/123/label"
            parsed = httpx.Response(200, content=request.read()).json()
            assert parsed == [{"prefix": "global", "name": "new-label"}]
            return httpx.Response(
                200,
                json=[{"id": "l2", "name": "new-label", "prefix": "global"}],
            )

        assert request.method == "GET"
        assert request.url.path == "/rest/api/search"
        assert "type+%3D+user" in str(request.url)
        return httpx.Response(
            200,
            json={
                "results": [{"title": "Alice", "url": "/display/~alice", "excerpt": "Alice"}],
                "size": 1,
                "limit": 10,
                "start": 0,
            },
        )

    async def run() -> None:
        client = ConfluenceDataCenterClient(_config(), transport=httpx.MockTransport(handler))
        try:
            labels = await client.get_labels("123")
            added = await client.add_label("123", "new-label")
            users = await client.search_user("ali")
        finally:
            await client.close()

        assert labels[0].name == "roadmap"
        assert added[0].name == "new-label"
        assert users[0].display_name == "Alice"
        assert users[0].url == "/display/~alice"

    asyncio.run(run())


def test_get_attachment_list_maps_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/rest/api/content/123/child/attachment"
        assert "metadata" in str(request.url)
        assert "extensions" in str(request.url)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "789",
                        "type": "attachment",
                        "title": "report.pdf",
                        "version": {"number": 4},
                        "metadata": {"mediaType": "application/pdf"},
                        "extensions": {"fileSize": 1024},
                        "_links": {"download": "/download/attachments/123/report.pdf"},
                    },
                    {
                        "id": "790",
                        "type": "attachment",
                        "title": "image.png",
                        "extensions": {"mediaType": "image/png", "fileSize": 2048},
                    }
                ],
                "size": 2,
                "limit": 25,
                "start": 0,
            },
        )

    async def run() -> None:
        client = ConfluenceDataCenterClient(_config(), transport=httpx.MockTransport(handler))
        try:
            attachments = await client.get_attachment_list("123")
        finally:
            await client.close()

        assert len(attachments) == 2
        assert attachments[0].id == "789"
        assert attachments[0].title == "report.pdf"
        assert attachments[0].media_type == "application/pdf"
        assert attachments[0].file_size == 1024
        assert attachments[0].version == 4
        assert attachments[0].download_url == "/download/attachments/123/report.pdf"
        assert attachments[1].media_type == "image/png"
        assert attachments[1].file_size == 2048

    asyncio.run(run())


def test_download_attachment_fetches_metadata_then_downloads_base64_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/rest/api/content/789":
            return httpx.Response(
                200,
                json={
                    "id": "789",
                    "type": "attachment",
                    "title": "report.pdf",
                    "metadata": {"mediaType": "application/pdf"},
                    "_links": {"download": "/download/attachments/123/report.pdf"},
                },
            )

        assert request.url.path == "/download/attachments/123/report.pdf"
        return httpx.Response(200, content=b"pdf-data")

    async def run() -> None:
        client = ConfluenceDataCenterClient(_config(), transport=httpx.MockTransport(handler))
        try:
            attachment = await client.download_attachment("789")
        finally:
            await client.close()

        assert attachment.id == "789"
        assert attachment.title == "report.pdf"
        assert attachment.media_type == "application/pdf"
        assert attachment.data_base64 == "cGRmLWRhdGE="

    asyncio.run(run())

    assert [request.url.path for request in requests] == [
        "/rest/api/content/789",
        "/download/attachments/123/report.pdf",
    ]
    assert requests[1].headers["accept"] == "*/*"


def test_upload_attachment_posts_multipart_file(tmp_path: Path) -> None:
    upload = tmp_path / "report.txt"
    upload.write_text("report-body")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/rest/api/content/123/child/attachment"
        assert request.headers["x-atlassian-token"] == "nocheck"
        body = request.read()
        assert b'name="comment"' in body
        assert b"Upload report" in body
        assert b'report-body' in body
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "789",
                        "type": "attachment",
                        "title": "report.txt",
                        "version": {"number": 1},
                        "metadata": {"mediaType": "text/plain"},
                        "extensions": {"fileSize": 11},
                    }
                ]
            },
        )

    async def run() -> None:
        client = ConfluenceDataCenterClient(_config(), transport=httpx.MockTransport(handler))
        try:
            attachment = await client.upload_attachment(
                "123",
                str(upload),
                comment="Upload report",
            )
        finally:
            await client.close()

        assert attachment.id == "789"
        assert attachment.media_type == "text/plain"

    asyncio.run(run())


def test_get_page_images_downloads_only_image_attachments() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/rest/api/content/123/child/attachment":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "img",
                            "type": "attachment",
                            "title": "diagram.png",
                            "metadata": {"mediaType": "image/png"},
                            "_links": {"download": "/download/diagram.png"},
                        },
                        {
                            "id": "pdf",
                            "type": "attachment",
                            "title": "report.pdf",
                            "metadata": {"mediaType": "application/pdf"},
                            "_links": {"download": "/download/report.pdf"},
                        },
                    ],
                    "size": 2,
                    "limit": 50,
                    "start": 0,
                },
            )
        if request.url.path == "/rest/api/content/img":
            return httpx.Response(
                200,
                json={
                    "id": "img",
                    "type": "attachment",
                    "title": "diagram.png",
                    "metadata": {"mediaType": "image/png"},
                    "_links": {"download": "/download/diagram.png"},
                },
            )

        assert request.url.path == "/download/diagram.png"
        return httpx.Response(200, content=b"png-data")

    async def run() -> None:
        client = ConfluenceDataCenterClient(_config(), transport=httpx.MockTransport(handler))
        try:
            images = await client.get_page_images("123")
        finally:
            await client.close()

        assert len(images) == 1
        assert images[0].id == "img"
        assert images[0].data_base64 == "cG5nLWRhdGE="

    asyncio.run(run())

    assert [request.url.path for request in requests] == [
        "/rest/api/content/123/child/attachment",
        "/rest/api/content/img",
        "/download/diagram.png",
    ]


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
