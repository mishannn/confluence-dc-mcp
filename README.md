# Confluence Data Center MCP

Typed Python MCP server for Confluence Data Center raw storage operations.

## Requirements

- Python 3.11+
- `uv`
- Confluence Data Center REST API access
- Either a Confluence Personal Access Token or username/password auth

## Setup

```bash
uv sync
cp .env.example .env
```

Set the values in `.env`, then run:

```bash
set -a
source .env
set +a
uv run confluence-dc-mcp
```

## Run with uvx

After the package is published, it can be run without cloning the repository:

```bash
CONFLUENCE_BASE_URL="https://confluence.example.com" \
CONFLUENCE_PAT="replace-with-token" \
uvx confluence-dc-mcp
```

Or with username/password authentication:

```bash
CONFLUENCE_BASE_URL="https://confluence.example.com" \
CONFLUENCE_USERNAME="alice" \
CONFLUENCE_PASSWORD="replace-with-password" \
uvx confluence-dc-mcp
```

For an MCP client using `uvx` with a Personal Access Token:

```json
{
  "mcpServers": {
    "confluence-data-center": {
      "command": "uvx",
      "args": ["confluence-dc-mcp"],
      "env": {
        "CONFLUENCE_BASE_URL": "https://confluence.example.com",
        "CONFLUENCE_PAT": "replace-with-token"
      }
    }
  }
}
```

For an MCP client using `uvx` with username/password authentication:

```json
{
  "mcpServers": {
    "confluence-data-center": {
      "command": "uvx",
      "args": ["confluence-dc-mcp"],
      "env": {
        "CONFLUENCE_BASE_URL": "https://confluence.example.com",
        "CONFLUENCE_USERNAME": "alice",
        "CONFLUENCE_PASSWORD": "replace-with-password"
      }
    }
  }
}
```

For MCP clients that pass environment variables directly, use:

```json
{
  "mcpServers": {
    "confluence-data-center": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/mikhail/Projects/mcp-atlassian-confluence-raw-storage",
        "run",
        "confluence-dc-mcp"
      ],
      "env": {
        "CONFLUENCE_BASE_URL": "https://confluence.example.com",
        "CONFLUENCE_PAT": "replace-with-token"
      }
    }
  }
}
```

## Environment

`CONFLUENCE_BASE_URL` is required and must be the root Confluence URL.

Use one authentication mode:

- `CONFLUENCE_PAT`
- `CONFLUENCE_USERNAME` and `CONFLUENCE_PASSWORD`

Optional settings:

- `CONFLUENCE_VERIFY_SSL`, defaults to `true`
- `CONFLUENCE_TIMEOUT_SECONDS`, defaults to `30`

## Tools

- `health_check`: validates server configuration.
- `search_pages`: searches content with CQL and returns page summaries.
- `get_page_storage`: returns raw storage-format XHTML for a content ID.
- `get_page_storage_by_title`: returns raw storage-format XHTML for a unique page title in a space.
- `get_page_children`: returns direct child page summaries for a content ID.
- `get_page_history`: returns page version history entries for a content ID.
- `create_page`: creates a page from raw storage-format XHTML.
- `move_page`: moves a page before, after, or under a target page.
- `get_comments`: returns page comments with storage-format bodies.
- `add_comment`: adds a storage-format comment to a page.
- `reply_to_comment`: replies to an existing comment with storage-format XHTML.
- `get_labels`: returns labels for a content ID.
- `add_label`: adds a label to a content ID.
- `search_user`: searches Confluence users through CQL-backed site search.
- `get_attachment_list`: returns attachment metadata for a page content ID.
- `download_attachment`: downloads an attachment as an embedded MCP resource for LLM analysis.
- `upload_attachment`: uploads a local file as a page attachment.
- `upload_attachments`: uploads multiple local files as page attachments.
- `download_attachment_to_file`: downloads an attachment to a local file path.
- `get_page_images`: downloads image attachments from a page as embedded MCP resources.
- `update_page_storage`: replaces raw storage-format XHTML and increments the Confluence version.

## Development

```bash
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

## CI and Release

GitHub Actions run linting, strict type checking, tests, and package build on push and pull
requests.

Publishing runs when a GitHub Release is published. The workflow uses PyPI Trusted Publishing,
so configure a PyPI trusted publisher for this repository with:

- workflow: `publish.yml`
- environment: `pypi`
- package name: `confluence-dc-mcp`
