import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from orgbrain.db import Base, ConversationStore
from orgbrain.people import PeopleStore, extract, parse_profile

ROWS = [
    ("g1", "gmail", "Escalation", "From: Alyssa Chen <alyssa.chen@cascadefg.com>\nTo: Markus Klein <markus.klein@redwoodinference.com>\n"
                                  "Cc: Rachel Kim <rachel.kim@redwoodinference.com>\nDate: Tue\n\nbody"),
    ("g2", "gmail", "Renewal", "From: Markus Klein <markus.klein@redwoodinference.com>\nTo: a@b.com\n\nbody"),
    ("f1", "fireflies", "Tethys sync", "transcript:\nAttendees: Maya Patel (Redwood AE); Markus Klein (Redwood CSM); Sofia Alvarez (Tethys)\n"),
    ("s1", "slack", "eng-runtime", "markus: rolling back\nmaya: ok\nrachel: on it"),
]


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_extract_keeps_redwood_people_and_links_slack_first_names():
    people = extract(ROWS)
    assert sorted(people) == ["markus.klein", "maya-patel", "rachel.kim"]
    mk = people["markus.klein"]
    assert mk.name == "Markus Klein" and mk.email == "markus.klein@redwoodinference.com"
    assert dict(mk.sources) == {"gmail": 2, "fireflies": 1, "slack": 1} and mk.role_hints == ["CSM"]
    assert people["maya-patel"].email is None and people["maya-patel"].role_hints == ["AE"]


def test_parse_profile_reads_the_json_object():
    text = 'Sure.\n{"role": "Customer Success Manager", "team": "Customer Success", "topics": ["renewals", "upgrades"]}'
    assert parse_profile(text) == {"role": "Customer Success Manager", "team": "Customer Success",
                                   "topics": ["renewals", "upgrades"]}
    assert parse_profile("no json") == {"role": None, "team": None, "topics": []}


@pytest.mark.anyio
async def test_find_ranks_by_matched_terms_then_activity():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = PeopleStore(ConversationStore(engine).sessions)
    await store.replace_all([
        {"id": "markus.klein", "name": "Markus Klein", "email": "markus.klein@redwoodinference.com", "role": "CSM",
         "team": "Customer Success", "topics": ["renewals", "rollback"], "sources": {"gmail": 2}, "doc_count": 2},
        {"id": "maya-patel", "name": "Maya Patel", "email": None, "role": "Account Executive", "team": "Partnerships",
         "topics": ["partner GTM"], "sources": {"fireflies": 1}, "doc_count": 9},
    ])
    assert [p["id"] for p in await store.find("customer success renewals")] == ["markus.klein"]
    assert [p["id"] for p in await store.find("Maya")] == ["maya-patel"]
    await store.set_admin(["markus.klein"], True)
    assert [p["id"] for p in await store.admins()] == ["markus.klein"] and (await store.get("markus.klein"))["is_admin"]


def test_extract_reads_comma_separated_attendees():
    rows = [("f2", "fireflies", "Aster sync", "Attendees: Liam Ortiz (Redwood AE), Priya Shah (Redwood SE), Omar Khan (Aster CTO)\n")]
    people = extract(rows)
    assert sorted(people) == ["liam-ortiz", "priya-shah"] and people["priya-shah"].role_hints == ["SE"]
    assert people["priya-shah"].name == "Priya Shah"
