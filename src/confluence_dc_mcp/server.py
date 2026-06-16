from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from mcp.types import (
    BlobResourceContents,
    CallToolResult,
    ContentBlock,
    EmbeddedResource,
    TextContent,
    ToolAnnotations,
)
from typing_extensions import TypedDict

from confluence_dc_mcp.client import (
    AttachmentSummary,
    CommentSummary,
    ConfluenceDataCenterClient,
    DownloadedAttachment,
    DownloadedAttachmentBytes,
    LabelSummary,
    MovePageResult,
    PageHistoryItem,
    PageStorage,
    PageSummary,
    PageUpdateResult,
    UserSummary,
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


class PageHistoryResult(TypedDict):
    number: int
    by_username: str | None
    by_display_name: str | None
    when: str | None
    message: str | None
    minor_edit: bool | None


class MovePageResultData(TypedDict):
    page_id: str
    target_id: str
    position: str
    moved: bool


class CommentSummaryResult(TypedDict):
    id: str
    title: str
    type: str
    container_id: str | None
    version: int | None
    storage: str | None


class LabelSummaryResult(TypedDict):
    name: str
    prefix: str | None
    id: str | None


class UserSummaryResult(TypedDict):
    username: str | None
    user_key: str | None
    account_id: str | None
    display_name: str | None
    email: str | None
    profile_picture_path: str | None
    url: str | None


class AttachmentSummaryResult(TypedDict):
    id: str
    title: str
    media_type: str | None
    file_size: int | None
    version: int | None
    download_url: str | None


class AttachmentFileResult(TypedDict):
    id: str
    title: str
    media_type: str
    file_path: str
    bytes_written: int


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
async def get_page_history(
    page_id: str, limit: int = 25, start: int = 0
) -> list[PageHistoryResult]:
    """Return version history entries for a Confluence page by content ID."""
    normalized_limit = _bounded_int(limit, minimum=1, maximum=50, name="limit")
    normalized_start = _bounded_int(start, minimum=0, maximum=100_000, name="start")
    history = await _get_client().get_page_history(
        page_id,
        limit=normalized_limit,
        start=normalized_start,
    )
    return [_page_history_result(item) for item in history]


@mcp.tool(annotations=WRITE_TOOL)
async def create_page(
    space_key: str,
    title: str,
    storage: str,
    parent_id: str | None = None,
) -> PageUpdateResultData:
    """Create a Confluence page with raw storage-format XHTML."""
    result = await _get_client().create_page(
        space_key,
        title,
        storage,
        parent_id=parent_id,
    )
    return _page_update_result(result)


@mcp.tool(annotations=WRITE_TOOL)
async def move_page(
    page_id: str,
    target_id: str,
    position: Literal["before", "after", "append"] = "append",
) -> MovePageResultData:
    """Move a page before, after, or under a target page."""
    result = await _get_client().move_page(page_id, target_id, position=position)
    return _move_page_result(result)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def get_comments(
    page_id: str, limit: int = 25, start: int = 0
) -> list[CommentSummaryResult]:
    """Return page comments with storage-format bodies by page content ID."""
    normalized_limit = _bounded_int(limit, minimum=1, maximum=50, name="limit")
    normalized_start = _bounded_int(start, minimum=0, maximum=100_000, name="start")
    comments = await _get_client().get_comments(
        page_id,
        limit=normalized_limit,
        start=normalized_start,
    )
    return [_comment_summary_result(comment) for comment in comments]


@mcp.tool(annotations=WRITE_TOOL)
async def add_comment(page_id: str, storage: str) -> CommentSummaryResult:
    """Add a storage-format comment to a Confluence page."""
    comment = await _get_client().add_comment(page_id, storage)
    return _comment_summary_result(comment)


@mcp.tool(annotations=WRITE_TOOL)
async def reply_to_comment(comment_id: str, storage: str) -> CommentSummaryResult:
    """Reply to an existing Confluence comment with a storage-format body."""
    comment = await _get_client().reply_to_comment(comment_id, storage)
    return _comment_summary_result(comment)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def get_labels(
    content_id: str, limit: int = 25, start: int = 0, prefix: str | None = None
) -> list[LabelSummaryResult]:
    """Return labels for a Confluence content ID."""
    normalized_limit = _bounded_int(limit, minimum=1, maximum=50, name="limit")
    normalized_start = _bounded_int(start, minimum=0, maximum=100_000, name="start")
    labels = await _get_client().get_labels(
        content_id,
        limit=normalized_limit,
        start=normalized_start,
        prefix=prefix,
    )
    return [_label_summary_result(label) for label in labels]


@mcp.tool(annotations=WRITE_TOOL)
async def add_label(
    content_id: str,
    name: str,
    prefix: str = "global",
) -> list[LabelSummaryResult]:
    """Add a label to a Confluence content ID."""
    labels = await _get_client().add_label(content_id, name, prefix=prefix)
    return [_label_summary_result(label) for label in labels]


@mcp.tool(annotations=READ_ONLY_TOOL)
async def search_user(query: str, limit: int = 10, start: int = 0) -> list[UserSummaryResult]:
    """Search Confluence users by username query."""
    normalized_limit = _bounded_int(limit, minimum=1, maximum=50, name="limit")
    normalized_start = _bounded_int(start, minimum=0, maximum=100_000, name="start")
    users = await _get_client().search_user(query, limit=normalized_limit, start=normalized_start)
    return [_user_summary_result(user) for user in users]


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
async def upload_attachment(
    page_id: str,
    file_path: str,
    comment: str | None = None,
    minor_edit: bool = False,
) -> AttachmentSummaryResult:
    """Upload a local file as a Confluence page attachment."""
    attachment = await _get_client().upload_attachment(
        page_id,
        file_path,
        comment=comment,
        minor_edit=minor_edit,
    )
    return _attachment_summary_result(attachment)


@mcp.tool(annotations=WRITE_TOOL)
async def upload_attachments(
    page_id: str,
    file_paths: list[str],
    comment: str | None = None,
    minor_edit: bool = False,
) -> list[AttachmentSummaryResult]:
    """Upload multiple local files as Confluence page attachments."""
    attachments = await _get_client().upload_attachments(
        page_id,
        file_paths,
        comment=comment,
        minor_edit=minor_edit,
    )
    return [_attachment_summary_result(attachment) for attachment in attachments]


@mcp.tool(annotations=WRITE_TOOL)
async def download_attachment_to_file(attachment_id: str, file_path: str) -> AttachmentFileResult:
    """Download a Confluence attachment to a local file path."""
    attachment = await _get_client().download_attachment_bytes(attachment_id)
    path = Path(file_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(attachment.data)
    return _attachment_file_result(attachment, str(path))


@mcp.tool(annotations=READ_ONLY_TOOL)
async def get_page_images(page_id: str, limit: int = 50, start: int = 0) -> CallToolResult:
    """Download image attachments from a Confluence page as embedded MCP resources."""
    normalized_limit = _bounded_int(limit, minimum=1, maximum=50, name="limit")
    normalized_start = _bounded_int(start, minimum=0, maximum=100_000, name="start")
    images = await _get_client().get_page_images(
        page_id,
        limit=normalized_limit,
        start=normalized_start,
    )
    return _downloaded_attachments_result(images)


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


def _page_history_result(item: PageHistoryItem) -> PageHistoryResult:
    return {
        "number": item.number,
        "by_username": item.by_username,
        "by_display_name": item.by_display_name,
        "when": item.when,
        "message": item.message,
        "minor_edit": item.minor_edit,
    }


def _move_page_result(result: MovePageResult) -> MovePageResultData:
    return {
        "page_id": result.page_id,
        "target_id": result.target_id,
        "position": result.position,
        "moved": result.moved,
    }


def _comment_summary_result(comment: CommentSummary) -> CommentSummaryResult:
    return {
        "id": comment.id,
        "title": comment.title,
        "type": comment.type,
        "container_id": comment.container_id,
        "version": comment.version,
        "storage": comment.storage,
    }


def _label_summary_result(label: LabelSummary) -> LabelSummaryResult:
    return {
        "name": label.name,
        "prefix": label.prefix,
        "id": label.id,
    }


def _user_summary_result(user: UserSummary) -> UserSummaryResult:
    return {
        "username": user.username,
        "user_key": user.user_key,
        "account_id": user.account_id,
        "display_name": user.display_name,
        "email": user.email,
        "profile_picture_path": user.profile_picture_path,
        "url": user.url,
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


def _attachment_file_result(
    attachment: DownloadedAttachmentBytes,
    file_path: str,
) -> AttachmentFileResult:
    return {
        "id": attachment.id,
        "title": attachment.title,
        "media_type": attachment.media_type,
        "file_path": file_path,
        "bytes_written": len(attachment.data),
    }


def _downloaded_attachment_result(attachment: DownloadedAttachment) -> CallToolResult:
    return _downloaded_attachments_result([attachment])


def _downloaded_attachments_result(attachments: list[DownloadedAttachment]) -> CallToolResult:
    metadata = [
        {
            "id": attachment.id,
            "title": attachment.title,
            "media_type": attachment.media_type,
        }
        for attachment in attachments
    ]
    content: list[ContentBlock] = [
        TextContent(
            type="text",
            text=json.dumps(metadata, indent=2),
        )
    ]
    for attachment in attachments:
        content.append(_downloaded_attachment_resource(attachment))

    return CallToolResult(content=content)


def _downloaded_attachment_resource(attachment: DownloadedAttachment) -> EmbeddedResource:
    uri_title = quote(attachment.title, safe="")
    uri = f"confluence://attachment/{attachment.id}/{uri_title}"
    return EmbeddedResource(
        type="resource",
        resource=BlobResourceContents(
            uri=cast(Any, uri),
            mimeType=attachment.media_type,
            blob=attachment.data_base64,
        ),
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
