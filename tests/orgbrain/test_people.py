import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from orgbrain.db import Base, ConversationStore
from orgbrain.people import PeopleStore, extract, is_mailbox, parse_profile

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


DEDUPE_ROWS = [
    ("f9", "fireflies", "Kickoff", "Attendees: Markus Klein (Redwood CSM), Markus (Redwood CSM), Jordan (Redwood AE)\n"),
    ("g7", "gmail", "Ping", "From: Markus Klein <markus_klein@redwoodinference.com>\nTo: Legal Ops <legal_ops@redwoodinference.com>\n"),
    ("g8", "gmail", "Ping 2", "From: Markus Klein <markus.klein@redwoodinference.com>\nCc: Markus Klein <mk@redwoodinference.com>\n"
                              "To: Finance Ops <finance@redwoodinference.com>\n"),
    ("g9", "gmail", "Ping 3", "From: Markus Klein <mk@redwoodinference.com>\n"),
]


def test_one_person_per_display_name_whatever_the_address_or_row_order():
    people = extract(DEDUPE_ROWS)
    assert sorted(people) == ["markus.klein"]
    mk = people["markus.klein"]
    assert mk.email == "markus.klein@redwoodinference.com"
    assert {"markus_klein@redwoodinference.com", "mk@redwoodinference.com"} <= mk.aliases
    assert len(mk.docs) == 4 and mk.role_hints == ["CSM"]


def test_shared_mailboxes_are_not_people():
    assert all(is_mailbox(n) for n in ["Legal Ops", "Finance Ops", "Customer Success Team", "Redwood Demo", "Signup Bot",
                                       "Accounts Payable", "Exec Leadership", "AM Redwood Security", "Deal Desk"])
    assert not any(is_mailbox(n) for n in ["Markus Klein", "Grace O'Connor", "Dr. Aisha Rahman", "Omar El-Sayed"])


def test_first_name_only_attendees_link_to_a_unique_full_name_or_are_dropped():
    people = extract(DEDUPE_ROWS[:1])
    assert sorted(people) == ["markus-klein"] and "markus" in people["markus-klein"].aliases
