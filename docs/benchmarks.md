# Benchmarks

```console
uv run --no-sync python benchmarks/benchmark_10k.py
uv run --no-sync pytest tests/benchmarks
```

The script constructs 10,000 Skills, measures `RetrievalLoomDiscoveryProvider`
indexing (keyword, fuzzy and BM25), top-10 discovery
and 100 query coroutines, and reports traced memory. No network or framework is
used. These are synthetic local measurements, not production guarantees.

A Windows/Python 3.14 run with tracemalloc enabled measured approximately:

| Measurement | Result |
|---|---|
| Construct 10,000 models | 1.05 s |
| Index (RetrievalLoom ingestion) | 104 s |
| Top-10 discovery | 0.42 s |
| 100 query coroutines | 29.6 s |
| Peak traced allocations | 116 MB |

Indexing dominates: every Skill is ingested durably and idempotently (content
hashing, metadata store, keyword/fuzzy/BM25 indexes) in batches of 1,000. It is a
one-time cost; re-indexing an unchanged catalog ingests nothing, and changed
catalogs ingest only new or edited Skills. Large catalogs should index at startup,
not per request.

The regression test separately requires exact retrieval from 2,000 indexed Skills in
under two seconds. Benchmark on representative data. Retrieval is CPU-bound;
asyncio concurrency is not CPU parallelism.
