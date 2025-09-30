#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Index the repository into Qdrant (collection=code_rag) using bge-m3 embeddings via Ollama.

- Embeddings: Ollama bge-m3 (1024 dims)
- Vector DB: Qdrant (Cosine)
- Payload fields: path, start, end, commit, preview
"""

import os
import re
import sys
import uuid
import json
import time
import hashlib
import httpx
import asyncio
from typing import Iterator, Tuple, List

# ====== CONFIG ======
REPO = os.path.abspath(os.getenv("CODE_REPO_DIR", os.getcwd()))
QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11435")
COLLECTION = os.getenv("QDRANT_COLLECTION", "code_rag")

# batch upsert size
BATCH = int(os.getenv("INDEX_BATCH", "128"))

# chunking
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

# files to include/exclude
INCLUDE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".txt", ".json", ".toml", ".yaml", ".yml"}
EXCLUDE_DIR = {
    ".git", ".svn", ".hg", ".idea", ".vscode",
    ".venv", "venv", "node_modules", ".next", "dist", "build", "__pycache__",
}

# ====== Embeddings ======
async def embed(client: httpx.AsyncClient, text: str) -> List[float]:
    """Call Ollama embeddings (bge-m3) -> list[float] of size 1024."""
    try:
        resp = await client.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": "bge-m3", "prompt": text},
            timeout=120.0
        )
        resp.raise_for_status()
        emb = resp.json().get("embedding")
        if not isinstance(emb, list):
            raise ValueError("embedding missing or not a list")
        return emb
    except Exception as e:
        print(f"EMBED ERROR: {e}", file=sys.stderr)
        # ถ้า embed พัง ให้ข้ามชิ้นนี้ไปโดยคืน None เพื่อไม่ upsert
        return None  # type: ignore

# ====== Repo scan / chunking ======
def collect_files(root: str) -> List[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded directories
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIR]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in INCLUDE_EXT:
                out.append(os.path.join(dirpath, fn))
    return out

def read_text_safe(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""

def chunk_file(path: str) -> Iterator[Tuple[int, int, str]]:
    text = read_text_safe(path)
    if not text:
        return
    n = len(text)
    i = 0
    while i < n:
        j = min(i + CHUNK_SIZE, n)
        yield (i, j, text[i:j])
        if j >= n:
            break
        i = j - CHUNK_OVERLAP  # overlap

def get_commit_hash(repo_root: str) -> str:
    head = ""
    git_head = os.path.join(repo_root, ".git", "HEAD")
    try:
        if os.path.isfile(git_head):
            with open(git_head, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read().strip()
            if head.startswith("ref:"):
                ref_path = head.split(" ", 1)[1].strip()
                full_ref = os.path.join(repo_root, ".git", ref_path)
                if os.path.isfile(full_ref):
                    with open(full_ref, "r", encoding="utf-8", errors="ignore") as f:
                        return f.read().strip()
            return head[:40]
    except Exception:
        pass
    # fallback: hash of filenames + sizes + mtimes
    h = hashlib.sha1()
    for p in sorted(collect_files(repo_root)):
        try:
            st = os.stat(p)
            h.update(p.encode())
            h.update(str(st.st_size).encode())
            h.update(str(int(st.st_mtime)).encode())
        except Exception:
            continue
    return h.hexdigest()

# ====== Qdrant upsert ======
async def ensure_collection(client: httpx.AsyncClient) -> None:
    # try GET collection to check existence
    try:
        r = await client.get(f"{QDRANT_URL}/collections/{COLLECTION}", timeout=5)
        if r.status_code == 200:
            return # Collection exists
    except Exception:
        pass

    # create if not exists
    print(f"Creating Qdrant collection: {COLLECTION}")
    body = {
        "vectors": {"size": 1024, "distance": "Cosine"},
        "on_disk_payload": True,
    }
    try:
        r = await client.put(f"{QDRANT_URL}/collections/{COLLECTION}", json=body, timeout=30)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        # ignore "already exists"
        if "already exists" not in str(e):
            raise

async def upsert_batch(client: httpx.AsyncClient, ids: List[str], vecs: List[List[float]], pays: List[dict]) -> int:
    points = []
    for i, v, p in zip(ids, vecs, pays):
        if v is None:
            # ข้ามจุดที่ embed ล้มเหลว
            continue
        points.append({"id": i, "vector": v, "payload": p})
    
    if not points:
        return 0

    body = {"points": points, "wait": True}
    resp = await client.put(f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true", json=body, timeout=300)
    resp.raise_for_status()
    
    result = resp.json().get("result", {})
    if result.get("status") == "completed":
        return len(points)
    return 0

# ====== MAIN ======
async def process_chunk(client: httpx.AsyncClient, text: str, rel: str, start: int, end: int, commit: str):
    vec = await embed(client, text)
    if vec:
        pid = str(uuid.uuid4())
        snippet = (text or "")[:220]
        pay = {
            "path": rel,
            "start": start,
            "end": end,
            "commit": commit,
            "preview": snippet,
        }
        return pid, vec, pay
    return None, None, None

async def main():
    start_time = time.time()
    
    async with httpx.AsyncClient() as client:
        await ensure_collection(client)

        repo = REPO
        commit = get_commit_hash(repo)
        files = collect_files(repo)
        print(f"Repo: {repo}")
        print(f"Commit: {commit}")
        print(f"Files to process: {len(files)}")

        batch_ids, batch_vecs, batch_pays = [], [], []
        total_upserted = 0
        tasks = []

        for fpath in files:
            rel = os.path.relpath(fpath, repo)
            for start, end, text in chunk_file(fpath):
                tasks.append(process_chunk(client, text, rel, start, end, commit))

        print(f"Total chunks to process: {len(tasks)}")

        for i in range(0, len(tasks), BATCH):
            batch_tasks = tasks[i:i+BATCH]
            results = await asyncio.gather(*batch_tasks)
            
            current_batch_ids = []
            current_batch_vecs = []
            current_batch_pays = []

            for pid, vec, pay in results:
                if pid:
                    current_batch_ids.append(pid)
                    current_batch_vecs.append(vec)
                    current_batch_pays.append(pay)
            
            if current_batch_ids:
                try:
                    upserted_count = await upsert_batch(client, current_batch_ids, current_batch_vecs, current_batch_pays)
                    total_upserted += upserted_count
                    print(f"Upserted batch {i//BATCH + 1}, {upserted_count} points. Total: {total_upserted}")
                except Exception as e:
                    print(f"ERROR during upsert for batch {i//BATCH + 1}: {e}", file=sys.stderr)

    end_time = time.time()
    print(f"\nIndexing finished.")
    print(f"Total indexed chunks: {total_upserted}")
    print(f"Total time: {end_time - start_time:.2f} seconds")

if __name__ == "__main__":
    asyncio.run(main())
