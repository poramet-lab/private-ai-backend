from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
import os, time, httpx

router = APIRouter(prefix="/ingest", tags=["ingest"])

# Phase 1: ใช้โลคอลเท่านั้น
BASE_DIR = os.path.expanduser("~/private-ai/projects")
OLLAMA_URL = "http://127.0.0.1:11435"
QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION = "demo_rag"

ALLOWED_EXT = {".md",".txt",".csv",".py"}

class IngestResp(BaseModel):
    room_id: str
    file_path: str
    chunks: int
    upserted: int

def ensure_room_dirs(project_id: str, room_id: str) -> str:
    room_dir = os.path.join(BASE_DIR, project_id, "rooms", room_id, "files")
    os.makedirs(room_dir, exist_ok=True)
    return room_dir

def chunk_text(s: str, n: int = 1000, overlap: int = 100):
    i = 0
    L = len(s)
    while i < L:
        yield s[i:i+n]
        i += max(1, n-overlap)

@router.post("/upload", response_model=IngestResp)
async def upload(
    project_id: str = Form("demo"),
    room_id: str = Form("general"),
    file: UploadFile = File(...)
):
    _, ext = os.path.splitext(file.filename or "")
    ext = ext.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    # 1) บันทึกไฟล์ลงโฟลเดอร์ห้อง
    room_dir = ensure_room_dirs(project_id, room_id)
    save_path = os.path.join(room_dir, file.filename)
    data = await file.read()
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception as e:
        raise HTTPException(400, f"Cannot decode text: {e}")
    with open(save_path, "wb") as f:
        f.write(data)

    # 2) ทำ embedding + upsert เป็น batch
    created_at = int(time.time())
    upserted = 0
    idx = 0
    batch = []
    max_batch = 16

    async with httpx.AsyncClient(timeout=120.0) as client:
        for ck in chunk_text(text, n=1000, overlap=100):
            snippet = ck.strip()
            if not snippet:
                idx += 1
                continue

            emb_resp = await client.post(f"{OLLAMA_URL}/api/embeddings", json={"model":"bge-m3","prompt": snippet[:4000]})
            if emb_resp.status_code != 200:
                raise HTTPException(500, f"Ollama embeddings error: {emb_resp.text}")
            emb = emb_resp.json().get("embedding")
            if not emb:
                idx += 1
                continue

            pid = int(f"{created_at}{idx:03d}")
            batch.append({
                "id": pid,
                "vector": emb,
                "payload": {
                    "project_id": project_id,
                    "room_id": room_id,
                    "source_type": "file",
                    "file_path": save_path,
                    "created_at": created_at,
                    "chunk_index": idx,
                    "preview": snippet[:220]
                }
            })

            if len(batch) >= max_batch:
                r = await client.put(f"{QDRANT_URL}/collections/{COLLECTION}/points", json={"points": batch, "wait": True})
                if r.status_code != 200:
                    raise HTTPException(500, f"Qdrant upsert error: {r.text}")
                upserted += len(batch)
                batch = []
            idx += 1

        if batch:
            r = await client.put(f"{QDRANT_URL}/collections/{COLLECTION}/points", json={"points": batch, "wait": True})
            if r.status_code != 200:
                raise HTTPException(500, f"Qdrant upsert error: {r.text}")
            upserted += len(batch)

    return IngestResp(room_id=room_id, file_path=save_path, chunks=idx, upserted=upserted)
