from sqlalchemy import create_engine, inspect, text

from app.db_migrations import run_sqlite_migrations


def test_old_sqlite_schema_is_upgraded_idempotently(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE content_items ("
                "id VARCHAR(36) PRIMARY KEY, source_url VARCHAR(2048), source_platform VARCHAR(20), "
                "raw_text TEXT NOT NULL DEFAULT '', process_status VARCHAR(20), created_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO content_items(id, source_url, source_platform, raw_text, process_status, created_at) "
                "VALUES ('url-id', 'https://example.com/a?utm_source=x', 'WEB', 'body', 'COMPLETED', '2026-01-01'), "
                "('text-id', NULL, 'MANUAL', ' same   text ', 'COMPLETED', '2026-01-02')"
            )
        )

    run_sqlite_migrations(engine)
    run_sqlite_migrations(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("content_items")}
    assert {"input_type", "normalized_url", "content_hash", "clean_content", "fetch_status", "ai_status", "key_concepts", "related_entities", "knowledge_relations", "archive_markdown", "source_type", "archived_at"} <= columns
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id,input_type,normalized_url,content_hash,clean_content,fetch_status,ai_status "
                "FROM content_items ORDER BY id"
            )
        ).mappings().all()
        indexes = {row[1] for row in connection.execute(text("PRAGMA index_list('content_items')"))}

    by_id = {row["id"]: row for row in rows}
    assert by_id["url-id"]["normalized_url"] == "https://example.com/a"
    assert by_id["url-id"]["fetch_status"] == "success"
    assert by_id["text-id"]["input_type"] == "text"
    assert len(by_id["text-id"]["content_hash"]) == 64
    assert by_id["text-id"]["clean_content"] == " same   text "
    assert "ix_content_items_normalized_url" in indexes
    assert "ix_content_items_content_hash" in indexes
    engine.dispose()
