"""
classification_server.py
------------------------
A toy FastAPI server that classifies text snippets as "code" or "not code".
It accepts up to five strings per call. Latency = (longest string length)^2 ms
"""

import asyncio
from typing import List
from enum import Enum
import math

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Toy Classification Server", version="1.0")

class ClassifyRequest(BaseModel):
    sequences: List[str]

class ClassifyResponse(BaseModel):
    results: List[str]

class Labels(str, Enum):
    code = "code"
    not_code = "not code"


def _is_code(text: str) -> bool:
    return any(tok in text for tok in (";", "{", "}", "def ", "class "))


@app.post("/classify", response_model=ClassifyResponse)
async def classify(body: ClassifyRequest):
    if not (1 <= len(body.sequences) <= 5):
        raise HTTPException(400, "Need 1 - 5 sequences per request")
    longest = max(len(s) for s in body.sequences)
    # Keep quadratic but make very fast for testing: 720² / 1,000,000 = 0.518 seconds
    await asyncio.sleep((longest ** 2) / 1_000_000)

    return {
        "results": [
            Labels.code if _is_code(x) \
            else Labels.not_code \
            for x in body.sequences
        ]
    }

