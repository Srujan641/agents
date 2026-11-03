import argparse
import logging
from pathlib import Path

from meeting_agent.config import Settings
from meeting_agent.drive import DriveClient, GoogleDriveClient, LocalFolderDrive
from meeting_agent.schemas import Transcript, TranscriptStatus
from meeting_agent.storage import Storage
from meeting_agent.watcher import Watcher

logger = logging.getLogger(__name__)


def _log_only_handler(transcript: Transcript) -> TranscriptStatus:
    # Placeholder until the LangGraph workflow arrives in Stage 3.
    logger.info(
        "Read %s: %d lines, %d words",
        transcript.name,
        len(transcript.text.splitlines()),
        len(transcript.text.split()),
    )
    return TranscriptStatus.COMPLETED


def _build_drive(settings: Settings, local_folder: Path | None) -> DriveClient:
    if local_folder is not None:
        return LocalFolderDrive(local_folder)
    if not settings.drive_folder_id:
        raise SystemExit("Set DRIVE_FOLDER_ID in .env, or pass --local-folder.")
    if not settings.google_service_account_file.exists():
        raise SystemExit(f"Service account key not found: {settings.google_service_account_file}")
    return GoogleDriveClient.from_service_account(
        settings.google_service_account_file, settings.drive_folder_id
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="meeting-agent")
    commands = parser.add_subparsers(dest="command", required=True)
    watch = commands.add_parser("watch", help="Process new transcripts from the Drive folder")
    watch.add_argument("--once", action="store_true", help="Check once, then exit")
    watch.add_argument("--local-folder", type=Path, help="Read a local folder instead of Drive")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # The Google client logs every request at INFO.
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)

    settings = Settings()
    watcher = Watcher(
        _build_drive(settings, args.local_folder),
        Storage(settings.database_path),
        _log_only_handler,
        settle_seconds=settings.settle_seconds,
        stale_after_seconds=settings.stale_after_seconds,
        max_attempts=settings.max_attempts,
    )
    if args.once:
        logger.info("%s", watcher.poll_once())
    else:
        watcher.run(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
