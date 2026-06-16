from __future__ import annotations

import json
from typing import Any, cast
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from mcp.types import (
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    TextContent,
    ToolAnnotations,
)
from typing_extensions import TypedDict

from confluence_dc_mcp.client import (
    AttachmentSummary,
    ConfluenceDataCenterClient,
    DownloadedAttachment,
    PageStorage,
    PageSummary,
    PageUpdateResult,
)
from confluence_dc_mcp.config import load_config


class PageSummaryResult(TypedDict):
    id: str
    title: str
    type: str
    space_key: str | None
    version: int | None


class PageStorageResult(TypedDict):
    id: str
    title: str
    type: str
    space_key: str | None
    version: int
    storage: str


class PageUpdateResultData(TypedDict):
    id: str
    title: str
    type: str
    version: int


class AttachmentSummaryResult(TypedDict):
    id: str
    title: str
    media_type: str | None
    file_size: int | None
    version: int | None
    download_url: str | None


class HealthResult(TypedDict):
    ok: bool
    base_url: str


mcp = FastMCP("confluence-data-center")
_client: ConfluenceDataCenterClient | None = None

READ_ONLY_TOOL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
WRITE_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def get_page_storage(page_id: str) -> PageStorageResult:
    """Return a Confluence page's raw storage-format XHTML by content ID."""
    page = await _get_client().get_page(page_id)
    return _page_storage_result(page)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def get_page_storage_by_title(space_key: str, title: str) -> PageStorageResult:
    """Return raw storage-format XHTML for the uniquely matching page title in a space."""
    page = await _get_client().find_page_by_title(space_key, title)
    return _page_storage_result(page)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def search_pages(cql: str, limit: int = 10, start: int = 0) -> list[PageSummaryResult]:
    """Search Confluence content with CQL and return page summaries."""
    normalized_limit = _bounded_int(limit, minimum=1, maximum=50, name="limit")
    normalized_start = _bounded_int(start, minimum=0, maximum=100_000, name="start")
    pages = await _get_client().search(cql, limit=normalized_limit, start=normalized_start)
    return [_page_summary_result(page) for page in pages]


@mcp.tool(annotations=READ_ONLY_TOOL)
async def get_page_children(
    page_id: str, limit: int = 25, start: int = 0
) -> list[PageSummaryResult]:
    """Find direct child pages under a Confluence page by content ID."""
    normalized_limit = _bounded_int(limit, minimum=1, maximum=50, name="limit")
    normalized_start = _bounded_int(start, minimum=0, maximum=100_000, name="start")
    pages = await _get_client().get_page_children(
        page_id,
        limit=normalized_limit,
        start=normalized_start,
    )
    return [_page_summary_result(page) for page in pages]


@mcp.tool(annotations=READ_ONLY_TOOL)
async def get_attachment_list(
    page_id: str, limit: int = 25, start: int = 0
) -> list[AttachmentSummaryResult]:
    """Return attachment metadata for a Confluence page by content ID."""
    normalized_limit = _bounded_int(limit, minimum=1, maximum=50, name="limit")
    normalized_start = _bounded_int(start, minimum=0, maximum=100_000, name="start")
    attachments = await _get_client().get_attachment_list(
        page_id,
        limit=normalized_limit,
        start=normalized_start,
    )
    return [_attachment_summary_result(attachment) for attachment in attachments]


@mcp.tool(annotations=READ_ONLY_TOOL)
async def download_attachment(attachment_id: str) -> CallToolResult:
    """Download a Confluence attachment as an embedded resource for LLM analysis."""
    attachment = await _get_client().download_attachment(attachment_id)
    return _downloaded_attachment_result(attachment)


@mcp.tool(annotations=WRITE_TOOL)
async def update_page_storage(
    page_id: str,
    storage: str,
    title: str | None = None,
    version_comment: str | None = None,
    minor_edit: bool = False,
) -> PageUpdateResultData:
    """Replace a page's raw storage-format XHTML, automatically incrementing its version."""
    result = await _get_client().update_storage(
        page_id,
        storage,
        title=title,
        version_comment=version_comment,
        minor_edit=minor_edit,
    )
    return _page_update_result(result)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def health_check() -> HealthResult:
    """Confirm that the MCP server can load Confluence configuration."""
    config = load_config()
    return {"ok": True, "base_url": config.base_url}


def main() -> None:
    mcp.run()


def _get_client() -> ConfluenceDataCenterClient:
    global _client
    if _client is None:
        _client = ConfluenceDataCenterClient(load_config())
    return _client


def _page_summary_result(page: PageSummary) -> PageSummaryResult:
    return {
        "id": page.id,
        "title": page.title,
        "type": page.type,
        "space_key": page.space_key,
        "version": page.version,
    }


def _page_storage_result(page: PageStorage) -> PageStorageResult:
    return {
        "id": page.id,
        "title": page.title,
        "type": page.type,
        "space_key": page.space_key,
        "version": page.version,
        "storage": page.storage,
    }


def _attachment_summary_result(attachment: AttachmentSummary) -> AttachmentSummaryResult:
    return {
        "id": attachment.id,
        "title": attachment.title,
        "media_type": attachment.media_type,
        "file_size": attachment.file_size,
        "version": attachment.version,
        "download_url": attachment.download_url,
    }


def _downloaded_attachment_result(attachment: DownloadedAttachment) -> CallToolResult:
    uri_title = quote(attachment.title, safe="")
    uri = f"confluence://attachment/{attachment.id}/{uri_title}"
    metadata = {
        "id": attachment.id,
        "title": attachment.title,
        "media_type": attachment.media_type,
    }
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps(metadata, indent=2),
            ),
            EmbeddedResource(
                type="resource",
                resource=BlobResourceContents(
                    uri=cast(Any, uri),
                    mimeType=attachment.media_type,
                    blob=attachment.data_base64,
                ),
            ),
        ],
    )


def _page_update_result(result: PageUpdateResult) -> PageUpdateResultData:
    return {
        "id": result.id,
        "title": result.title,
        "type": result.type,
        "version": result.version,
    }


def _bounded_int(value: int, *, minimum: int, maximum: int, name: str) -> int:
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


if __name__ == "__main__":
    main()
