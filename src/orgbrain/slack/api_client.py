import asyncio
import json
import time
from collections.abc import AsyncIterator, Iterable, Iterator

import httpx


def iter_sse(lines: Iterable[str]) -> Iterator[tuple[str, dict]]:
    name = None
    for line in lines:
        if line.startswith("event:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and name:
            yield name, json.loads(line.split(":", 1)[1].strip())
            name = None


class OrgbrainApi:
    def __init__(self, base_url: str, http: httpx.AsyncClient | None = None, retry_every: float = 3.0, max_wait: float = 600):
        self.http = http or httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(10, read=900))
        self.retry_every, self.max_wait = retry_every, max_wait

    async def ask(self, message: str, conversation_id: str, user_id: str | None = None,
                  cache: bool = True) -> AsyncIterator[tuple[str, dict]]:
        body = {"message": message, "conversation_id": conversation_id, "user_id": user_id, "cache": cache}
        deadline = time.monotonic() + self.max_wait
        while True:
            async with self.http.stream("POST", "/api/ask", json=body) as r:
                if r.status_code == 409 and time.monotonic() < deadline:
                    await asyncio.sleep(self.retry_every)
                    continue
                r.raise_for_status()
                buf = []
                async for line in r.aiter_lines():
                    buf.append(line)
                    if line == "":
                        for ev in iter_sse(buf):
                            yield ev
                        buf = []
                for ev in iter_sse(buf):
                    yield ev
                return

    async def decide(self, memory_id: int, action: str, user_id: str) -> tuple[int, dict]:
        r = await self.http.post(f"/api/memories/{memory_id}/{action}", json={"user_id": user_id})
        return r.status_code, r.json()
