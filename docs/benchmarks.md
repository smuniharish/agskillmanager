# Benchmarks

```console
uv run --no-sync python benchmarks/benchmark_10k.py
uv run --no-sync pytest tests/benchmarks
```

The script constructs 10,000 Skills, measures lexical indexing, top-10 discovery
and 100 query coroutines, and reports traced memory. No network or framework is
used. These are synthetic local measurements, not production guarantees.

A Windows/Python 3.14 run with tracemalloc enabled measured approximately:

| Measurement | Result |
|---|---|
| Construct 10,000 models | 0.55 s |
| Lexical index | 0.29 s |
| Top-10 discovery | 0.071 s |
| 100 query coroutines | 8.61 s |
| Peak traced allocations | 59 MB |

The regression test separately requires exact retrieval from 2,000 Skills in under
two seconds. Benchmark on representative data. Lexical scoring is CPU-bound;
asyncio concurrency is not CPU parallelism.
