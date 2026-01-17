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
    callback_received_at: Optional[float] = None


@dataclass
class LoadTestStats:
    """Aggregated statistics."""
    mode: str
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    latencies_ms: list = field(default_factory=list)
    callback_times_ms: list = field(default_factory=list)
    
    def add_result(self, result: RequestResult):
        self.total_requests += 1
        if result.success:
            self.successful += 1
            self.latencies_ms.append(result.latency_ms)
        else:
            self.failed += 1
    
    def add_callback_time(self, time_ms: float):
        self.callback_times_ms.append(time_ms)
    
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
            "callback_p50_ms": round(self.percentile(self.callback_times_ms, 50), 2) if self.callback_times_ms else None,
            "callback_p95_ms": round(self.percentile(self.callback_times_ms, 95), 2) if self.callback_times_ms else None,
            "callback_p99_ms": round(self.percentile(self.callback_times_ms, 99), 2) if self.callback_times_ms else None,
        }


class CallbackServer:
    """Simple HTTP server to receive callbacks."""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8888):
        self.host = host
        self.port = port
        self.callbacks: dict[str, float] = {}  # request_id -> received_time
        self.request_start_times: dict[str, float] = {}  # request_id -> start_time
        self._server = None
        self._runner = None
    
    async def handle_callback(self, request):
        """Handle incoming callback."""
        received_time = time.perf_counter()
        try:
            data = await request.json()
            request_id = data.get("request_id")
            if request_id:
                self.callbacks[request_id] = received_time
        except:
            pass
        return aiohttp.web.json_response({"status": "received"})
    
    async def start(self):
        """Start the callback server."""
        app = aiohttp.web.Application()
        app.router.add_post("/callback", self.handle_callback)
        app.router.add_post("/", self.handle_callback)
        
        self._runner = aiohttp.web.AppRunner(app)
        await self._runner.setup()
        
        self._server = aiohttp.web.TCPSite(self._runner, self.host, self.port)
        await self._server.start()
        print(f"📡 Callback server started on http://{self.host}:{self.port}")
    
    async def stop(self):
        """Stop the callback server."""
        if self._runner:
            await self._runner.cleanup()
    
    def register_request(self, request_id: str, start_time: float):
        """Register when a request was sent."""
        self.request_start_times[request_id] = start_time
    
    def get_callback_time(self, request_id: str) -> Optional[float]:
        """Get time from request to callback in ms."""
        if request_id in self.callbacks and request_id in self.request_start_times:
            return (self.callbacks[request_id] - self.request_start_times[request_id]) * 1000
        return None


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
    stats: LoadTestStats,
    callback_server: CallbackServer
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
            
            # Register for callback tracking
            callback_server.register_request(request_id, start_time)
            
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
    callback_host: str,
    callback_port: int
):
    """Run the load test."""
    print(f"\n🚀 Starting load test")
    print(f"   Target: {base_url}")
    print(f"   Requests: {num_requests}")
    print(f"   Concurrency: {concurrency}")
    print(f"   Mode: {mode}")
    print()
    
    # Initialize stats
    sync_stats = LoadTestStats(mode="sync")
    async_stats = LoadTestStats(mode="async")
    
    # Start callback server if testing async
    callback_server = CallbackServer(host=callback_host, port=callback_port)
    callback_url = ""
    if mode in ("async", "both"):
        await callback_server.start()
        callback_url = f"http://{callback_host}:{callback_port}/callback"
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(concurrency)
    
    # Sample payload
    payload = {"text": "Hello, this is a test message for load testing.", "count": 3}
    
    async def bounded_request(request_func, *args):
        async with semaphore:
            return await request_func(*args)
    
    try:
        async with aiohttp.ClientSession() as session:
            tasks = []
            
            # Generate requests
            for i in range(num_requests):
                if mode == "sync":
                    tasks.append(bounded_request(send_sync_request, session, base_url, payload, sync_stats))
                elif mode == "async":
                    tasks.append(bounded_request(send_async_request, session, base_url, payload, callback_url, async_stats, callback_server))
                elif mode == "both":
                    # Alternate between sync and async
                    if i % 2 == 0:
                        tasks.append(bounded_request(send_sync_request, session, base_url, payload, sync_stats))
                    else:
                        tasks.append(bounded_request(send_async_request, session, base_url, payload, callback_url, async_stats, callback_server))
            
            # Execute all requests
            start_time = time.perf_counter()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            total_time = time.perf_counter() - start_time
            
            # Wait for callbacks to arrive (give some time for async processing)
            if mode in ("async", "both"):
                print("\n⏳ Waiting for callbacks (5 seconds)...")
                await asyncio.sleep(5)
                
                # Collect callback times
                for result in results:
                    if isinstance(result, RequestResult) and result.mode == "async" and result.success:
                        callback_time = callback_server.get_callback_time(result.request_id)
                        if callback_time:
                            async_stats.add_callback_time(callback_time)
    
    finally:
        if mode in ("async", "both"):
            await callback_server.stop()
    
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
        print(f"  Callback p50:       {summary['callback_p50_ms']} ms")
        print(f"  Callback p95:       {summary['callback_p95_ms']} ms")
        print(f"  Callback p99:       {summary['callback_p99_ms']} ms")
        callbacks_received = len(async_stats.callback_times_ms)
        print(f"  Callbacks received: {callbacks_received}/{async_stats.successful}")
        print()
    
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
        "--callback-host",
        type=str,
        default="127.0.0.1",
        help="Host for callback server (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--callback-port",
        type=int,
        default=8888,
        help="Port for callback server (default: 8888)"
    )
    
    args = parser.parse_args()
    
    asyncio.run(run_load_test(
        base_url=args.target,
        num_requests=args.requests,
        concurrency=args.concurrency,
        mode=args.mode,
        callback_host=args.callback_host,
        callback_port=args.callback_port
    ))


if __name__ == "__main__":
    main()
