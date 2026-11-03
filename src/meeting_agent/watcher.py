import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from meeting_agent.drive import DriveClient, DriveFile
from meeting_agent.parsers import TranscriptParseError, is_supported, parse_transcript
from meeting_agent.schemas import Transcript, TranscriptStatus
from meeting_agent.storage import Storage

logger = logging.getLogger(__name__)

# Returns the status the run ended in, such as AWAITING_APPROVAL.
TranscriptHandler = Callable[[Transcript], TranscriptStatus]


@dataclass
class PollResult:
    processed: int = 0
    failed: int = 0
    will_retry: int = 0


class Watcher:
    def __init__(
        self,
        drive: DriveClient,
        storage: Storage,
        handler: TranscriptHandler,
        settle_seconds: int = 60,
        stale_after_seconds: int = 1800,
        max_attempts: int = 3,
    ) -> None:
        self._drive = drive
        self._storage = storage
        self._handler = handler
        self._settle = timedelta(seconds=settle_seconds)
        self._stale_after_seconds = stale_after_seconds
        self._max_attempts = max_attempts

    def poll_once(self) -> PollResult:
        result = PollResult()
        files = self._drive.list_files()
        retries = self._storage.reclaim_stale_transcripts(
            self._stale_after_seconds, self._max_attempts
        )
        settled_before = datetime.now(UTC) - self._settle
        for file in files:
            if not is_supported(file.name, file.mime_type) or file.modified_time > settled_before:
                continue
            if (file.id, file.revision) in retries or self._storage.claim_transcript(
                file.id, file.revision, file.name
            ):
                self._process(file, result)
        return result

    def run(self, interval_seconds: int, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        while not stop.is_set():
            try:
                self.poll_once()
            except Exception:  # a Drive outage shouldn't stop the watcher
                logger.exception("Poll failed, trying again in %ss", interval_seconds)
            stop.wait(interval_seconds)

    def _process(self, file: DriveFile, result: PollResult) -> None:
        logger.info("Processing %s (revision %s)", file.name, file.revision)
        try:
            text = parse_transcript(file.name, file.mime_type, self._drive.download(file))
            status = self._handler(
                Transcript(file_id=file.id, revision=file.revision, name=file.name, text=text)
            )
        except TranscriptParseError as exc:
            logger.error("Cannot parse %s: %s", file.name, exc)
            self._storage.set_transcript_status(
                file.id, file.revision, TranscriptStatus.FAILED, error=str(exc)
            )
            result.failed += 1
        except Exception as exc:
            logger.exception("Error processing %s, it will be retried", file.name)
            self._storage.record_transcript_error(file.id, file.revision, str(exc))
            result.will_retry += 1
        else:
            self._storage.set_transcript_status(file.id, file.revision, status)
            result.processed += 1
