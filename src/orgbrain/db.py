from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Identity, Integer, String, Text, func, select
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    runtime: Mapped[str] = mapped_column(String(32))
    runtime_session_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, server_default=sql_text("'[]'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationStore:
    def __init__(self, engine: AsyncEngine):
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def runtime_session(self, cid: str) -> str | None:
        async with self.sessions() as s:
            c = await s.get(Conversation, cid)
            return c.runtime_session_id if c else None

    async def save_turn(self, cid: str, runtime: str, session_id: str | None, question: str, answer_text: str,
                        citations: list[dict]) -> None:
        async with self.sessions.begin() as s:
            c = await s.get(Conversation, cid)
            if c is None:
                c = Conversation(id=cid, runtime=runtime)
                s.add(c)
            if session_id:
                c.runtime_session_id = session_id
            await s.flush()
            s.add_all([Message(conversation_id=cid, role="user", text=question, citations=[]),
                       Message(conversation_id=cid, role="assistant", text=answer_text, citations=citations)])

    async def messages(self, cid: str) -> list[dict]:
        async with self.sessions() as s:
            rows = (await s.execute(select(Message).where(Message.conversation_id == cid).order_by(Message.id))).scalars()
            return [{"role": m.role, "text": m.text, "citations": m.citations} for m in rows]
