import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    from agent.tools import close_driver
    close_driver()


app = FastAPI(title="Perry Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://agente-perry-1ndr.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HistoryEntry(BaseModel):
    role: str   # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    query: str
    history: list[HistoryEntry] = []


class ChatResponse(BaseModel):
    query: str
    cypher: str
    results: list[dict]
    graph_records: list[dict] = []
    narrative: str
    success: bool
    retries: int


@app.get("/health")
def health():
    return {"status": "ok", "agent": "perry"}


class EnrichRequest(BaseModel):
    rucs: list[str]

@app.post("/graph-enrich")
def graph_enrich(req: EnrichRequest):
    if not req.rucs:
        return {"records": []}
    from agent.graph import _enrich_graph
    fake = [{"c.ruc": ruc} for ruc in req.rucs]
    return {"records": _enrich_graph(fake)}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query vacío")

    import traceback
    from agent.graph import run_query
    try:
        history = [{"role": h.role, "content": h.content} for h in req.history]
        result = run_query(req.query.strip(), history=history)
        return ChatResponse(**result)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
