"""
SQLite database connection and schema management.
"""
import aiosqlite
from pathlib import Path
from contextlib import asynccontextmanager

DATABASE_PATH = Path(__file__).parent.parent / "data" / "requests.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK(mode IN ('sync', 'async')),
    input_data TEXT NOT NULL,
    output_data TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    callback_url TEXT,
    callback_status TEXT CHECK(callback_status IN ('pending', 'sent', 'failed') OR callback_status IS NULL),
    callback_attempts INTEGER DEFAULT 0,
    callback_last_error TEXT,
    callback_sent_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_requests_mode ON requests(mode);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_created_at ON requests(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_requests_callback_status ON requests(callback_status);
"""


async def init_database():
    """Initialize database and create tables."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


@asynccontextmanager
async def get_db():
    """Get database connection context manager."""
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()
