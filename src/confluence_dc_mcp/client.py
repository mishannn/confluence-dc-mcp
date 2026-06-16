from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict, cast

import httpx

from confluence_dc_mcp.config import ConfluenceConfig


class SpaceRef(TypedDict):
    key: str


class VersionRef(TypedDict):
    number: int


class UserRef(TypedDict, total=False):
    username: str
    userKey: str
    accountId: str
    displayName: str
    email: str
    emailAddress: str
    profilePicture: dict[str, Any]


class ContainerRef(TypedDict, total=False):
    id: str
    type: str
    title: str


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
    container: NotRequired[ContainerRef]
    metadata: NotRequired[dict[str, Any]]
    extensions: NotRequired[dict[str, Any]]
    _links: NotRequired[LinkRef]


class SearchResponse(TypedDict):
    results: list[ContentResponse]
    size: int
    limit: int
    start: int


class VersionResponseRequired(TypedDict):
    number: int


class VersionResponse(VersionResponseRequired, total=False):
    by: UserRef
    when: str
    message: str
    minorEdit: bool


class VersionSearchResponse(TypedDict):
    results: list[VersionResponse]
    size: int
    limit: int
    start: int


class LabelResponse(TypedDict, total=False):
    id: str
    name: str
    prefix: str
    label: str


class LabelSearchResponse(TypedDict):
    results: list[LabelResponse]
    size: int
    limit: int
    start: int


class SearchResultResponse(TypedDict, total=False):
    title: str
    excerpt: str
    url: str


class SearchResultPageResponse(TypedDict):
    results: list[SearchResultResponse]
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
class PageHistoryItem:
    number: int
    by_username: str | None
    by_display_name: str | None
    when: str | None
    message: str | None
    minor_edit: bool | None


@dataclass(frozen=True, slots=True)
class MovePageResult:
    page_id: str
    target_id: str
    position: str
    moved: bool


@dataclass(frozen=True, slots=True)
class CommentSummary:
    id: str
    title: str
    type: str
    container_id: str | None
    version: int | None
    storage: str | None


@dataclass(frozen=True, slots=True)
class LabelSummary:
    name: str
    prefix: str | None
    id: str | None


@dataclass(frozen=True, slots=True)
class UserSummary:
    username: str | None
    user_key: str | None
    account_id: str | None
    display_name: str | None
    email: str | None
    profile_picture_path: str | None
    url: str | None


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


@dataclass(frozen=True, slots=True)
class DownloadedAttachmentBytes:
    id: str
    title: str
    media_type: str
    data: bytes


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

    async def get_page_history(
        self, page_id: str, limit: int = 25, start: int = 0
    ) -> list[PageHistoryItem]:
        data = await self._request_json(
            "GET",
            f"/rest/api/content/{page_id}/version",
            params={"limit": limit, "start": start, "expand": "by"},
        )
        response = _as_version_search_response(data)
        return [_page_history_from_response(item) for item in response["results"]]

    async def create_page(
        self,
        space_key: str,
        title: str,
        storage: str,
        *,
        parent_id: str | None = None,
    ) -> PageUpdateResult:
        payload: dict[str, Any] = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {
                "storage": {
                    "value": storage,
                    "representation": "storage",
                }
            },
        }
        if parent_id is not None:
            payload["ancestors"] = [{"id": parent_id}]

        data = await self._request_json("POST", "/rest/api/content", json=payload)
        page = _as_content_response(data)
        version = _version_number(page)
        if version is None:
            raise ConfluenceError("Confluence create response did not include a version number.")
        return PageUpdateResult(
            id=page["id"],
            title=page["title"],
            type=page["type"],
            version=version,
        )

    async def move_page(
        self,
        page_id: str,
        target_id: str,
        position: Literal["before", "after", "append"] = "append",
    ) -> MovePageResult:
        await self._request_optional_json(
            "PUT",
            f"/rest/api/content/{page_id}/move/{position}/{target_id}",
        )
        return MovePageResult(
            page_id=page_id,
            target_id=target_id,
            position=position,
            moved=True,
        )

    async def get_comments(
        self, page_id: str, limit: int = 25, start: int = 0
    ) -> list[CommentSummary]:
        data = await self._request_json(
            "GET",
            f"/rest/api/content/{page_id}/child/comment",
            params={
                "limit": limit,
                "start": start,
                "expand": "body.storage,version,container",
            },
        )
        response = _as_search_response(data)
        return [_comment_summary_from_response(item) for item in response["results"]]

    async def add_comment(self, page_id: str, storage: str) -> CommentSummary:
        return await self._create_comment(
            container_id=page_id,
            container_type="page",
            storage=storage,
        )

    async def reply_to_comment(self, comment_id: str, storage: str) -> CommentSummary:
        return await self._create_comment(
            container_id=comment_id,
            container_type="comment",
            storage=storage,
        )

    async def get_labels(
        self, content_id: str, limit: int = 25, start: int = 0, prefix: str | None = None
    ) -> list[LabelSummary]:
        params: dict[str, str | int] = {"limit": limit, "start": start}
        if prefix is not None:
            params["prefix"] = prefix
        data = await self._request_json(
            "GET",
            f"/rest/api/content/{content_id}/label",
            params=params,
        )
        response = _as_label_search_response(data)
        return [_label_summary_from_response(item) for item in response["results"]]

    async def add_label(
        self,
        content_id: str,
        name: str,
        *,
        prefix: str = "global",
    ) -> list[LabelSummary]:
        data = await self._request_json(
            "POST",
            f"/rest/api/content/{content_id}/label",
            json=[{"prefix": prefix, "name": name}],
        )
        labels = _as_label_list_response(data)
        return [_label_summary_from_response(item) for item in labels]

    async def search_user(
        self,
        query: str,
        limit: int = 10,
        start: int = 0,
    ) -> list[UserSummary]:
        escaped_query = _escape_cql(query)
        data = await self._request_json(
            "GET",
            "/rest/api/search",
            params={
                "cql": f'siteSearch ~ "{escaped_query}" and type = user',
                "limit": limit,
                "start": start,
            },
        )
        users = _as_search_result_page_response(data)
        return [_user_summary_from_search_result(user) for user in users["results"]]

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
        attachment = await self.download_attachment_bytes(attachment_id)
        return DownloadedAttachment(
            id=attachment.id,
            title=attachment.title,
            media_type=attachment.media_type,
            data_base64=base64.b64encode(attachment.data).decode("ascii"),
        )

    async def download_attachment_bytes(self, attachment_id: str) -> DownloadedAttachmentBytes:
        metadata = await self._get_attachment_metadata(attachment_id)
        download_url = _attachment_download_url(metadata)
        if download_url is None:
            raise ConfluenceError("Confluence attachment response did not include a download URL.")

        data = await self._request_bytes("GET", download_url)
        media_type = _attachment_media_type(metadata) or "application/octet-stream"
        return DownloadedAttachmentBytes(
            id=metadata["id"],
            title=metadata["title"],
            media_type=media_type,
            data=data,
        )

    async def upload_attachment(
        self,
        page_id: str,
        file_path: str,
        *,
        comment: str | None = None,
        minor_edit: bool = False,
    ) -> AttachmentSummary:
        path = Path(file_path).expanduser()
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        fields: dict[str, str] = {"minorEdit": str(minor_edit).lower()}
        if comment is not None:
            fields["comment"] = comment

        data = await self._request_multipart_json(
            "POST",
            f"/rest/api/content/{page_id}/child/attachment",
            data=fields,
            files={"file": (path.name, path.read_bytes(), media_type)},
        )
        attachment = _first_content_response(data)
        return _attachment_summary_from_response(attachment)

    async def upload_attachments(
        self,
        page_id: str,
        file_paths: list[str],
        *,
        comment: str | None = None,
        minor_edit: bool = False,
    ) -> list[AttachmentSummary]:
        attachments: list[AttachmentSummary] = []
        for file_path in file_paths:
            attachments.append(
                await self.upload_attachment(
                    page_id,
                    file_path,
                    comment=comment,
                    minor_edit=minor_edit,
                )
            )
        return attachments

    async def get_page_images(
        self, page_id: str, limit: int = 50, start: int = 0
    ) -> list[DownloadedAttachment]:
        attachments = await self.get_attachment_list(page_id, limit=limit, start=start)
        images: list[DownloadedAttachment] = []
        for attachment in attachments:
            if _is_image_attachment(attachment):
                images.append(await self.download_attachment(attachment.id))
        return images

    async def _create_comment(
        self,
        *,
        container_id: str,
        container_type: Literal["page", "comment"],
        storage: str,
    ) -> CommentSummary:
        data = await self._request_json(
            "POST",
            "/rest/api/content",
            json={
                "type": "comment",
                "container": {
                    "id": container_id,
                    "type": container_type,
                },
                "body": {
                    "storage": {
                        "value": storage,
                        "representation": "storage",
                    }
                },
            },
        )
        return _comment_summary_from_response(_as_content_response(data))

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
        method: Literal["GET", "POST", "PUT"],
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        json: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> object:
        try:
            response = await self._client.request(method, url, params=params, json=json)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _error_from_response(exc.response) from exc
        except httpx.HTTPError as exc:
            raise ConfluenceError(f"Confluence request failed: {exc}") from exc

        return response.json()

    async def _request_optional_json(
        self,
        method: Literal["PUT"],
        url: str,
    ) -> object | None:
        try:
            response = await self._client.request(method, url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _error_from_response(exc.response) from exc
        except httpx.HTTPError as exc:
            raise ConfluenceError(f"Confluence request failed: {exc}") from exc

        if not response.content:
            return None
        return cast(object, response.json())

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

    async def _request_multipart_json(
        self,
        method: Literal["POST"],
        url: str,
        *,
        data: dict[str, str],
        files: dict[str, Any],
    ) -> object:
        try:
            response = await self._client.request(
                method,
                url,
                data=data,
                files=files,
                headers={"X-Atlassian-Token": "nocheck"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _error_from_response(exc.response) from exc
        except httpx.HTTPError as exc:
            raise ConfluenceError(f"Confluence request failed: {exc}") from exc

        return response.json()

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


def _page_history_from_response(data: VersionResponse) -> PageHistoryItem:
    by = data.get("by", {})
    return PageHistoryItem(
        number=data["number"],
        by_username=_user_name(by),
        by_display_name=_user_display_name(by),
        when=data.get("when"),
        message=data.get("message"),
        minor_edit=data.get("minorEdit"),
    )


def _comment_summary_from_response(data: ContentResponse) -> CommentSummary:
    return CommentSummary(
        id=data["id"],
        title=data["title"],
        type=data["type"],
        container_id=_container_id(data),
        version=_version_number(data),
        storage=_storage_value(data),
    )


def _label_summary_from_response(data: LabelResponse) -> LabelSummary:
    return LabelSummary(
        name=data.get("name") or data.get("label") or "",
        prefix=data.get("prefix"),
        id=data.get("id"),
    )


def _user_summary_from_response(data: UserRef) -> UserSummary:
    profile_picture = data.get("profilePicture")
    profile_picture_path = None
    if isinstance(profile_picture, dict):
        path = profile_picture.get("path")
        if isinstance(path, str):
            profile_picture_path = path

    return UserSummary(
        username=_user_name(data),
        user_key=_user_key(data),
        account_id=_user_account_id(data),
        display_name=_user_display_name(data),
        email=_user_email(data),
        profile_picture_path=profile_picture_path,
        url=None,
    )


def _user_summary_from_search_result(data: SearchResultResponse) -> UserSummary:
    return UserSummary(
        username=None,
        user_key=None,
        account_id=None,
        display_name=data.get("title"),
        email=None,
        profile_picture_path=None,
        url=data.get("url"),
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


def _is_image_attachment(attachment: AttachmentSummary) -> bool:
    if attachment.media_type is not None and attachment.media_type.startswith("image/"):
        return True
    return mimetypes.guess_type(attachment.title)[0] in {
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/svg+xml",
        "image/webp",
    }


def _storage_value(data: ContentResponse) -> str | None:
    body = data.get("body")
    if body is None or "storage" not in body:
        return None
    storage = body["storage"]
    if storage.get("representation") != "storage":
        return None
    return storage["value"]


def _container_id(data: ContentResponse) -> str | None:
    container = data.get("container")
    if container is None:
        return None
    return container.get("id")


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


def _user_name(data: UserRef) -> str | None:
    value = data.get("username")
    if isinstance(value, str):
        return value
    return None


def _user_key(data: UserRef) -> str | None:
    value = data.get("userKey")
    if isinstance(value, str):
        return value
    return None


def _user_account_id(data: UserRef) -> str | None:
    value = data.get("accountId")
    if isinstance(value, str):
        return value
    return None


def _user_display_name(data: UserRef) -> str | None:
    value = data.get("displayName")
    if isinstance(value, str):
        return value
    return None


def _user_email(data: UserRef) -> str | None:
    value = data.get("email") or data.get("emailAddress")
    if isinstance(value, str):
        return value
    return None


def _as_content_response(data: object) -> ContentResponse:
    if not isinstance(data, dict):
        raise ConfluenceError("Expected a JSON object from Confluence.")
    for key in ("id", "type", "title"):
        if not isinstance(data.get(key), str):
            raise ConfluenceError(f"Confluence response is missing string field {key!r}.")
    return cast(ContentResponse, data)


def _first_content_response(data: object) -> ContentResponse:
    if isinstance(data, list):
        if not data:
            raise ConfluenceError("Confluence response did not include attachment metadata.")
        return _as_content_response(data[0])

    if isinstance(data, dict):
        results = data.get("results")
        if isinstance(results, list):
            if not results:
                raise ConfluenceError("Confluence response did not include attachment metadata.")
            return _as_content_response(results[0])
        return _as_content_response(data)

    raise ConfluenceError("Expected attachment metadata from Confluence.")


def _as_search_response(data: object) -> SearchResponse:
    if not isinstance(data, dict):
        raise ConfluenceError("Expected a JSON object from Confluence search.")
    results = data.get("results")
    if not isinstance(results, list):
        raise ConfluenceError("Confluence search response is missing results.")
    return cast(SearchResponse, data)


def _as_version_search_response(data: object) -> VersionSearchResponse:
    if not isinstance(data, dict):
        raise ConfluenceError("Expected a JSON object from Confluence version history.")
    results = data.get("results")
    if not isinstance(results, list):
        raise ConfluenceError("Confluence version history response is missing results.")
    for result in results:
        if not isinstance(result, dict) or not isinstance(result.get("number"), int):
            raise ConfluenceError("Confluence version history result is missing a number.")
    return cast(VersionSearchResponse, data)


def _as_label_search_response(data: object) -> LabelSearchResponse:
    if not isinstance(data, dict):
        raise ConfluenceError("Expected a JSON object from Confluence labels.")
    results = data.get("results")
    if not isinstance(results, list):
        raise ConfluenceError("Confluence label response is missing results.")
    return cast(LabelSearchResponse, data)


def _as_label_list_response(data: object) -> list[LabelResponse]:
    if isinstance(data, list):
        return cast(list[LabelResponse], data)
    if isinstance(data, dict):
        results = data.get("results")
        if isinstance(results, list):
            return cast(list[LabelResponse], results)
    raise ConfluenceError("Confluence label response is missing labels.")


def _as_search_result_page_response(data: object) -> SearchResultPageResponse:
    if not isinstance(data, dict):
        raise ConfluenceError("Expected a JSON object from Confluence search.")
    results = data.get("results")
    if not isinstance(results, list):
        raise ConfluenceError("Confluence search response is missing results.")
    return cast(SearchResultPageResponse, data)


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
