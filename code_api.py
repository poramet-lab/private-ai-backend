# code_api.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
import asyncio
from typing import List, Literal, Optional, Dict, Any
import os, httpx, logging, json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Router and Configs ---
router = APIRouter(prefix="/code", tags=["code"])

# ---- Config ----
QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
COLLECTION = "code_rag"
CONVERSATION_COLLECTION = "conversation_rag"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11435")
OLLAMA_EMB = f"{OLLAMA_URL}/api/embeddings"
OLLAMA_GEN = f"{OLLAMA_URL}/api/generate"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
# ทำให้สอดคล้องกับ index_repo.py โดยใช้ Current Working Directory
REPO_DIR = os.path.abspath(os.getenv("CODE_REPO_DIR", os.getcwd()))

# ---- Schemas ----
class CodeSearchReq(BaseModel):
    query: str
    limit: int = 5

class CodeHit(BaseModel):
    id: str
    score: float
    payload: Dict[str, Any]

class CodeSearchResp(BaseModel):
    hits: List[CodeHit]

class CodeAnswerReq(BaseModel):
    query: str
    limit: int = 5
    score_threshold: float = Field(0.3, ge=0.0, le=1.0)
    provider: Literal["chatgpt","local"] = "chatgpt"
    model: Optional[str] = None

class CodeAnswerResp(BaseModel):
    answer: str
    sources: List[CodeHit]

# ---- Helpers ----
async def embed_query(client: httpx.AsyncClient, text: str) -> List[float]:
    logger.info(f"Embedding query: '{text[:50]}...'")
    r = await client.post(OLLAMA_EMB, json={"model":"bge-m3","prompt": text})
    if r.status_code != 200:
        logger.error(f"Ollama embeddings error: {r.text}")
        raise HTTPException(500, f"Ollama embeddings error: {r.text}")
    logger.info("Embedding successful.")
    return r.json()["embedding"]

async def qdrant_search(client: httpx.AsyncClient, collection: str, vec: List[float], limit: int, score_threshold: float):
    filter_body = {}
    if collection == COLLECTION: # Only apply .next filter to code_rag
        filter_body = {
            "filter": {
                "must_not": [
                    {"key": "path", "match": {"text": ".next"}}
                ]
            }
        }

    body = {
        "vector": vec,
        "limit": limit,
        "with_payload": True,
        "score_threshold": score_threshold,
        **filter_body
    }
    logger.info(f"Searching Qdrant in collection '{collection}' with limit {limit}.")
    r = await client.post(f"{QDRANT_URL}/collections/{collection}/points/search", json=body)
    logger.info(f"Qdrant search responded with status: {r.status_code}")
    r.raise_for_status()
    result = r.json().get("result", [])
    logger.info(f"Qdrant returned {len(result)} hits.")
    return result

def load_prompt_from_file(filename: str) -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", filename)
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Prompt file not found at {prompt_path}")
        return "คุณคือผู้ช่วย AI" # Fallback prompt

def build_prompt(query: str, hits: List[CodeHit]) -> str:
    system_prompt = load_prompt_from_file("code_assistant_prompt.md")
    
    context_lines = []
    for i, h in enumerate(hits, start=1):
        payload = h.payload
        if "path" in payload: # It's a code hit
            context_lines.append(f"[{i}] path: {payload['path']}\ncontent: {payload['preview']}")
        elif "content" in payload: # It's a conversation hit
            username = payload.get('username', 'unknown')
            context_lines.append(f"[{i}] conversation by {username}:\ncontent: {payload['content']}")

    full_context = "\n---\n".join(context_lines)
    return f"{system_prompt}\n\n[บริบทโค้ด]\n{full_context}\n\n[คำถาม]\n{query}"

def clean_ai_response(text: str) -> str:
    """Removes <think> and </think> tags from the AI's response."""
    if "<think>" in text and "</think>" in text:
        start_index = text.find("</think>") + len("</think>")
        return text[start_index:].strip()
    return text.strip()


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
            "max_tokens": 2048,
        }
    )
    if r.status_code != 200:
        raise HTTPException(500, f"OpenAI error: {r.text}")
    data = r.json()
    raw_answer = data["choices"][0]["message"]["content"]
    return clean_ai_response(raw_answer)

async def call_local_llm(client: httpx.AsyncClient, model: str, prompt: str) -> str:
    r = await client.post(
        OLLAMA_GEN,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "top_p": 0.9, "num_predict": 2048}
        }
    )
    if r.status_code != 200:
        raise HTTPException(500, f"Ollama generate error: {r.text}")
    raw_answer = r.json().get("response","")
    return clean_ai_response(raw_answer)

# ---- Endpoints ----

@router.post("/search", response_model=CodeSearchResp)
async def code_search(body: CodeSearchReq):
    logger.info(f"--- Handling /code/search request with query: '{body.query}' ---")
    async with httpx.AsyncClient(timeout=60.0) as client:
        vec = await embed_query(client, body.query)
        qdrant_hits = await qdrant_search(client, COLLECTION, vec, body.limit)

    parsed_hits: List[CodeHit] = []
    for hit in qdrant_hits:
        try:
            payload = hit.get("payload", {})
            parsed_hits.append(CodeHit(
                id=hit.get("id"),
                score=hit.get("score"),
                **payload
            ))
        except Exception as e:
            logger.error(f"Error parsing hit: {hit}. Error: {e}")
            continue
    logger.info(f"Successfully parsed {len(parsed_hits)} hits. Returning response.")
    return CodeSearchResp(hits=parsed_hits)

@router.post("/answer", response_model=CodeAnswerResp)
async def code_answer(body: CodeAnswerReq):
    logger.info(f"--- Handling /code/answer request with query: '{body.query}' ---")
    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. Embed the query
        vec = await embed_query(client, body.query)

        # 2. Search both collections in parallel
        code_hits_task = qdrant_search(client, COLLECTION, vec, body.limit, body.score_threshold)
        conv_hits_task = qdrant_search(client, CONVERSATION_COLLECTION, vec, body.limit, body.score_threshold)
        
        results = await asyncio.gather(code_hits_task, conv_hits_task)
        qdrant_hits = results[0] + results[1]

        # 3. Sort and combine results
        qdrant_hits.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        top_hits = qdrant_hits[:body.limit]
        
        hits: List[CodeHit] = []
        for hit in top_hits:
            try:
                hits.append(CodeHit(id=hit.get("id"), score=hit.get("score"), payload=hit.get("payload", {})))
            except Exception as e:
                logger.error(f"Error parsing hit for answer: {hit}. Error: {e}")
                continue

        logger.info(f"Found {len(hits)} sources to build prompt.")
        if not hits:
            return CodeAnswerResp(answer="ขออภัยครับ ไม่พบข้อมูลโค้ดที่เกี่ยวข้องเพื่อใช้ในการตอบคำถามนี้", sources=[])

        prompt = build_prompt(body.query, hits)

        if body.provider == "chatgpt":
            model = body.model or "gpt-4o-mini"
            answer = await call_chatgpt(client, model, prompt)
        else:
            model = body.model or "qwen3:8b"
            answer = await call_local_llm(client, model, prompt)

        logger.info("Returning answer and sources.")
        return CodeAnswerResp(answer=answer, sources=hits)

@router.get("/raw", response_class=PlainTextResponse)
async def get_raw_code(path: str):
    """
    Endpoint สำหรับอ่านเนื้อหาของไฟล์โค้ดแบบดิบๆ
    ใช้สำหรับให้ UI แสดงตัวอย่างโค้ดฉบับเต็ม หรือให้ผู้ใช้ดาวน์โหลด
    """
    logger.info(f"--- Handling /code/raw request for path: '{path}' ---")

    # ป้องกัน Path Traversal Attack
    if ".." in path:
        raise HTTPException(status_code=400, detail="Invalid path.")

    # สร้าง absolute path ของไฟล์ที่ต้องการให้ถูกต้อง
    file_path = os.path.join(REPO_DIR, path)
    logger.info(f"Attempting to read file from absolute path: {file_path}")

    # ตรวจสอบว่า path ที่ได้มายังคงอยู่ใน REPO_DIR จริงๆ
    if not os.path.abspath(file_path).startswith(REPO_DIR):
        raise HTTPException(status_code=400, detail="Invalid path, access denied.")

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        logger.info(f"Successfully read file: {path}")
        return PlainTextResponse(content=content)
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise HTTPException(status_code=404, detail="File not found.")
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")
