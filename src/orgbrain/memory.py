from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from orgbrain.db import Memory, Person, enqueue

MOVES = {("pending", "approve"): "approved", ("pending", "reject"): "rejected", ("approved", "forget"): "forgotten"}


def _row(m: Memory) -> dict:
    return {"id": m.id, "text": m.text, "status": m.status, "proposed_by": m.proposed_by,
            "conversation_id": m.conversation_id, "decided_by": m.decided_by,
            "decided_at": m.decided_at.isoformat() if m.decided_at else None,
            "created_at": m.created_at.isoformat() if m.created_at else None}


class MemoryStore:
    def __init__(self, sessions):
        self.sessions = sessions

    async def propose(self, text: str, proposed_by: str | None = None, conversation_id: str | None = None) -> int:
        async with self.sessions.begin() as s:
            m = Memory(text=text.strip(), proposed_by=proposed_by, conversation_id=conversation_id)
            s.add(m)
            await s.flush()
            return m.id

    async def list(self, status: str | None = None) -> list[dict]:
        q = select(Memory).order_by(Memory.id.desc())
        if status:
            q = q.where(Memory.status == status)
        async with self.sessions() as s:
            return [_row(m) for m in (await s.execute(q)).scalars()]

    async def decide(self, memory_id: int, action: str, user_id: str) -> dict:
        async with self.sessions.begin() as s:
            user = await s.get(Person, user_id)
            if user is None or not user.is_admin:
                raise PermissionError(f"{user_id} is not an admin")
            m = await s.get(Memory, memory_id)
            if m is None:
                raise LookupError(f"no memory {memory_id}")
            new = MOVES.get((m.status, action))
            if new is None:
                raise ValueError(f"cannot {action} a {m.status} memory")
            m.status, m.decided_by, m.decided_at = new, user_id, datetime.now(UTC)
            doc_id = f"memory:{m.id}"
            if new == "approved":
                proposer = await s.get(Person, m.proposed_by) if m.proposed_by else None
                who = proposer.name if proposer else (m.proposed_by or "a teammate")
                content = f"{m.text}\n\nProposed by {who}, approved by {user.name} on {m.decided_at:%Y-%m-%d}."
                enqueue(s, "upsert", doc_id, {"source": "memory", "title": f"Memory: {m.text[:80]}", "content": content})
            elif new == "forgotten":
                enqueue(s, "delete", doc_id)
            await s.flush()
            return _row(m)


@dataclass
class AppStores:
    memories: MemoryStore
    people: "object | None" = None
