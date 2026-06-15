"""Embed parsed document chunks and upsert them into Qdrant."""

from __future__ import annotations

from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.config import settings
from app.rag.ingestion.embedder import embed_batch


def _get_client() -> QdrantClient:
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        timeout=30,
    )


def upsert_chunks(
    chunks: list[dict[str, Any]],
    dry_run: bool = False,
    batch_size: int = 128,
) -> int:
    """Embed and upsert chunks, returning the number accepted."""
    if not chunks:
        return 0
    if dry_run:
        return len(chunks)

    client = _get_client()
    upserted = 0

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        texts = [str(chunk["content"]) for chunk in batch]
        vectors = embed_batch(texts)
        points: list[PointStruct] = []

        for chunk, vector in zip(batch, vectors):
            payload = {
                key: value
                for key, value in chunk.items()
                if key != "point_id"
            }
            # Akilu changed this because retrieval, reranking, and prompt
            # construction use the canonical payload field named "text".
            payload["text"] = payload.pop("content")
            points.append(
                PointStruct(
                    id=chunk["point_id"],
                    vector=vector,
                    payload=payload,
                )
            )

        client.upsert(
            collection_name=settings.collection_name,
            points=points,
            wait=True,
        )
        upserted += len(points)

    return upserted
