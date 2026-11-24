from datetime import datetime

from sqlalchemy import (JSON, Boolean, DateTime, ForeignKey, Identity, Integer, PrimaryKeyConstraint, String, Text, func,
                        select)
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


class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    doc_id: Mapped[str] = mapped_column(String(512))
    payload: Mapped[dict] = mapped_column(JSON, server_default=sql_text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending", index=True)
    proposed_by: Mapped[str | None] = mapped_column(String(64))
    conversation_id: Mapped[str | None] = mapped_column(String(32))
    decided_by: Mapped[str | None] = mapped_column(String(64))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Person(Base):
    __tablename__ = "people"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(256), unique=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list, server_default=sql_text("'[]'"))
    role: Mapped[str | None] = mapped_column(String(128))
    team: Mapped[str | None] = mapped_column(String(128))
    topics: Mapped[list] = mapped_column(JSON, default=list, server_default=sql_text("'[]'"))
    sources: Mapped[dict] = mapped_column(JSON, default=dict, server_default=sql_text("'{}'"))
    doc_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    search_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_text("false"))


class ConnectorSource(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    config: Mapped[dict] = mapped_column(JSON, server_default=sql_text("'{}'"))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceFile(Base):
    __tablename__ = "source_files"
    __table_args__ = (PrimaryKeyConstraint("source_id", "rel_path"),)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    rel_path: Mapped[str] = mapped_column(String(1024))
    doc_id: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def enqueue(session, kind: str, doc_id: str, payload: dict | None = None) -> None:
    session.add(Outbox(kind=kind, doc_id=doc_id, payload=payload or {}))


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
