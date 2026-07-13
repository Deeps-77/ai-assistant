"""ChromaDB vector database layer for the AI Software Delivery Assistant.

Collections:
  - threads       : conversation/run metadata keyed by thread_id
  - projects      : project records keyed by project_path
  - agent_steps   : per-run agent step events (for real-time streaming + history)
  - code_embeddings: generated code chunks for semantic search
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import chromadb
from chromadb.config import Settings

_CHROMA_PATH = os.getenv("CHROMA_PATH", os.path.join(os.getcwd(), ".chroma"))

_client: chromadb.PersistentClient | None = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=_CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


# ─── Collections ────────────────────────────────────────────────────────────


def _col(name: str):
    return _get_client().get_or_create_collection(name)


# ─── Threads ─────────────────────────────────────────────────────────────────


def save_thread(thread_id: str, metadata: dict[str, Any]) -> None:
    """Upsert a thread record."""
    col = _col("threads")
    safe = {k: (json.dumps(v) if not isinstance(v, (str, int, float, bool)) else v)
            for k, v in metadata.items()}
    safe["updated_at"] = time.time()
    safe["thread_id"] = thread_id
    col.upsert(
        ids=[thread_id],
        documents=[json.dumps(metadata)],
        metadatas=[safe],
    )


def get_thread(thread_id: str) -> dict | None:
    col = _col("threads")
    try:
        result = col.get(ids=[thread_id], include=["documents", "metadatas"])
        if result["ids"]:
            doc = result["documents"][0]
            try:
                return json.loads(doc)
            except json.JSONDecodeError:
                return result["metadatas"][0]
    except Exception:
        pass
    return None


def list_threads(limit: int = 50) -> list[dict]:
    col = _col("threads")
    try:
        result = col.get(include=["documents", "metadatas"], limit=limit)
        threads = []
        for doc, meta in zip(result.get("documents", []), result.get("metadatas", [])):
            try:
                threads.append(json.loads(doc))
            except Exception:
                threads.append(meta)
        # Sort by updated_at descending
        threads.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        return threads
    except Exception:
        return []


# ─── Projects ────────────────────────────────────────────────────────────────


def save_project(project_path: str, metadata: dict[str, Any]) -> None:
    """Upsert a project record."""
    col = _col("projects")
    project_id = project_path.replace("/", "_").replace("\\", "_").replace(":", "")
    safe = {k: (json.dumps(v) if not isinstance(v, (str, int, float, bool)) else v)
            for k, v in metadata.items()}
    safe["updated_at"] = time.time()
    safe["project_path"] = project_path
    safe["project_id"] = project_id
    col.upsert(
        ids=[project_id],
        documents=[json.dumps(metadata)],
        metadatas=[safe],
    )


def list_projects(limit: int = 50) -> list[dict]:
    col = _col("projects")
    try:
        result = col.get(include=["documents", "metadatas"], limit=limit)
        projects = []
        for doc, meta in zip(result.get("documents", []), result.get("metadatas", [])):
            try:
                projects.append(json.loads(doc))
            except Exception:
                projects.append(meta)
        projects.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        return projects
    except Exception:
        return []


# ─── Agent Steps ─────────────────────────────────────────────────────────────


def append_agent_step(
    thread_id: str,
    agent: str,
    status: str,  # "running" | "done" | "error"
    message: str,
    extra: dict | None = None,
) -> str:
    """Append a single agent step event and return its ID."""
    col = _col("agent_steps")
    step_id = f"{thread_id}|{agent}|{time.time()}"
    payload = {
        "thread_id": thread_id,
        "agent": agent,
        "status": status,
        "message": message,
        "timestamp": time.time(),
        **(extra or {}),
    }
    col.upsert(
        ids=[step_id],
        documents=[json.dumps(payload)],
        metadatas=[{
            "thread_id": thread_id,
            "agent": agent,
            "status": status,
            "timestamp": payload["timestamp"],
        }],
    )
    return step_id


def get_agent_steps(thread_id: str) -> list[dict]:
    """Return all agent steps for a thread, sorted by timestamp."""
    col = _col("agent_steps")
    try:
        result = col.get(
            where={"thread_id": thread_id},
            include=["documents", "metadatas"],
        )
        steps = []
        for doc in result.get("documents", []):
            try:
                steps.append(json.loads(doc))
            except Exception:
                pass
        steps.sort(key=lambda x: x.get("timestamp", 0))
        return steps
    except Exception:
        return []


# ─── Code Embeddings ─────────────────────────────────────────────────────────


def save_code_embedding(
    thread_id: str,
    file_path: str,
    content: str,
    module: str = "",
) -> None:
    """Store a generated file for later semantic search.
    
    Uses ChromaDB's default embedding function (sentence-transformers).
    Chunks long files at 2000 chars.
    """
    col = _col("code_embeddings")
    chunk_size = 2000
    chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)]
    ids, docs, metas = [], [], []
    for idx, chunk in enumerate(chunks):
        chunk_id = f"{thread_id}|{file_path}|{idx}"
        ids.append(chunk_id)
        docs.append(chunk)
        metas.append({
            "thread_id": thread_id,
            "file_path": file_path,
            "module": module,
            "chunk_index": idx,
            "timestamp": time.time(),
        })
    try:
        col.upsert(ids=ids, documents=docs, metadatas=metas)
    except Exception:
        # Embedding errors are non-fatal
        pass


def search_code(query: str, thread_id: str | None = None, n_results: int = 5) -> list[dict]:
    """Semantic search over generated code chunks."""
    col = _col("code_embeddings")
    try:
        where = {"thread_id": thread_id} if thread_id else None
        kwargs: dict = {"query_texts": [query], "n_results": n_results, "include": ["documents", "metadatas", "distances"]}
        if where:
            kwargs["where"] = where
        result = col.query(**kwargs)
        hits = []
        for doc, meta, dist in zip(
            result.get("documents", [[]])[0],
            result.get("metadatas", [[]])[0],
            result.get("distances", [[]])[0],
        ):
            hits.append({"content": doc, "metadata": meta, "score": 1 - dist})
        return hits
    except Exception:
        return []
