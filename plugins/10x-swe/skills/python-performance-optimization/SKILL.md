---
name: python-performance-optimization
description: Profile and optimize Python code using cProfile, memory profilers, and
  performance best practices. Use when debugging slow Python code, optimizing bottlenecks,
  or improving application performance.
metadata:
  skill-graph-id: plugin/10x-swe/python-performance-optimization
  skill-graph-uses: ''
  skill-graph-used-by: ''
---

# Python Performance Optimization

Use this skill to find and reduce measured Python bottlenecks. Preserve behavior and compare representative workloads before claiming improvement.

## Workflow

1. Define the performance problem and target: latency distribution, throughput, peak memory, CPU use, or I/O wait. Record runtime, hardware, input size, and workload characteristics.
2. Establish a repeatable baseline. Separate initialization, steady-state work, and cache effects. Use `timeit` for small operations and appropriate end-to-end measurements for user-visible performance.
3. Locate the bottleneck: `cProfile` for call costs, line profiling for a confirmed hot function, `tracemalloc` for allocation changes, and sampling tools for running processes. Inspect production only within authorized scope.
4. Improve algorithms and data layout before micro-optimizing. Consider indexes and batching for databases, streaming for large inputs, bounded caches for repeated work, and vectorization for suitable numeric workloads.
5. Choose concurrency for the bottleneck. Async helps overlapping I/O; processes can parallelize CPU work but add serialization and startup costs. Threads benefit blocking I/O and workloads that release the GIL.
6. Change one hypothesis at a time. Re-run correctness checks and identical benchmarks. Report absolute results and variance, not only a speedup ratio.
7. Check tradeoffs: memory, cache invalidation, contention, startup time, transaction semantics, and maintainability. Keep the simpler implementation when the gain is not material.

## Reference routing

Open the relevant section of [detailed patterns](references/patterns.md):

- Profiling Tools: CPU, line, memory, and sampling examples.
- Optimization Patterns: collections, generators, strings, lookups, and call overhead.
- Advanced Optimization: NumPy, caching, slots, processes, and async I/O.
- Database Optimization and Memory Optimization: batching, query plans, allocation snapshots, streaming, and weak caches.
- Benchmarking Tools: timing and pytest-benchmark examples.

Preserved examples are experiments, not performance guarantees. `map` is not always faster than a comprehension; NumPy includes allocation costs and fixed-width arithmetic semantics. `sys.getsizeof()` does not measure referenced objects or total retained memory. The leak sketch drops its local references on return and does not demonstrate a retained leak. Validate these claims against the actual workload.

## Acceptance

Provide the baseline, final measurement, relevant environment, correctness results, and remaining limits. Do not introduce caches, dependencies, schema changes, or production profiling permissions merely because they appear in an example.
