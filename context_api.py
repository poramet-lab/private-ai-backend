from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx, time, os

router = APIRouter(prefix="/context", tags=["context"])

QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION = "demo_rag"

class BundleReq(BaseModel):
    ids: list[int | str] = Field(..., min_items=1, description="รายการ point ids ที่จะรวมเป็นบริบท")
    title: str | None = Field(None, description="หัวข้อ bundle (ถ้าไม่ระบุจะสร้างให้)")

class BundleResp(BaseModel):
    title: str
    bundle: str
    length: int

@router.post("/bundle", response_model=BundleResp)
async def make_bundle(body: BundleReq):
    async with httpx.AsyncClient(timeout=60.0) as client:
        # ใช้ POST /points กับ ids เพื่อดึง payload/vectors
        resp = await client.post(f"{QDRANT_URL}/collections/{COLLECTION}/points", json={
            "ids": body.ids,
            "with_payload": True,
            "with_vectors": False
        })
        if resp.status_code != 200:
            raise HTTPException(500, f"Qdrant retrieve error: {resp.text}")
        pts = resp.json().get("result", [])

    # ประกอบข้อความ bundle
    title = body.title or f"Context Bundle ({time.strftime('%Y-%m-%d %H:%M:%S')})"
    lines = [f"### {title}"]
    for i,pt in enumerate(pts, 1):
        pl = pt.get("payload") or {}
        file_path = pl.get("file_path") or ""
        room = pl.get("room_id") or "-"
        preview = (pl.get("preview") or "").replace("\r","").strip()
        lines.append("")
        lines.append(f"--- [{i}] id={pt.get('id')} room={room}")
        lines.append(f"file: {file_path}")
        lines.append("content:")
        lines.append(preview[:1200])
    bundle = "\n".join(lines)
    return BundleResp(title=title, bundle=bundle, length=len(bundle))
