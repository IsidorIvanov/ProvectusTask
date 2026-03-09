"""
Real-time Streaming Simulator
──────────────────────────────
Replays telemetry events from the JSONL file into the SQLite database
with realistic timing, simulating a live data stream.

This demonstrates how the platform could handle live data ingestion.

Usage:
    python src/stream_simulator.py --jsonl DataEntry/telemetry_logs.jsonl --speed 50

The dashboard auto-refreshes when new data arrives (via Streamlit's rerun).
"""

from __future__ import annotations

import json
import sqlite3
import logging
import time
import random
from pathlib import Path

from ingest import parse_log_event, init_db, INSERT_SQL, DB_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def stream_replay(
    jsonl_path: str,
    db_path: str = None,
    speed: int = 10,
    batch_size: int = 5,
    max_events: int = 500,
) -> None:
    """
    Replay events from the JSONL file one batch at a time, simulating
    real-time ingestion.

    Args:
        jsonl_path:  Path to .jsonl file
        db_path:     SQLite DB path
        speed:       Events per second (approximate)
        batch_size:  Events per insert batch
        max_events:  Stop after N events (for demo purposes)
    """
    db_path = Path(db_path or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    init_db(conn)

    delay = batch_size / max(speed, 1)
    total = 0
    buffer = []

    logger.info(f"🔴 LIVE STREAM started — {speed} events/sec from {jsonl_path}")
    logger.info(f"   Target: {max_events} events, batch size: {batch_size}")

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if total >= max_events:
                break

            line = line.strip()
            if not line:
                continue

            try:
                outer = json.loads(line)
            except json.JSONDecodeError:
                continue

            if outer.get("messageType") != "DATA_MESSAGE":
                continue

            for raw_event in outer.get("logEvents", []):
                if total >= max_events:
                    break

                parsed = parse_log_event(raw_event)
                if not parsed:
                    continue

                # Give a fresh unique ID to avoid INSERT OR IGNORE skipping
                parsed["id"] = f"stream_{total}_{random.randint(1000, 9999)}"
                buffer.append(parsed)
                total += 1

                if len(buffer) >= batch_size:
                    conn.executemany(INSERT_SQL, buffer)
                    conn.commit()
                    logger.info(
                        f"  📥 Ingested batch — {total} events total "
                        f"(latest: {parsed['event_name']})"
                    )
                    buffer.clear()
                    time.sleep(delay)

    # Flush remaining
    if buffer:
        conn.executemany(INSERT_SQL, buffer)
        conn.commit()

    conn.close()
    logger.info(f"✅ Stream complete — {total} events ingested into {db_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Simulate real-time telemetry streaming")
    parser.add_argument("--jsonl", required=True, help="Path to .jsonl file")
    parser.add_argument("--db", help="SQLite DB path (default: db/telemetry.db)")
    parser.add_argument("--speed", type=int, default=10, help="Events per second (default: 10)")
    parser.add_argument("--batch", type=int, default=5, help="Batch size (default: 5)")
    parser.add_argument("--max", type=int, default=500, help="Max events to stream (default: 500)")
    args = parser.parse_args()

    stream_replay(
        jsonl_path=args.jsonl,
        db_path=args.db,
        speed=args.speed,
        batch_size=args.batch,
        max_events=args.max,
    )

