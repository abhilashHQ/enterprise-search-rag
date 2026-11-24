"""People directory: Redwood employees found in the record, with an LLM-inferred role, team and topics.

  uv run --extra app orgbrain-people build --limit 5     # check five profiles first
  uv run --extra app orgbrain-people build               # everyone (gpt-oss-120b on Bedrock, under $0.50)
  uv run --extra app orgbrain-people admin markus.klein rachel.kim
"""

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import delete, select, update

from orgbrain.db import Person

DOMAIN = "redwoodinference.com"
ADDR = re.compile(r"([A-Z][\w'.-]+(?: [A-Z][\w'.-]+)+) <([\w.+-]+)@" + re.escape(DOMAIN) + ">")
ATTENDEES = re.compile(r"^Attendees:(.*)$", re.M)
ATTENDEE = re.compile(r"\s*([^;,(]+?)\s*\(Redwood\s*([^)]*)\)")
SPEAKER = re.compile(r"^([a-z][\w.-]*): ", re.M)
MAILBOX = re.compile(r"\b(?:team|ops|operations|desk|deals|distro|bot|portal|trials|notices|onboarding|demo|support|sales|"
                     r"sdrs|billing|finance|accounts|payable|procurement|legal|security|hr|product|success|leadership|"
                     r"redwood|inference)\b", re.I)
SAMPLES = 15
MIN_DOCS = 2


@dataclass
class PersonDraft:
    id: str
    name: str
    email: str | None = None
    aliases: set = field(default_factory=set)
    role_hints: list = field(default_factory=list)
    sources: Counter = field(default_factory=Counter)
    sample_doc_ids: list = field(default_factory=list)
    docs: set = field(default_factory=set)
    addresses: Counter = field(default_factory=Counter)

    def seen(self, doc_id: str, source: str) -> None:
        if doc_id in self.docs:
            return
        self.docs.add(doc_id)
        self.sources[source] += 1
        if len(self.sample_doc_ids) < SAMPLES * 4:
            self.sample_doc_ids.append(doc_id)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def is_mailbox(display_name: str) -> bool:
    """A shared mailbox, not a person: the display name holds a team or function word, or the company's name."""
    return bool(MAILBOX.search(display_name))


def _spells(local: str, name: str) -> bool:
    return re.split(r"[._-]", local) == [re.sub(r"[^a-z0-9]", "", t) for t in name.lower().split()]


def _canonical(p: PersonDraft) -> str:
    """The address that spells the full name (first.last before first_last), else the most used one."""
    return min(p.addresses, key=lambda a: (not _spells(a, p.name), "." not in a, -p.addresses[a], a))


def _add_role(p: PersonDraft, role: str) -> None:
    if role.strip() and role.strip() not in p.role_hints:
        p.role_hints.append(role.strip())


def extract(rows: Iterable[tuple[str, str, str, str]]) -> dict[str, PersonDraft]:
    """Redwood people keyed by id. One person per full display name, whatever address or meeting they appear under.
    Shared mailboxes are skipped; a first name alone (a Slack speaker, a one-word attendee) links to the one full-name
    person with that first name, or is dropped."""
    by_name: dict[str, PersonDraft] = {}
    firsts_seen: list[tuple[str, str, str, str]] = []
    for doc_id, source, _title, content in rows:
        head = content[:2000]
        if source == "gmail":
            for name, local in ADDR.findall(head):
                if is_mailbox(name):
                    continue
                p = by_name.setdefault(name.lower(), PersonDraft("", name))
                p.addresses[local.lower()] += 1
                p.seen(doc_id, source)
        elif source == "fireflies":
            for line in ATTENDEES.findall(head):
                for name, role in ATTENDEE.findall(line):
                    if len(name.split()) == 1:
                        firsts_seen.append((doc_id, source, name.lower(), role))
                    elif not is_mailbox(name):
                        p = by_name.setdefault(name.lower(), PersonDraft("", name))
                        _add_role(p, role)
                        p.seen(doc_id, source)
        elif source == "slack":
            firsts_seen += [(doc_id, source, n, "") for n in set(SPEAKER.findall(content))]
    firsts = Counter(p.name.split()[0].lower() for p in by_name.values())
    by_first = {p.name.split()[0].lower(): p for p in by_name.values() if firsts[p.name.split()[0].lower()] == 1}
    for doc_id, source, first, role in firsts_seen:
        if p := by_first.get(first):
            p.aliases.add(first)
            _add_role(p, role)
            p.seen(doc_id, source)
    people: dict[str, PersonDraft] = {}
    for p in by_name.values():
        local = _canonical(p) if p.addresses else None
        if local in people:
            local = None
        p.id, p.email = (local, f"{local}@{DOMAIN}") if local else (_slug(p.name), None)
        p.aliases |= {f"{a}@{DOMAIN}" for a in p.addresses if a != local}
        people[p.id] = p
    return people


def profile_prompt(d: PersonDraft, samples: list[tuple[str, str]]) -> str:
    docs = "\n".join(f"- {t}: {s}" for t, s in samples)
    hints = ", ".join(d.role_hints) or "none"
    return (f"These documents from the company Redwood Inference mention or were written by {d.name}"
            f"{f' ({d.email})' if d.email else ''}. Role hints from meeting attendee lists: {hints}.\n\n{docs}\n\n"
            "From these documents only, infer this person's job title, team, and up to 6 topics they work on. Use null "
            "when the documents don't say. Reply with one JSON object: "
            '{"role": string|null, "team": string|null, "topics": [string]}')


def parse_profile(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        obj = json.loads(m.group()) if m else {}
    except json.JSONDecodeError:
        obj = {}
    return {"role": obj.get("role"), "team": obj.get("team"), "topics": list(obj.get("topics") or [])[:6]}


def _row(p: Person) -> dict:
    return {"id": p.id, "name": p.name, "email": p.email, "aliases": p.aliases, "role": p.role, "team": p.team,
            "topics": p.topics, "sources": p.sources, "doc_count": p.doc_count, "is_admin": p.is_admin}


class PeopleStore:
    def __init__(self, sessions):
        self.sessions = sessions

    async def replace_all(self, people: list[dict]) -> None:
        async with self.sessions.begin() as s:
            admins = set((await s.execute(select(Person.id).where(Person.is_admin))).scalars())
            await s.execute(delete(Person))
            for p in people:
                text = " ".join([p["name"], p.get("email") or "", p.get("role") or "", p.get("team") or "",
                                 *p.get("topics", []), *p.get("aliases", [])]).lower()
                s.add(Person(**{k: p.get(k) for k in ("id", "name", "email", "role", "team")},
                             aliases=list(p.get("aliases", [])), topics=p.get("topics", []), sources=p.get("sources", {}),
                             doc_count=p.get("doc_count", 0), search_text=text, is_admin=p["id"] in admins))

    async def get(self, pid: str) -> dict | None:
        async with self.sessions() as s:
            p = await s.get(Person, pid)
            return _row(p) if p else None

    async def find(self, query: str, k: int = 10) -> list[dict]:
        terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 1]
        async with self.sessions() as s:
            rows = (await s.execute(select(Person))).scalars().all()
        if not terms:
            return [_row(p) for p in sorted(rows, key=lambda p: -p.doc_count)][:k]
        scored = [(sum(t in p.search_text for t in terms), p.doc_count, p) for p in rows]
        return [_row(p) for n, _, p in sorted(scored, key=lambda x: (-x[0], -x[1])) if n][:k]

    async def set_admin(self, ids: list[str], flag: bool) -> None:
        async with self.sessions.begin() as s:
            await s.execute(update(Person).where(Person.id.in_(ids)).values(is_admin=flag))

    async def admins(self) -> list[dict]:
        async with self.sessions() as s:
            return [_row(p) for p in (await s.execute(select(Person).where(Person.is_admin).order_by(Person.id))).scalars()]


def build(docstore, limit: int | None, llm: bool) -> list[dict]:
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor

    from orgbrain.qdrant_store import best_passage

    con = sqlite3.connect(f"file:{docstore.as_posix()}?mode=ro", uri=True)
    rows = con.execute("SELECT doc_id, source_type, title, content FROM docs "
                       "WHERE source_type IN ('gmail','fireflies','slack')")
    drafts = sorted((d for d in extract(rows).values() if d.email or len(d.docs) >= MIN_DOCS),
                    key=lambda d: -len(d.docs))[:limit]
    print(f"{len(drafts)} people", flush=True)
    profiles: dict[str, dict] = {d.id: {"role": None, "team": None, "topics": []} for d in drafts}
    if llm:
        from entsearch.llm import client, generate

        llm_client = client()

        def samples_for(ids: list[str]) -> dict[str, tuple[str, str]]:
            c = sqlite3.connect(f"file:{docstore.as_posix()}?mode=ro", uri=True)
            try:
                q = f"SELECT doc_id, title, content FROM docs WHERE doc_id IN ({','.join('?' * len(ids))})"
                return {r[0]: (r[1], r[2]) for r in c.execute(q, ids)}
            finally:
                c.close()

        def profile(d: PersonDraft):
            ids = d.sample_doc_ids[:SAMPLES]
            got = samples_for(ids)
            samples = [(got[i][0], best_passage(got[i][1], d.name)) for i in ids if i in got]
            return d.id, generate(llm_client, profile_prompt(d, samples), effort="low")

        cost, cached = 0.0, 0
        with ThreadPoolExecutor(8) as pool:
            for pid, gen in pool.map(profile, drafts):
                profiles[pid] = parse_profile(gen.text)
                cost, cached = cost + gen.cost, cached + gen.cached
        print(f"LLM cost ${cost:.4f} ({cached} of {len(drafts)} from cache)", flush=True)
    return [{"id": d.id, "name": d.name, "email": d.email, "aliases": sorted(d.aliases), **profiles[d.id],
             "sources": dict(d.sources), "doc_count": len(d.docs)} for d in drafts]


async def _main(a) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from orgbrain.config import Settings

    settings = Settings.from_env()
    store = PeopleStore(async_sessionmaker(create_async_engine(settings.database_url), expire_on_commit=False))
    if a.cmd == "build":
        people = await asyncio.to_thread(build, settings.docstore_path, a.limit, not a.no_llm)
        for p in people[:a.limit or 0]:
            print(f"{p['id']}: {p['role']} | {p['team']} | {', '.join(p['topics'])}")
        await store.replace_all(people)
        print(f"wrote {len(people)} people")
    elif a.cmd == "admin":
        await store.set_admin(a.ids, not a.remove)
        print("admins:", ", ".join(p["id"] for p in await store.admins()) or "none")
    else:
        for p in await (store.admins() if a.admins else store.find("", k=1000)):
            flag = "\tadmin" if p["is_admin"] else ""
            print(f"{p['id']}\t{p['name']}\t{p['role']}\t{p['team']}\t{p['doc_count']}{flag}")


def main() -> None:
    p = argparse.ArgumentParser(prog="orgbrain-people", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--limit", type=int, help="only the N most active people")
    b.add_argument("--no-llm", action="store_true")
    ad = sub.add_parser("admin")
    ad.add_argument("ids", nargs="+")
    ad.add_argument("--remove", action="store_true")
    ls = sub.add_parser("list")
    ls.add_argument("--admins", action="store_true")
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(_main(p.parse_args()))


if __name__ == "__main__":
    main()
