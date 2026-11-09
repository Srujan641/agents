CREATE TABLE IF NOT EXISTS transcripts (
    file_id     TEXT NOT NULL,
    revision    TEXT NOT NULL,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 1,
    error       TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (file_id, revision)
);

CREATE TABLE IF NOT EXISTS ticket_drafts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id     TEXT NOT NULL,
    revision    TEXT NOT NULL,
    payload     TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id, revision) REFERENCES transcripts (file_id, revision)
);

CREATE TABLE IF NOT EXISTS deliveries (
    idempotency_key TEXT PRIMARY KEY,
    channel         TEXT NOT NULL,
    external_id     TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
