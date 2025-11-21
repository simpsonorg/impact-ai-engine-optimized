# analyzer/rag_retriever.py
import os
from typing import List, Dict, Any
import numpy as np

# try to import faiss - optional
try:
    import faiss
except Exception:
    faiss = None

from .vcs_scanner import read_file_content

# OpenAI client for embeddings (new API wrapper)
try:
    from openai import OpenAI
    _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    _openai_client = None


def _chunk_text(text: str, max_len: int = 1200) -> List[str]:
    """
    Chunk long text into reasonably sized pieces for embeddings (simple slicing by characters).
    """
    if not text:
        return []
    if len(text) <= max_len:
        return [text]
    result = []
    start = 0
    while start < len(text):
        end = min(start + max_len, len(text))
        result.append(text[start:end])
        start = end
    return result


def _embed_texts(texts: List[str]) -> Any:
    if not _openai_client:
        raise RuntimeError("OPENAI_API_KEY not configured - cannot create embeddings")
    # OpenAI embeddings API - text-embedding-3-large
    resp = _openai_client.embeddings.create(model="text-embedding-3-large", input=texts)
    vecs = [r.embedding for r in resp.data]
    arr = np.array(vecs, dtype="float32")
    return arr


def get_relevant_snippets(base_dir: str,
                          services: Dict[str, List[str]],
                          impacted_services: List[str],
                          changed_files: List[str],
                          max_snippets: int = 12) -> List[Dict[str, Any]]:
    """
    For impacted services, chunk code files, embed them, and return top-K snippets most similar to changed files.
    """
    docs = []  # {service, file, text}
    for svc in impacted_services:
        for fp in services.get(svc, []):
            content = read_file_content(fp)
            if not content:
                continue
            rel = os.path.relpath(fp, base_dir).replace("\\", "/")
            for chunk in _chunk_text(content, max_len=1200):
                docs.append({"service": svc, "file": rel, "text": chunk})

    if not docs:
        return []

    # embed documents and queries (changed files)
    try:
        doc_texts = [d["text"] for d in docs]
        doc_vecs = _embed_texts(doc_texts)
    except Exception as e:
        # if embeddings fail, return small set of raw snippets (fallback)
        limited = docs[:min(max_snippets, len(docs))]
        return [{"service": d["service"], "file": d["file"], "snippet": d["text"][:800]} for d in limited]

    # normalize
    doc_norms = doc_vecs / np.linalg.norm(doc_vecs, axis=1, keepdims=True)

    # build index if faiss available
    if faiss is not None:
        index = faiss.IndexFlatIP(doc_norms.shape[1])
        index.add(doc_norms)
    else:
        index = None

    # build query vectors from changed file contents
    query_texts = []
    for cf in changed_files:
        full = os.path.join(base_dir, cf)
        content = read_file_content(full)
        if not content:
            content = cf
        query_texts.append(content)

    if not query_texts:
        return []

    try:
        q_vecs = _embed_texts(query_texts)
        q_norms = q_vecs / np.linalg.norm(q_vecs, axis=1, keepdims=True)
    except Exception:
        # embedding error -> return raw
        limited = docs[:min(max_snippets, len(docs))]
        return [{"service": d["service"], "file": d["file"], "snippet": d["text"][:800]} for d in limited]

    # search
    if index is not None:
        D, I = index.search(q_norms, k=min(max_snippets, len(docs)))
        # flatten indices and dedupe
        idxs = list(set(I.flatten().tolist()))
    else:
        sims = q_norms @ doc_norms.T  # (q, docs)
        # take max sim across queries
        max_sims = sims.max(axis=0)
        idxs = list(np.argsort(-max_sims)[:min(max_snippets, len(docs))])

    snippets = []
    for i in idxs:
        d = docs[int(i)]
        snippets.append({"service": d["service"], "file": d["file"], "snippet": d["text"][:1200]})
    return snippets
