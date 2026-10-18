---
name: golang-backend-development
description: Complete guide for Go backend development including concurrency patterns,
  web servers, database integration, microservices, and production deployment
metadata:
  tags: golang, go, concurrency, web-servers, microservices, backend, goroutines,
    channels, grpc, rest-api
  tier: tier-1
  skill-graph-id: plugin/10x-swe/golang-backend-development
  skill-graph-uses: ''
  skill-graph-used-by: ''
---

# Go Backend Development

Build or change Go HTTP/gRPC services, concurrent workers, database access, and production lifecycle behavior. Match the project's Go version and existing boundaries before selecting a pattern.

## Workflow

1. Identify the handler or worker, its inputs, dependencies, cancellation path, and completion condition.
2. Reuse the current service structure. Prefer the standard library unless the project already uses a suitable dependency.
3. Bound work and resource use: goroutines, queues, request bodies, connection pools, and timeouts. Give every goroutine an exit path and an owner that waits for completion.
4. Propagate request contexts into network and database operations. Cancel derived contexts; close resources and check iteration errors.
5. Protect shared state, parameterize SQL, and keep transaction boundaries explicit. Return contextual errors without exposing sensitive details to clients.
6. Verify changed behavior with focused tests. Use the race detector for concurrency changes and benchmarks/profiles for performance claims. Confirm graceful shutdown when lifecycle behavior changes.

## Load only the relevant examples

- [Pattern reference](references/patterns.md): concurrency primitives, HTTP handlers, pipelines, worker pools, SQL, errors, testing, shutdown, logging, and microservice examples. Read the matching section only.
- [Extended examples](EXAMPLES.md): use its contents to select an implementation example when the pattern reference is insufficient.

These are retained illustrative examples, not verified production implementations. Adapt them to the installed Go version and current code; do not copy arbitrary pool sizes, coverage targets, layouts, or deployment architecture. Some examples use older APIs or simplified cancellation/error handling. Confirm those details in the official references before use.

## Authoritative references

[Go documentation](https://go.dev/doc/), [net/http](https://pkg.go.dev/net/http), [database/sql](https://pkg.go.dev/database/sql), [context](https://pkg.go.dev/context), [sync](https://pkg.go.dev/sync), and [Go pipelines](https://go.dev/blog/pipelines).
