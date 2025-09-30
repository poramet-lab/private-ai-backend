from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx, os

router = APIRouter(prefix="/chat", tags=["chat"])

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11435")
OLLAMA_GEN = f"{OLLAMA_URL}/api/generate"
OLLAMA_EMB = f"{OLLAMA_URL}/api/embeddings"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
COLLECTION = "demo_rag"
BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8081")

class Message(BaseModel):
    role: str
    content: str

class Controls(BaseModel):
    model_selection: str = Field("chatgpt", description="'chatgpt' | 'local'")
    model_name: str = Field("gpt-4o-mini")
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int = 512
    language: str = "th"
    # Auto re-augment
    auto_reaugment: bool = True
    room_scope: str = Field("project", description="'room' หรือ 'project'")
    max_extra_k: int = Field(3, ge=0, le=10)
    score_threshold: float = 0.30
    # Logging
    log_history: bool = True
    # NEW: บังคับค้นเพิ่มก่อนตอบเสมอ
    force_reaugment: bool = False  # บังคับค้น RAG ก่อนตอบเสมอ

class Packet(BaseModel):
    question: str
    recent_window: list[Message] = []
    rag_bundle: str = ""
    controls: Controls
    # ตัวกรองสโคป/เวลา (ใช้ตอน auto-reaugment)
    project_id: str | None = None
    room_id: str | None = None
    after: int | None = None
    before: int | None = None
    # สำหรับบันทึกประวัติ
    username: str | None = None

class GenResp(BaseModel):
    provider: str
    used_model: str
    answer: str
    sources: list[dict] = []

def build_prompt(p: Packet, ctx: str) -> str:
    recent = "\n".join(f"{m.role}: {m.content}" for m in p.recent_window)
    return (
        "คุณคือผู้ช่วยทีมพัฒนาซอฟต์แวร์ ตอบเป็นภาษาไทยเท่านั้น และตอบแบบ bullet สั้น กระชับ ไม่เกิน 8 บรรทัด\n"
        "ห้ามใส่ข้อมูลนอกเหนือจากบริบท ถ้าไม่พอให้ตอบว่า \"ข้อมูลไม่พอ\"\n\n"
        f"[บริบทจาก RAG]\n{ctx}\n\n"
        f"[บริบทล่าสุด]\n{recent}\n\n"
        f"[คำถาม]\n{p.question}"
    )

def seems_insufficient(text: str) -> bool:
    txt = (text or "").strip()
    if len(txt) < 20:
        return True
    for kw in ("ข้อมูลไม่พอ", "ไม่พบข้อมูล", "ไม่มีข้อมูลพอ", "ไม่พอ"):
        if kw in txt:
            return True
    return False

async def call_local_model(client: httpx.AsyncClient, model: str, prompt: str, temperature: float, top_p: float, max_tokens: int) -> str:
    r = await client.post(OLLAMA_GEN, json={
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "top_p": top_p, "num_predict": max_tokens}
    })
    if r.status_code != 200:
        raise HTTPException(500, f"Ollama error: {r.text}")
    return r.json().get("response","").strip()

async def call_chatgpt(client: httpx.AsyncClient, model: str, prompt: str, temperature: float, max_tokens: int) -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(400, "Missing OPENAI_API_KEY")
    r = await client.post(OPENAI_URL, json={
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role":"system","content":"ตอบเป็นภาษาไทยเท่านั้น แบบ bullet สั้น กระชับ"},
            {"role":"user","content": prompt}
        ]
    }, headers={"Authorization": f"Bearer {key}"})
    if r.status_code != 200:
        raise HTTPException(500, f"OpenAI error: {r.text}")
    return r.json()["choices"][0]["message"]["content"].strip()

async def embed_query(client: httpx.AsyncClient, text: str) -> list[float]:
    r = await client.post(OLLAMA_EMB, json={"model":"bge-m3","prompt": text})
    if r.status_code != 200:
        raise HTTPException(500, f"Ollama embeddings error: {r.text}")
    emb = r.json().get("embedding")
    if not emb:
        raise HTTPException(500, "No embedding returned")
    return emb

async def search_qdrant(
    client: httpx.AsyncClient, emb: list[float], *,
    limit: int, score_threshold: float,
    scope: str, room_id: str | None, project_id: str | None,
    after: int | None, before: int | None
):
    must_filters = []
    if scope == "room" and room_id:
        must_filters.append({"key":"room_id","match":{"value":room_id}})
    elif project_id:
        must_filters.append({"key":"project_id","match":{"value":project_id}})
    # เวลา
    if after is not None or before is not None:
        rng = {}
        if after is not None:
            rng["gte"] = int(after)
        if before is not None:
            rng["lte"] = int(before)
        must_filters.append({"key":"created_at","range": rng})

    search = {
        "vector": emb,
        "limit": limit,
        "with_payload": True,
        "with_vectors": False,
        "score_threshold": score_threshold
    }
    if must_filters:
        search["filter"] = {"must": must_filters}

    r = await client.post(f"{QDRANT_URL}/collections/{COLLECTION}/points/search", json=search)
    if r.status_code != 200:
        raise HTTPException(500, f"Qdrant search error: {r.text}")
    return r.json().get("result", [])

@router.post("/generate", response_model=GenResp)
async def generate(p: Packet):
    async with httpx.AsyncClient(timeout=120.0) as client:
        sources = []
        
        # 1. Force Re-augment: ค้นหาข้อมูลใหม่จากคำถามเสมอถ้าเปิดใช้งาน
        if p.controls.auto_reaugment and p.controls.force_reaugment and p.controls.max_extra_k > 0:
            emb = await embed_query(client, p.question)
            results = await search_qdrant(
                client, emb,
                limit=max(3, p.controls.max_extra_k),
                score_threshold=p.controls.score_threshold,
                scope=p.controls.room_scope,
                room_id=p.room_id, project_id=p.project_id,
                after=p.after, before=p.before
            )
            
            appended_count = 0
            for pt in results:
                pl = pt.get("payload") or {}
                fp = pl.get("file_path") or ""
                preview = (pl.get("preview") or "").strip()
                
                # กันการเพิ่มข้อมูลซ้ำซ้อน
                if fp and (fp.split("/")[-1] in p.rag_bundle):
                    continue

                p.rag_bundle += f"\n\n--- [PRE-ADD] id={pt.get('id')} room={pl.get('room_id')} file={fp}\n{preview[:1200]}"
                sources.append({
                    "id": pt.get("id"),
                    "score": round(float(pt.get("score", 0.0)), 3),
                    "room": pl.get("room_id"),
                    "file": fp.split("/")[-1] if fp else None
                })
                appended_count += 1
                if appended_count >= p.controls.max_extra_k:
                    break

        # 2. Generate initial answer
        prompt = build_prompt(p, p.rag_bundle)
        provider = p.controls.model_selection
        chosen_model_name = p.controls.model_name

        if provider == "local":
            ans = await call_local_model(client, "qwen3:8b", prompt, p.controls.temperature, p.controls.top_p, p.controls.max_tokens)
        elif provider == "chatgpt":
            ans = await call_chatgpt(client, chosen_model_name, prompt, p.controls.temperature, p.controls.max_tokens)
        else:
            raise HTTPException(400, "Unknown model_selection")

        # 3. Auto Re-augment if answer is insufficient
        if p.controls.auto_reaugment and seems_insufficient(ans) and p.controls.max_extra_k > 0:
            emb = await embed_query(client, p.question)
            results = await search_qdrant(
                client, emb,
                limit=max(3, p.controls.max_extra_k),
                score_threshold=p.controls.score_threshold,
                scope=p.controls.room_scope, room_id=p.room_id, project_id=p.project_id,
                after=p.after, before=p.before
            )
            
            appended_count = 0
            for pt in results:
                pl = pt.get("payload") or {}
                fp = (pl.get("file_path") or "")
                fname = fp.split("/")[-1] if fp else ""
                prev = (pl.get("preview") or "").strip()
                if fname and (fname in p.rag_bundle):
                    continue
                
                p.rag_bundle += f"\n\n--- [AUTO-ADD] id={pt.get('id')} room={pl.get('room_id')} file={fp}\n{prev[:1200]}"
                sources.append({"id": pt.get("id"), "score": round(float(pt.get("score", 0.0)),3), "room": pl.get("room_id"), "file": fname})
                appended_count += 1
                if appended_count >= p.controls.max_extra_k:
                    break
            
            if appended_count > 0:
                prompt2 = build_prompt(p, p.rag_bundle)
                if provider == "local":
                    ans = await call_local_model(client, "qwen3:8b", prompt2, p.controls.temperature, p.controls.top_p, p.controls.max_tokens)
                else:
                    ans = await call_chatgpt(client, chosen_model_name, prompt2, p.controls.temperature, p.controls.max_tokens)

        # 4. Log history
        if p.controls.log_history and p.room_id:
            try:
                await client.post(
                    f"{BASE_URL}/rooms/{p.room_id}/messages",
                    params={"project_id":"demo"},
                    json={"role":"user","content":p.question,"username": (p.username or "user")}
                )
                await client.post(
                    f"{BASE_URL}/rooms/{p.room_id}/messages",
                    params={"project_id":"demo"},
                    json={"role":"assistant","content":ans,"username":"ai","meta":{"provider":provider,"model":chosen_model_name,"sources":sources}}
                )
            except Exception:
                pass

        # 5. Return final response
        return GenResp(
            provider=provider,
            used_model=chosen_model_name,
            answer=ans,
            sources=sources,
        )
