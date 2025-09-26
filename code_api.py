# code_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
import os, httpx

router = APIRouter(prefix="/code", tags=["code"])

# ---- Config (อิงของเดิมในโปรเจ็กต์) ----
QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION = "code_rag"
OLLAMA_URL = "http://127.0.0.1:11435"
OLLAMA_EMB = f"{OLLAMA_URL}/api/embeddings"
OLLAMA_GEN = f"{OLLAMA_URL}/api/generate"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

# ---- Schemas ----
class CodeSearchReq(BaseModel):
    query: str
    limit: int = 5

class CodeHit(BaseModel):
    id: str
    score: float
    path: str
    start: int
    end: int
    commit: str
    preview: str

class CodeSearchResp(BaseModel):
    hits: List[CodeHit]

class CodeAnswerReq(BaseModel):
    query: str
    limit: int = 5
    provider: Literal["chatgpt","local"] = "chatgpt"
    model: Optional[str] = None  # chatgpt: gpt-4o-mini (default), local: qwen2.5:7b-instruct

class CodeAnswerResp(BaseModel):
    answer: str
    sources: List[CodeHit]

# ---- Helpers ----
async def embed_query(client: httpx.AsyncClient, text: str) -> List[float]:
    r = await client.post(OLLAMA_EMB, json={"model":"bge-m3","prompt": text})
    if r.status_code != 200:
        raise HTTPException(500, f"Ollama embeddings error: {r.text}")
    return r.json()["embedding"]

async def qdrant_search(client: httpx.AsyncClient, vec: List[float], limit: int) -> List[CodeHit]:
    body = {"vector": vec, "limit": limit, "with_payload": True}
    r = await client.post(f"{QDRANT_URL}/collections/{COLLECTION}/points/search", json=body)
    if r.status_code != 200:
        raise HTTPException(500, f"Qdrant search error: {r.text}")
    out = []
    for it in r.json().get("result", []):
        payload = it.get("payload", {})
        out.append(CodeHit(
            id=str(it.get("id")),
            score=float(it.get("score", 0.0)),
            path=str(payload.get("path","")),
            start=int(payload.get("start",0)),
            end=int(payload.get("end",0)),
            commit=str(payload.get("commit","")),
            preview=str(payload.get("preview","")),
        ))
    return out

def build_prompt(query: str, hits: List[CodeHit]) -> str:
    # รวมบริบทเป็นรายการสั้น ๆ พร้อมเลขอ้างอิง [1]..[k]
    lines = ["คุณเป็นผู้ช่วยนักพัฒนา ตอบเป็นภาษาไทยแบบ bullet สั้น ไม่เกิน 8 บรรทัด",
             "อ้างอิงที่มาโดยใส่รายการ 'อ้างอิง' ด้านล่าง (ใช้เลข [1], [2], ... ที่สอดคล้องกับรายการโค้ด)",
             "ห้ามแต่งข้อมูลเกินบริบท ถ้าไม่พอให้ตอบว่า \"ข้อมูลไม่พอ\"",
             "",
             "[คำถาม]", query, "",
             "[บริบทโค้ด]"]
    for i, h in enumerate(hits, start=1):
        prev = (h.preview or "").strip().replace("\n", " ")
        if len(prev) > 300:
            prev = prev[:300] + "..."
        lines.append(f"[{i}] {h.path}:{h.start}-{h.end}@{h.commit}\n{prev}")
    lines += ["", "เขียน 'อ้างอิง:' ต่อท้าย โดยใส่รายการ [เลข] path:start-end@commit"]
    return "\n".join(lines)

async def call_chatgpt(client: httpx.AsyncClient, model: str, prompt: str) -> str:
    if not OPENAI_KEY:
        raise HTTPException(400, "OPENAI_API_KEY ไม่ได้ตั้งค่า แต่ provider=chatgpt")
    r = await client.post(
        OPENAI_URL,
        headers={"Authorization": f"Bearer {OPENAI_KEY}"},
        json={
            "model": model,
            "messages": [{"role":"user","content": prompt}],
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 500,
        }
    )
    if r.status_code != 200:
        raise HTTPException(500, f"OpenAI error: {r.text}")
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

async def call_local_llm(client: httpx.AsyncClient, model: str, prompt: str) -> str:
    r = await client.post(
        OLLAMA_GEN,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "top_p": 0.9, "num_predict": 500}
        }
    )
    if r.status_code != 200:
        raise HTTPException(500, f"Ollama generate error: {r.text}")
    return r.json().get("response","").strip()

# ---- Endpoints ----

@router.post("/search", response_model=CodeSearchResp)
async def code_search(body: CodeSearchReq):
    async with httpx.AsyncClient(timeout=60.0) as client:
        vec = await embed_query(client, body.query)
        hits = await qdrant_search(client, vec, body.limit)
    return CodeSearchResp(hits=hits)

@router.post("/answer", response_model=CodeAnswerResp)
async def code_answer(body: CodeAnswerReq):
    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1) หาเวกเตอร์จาก query
        vec = await embed_query(client, body.query)
        # 2) ค้น Qdrant
        hits = await qdrant_search(client, vec, body.limit)
        # 3) สร้าง prompt จากบริบท
        prompt = build_prompt(body.query, hits)
        # 4) เรียกโมเดล
        if body.provider == "chatgpt":
            model = body.model or "gpt-4o-mini"
            answer = await call_chatgpt(client, model, prompt)
        else:
            model = body.model or "qwen2.5:7b-instruct"
            answer = await call_local_llm(client, model, prompt)
        # 5) คืนคำตอบ + แหล่งอ้างอิง (แบบ structured)
        return CodeAnswerResp(answer=answer, sources=hits)
