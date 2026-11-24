from app.core.storage import (
    ObjectInfo,
    PresignedUpload,
    content_disposition,
    download_cache_control,
    is_inline_content_type,
)


class FakeStorage:
    """In-memory `Storage`. `objects` maps key -> size; `simulate_upload` plays the browser."""

    def __init__(self, public_base_url: str | None = None) -> None:
        self.objects: dict[str, int] = {}
        self.deleted: list[str] = []
        self.fail_delete = False
        self.public_base_url = public_base_url

    def simulate_upload(self, key: str, size: int) -> None:
        self.objects[key] = size

    def presign_upload(
        self, key: str, *, content_type: str, size: int, expires_in: int
    ) -> PresignedUpload:
        return PresignedUpload(
            url=f"https://bucket.test/{key}?upload&size={size}&exp={expires_in}",
            headers={"Content-Type": content_type},
        )

    def presign_download(
        self,
        key: str,
        *,
        filename: str,
        content_type: str,
        expires_in: int,
        public: bool = False,
    ) -> str:
        disposition = content_disposition(
            filename, inline=is_inline_content_type(content_type)
        )
        cache = download_cache_control(expires_in=expires_in, public=public)
        return (
            f"https://bucket.test/{key}?disposition={disposition}"
            f"&exp={expires_in}&cache={cache}"
        )

    def public_url(self, key: str) -> str | None:
        if not self.public_base_url:
            return None
        return f"{self.public_base_url}/{key}"

    def head(self, key: str) -> ObjectInfo | None:
        size = self.objects.get(key)
        return None if size is None else ObjectInfo(size=size)

    def delete(self, key: str) -> None:
        if self.fail_delete:
            raise RuntimeError("boom")
        self.objects.pop(key, None)
        self.deleted.append(key)
