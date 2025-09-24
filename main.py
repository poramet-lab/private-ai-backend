from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Private AI Backend", version="0.1.0")

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
