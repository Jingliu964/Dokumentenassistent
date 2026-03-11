import os
import sqlite3
from typing import List, Tuple

import numpy as np
import faiss
import requests
from openai import OpenAI

from .loaders import iter_documents
from .settings import (
    MODEL_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_EMBED_MODEL,
    OPENAI_CHAT_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_CHAT_MODEL,
    OLLAMA_EMBED_MODEL,
    OLLAMA_TIMEOUT,
    RAG_CHUNK_SIZE,
    RAG_CHUNK_OVERLAP,
    RAG_TOP_K,
    get_tenant_paths,
)


_openai_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def _ensure_dirs(paths) -> None:
    os.makedirs(paths.docs_dir, exist_ok=True)
    os.makedirs(paths.uploads_dir, exist_ok=True)
    os.makedirs(paths.index_dir, exist_ok=True)


def _connect_db(sqlite_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(sqlite_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL
        );
        """
    )
    return conn


def _chunk_text(text: str) -> List[str]:
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + RAG_CHUNK_SIZE, length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += max(RAG_CHUNK_SIZE - RAG_CHUNK_OVERLAP, 1)
    return chunks


def _embed_texts(texts: List[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    if MODEL_PROVIDER == "openai":
        response = _get_openai_client().embeddings.create(model=OPENAI_EMBED_MODEL, input=texts)
        vectors = [item.embedding for item in response.data]
        return np.array(vectors, dtype=np.float32)
    if MODEL_PROVIDER == "ollama":
        return _ollama_embeddings(texts)
    raise RuntimeError(f"Unsupported MODEL_PROVIDER: {MODEL_PROVIDER}")


def _ollama_embeddings(texts: List[str]) -> np.ndarray:
    vectors: List[List[float]] = []
    for text in texts:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": OLLAMA_EMBED_MODEL, "prompt": text},
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        embedding = data.get("embedding")
        if embedding is None:
            embeddings = data.get("embeddings") or data.get("data")
            if isinstance(embeddings, list):
                if embeddings and isinstance(embeddings[0], dict) and "embedding" in embeddings[0]:
                    embedding = embeddings[0]["embedding"]
                elif embeddings and isinstance(embeddings[0], list):
                    embedding = embeddings[0]
        if embedding is None:
            raise RuntimeError("Ollama embedding response missing embedding.")
        vectors.append(embedding)
    return np.array(vectors, dtype=np.float32)


def _chat_completion(system_prompt: str, user_prompt: str) -> str:
    if MODEL_PROVIDER == "openai":
        completion = _get_openai_client().chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return completion.choices[0].message.content or ""
    if MODEL_PROVIDER == "ollama":
        return _ollama_chat(system_prompt, user_prompt)
    raise RuntimeError(f"Unsupported MODEL_PROVIDER: {MODEL_PROVIDER}")


def _ollama_chat(system_prompt: str, user_prompt: str) -> str:
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": OLLAMA_CHAT_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "temperature": 0.2,
        },
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    message = data.get("message") or {}
    return message.get("content") or data.get("response") or ""


def _load_index(dim: int, faiss_path: str) -> faiss.IndexIDMap2:
    if os.path.exists(faiss_path):
        index = faiss.read_index(faiss_path)
        if index.d != dim:
            raise RuntimeError("Embedding dimension mismatch. Rebuild the index.")
        return index
    base = faiss.IndexFlatL2(dim)
    return faiss.IndexIDMap2(base)


def _save_index(index: faiss.Index, faiss_path: str) -> None:
    faiss.write_index(index, faiss_path)


def rebuild_index(tenant_id: str) -> None:
    paths = get_tenant_paths(tenant_id)
    if os.path.exists(paths.faiss_path):
        os.remove(paths.faiss_path)
    if os.path.exists(paths.sqlite_path):
        os.remove(paths.sqlite_path)


def ingest_documents(tenant_id: str) -> Tuple[int, int]:
    paths = get_tenant_paths(tenant_id)
    _ensure_dirs(paths)
    conn = _connect_db(paths.sqlite_path)

    files_processed = 0
    total_chunks = 0

    texts = []
    meta = []

    for source, content in iter_documents([paths.docs_dir, paths.uploads_dir], paths.base_dir):
        files_processed += 1
        chunks = _chunk_text(content)
        for i, chunk in enumerate(chunks):
            texts.append(chunk)
            meta.append((source, i, chunk))

    if not texts:
        conn.close()
        return files_processed, total_chunks

    embeddings = _embed_texts(texts)
    dim = embeddings.shape[1]
    index = _load_index(dim, paths.faiss_path)

    for i, (source, chunk_index, content) in enumerate(meta):
        cursor = conn.execute(
            "INSERT INTO chunks (source, chunk_index, content) VALUES (?, ?, ?)",
            (source, chunk_index, content),
        )
        chunk_id = cursor.lastrowid
        vector = embeddings[i : i + 1]
        index.add_with_ids(vector, np.array([chunk_id], dtype=np.int64))
        total_chunks += 1

    conn.commit()
    conn.close()
    _save_index(index, paths.faiss_path)

    return files_processed, total_chunks


def query_rag(
    tenant_id: str, question: str, top_k: int | None = None
) -> Tuple[str, List[Tuple[str, int]]]:
    paths = get_tenant_paths(tenant_id)
    if not os.path.exists(paths.faiss_path) or not os.path.exists(paths.sqlite_path):
        raise RuntimeError("Index not found. Run /ingest first.")

    top_k = top_k or RAG_TOP_K
    q_emb = _embed_texts([question])

    index = faiss.read_index(paths.faiss_path)
    distances, ids = index.search(q_emb, top_k)
    id_list = [int(i) for i in ids[0] if i != -1]

    if not id_list:
        return "I couldn't find relevant context in the index.", []

    conn = _connect_db(paths.sqlite_path)
    placeholders = ",".join("?" for _ in id_list)
    rows = conn.execute(
        f"SELECT id, source, content FROM chunks WHERE id IN ({placeholders})",
        id_list,
    ).fetchall()
    conn.close()

    # Preserve FAISS order
    row_map = {row[0]: row for row in rows}
    ordered = [row_map[i] for i in id_list if i in row_map]

    context_blocks = []
    citations: List[Tuple[str, int]] = []
    for chunk_id, source, content in ordered:
        context_blocks.append(f"Source: {source}\n{content}")
        citations.append((source, chunk_id))

    context = "\n\n".join(context_blocks)

    system_prompt = (
        "You are a helpful assistant. Use only the provided context to answer. "
        "If the context is insufficient, say so." 
    )
    user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

    answer = _chat_completion(system_prompt, user_prompt)
    return answer, citations
