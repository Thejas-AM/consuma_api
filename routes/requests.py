"""
Request listing and detail endpoints.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from model import RequestMode, RequestRecord, RequestListResponse
from database import repository

router = APIRouter()


@router.get("/requests", response_model=RequestListResponse)
async def list_requests(
    mode: Optional[RequestMode] = Query(None, description="Filter by request mode"),
    limit: int = Query(50, ge=1, le=100, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """
    List recent requests with optional filtering.
    """
    summaries, total = await repository.list_requests(
        mode=mode,
        limit=limit,
        offset=offset
    )
    
    return RequestListResponse(
        requests=summaries,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/requests/{request_id}", response_model=RequestRecord)
async def get_request(request_id: str):
    """
    Get detailed information about a specific request.
    """
    record = await repository.get_request(request_id)
    
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")
    
    return record
