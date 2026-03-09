
import json
import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "db" / "telemetry.db"
CHUNK_SIZE = 1000  # flush to DB every N events


# ─── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    timestamp       INTEGER NOT NULL,
    event_timestamp TEXT,
    event_name      TEXT NOT NULL,
    -- session / user
    organization_id TEXT,
    session_id      TEXT,
    user_id         TEXT,
    user_email      TEXT,
    user_practice   TEXT,
    user_profile    TEXT,
    terminal_type   TEXT,
    -- api_request fields
    model           TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cache_creation_tokens INTEGER,
    cache_read_tokens     INTEGER,
    cost_usd        REAL,
    duration_ms     INTEGER,
    -- user_prompt fields
    prompt_length   INTEGER,
    -- tool_decision / tool_result fields
    tool_name       TEXT,
    decision        TEXT,
    decision_source TEXT,
    success         TEXT,
    -- host info
    host_name       TEXT,
    os_type         TEXT,
    service_version TEXT,
    -- raw (for debugging)
    raw_message     TEXT,
    ingested_at     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_event_name   ON events(event_name);
CREATE INDEX IF NOT EXISTS idx_session_id   ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_user_id      ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_user_practice ON events(user_practice);
CREATE INDEX IF NOT EXISTS idx_model        ON events(model);
CREATE INDEX IF NOT EXISTS idx_timestamp    ON events(timestamp);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    logger.info("Database schema initialized.")


# ─── Parsing ──────────────────────────────────────────────────────────────────

def parse_log_event(raw_event: dict) -> dict | None:
    """
    Parse a single logEvent entry from the JSONL file.
    Returns a flat dict ready for DB insertion, or None on parse error.
    """
    try:
        msg = json.loads(raw_event["message"])
        attrs = msg.get("attributes", {})
        resource = msg.get("resource", {})

        event_name = attrs.get("event.name", msg.get("body", "unknown"))
        # Normalize body-style names like "claude_code.api_request" -> "api_request"
        if "." in event_name:
            event_name = event_name.split(".")[-1]

        return {
            "id": raw_event["id"],
            "timestamp": raw_event["timestamp"],
            "event_timestamp": attrs.get("event.timestamp"),
            "event_name": event_name,
            # session / user
            "organization_id": attrs.get("organization.id"),
            "session_id": attrs.get("session.id"),
            "user_id": attrs.get("user.id"),
            "user_email": attrs.get("user.email"),
            "user_practice": resource.get("user.practice"),
            "user_profile": resource.get("user.profile"),
            "terminal_type": attrs.get("terminal.type"),
            # api_request
            "model": attrs.get("model"),
            "input_tokens": _int(attrs.get("input_tokens")),
            "output_tokens": _int(attrs.get("output_tokens")),
            "cache_creation_tokens": _int(attrs.get("cache_creation_tokens")),
            "cache_read_tokens": _int(attrs.get("cache_read_tokens")),
            "cost_usd": _float(attrs.get("cost_usd")),
            "duration_ms": _int(attrs.get("duration_ms")),
            # user_prompt
            "prompt_length": _int(attrs.get("prompt_length")),
            # tool events
            "tool_name": attrs.get("tool_name"),
            "decision": attrs.get("decision"),
            "decision_source": attrs.get("source") or attrs.get("decision_source"),
            "success": attrs.get("success"),
            # host
            "host_name": resource.get("host.name"),
            "os_type": resource.get("os.type"),
            "service_version": resource.get("service.version"),
            # raw
            "raw_message": raw_event["message"],
        }
    except Exception as e:
        logger.warning(f"Failed to parse event {raw_event.get('id', '?')}: {e}")
        return None


def _int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


# ─── Ingestion ────────────────────────────────────────────────────────────────

INSERT_SQL = """
INSERT OR IGNORE INTO events (
    id, timestamp, event_timestamp, event_name,
    organization_id, session_id, user_id, user_email, user_practice, user_profile, terminal_type,
    model, input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens, cost_usd, duration_ms,
    prompt_length, tool_name, decision, decision_source, success,
    host_name, os_type, service_version, raw_message
) VALUES (
    :id, :timestamp, :event_timestamp, :event_name,
    :organization_id, :session_id, :user_id, :user_email, :user_practice, :user_profile, :terminal_type,
    :model, :input_tokens, :output_tokens, :cache_creation_tokens, :cache_read_tokens, :cost_usd, :duration_ms,
    :prompt_length, :tool_name, :decision, :decision_source, :success,
    :host_name, :os_type, :service_version, :raw_message
)
"""


def ingest_jsonl(jsonl_path: str, db_path: str = None, limit: int = None) -> dict:
    """
    Stream-parse a (large) JSONL file and insert events into SQLite.
    Uses chunked commits to keep memory usage low.

    Args:
        jsonl_path: Path to the .jsonl file
        db_path:    Path for the SQLite DB (defaults to DB_PATH)
        limit:      Max number of lines to process (useful for testing)

    Returns:
        Summary dict with counts.
    """
    db_path = Path(db_path or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")   # faster writes
    conn.execute("PRAGMA synchronous=NORMAL")
    init_db(conn)

    total_lines = 0
    total_events = 0
    skipped = 0
    buffer = []

    logger.info(f"Starting ingestion: {jsonl_path}")

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if limit and total_lines >= limit:
                break
            total_lines += 1
            line = line.strip()
            if not line:
                continue

            try:
                outer = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"Line {total_lines}: invalid JSON – {e}")
                skipped += 1
                continue

            # Validate expected structure
            if outer.get("messageType") != "DATA_MESSAGE":
                continue

            log_events = outer.get("logEvents", [])
            for raw_event in log_events:
                parsed = parse_log_event(raw_event)
                if parsed:
                    buffer.append(parsed)
                    total_events += 1
                else:
                    skipped += 1

            # Flush buffer to DB
            if len(buffer) >= CHUNK_SIZE:
                conn.executemany(INSERT_SQL, buffer)
                conn.commit()
                buffer.clear()
                logger.info(f"  Processed {total_lines} lines / {total_events} events...")

    # Final flush
    if buffer:
        conn.executemany(INSERT_SQL, buffer)
        conn.commit()

    conn.close()

    summary = {
        "lines_processed": total_lines,
        "events_inserted": total_events,
        "events_skipped": skipped,
        "db_path": str(db_path),
    }
    logger.info(f"Ingestion complete: {summary}")
    return summary


# ─── CSV ingestion (for the second dataset) ───────────────────────────────────

def ingest_csv(csv_path: str, db_path: str = None) -> dict:
    """
    Ingest employees.csv into user_metadata table.
    Schema: email, full_name, practice, level, location
    Join key to events table: user_email == email
    """
    import csv

    db_path = Path(db_path or DB_PATH)
    conn = sqlite3.connect(db_path)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_metadata (
            email      TEXT PRIMARY KEY,
            full_name  TEXT,
            practice   TEXT,
            level      TEXT,
            location   TEXT
        )
    """)
    conn.commit()

    rows_inserted = 0
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            conn.execute("""
                INSERT OR REPLACE INTO user_metadata (email, full_name, practice, level, location)
                VALUES (?, ?, ?, ?, ?)
            """, (
                row.get("email", "").strip(),
                row.get("full_name", "").strip(),
                row.get("practice", "").strip(),
                row.get("level", "").strip(),
                row.get("location", "").strip(),
            ))
            rows_inserted += 1

    conn.commit()
    conn.close()
    logger.info(f"CSV ingestion complete: {rows_inserted} rows inserted.")
    return {"rows_inserted": rows_inserted}


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest Claude Code telemetry data")
    parser.add_argument("--jsonl", required=True, help="Path to .jsonl file")
    parser.add_argument("--csv",   help="Path to user metadata .csv file (optional)")
    parser.add_argument("--db",    help="Path to SQLite DB (default: db/telemetry.db)")
    parser.add_argument("--limit", type=int, help="Limit number of lines (for testing)")
    args = parser.parse_args()

    result = ingest_jsonl(args.jsonl, db_path=args.db, limit=args.limit)
    print(json.dumps(result, indent=2))

    if args.csv:
        csv_result = ingest_csv(args.csv, db_path=args.db)
        print(json.dumps(csv_result, indent=2))
