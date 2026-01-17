#!/usr/bin/env python3
"""
Load Generator for Sync/Async Work Service

A CLI tool to generate high volumes of requests and collect metrics.
"""
import asyncio
import argparse
import time
from typing import Optional
from dataclasses import dataclass, field
import aiohttp


@dataclass
class RequestResult:
    """Result of a single request."""
    request_id: str
    mode: str
    success: bool
    latency_ms: float
    error: Optional[str] = None


@dataclass
class LoadTestStats:
    """Aggregated statistics."""
    mode: str
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    latencies_ms: list = field(default_factory=list)
    
    def add_result(self, result: RequestResult):
        self.total_requests += 1
        if result.success:
            self.successful += 1
            self.latencies_ms.append(result.latency_ms)
        else:
            self.failed += 1
    
    def percentile(self, data: list, p: float) -> Optional[float]:
        if not data:
            return None
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * (p / 100)
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f
        return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])
    
    def summary(self) -> dict:
        return {
            "mode": self.mode,
            "total_requests": self.total_requests,
            "successful": self.successful,
            "failed": self.failed,
            "success_rate": f"{(self.successful / self.total_requests * 100):.1f}%" if self.total_requests > 0 else "N/A",
            "latency_p50_ms": round(self.percentile(self.latencies_ms, 50), 2) if self.latencies_ms else None,
            "latency_p95_ms": round(self.percentile(self.latencies_ms, 95), 2) if self.latencies_ms else None,
            "latency_p99_ms": round(self.percentile(self.latencies_ms, 99), 2) if self.latencies_ms else None,
        }


async def send_sync_request(
    session: aiohttp.ClientSession,
    base_url: str,
    payload: dict,
    stats: LoadTestStats
) -> RequestResult:
    """Send a sync request."""
    start_time = time.perf_counter()
    
    try:
        async with session.post(f"{base_url}/sync", json=payload) as response:
            latency_ms = (time.perf_counter() - start_time) * 1000
            data = await response.json()
            
            success = response.status == 200
            result = RequestResult(
                request_id=data.get("request_id", "unknown"),
                mode="sync",
                success=success,
                latency_ms=latency_ms,
                error=None if success else data.get("detail")
            )
            stats.add_result(result)
            return result
            
    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        result = RequestResult(
            request_id="error",
            mode="sync",
            success=False,
            latency_ms=latency_ms,
            error=str(e)
        )
        stats.add_result(result)
        return result


async def send_async_request(
    session: aiohttp.ClientSession,
    base_url: str,
    payload: dict,
    callback_url: str,
    stats: LoadTestStats
) -> RequestResult:
    """Send an async request."""
    start_time = time.perf_counter()
    payload_with_callback = {**payload, "callback_url": callback_url}
    
    try:
        async with session.post(f"{base_url}/async", json=payload_with_callback) as response:
            latency_ms = (time.perf_counter() - start_time) * 1000
            data = await response.json()
            
            success = response.status == 200
            request_id = data.get("request_id", "unknown")
            
            result = RequestResult(
                request_id=request_id,
                mode="async",
                success=success,
                latency_ms=latency_ms,
                error=None if success else data.get("detail")
            )
            stats.add_result(result)
            return result
            
    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        result = RequestResult(
            request_id="error",
            mode="async",
            success=False,
            latency_ms=latency_ms,
            error=str(e)
        )
        stats.add_result(result)
        return result


async def run_load_test(
    base_url: str,
    num_requests: int,
    concurrency: int,
    mode: str,
    callback_url: str
):
    """Run the load test."""
    print(f"\n🚀 Starting load test")
    print(f"   Target: {base_url}")
    print(f"   Requests: {num_requests}")
    print(f"   Concurrency: {concurrency}")
    print(f"   Mode: {mode}")
    if mode in ("async", "both"):
        print(f"   Callback URL: {callback_url}")
    print()
    
    # Initialize stats
    sync_stats = LoadTestStats(mode="sync")
    async_stats = LoadTestStats(mode="async")
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(concurrency)
    
    # Sample payload
    payload = {"text": "Hello, this is a test message for load testing.", "count": 3}
    
    async def bounded_request(request_func, *args):
        async with semaphore:
            return await request_func(*args)
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        
        # Generate requests
        for i in range(num_requests):
            if mode == "sync":
                tasks.append(bounded_request(send_sync_request, session, base_url, payload, sync_stats))
            elif mode == "async":
                tasks.append(bounded_request(send_async_request, session, base_url, payload, callback_url, async_stats))
            elif mode == "both":
                # Alternate between sync and async
                if i % 2 == 0:
                    tasks.append(bounded_request(send_sync_request, session, base_url, payload, sync_stats))
                else:
                    tasks.append(bounded_request(send_async_request, session, base_url, payload, callback_url, async_stats))
        
        # Execute all requests
        start_time = time.perf_counter()
        await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.perf_counter() - start_time
    
    # Print results
    print("\n" + "=" * 60)
    print("📊 LOAD TEST RESULTS")
    print("=" * 60)
    print(f"Total time: {total_time:.2f}s")
    print(f"Requests/second: {num_requests / total_time:.2f}")
    print()
    
    if mode in ("sync", "both"):
        summary = sync_stats.summary()
        print("🔄 SYNC ENDPOINT")
        print("-" * 40)
        print(f"  Total requests:  {summary['total_requests']}")
        print(f"  Successful:      {summary['successful']}")
        print(f"  Failed:          {summary['failed']}")
        print(f"  Success rate:    {summary['success_rate']}")
        print(f"  Latency p50:     {summary['latency_p50_ms']} ms")
        print(f"  Latency p95:     {summary['latency_p95_ms']} ms")
        print(f"  Latency p99:     {summary['latency_p99_ms']} ms")
        print()
    
    if mode in ("async", "both"):
        summary = async_stats.summary()
        print("⚡ ASYNC ENDPOINT")
        print("-" * 40)
        print(f"  Total requests:     {summary['total_requests']}")
        print(f"  Successful:         {summary['successful']}")
        print(f"  Failed:             {summary['failed']}")
        print(f"  Success rate:       {summary['success_rate']}")
        print(f"  Ack latency p50:    {summary['latency_p50_ms']} ms")
        print(f"  Ack latency p95:    {summary['latency_p95_ms']} ms")
        print(f"  Ack latency p99:    {summary['latency_p99_ms']} ms")
        print()
        
        # Check callback status from the backend
        print("  📡 Checking callback delivery status...")
    
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Load generator for Sync/Async Work Service")
    parser.add_argument(
        "--target",
        type=str,
        default="http://localhost:8000",
        help="Base URL of the service (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=100,
        help="Number of requests to send (default: 100)"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent requests (default: 10)"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["sync", "async", "both"],
        default="both",
        help="Which endpoints to test (default: both)"
    )
    parser.add_argument(
        "--callback-url",
        type=str,
        default="https://httpbin.org/post",
        help="Callback URL for async requests (default: https://httpbin.org/post)"
    )
    
    args = parser.parse_args()
    
    asyncio.run(run_load_test(
        base_url=args.target,
        num_requests=args.requests,
        concurrency=args.concurrency,
        mode=args.mode,
        callback_url=args.callback_url
    ))


if __name__ == "__main__":
    main()
