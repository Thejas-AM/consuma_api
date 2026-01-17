"""
Pydantic models for request/response schemas.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class RequestMode(str, Enum):
    SYNC = "sync"
    ASYNC = "async"


class RequestStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CallbackStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


# ============ Input Schemas ============

class WorkInput(BaseModel):
    """Input payload for work processing."""
    text: str = Field(..., min_length=1, max_length=10000, description="Text to process")
    count: int = Field(default=1, ge=1, le=100, description="Processing iterations")


class SyncRequest(WorkInput):
    """Request body for /sync endpoint."""
    pass


class AsyncRequest(WorkInput):
    """Request body for /async endpoint."""
    callback_url: str = Field(..., description="URL to send the result to")


# ============ Output Schemas ============

class WorkResult(BaseModel):
    """Result of work processing."""
    input_hash: str
    word_count: int
    character_count: int
    processed_text: str
    iterations: int
    processing_time_ms: float


class SyncResponse(BaseModel):
    """Response for /sync endpoint."""
    request_id: str
    status: RequestStatus
    result: WorkResult


class AsyncAckResponse(BaseModel):
    """Acknowledgement response for /async endpoint."""
    request_id: str
    status: RequestStatus
    message: str = "Request accepted. Result will be sent to callback URL."


class CallbackPayload(BaseModel):
    """Payload sent to callback URL."""
    request_id: str
    status: RequestStatus
    result: Optional[WorkResult] = None
    error: Optional[str] = None
    timestamp: datetime


# ============ Database Record ============

class RequestRecord(BaseModel):
    """Full request record from database."""
    id: str
    mode: RequestMode
    input_data: dict
    output_data: Optional[dict] = None
    status: RequestStatus
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    callback_url: Optional[str] = None
    callback_status: Optional[CallbackStatus] = None
    callback_attempts: int = 0
    callback_last_error: Optional[str] = None
    callback_sent_at: Optional[datetime] = None


class RequestSummary(BaseModel):
    """Summary of a request for listing."""
    id: str
    mode: RequestMode
    status: RequestStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    callback_status: Optional[CallbackStatus] = None


class RequestListResponse(BaseModel):
    """Response for requests listing."""
    requests: list[RequestSummary]
    total: int
    limit: int
    offset: int
