from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field
from typing import List, Optional
import os, json, time

router = APIRouter(prefix="/rooms", tags=["history"])

BASE_DIR = os.path.expanduser("~/private-ai/projects")
HIST_NAME = "chat.jsonl"   # เก็บแบบ JSONL ต่อบรรทัด

class Msg(BaseModel):
    role: str = Field(..., description="'user' | 'assistant' | 'system'")
    content: str = Field(..., description="ข้อความ")
    ts: int = Field(default_factory=lambda: int(time.time()))
    username: Optional[str] = None
    attachments: Optional[list[str]] = None
    meta: Optional[dict] = None

class WriteResp(BaseModel):
    room_id: str
    ok: bool
    path: str
    last_ts: int

class ReadResp(BaseModel):
    room_id: str
    items: List[Msg]
    next_before: Optional[int] = None   # สำหรับหน้า/โหลดย้อนหลัง

def room_hist_path(project_id: str, room_id: str) -> str:
    room_dir = os.path.join(BASE_DIR, project_id, "rooms", room_id)
    os.makedirs(room_dir, exist_ok=True)
    hist_dir = os.path.join(room_dir, "history")
    os.makedirs(hist_dir, exist_ok=True)
    return os.path.join(hist_dir, HIST_NAME)

@router.post("/{room_id}/messages", response_model=WriteResp)
def append_message(
    room_id: str = Path(...),
    project_id: str = Query("demo"),
    msg: Msg = None
):
    if msg is None:
        raise HTTPException(400, "missing body")
    path = room_hist_path(project_id, room_id)
    rec = msg.dict()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return WriteResp(room_id=room_id, ok=True, path=path, last_ts=rec["ts"])

@router.get("/{room_id}/messages", response_model=ReadResp)
def read_messages(
    room_id: str = Path(...),
    project_id: str = Query("demo"),
    limit: int = Query(30, ge=1, le=200),
    before: Optional[int] = Query(None, description="ดึงรายการก่อน timestamp นี้ (วินาที)"),
):
    path = room_hist_path(project_id, room_id)
    items: list[Msg] = []

    if not os.path.exists(path):
        return ReadResp(room_id=room_id, items=[], next_before=None)

    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue

    # เรียงใหม่→เก่า
    rows.sort(key=lambda x: x.get("ts", 0), reverse=True)

    # กรอง before
    if before is not None:
        rows = [r for r in rows if r.get("ts", 0) < before]

    # ตัดตาม limit
    picked = rows[:limit]
    next_before = picked[-1]["ts"] if len(picked) == limit else None

    # แปลงเป็น Msg
    for r in picked:
        try:
            items.append(Msg(**r))
        except Exception:
            continue

    return ReadResp(room_id=room_id, items=items, next_before=next_before)
