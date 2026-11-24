"""Semantic answer cache in Redis: question vectors in one hash, answers in another. Lookup is a brute-force cosine
over every cached question, fine for the few thousand entries a team builds up."""

import json
import uuid

import numpy as np

VECS, ANSWERS = "orgbrain:cache:vec", "orgbrain:cache:ans"


class SemanticCache:
    def __init__(self, redis, threshold: float = 0.98, invalidate_at: float = 0.5, max_entries: int = 5000):
        self.redis, self.threshold, self.invalidate_at, self.max_entries = redis, threshold, invalidate_at, max_entries

    async def _scores(self, vec) -> tuple[list[bytes], np.ndarray]:
        raw = await self.redis.hgetall(VECS)
        if not raw:
            return [], np.zeros(0)
        keys = list(raw)
        mat = np.stack([np.frombuffer(raw[k], dtype=np.float32) for k in keys])
        return keys, mat @ np.asarray(vec, dtype=np.float32)

    async def get(self, qvec) -> dict | None:
        keys, scores = await self._scores(qvec)
        if not keys or scores.max() < self.threshold:
            return None
        hit = await self.redis.hget(ANSWERS, keys[int(scores.argmax())])
        return json.loads(hit) if hit else None

    async def _drop_at_or_above(self, vec, cutoff: float) -> int:
        keys, scores = await self._scores(vec)
        drop = [k for k, s in zip(keys, scores) if s >= cutoff]
        if drop:
            await self.redis.hdel(VECS, *drop)
            await self.redis.hdel(ANSWERS, *drop)
        return len(drop)

    async def put(self, question: str, qvec, answer: dict) -> None:
        await self._drop_at_or_above(qvec, self.threshold)
        if await self.redis.hlen(VECS) >= self.max_entries:
            return
        key = uuid.uuid4().hex
        await self.redis.hset(VECS, key, np.asarray(qvec, dtype=np.float32).tobytes())
        await self.redis.hset(ANSWERS, key, json.dumps({**answer, "question": question}))

    async def invalidate(self, dvec) -> int:
        return await self._drop_at_or_above(dvec, self.invalidate_at)
