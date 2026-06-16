from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict, cast

import httpx

from confluence_dc_mcp.config import ConfluenceConfig


class SpaceRef(TypedDict):
    key: str


class VersionRef(TypedDict):
    number: int


class LinkRef(TypedDict, total=False):
    base: str
    download: str
    webui: str


class BodyValue(TypedDict):
    value: str
    representation: str


class BodyStorage(TypedDict):
    storage: BodyValue


class ContentResponse(TypedDict):
    id: str
    type: str
    title: str
    space: NotRequired[SpaceRef]
    version: NotRequired[VersionRef]
    body: NotRequired[BodyStorage]
    metadata: NotRequired[dict[str, Any]]
    extensions: NotRequired[dict[str, Any]]
    _links: NotRequired[LinkRef]


class SearchResponse(TypedDict):
    results: list[ContentResponse]
    size: int
    limit: int
    start: int


@dataclass(frozen=True, slots=True)
class PageSummary:
    id: str
    title: str
    type: str
    space_key: str | None
    version: int | None


@dataclass(frozen=True, slots=True)
class PageStorage:
    id: str
    title: str
    type: str
    space_key: str | None
    version: int
    storage: str


@dataclass(frozen=True, slots=True)
class PageUpdateResult:
    id: str
    title: str
    type: str
    version: int


@dataclass(frozen=True, slots=True)
class AttachmentSummary:
    id: str
    title: str
    media_type: str | None
    file_size: int | None
    version: int | None
    download_url: str | None


@dataclass(frozen=True, slots=True)
class DownloadedAttachment:
    id: str
    title: str
    media_type: str
    data_base64: str


class ConfluenceDataCenterClient:
    def __init__(
        self,
        config: ConfluenceConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"Accept": "application/json"}
        auth: httpx.Auth | None = None

        if config.pat is not None:
            headers["Authorization"] = f"Bearer {config.pat}"
        elif config.username is not None and config.password is not None:
            auth = httpx.BasicAuth(config.username, config.password)

        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            headers=headers,
            auth=auth,
            verify=config.verify_ssl,
            timeout=config.timeout_seconds,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_page(self, page_id: str) -> PageStorage:
        data = await self._request_json(
            "GET",
            f"/rest/api/content/{page_id}",
            params={"expand": "space,version,body.storage"},
        )
        return _page_storage_from_response(_as_content_response(data))

    async def find_page_by_title(self, space_key: str, title: str) -> PageStorage:
        escaped_space = _escape_cql(space_key)
        escaped_title = _escape_cql(title)
        cql = f'type = page and space = "{escaped_space}" and title = "{escaped_title}"'
        response = await self.search(cql, limit=2)
        if not response:
            raise ConfluenceNotFoundError(
                f"No page found with title {title!r} in space {space_key!r}."
            )
        if len(response) > 1:
            raise ConfluenceError(
                f"More than one page matched title {title!r} in space {space_key!r}."
            )
        return await self.get_page(response[0].id)

    async def search(self, cql: str, limit: int = 10, start: int = 0) -> list[PageSummary]:
        data = await self._request_json(
            "GET",
            "/rest/api/content/search",
            params={"cql": cql, "limit": limit, "start": start, "expand": "space,version"},
        )
        response = _as_search_response(data)
        return [_page_summary_from_response(item) for item in response["results"]]

    async def get_page_children(
        self, page_id: str, limit: int = 25, start: int = 0
    ) -> list[PageSummary]:
        data = await self._request_json(
            "GET",
            f"/rest/api/content/{page_id}/child/page",
            params={"limit": limit, "start": start, "expand": "space,version"},
        )
        response = _as_search_response(data)
        return [_page_summary_from_response(item) for item in response["results"]]

    async def get_attachment_list(
        self, page_id: str, limit: int = 25, start: int = 0
    ) -> list[AttachmentSummary]:
        data = await self._request_json(
            "GET",
            f"/rest/api/content/{page_id}/child/attachment",
            params={
                "limit": limit,
                "start": start,
                "expand": "version,metadata,extensions",
            },
        )
        response = _as_search_response(data)
        return [_attachment_summary_from_response(item) for item in response["results"]]

    async def download_attachment(self, attachment_id: str) -> DownloadedAttachment:
        metadata = await self._get_attachment_metadata(attachment_id)
        download_url = _attachment_download_url(metadata)
        if download_url is None:
            raise ConfluenceError("Confluence attachment response did not include a download URL.")

        data = await self._request_bytes("GET", download_url)
        media_type = _attachment_media_type(metadata) or "application/octet-stream"
        return DownloadedAttachment(
            id=metadata["id"],
            title=metadata["title"],
            media_type=media_type,
            data_base64=base64.b64encode(data).decode("ascii"),
        )

    async def update_storage(
        self,
        page_id: str,
        storage: str,
        *,
        title: str | None = None,
        version_comment: str | None = None,
        minor_edit: bool = False,
    ) -> PageUpdateResult:
        current = await self.get_page(page_id)
        next_title = current.title if title is None else title
        payload: dict[str, Any] = {
            "id": current.id,
            "type": current.type,
            "title": next_title,
            "version": {
                "number": current.version + 1,
                "minorEdit": minor_edit,
            },
            "body": {
                "storage": {
                    "value": storage,
                    "representation": "storage",
                }
            },
        }
        if current.space_key is not None:
            payload["space"] = {"key": current.space_key}
        if version_comment is not None:
            payload["version"]["message"] = version_comment

        data = await self._request_json("PUT", f"/rest/api/content/{page_id}", json=payload)
        updated = _as_content_response(data)
        version = updated.get("version", {}).get("number")
        if not isinstance(version, int):
            raise ConfluenceError("Confluence update response did not include a version number.")
        return PageUpdateResult(
            id=updated["id"],
            title=updated["title"],
            type=updated["type"],
            version=version,
        )

    async def _request_json(
        self,
        method: Literal["GET", "PUT"],
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        json: dict[str, Any] | None = None,
    ) -> object:
        try:
            response = await self._client.request(method, url, params=params, json=json)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _error_from_response(exc.response) from exc
        except httpx.HTTPError as exc:
            raise ConfluenceError(f"Confluence request failed: {exc}") from exc

        return response.json()

    async def _request_bytes(
        self,
        method: Literal["GET"],
        url: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> bytes:
        try:
            response = await self._client.request(
                method,
                url,
                params=params,
                headers={"Accept": "*/*"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _error_from_response(exc.response) from exc
        except httpx.HTTPError as exc:
            raise ConfluenceError(f"Confluence request failed: {exc}") from exc

        return response.content

    async def _get_attachment_metadata(self, attachment_id: str) -> ContentResponse:
        data = await self._request_json(
            "GET",
            f"/rest/api/content/{attachment_id}",
            params={"expand": "version,metadata,extensions"},
        )
        metadata = _as_content_response(data)
        if metadata["type"] != "attachment":
            raise ConfluenceError(f"Content {attachment_id!r} is not an attachment.")
        return metadata


class ConfluenceError(RuntimeError):
    pass


class ConfluenceNotFoundError(ConfluenceError):
    pass


def _page_summary_from_response(data: ContentResponse) -> PageSummary:
    return PageSummary(
        id=data["id"],
        title=data["title"],
        type=data["type"],
        space_key=_space_key(data),
        version=_version_number(data),
    )


def _page_storage_from_response(data: ContentResponse) -> PageStorage:
    body = data.get("body")
    version = _version_number(data)
    if version is None:
        raise ConfluenceError("Confluence response did not include a page version.")
    if body is None or "storage" not in body:
        raise ConfluenceError("Confluence response did not include body.storage.")

    storage = body["storage"]
    if storage.get("representation") != "storage":
        raise ConfluenceError("Confluence response body is not storage representation.")

    return PageStorage(
        id=data["id"],
        title=data["title"],
        type=data["type"],
        space_key=_space_key(data),
        version=version,
        storage=storage["value"],
    )


def _attachment_summary_from_response(data: ContentResponse) -> AttachmentSummary:
    return AttachmentSummary(
        id=data["id"],
        title=data["title"],
        media_type=_attachment_media_type(data),
        file_size=_attachment_file_size(data),
        version=_version_number(data),
        download_url=_attachment_download_url(data),
    )


def _attachment_media_type(data: ContentResponse) -> str | None:
    metadata = data.get("metadata")
    if metadata is not None:
        value = metadata.get("mediaType")
        if isinstance(value, str):
            return value

    extensions = data.get("extensions")
    if extensions is not None:
        value = extensions.get("mediaType")
        if isinstance(value, str):
            return value

    return None


def _attachment_file_size(data: ContentResponse) -> int | None:
    extensions = data.get("extensions")
    if extensions is None:
        return None
    value = extensions.get("fileSize")
    if isinstance(value, int):
        return value
    return None


def _attachment_download_url(data: ContentResponse) -> str | None:
    links = data.get("_links")
    if links is None:
        return None
    value = links.get("download")
    if isinstance(value, str):
        return value
    return None


def _space_key(data: ContentResponse) -> str | None:
    space = data.get("space")
    if space is None:
        return None
    return space.get("key")


def _version_number(data: ContentResponse) -> int | None:
    version = data.get("version")
    if version is None:
        return None
    return version.get("number")


def _as_content_response(data: object) -> ContentResponse:
    if not isinstance(data, dict):
        raise ConfluenceError("Expected a JSON object from Confluence.")
    for key in ("id", "type", "title"):
        if not isinstance(data.get(key), str):
            raise ConfluenceError(f"Confluence response is missing string field {key!r}.")
    return cast(ContentResponse, data)


def _as_search_response(data: object) -> SearchResponse:
    if not isinstance(data, dict):
        raise ConfluenceError("Expected a JSON object from Confluence search.")
    results = data.get("results")
    if not isinstance(results, list):
        raise ConfluenceError("Confluence search response is missing results.")
    return cast(SearchResponse, data)


def _error_from_response(response: httpx.Response) -> ConfluenceError:
    if response.status_code == 404:
        return ConfluenceNotFoundError("Confluence content was not found.")

    details = _extract_error_message(response)
    return ConfluenceError(f"Confluence returned HTTP {response.status_code}: {details}")


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]

    if isinstance(payload, dict):
        for key in ("message", "errorMessage", "authorized", "valid"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        if "errors" in payload:
            return str(payload["errors"])

    return str(payload)[:500]


def _escape_cql(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
