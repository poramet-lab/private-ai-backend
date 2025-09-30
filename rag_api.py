from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx
import os

router = APIRouter(prefix="/rag", tags=["rag"])

# ปรับ URL ให้ตรงกับที่เราตั้งไว้
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11435")
QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
COLLECTION = "demo_rag"

class SearchReq(BaseModel):
    query: str = Field(..., description="คำค้น/คำถาม")
    # ตัวกรองใหม่
    project_id: str | None = Field(None, description="จำกัดโปรเจ็กต์ เช่น demo")
    room_id: str | None = Field(None, description="จำกัดห้อง เช่น general")
    after: int | None = Field(None, description="ค้นหาเฉพาะ payload.created_at >= after (unix seconds)")
    before: int | None = Field(None, description="ค้นหาเฉพาะ payload.created_at <= before (unix seconds)")

    # พารามิเตอร์การค้นหา
    limit: int = Field(5, ge=1, le=20)
    score_threshold: float = Field(0.30, ge=0.0, le=1.0)

class Hit(BaseModel):
    id: int | str
    score: float
    room_id: str | None = None
    project_id: str | None = None
    file: str | None = None
    file_path: str | None = None
    preview: str | None = None
    created_at: int | None = None

class SearchResp(BaseModel):
    hits: list[Hit]

@router.post("/search", response_model=SearchResp)
async def rag_search(body: SearchReq):
    # 1) สร้าง embedding ของ query
    async with httpx.AsyncClient(timeout=60.0) as client:
        emb_resp = await client.post(f"{OLLAMA_URL}/api/embeddings", json={"model":"bge-m3","prompt": body.query})
        if emb_resp.status_code != 200:
            raise HTTPException(500, f"Ollama embeddings error: {emb_resp.text}")
        emb = emb_resp.json().get("embedding")
        if not emb:
            raise HTTPException(500, "No embedding returned")

        # 2) สร้าง filter ตามตัวกรองที่ส่งมา
        must_filters = []
        if body.project_id:
            must_filters.append({"key":"project_id","match":{"value": body.project_id}})
        if body.room_id:
            must_filters.append({"key":"room_id","match":{"value": body.room_id}})

        # range created_at
        if body.after is not None or body.before is not None:
            rng = {}
            if body.after is not None:
                rng["gte"] = int(body.after)
            if body.before is not None:
                rng["lte"] = int(body.before)
            must_filters.append({"key":"created_at","range": rng})

        search = {
            "vector": emb,
            "limit": body.limit,
            "with_payload": True,
            "with_vectors": False,
            "score_threshold": body.score_threshold
        }
        if must_filters:
            search["filter"] = {"must": must_filters}

        qdr = await client.post(f"{QDRANT_URL}/collections/{COLLECTION}/points/search", json=search)
        if qdr.status_code != 200:
            raise HTTPException(500, f"Qdrant search error: {qdr.text}")

        out: list[Hit] = []
        for pt in qdr.json().get("result", []):
            pl = pt.get("payload") or {}
            out.append(Hit(
                id=pt.get("id"),
                score=float(pt.get("score", 0.0)),
                project_id=pl.get("project_id"),
                room_id=pl.get("room_id"),
                file=(pl.get("file_path") or "").split("/")[-1] or None,
                file_path=pl.get("file_path"),
                preview=(pl.get("preview") or "")[:200],
                created_at=pl.get("created_at")
            ))
        return SearchResp(hits=out)
