"""
Callback handling with URL validation and retry logic.
"""
import asyncio
import httpx
import ipaddress
from urllib.parse import urlparse
from datetime import datetime
from typing import Optional
import logging

from model import CallbackPayload, CallbackStatus, RequestStatus, WorkResult
from database import repository

logger = logging.getLogger(__name__)

# SSRF Protection - blocked IP ranges
BLOCKED_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("::1/128"),  # IPv6 localhost
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

BLOCKED_HOSTNAMES = [
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",  # Cloud metadata
]

# Retry configuration
MAX_RETRY_ATTEMPTS = 5
BASE_RETRY_DELAY_SECONDS = 1
CALLBACK_TIMEOUT_SECONDS = 10


class CallbackValidationError(Exception):
    """Raised when callback URL validation fails."""
    pass


def validate_callback_url(url: str) -> None:
    """
    Validate callback URL for security (SSRF prevention).
    
    Raises:
        CallbackValidationError: If URL is deemed unsafe
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise CallbackValidationError(f"Invalid URL format: {e}")
    
    # Check scheme
    if parsed.scheme not in ("http", "https"):
        raise CallbackValidationError(f"Invalid scheme: {parsed.scheme}. Only http/https allowed.")
    
    # Check hostname
    hostname = parsed.hostname
    if not hostname:
        raise CallbackValidationError("Missing hostname in URL")
    
    # Check against blocked hostnames
    hostname_lower = hostname.lower()
    for blocked in BLOCKED_HOSTNAMES:
        if hostname_lower == blocked or hostname_lower.endswith(f".{blocked}"):
            raise CallbackValidationError(f"Blocked hostname: {hostname}")
    
    # Check if hostname is an IP address in blocked ranges
    try:
        ip = ipaddress.ip_address(hostname)
        for blocked_range in BLOCKED_IP_RANGES:
            if ip in blocked_range:
                raise CallbackValidationError(f"Blocked IP range: {hostname}")
    except ValueError:
        # Not an IP address, continue with hostname
        pass


async def send_callback_with_retry(
    request_id: str,
    callback_url: str,
    result: Optional[WorkResult] = None,
    error: Optional[str] = None
) -> bool:
    """
    Send callback with exponential backoff retry.
    
    Returns True if successful, False if all retries exhausted.
    """
    status = RequestStatus.COMPLETED if result else RequestStatus.FAILED
    payload = CallbackPayload(
        request_id=request_id,
        status=status,
        result=result,
        error=error,
        timestamp=datetime.utcnow()
    )
    
    error_msg = ""
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=CALLBACK_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    callback_url,
                    json=payload.model_dump(mode="json"),
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code < 400:
                    # Success
                    await repository.update_callback_status(
                        request_id=request_id,
                        status=CallbackStatus.SENT,
                        attempts=attempt,
                        sent_at=datetime.utcnow()
                    )
                    logger.info(f"Callback sent successfully for request {request_id}")
                    return True
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning(f"Callback failed for {request_id}: {error_msg}")
                    
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Callback error for {request_id} (attempt {attempt}): {error_msg}")
        
        # Update status with current attempt
        await repository.update_callback_status(
            request_id=request_id,
            status=CallbackStatus.PENDING,
            attempts=attempt,
            error=error_msg
        )
        
        # Calculate delay with exponential backoff
        if attempt < MAX_RETRY_ATTEMPTS:
            delay = BASE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.info(f"Retrying callback for {request_id} in {delay}s (attempt {attempt + 1})")
            await asyncio.sleep(delay)
    
    # All retries exhausted
    await repository.update_callback_status(
        request_id=request_id,
        status=CallbackStatus.FAILED,
        attempts=MAX_RETRY_ATTEMPTS,
        error=f"Max retries ({MAX_RETRY_ATTEMPTS}) exhausted. Last error: {error_msg}"
    )
    logger.error(f"Callback permanently failed for request {request_id}")
    return False
