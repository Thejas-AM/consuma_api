# Sync/Async Work Service

A Python backend that exposes two endpoints performing the same "work" in different interaction styles:

- **Sync API**: Request comes in, response is returned inline
- **Async API**: Request comes in, returns quickly with an ack, and later calls a provided callback URL with the result

## Features

- ✅ Shared work logic between sync and async paths (no code duplication)
- ✅ SQLite persistence for request tracking and auditing
- ✅ Callback retry with exponential backoff (5 attempts max)
- ✅ SSRF protection (blocks private IPs and internal hostnames)
- ✅ Load generator with latency metrics (p50/p95/p99)
- ✅ Request tracing through callback delivery

## Project Structure

```
consuma/
├── main.py              # FastAPI app entry point
├── core/
│   └── work.py          # Shared work logic
├── database/
│   ├── database.py      # SQLite connection & schema
│   └── repository.py    # CRUD operations
├── model/
│   └── models.py        # Pydantic schemas
├── routes/
│   ├── sync.py          # POST /sync
│   ├── async_.py        # POST /async
│   └── requests.py      # GET /requests
├── utils/
│   └── callback.py      # Callback handling & SSRF protection
└── tools/
    └── load_generator.py # CLI load testing tool
```

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## Running Locally

### 1. Install dependencies

```bash
uv sync
```

### 2. Start the server

```bash
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000` with interactive docs at `/docs`.

## API Endpoints

### POST /sync

Perform work synchronously and return result inline.

```bash
curl -X POST http://localhost:8000/sync \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "count": 3}'
```

**Response:**
```json
{
  "request_id": "uuid",
  "status": "completed",
  "result": {
    "input_hash": "abc123",
    "word_count": 2,
    "character_count": 11,
    "processed_text": "hello world",
    "iterations": 3,
    "processing_time_ms": 205.5
  }
}
```

### POST /async

Queue work and receive result via callback.

```bash
curl -X POST http://localhost:8000/async \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "count": 3, "callback_url": "https://your-server.com/webhook"}'
```

**Immediate Response:**
```json
{
  "request_id": "uuid",
  "status": "pending",
  "message": "Request accepted. Result will be sent to callback URL."
}
```

**Callback Payload (sent later):**
```json
{
  "request_id": "uuid",
  "status": "completed",
  "result": { ... },
  "timestamp": "2024-01-17T10:30:00Z"
}
```

### GET /requests

List recent requests with optional filtering.

```bash
curl "http://localhost:8000/requests?mode=sync&limit=10"
```

### GET /requests/{id}

Get detailed information about a specific request.

```bash
curl http://localhost:8000/requests/{request_id}
```

### GET /healthz

Health check endpoint.

```bash
curl http://localhost:8000/healthz
```

## Load Generator

A CLI tool for load testing both endpoints with metrics.

### Usage

```bash
# Test both endpoints with 100 requests at 10 concurrency
uv run python tools/load_generator.py --requests 100 --concurrency 10 --mode both

# Test only sync endpoint
uv run python tools/load_generator.py --requests 500 --concurrency 20 --mode sync

# Test only async endpoint (starts a callback server automatically)
uv run python tools/load_generator.py --requests 100 --concurrency 10 --mode async
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--target` | http://localhost:8000 | Base URL of the service |
| `--requests` | 100 | Total number of requests |
| `--concurrency` | 10 | Max concurrent requests |
| `--mode` | both | Endpoints to test: sync, async, both |
| `--callback-host` | 127.0.0.1 | Host for callback receiver |
| `--callback-port` | 8888 | Port for callback receiver |

### Sample Output

```
🚀 Starting load test
   Target: http://localhost:8000
   Requests: 100
   Concurrency: 10
   Mode: both

⏳ Waiting for callbacks (5 seconds)...

============================================================
📊 LOAD TEST RESULTS
============================================================
Total time: 4.52s
Requests/second: 22.12

🔄 SYNC ENDPOINT
----------------------------------------
  Total requests:  50
  Successful:      50
  Failed:          0
  Success rate:    100.0%
  Latency p50:     215.32 ms
  Latency p95:     248.91 ms
  Latency p99:     262.15 ms

⚡ ASYNC ENDPOINT
----------------------------------------
  Total requests:     50
  Successful:         50
  Failed:             0
  Success rate:       100.0%
  Ack latency p50:    12.45 ms
  Ack latency p95:    18.32 ms
  Ack latency p99:    22.18 ms
  Callback p50:       245.67 ms
  Callback p95:       289.43 ms
  Callback p99:       312.55 ms
  Callbacks received: 50/50

============================================================
```

## Key Design Decisions

### 1. Work Definition
The "work" performs deterministic text processing:
- SHA-256 hash of input
- Word/character counting
- Text transformation (alternating upper/lower case based on iterations)
- Simulated processing delay (~200ms) to mimic real workloads

Same input always produces the same output for testing consistency.

### 2. Callback Security (SSRF Prevention)
- Blocks private IP ranges (10.x, 172.16-31.x, 192.168.x, 127.x)
- Blocks cloud metadata endpoints (169.254.169.254)
- Blocks internal hostnames (localhost, *.internal)
- Only allows http/https schemes

### 3. Retry Strategy
Failed callbacks use exponential backoff:
- Attempts: 1s → 2s → 4s → 8s → 16s (5 max)
- Tracks retry count and last error in database
- Status: pending → sent (success) or failed (exhausted)

### 4. Request Persistence
SQLite database stores:
- Request ID, mode, input/output data
- Status progression (pending → processing → completed/failed)
- Callback delivery tracking (attempts, errors, timestamps)

### 5. Scalability
- Async processing via FastAPI BackgroundTasks
- Non-blocking I/O with asyncio and aiohttp
- Connection pooling for database and HTTP clients

## Tradeoffs

| Decision | Tradeoff |
|----------|----------|
| SQLite | Simple setup, but limited write concurrency at very high scale |
| BackgroundTasks | No persistence of job queue if server crashes (vs Redis/RabbitMQ) |
| In-memory callback server | Works for testing; production would use dedicated webhook receiver |
| Blocking SSRF by IP | Doesn't prevent DNS rebinding; production may need egress proxy |
