"""
Shared work logic used by both sync and async paths.
"""
import hashlib
import time
import asyncio
from model import WorkInput, WorkResult


async def perform_work(input_data: WorkInput, simulated_delay_ms: int = 200) -> WorkResult:
    """
    Perform deterministic work on the input data.
    
    This is the shared business logic used by both sync and async endpoints.
    
    Args:
        input_data: The input payload to process
        simulated_delay_ms: Simulated processing time in milliseconds
    
    Returns:
        WorkResult with processed data
    """
    start_time = time.perf_counter()
    
    # Simulate processing time (non-blocking)
    await asyncio.sleep(simulated_delay_ms / 1000)
    
    text = input_data.text
    iterations = input_data.count
    
    # Deterministic processing
    processed_text = text
    for i in range(iterations):
        # Apply transformations
        processed_text = processed_text.upper() if i % 2 == 0 else processed_text.lower()
    
    # Compute hash
    input_hash = hashlib.sha256(
        f"{text}:{iterations}".encode()
    ).hexdigest()[:16]
    
    # Count words and characters
    word_count = len(text.split())
    character_count = len(text)
    
    end_time = time.perf_counter()
    processing_time_ms = (end_time - start_time) * 1000
    
    return WorkResult(
        input_hash=input_hash,
        word_count=word_count,
        character_count=character_count,
        processed_text=processed_text,
        iterations=iterations,
        processing_time_ms=round(processing_time_ms, 2)
    )
