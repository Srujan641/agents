import threading
from datetime import UTC, datetime, timedelta

from meeting_agent.drive import DriveFile
from meeting_agent.schemas import TranscriptStatus
from meeting_agent.watcher import Watcher


class FakeDrive:
    def __init__(self, contents=None):
        self.contents = contents or {"a.txt": b"Ana: Hello"}
        self.modified = datetime.now(UTC) - timedelta(hours=1)
        self.revision = "rev-1"
        self.list_error = None

    def list_files(self):
        if self.list_error:
            raise self.list_error
        return [
            DriveFile(name, name, "text/plain", self.revision, self.modified)
            for name in self.contents
        ]

    def download(self, file):
        return self.contents[file.name]


class FakeHandler:
    def __init__(self, status=TranscriptStatus.COMPLETED):
        self.status = status
        self.seen = []
        self.error = None

    def __call__(self, transcript):
        self.seen.append(transcript)
        if self.error:
            raise self.error
        return self.status


def make_watcher(drive, storage, handler, **kwargs):
    return Watcher(drive, storage, handler, settle_seconds=60, **kwargs)


def test_new_file_runs_exactly_once(storage):
    drive, handler = FakeDrive(), FakeHandler()
    watcher = make_watcher(drive, storage, handler)

    assert watcher.poll_once().processed == 1
    assert watcher.poll_once().processed == 0
    assert [t.text for t in handler.seen] == ["Ana: Hello"]
    assert storage.get_transcript_status("a.txt", "rev-1") is TranscriptStatus.COMPLETED


def test_handler_status_is_saved(storage):
    handler = FakeHandler(TranscriptStatus.AWAITING_APPROVAL)
    make_watcher(FakeDrive(), storage, handler).poll_once()
    assert storage.get_transcript_status("a.txt", "rev-1") is TranscriptStatus.AWAITING_APPROVAL


def test_edited_file_runs_again(storage):
    drive, handler = FakeDrive(), FakeHandler()
    watcher = make_watcher(drive, storage, handler)
    watcher.poll_once()
    drive.revision = "rev-2"
    assert watcher.poll_once().processed == 1
    assert len(handler.seen) == 2


def test_recently_changed_file_waits_until_settled(storage):
    drive, handler = FakeDrive(), FakeHandler()
    watcher = make_watcher(drive, storage, handler)
    drive.modified = datetime.now(UTC)
    assert watcher.poll_once().processed == 0
    assert handler.seen == []

    drive.modified = datetime.now(UTC) - timedelta(minutes=5)
    assert watcher.poll_once().processed == 1


def test_unsupported_file_is_ignored(storage):
    handler = FakeHandler()
    make_watcher(FakeDrive({"slides.pdf": b"%PDF"}), storage, handler).poll_once()
    assert handler.seen == []
    assert storage.get_transcript_status("slides.pdf", "rev-1") is None


def test_unparseable_file_fails_without_retry(storage):
    drive, handler = FakeDrive({"a.txt": b"   "}), FakeHandler()
    watcher = make_watcher(drive, storage, handler, stale_after_seconds=0)

    assert watcher.poll_once().failed == 1
    assert watcher.poll_once().processed == 0
    assert handler.seen == []
    assert storage.get_transcript_status("a.txt", "rev-1") is TranscriptStatus.FAILED


def test_one_bad_file_does_not_block_the_others(storage):
    drive = FakeDrive({"bad.txt": b"  ", "good.txt": b"Ana: Hello"})
    result = make_watcher(drive, storage, FakeHandler()).poll_once()
    assert (result.failed, result.processed) == (1, 1)


def test_temporary_error_waits_for_stale_window_then_retries(storage):
    drive, handler = FakeDrive(), FakeHandler()
    handler.error = ConnectionError("OpenAI is down")
    watcher = make_watcher(drive, storage, handler, stale_after_seconds=3600)

    assert watcher.poll_once().will_retry == 1
    assert watcher.poll_once().processed == 0
    assert len(handler.seen) == 1

    handler.error = None
    retry = make_watcher(drive, storage, handler, stale_after_seconds=0)
    assert retry.poll_once().processed == 1
    assert storage.get_transcript_status("a.txt", "rev-1") is TranscriptStatus.COMPLETED


def test_crashed_run_is_retried(storage):
    # A crash leaves the row in processing with nothing recorded.
    storage.claim_transcript("a.txt", "rev-1", "a.txt")
    handler = FakeHandler()
    make_watcher(FakeDrive(), storage, handler, stale_after_seconds=0).poll_once()
    assert len(handler.seen) == 1


def test_gives_up_after_max_attempts_and_keeps_the_error(storage):
    drive, handler = FakeDrive(), FakeHandler()
    handler.error = ConnectionError("OpenAI is down")
    watcher = make_watcher(drive, storage, handler, stale_after_seconds=0, max_attempts=2)

    for _ in range(5):
        watcher.poll_once()

    assert len(handler.seen) == 2
    assert storage.get_transcript_status("a.txt", "rev-1") is TranscriptStatus.FAILED
    with storage._connect() as conn:
        error = conn.execute("SELECT error FROM transcripts").fetchone()["error"]
    assert error == "OpenAI is down"


def test_finished_runs_are_never_reclaimed(storage):
    handler = FakeHandler(TranscriptStatus.AWAITING_APPROVAL)
    watcher = make_watcher(FakeDrive(), storage, handler, stale_after_seconds=0)
    watcher.poll_once()
    watcher.poll_once()
    assert len(handler.seen) == 1


def test_run_survives_a_drive_outage(storage):
    class FlakyDrive(FakeDrive):
        calls = 0

        def list_files(self):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("Drive is down")
            return super().list_files()

    drive = FlakyDrive()
    stop = threading.Event()

    def stop_after_recovery(transcript):
        stop.set()
        return TranscriptStatus.COMPLETED

    thread = threading.Thread(
        target=make_watcher(drive, storage, stop_after_recovery).run, args=(0.01, stop)
    )
    thread.start()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert drive.calls >= 2
    assert storage.get_transcript_status("a.txt", "rev-1") is TranscriptStatus.COMPLETED
