import fakeredis
import numpy as np
import pytest

from orgbrain.cache import SemanticCache


@pytest.fixture
def anyio_backend():
    return "asyncio"


def unit(*v):
    a = np.array(v, dtype=np.float32)
    return (a / np.linalg.norm(a)).tolist()


@pytest.mark.anyio
async def test_hit_only_above_threshold_and_invalidation_by_similarity():
    cache = SemanticCache(fakeredis.aioredis.FakeRedis(), threshold=0.95, invalidate_at=0.5)
    assert await cache.get(unit(1, 0, 0)) is None
    await cache.put("how do I roll back perf-canary?", unit(1, 0, 0), {"text": "Pin the tag [a1b2c3]", "citations": []})
    await cache.put("who owns billing?", unit(0, 1, 0), {"text": "Grace", "citations": []})
    assert (await cache.get(unit(1, 0.1, 0)))["text"] == "Pin the tag [a1b2c3]"
    assert await cache.get(unit(1, 0.6, 0)) is None
    assert await cache.invalidate(unit(0.9, 0.1, 0.3)) == 1
    assert await cache.get(unit(1, 0, 0)) is None and (await cache.get(unit(0, 1, 0)))["text"] == "Grace"
