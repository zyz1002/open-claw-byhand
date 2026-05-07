"""Memory-RAG bridge — connects bot's curated memories to ChromaDB for semantic search.

Architecture (v3 — consolidation-driven):
  SQLite        = primary store (instant CRUD during conversation)
  Consolidation = background LLM job curates raw → consolidated memories
  ChromaDB      = vector index for curated memories only (RAG semantic search)

Only consolidated (high-quality) memories get vectorized into ChromaDB.
This keeps the vector index clean and useful for fuzzy/semantic recall.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MEMORY_COLLECTION = "memories"

CHROMA_PERSIST_DIR = os.getenv(
    "MEMORY_CHROMA_DIR",
    "data/chroma",
)

EMBEDDING_API_KEY = os.getenv("MEMORY_EMBEDDING_API_KEY")
EMBEDDING_BASE_URL = os.getenv(
    "MEMORY_EMBEDDING_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
EMBEDDING_MODEL = os.getenv("MEMORY_EMBEDDING_MODEL", "text-embedding-v4")

# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------
_chroma_client = None
_memory_collection = None
_embedding_client = None


def _get_chroma_collection():
    """Get or create the ChromaDB memories collection."""
    global _chroma_client, _memory_collection
    if _memory_collection is not None:
        return _memory_collection

    import chromadb
    from chromadb.config import Settings as ChromaSettings

    _chroma_client = chromadb.PersistentClient(
        path=CHROMA_PERSIST_DIR,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    _memory_collection = _chroma_client.get_or_create_collection(
        name=MEMORY_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info(
        "Connected to ChromaDB memories collection at %s, count=%d",
        CHROMA_PERSIST_DIR, _memory_collection.count(),
    )
    return _memory_collection


def _get_embedding(texts: list[str]) -> list[list[float]]:
    """Call DashScope embedding API."""
    global _embedding_client
    if _embedding_client is None:
        from openai import OpenAI
        _embedding_client = OpenAI(
            api_key=EMBEDDING_API_KEY,
            base_url=EMBEDDING_BASE_URL,
        )

    response = _embedding_client.embeddings.create(
        input=texts,
        model=EMBEDDING_MODEL,
    )
    return [item.embedding for item in response.data]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def delete_memory_from_rag(memory_id: int) -> None:
    """Remove a memory from RAG ChromaDB. Fast (no embedding needed)."""
    try:
        collection = _get_chroma_collection()
        collection.delete(ids=[f"memory_{memory_id}"])
        logger.info("[memory_rag] deleted memory %d from ChromaDB", memory_id)
    except Exception as e:
        logger.error("[memory_rag] failed to delete memory %d: %s", memory_id, e)


def update_memory_status_in_rag(memory_id: int, status: str) -> None:
    """Update a memory's status in RAG (no embedding needed, reuses existing vector)."""
    try:
        collection = _get_chroma_collection()
        existing = collection.get(
            ids=[f"memory_{memory_id}"],
            include=["embeddings", "documents", "metadatas"],
        )
        if existing["ids"]:
            metas = existing["metadatas"][0]
            metas["status"] = status
            collection.upsert(
                ids=[f"memory_{memory_id}"],
                embeddings=[existing["embeddings"][0]],
                documents=[existing["documents"][0]],
                metadatas=[metas],
            )
            logger.info("[memory_rag] updated memory %d status to %s", memory_id, status)
    except Exception as e:
        logger.error("[memory_rag] failed to update memory %d status: %s", memory_id, e)


def search_memories_in_rag(query: str, user_id: str, top_k: int = 5) -> list[dict]:
    """Dense search for relevant memories in RAG ChromaDB.

    NOTE: Calls embedding API (blocking). Only used by recall_memories
    as a fallback when SQLite LIKE returns no results.
    """
    try:
        collection = _get_chroma_collection()
        query_embedding = _get_embedding([query])[0]
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={
                "$and": [
                    {"user_id": user_id},
                    {"status": "active"},
                ]
            },
            include=["documents", "metadatas", "distances"],
        )

        output: list[dict[str, Any]] = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc in enumerate(results["documents"][0]):
                distance = results["distances"][0][i]
                score = 1.0 - (distance / 2.0)
                meta = results["metadatas"][0][i] or {}
                output.append({
                    "content": doc,
                    "category": meta.get("category", "fact"),
                    "score": round(max(0.0, score), 4),
                    "memory_id": meta.get("memory_id", 0),
                })
        return output
    except Exception as e:
        logger.error("[memory_rag] search failed: %s", e)
        return []


def batch_sync_memories_to_rag(memories: list[dict], user_id: str) -> int:
    """Batch-sync curated memories to ChromaDB (called by consolidation).

    Args:
        memories: [{"id": int, "content": str, "category": str, "status": str}, ...]
        user_id: user ID

    Returns:
        Number of successfully synced memories.
    """
    if not memories:
        return 0

    synced = 0
    batch_size = 10
    for i in range(0, len(memories), batch_size):
        batch = memories[i:i + batch_size]
        texts = [m["content"] for m in batch]
        try:
            embeddings = _get_embedding(texts)
            collection = _get_chroma_collection()
            collection.upsert(
                ids=[f"memory_{m['id']}" for m in batch],
                embeddings=embeddings,
                documents=texts,
                metadatas=[{
                    "memory_id": m["id"],
                    "category": m["category"],
                    "user_id": user_id,
                    "status": m.get("status", "active"),
                } for m in batch],
            )
            synced += len(batch)
        except Exception as e:
            logger.error("[memory_rag] batch sync failed at offset %d: %s", i, e)

    logger.info("[memory_rag] synced %d/%d curated memories", synced, len(memories))
    return synced
