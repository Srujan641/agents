from datetime import UTC, datetime

from meeting_agent.drive import DriveFile, GoogleDriveClient, LocalFolderDrive
from meeting_agent.parsers import GOOGLE_DOC_MIME


class FakeRequest:
    def __init__(self, result):
        self._result = result

    def execute(self, num_retries=0):
        return self._result


class FakeFiles:
    """Stands in for the Google client's files() resource."""

    def __init__(self, pages):
        self.pages = pages
        self.list_calls = []
        self.exported = []
        self.fetched = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return FakeRequest(self.pages[len(self.list_calls) - 1])

    def export_media(self, fileId, mimeType):
        self.exported.append((fileId, mimeType))
        return FakeRequest(b"exported")

    def get_media(self, fileId, supportsAllDrives):
        self.fetched.append(fileId)
        return FakeRequest(b"raw")


class FakeService:
    def __init__(self, pages):
        self._files = FakeFiles(pages)

    def files(self):
        return self._files


def api_item(file_id, **extra):
    return {
        "id": file_id,
        "name": f"{file_id}.txt",
        "mimeType": "text/plain",
        "modifiedTime": "2026-11-02T10:00:00.000Z",
        **extra,
    }


def test_list_files_follows_pages_and_scopes_to_folder():
    service = FakeService(
        [
            {"files": [api_item("a", md5Checksum="hash-a")], "nextPageToken": "next"},
            {"files": [api_item("b", md5Checksum="hash-b")]},
        ]
    )
    files = GoogleDriveClient(service, "folder-1").list_files()

    assert [f.id for f in files] == ["a", "b"]
    assert files[0].revision == "hash-a"
    calls = service.files().list_calls
    assert calls[0]["q"] == "'folder-1' in parents and trashed = false"
    assert calls[1]["pageToken"] == "next"


def test_google_doc_without_checksum_uses_modified_time_as_revision():
    service = FakeService([{"files": [api_item("doc", mimeType=GOOGLE_DOC_MIME)]}])
    file = GoogleDriveClient(service, "folder-1").list_files()[0]
    assert file.revision == "2026-11-02T10:00:00.000Z"
    assert file.modified_time == datetime(2026, 11, 2, 10, tzinfo=UTC)


def test_download_exports_google_docs_and_fetches_other_files():
    service = FakeService([])
    client = GoogleDriveClient(service, "folder-1")
    now = datetime.now(UTC)

    assert client.download(DriveFile("d", "Notes", GOOGLE_DOC_MIME, "r", now)) == b"exported"
    assert client.download(DriveFile("t", "a.txt", "text/plain", "r", now)) == b"raw"
    assert service.files().exported == [("d", "text/plain")]
    assert service.files().fetched == ["t"]


def test_local_folder_revision_changes_with_content(tmp_path):
    (tmp_path / "a.txt").write_text("one")
    drive = LocalFolderDrive(tmp_path)
    first = drive.list_files()[0]
    assert drive.download(first) == b"one"

    (tmp_path / "a.txt").write_text("two")
    assert drive.list_files()[0].revision != first.revision
