import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from meeting_agent.schemas import DraftStatus, TicketDraft, TranscriptStatus

_SCHEMA_FILE = Path(__file__).resolve().parents[2] / "database" / "schema.sql"


@dataclass(frozen=True)
class StoredTranscript:
    file_id: str
    revision: str
    name: str


@dataclass(frozen=True)
class StoredDraft:
    id: int
    file_id: str
    revision: str
    status: DraftStatus
    ticket: TicketDraft


class Storage:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA_FILE.read_text(encoding="utf-8"))

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def claim_transcript(self, file_id: str, revision: str, name: str) -> bool:
        """Return True only for the first caller, so each file revision runs exactly once."""
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO transcripts (file_id, revision, name, status) "
                "VALUES (?, ?, ?, ?)",
                (file_id, revision, name, TranscriptStatus.PROCESSING),
            )
            return cursor.rowcount == 1

    def reclaim_stale_transcripts(
        self, stale_after_seconds: int, max_attempts: int
    ) -> set[tuple[str, str]]:
        """Find runs that crashed or hit a temporary error, and return those to try again.

        Runs that have used all their attempts are marked failed instead.
        """
        cutoff = f"-{stale_after_seconds} seconds"
        with self._connect() as conn:
            conn.execute(
                "UPDATE transcripts SET status = ?, "
                "error = COALESCE(error, 'Gave up: run never finished'), "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE status = ? AND updated_at <= datetime('now', ?) AND attempts >= ?",
                (TranscriptStatus.FAILED, TranscriptStatus.PROCESSING, cutoff, max_attempts),
            )
            rows = conn.execute(
                "UPDATE transcripts SET attempts = attempts + 1, "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE status = ? AND updated_at <= datetime('now', ?) "
                "RETURNING file_id, revision",
                (TranscriptStatus.PROCESSING, cutoff),
            ).fetchall()
        return {(row["file_id"], row["revision"]) for row in rows}

    def record_transcript_error(self, file_id: str, revision: str, error: str) -> None:
        """Note a temporary error. The run stays in processing until it is retried."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE transcripts SET error = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE file_id = ? AND revision = ?",
                (error, file_id, revision),
            )

    def set_transcript_status(
        self, file_id: str, revision: str, status: TranscriptStatus, error: str | None = None
    ) -> None:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE transcripts SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE file_id = ? AND revision = ?",
                (status, error, file_id, revision),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Unknown transcript: {file_id} revision {revision}")

    def list_transcripts(self, status: TranscriptStatus) -> list[StoredTranscript]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT file_id, revision, name FROM transcripts WHERE status = ? "
                "ORDER BY created_at, file_id",
                (status,),
            ).fetchall()
        return [StoredTranscript(row["file_id"], row["revision"], row["name"]) for row in rows]

    def get_transcript_status(self, file_id: str, revision: str) -> TranscriptStatus | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM transcripts WHERE file_id = ? AND revision = ?",
                (file_id, revision),
            ).fetchone()
        return TranscriptStatus(row["status"]) if row else None

    def add_draft(self, file_id: str, revision: str, ticket: TicketDraft) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO ticket_drafts (file_id, revision, payload, status) "
                "VALUES (?, ?, ?, ?)",
                (file_id, revision, ticket.model_dump_json(), DraftStatus.PENDING),
            )
            return cursor.lastrowid

    def replace_drafts(self, file_id: str, revision: str, tickets: list[TicketDraft]) -> None:
        """Save a run's drafts in one step, so a retried run can't leave duplicates."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM ticket_drafts WHERE file_id = ? AND revision = ? AND status = ?",
                (file_id, revision, DraftStatus.PENDING),
            )
            conn.executemany(
                "INSERT INTO ticket_drafts (file_id, revision, payload, status) "
                "VALUES (?, ?, ?, ?)",
                [
                    (file_id, revision, ticket.model_dump_json(), DraftStatus.PENDING)
                    for ticket in tickets
                ],
            )

    def list_drafts(
        self,
        status: DraftStatus | None = None,
        file_id: str | None = None,
        revision: str | None = None,
    ) -> list[StoredDraft]:
        filters = {"status": status, "file_id": file_id, "revision": revision}
        used = {column: value for column, value in filters.items() if value is not None}
        where = " AND ".join(f"{column} = ?" for column in used)
        query = "SELECT * FROM ticket_drafts" + (f" WHERE {where}" if where else "")
        with self._connect() as conn:
            rows = conn.execute(query + " ORDER BY id", tuple(used.values())).fetchall()
        return [
            StoredDraft(
                id=row["id"],
                file_id=row["file_id"],
                revision=row["revision"],
                status=DraftStatus(row["status"]),
                ticket=TicketDraft.model_validate_json(row["payload"]),
            )
            for row in rows
        ]

    def update_draft(
        self, draft_id: int, status: DraftStatus, ticket: TicketDraft | None = None
    ) -> None:
        """Change a draft's status, saving the reviewer's edits when a ticket is given."""
        with self._connect() as conn:
            if ticket is None:
                cursor = conn.execute(
                    "UPDATE ticket_drafts SET status = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = ?",
                    (status, draft_id),
                )
            else:
                cursor = conn.execute(
                    "UPDATE ticket_drafts SET status = ?, payload = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (status, ticket.model_dump_json(), draft_id),
                )
            if cursor.rowcount == 0:
                raise KeyError(f"Unknown draft: {draft_id}")

    def get_delivery(self, idempotency_key: str) -> str | None:
        """Return the external ID if this message was already sent, so retries can skip it."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT external_id FROM deliveries WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return row["external_id"] if row else None

    def record_delivery(self, idempotency_key: str, channel: str, external_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO deliveries (idempotency_key, channel, external_id) VALUES (?, ?, ?)",
                (idempotency_key, channel, external_id),
            )
