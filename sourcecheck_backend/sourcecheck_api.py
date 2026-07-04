from typing import Any, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from source_verifier import verify_batch, verify_response


app = FastAPI(title="GEN Y SourceCheck API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


class SingleRequest(BaseModel):
    response: str


class BatchItem(BaseModel):
    item_id: Optional[Any] = None
    response: str


class BatchRequest(BaseModel):
    items: List[BatchItem]


@app.get("/api/sourcecheck/health")
def health():
    return {"status": "ok"}


@app.post("/api/sourcecheck/single")
def sourcecheck_single(payload: SingleRequest):
    return verify_response(payload.response, item_id=None, perform_level2=True)


@app.post("/api/sourcecheck/batch")
def sourcecheck_batch(payload: BatchRequest):
    items = [item.model_dump() if hasattr(item, "model_dump") else item.dict() for item in payload.items]
    return verify_batch(items, perform_level2=True)
