"""FlashRank reranker microservice — CPU-optimized ONNX cross-encoder."""

import os

from fastapi import FastAPI
from flashrank import Ranker, RerankRequest
from pydantic import BaseModel

app = FastAPI()

MODEL_NAME = os.getenv("RERANKER_MODEL", "ms-marco-MiniLM-L-12-v2")
_ranker: Ranker | None = None


def _get_ranker() -> Ranker:
    global _ranker
    if _ranker is None:
        _ranker = Ranker(model_name=MODEL_NAME)
    return _ranker


class RerankInput(BaseModel):
    query: str
    documents: list[str]
    top_k: int = 10


class RerankResult(BaseModel):
    index: int
    relevance_score: float


class RerankOutput(BaseModel):
    results: list[RerankResult]


@app.post("/rerank", response_model=RerankOutput)
def rerank(req: RerankInput):
    ranker = _get_ranker()
    passages = [{"id": i, "text": doc} for i, doc in enumerate(req.documents)]
    rerank_req = RerankRequest(query=req.query, passages=passages)
    ranked = ranker.rerank(rerank_req)

    results = []
    for item in ranked[: req.top_k]:
        results.append(
            RerankResult(
                index=int(item["id"]),
                relevance_score=float(item["score"]),
            )
        )
    return RerankOutput(results=results)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME}
