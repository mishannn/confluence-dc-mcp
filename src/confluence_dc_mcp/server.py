from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from typing_extensions import TypedDict

from confluence_dc_mcp.client import (
    ConfluenceDataCenterClient,
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
