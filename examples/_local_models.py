"""Local Hugging Face model adapters for RetrievalLoom: embeddings, reranker and NLI.

Requires the ``models`` dependency group (``uv sync --group models``) and model
directories under ``MODELS_DIR`` (default ``models/``):

- ``bge-m3`` for dense embeddings,
- ``bge-reranker-v2-m3`` for cross-encoder reranking,
- ``nli/deberta-base-long-nli`` (or any entailment/neutral/contradiction classifier).

Inference is blocking CPU work, so every call goes through the engine's
offloader. Weights load once on ``initialize`` and are never downloaded.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from retrievalloom.contracts.component import ComponentInfo, make_info
from retrievalloom.contracts.models import NLIABC, EmbeddingModelABC, RerankerABC, RerankScore
from retrievalloom.domain.retrieval import NLIJudgement, NLILabel
from retrievalloom.runtime.offloader import WorkloadKind

if TYPE_CHECKING:
    from collections.abc import Sequence

    from retrievalloom.contracts.component import ComponentContext
    from retrievalloom.contracts.models import NLIPair, RerankItem
    from retrievalloom.runtime.offloader import Offloader

MODELS_DIR = Path(os.getenv("MODELS_DIR", Path(__file__).resolve().parents[1] / "models"))
EMBEDDING_DIR = MODELS_DIR / "bge-m3"
RERANKER_DIR = MODELS_DIR / "bge-reranker-v2-m3"
NLI_DIR = MODELS_DIR / "nli" / os.getenv("NLI_MODEL", "deberta-base-long-nli")
_LABELS = {
    "entailment": NLILabel.ENTAILMENT,
    "neutral": NLILabel.NEUTRAL,
    "contradiction": NLILabel.CONTRADICTION,
}


def models_available() -> bool:
    return all(path.is_dir() for path in (EMBEDDING_DIR, RERANKER_DIR, NLI_DIR))


class _LocalModel:
    _offloader: Offloader
    _model: Any = None

    def __init__(self, model_dir: Path, workload: WorkloadKind) -> None:
        self._dir = model_dir
        self._workload = workload
        self._lock = threading.Lock()

    def _load(self) -> Any:
        raise NotImplementedError

    async def initialize(self, context: ComponentContext) -> None:
        self._offloader = context.offloader
        if self._model is None:
            self._model = await context.offloader.run(self._workload, self._load)

    async def close(self) -> None:
        self._model = None


class BgeM3Embedding(_LocalModel, EmbeddingModelABC):
    """Dense, normalized 1024-dimensional bge-m3 embeddings via sentence-transformers."""

    def __init__(self, model_dir: Path = EMBEDDING_DIR, *, batch_size: int = 16) -> None:
        super().__init__(model_dir, WorkloadKind.EMBEDDING)
        self._batch_size = batch_size
        self._info = make_info(
            component="embedding",
            implementation="bge-m3-sentence-transformers",
            version="1",
            model_identity="BAAI/bge-m3",
            dimensions=1024,
        )

    @property
    def info(self) -> ComponentInfo:
        return self._info

    @property
    def dimensions(self) -> int:
        return 1024

    @property
    def max_batch_size(self) -> int:
        return self._batch_size

    def _load(self) -> Any:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(str(self._dir), device="cpu", local_files_only=True)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            vectors = self._model.encode(
                texts, batch_size=self._batch_size, normalize_embeddings=True
            )
        return [[float(value) for value in vector] for vector in vectors]

    async def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return await self._offloader.run(WorkloadKind.EMBEDDING, self._encode, list(texts))

    async def embed_query(self, text: str) -> Sequence[float]:
        return (await self._offloader.run(WorkloadKind.EMBEDDING, self._encode, [text]))[0]


class BgeReranker(_LocalModel, RerankerABC):
    """bge-reranker-v2-m3 cross-encoder via sentence-transformers ``CrossEncoder``."""

    def __init__(self, model_dir: Path = RERANKER_DIR) -> None:
        super().__init__(model_dir, WorkloadKind.RERANK)
        self._info = make_info(
            component="reranker",
            implementation="bge-reranker-v2-m3",
            version="1",
            model_identity="BAAI/bge-reranker-v2-m3",
        )

    @property
    def info(self) -> ComponentInfo:
        return self._info

    def _load(self) -> Any:
        from sentence_transformers import CrossEncoder

        return CrossEncoder(str(self._dir), device="cpu", local_files_only=True)

    def _score(self, query: str, texts: list[str]) -> list[float]:
        with self._lock:
            scores = self._model.predict([(query, text) for text in texts])
        return [float(score) for score in scores]

    async def rerank(self, query: str, items: Sequence[RerankItem]) -> Sequence[RerankScore]:
        if not items:
            return []
        scores = await self._offloader.run(
            WorkloadKind.RERANK, self._score, query, [item.text for item in items]
        )
        return [
            RerankScore(item_id=item.item_id, score=score)
            for item, score in zip(items, scores, strict=True)
        ]


class LocalNLI(_LocalModel, NLIABC):
    """Premise/hypothesis classifier with entailment, neutral and contradiction labels."""

    def __init__(self, model_dir: Path = NLI_DIR, *, max_length: int = 512) -> None:
        super().__init__(model_dir, WorkloadKind.NLI)
        self._max_length = max_length
        self._identity = model_dir.name
        self._info = make_info(
            component="nli",
            implementation="transformers-sequence-classification",
            version="1",
            model_identity=self._identity,
        )

    @property
    def info(self) -> ComponentInfo:
        return self._info

    def _load(self) -> Any:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(self._dir, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(self._dir, local_files_only=True)
        return tokenizer, model.eval()

    def _classify(self, premises: list[str], hypotheses: list[str]) -> list[dict[str, float]]:
        import torch

        tokenizer, model = self._model
        with self._lock, torch.inference_mode():
            batch = tokenizer(
                premises,
                hypotheses,
                padding=True,
                truncation=True,
                max_length=self._max_length,
                return_tensors="pt",
            )
            probabilities = torch.softmax(model(**batch).logits, dim=-1)
        labels = model.config.id2label
        return [
            {str(labels[index]).casefold(): float(value) for index, value in enumerate(row)}
            for row in probabilities
        ]

    async def judge(self, pairs: Sequence[NLIPair]) -> Sequence[NLIJudgement]:
        if not pairs:
            return []
        rows = await self._offloader.run(
            WorkloadKind.NLI,
            self._classify,
            [pair.premise for pair in pairs],
            [pair.hypothesis for pair in pairs],
        )
        judgements = []
        for pair, row in zip(pairs, rows, strict=True):
            scores = {_LABELS[name]: value for name, value in row.items()}
            label = max(scores, key=scores.__getitem__)
            judgements.append(
                NLIJudgement(
                    label=label,
                    confidence=min(1.0, max(0.0, scores[label])),
                    scores=scores,
                    model_identity=self._identity,
                    hypothesis_ref=pair.hypothesis_ref,
                )
            )
        return judgements
