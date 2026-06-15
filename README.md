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
