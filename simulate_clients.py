"""
simulate_clients.py
-------------------
Emits traffic from two fake customers:
    • Customer A – bursts of 10 very short snippets every ~3 s
    • Customer B – one large block every ~4.5 s
Prints end-to-end latency observed for each request.
"""

import asyncio
import random
import time
import httpx

PROXY = "http://localhost:8000/proxy_classify"


def _random_code():
    return "def foo(): pass" if random.random() < 0.5 else "hello world"


async def customer_a(cli):
    while True:
        snippets = [_random_code()[:5] for _ in range(5)]  # Changed from 10 to 5
        t0 = time.time()
        r = await cli.post(PROXY, json={"sequences": snippets},
                           headers={"X-Customer-Id": "A"})
        if r.status_code != 200:
            print(f"A: Error {r.status_code}: {r.text}")
            await asyncio.sleep(3)
            continue
        lat = (time.time() - t0) * 1_000
        print(f"A: burst of {len(snippets)} done in {lat:6.1f} ms "
              f"(proxy said {r.json()['proxy_latency_ms']} ms)")
        await asyncio.sleep(3)


async def customer_b(cli):
    while True:
        block = "class X:\n" + ("    pass\n" * 80)
        t0 = time.time()
        r = await cli.post(PROXY, json={"sequences": [block]},
                           headers={"X-Customer-Id": "B"})
        if r.status_code != 200:
            print(f"B: Error {r.status_code}: {r.text}")
            await asyncio.sleep(4.5)
            continue
        lat = (time.time() - t0) * 1_000
        print(f"B: big block done in {lat:6.1f} ms "
              f"(proxy said {r.json()['proxy_latency_ms']} ms)")
        await asyncio.sleep(4.5)


async def main():
    async with httpx.AsyncClient(timeout=None) as cli:
        await asyncio.gather(customer_a(cli), customer_b(cli))

if __name__ == "__main__":
    asyncio.run(main()) 