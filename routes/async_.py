"""
Async endpoint - accepts work, returns immediately, calls back later.
"""
import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException

from model import AsyncRequest, AsyncAckResponse, RequestStatus, RequestMode
from core import perform_work
from utils import validate_callback_url, send_callback_with_retry, CallbackValidationError
from database import repository

router = APIRouter()


async def process_async_work(request_id: str, request: AsyncRequest):
    """
    Background task to process work and send callback.
    """
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
        
        # Send callback with retry
        await send_callback_with_retry(
            request_id=request_id,
            callback_url=request.callback_url,
            result=result
        )
        
    except Exception as e:
        # Update with error
        await repository.update_request_result(
            request_id=request_id,
            status=RequestStatus.FAILED,
            error=str(e)
        )
        
        # Still try to send callback with error
        await send_callback_with_retry(
            request_id=request_id,
            callback_url=request.callback_url,
            error=str(e)
        )


@router.post("/async", response_model=AsyncAckResponse)
async def async_endpoint(request: AsyncRequest, background_tasks: BackgroundTasks):
    """
    Accept work request and process asynchronously.
    
    Returns immediately with an acknowledgement. The actual work
    is performed in the background, and the result is sent to
    the provided callback_url.
    """
    # Validate callback URL (SSRF protection)
    try:
        validate_callback_url(request.callback_url)
    except CallbackValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid callback URL: {e}")
    
    request_id = str(uuid.uuid4())
    
    # Create request record
    await repository.create_request(
        request_id=request_id,
        mode=RequestMode.ASYNC,
        input_data=request,
        callback_url=request.callback_url
    )
    
    # Queue background work
    background_tasks.add_task(process_async_work, request_id, request)
    
    return AsyncAckResponse(
        request_id=request_id,
        status=RequestStatus.PENDING,
        message="Request accepted. Result will be sent to callback URL."
    )
