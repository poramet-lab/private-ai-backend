import asyncio
from fastapi import WebSocket
from typing import List, Dict
import json
import logging
import time

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # { "room_id": [websocket1, websocket2] }
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)
        logger.info(f"WebSocket connected to room '{room_id}'. Total connections in room: {len(self.active_connections[room_id])}")

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            try:
                self.active_connections[room_id].remove(websocket)
                logger.info(f"WebSocket disconnected from room '{room_id}'.")
                # ถ้าในห้องไม่มีใครแล้ว ให้ลบห้องออกจาก active_connections
                if not self.active_connections[room_id]:
                    del self.active_connections[room_id]
                    logger.info(f"Room '{room_id}' is now empty and has been removed.")
            except ValueError:
                # ป้องกันกรณีที่ websocket ไม่ได้อยู่ใน list แล้ว (อาจเกิด race condition)
                logger.warning(f"WebSocket to be disconnected not found in room '{room_id}'.")

    async def broadcast(self, room_id: str, message: dict):
        if room_id in self.active_connections:
            # Add timestamp to the message before broadcasting
            message_with_ts = {**message, "ts": int(time.time())}
            message_str = json.dumps(message_with_ts, ensure_ascii=False)
            
            # สร้าง list ของ coroutines ที่จะส่งข้อความ
            tasks = [connection.send_text(message_str) for connection in self.active_connections[room_id]]
            
            # รัน coroutines ทั้งหมดพร้อมกัน
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # จัดการกับการเชื่อมต่อที่ล้มเหลว
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failed_connection = self.active_connections[room_id][i]
                    logger.error(f"Failed to send message to a websocket in room '{room_id}': {result}")
                    # อาจจะ disconnect client ที่มีปัญหาออกจากตรงนี้ได้
                    # self.disconnect(failed_connection, room_id)