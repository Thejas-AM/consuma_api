"""
Sync endpoint - performs work inline and returns result.
"""
import uuid
from fastapi import APIRouter, HTTPException

from model import SyncRequest, SyncResponse, RequestStatus, RequestMode
from core import perform_work
from database import repository

router = APIRouter()


@router.post("/sync", response_model=SyncResponse)
async def sync_endpoint(request: SyncRequest):
    """
    Perform work synchronously and return result inline.
    
    The work is executed immediately, and the result is returned
    in the same HTTP response.
    """
    request_id = str(uuid.uuid4())
    
    # Create request record
    await repository.create_request(
        request_id=request_id,
        mode=RequestMode.SYNC,
        input_data=request
    )
    
    try:
        # Update to processing
        await repository.update_request_result(
            request_id=request_id,
            status=RequestStatus.PROCESSING
        )
        
        # Perform the actual work
        result = await perform_work(request)
        
        # Update with result
        await repository.update_request_result(
            request_id=request_id,
            status=RequestStatus.COMPLETED,
            result=result
        )
        
        return SyncResponse(
            request_id=request_id,
            status=RequestStatus.COMPLETED,
            result=result
        )
        
    except Exception as e:
        # Update with error
        await repository.update_request_result(
            request_id=request_id,
            status=RequestStatus.FAILED,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Work processing failed: {e}")
