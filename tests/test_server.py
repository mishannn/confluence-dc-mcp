from __future__ import annotations

import asyncio

from confluence_dc_mcp.server import mcp


def test_tool_annotations_identify_read_and_write_tools() -> None:
    async def run() -> None:
        tools = {tool.name: tool for tool in await mcp.list_tools()}

        for name in (
            "get_page_storage",
            "get_page_storage_by_title",
            "search_pages",
            "get_page_children",
            "get_attachment_list",
            "download_attachment",
            "health_check",
        ):
            annotations = tools[name].annotations
            assert annotations is not None
            assert annotations.readOnlyHint is True
            assert annotations.destructiveHint is False
            assert annotations.idempotentHint is True

        annotations = tools["update_page_storage"].annotations
        assert annotations is not None
        assert annotations.readOnlyHint is False
        assert annotations.destructiveHint is True
        assert annotations.idempotentHint is False

    asyncio.run(run())
