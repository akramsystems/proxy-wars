"""
proxy.py
========
FastAPI proxy that batches incoming requests before forwarding them to the
classification server.

Three scheduling strategies (choose via $ PROXY_STRATEGY=...):

    • sjf   – Shortest-Job-First       (low average latency)
    • fair  – Round-Robin per client   (fairness / SLA for both customers)
    • fcfs  – FIFO + micro-batching    (max throughput, simple baseline)

Author: 2025-06-13
"""

import os
import time
import uuid
import asyncio
from enum import Enum
from typing import List, Deque, Tuple

import httpx
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from collections import deque

# ------------------------------------------------------------------ config --

DOWNSTREAM = "http://localhost:8001/classify"
MAX_BATCH = 5
BATCH_TIMEOUT_MS = 50
DEFAULT = os.getenv("PROXY_STRATEGY", "sjf").lower()

# ---------------------------------------------------------------- pydantic --

class _Req(BaseModel):
    sequences: List[str]


class _Resp(BaseModel):
    results: List[str]
    proxy_latency_ms: int


class _Strategy(str, Enum):
    sjf = "sjf"
    fair = "fair"
    fcfs = "fcfs"


# ------------------------------------------------------------- queue item --

class _Item:
    __slots__ = ("id", "cid", "seqs", "maxlen", "ts", "fut")

    def __init__(self, cid: str, seqs: List[str]):
        self.id = str(uuid.uuid4())
        self.cid = cid
        self.seqs = seqs
        self.maxlen = max(map(len, seqs))
        self.ts = time.time()
        self.fut: asyncio.Future = asyncio.get_event_loop().create_future()

    def latency(self) -> int:
        return int((time.time() - self.ts) * 1_000)

    def __lt__(self, other):          # for heapq / sorting (SJF)
        return self.maxlen < other.maxlen


# ---------------------------------------------------------------- server --

app = FastAPI(title="Smart Batching Proxy")
q_lock = asyncio.Lock()
fifo_q: Deque[_Item] = deque()
q_a: Deque[_Item] = deque()
q_b: Deque[_Item] = deque()
last_turn = "B"
strategy: _Strategy = _Strategy(DEFAULT)


@app.on_event("startup")
async def _start():
    app.state.cli = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    app.state.task = asyncio.create_task(_dispatcher())
    print(f"[proxy] running, strategy = {strategy.value}")


@app.on_event("shutdown")
async def _stop():
    app.state.task.cancel()
    await app.state.cli.aclose()


@app.post("/proxy_classify", response_model=_Resp)
async def proxy_classify(body: _Req, x_customer_id: str = Header(default="A")):
    if not (1 <= len(body.sequences) <= MAX_BATCH):
        raise HTTPException(400, "Need 1–5 sequences")

    itm = _Item(x_customer_id.upper(), body.sequences)

    async with q_lock:
        if strategy == _Strategy.fair:
            (q_a if itm.cid == "A" else q_b).append(itm)
        else:
            fifo_q.append(itm)

    try:
        await itm.fut
        return {"results": itm.fut.result(), "proxy_latency_ms": itm.latency()}
    except Exception as e:
        raise HTTPException(500, f"Downstream service error: {str(e)}")


@app.post("/strategy")
async def change(new_strategy: _Strategy):
    global strategy
    strategy = new_strategy
    return {"active_strategy": strategy.value}


# ----------------------------------------------------------- dispatcher --

async def _dispatcher():
    global last_turn
    while True:
        await asyncio.sleep(0)
        batch: List[_Item] = []
        total_sequences = 0

        # ------------- SJF -------------
        if strategy == _Strategy.sjf:
            async with q_lock:
                if fifo_q:
                    # Sort by sequence length (shortest first)
                    sorted_items = sorted(fifo_q)
                    for item in sorted_items:
                        if total_sequences + len(item.seqs) <= MAX_BATCH:
                            batch.append(item)
                            total_sequences += len(item.seqs)
                            fifo_q.remove(item)
                        else:
                            break  # Stop if adding this item would exceed limit

        # ------------- FAIR ------------
        elif strategy == _Strategy.fair:
            async with q_lock:
                if q_a or q_b:
                    turn = "A" if last_turn == "B" else "B"
                    primary, secondary = (q_a, q_b) if turn == "A" else (q_b, q_a)
                    
                    # Try to get at least one item from primary queue
                    if primary and total_sequences + len(primary[0].seqs) <= MAX_BATCH:
                        item = primary.popleft()
                        batch.append(item)
                        total_sequences += len(item.seqs)
                        last_turn = turn
                    
                    # Fill remaining space from primary queue
                    while primary and total_sequences + len(primary[0].seqs) <= MAX_BATCH:
                        item = primary.popleft()
                        batch.append(item)
                        total_sequences += len(item.seqs)
                    
                    # Fill remaining space from secondary queue
                    while secondary and total_sequences + len(secondary[0].seqs) <= MAX_BATCH:
                        item = secondary.popleft()
                        batch.append(item)
                        total_sequences += len(item.seqs)

        # ------------- FCFS ------------
        else:
            async with q_lock:
                while fifo_q and total_sequences + len(fifo_q[0].seqs) <= MAX_BATCH:
                    item = fifo_q.popleft()
                    batch.append(item)
                    total_sequences += len(item.seqs)
            
            # Wait a bit and try to fill more if we have space
            if batch and total_sequences < MAX_BATCH:
                await asyncio.sleep(BATCH_TIMEOUT_MS / 1_000)
                async with q_lock:
                    while fifo_q and total_sequences + len(fifo_q[0].seqs) <= MAX_BATCH:
                        item = fifo_q.popleft()
                        batch.append(item)
                        total_sequences += len(item.seqs)

        if not batch:
            await asyncio.sleep(0.005)
            continue

        # flatten & record mapping
        flat: List[str] = []
        idx_map: List[Tuple[_Item, int]] = []
        for itm in batch:
            for i, s in enumerate(itm.seqs):
                flat.append(s)
                idx_map.append((itm, i))

        # Debug: Log batch info
        print(f"[dispatcher] Sending batch: {len(batch)} requests, {len(flat)} sequences total")

        try:
            print(f"[dispatcher] Making request to {DOWNSTREAM} with {len(flat)} sequences")
            r = await app.state.cli.post(DOWNSTREAM, json={"sequences": flat})
            print(f"[dispatcher] Got response: {r.status_code}")
            r.raise_for_status()
            labels = r.json()["results"]
            print(f"[dispatcher] Got {len(labels)} labels back")
        except Exception as e:
            print(f"[dispatcher] Error from classification server: {e}")
            for itm in batch:
                if not itm.fut.done():
                    itm.fut.set_exception(RuntimeError(str(e)))
            continue

        # demux back to callers
        print(f"[dispatcher] Demuxing results back to {len(batch)} requests")
        
        # Group results by request
        request_results = {}
        for (itm, pos), lab in zip(idx_map, labels):
            if itm.id not in request_results:
                request_results[itm.id] = {
                    'item': itm,
                    'results': [None] * len(itm.seqs)
                }
            request_results[itm.id]['results'][pos] = lab
        
        # Set results for completed requests
        for req_id, req_data in request_results.items():
            item = req_data['item']
            results = req_data['results']
            print(f"[dispatcher] Request {req_id[:8]} results: {results}")
            
            # Check if all positions are filled
            if all(x is not None for x in results) and not item.fut.done():
                print(f"[dispatcher] Setting result for request {req_id[:8]}")
                item.fut.set_result(results)
            else:
                print(f"[dispatcher] Request {req_id[:8]} not complete or future already done")
        
        print(f"[dispatcher] Batch processing complete")
