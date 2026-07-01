from __future__ import annotations

import logging

from sqlalchemy import Engine, inspect, text

from app.utils.content_identity import content_hash, normalize_url


logger = logging.getLogger(__name__)

SQLITE_COLUMNS = {
    "input_type": "VARCHAR(4) NOT NULL DEFAULT 'url'",
    "normalized_url": "VARCHAR(2048)",
    "content_hash": "VARCHAR(64)",
    "clean_content": "TEXT NOT NULL DEFAULT ''",
    "key_concepts": "TEXT NOT NULL DEFAULT '[]'",
    "related_entities": "TEXT NOT NULL DEFAULT '{}'",
    "knowledge_relations": "TEXT NOT NULL DEFAULT '[]'",
    "archive_markdown": "TEXT NOT NULL DEFAULT ''",
    "source_type": "VARCHAR(50) NOT NULL DEFAULT ''",
    "archived_at": "DATETIME",
    "fetch_status": "VARCHAR(7) NOT NULL DEFAULT 'skipped'",
    "ai_status": "VARCHAR(7) NOT NULL DEFAULT 'skipped'",
}


def run_sqlite_migrations(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        logger.info("Skipping SQLite migrations for dialect %s", engine.dialect.name)
        return

    try:
        with engine.begin() as connection:
            tables = inspect(connection).get_table_names()
            if "content_items" not in tables:
                logger.info("content_items does not exist; create_all will create the current schema")
                return

            existing = {column["name"] for column in inspect(connection).get_columns("content_items")}
            for name, definition in SQLITE_COLUMNS.items():
                if name in existing:
                    continue
                connection.execute(text(f'ALTER TABLE content_items ADD COLUMN "{name}" {definition}'))
                logger.info("Added SQLite column content_items.%s", name)

            _backfill_content_identity(connection)
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_content_items_normalized_url "
                    "ON content_items(normalized_url) WHERE normalized_url IS NOT NULL"
                )
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_content_items_content_hash "
                    "ON content_items(content_hash) WHERE content_hash IS NOT NULL"
                )
            )
    except Exception:
        logger.exception("SQLite migration failed")
        raise


def _backfill_content_identity(connection) -> None:
    # Recompute URL identities so new canonicalization rules apply to historical rows.
    # NULL first avoids transient unique-index collisions; the oldest row wins.
    connection.execute(text("UPDATE content_items SET normalized_url=NULL WHERE source_url IS NOT NULL"))
    rows = connection.execute(
        text(
            "SELECT id, source_url, source_platform, raw_text, process_status, "
            "normalized_url, content_hash FROM content_items ORDER BY created_at, id"
        )
    ).mappings()
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    for row in rows:
        is_url = bool(row["source_url"])
        normalized = row["normalized_url"]
        digest = row["content_hash"]
        if is_url and not normalized:
            try:
                candidate = normalize_url(row["source_url"])
                if candidate not in seen_urls:
                    normalized = candidate
                else:
                    logger.warning("Duplicate normalized URL retained without identity for item %s", row["id"])
            except ValueError:
                logger.warning("Could not normalize historical URL for item %s", row["id"])
        if not is_url and not digest and row["raw_text"]:
            candidate = content_hash(row["raw_text"])
            if candidate not in seen_hashes:
                digest = candidate
            else:
                logger.warning("Duplicate text retained without identity for item %s", row["id"])

        if normalized:
            seen_urls.add(normalized)
        if digest:
            seen_hashes.add(digest)
        process_status = str(row["process_status"] or "").lower()
        completed = process_status in {"completed", "processstatus.completed"}
        failed = process_status in {"failed", "processstatus.failed"}
        fetch_status = "skipped" if not is_url else ("success" if completed else "failed" if failed else "skipped")
        ai_status = "success" if completed else "failed" if failed else "skipped"
        connection.execute(
            text(
                "UPDATE content_items SET input_type=:input_type, normalized_url=:normalized_url, "
                "content_hash=:content_hash, clean_content=CASE WHEN clean_content='' THEN raw_text ELSE clean_content END, "
                "fetch_status=:fetch_status, ai_status=:ai_status WHERE id=:id"
            ),
            {
                "id": row["id"],
                "input_type": "url" if is_url else "text",
                "normalized_url": normalized,
                "content_hash": digest,
                "fetch_status": fetch_status,
                "ai_status": ai_status,
            },
        )
