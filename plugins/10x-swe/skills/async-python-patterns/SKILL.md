---
name: async-python-patterns
description: Master Python asyncio, concurrent programming, and async/await patterns
  for high-performance applications. Use when building async APIs, concurrent systems,
  or I/O-bound applications requiring non-blocking operations.
metadata:
  skill-graph-id: plugin/10x-swe/async-python-patterns
  skill-graph-uses: ''
  skill-graph-used-by: ''
---

# Async Python Patterns

Use asyncio for concurrent I/O when a synchronous implementation cannot meet the requirement. Inspect the supported Python version and existing async framework before selecting APIs.

## Workflow

1. Identify the workload: concurrent network or database I/O, blocking library calls, or CPU work. Keep simple scripts synchronous. Threads can offload blocking I/O; pure Python CPU parallelism generally requires processes unless the workload releases the GIL.
2. Mark sync/async boundaries explicitly. Await coroutines and use async-native clients. Offload necessary blocking calls; never call `asyncio.run()` inside an already running event loop.
3. Define task ownership, maximum concurrency, queue capacity, deadlines, and shutdown behavior. A semaphore limits concurrent operations; it does not enforce requests per second.
4. Reuse connection pools and close responses, sessions, and database resources. Use async context managers and failure-safe cleanup.
5. Choose the failure policy before launching tasks: fail the group, collect individual failures, or retry bounded transient errors. Inspect every collected exception; do not silently discard failed items.
6. On cancellation, clean up and propagate `CancelledError`. Cancel and await owned tasks during shutdown. Ensure each queue item receives `task_done()`, including sentinels, and provide a shutdown path for every consumer.
7. Test successful completion, timeout, cancellation, partial failure, resource cleanup, and concurrency limits. Measure latency and resource usage under representative load.

## Reference routing

Use [detailed patterns](references/patterns.md) only for the needed topic:

- Fundamental Patterns: coroutines, `gather`, task creation, errors, and timeouts.
- Advanced Patterns: context managers, iterators, queues, semaphores, and locks.
- Real-World Applications: HTTP, database, and WebSocket sketches.
- Performance Best Practices: pooling, batches, and blocking-call boundaries.
- Common Pitfalls and Testing Async Code: cancellation and pytest examples.

These preserved examples contain simplifications. The producer-consumer sketch has fewer sentinels than consumers and does not await cancelled tasks; the HTTP pooling sketch leaves responses unconsumed; database query strings are illustrative and must use driver parameters in real code. An asyncio lock synchronizes tasks on one loop, not arbitrary threads. Adapt rather than copy.

## Verify

Use the installed framework's supported task and fixture APIs. Prefer [Python's asyncio documentation](https://docs.python.org/3/library/asyncio.html) for exact semantics. Report unresolved failures and untested shutdown behavior; completed tasks alone do not prove safe cleanup.
