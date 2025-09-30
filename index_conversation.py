#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Index conversation history from chat.jsonl files into Qdrant.
- Collection: conversation_rag
- Embeddings: Ollama bge-m3 (1024 dims)
- Vector DB: Qdrant (Cosine)
"""

import os
import sys
import uuid
import json
import glob
import time
import urllib.request
import urllib.error
from typing import Iterator, List, Dict

# ====== CONFIG ======
HISTORY_DIR = os.path.abspath(os.getenv("HISTORY_DIR", "./chat_history"))
QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11435")
COLLECTION = os.getenv("QDRANT_CONVERSATION_COLLECTION", "conversation_rag")

# batch upsert size
BATCH = int(os.getenv("INDEX_BATCH", "64"))

# ====== HTTP helpers ======
def http_post(url: str, body: dict, timeout: int = 120) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"HTTP {e.code} {url}: {detail[:400]}") from None
    except Exception as e:
        raise RuntimeError(f"POST {url} failed: {e}") from None

def http_put(url: str, body: dict, timeout: int = 300) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"HTTP {e.code} {url}: {detail[:400]}") from None
    except Exception as e:
        raise RuntimeError(f"PUT {url} failed: {e}") from None

# ====== Embeddings ======
def embed(text: str) -> List[float]:
    """Call Ollama embeddings (bge-m3) -> list[float] of size 1024."""
    try:
        resp = http_post(f"{OLLAMA_URL}/api/embeddings", {"model": "bge-m3", "prompt": text})
        emb = resp.get("embedding")
        if not isinstance(emb, list):
            raise ValueError("embedding missing or not a list")
        return emb
    except Exception as e:
        print(f"EMB ERROR: {e}", file=sys.stderr)
        return None

# ====== History scan ======
def collect_history_files(root: str) -> List[str]:
    """Find all chat.jsonl files recursively."""
    return glob.glob(os.path.join(root, "**", "chat.jsonl"), recursive=True)

def read_messages(path: str) -> Iterator[Dict]:
    """Yield each message from a .jsonl file."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return

# ====== Qdrant upsert ======
def ensure_collection() -> None:
    """Create Qdrant collection if it doesn't exist."""
    try:
        with urllib.request.urlopen(f"{QDRANT_URL}/collections/{COLLECTION}", timeout=5) as r:
            if r.status == 200:
                return
    except Exception:
        pass
    
    body = {
        "vectors": {"size": 1024, "distance": "Cosine"},
        "on_disk_payload": True,
    }
    http_put(f"{QDRANT_URL}/collections/{COLLECTION}", body)
    print(f"Created Qdrant collection: {COLLECTION}")

def upsert_batch(ids: List[str], vecs: List[List[float]], pays: List[dict]) -> None:
    points = [{"id": i, "vector": v, "payload": p} for i, v, p in zip(ids, vecs, pays) if v is not None]
    if not points:
        return
    
    resp = http_put(f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true", {"points": points})
    if resp.get("status") != "ok":
        print("UPSERT failed:", resp)

# ====== MAIN ======
def main():
    ensure_collection()

    history_files = collect_history_files(HISTORY_DIR)
    print(f"Found {len(history_files)} history files in {HISTORY_DIR}")

    batch_ids, batch_vecs, batch_pays = [], [], []
    total_indexed = 0

    for fpath in history_files:
        rel_path = os.path.relpath(fpath, HISTORY_DIR)
        project_id, room_id, _ = rel_path.split(os.sep)

        for msg in read_messages(fpath):
            content = msg.get("content", "").strip()
            username = msg.get("username", "unknown")
            if not content:
                continue

            text_to_embed = f"{username}: {content}"
            vec = embed(text_to_embed)
            if vec is None:
                continue

            payload = {
                "project_id": project_id,
                "room_id": room_id,
                "username": username,
                "content": content,
                "created_at": msg.get("created_at", int(time.time())),
                "file_path": rel_path,
            }

            batch_ids.append(str(uuid.uuid4()))
            batch_vecs.append(vec)
            batch_pays.append(payload)

            if len(batch_ids) >= BATCH:
                upsert_batch(batch_ids, batch_vecs, batch_pays)
                total_indexed += len(batch_ids)
                print(f"Indexed {total_indexed} messages...")
                batch_ids, batch_vecs, batch_pays = [], [], []

    if batch_ids:
        upsert_batch(batch_ids, batch_vecs, batch_pays)
        total_indexed += len(batch_ids)

    print(f"Finished indexing. Total messages indexed: {total_indexed}")

if __name__ == "__main__":
    main()