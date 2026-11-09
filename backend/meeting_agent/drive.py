import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from google.oauth2 import service_account
from googleapiclient.discovery import build

from meeting_agent.parsers import GOOGLE_DOC_MIME

_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
_FILE_FIELDS = "nextPageToken, files(id, name, mimeType, md5Checksum, modifiedTime)"


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime_type: str
    # Changes when the content changes, so an edited file is treated as new.
    revision: str
    modified_time: datetime


class DriveClient(Protocol):
    def list_files(self) -> list[DriveFile]: ...

    def download(self, file: DriveFile) -> bytes: ...


class GoogleDriveClient:
    """Reads one Drive folder. Subfolders are not searched."""

    def __init__(self, service: Any, folder_id: str) -> None:
        self._service = service
        self._folder_id = folder_id

    @classmethod
    def from_service_account(cls, key_file: Path, folder_id: str) -> "GoogleDriveClient":
        credentials = service_account.Credentials.from_service_account_file(
            str(key_file), scopes=_SCOPES
        )
        return cls(build("drive", "v3", credentials=credentials, cache_discovery=False), folder_id)

    def list_files(self) -> list[DriveFile]:
        files: list[DriveFile] = []
        page_token = None
        while True:
            response = (
                self._service.files()
                .list(
                    q=f"'{self._folder_id}' in parents and trashed = false",
                    fields=_FILE_FIELDS,
                    pageSize=100,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute(num_retries=3)
            )
            files.extend(_to_drive_file(item) for item in response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return files

    def download(self, file: DriveFile) -> bytes:
        files = self._service.files()
        if file.mime_type == GOOGLE_DOC_MIME:
            request = files.export_media(fileId=file.id, mimeType="text/plain")
        else:
            request = files.get_media(fileId=file.id, supportsAllDrives=True)
        return request.execute(num_retries=3)


def _to_drive_file(item: dict[str, str]) -> DriveFile:
    modified = item["modifiedTime"]
    return DriveFile(
        id=item["id"],
        name=item["name"],
        mime_type=item["mimeType"],
        # Google Docs have no checksum.
        revision=item.get("md5Checksum") or modified,
        modified_time=datetime.fromisoformat(modified),
    )


class LocalFolderDrive:
    """Treats a local folder as the Drive folder, for running without Google credentials."""

    def __init__(self, folder: Path | str) -> None:
        self._folder = Path(folder)

    def list_files(self) -> list[DriveFile]:
        return [self._to_drive_file(p) for p in sorted(self._folder.iterdir()) if p.is_file()]

    def download(self, file: DriveFile) -> bytes:
        return (self._folder / file.name).read_bytes()

    def _to_drive_file(self, path: Path) -> DriveFile:
        return DriveFile(
            id=path.name,
            name=path.name,
            mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            revision=hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest(),
            modified_time=datetime.fromtimestamp(path.stat().st_mtime, UTC),
        )
