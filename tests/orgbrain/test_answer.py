import pytest

from orgbrain.answer import Citation, collect_hits, finalize
from orgbrain.instructions import instructions

SEARCH = {"results": [{"ref": "a1b2c3", "doc_id": "d1", "source": "confluence", "title": "Runbook", "snippet": "", "score": 1}]}
READ = {"ref": "d4e5f6", "doc_id": "d2", "source": "slack", "title": "eng-releases", "content": "", "truncated": False}


def test_collect_hits_from_search_and_read_doc():
    hits = collect_hits([SEARCH, READ, {"unrelated": 1}])
    assert hits == {"a1b2c3": {"doc_id": "d1", "source": "confluence", "title": "Runbook"},
                    "d4e5f6": {"doc_id": "d2", "source": "slack", "title": "eng-releases"}}


def test_finalize_maps_citations_and_reports_unknown_refs():
    a = finalize("Maria's runbook covers it [a1b2c3]. Alex flagged the rename [d4e5f6][ffffff].", collect_hits([SEARCH, READ]))
    assert a.citations == [Citation("a1b2c3", "d1", "confluence", "Runbook"), Citation("d4e5f6", "d2", "slack", "eng-releases")]
    assert a.unknown_refs == ["ffffff"] and not a.abstained


def test_an_answer_without_resolved_citations_counts_as_abstained():
    assert finalize("I couldn't find that. Grace's team owns billing, worth asking her.", {}).abstained
    assert finalize("Only an unknown ref [ffffff].", collect_hits([SEARCH])).abstained


def test_instructions_load_the_constitution_for_the_company():
    text = instructions("Acme")
    assert "You are a teammate at Acme." in text
    assert "{company}" not in text
    assert "## Hard limits" in text and "google_drive" in text


def test_custom_constitution_must_name_the_company(tmp_path):
    good = tmp_path / "good.md"
    good.write_text("You work at {company}.", encoding="utf8")
    assert instructions("Acme", good).startswith("You work at Acme.")
    bad = tmp_path / "bad.md"
    bad.write_text("No placeholder here.", encoding="utf8")
    with pytest.raises(ValueError, match="company"):
        instructions("Acme", bad)


def test_collect_hits_skips_results_that_are_not_documents():
    people = {"query": "renewals", "results": [{"id": "markus.klein", "name": "Markus Klein"}]}
    docs = {"results": [{"ref": "a1b2c3", "doc_id": "d1", "source": "jira", "title": "T"}]}
    assert collect_hits([people, docs]) == {"a1b2c3": {"doc_id": "d1", "source": "jira", "title": "T"}}
