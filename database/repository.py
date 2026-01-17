import json
from datetime import datetime
from typing import Optional
from database.database import get_db
from model import (
    RequestMode, RequestStatus, CallbackStatus,
    RequestRecord, RequestSummary, WorkInput, WorkResult
)


async def create_request(
    request_id: str,
    mode: RequestMode,
    input_data: WorkInput,
    callback_url: Optional[str] = None
) -> RequestRecord:
    """Create a new request record."""
    async with get_db() as db:
        now = datetime.utcnow()
        callback_status = CallbackStatus.PENDING if callback_url else None
        
        await db.execute(
            """
            INSERT INTO requests (id, mode, input_data, status, created_at, callback_url, callback_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                mode.value,
                json.dumps(input_data.model_dump()),
                RequestStatus.PENDING.value,
                now.isoformat(),
                callback_url,
                callback_status.value if callback_status else None
            )
        )
        await db.commit()
        
        return RequestRecord(
            id=request_id,
            mode=mode,
            input_data=input_data.model_dump(),
            status=RequestStatus.PENDING,
            created_at=now,
            callback_url=callback_url,
            callback_status=callback_status
        )


async def update_request_result(
    request_id: str,
    status: RequestStatus,
    result: Optional[WorkResult] = None,
    error: Optional[str] = None
) -> None:
    """Update request with result or error."""
    async with get_db() as db:
        now = datetime.utcnow()
        await db.execute(
            """
            UPDATE requests 
            SET status = ?, output_data = ?, error = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                status.value,
                json.dumps(result.model_dump()) if result else None,
                error,
                now.isoformat(),
                request_id
            )
        )
        await db.commit()


async def update_callback_status(
    request_id: str,
    status: CallbackStatus,
    attempts: int,
    error: Optional[str] = None,
    sent_at: Optional[datetime] = None
) -> None:
    """Update callback delivery status."""
    async with get_db() as db:
        await db.execute(
            """
            UPDATE requests 
            SET callback_status = ?, callback_attempts = ?, 
                callback_last_error = ?, callback_sent_at = ?
            WHERE id = ?
            """,
            (
                status.value,
                attempts,
                error,
                sent_at.isoformat() if sent_at else None,
                request_id
            )
        )
        await db.commit()


async def get_request(request_id: str) -> Optional[RequestRecord]:
    """Get a request by ID."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM requests WHERE id = ?",
            (request_id,)
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        return _row_to_record(row)


async def list_requests(
    mode: Optional[RequestMode] = None,
    limit: int = 50,
    offset: int = 0
) -> tuple[list[RequestSummary], int]:
    """List requests with optional mode filter."""
    async with get_db() as db:
        # Count total
        if mode:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM requests WHERE mode = ?",
                (mode.value,)
            )
        else:
            cursor = await db.execute("SELECT COUNT(*) FROM requests")
        
        total = (await cursor.fetchone())[0]
        
        # Fetch records
        if mode:
            cursor = await db.execute(
                """
                SELECT id, mode, status, created_at, completed_at, callback_status
                FROM requests 
                WHERE mode = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (mode.value, limit, offset)
            )
        else:
            cursor = await db.execute(
                """
                SELECT id, mode, status, created_at, completed_at, callback_status
                FROM requests 
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            )
        
        rows = await cursor.fetchall()
        
        summaries = [
            RequestSummary(
                id=row["id"],
                mode=RequestMode(row["mode"]),
                status=RequestStatus(row["status"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
                callback_status=CallbackStatus(row["callback_status"]) if row["callback_status"] else None
            )
            for row in rows
        ]
        
        return summaries, total


def _row_to_record(row) -> RequestRecord:
    """Convert database row to RequestRecord."""
    return RequestRecord(
        id=row["id"],
        mode=RequestMode(row["mode"]),
        input_data=json.loads(row["input_data"]),
        output_data=json.loads(row["output_data"]) if row["output_data"] else None,
        status=RequestStatus(row["status"]),
        error=row["error"],
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        callback_url=row["callback_url"],
        callback_status=CallbackStatus(row["callback_status"]) if row["callback_status"] else None,
        callback_attempts=row["callback_attempts"],
        callback_last_error=row["callback_last_error"],
        callback_sent_at=datetime.fromisoformat(row["callback_sent_at"]) if row["callback_sent_at"] else None
    )
