import os # dotenv ถูกโหลดแล้วใน database.py

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Annotated
from websocket_manager import ConnectionManager
from code_api import CodeAnswerReq # เพิ่มการ import
import httpx # เพิ่มการ import
import logging
from auth_api import validate_token_for_ws # เปลี่ยนมาใช้ฟังก์ชันใหม่

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Private AI Backend", version="0.1.0")

manager = ConnectionManager()

# --- Dependency Injection for HTTP Client ---
async def get_http_client() -> httpx.AsyncClient:
    """
    Dependency to create and yield a single httpx.AsyncClient instance per request.
    This is more efficient than creating a new client for every call.
    """
    async with httpx.AsyncClient() as client:
        yield client

BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8081")

# --- CORS for frontend dev ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3002","http://127.0.0.1:3002",
        "http://localhost:3003","http://127.0.0.1:3003",
        # Add the IP address of your development machine
        "http://192.168.10.138:3002"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from history_api import router as history_router
app.include_router(history_router)

from ingest_api import router as ingest_router
app.include_router(ingest_router)

from chat_api import router as chat_router
app.include_router(chat_router)

from context_api import router as context_router
app.include_router(context_router)

from rag_api import router as rag_router
app.include_router(rag_router)

@app.get("/health")
def health():
    return JSONResponse({"status":"ok","service":"private-ai-backend"})

from code_api import router as code_router
app.include_router(code_router)

from auth_api import router as auth_router
app.include_router(auth_router)

@app.websocket("/ws/{project_id}/{room_id}/{username}")
async def websocket_endpoint(
    websocket: WebSocket,
    project_id: str,
    room_id: str,
    username: str, # รับ username จาก path โดยตรง
    token: str | None = Query(None), # เปลี่ยนเป็น Optional
    client: httpx.AsyncClient = Depends(get_http_client)
):
    if not token:
        logger.warning(f"WebSocket connection for user '{username}' rejected. Reason: Missing token")
        await websocket.close(code=1008, reason="Missing token")
        return

    user = await validate_token_for_ws(token)
    if not user or user.get('username') != username:
        reason = "Invalid token" if not user else "Username mismatch"
        logger.warning(f"WebSocket connection rejected for user '{username}'. Reason: {reason}")
        await websocket.close(code=1008, reason="Invalid token")
        return

    # ใช้ project_id และ room_id ประกอบกันเป็น key ของห้อง
    full_room_id = f"{project_id}:{room_id}"
    await manager.connect(websocket, full_room_id)
    
    # ประกาศให้ทุกคนในห้องรู้ว่ามีคนเข้ามาใหม่
    await manager.broadcast(full_room_id, {"type": "system", "username": username, "message": "joined the room"})
    
    try:
        while True:
            data = await websocket.receive_json() # { "message": "..." }
            message_text = data.get("message", "")
            
            # รับค่า RAG controls จาก Frontend (ถ้ามี)
            rag_controls = data.get("rag_controls", {})
            limit = rag_controls.get("limit", 5)
            score_threshold = rag_controls.get("score_threshold", 0.3)

            # ตรวจสอบว่าเป็นคำสั่งเรียก AI หรือไม่
            if message_text.startswith("/ai "):
                # แสดงคำถามของผู้ใช้ในห้องแชทก่อน
                await manager.broadcast(full_room_id, {"type": "chat", "username": username, "message": message_text})
                # บันทึกคำถามของผู้ใช้ลงในประวัติ
                try:
                    # ส่ง rag_controls ไปกับ log ด้วย
                    await client.post(
                        f"{BASE_URL}/rooms/{room_id}/messages",
                        params={"project_id": project_id},
                        json={"role": "user", "content": message_text, "username": username}
                    )
                except Exception as log_e:
                    logger.error(f"Failed to log user /ai command for room '{full_room_id}': {log_e}")

                
                try:
                    query = message_text[len("/ai "):]
                    # เรียกใช้ /code/answer ภายใน
                    ai_req = CodeAnswerReq(
                        query=query, 
                        provider="local", # ใช้โมเดล local เป็นค่าเริ่มต้น
                        limit=limit,
                        # score_threshold ยังไม่ได้ถูกใช้ใน CodeAnswerReq แต่เราส่งไปเผื่ออนาคต
                    )
                    response = await client.post(f"{BASE_URL}/code/answer", json=ai_req.dict(), timeout=120.0)
                    response.raise_for_status()
                    ai_response = response.json()
                    
                    answer_message = ai_response.get('answer', 'ขออภัยครับ ไม่สามารถสร้างคำตอบได้')
                    await manager.broadcast(full_room_id, {"type": "chat", "username": "AI", "message": answer_message})
                    
                    try:
                        await client.post(f"{BASE_URL}/rooms/{room_id}/messages", params={"project_id": project_id}, json={"role":"assistant", "content": answer_message, "username": "AI", "meta": ai_response})
                    except Exception as log_e:
                        logger.error(f"Failed to log AI response: {log_e}")
                except Exception as e:
                    error_message = f"ขออภัยครับ เกิดข้อผิดพลาด: {e}"
                    await manager.broadcast(full_room_id, {"type": "chat", "username": "AI", "message": error_message})
                    try:
                        # การบันทึกประวัติจะใช้ timestamp จาก object ที่ส่งไปโดยอัตโนมัติ
                        await client.post(f"{BASE_URL}/rooms/{room_id}/messages", params={"project_id": project_id}, json={"role":"assistant", "content": error_message, "username": "AI", "meta": {"error": str(e)}})
                    except Exception as log_e:
                        logger.error(f"Failed to log error message: {log_e}")
            else:
                # ถ้าไม่ใช่คำสั่ง AI ก็ส่งเป็นข้อความแชทปกติ
                await manager.broadcast(full_room_id, {"type": "chat", "username": username, "message": message_text})
                # บันทึกข้อความของผู้ใช้ลงในประวัติ
                try:
                    await client.post(
                        f"{BASE_URL}/rooms/{room_id}/messages",
                        params={"project_id": project_id},
                        json={"role": "user", "content": message_text, "username": username}
                    )
                except Exception as log_e:
                    logger.error(f"Failed to log user message for room '{full_room_id}': {log_e}")

    except WebSocketDisconnect:
        manager.disconnect(websocket, full_room_id)
        # ประกาศให้ทุกคนในห้องรู้ว่ามีคนออกไป
        await manager.broadcast(full_room_id, {"type": "system", "username": username, "message": "left the room"})
